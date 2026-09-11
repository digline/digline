"""The half of a provider target that ships with digline.

No SDK is imported here and no socket is opened. What is checked is the part
that every provider shares and that a plugin cannot get wrong on its own: the
substitution, the arithmetic, and the two refusals that have to happen before
the first paid call.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from digline.core import Contains, Finish, Output
from digline.run import Case, HasArtifacts, Preflight, Suite, execute
from digline.targets import (
    Completion,
    HttpTarget,
    ModelPrice,
    Pricing,
    PromptTemplate,
    ProviderTarget,
    UnknownModelError,
    Usage,
)

PRICES = Pricing({"m1": ModelPrice(3.0, 15.0, 0.30)})


class FakeTarget(ProviderTarget):
    """A `ProviderTarget` with the provider replaced by a canned answer.

    **Returns the pair**, and keeps returning it: that is the compatibility
    guarantee of ADR 0004 §6 under test on every assertion in this file. A
    plugin written before the record keeps working, and this fake not having to
    change is how that is proved.
    """

    def __init__(self, *args: object, reply: str = "ok", **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self.reply = reply
        self.seen: list[tuple[str, str | None]] = []

    def _complete(self, prompt: str, system: str | None) -> tuple[str, Usage]:
        self.seen.append((prompt, system))
        return self.reply, Usage(input_tokens=1000, output_tokens=200)


class RecordTarget(ProviderTarget):
    """The same, returning the record and whatever it was told to report."""

    provider = "fake"

    def __init__(
        self, *args: object, replies: list[Completion], **kwargs: object
    ) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self.replies = list(replies)

    def _complete(self, prompt: str, system: str | None) -> Completion:
        return self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]


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


# --------------------------------------------------------------------------- #
# HttpTarget: an application digline cannot import (friction 14)
# --------------------------------------------------------------------------- #


@pytest.fixture
def service() -> Iterator[str]:
    """A two-route service on an ephemeral port. No mocking of urllib."""

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length") or 0)
            asked = json.loads(self.rfile.read(length).decode("utf-8"))
            body = json.dumps(
                {
                    "data": {"answer": f"heard {asked['text']}"},
                    "usage": {"cost_usd": 0.002, "elapsed_ms": 12.5},
                }
            ).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None: ...

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{httpd.server_address[1]}/x"
    finally:
        httpd.shutdown()


def an_http_target(url: str, **kwargs: object) -> HttpTarget:
    return HttpTarget(
        url,
        request=lambda case: {"text": case.vars["text"]},
        output_path="data.answer",
        **kwargs,  # type: ignore[arg-type]
    )


def test_it_posts_the_body_and_reads_the_answer_out(service: str) -> None:
    response = an_http_target(service)(Case(id="c", vars={"text": "hello"}))
    assert response.output == "heard hello"
    assert response.input == '{"text": "hello"}'


def test_cost_and_latency_come_from_the_paths_that_name_them(service: str) -> None:
    target = an_http_target(
        service, cost_path="usage.cost_usd", latency_from_response="usage.elapsed_ms"
    )
    response = target(Case(id="c", vars={"text": "hello"}))
    assert response.cost_usd == 0.002
    # The service's own number, not the round trip: a path was given.
    assert response.latency_ms == 12.5


def test_without_a_path_the_round_trip_is_measured(service: str) -> None:
    """Which includes the network, and is a different number measuring a
    different thing — so it is what you get only when you did not say."""
    response = an_http_target(service)(Case(id="c", vars={"text": "hello"}))
    assert response.latency_ms is not None and response.latency_ms != 12.5


def test_a_path_that_is_not_there_says_what_was(service: str) -> None:
    target = an_http_target(service)
    target.output_path = "data.missing"
    with pytest.raises(ValueError, match="no 'missing' in answer"):
        target(Case(id="c", vars={"text": "hello"}))


def test_preflight_refuses_before_the_first_case_when_nothing_answers() -> None:
    """The alternative is finding out one case at a time, with a run half
    written and a stack trace per case."""
    target = an_http_target("http://127.0.0.1:9/none")
    with pytest.raises(ValueError, match="nothing answered"):
        target.preflight([Case(id="c", vars={"text": "x"})])


def test_preflight_accepts_a_service_that_answers_at_all(service: str) -> None:
    """A 405 to a HEAD is an answer: something is there and the request was
    wrong, which is a different problem from nothing being there."""
    an_http_target(service).preflight([Case(id="c", vars={"text": "x"})])


# --------------------------------------------------------------------------- #
# What the application says it was set up as (ADR 0005 §8)
# --------------------------------------------------------------------------- #


class Stub:
    """A service whose reported configuration a test can move under it."""

    url: str = ""
    config: object = {
        "provider": "openai",
        "model": "gpt-4o-mini",
        "temperature": 0.0,
        "max_tokens": 512,
    }


@pytest.fixture
def declaring_service() -> Iterator[Stub]:
    """The Java example's shape: data, usage, and how the model was set up."""
    stub = Stub()

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length") or 0)
            asked = json.loads(self.rfile.read(length).decode("utf-8"))
            body = json.dumps(
                {
                    "data": {"answer": f"heard {asked['text']}"},
                    "usage": {"cost_usd": 0.002, "elapsed_ms": 12.5},
                    "config": stub.config,
                }
            ).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None: ...

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    stub.url = f"http://127.0.0.1:{httpd.server_address[1]}/x"
    try:
        yield stub
    finally:
        httpd.shutdown()


def a_declaring_target(stub: Stub) -> HttpTarget:
    return an_http_target(stub.url, config_path="config")


def test_the_configuration_the_application_reports_is_recorded(
    declaring_service: Stub,
) -> None:
    """The point of §8: the model call happened on the other side of HTTP, so
    the only party who can say which model answered is the application."""
    target = a_declaring_target(declaring_service)
    assert target.config == {}, "nothing is known before a case is answered"

    target(Case(id="c", vars={"text": "hello"}))
    assert target.config == {
        "provider": "openai",
        "model": "gpt-4o-mini",
        "temperature": 0.0,
        "max_tokens": 512,
    }


def test_without_a_config_path_the_target_declares_nothing(
    declaring_service: Stub,
) -> None:
    """Absent stays absent: every suite written before §8 is unaffected."""
    target = an_http_target(declaring_service.url)
    target(Case(id="c", vars={"text": "hello"}))
    assert target.config == {}


def test_a_null_is_not_sent_rather_than_sent_as_null(
    declaring_service: Stub,
) -> None:
    """`sent()`'s rule, arriving over the wire: "we left it alone, and the
    provider's default applied" is a different fact from "we sent nothing"."""
    declaring_service.config = {
        "provider": "openai",
        "model": "gpt-4o-mini",
        "temperature": None,
    }
    target = a_declaring_target(declaring_service)
    target(Case(id="c", vars={"text": "hello"}))
    assert target.config == {"provider": "openai", "model": "gpt-4o-mini"}


def test_a_reported_endpoint_is_reduced_to_its_host(declaring_service: Stub) -> None:
    """The credential guard, and the reason it is applied here rather than
    trusted: an application reporting its own endpoint sends the whole URL."""
    declaring_service.config = {
        "provider": "openai",
        "model": "gpt-4o-mini",
        "base_url": "https://user:secret@llm-gw.internal.acme-bank.it:8443/v1",
    }
    target = a_declaring_target(declaring_service)
    target(Case(id="c", vars={"text": "hello"}))
    assert target.config["base_url"] == "llm-gw.internal.acme-bank.it:8443"
    assert "secret" not in json.dumps(target.config)


@pytest.mark.parametrize(
    ("reported", "message"),
    [
        (
            ["openai", "gpt-4o-mini"],
            "holds a list, not an object",
        ),
        (
            {"provider": "openai", "model": "m", "customer_id": "acme-4821"},
            "customer_id, which is not part of the configuration contract",
        ),
        (
            {"provider": "openai", "model": "m", "temperature": {"value": 0.7}},
            "records 'temperature' as a dict, which is not a scalar",
        ),
        (
            {"provider": "openai", "temperature": 0.0},
            "gives no model",
        ),
        (
            {"provider": "", "model": "m"},
            "gives no provider",
        ),
    ],
)
def test_a_malformed_configuration_is_refused_by_name(
    declaring_service: Stub, reported: object, message: str
) -> None:
    """Refused rather than repaired, and refused where the reader can act:
    every message names `config`, the path it was read from."""
    declaring_service.config = reported
    target = a_declaring_target(declaring_service)
    with pytest.raises(ValueError, match=message):
        target(Case(id="c", vars={"text": "hello"}))


def test_an_unknown_key_is_refused_with_the_allowed_set(
    declaring_service: Stub,
) -> None:
    """Dropping it silently is how a team believes they recorded something they
    did not — and it is where an account identifier would arrive."""
    declaring_service.config = {"provider": "o", "model": "m", "tenant_id": "acme"}
    target = a_declaring_target(declaring_service)
    with pytest.raises(ValueError, match="Allowed: base_url, json_mode, max_tokens"):
        target(Case(id="c", vars={"text": "hello"}))


def test_a_service_that_changes_model_part_way_errors_that_case(
    declaring_service: Stub,
) -> None:
    """One run measures one system (ADR 0005 §6). Recording either answer would
    be a fact nobody established; merging them would describe a set-up nobody
    built."""
    target = a_declaring_target(declaring_service)
    target(Case(id="first", vars={"text": "hello"}))

    declaring_service.config = {"provider": "openai", "model": "gpt-4o"}
    with pytest.raises(ValueError, match="a different configuration part way"):
        target(Case(id="seventh", vars={"text": "hello"}))
    # The first answer stands: the run still says what it measured.
    assert target.config["model"] == "gpt-4o-mini"


def test_the_run_records_what_the_endpoint_declared(declaring_service: Stub) -> None:
    """End to end through `execute()`, which is what made the second
    `target_config` read necessary: there is nothing to declare until a case has
    been answered."""
    suite = Suite(
        tenant="helpdesk",
        environment="staging",
        name="routing",
        assertions=[Contains(needle="heard")],
        cases=[Case(id="c", vars={"text": "hello"})],
    )
    run = execute(
        suite, a_declaring_target(declaring_service), created_at="2026-09-01T00:00:00Z"
    )
    assert run.target_config.values["model"] == "gpt-4o-mini"
    assert run.target_config.recorded


def test_a_credential_in_the_url_never_reaches_a_message() -> None:
    """`https://user:sk-secret@gateway/v1` is a URL people really write, and the
    sentence this target raises when nothing answers used to carry it whole — to
    stderr, and in CI to a build log, which is often read more widely than the
    repository is.

    ADR 0005 §2 already reduced `base_url` to its host for exactly this reason.
    A target that took its endpoint under a different name was not covered by
    that decision, only by the fact that nobody had looked.
    """
    secret = "sk-SUPERSECRET"  # noqa: S105 — the thing being kept out of a message
    target = HttpTarget(
        f"http://user:{secret}@127.0.0.1:1/answer",
        body={"question": "case.vars.question"},
        output_path="data.answer",
    )
    with pytest.raises(ValueError) as refusal:
        target.preflight([Case(id="one", vars={"question": "q"})])

    said = str(refusal.value)
    assert secret not in said
    assert "user" not in said
    # Still names the endpoint, or the message would have lost its diagnosis
    # along with the credential.
    assert "127.0.0.1:1" in said
    # The URL itself is untouched: it is what gets called, and only what is
    # *said* about it is reduced.
    assert target.url.endswith("@127.0.0.1:1/answer")


def test_the_endpoint_is_still_named_when_there_is_no_credential() -> None:
    """The guard on the guard: reducing to the host must not reduce to nothing,
    or every diagnostic sentence about a down endpoint becomes the same one."""
    target = HttpTarget(
        "http://127.0.0.1:1/answer",
        body={"question": "case.vars.question"},
        output_path="data.answer",
    )
    with pytest.raises(ValueError, match="nothing answered at 127.0.0.1:1"):
        target.preflight([Case(id="one", vars={"question": "q"})])


# --------------------------------------------------------------------------- #
# The record, and the identity it carries (ADR 0004 §6, ADR 0005 §9)
# --------------------------------------------------------------------------- #


def a_case() -> Case:
    return Case(id="c1", vars={"question": "q", "customer": "n"})


def a_record(
    *,
    finish: Finish | None = None,
    tools: tuple[str, ...] | None = None,
    model: str | None = None,
    fingerprint: str | None = None,
) -> Completion:
    return Completion(
        text="ok",
        usage=Usage(input_tokens=10, output_tokens=4),
        finish=finish,
        tools=tools,
        model=model,
        fingerprint=fingerprint,
    )


def recorder(prompt: Path, *replies: Completion) -> RecordTarget:
    return RecordTarget(prompt, "m1", pricing=PRICES, replies=list(replies))


def test_a_target_that_returns_the_pair_reports_no_trajectory(prompt: Path) -> None:
    """The reading that keeps `ToolsCalled` honest: a plugin returning the pair
    has not said the model called no tools, it has said nothing about them."""
    response = FakeTarget(prompt, "m1", pricing=PRICES)(a_case())
    assert "tools" not in response.metadata
    assert "finish" not in response.metadata


def test_the_trajectory_reaches_the_response_metadata(prompt: Path) -> None:
    target = recorder(prompt, a_record(finish="tool_use", tools=("search",)))
    response = target(a_case())
    assert response.metadata["tools"] == ["search"]
    assert response.metadata["finish"] == "tool_use"


def test_the_observed_identity_is_empty_until_a_case_has_run(prompt: Path) -> None:
    """Which is why `execute()` reads a target's configuration after the last
    case as well as before the first."""
    target = recorder(prompt, a_record(model="m1-20260101"))
    assert "resolved_model" not in target.config
    target(a_case())
    assert target.config["resolved_model"] == "m1-20260101"


def test_a_provider_that_names_no_model_records_none(prompt: Path) -> None:
    """Bedrock Converse, every run. Absent rather than the requested id echoed
    back, which would manufacture the fact the field exists to obtain."""
    target = recorder(prompt, a_record(finish="stop"))
    target(a_case())
    assert "resolved_model" not in target.config
    assert target.config["model"] == "m1"


def test_a_model_that_rolled_part_way_through_raises_from_the_call(
    prompt: Path,
) -> None:
    """Which is how the driver errors that one case (ADR 0005 §9). The run is
    still written and every other case keeps its verdicts."""
    target = recorder(
        prompt, a_record(model="m1-20260101"), a_record(model="m1-20260301")
    )
    target(a_case())
    with pytest.raises(ValueError, match="One run measures one system"):
        target(a_case())


def test_a_fingerprint_that_rolled_goes_absent_without_raising(prompt: Path) -> None:
    target = recorder(
        prompt, a_record(fingerprint="fp_1"), a_record(fingerprint="fp_2")
    )
    target(a_case())
    assert target.config["fingerprint"] == "fp_1"
    target(a_case())
    assert "fingerprint" not in target.config


# --------------------------------------------------------------------------- #
# A target that said nothing says why (the twin of `JudgeBase._no_text`)
# --------------------------------------------------------------------------- #
#
# An empty completion is a legal *output* — the assertions get to fail it, and
# that is unchanged. What was not legal was the sentence a suite judging a
# *shape* got: the reply died inside `parse`, and the ending the provider had
# just declared was thrown away at the moment it was worth most.


class MuteTarget(RecordTarget):
    """A target whose suite judges a shape, answered by a provider that said
    nothing. The two halves of the case, in one fake."""

    max_tokens = 512

    def parse(self, text: str) -> Output:
        parsed: Output = json.loads(text)
        return parsed


def a_mute_record(
    *, finish: Finish | None = None, finish_raw: str | None = None, output: int = 512
) -> Completion:
    return Completion(
        text="",
        usage=Usage(input_tokens=10, output_tokens=output),
        finish=finish,
        finish_raw=finish_raw,
    )


@pytest.mark.parametrize(
    ("finish", "expected"),
    [
        ("length", "truncated before the first character"),
        ("tool_use", "tool call"),
        ("filtered", "refused or filtered"),
        ("stop", "ended normally and said nothing"),
        ("other", "a reason of its own"),
    ],
)
def test_a_mute_reply_reports_the_ending_the_provider_declared(
    prompt: Path, finish: Finish, expected: str
) -> None:
    """Every entry of the vocabulary, because each one needs a different action
    and a token count cannot tell them apart."""
    target = MuteTarget(
        prompt, "m1", pricing=PRICES, replies=[a_mute_record(finish=finish)]
    )
    with pytest.raises(ValueError) as raised:
        target(a_case())
    message = str(raised.value)
    assert "the target returned no text" in message
    assert expected in message
    # The parser's sentence must not be the one that reaches the operator.
    assert "Expecting value" not in message


def test_the_providers_own_word_travels_with_the_reading(prompt: Path) -> None:
    """`other` is where a word we do not know goes, and the word goes with it:
    it is what an operator searches the provider's documentation for."""
    target = MuteTarget(
        prompt,
        "m1",
        pricing=PRICES,
        replies=[a_mute_record(finish="other", finish_raw="pause_turn")],
    )
    with pytest.raises(ValueError, match="'pause_turn'"):
        target(a_case())


def test_a_mute_reply_with_no_ending_reported_falls_back_to_the_cap(
    prompt: Path,
) -> None:
    """The ordinary case on a compatible endpoint. The inference is marked as
    one, exactly as it is for a judge."""
    target = MuteTarget(prompt, "m1", pricing=PRICES, replies=[a_mute_record()])
    with pytest.raises(ValueError) as raised:
        target(a_case())
    assert "max_tokens cap (512 of 512)" in str(raised.value)
    assert "likely truncated" in str(raised.value)


def test_well_under_the_cap_says_so_instead(prompt: Path) -> None:
    """Raising the cap would do nothing here, so the sentence must not suggest
    it."""
    target = MuteTarget(prompt, "m1", pricing=PRICES, replies=[a_mute_record(output=7)])
    with pytest.raises(ValueError) as raised:
        target(a_case())
    assert "well under the cap (7 of 512)" in str(raised.value)
    assert "max_tokens cap" not in str(raised.value)


def test_a_target_that_sends_no_cap_claims_none(prompt: Path) -> None:
    """`max_tokens` is the plugins' own name and not the base's contract. A
    target that does not carry one gets a sentence that does not invent one."""

    class Capless(MuteTarget):
        max_tokens = None

    target = Capless(prompt, "m1", pricing=PRICES, replies=[a_mute_record(output=7)])
    with pytest.raises(ValueError) as raised:
        target(a_case())
    message = str(raised.value)
    assert "(7 output tokens)" in message
    assert "cap" not in message


def test_a_reply_that_is_only_the_prefill_is_no_text_either(prompt: Path) -> None:
    """The case that would have escaped, on the provider that prefills:
    `AnthropicTarget` opens the assistant turn with `{` and prepends it back, so
    a model that produced nothing arrives as `"{"` rather than as `""`."""
    target = MuteTarget(
        prompt,
        "m1",
        pricing=PRICES,
        replies=[
            Completion(
                text="{",
                usage=Usage(input_tokens=10, output_tokens=512),
                finish="length",
            )
        ],
    )
    target.prefill = "{"
    with pytest.raises(ValueError, match="the target returned no text"):
        target(a_case())


def test_a_reply_that_said_something_keeps_the_parsers_own_failure(
    prompt: Path,
) -> None:
    """The reading is for a reply with nothing in it. A model that answered and
    got the shape wrong is a different fault, and its own message is the useful
    one."""
    target = MuteTarget(
        prompt,
        "m1",
        pricing=PRICES,
        replies=[
            Completion(text="not json", usage=Usage(input_tokens=1, output_tokens=3))
        ],
    )
    with pytest.raises(json.JSONDecodeError):
        target(a_case())


def test_the_parse_failure_is_kept_underneath(prompt: Path) -> None:
    """It is the second question a reader asks, and the first one is now
    answered."""
    target = MuteTarget(
        prompt, "m1", pricing=PRICES, replies=[a_mute_record(finish="length")]
    )
    with pytest.raises(ValueError) as raised:
        target(a_case())
    assert isinstance(raised.value.__cause__, json.JSONDecodeError)


def test_an_empty_reply_is_still_a_legal_output_by_default(prompt: Path) -> None:
    """Unchanged, and deliberately: with the default `parse` an empty completion
    is an output the assertions get to fail. The reading above exists for the
    suite whose `parse` refuses it, not for every suite."""
    target = RecordTarget(
        prompt, "m1", pricing=PRICES, replies=[a_mute_record(finish="length")]
    )
    response = target(a_case())
    assert response.output == ""
    assert response.metadata["finish"] == "length"


def test_the_cause_reaches_the_run_document(prompt: Path) -> None:
    """End to end, which is the claim that matters: every assertion on the case
    errors, and the reason names the ending rather than the parser."""
    suite = Suite(
        tenant="t",
        environment="e",
        name="s",
        assertions=[Contains(needle="x")],
        cases=[Case(id="c1", vars={"question": "q", "customer": "A"})],
    )
    target = MuteTarget(
        prompt, "m1", pricing=PRICES, replies=[a_mute_record(finish="length")]
    )
    run = execute(suite, target, created_at="2026-08-27T10:00:00+00:00")
    (case,) = run.results
    (verdict,) = case.verdicts
    assert verdict.status == "error"
    assert "the target returned no text" in verdict.reason
    assert "raise max_tokens" in verdict.reason


@pytest.mark.parametrize(
    ("module", "name"),
    [
        ("digline_anthropic", "AnthropicTarget"),
        ("digline_openai", "OpenAITarget"),
        ("digline_bedrock", "BedrockTarget"),
    ],
)
def test_every_plugin_inherits_the_reading(module: str, name: str) -> None:
    """One implementation, like `ObservedIdentity`. A plugin that overrode the
    call or the parse hook would be a provider whose mute replies are diagnosed
    differently from the other two — which is the thing this is not."""
    plugin = pytest.importorskip(module)
    target_class = getattr(plugin, name)
    assert issubclass(target_class, ProviderTarget)
    for method in ("__call__", "_parsed", "_token_cap", "parse"):
        assert getattr(target_class, method) is getattr(ProviderTarget, method), method
    # The cap the sentence names is read off the plugin's own attribute, so the
    # name has to be the one all three of them use.
    assert "max_tokens" in target_class.__init__.__annotations__
