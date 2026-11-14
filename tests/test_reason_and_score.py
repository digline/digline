"""A judge whose reason says one score and whose `score` is another. (P-1685)

Found in a first use outside the project, on a Java application with a
judged suite: a reason wrote *score 1* over a returned 0, and the run kept
the 0 as if the judge had meant it. Which half the judge meant nobody can
tell, so the sample is an `error`, *reason and score disagree*, kept in the
run and said by `explain` under its case where the samples disagreed.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from tests.test_judge import PRICING, FakeScoreJudge

from digline.core import EvaluatorInputs, LlmRubric
from digline.report import judge_words
from digline.run import Case, Response, Suite, execute
from digline.targets import SCORE_SYSTEM, CompletionResult, ScoreJudge, Usage
from digline.targets.judge import scores_said


@pytest.mark.parametrize(
    "reason",
    [
        "score 1: the output answers the question",
        "Score: 1 — it is right",
        "fully meets the rubric, 1/1",
    ],
)
def test_a_reason_that_says_another_score_is_refused(reason: str) -> None:
    judge = FakeScoreJudge(f'{{"score": 0, "reason": "{reason}"}}')
    with pytest.raises(
        ValueError, match="^reason and score disagree: the judge returned 0"
    ):
        judge("Output to judge:\nRome.")


@pytest.mark.parametrize(
    "reason",
    [
        "score 1: the output answers the question",
        # A reason that writes no score is not read.
        "the output answers the question",
        # A count of claims is not a score.
        "3/5 of the points are covered",
        # The rounding a sentence does.
        "score 0.99: nearly all of it",
    ],
)
def test_a_reason_that_agrees_or_says_no_score_is_kept(reason: str) -> None:
    judge = FakeScoreJudge(f'{{"score": 1, "reason": "{reason}"}}')
    assert judge("Output to judge:\nRome.").reason == reason


def test_the_scores_a_reason_writes_out() -> None:
    assert scores_said("score of 0.83 overall, 1/1 for tone") == (0.83, 1.0)
    assert scores_said("scored 1 out of 10, score 10") == ()


def test_the_disagreement_is_an_error_whose_reason_says_it() -> None:
    judge = FakeScoreJudge('{"score": 0, "reason": "score 1: right"}')
    verdict = LlmRubric(rubric="right?", judge=judge, threshold=0.5, tolerance=0.05)(
        EvaluatorInputs(output="Rome.")
    )
    assert verdict.status == "error"
    assert verdict.reason is not None
    assert "reason and score disagree" in verdict.reason


def test_the_instruction_says_the_context_is_not_what_is_graded() -> None:
    assert (
        "Grade the output alone. The input and the context are reference: the "
        "context is what the system was allowed to use, not what you grade."
    ) in SCORE_SYSTEM


class _Sequence(ScoreJudge):
    """A judge whose replies come in order, one per call."""

    def __init__(self, replies: list[str]) -> None:
        super().__init__("fake-1", max_tokens=100, pricing=PRICING)
        self._replies: Iterator[str] = iter(replies)

    def _complete(self, system: str, prompt: str) -> CompletionResult:
        return next(self._replies), Usage(input_tokens=10, output_tokens=10)


def test_the_run_keeps_it_and_explain_says_it_under_the_case() -> None:
    judge = _Sequence(
        [
            '{"score": 1, "reason": "right"}',
            '{"score": 0, "reason": "score 1: right"}',
            '{"score": 1, "reason": "right"}',
        ]
    )
    suite = Suite(
        tenant="acme",
        environment="dev",
        name="support",
        assertions=[
            LlmRubric(rubric="right?", judge=judge, threshold=0.5, tolerance=0.05)
        ],
        cases=[Case(id="torn")],
        samples=3,
        min_agreement="2/3",
    )
    run = execute(
        suite,
        lambda case: Response(output="Rome.", cost_usd=0.0),
        created_at="2026-11-14T00:00:00+00:00",
    )
    [verdict] = run.results[0].verdicts
    assert verdict.score.metadata.get("errored_samples") == 1
    assert verdict.reason is not None
    assert "reason and score disagree" in verdict.reason
    lines = judge_words(run, locale="en")
    assert lines[1] == "torn · llm_rubric"
    assert "reason and score disagree" in lines[2]
