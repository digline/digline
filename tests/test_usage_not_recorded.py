"""A provider's usage that could not be read is *not recorded*, never zero (#629).

A plugin reads its counts off the SDK's reply. When a field it needs is absent
— an SDK that renamed it, a release that predates it — the honest answer is
that the call's usage was not recorded, and the bill has to say so: the call
is on the line, its tokens and its cost are not, and `every_cost_known` is
`False` because digline knows a call was made. A zero would be a price nobody
stated, and the undercount that reads as good news.

`Completion.usage=None` is how a plugin says it. A usage **present at zero**
is a measurement and stays zero: that is the control in every pair below,
because the two are different facts and this repair is the line between them.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from digline.core import Contains, JudgeReply, LlmRubric, RunUsage
from digline.run import Case, Suite, execute
from digline.run.driver import judge_totals
from digline.targets import Completion, ProviderTarget
from digline.targets.completion import no_text_reason
from digline.targets.judge import ScoreJudge
from digline.targets.pricing import ModelPrice, Pricing, Usage

CREATED = "2026-01-01T00:00:00+00:00"
PRICING = Pricing(
    per_model={
        "m-1": ModelPrice(input_per_mtok=1.0, output_per_mtok=2.0),
        "j-1": ModelPrice(input_per_mtok=1.0, output_per_mtok=2.0),
    }
)
ZERO = Usage(input_tokens=0, output_tokens=0)


@pytest.fixture
def prompt(tmp_path: Path) -> Path:
    path = tmp_path / "prompt.md"
    path.write_text("Say yes.\n", encoding="utf-8")
    return path


class Reading(ProviderTarget):
    """A provider target whose plugin hands over `usage` as given: `None` is a
    reply whose counts the plugin could not read."""

    provider = "fake"

    def __init__(self, prompt: Path, usage: Usage | None) -> None:
        super().__init__(prompt, "m-1", pricing=PRICING)
        self.usage = usage

    def _complete(self, prompt: str, system: str | None) -> Completion:
        return Completion(text="yes", usage=self.usage)


class ReadingJudge(ScoreJudge):
    """A `JudgeBase` whose plugin hands over each call's usage from a list."""

    provider = "fake"
    system = "unused"

    def __init__(self, *usages: Usage | None) -> None:
        super().__init__(model="j-1", max_tokens=16, pricing=PRICING)
        self.usages = list(usages)

    def _complete(self, system: str, prompt: str) -> Completion:
        text = json.dumps({"score": 1.0, "reason": "fine"})
        return Completion(text=text, usage=self.usages.pop(0))


def suite(*assertions: object, cases: int = 1) -> Suite:
    return Suite(
        tenant="acme",
        environment="staging",
        name="qa",
        assertions=list(assertions) or [Contains(needle="yes", threshold=1.0)],  # pyright: ignore[reportArgumentType]
        cases=[Case(id=f"c{n}") for n in range(1, cases + 1)],
    )


def rubric(judge: object) -> LlmRubric:
    return LlmRubric(
        rubric="Is it polite?",
        judge=judge,  # pyright: ignore[reportArgumentType]
        threshold=0.5,
        tolerance=0.0,
    )


def usage_of(run: object) -> RunUsage:
    found = getattr(run, "usage", None)
    assert isinstance(found, RunUsage)
    return found


# --------------------------------------------------------------------------- #
# The target: no cost, no usage, no counts in metadata
# --------------------------------------------------------------------------- #


def test_a_target_reply_with_no_usage_has_no_cost_and_no_usage(prompt: Path) -> None:
    response = Reading(prompt, None)(Case(id="c1"))
    assert response.cost_usd is None
    assert response.usage is None
    for key in (
        "input_tokens",
        "output_tokens",
        "cache_read_tokens",
        "cache_write_tokens",
    ):
        assert key not in response.metadata


def test_a_target_reply_at_zero_is_priced_at_zero(prompt: Path) -> None:
    """The control: a count that was read and is zero is a measurement."""
    response = Reading(prompt, ZERO)(Case(id="c1"))
    assert response.cost_usd == 0.0
    assert response.usage == ZERO
    assert response.metadata["input_tokens"] == 0


def test_the_target_line_knows_a_call_was_made_and_not_its_cost(prompt: Path) -> None:
    line = usage_of(execute(suite(), Reading(prompt, None), created_at=CREATED)).target
    assert (line.calls, line.counted, line.spent_usd) == (1, 0, 0.0)
    assert line.every_cost_known is False
    assert line.every_call_seen is True


def test_the_target_line_at_zero_is_complete(prompt: Path) -> None:
    line = usage_of(execute(suite(), Reading(prompt, ZERO), created_at=CREATED)).target
    assert (line.calls, line.counted) == (1, 1)
    assert line.every_cost_known is True


# --------------------------------------------------------------------------- #
# The judge: counted as a call, not as a cost
# --------------------------------------------------------------------------- #


def test_a_judge_reply_with_no_usage_is_a_call_with_no_cost() -> None:
    judge = ReadingJudge(None)
    judge("Output to judge:\nyes")
    assert judge.calls == 1
    assert judge.uncounted_calls == 1
    assert judge.spent_usd == 0.0
    assert judge.tokens == Usage(0, 0)


def test_a_judge_reply_at_zero_is_counted() -> None:
    judge = ReadingJudge(ZERO)
    judge("Output to judge:\nyes")
    assert (judge.calls, judge.uncounted_calls) == (1, 0)


def test_a_counted_call_after_an_uncounted_one_is_the_seed() -> None:
    """The fold's seed is the first *counted* reply, not the first call: an
    uncounted first call must not make the second fold into `NO_USAGE`, whose
    thinking split is *not reported* and would unreport the total
    (ADR 0026 §3)."""
    reported = Usage(input_tokens=7, output_tokens=3, thinking_tokens=1)
    judge = ReadingJudge(None, reported)
    judge("Output to judge:\nyes")
    judge("Output to judge:\nyes")
    assert judge.tokens == reported


def test_the_judge_line_reads_the_judges_count_instead_of_assuming() -> None:
    """`every_cost_known` was written `True` for every billable judge, on the
    claim that a call it could not price had raised. A call whose usage was not
    recorded did not raise, so the claim was false."""
    line = usage_of(
        execute(suite(rubric(ReadingJudge(None))), Reading_target(), created_at=CREATED)
    ).judge
    assert (line.calls, line.counted) == (1, 0)
    assert line.every_cost_known is False


def test_the_judge_line_at_zero_is_complete() -> None:
    line = usage_of(
        execute(suite(rubric(ReadingJudge(ZERO))), Reading_target(), created_at=CREATED)
    ).judge
    assert (line.calls, line.counted) == (1, 1)
    assert line.every_cost_known is True


class HandWritten:
    """A `Billable` judge that keeps no count of uncounted calls."""

    def __init__(self) -> None:
        self.calls = 0
        self.spent_usd = 0.0
        self.tokens = Usage(0, 0)
        self.config = {"provider": "fake", "model": "j-1"}

    def __call__(self, prompt: str) -> JudgeReply:
        return JudgeReply(score=1.0, reason="fine")


def test_a_judge_that_keeps_no_such_count_is_not_recorded() -> None:
    """Nothing established that it priced every call, so `None`, not `True`."""
    assert judge_totals(suite(rubric(HandWritten()))).every_cost_known is None


# --------------------------------------------------------------------------- #
# The sentence for an empty reply
# --------------------------------------------------------------------------- #


def test_an_empty_reply_with_no_usage_says_the_count_was_not_recorded() -> None:
    sentence = no_text_reason(
        Completion(text="", usage=None), max_tokens=16, subject="the judge"
    )
    assert "not recorded" in sentence


def Reading_target() -> object:  # noqa: N802
    """A target that answers with a recorded usage, so a judge line is alone
    in what this test varies."""

    class Answering:
        config = {"provider": "fake", "model": "m-1"}

        def __call__(self, case: Case) -> object:
            from digline.run import Response

            return Response(output="yes", cost_usd=0.0, usage=ZERO)

    return Answering()
