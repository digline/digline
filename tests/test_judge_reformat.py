"""A judge reply with no JSON object is asked for once more. (ADR 0004 §4, as
noted 2026-11-12)

Found in a first use outside the project, on a Java application with a judged
suite: a judge answered in prose, and the sample errored. The second call
quotes the first reply and asks for the object alone; it is a call like any
other on the judge's line. Asked once: where the second holds no object
either, the sample is an error whose reason is the judge's own prose.
"""

from __future__ import annotations

import json

import pytest

from digline.core import LlmRubric, Usage
from digline.run import Case, Response, Suite, execute
from digline.targets import Completion, ModelPrice, Pricing
from digline.targets.judge import AGAIN, ScoreJudge

PROSE = "The answer is polite and correct, so I would give it full marks."
VERDICT = json.dumps({"score": 1.0, "reason": "polite"})


class Replying(ScoreJudge):
    """A judge that answers each call with the next reply, and keeps the
    prompts it was sent."""

    provider = "fake"
    system = "unused"

    def __init__(self, *replies: str) -> None:
        super().__init__(
            model="j-1",
            max_tokens=64,
            pricing=Pricing({"j-1": ModelPrice(1_000_000.0, 0.0)}),
        )
        self.replies = list(replies)
        self.prompts: list[str] = []

    def _complete(self, system: str, prompt: str) -> Completion:
        self.prompts.append(prompt)
        return Completion(text=self.replies.pop(0), usage=Usage(1, 0))


def test_prose_then_json_is_two_calls_and_a_verdict() -> None:
    judge = Replying(PROSE, VERDICT)
    reply = judge("Output to judge:\nyes")
    assert (reply.score, reply.reason) == (1.0, "polite")
    # Both calls on the line, both billed: one input token at 1 USD each.
    assert judge.calls == 2
    assert judge.spent_usd == pytest.approx(2.0)
    second = judge.prompts[1]
    assert second.startswith("Output to judge:\nyes")
    assert PROSE in second and second.endswith(AGAIN)


def test_prose_twice_is_an_error_whose_reason_is_the_prose() -> None:
    judge = Replying(PROSE, "Still prose, sorry.")
    with pytest.raises(ValueError, match="replied twice with no JSON object") as err:
        judge("p")
    assert PROSE in str(err.value)
    assert judge.calls == 2 and judge.replies == []


def test_a_reply_with_an_object_is_asked_once() -> None:
    """The control: nothing is asked again where the first reply reads."""
    judge = Replying(VERDICT)
    assert judge("p").score == 1.0
    assert judge.calls == 1


def test_an_object_with_a_wrong_field_is_not_asked_again() -> None:
    """Lenient about the wrapping, strict about the content: an object is
    there, and its missing score is the error."""
    judge = Replying(json.dumps({"reason": "no score"}), VERDICT)
    with pytest.raises(ValueError):
        judge("p")
    assert judge.calls == 1


def test_in_a_run_the_second_call_is_on_the_judge_line_and_the_prose_visible() -> None:
    judge = Replying(PROSE, VERDICT, PROSE, "prose again")
    rubric = LlmRubric(rubric="polite?", judge=judge, threshold=0.5, tolerance=0.0)
    suite = Suite(
        tenant="acme",
        environment="dev",
        name="support",
        assertions=[rubric],
        cases=[Case(id="read-again"), Case(id="never-read")],
    )
    run = execute(
        suite,
        lambda case: Response(output="yes", cost_usd=0.0, usage=Usage(0, 0)),
        created_at="2026-11-12T00:00:00+00:00",
    )
    assert run.usage is not None
    assert run.usage.judge.calls == 4
    first, second = run.results
    assert first.verdicts[0].status == "pass"
    assert second.verdicts[0].status == "error"
    assert PROSE in second.verdicts[0].reason
