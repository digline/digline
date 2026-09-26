"""`--judge-samples`: the judge's own range on answers that do not move, and
never without its scale. (ADR 0024 §5, amended in §5.5)

The file follows the record: what is recorded (the same quantity a plain replay
records), where the range lives (metadata, never the noise floor), what the
document carries, and the sentence.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from tests._helpers import baseline_in, cli
from tests._vocabulary import ADVICE, SPECULATION, spoken

from digline.core import (
    CalibrationBand,
    CaseResult,
    Contains,
    JudgeReply,
    LlmRubric,
    Repeated,
    Run,
    Score,
    Verdict,
    compare,
    fold_judgements,
    judged,
    redact,
    run_from_json,
    run_to_json,
)
from digline.report import judge_reading
from digline.run import (
    Calibration,
    Case,
    Response,
    Suite,
    execute,
    planned_calls,
    rejudge,
)
from digline.wire import EXIT_USAGE

CREATED = "2026-01-01T00:00:00+00:00"
LATER = "2026-01-02T00:00:00+00:00"


def verdict(score: float | None, *, name: str = "llm_rubric") -> Verdict:
    if score is None:
        return Verdict(
            score=Score(name=name, score=None),
            threshold=0.5,
            status="error",
            reason="the judge raised",
            assertion_id="id",
        )
    return Verdict(
        score=Score(name=name, score=score),
        threshold=0.5,
        status="pass" if score >= 0.5 else "fail",
        reason="judged",
        assertion_id="id",
    )


def answers(*rows: Sequence[float | None]) -> list[list[Verdict]]:
    return [[verdict(score) for score in row] for row in rows]


# --------------------------------------------------------------------------- #
# §5.5 — what is recorded is what a plain replay records
# --------------------------------------------------------------------------- #


def test_the_first_judgement_is_what_the_verdict_records() -> None:
    folded = fold_judgements(answers((0.6, 0.9, 0.7)), min_agreement=1.0)
    plain = fold_judgements(answers((0.6,)), min_agreement=1.0)
    assert (folded.score.score, folded.status, folded.reason) == (
        plain.score.score,
        plain.status,
        plain.reason,
    )
    assert folded.score.samples == ()


def test_across_sampled_answers_the_fields_are_the_plain_fold() -> None:
    """`samples`, `sample_min` and `sample_max` are the first judgements of each
    answer, so `compare()`'s noise floor never sees the judge's range."""
    judged_twice = fold_judgements(
        answers((0.6, 0.0, 1.0), (0.8, 0.8, 0.8)), min_agreement=0.5
    )
    plain = fold_judgements(answers((0.6,), (0.8,)), min_agreement=0.5)
    assert judged_twice.score.score == plain.score.score == 0.7
    assert judged_twice.score.samples == plain.score.samples == (0.6, 0.8)
    assert judged_twice.score.sample_min == 0.6
    assert judged_twice.score.sample_max == 0.8
    assert judged_twice.status == plain.status
    assert judged_twice.reason == plain.reason


def test_a_first_judgement_that_errored_falls_to_the_first_that_scored() -> None:
    folded = fold_judgements(answers((None, 0.4, 0.9)), min_agreement=1.0)
    assert folded.score.score == 0.4
    assert folded.score.metadata["judge_errored"] == 1


def test_an_answer_no_judgement_scored_is_unjudged() -> None:
    folded = fold_judgements(answers((None, None)), min_agreement=1.0)
    assert folded.status == "error"
    assert folded.score.metadata["judge_errored"] == 2
    assert "judge_min" not in folded.score.metadata


# --------------------------------------------------------------------------- #
# §5.3, amended — the keys
# --------------------------------------------------------------------------- #


def test_the_bounds_are_the_widest_answers_own() -> None:
    """A min on one answer and a max on another would describe two different
    questions, not an unstable judge."""
    folded = fold_judgements(
        answers((0.0, 0.1, 0.1), (0.5, 0.9, 0.7), (1.0, 1.0, 1.0)),
        min_agreement=1 / 3,
    )
    metadata = folded.score.metadata
    assert metadata["judge_samples"] == 3
    assert metadata["judge_errored"] == 0
    assert (metadata["judge_min"], metadata["judge_max"]) == (0.5, 0.9)
    assert metadata["judge_answer"] == 2
    assert "judge_range" not in metadata


def test_a_tie_names_the_lowest_position() -> None:
    folded = fold_judgements(answers((0.2, 0.4), (0.6, 0.8)), min_agreement=0.5)
    assert folded.score.metadata["judge_answer"] == 1
    assert (folded.score.metadata["judge_min"], folded.score.metadata["judge_max"]) == (
        0.2,
        0.4,
    )


def test_no_range_where_no_answer_scored_twice() -> None:
    folded = fold_judgements(answers((0.5, None), (0.7, None)), min_agreement=0.5)
    assert "judge_min" not in folded.score.metadata
    assert folded.score.metadata["judge_errored"] == 2


def test_a_collapsed_judge_reads_as_perfectly_repeatable() -> None:
    """The reason the sentence never prints this alone."""
    folded = fold_judgements(answers((1.0, 1.0, 1.0)), min_agreement=1.0)
    assert folded.score.metadata["judge_min"] == folded.score.metadata["judge_max"]


# --------------------------------------------------------------------------- #
# The driver: which checks, how many calls, and on what
# --------------------------------------------------------------------------- #


class Judge:
    """Scores each prompt from a fixed sequence, per prompt, in call order: the
    first call on a prompt always gets `scores[0]`."""

    def __init__(self, scores: Sequence[float]) -> None:
        self.scores = list(scores)
        self.calls: Counter[str] = Counter()

    def __call__(self, prompt: str) -> JudgeReply:
        index = self.calls[prompt]
        self.calls[prompt] += 1
        return JudgeReply(score=self.scores[index % len(self.scores)], reason="r")


def recording_suite(judge: Judge, **extra: Any) -> Suite:
    fields: dict[str, Any] = {
        "tenant": "acme",
        "environment": "dev",
        "name": "qa",
        "assertions": [
            Contains(needle="Rome"),
            LlmRubric(rubric="right?", judge=judge, threshold=0.5, tolerance=0.05),
        ],
        "cases": [Case(id="one"), Case(id="two")],
        "record_responses": True,
    }
    fields.update(extra)
    return Suite(**fields)


def target(case: Case) -> Response:
    return Response(output=f"Rome, for {case.id}", input=f"capital? {case.id}")


def source_run() -> Run:
    return execute(recording_suite(Judge([0.6])), target, created_at=CREATED)


def test_judged_reads_kind_through_repeated() -> None:
    rubric = LlmRubric(rubric="r", judge=Judge([1.0]), threshold=0.5, tolerance=0.0)
    assert judged(rubric)
    assert judged(Repeated(inner=rubric, samples=2, min_agreement="2/2"))
    assert not judged(Contains(needle="x"))


def test_only_judged_checks_are_asked_again_and_the_rest_are_untouched() -> None:
    source = source_run()
    judge = Judge([0.6, 0.9, 0.2])
    replay = rejudge(
        recording_suite(judge), source, key="k", created_at=LATER, judge_samples=3
    )
    assert set(judge.calls.values()) == {3}
    contains = replay.results[0].verdicts[0]
    assert not any(key.startswith("judge_") for key in contains.score.metadata)
    rubric = replay.results[0].verdicts[1]
    assert rubric.score.score == 0.6
    assert (rubric.score.metadata["judge_min"], rubric.score.metadata["judge_max"]) == (
        0.2,
        0.9,
    )
    assert replay.judge_samples == 3
    assert replay.rejudged_from == "k"


def test_a_judged_replay_records_what_a_plain_replay_records() -> None:
    """Same scores, extra metadata: comparing the two isolates the flag."""
    source = source_run()
    plain = rejudge(
        recording_suite(Judge([0.6, 0.9])), source, key="k", created_at=LATER
    )
    measured = rejudge(
        recording_suite(Judge([0.6, 0.9])),
        source,
        key="k",
        created_at=LATER,
        judge_samples=4,
    )
    comparison = compare(measured, plain)
    assert {d.outcome for d in comparison.deltas} == {"unchanged"}
    assert all(d.delta == 0.0 for d in comparison.deltas)
    against_source = [
        (d.outcome, d.noise_min, d.noise_max) for d in compare(measured, source).deltas
    ]
    assert against_source == [
        (d.outcome, d.noise_min, d.noise_max) for d in compare(plain, source).deltas
    ]


def test_it_is_refused_on_a_live_target_before_any_call() -> None:
    judge = Judge([1.0])
    asked: list[str] = []

    def live(case: Case) -> Response:
        asked.append(case.id)
        return target(case)

    with pytest.raises(ValueError, match="only on a replay"):
        execute(recording_suite(judge), live, created_at=CREATED, judge_samples=3)
    with pytest.raises(ValueError, match="at least two"):
        execute(recording_suite(judge), live, created_at=CREATED, judge_samples=1)
    assert asked == [] and not judge.calls


def test_the_calibration_case_is_judged_again_too() -> None:
    calibrated = recording_suite(
        Judge([0.5, 0.4]),
        cases=[
            Case(id="one"),
            Case(
                id="half",
                calibration=Calibration(
                    output="HALF", check="llm_rubric", low=0.3, high=0.7, input=""
                ),
            ),
        ],
        samples=2,
        min_agreement="1/2",
    )

    def twice(case: Case) -> Response:
        return target(case)

    source = execute(calibrated, twice, created_at=CREATED)
    replay = rejudge(calibrated, source, key="k", created_at=LATER, judge_samples=2)
    half = replay.results[1].verdicts[0]
    assert half.score.score == 0.5
    assert half.score.metadata["judge_samples"] == 2


def test_the_plan_announces_the_judge_calls() -> None:
    suite = recording_suite(Judge([1.0]))
    sentence = planned_calls(suite, judge_samples=5).sentence(replayed=True)
    assert "each recorded answer is judged 5 times by llm_rubric" in sentence
    assert "judged" not in planned_calls(suite).sentence(replayed=True)


# --------------------------------------------------------------------------- #
# §9 — the document
# --------------------------------------------------------------------------- #


def test_the_count_round_trips_and_is_absent_when_unset() -> None:
    source = source_run()
    replay = rejudge(
        recording_suite(Judge([0.6, 0.8])),
        source,
        key="k",
        created_at=LATER,
        judge_samples=2,
    )
    assert json.loads(run_to_json(replay))["judge_samples"] == 2
    assert run_from_json(run_to_json(replay)) == replay
    assert "judge_samples" not in json.loads(run_to_json(source))


def test_the_count_and_the_range_survive_redaction() -> None:
    """All numbers, about our own instrument."""
    source = source_run()
    replay = rejudge(
        recording_suite(Judge([0.6, 0.8])),
        source,
        key="k",
        created_at=LATER,
        judge_samples=2,
    )
    hidden = redact(replay)
    assert hidden.judge_samples == 2
    assert hidden.results[0].verdicts[1].score.metadata["judge_max"] == 0.8


@pytest.mark.parametrize("count", [1, -1])
def test_a_count_that_measures_nothing_is_refused(count: int) -> None:
    with pytest.raises(ValueError, match="at least 2"):
        Run(
            tenant="acme",
            environment="dev",
            suite="qa",
            config_hash="h",
            created_at=CREATED,
            rejudged_from="k",
            judge_samples=count,
        )


def test_a_count_on_a_run_that_is_not_a_replay_is_refused() -> None:
    with pytest.raises(ValueError, match="only a replay"):
        Run(
            tenant="acme",
            environment="dev",
            suite="qa",
            config_hash="h",
            created_at=CREATED,
            judge_samples=3,
        )


# --------------------------------------------------------------------------- #
# §5.4 — the sentence, never without the scale
# --------------------------------------------------------------------------- #


def judged_run(
    *rows: tuple[str, float, float, int], calibration: tuple[float, bool] | None = None
) -> Run:
    results: list[CaseResult] = []
    for case_id, low, high, answer in rows:
        v = verdict(low)
        results.append(
            CaseResult(
                case_id,
                (
                    Verdict(
                        score=Score(
                            name="faithfulness",
                            score=low,
                            metadata={
                                "judge_samples": 5,
                                "judge_errored": 0,
                                "judge_min": low,
                                "judge_max": high,
                                "judge_answer": answer,
                            },
                        ),
                        threshold=v.threshold,
                        status=v.status,
                        reason="r",
                        assertion_id="id",
                    ),
                ),
            )
        )
    if calibration is not None:
        score, _ = calibration
        results.append(
            CaseResult(
                "half-supported",
                (verdict(score, name="faithfulness"),),
                calibration=CalibrationBand("faithfulness", 0.3, 0.7, "id"),
            )
        )
    return Run(
        tenant="acme",
        environment="dev",
        suite="qa",
        config_hash="h",
        created_at=LATER,
        results=tuple(results),
        rejudged_from="k",
        judge_samples=5,
    )


def test_the_sentence_names_the_widest_answer_and_the_calibration_inside() -> None:
    run = judged_run(
        ("steady", 0.5, 0.55, 1),
        ("refund-policy", 0.4, 0.5, 3),
        calibration=(0.5, True),
    )
    assert judge_reading(run, locale="en") == (
        "the judge's own range on these answers is at most 0.100000 across 5 "
        "judgements (faithfulness, answer 3 of case refund-policy); measured on "
        "recorded answers, which are not a sample of what a live run produces, "
        "so this is a lower bound on the judge's range in production; the "
        "calibration case half-supported scored 0.500000, inside its declared "
        "band 0.300000–0.700000"
    )


def test_a_suite_with_no_calibration_case_is_told_what_that_costs() -> None:
    run = judged_run(("steady", 1.0, 1.0, 1))
    assert judge_reading(run, locale="en") == (
        "the judge's own range on these answers is at most 0.000000 across 5 "
        "judgements (faithfulness, answer 1 of case steady); measured on "
        "recorded answers, which are not a sample of what a live run produces, "
        "so this is a lower bound on the judge's range in production; this suite "
        "declares no calibration case, and a judge that has lost its scale reads "
        "as perfectly repeatable"
    )


def test_a_lost_scale_is_named_first_among_calibration_cases() -> None:
    run = judged_run(("steady", 1.0, 1.0, 1), calibration=(1.0, False))
    assert "outside its declared band" in judge_reading(run, locale="en")


# --------------------------------------------------------------------------- #
# The range is a floor, and the reading says so (ADR 0024 §5.6)
# --------------------------------------------------------------------------- #


def test_the_range_says_it_is_a_lower_bound_in_both_locales() -> None:
    """A replay measures the judge on answers that did not move, and those are
    not a sample of what a live run produces — 2.0% abstention on replayed
    answers against 8–10.5% on live ones, on the suite that measured it.

    The record states it; this is the line where somebody reads the number. A
    record nobody opens protects nobody, which is the argument the seven
    absences already make: a reading declares what it cannot know.
    """
    run = judged_run(("steady", 0.4, 0.9, 1))
    assert (
        "so this is a lower bound on the judge's range in production"
        in judge_reading(run, locale="en")
    )
    assert (
        "quindi questo è un limite inferiore all'intervallo del giudice in "
        "produzione" in judge_reading(run, locale="it")
    )


def test_the_floor_clause_qualifies_the_range_it_is_about() -> None:
    """It sits between the range and the calibration result, because it is a
    caveat on the first and says nothing about the second. A reader who stops
    at the semicolon has still read the qualifier."""
    run = judged_run(("steady", 0.4, 0.9, 1), calibration=(0.5, True))
    text = judge_reading(run, locale="en")
    assert text.index("lower bound") < text.index("calibration case")


def test_an_unmeasured_range_is_not_given_a_floor() -> None:
    """The control that must fail, and the case that makes the clause wrong.

    Where no answer returned two scores there is no range, and qualifying a
    measurement that does not exist would be a caveat about nothing — the shape
    the spread's four causes were split apart to avoid.
    """
    run = judged_run(("steady", 0.5, 0.5, 1))
    bare = replace(run, results=(CaseResult("steady", ()),))
    text = judge_reading(bare, locale="en")
    assert "was not measured" in text
    assert "lower bound" not in text


def test_the_unmeasured_range_and_the_errored_judgements_are_said() -> None:
    run = judged_run(("steady", 0.5, 0.5, 1))
    bare = Run(
        tenant="acme",
        environment="dev",
        suite="qa",
        config_hash="h",
        created_at=LATER,
        results=(
            CaseResult(
                "steady",
                (
                    Verdict(
                        score=Score(
                            name="faithfulness",
                            score=0.5,
                            metadata={"judge_samples": 5, "judge_errored": 4},
                        ),
                        threshold=0.5,
                        status="pass",
                        reason="r",
                        assertion_id="id",
                    ),
                ),
            ),
        ),
        rejudged_from="k",
        judge_samples=5,
    )
    reading = judge_reading(bare, locale="en")
    assert reading.startswith("the judge's own range on these answers was not measured")
    assert ", and 4 judgements returned no score" in reading
    assert "declares no calibration case" in reading
    assert "0.000000" in judge_reading(run, locale="en")


@pytest.mark.parametrize("locale", ["en", "it"])
def test_nothing_it_says_is_a_guess_or_advice(locale: str) -> None:
    from digline.report import TEXT

    for key, text in TEXT[locale].items():  # type: ignore[index]
        if key.startswith("judged."):
            assert not spoken(ADVICE, text), (key, text)
            assert not spoken(SPECULATION, text), (key, text)
    run = judged_run(("steady", 0.4, 0.5, 2), calibration=(1.0, False))
    assert "0.100000" in judge_reading(run, locale=locale)  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# End to end
# --------------------------------------------------------------------------- #


SUITE_PY = """
from collections import Counter

from digline.core import Contains, JudgeReply, LlmRubric
from digline.run import Case, Response, Suite

SCORES = [0.6, 0.9, 0.3]
SEEN = Counter()


def judge(prompt):
    index = SEEN[prompt]
    SEEN[prompt] += 1
    return JudgeReply(score=SCORES[index % len(SCORES)], reason="r")


suite = Suite(
    tenant="acme-bank",
    environment="staging",
    name="judged",
    assertions=[
        Contains(needle="Rome"),
        LlmRubric(rubric="right?", judge=judge, threshold=0.5, tolerance=0.05),
    ],
    cases=[Case(id="one"), Case(id="two")],
    record_responses=True,
)


def target(case):
    return Response(output="Rome " + case.id, input="capital?")
"""


def test_rejudge_reports_the_range_beside_the_scale(repo: Path) -> None:
    (repo / "suite_judged.py").write_text(SUITE_PY, encoding="utf-8")
    source = cli(repo, "run", "--suite", "suite_judged.py").stdout.strip()

    done = cli(
        repo,
        "rejudge",
        "--suite",
        "suite_judged.py",
        "--run",
        source,
        "--judge-samples",
        "3",
        "--json",
    )
    assert done.returncode == 0, done.stderr
    assert "each recorded answer is judged 3 times by llm_rubric" in done.stderr
    assert (
        "digline: the judge's own range on these answers is at most 0.600000 across "
        "3 judgements (llm_rubric, answer 1 of case one); measured on recorded "
        "answers, which are not a sample of what a live run produces, so this is a "
        "lower bound on the judge's range in production; this suite declares no "
        "calibration case" in done.stderr
    )
    payload = json.loads(done.stdout)
    assert payload["judge_reading"].startswith("the judge's own range")

    promoted = cli(
        repo,
        "promote",
        "--replacing",
        baseline_in(repo),
        "--suite",
        "suite_judged.py",
        "--run",
        payload["key"],
    )
    assert "ReplayedRunError" in promoted.stderr

    once = cli(
        repo,
        "rejudge",
        "--suite",
        "suite_judged.py",
        "--run",
        source,
        "--judge-samples",
        "1",
    )
    assert once.returncode == EXIT_USAGE
    assert "a range needs at least 2" in once.stderr

    plain = cli(
        repo, "rejudge", "--suite", "suite_judged.py", "--run", source, "--json"
    )
    assert "judge_reading" not in json.loads(plain.stdout)
    assert "own range" not in plain.stderr
