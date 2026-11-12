"""The driver asks every judge's `preflight()` before the first call.

Found in a Java application with a judged suite: a judge whose model had no
price sat inside `Repeated`, the driver never asked it, and every case was
paid for — the target's call and the judge's — before each one errored on the
price. `JudgeBase.preflight()` existed and was called by a plugin's tests
only. Now the driver asks each judge `judges()` finds, wrappers followed
through, after the target's own preflight and before any call, and the
refusal is the one `preflight()` already raises. (ADR 0004 §8.0, as decided
2026-11-12)
"""

from __future__ import annotations

import json

import pytest

from digline.core import LlmRubric, Repeated, Usage
from digline.core.refused import RefusedError
from digline.run import Case, Response, Suite, execute
from digline.targets import Completion, ModelPrice, Pricing
from digline.targets.judge import ScoreJudge

CREATED = "2026-11-12T00:00:00+00:00"
PRICED = Pricing({"j-1": ModelPrice(1.0, 1.0)})
VERDICT = json.dumps({"score": 1.0, "reason": "fine"})


class CountingJudge(ScoreJudge):
    """A judge that counts every call it is asked to make."""

    provider = "fake"
    system = "unused"

    def __init__(self, model: str) -> None:
        super().__init__(model=model, max_tokens=16, pricing=PRICED)
        self.asked = 0

    def _complete(self, system: str, prompt: str) -> Completion:
        self.asked += 1
        return Completion(text=VERDICT, usage=Usage(1, 1))


class CountingTarget:
    def __init__(self) -> None:
        self.asked = 0

    def __call__(self, case: Case) -> Response:
        self.asked += 1
        return Response(output="yes", cost_usd=0.0, usage=Usage(0, 0))


def suite(judge: CountingJudge) -> Suite:
    inner = LlmRubric(rubric="polite?", judge=judge, threshold=0.5, tolerance=0.0)
    return Suite(
        tenant="acme",
        environment="dev",
        name="support",
        assertions=[Repeated(inner, samples=3, min_agreement="2/3")],
        cases=[Case(id="one"), Case(id="two"), Case(id="three")],
    )


def test_an_unpriced_judge_inside_repeated_refuses_before_any_call() -> None:
    judge = CountingJudge("not-priced")
    target = CountingTarget()
    with pytest.raises(RefusedError, match="judge model 'not-priced' has no price"):
        execute(suite(judge), target, created_at=CREATED)
    assert (target.asked, judge.asked) == (0, 0)


def test_a_priced_judge_inside_repeated_runs() -> None:
    """The control: the same suite with a priced judge is called as declared,
    three cases, each judged three times."""
    judge = CountingJudge("j-1")
    target = CountingTarget()
    execute(suite(judge), target, created_at=CREATED)
    assert (target.asked, judge.asked) == (3, 9)
