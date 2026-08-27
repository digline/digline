"""The half of a provider target that ships with digline.

No SDK is imported here and no socket is opened. What is checked is the part
that every provider shares and that a plugin cannot get wrong on its own: the
substitution, the arithmetic, and the two refusals that have to happen before
the first paid call.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from digline.core import Contains, Output
from digline.run import Case, HasArtifacts, Preflight, Suite, execute
from digline.targets import (
    ModelPrice,
    Pricing,
    PromptTemplate,
    ProviderTarget,
    UnknownModelError,
    Usage,
)

PRICES = Pricing({"m1": ModelPrice(3.0, 15.0, 0.30)})


class FakeTarget(ProviderTarget):
    """A `ProviderTarget` with the provider replaced by a canned answer."""

    def __init__(self, *args: object, reply: str = "ok", **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self.reply = reply
        self.seen: list[tuple[str, str | None]] = []

    def _complete(self, prompt: str, system: str | None) -> tuple[str, Usage]:
        self.seen.append((prompt, system))
        return self.reply, Usage(input_tokens=1000, output_tokens=200)


@pytest.fixture
def prompt(tmp_path: Path) -> Path:
    path = tmp_path / "answer.md"
    path.write_text("Answer {question} for {customer}.\n", encoding="utf-8")
    return path


# --------------------------------------------------------------------------- #
# Substitution
# --------------------------------------------------------------------------- #


def test_braces_that_are_not_variables_are_left_alone(tmp_path: Path) -> None:
    """Real prompts carry JSON. `str.format` raises on every one of them, which
    is the whole reason this is a regex."""
    template = PromptTemplate.from_text(
        'Reply as {tone}. Shape: {"role": "user", "content": ""}. Braces: {} {{'
    )
    assert template.variables == frozenset({"tone"})
    rendered = template.render({"tone": "brief"})
    assert '{"role": "user", "content": ""}' in rendered
    assert "{} {{" in rendered


def test_values_render_the_same_way_every_time() -> None:
    """The same vars must give the same prompt, here and on the next machine."""
    template = PromptTemplate.from_text("{n} {flag} {payload} {text}")
    once = template.render(
        {"n": 3, "flag": True, "payload": {"b": 2, "a": [1, None]}, "text": "x"}
    )
    twice = template.render(
        {"payload": {"a": [1, None], "b": 2}, "text": "x", "flag": True, "n": 3}
    )
    assert once == twice
    assert once == '3 True {"a":[1,null],"b":2} x'


def test_a_value_with_no_deterministic_form_is_refused() -> None:
    """An object's `str()` may carry a memory address, and a prompt that differs
    per process is a prompt nobody can reproduce."""
    template = PromptTemplate.from_text("{thing}")
    with pytest.raises(ValueError, match="deterministic"):
        template.render({"thing": object()})


def test_a_missing_file_fails_when_the_suite_is_imported(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        PromptTemplate(tmp_path / "absent.md")


# --------------------------------------------------------------------------- #
# Money
# --------------------------------------------------------------------------- #


def test_the_arithmetic_is_per_million_tokens() -> None:
    assert PRICES.cost("m1", Usage(1_000_000, 0)) == pytest.approx(3.0)
    assert PRICES.cost("m1", Usage(0, 1_000_000)) == pytest.approx(15.0)
    assert PRICES.cost("m1", Usage(0, 0, 1_000_000)) == pytest.approx(0.30)


def test_an_unknown_model_raises_rather_than_costing_nothing() -> None:
    """Fixed decision 3, in the one place it is easiest to break: a model priced
    at zero passes every `CostBudget` there is, and does it quietly."""
    with pytest.raises(UnknownModelError, match="no price"):
        PRICES.cost("m2", Usage(10, 10))


def test_cache_writes_are_priced_separately() -> None:
    """A separate count because it is billed at a separate rate, and because the
    provider does not fold it into `input_tokens`. (friction 25)"""
    priced = Pricing({"m1": ModelPrice(3.0, 15.0, 0.30, 3.75)})
    assert priced.cost("m1", Usage(0, 0, 0, 1_000_000)) == pytest.approx(3.75)


def test_cache_writes_with_no_write_rate_raise() -> None:
    lean = Pricing({"m1": ModelPrice(3.0, 15.0, 0.30)})
    with pytest.raises(UnknownModelError, match="cache-write"):
        lean.cost("m1", Usage(10, 10, 0, 5))


def test_cached_reads_with_no_cached_rate_raise() -> None:
    """Undercounting a cost is the failure that reads as good news."""
    lean = Pricing({"m1": ModelPrice(3.0, 15.0)})
    assert lean.cost("m1", Usage(10, 10)) > 0
    with pytest.raises(UnknownModelError, match="cached-read"):
        lean.cost("m1", Usage(10, 10, 5))


def test_a_price_is_corrected_in_one_argument() -> None:
    """Lists change on the provider's schedule. digline does not cut a release
    because a price moved."""
    corrected = PRICES.override("m1", ModelPrice(2.0, 10.0, 0.20))
    assert corrected.cost("m1", Usage(1_000_000, 0)) == pytest.approx(2.0)
    # And the original is untouched: a price list is a value.
    assert PRICES.cost("m1", Usage(1_000_000, 0)) == pytest.approx(3.0)


# --------------------------------------------------------------------------- #
# The Response the base builds
# --------------------------------------------------------------------------- #


def test_the_response_carries_the_prompt_the_cost_and_the_latency(
    prompt: Path,
) -> None:
    target = FakeTarget(prompt, "m1", pricing=PRICES, reply="Rome.")
    response = target(Case(id="c1", vars={"question": "capital", "customer": "ACME"}))

    assert response.output == "Rome."
    assert response.input == "Answer capital for ACME.\n"
    assert response.cost_usd == pytest.approx(1000 * 3.0 / 1e6 + 200 * 15.0 / 1e6)
    assert response.latency_ms is not None and response.latency_ms >= 0.0
    assert response.metadata["model"] == "m1"
    assert response.metadata["input_tokens"] == 1000


def test_the_system_prompt_is_rendered_too(tmp_path: Path, prompt: Path) -> None:
    system = tmp_path / "system.md"
    system.write_text("You serve {customer}.", encoding="utf-8")
    target = FakeTarget(prompt, "m1", pricing=PRICES, system_file=system)
    target(Case(id="c1", vars={"question": "q", "customer": "ACME"}))
    assert target.seen[0][1] == "You serve ACME."


def test_giving_both_a_system_string_and_a_system_file_is_refused(
    tmp_path: Path, prompt: Path
) -> None:
    (tmp_path / "system.md").write_text("s", encoding="utf-8")
    with pytest.raises(ValueError, match="not both"):
        FakeTarget(
            prompt, "m1", pricing=PRICES, system="s", system_file=tmp_path / "system.md"
        )


# --------------------------------------------------------------------------- #
# The two things a target knows that the suite cannot
# --------------------------------------------------------------------------- #


def test_the_target_names_its_files_so_the_suite_need_not(
    tmp_path: Path, prompt: Path
) -> None:
    system = tmp_path / "system.md"
    system.write_text("You are terse.", encoding="utf-8")
    target = FakeTarget(prompt, "m1", pricing=PRICES, system_file=system)
    assert isinstance(target, HasArtifacts)
    assert set(target.artifacts()) == {prompt, system}


def test_an_inline_system_prompt_is_not_an_artifact(prompt: Path) -> None:
    """It is already in the suite's source; recording it would record it twice."""
    target = FakeTarget(prompt, "m1", pricing=PRICES, system="terse")
    assert list(target.artifacts()) == [prompt]


def test_preflight_names_every_gap_at_once(prompt: Path) -> None:
    """One error before the first call, not a failure on case thirty-seven with
    thirty-six paid calls behind it."""
    target = FakeTarget(prompt, "m1", pricing=PRICES)
    assert isinstance(target, Preflight)
    with pytest.raises(ValueError) as caught:
        target.preflight(
            [Case(id="c1", vars={"question": "q"}), Case(id="c2", vars={})]
        )
    message = str(caught.value)
    assert "c1" in message and "customer" in message
    assert "c2" in message and "question" in message


def test_preflight_checks_the_price_before_the_call_not_after(prompt: Path) -> None:
    """The other way round, the suite runs to the end and then cannot say what
    it cost."""
    target = FakeTarget(prompt, "unpriced", pricing=PRICES)
    with pytest.raises(ValueError, match="has no price"):
        target.preflight([Case(id="c1", vars={"question": "q", "customer": "A"})])


def test_a_suspended_case_is_not_asked_for_variables(prompt: Path) -> None:
    """The driver will not run it, so demanding its vars would refuse a suite
    over a case nobody is going to call."""
    target = FakeTarget(prompt, "m1", pricing=PRICES)
    target.preflight([Case(id="c1", vars={}, suspended="the API is down")])


def test_execute_asks_before_it_calls(prompt: Path) -> None:
    """The driver is where it has to happen: `calibrate.py` in the guide never
    goes through the CLI."""
    suite = Suite(
        tenant="t",
        environment="e",
        name="s",
        assertions=[Contains(needle="x")],
        cases=[Case(id="c1", vars={"question": "q"})],
    )
    target = FakeTarget(prompt, "m1", pricing=PRICES)
    with pytest.raises(ValueError, match="customer"):
        execute(suite, target, created_at="2026-08-27T10:00:00+00:00")
    assert target.seen == [], "the provider was called despite the gap"


def test_a_plain_function_target_is_left_alone() -> None:
    """Most targets are functions. Asking is optional, which is what `Protocol`
    plus `isinstance` buys."""
    suite = Suite(
        tenant="t",
        environment="e",
        name="s",
        assertions=[Contains(needle="x")],
        cases=[Case(id="c1")],
    )
    from digline.run import Response

    run = execute(
        suite,
        lambda case: Response(output="x", cost_usd=0.0),
        created_at="2026-08-27T10:00:00+00:00",
    )
    assert len(run.results) == 1


# --------------------------------------------------------------------------- #
# What a suite that judges a shape needs (friction 26)
# --------------------------------------------------------------------------- #


class JsonTarget(FakeTarget):
    """A target whose replies are judged as structure, not as text."""

    def parse(self, text: str) -> Output:
        parsed: Output = json.loads(text)
        return parsed


def test_the_reply_can_be_parsed_into_the_shape_the_suite_judges(
    prompt: Path,
) -> None:
    """A provider returns text; `JsonSchema` and anything reading
    `output["score"]` need the shape. Without a hook the suite had to give up on
    one or the other."""
    target = JsonTarget(prompt, "m1", pricing=PRICES, reply='{"score": 4}')
    response = target(Case(id="c1", vars={"question": "q", "customer": "A"}))
    assert response.output == {"score": 4}
    # The text that produced it is still recorded as the input.
    assert response.input == "Answer q for A.\n"


def test_a_reply_that_will_not_parse_becomes_an_error_not_a_failure(
    prompt: Path,
) -> None:
    """The model failed to answer in the agreed shape. That is neither a pass
    nor a regression, and the driver turning a raise into `error` is what says
    so."""
    suite = Suite(
        tenant="t",
        environment="e",
        name="s",
        assertions=[Contains(needle="x")],
        cases=[Case(id="c1", vars={"question": "q", "customer": "A"})],
    )
    target = JsonTarget(prompt, "m1", pricing=PRICES, reply="not json at all")
    run = execute(suite, target, created_at="2026-08-27T10:00:00+00:00")
    (case,) = run.results
    assert [v.status for v in case.verdicts] == ["error"]


def test_by_default_the_reply_is_the_output(prompt: Path) -> None:
    target = FakeTarget(prompt, "m1", pricing=PRICES, reply="plain text")
    assert target(Case(id="c1", vars={"question": "q", "customer": "A"})).output == (
        "plain text"
    )
