"""How many judgements a case gets, said before the run and counted after it.

Found in a Java application with a judged suite: `Repeated(samples=3)` under
`Suite(samples=2)` is six judgements a case, the plan said *"each answer is
judged 3 times"*, and the report showed the mean of the two answers' means,
from which neither the six nor how many of them passed can be read back. The
fold now counts both through every level (`JUDGEMENTS_KEY`, `IN_FAVOUR_KEY`),
the plan says the per-case figure, and the run report puts the two counts
beside the mean.
"""

from __future__ import annotations

import itertools

from digline.core import JudgeReply, LlmRubric, Repeated, Verdict
from digline.core.sampling import IN_FAVOUR_KEY, JUDGEMENTS_KEY
from digline.report.render import judgements_said, render_run_html
from digline.run import Case, Response, Suite, execute
from digline.run.suite import planned_calls

CREATED = "2026-11-12T00:00:00+00:00"

#: The six judgements of one case, in call order: four pass at 0.5.
SCORES = (1.0, 0.0, 1.0, 1.0, 0.0, 1.0)


def suite(*, samples: int, judge: object, cases: int = 1) -> Suite:
    inner = LlmRubric(
        rubric="ok?",
        judge=judge,  # pyright: ignore[reportArgumentType]
        threshold=0.5,
        tolerance=0.0,
    )
    return Suite(
        tenant="acme",
        environment="dev",
        name="support",
        assertions=[Repeated(inner, samples=3, min_agreement="1/3")],
        cases=[Case(id=f"c{n}") for n in range(1, cases + 1)],
        samples=samples,
        min_agreement=f"1/{samples}",
    )


def judged_by(scores: tuple[float, ...]) -> object:
    cycle = itertools.cycle(scores)

    def judge(prompt: str) -> JudgeReply:
        return JudgeReply(score=next(cycle), reason="r")

    return judge


def verdict(samples: int) -> Verdict:
    run = execute(
        suite(samples=samples, judge=judged_by(SCORES)),
        lambda case: Response(output="x"),
        created_at=CREATED,
    )
    (found,) = run.results[0].verdicts
    return found


def test_the_plan_says_the_judgements_a_case_gets() -> None:
    plan = planned_calls(suite(samples=2, judge=judged_by(SCORES), cases=3))
    sentence = plan.sentence()
    assert "3 cases × 2 samples = 6 calls to the target" in sentence
    assert (
        "each answer is judged 3 times by llm_rubric, 6 judgements a case" in sentence
    )


def test_one_sample_adds_nothing_to_the_plan() -> None:
    """At `samples=1` a case is judged as often as its answer, and the
    sentence it always had says that."""
    sentence = planned_calls(suite(samples=1, judge=judged_by(SCORES))).sentence()
    assert "judgements a case" not in sentence


def test_the_fold_counts_every_judgement_through_both_levels() -> None:
    found = verdict(samples=2)
    assert found.score.metadata[JUDGEMENTS_KEY] == 6
    assert found.score.metadata[IN_FAVOUR_KEY] == 4
    # The control: the outer `scores` are the two inner means, from which the
    # six cannot be read back.
    assert found.score.metadata["scores"] == [0.666667, 0.666667]


def test_the_report_says_the_two_counts_beside_the_mean() -> None:
    found = verdict(samples=2)
    assert judgements_said(found, "en") == "6 judgements, 4 in favour"
    assert judgements_said(found, "it") == "6 giudizi, 4 a favore"
    run = execute(
        suite(samples=2, judge=judged_by(SCORES)),
        lambda case: Response(output="x"),
        created_at=CREATED,
    )
    page = render_run_html(run, locale="en")
    assert "<b>0.666667</b> / 0.500000 · 6 judgements, 4 in favour" in page


def test_a_single_repeated_counts_its_own_judgements() -> None:
    found = verdict(samples=1)
    assert (
        found.score.metadata[JUDGEMENTS_KEY],
        found.score.metadata[IN_FAVOUR_KEY],
    ) == (
        3,
        2,
    )
