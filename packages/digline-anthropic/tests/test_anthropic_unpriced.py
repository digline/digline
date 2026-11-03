"""ADR 0004 §8.9's criteria, end to end through `execute`, on the target and
on the judge, with the SDK replaced and no key.

A reply this plugin cannot price, an inference geography with no rate (#392)
or a write to the 1-hour cache (#368), was refused, and the case or the judged
check errored over a call that had answered. It is now an unpriced call: the
case is judged, the line counts the call and its tokens and says its cost is
not known, and the sentence is handed to the person who ran the command.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import pytest

from digline.core import Contains, CostBudget, LlmRubric, Run, RunUsage
from digline.run import Case, Response, Suite, execute
from digline.targets import Usage
from digline_anthropic import AnthropicJudge, AnthropicTarget
from digline_anthropic.client import completion_of

CREATED = "2026-01-01T00:00:00+00:00"


@dataclass
class FakeBlock:
    text: str
    type: str = "text"
    name: str = ""


@dataclass
class FakeCacheCreation:
    ephemeral_5m_input_tokens: int = 0
    ephemeral_1h_input_tokens: int = 0


@dataclass
class FakeUsage:
    input_tokens: int = 1000
    output_tokens: int = 100
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0
    output_tokens_details: object | None = None
    cache_creation: object | None = None
    inference_geo: str | None = None


@dataclass
class FakeReply:
    content: list[FakeBlock]
    usage: FakeUsage = field(default_factory=FakeUsage)
    stop_reason: str | None = "end_turn"
    model: str = "claude-fake-1-20260101"


class FakeMessages:
    def __init__(self, text: str, usage: FakeUsage) -> None:
        self.text = text
        self.usage = usage

    def create(self, **kwargs: Any) -> FakeReply:
        return FakeReply(content=[FakeBlock(self.text)], usage=self.usage)


class FakeClient:
    def __init__(self, text: str, usage: FakeUsage) -> None:
        self.messages = FakeMessages(text, usage)


#: A geography `GEO_MULTIPLIERS` has no rate for. It was `"not_available"`
#: until that string was priced, as a model without the parameter.
GEO = FakeUsage(inference_geo="eu")
ONE_HOUR = FakeUsage(
    cache_creation_input_tokens=1500,
    cache_creation=FakeCacheCreation(
        ephemeral_5m_input_tokens=500, ephemeral_1h_input_tokens=1000
    ),
)
UNPRICED = [
    pytest.param(GEO, "#392", id="geography"),
    pytest.param(ONE_HOUR, "#368", id="1-hour"),
]
PRICED = [
    pytest.param(FakeUsage(inference_geo="global"), id="global"),
    pytest.param(FakeUsage(inference_geo="us"), id="us"),
    pytest.param(FakeUsage(inference_geo="not_available"), id="not_available"),
]


@pytest.fixture
def prompt(tmp_path: Path) -> Path:
    path = tmp_path / "answer.md"
    path.write_text("Say yes.\n", encoding="utf-8")
    return path


def a_target(prompt: Path, usage: FakeUsage) -> AnthropicTarget:
    return AnthropicTarget(
        prompt, "claude-sonnet-5", 64, client=FakeClient("yes", usage)
    )


def a_judge(usage: FakeUsage) -> AnthropicJudge:
    return AnthropicJudge(
        model="claude-haiku-4-5",
        client=FakeClient('"score": 1, "reason": "fine"}', usage),
    )


class Answering:
    """A target priced at zero, so the judge's line is alone in what varies."""

    config = {"provider": "fake", "model": "m-1"}

    def __call__(self, case: Case) -> Response:
        return Response(output="yes", cost_usd=0.0, usage=Usage(0, 0))


def suite(*assertions: object) -> Suite:
    return Suite(
        tenant="acme",
        environment="staging",
        name="qa",
        assertions=list(assertions),  # pyright: ignore[reportArgumentType]
        cases=[Case(id="c1"), Case(id="c2")],
    )


def rubric(judge: AnthropicJudge) -> LlmRubric:
    return LlmRubric(rubric="Polite?", judge=judge, threshold=0.5, tolerance=0.0)


def usage_of(run: Run) -> RunUsage:
    assert run.usage is not None
    return run.usage


def statuses(run: Run) -> list[str]:
    return [v.status for case in run.results for v in case.verdicts]


# --------------------------------------------------------------------------- #
# 1. Cost not computable: judged, counted, and said
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(("usage", "issue"), UNPRICED)
def test_an_unpriced_target_reply_is_judged_and_its_cost_not_known(
    prompt: Path, usage: FakeUsage, issue: str
) -> None:
    said: list[str] = []
    run = execute(
        suite(Contains(needle="yes", threshold=1.0)),
        a_target(prompt, usage),
        created_at=CREATED,
        on_unpriced=said.append,
    )
    assert statuses(run) == ["pass", "pass"]
    assert all(case.error_kind is None for case in run.results)
    line = usage_of(run).target
    assert (line.calls, line.counted, line.spent_usd) == (2, 2, 0.0)
    assert line.tokens.input_tokens == 2000
    assert line.every_cost_known is False
    (sentence,) = said
    assert issue in sentence


@pytest.mark.parametrize(("usage", "issue"), UNPRICED)
def test_an_unpriced_judge_reply_is_judged_and_its_cost_not_known(
    usage: FakeUsage, issue: str
) -> None:
    said: list[str] = []
    run = execute(
        suite(rubric(a_judge(usage))),
        Answering(),
        created_at=CREATED,
        on_unpriced=said.append,
    )
    assert statuses(run) == ["pass", "pass"]
    line = usage_of(run).judge
    assert (line.calls, line.counted, line.spent_usd) == (2, 2, 0.0)
    assert line.tokens.input_tokens == 2000
    assert line.every_cost_known is False
    (sentence,) = said
    assert issue in sentence


# --------------------------------------------------------------------------- #
# 3. Cost known: the figure, and neither sentence
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("usage", PRICED)
def test_a_priced_target_reply_has_its_figure_and_no_sentence(
    prompt: Path, usage: FakeUsage
) -> None:
    said: list[str] = []
    run = execute(
        suite(Contains(needle="yes", threshold=1.0)),
        a_target(prompt, usage),
        created_at=CREATED,
        on_unpriced=said.append,
    )
    line = usage_of(run).target
    assert line.spent_usd > 0
    assert line.every_cost_known is True
    assert said == []


@pytest.mark.parametrize("usage", PRICED)
def test_a_priced_judge_reply_has_its_figure_and_no_sentence(
    usage: FakeUsage,
) -> None:
    said: list[str] = []
    run = execute(
        suite(rubric(a_judge(usage))),
        Answering(),
        created_at=CREATED,
        on_unpriced=said.append,
    )
    line = usage_of(run).judge
    assert line.spent_usd > 0
    assert line.every_cost_known is True
    assert said == []


def test_us_is_priced_at_its_multiplier_on_the_line(prompt: Path) -> None:
    """The control's figure, at the multiplier `GEO_MULTIPLIERS` gives."""

    def spent(geo: str) -> float:
        run = execute(
            suite(Contains(needle="yes", threshold=1.0)),
            a_target(prompt, FakeUsage(inference_geo=geo)),
            created_at=CREATED,
        )
        return usage_of(run).target.spent_usd

    assert spent("us") == pytest.approx(spent("global") * 1.1)


def test_not_available_is_a_model_without_the_parameter_at_the_standard_rate() -> None:
    """A model that takes no `inference_geo` reports `"not_available"`, and
    Anthropic prices it at the standard rate: the figure is the list's, read
    through `completion_of` and through a judge, as for `"global"`.

    The rate is claude-haiku-4-5's in `pricing.py`, 1 USD per million input
    tokens and 5 per million output tokens, and the figure below is worked
    from it rather than read back from the code under test.
    """
    usage = FakeUsage(
        input_tokens=1234, output_tokens=567, inference_geo="not_available"
    )
    expected = 1234 * 1.0 / 1_000_000 + 567 * 5.0 / 1_000_000  # 0.004069

    reply = FakeReply(content=[FakeBlock("yes")], usage=usage, model="claude-haiku-4-5")
    assert completion_of(reply).unpriced is None

    def spent(geo: str) -> float:
        judge = a_judge(replace(usage, inference_geo=geo))
        judge("Output to judge:\nyes")
        assert judge.unpriced_calls == 0
        return judge.spent_usd

    assert spent("not_available") == pytest.approx(expected)
    assert spent("not_available") == pytest.approx(spent("global"))


# --------------------------------------------------------------------------- #
# 4. A `CostBudget` over an unpriced cost
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(("usage", "issue"), UNPRICED)
def test_a_budget_over_an_unpriced_reply_errors_and_says_why(
    prompt: Path, usage: FakeUsage, issue: str
) -> None:
    run = execute(
        suite(
            Contains(needle="yes", threshold=1.0),
            CostBudget(max_usd=1.0, tolerance=0.0),
        ),
        a_target(prompt, usage),
        created_at=CREATED,
    )
    for case in run.results:
        content, budget = case.verdicts
        assert content.status == "pass"
        assert budget.status == "error"
        assert "cost_usd is not computable" in budget.reason
        assert issue in budget.reason


def test_a_budget_over_a_model_without_the_parameter_is_judged(prompt: Path) -> None:
    """The brief project's report: every `cost_budget` of a suite errored on
    claude-haiku-4-5, whose replies say `"not_available"`. It is judged."""
    run = execute(
        suite(
            Contains(needle="yes", threshold=1.0),
            CostBudget(max_usd=1.0, tolerance=0.0),
        ),
        a_target(prompt, FakeUsage(inference_geo="not_available")),
        created_at=CREATED,
    )
    assert statuses(run) == ["pass", "pass", "pass", "pass"]
