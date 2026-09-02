"""ADR 0006: repeated samples and the noise floor.

The ADR was written against a real event — the same suite, the same
`config_hash`, three runs inside fifteen minutes, one case going 5/5 → 2/5 →
5/5, and a reported regression that was nothing. The two surviving runs are in
`tests/fixtures/brief/`, and the last section of this file asserts against them
rather than against a hand-written approximation of them.

Everything above that section is the machinery, tested where it is defined:
what a sampled `Score` records, what survives serialization and redaction, what
a document written before this ADR gains on migration, and where the floor of
§5 does and does not reach.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import pytest

from digline.core import (
    Accuracy,
    AssertionDelta,
    CaseOutcome,
    CaseResult,
    Label,
    Run,
    Score,
    Verdict,
    combine_samples,
    compare,
    per_sample_outcomes,
    redact,
    run_from_json,
    run_to_json,
    with_noise_interval,
)
from digline.core.run import SCHEMA_VERSION
from digline.store.migrate import upgrade_document

CREATED = "2026-01-01T00:00:00+00:00"


def make_run(verdicts: Sequence[Verdict], *, case_id: str = "c1") -> Run:
    return Run(
        tenant="acme",
        environment="staging",
        suite="s",
        config_hash="h",
        created_at=CREATED,
        results=(CaseResult(case_id=case_id, verdicts=tuple(verdicts)),),
    )


def sample(score: float, *, threshold: float = 0.5, name: str = "check") -> Verdict:
    """One un-folded sample: what an assertion returns before anything repeats
    it."""
    return Verdict(
        score=Score(name=name, score=score),
        threshold=threshold,
        status="pass" if score >= threshold else "fail",
        reason=f"sample scored {score}",
        assertion_id=f"id-{name}",
    )


# -- §4: what a sampled score records ------------------------------------- #


def test_a_single_sample_records_no_interval() -> None:
    """The absence rule, and the reason a suite at `samples=1` is untouched by
    this ADR: there is nothing to record, so nothing is."""
    plain = Score(name="check", score=0.9)
    assert plain.samples == ()
    assert plain.sample_min is None and plain.sample_max is None
    assert not plain.sampled


def test_the_fold_records_the_raw_samples_and_the_interval() -> None:
    folded = combine_samples(
        [sample(1.0), sample(1.0), sample(0.0), sample(0.0), sample(0.0)],
        min_agreement=0.5,
    )
    # §2: the scalar is untouched — the mean of five binary samples is the
    # majority vote, and 2/5 is 0.4.
    assert folded.score.score == 0.4
    assert folded.score.samples == (1.0, 1.0, 0.0, 0.0, 0.0)
    assert folded.score.sample_min == 0.0
    assert folded.score.sample_max == 1.0


def test_the_fields_carry_the_same_numbers_as_the_metadata() -> None:
    """Two views of one measurement. The metadata half is reported, the fields
    are acted on — but they must never disagree."""
    folded = combine_samples([sample(0.8), sample(0.6), sample(0.7)], min_agreement=0.5)
    assert list(folded.score.samples) == folded.score.metadata["scores"]


def test_an_errored_sample_is_not_in_the_interval_but_is_still_counted() -> None:
    errored = Verdict(
        score=Score(name="check", score=None),
        threshold=0.5,
        status="error",
        reason="could not judge",
        assertion_id="id-check",
    )
    folded = combine_samples([sample(1.0), sample(1.0), errored], min_agreement=0.5)
    assert folded.score.samples == (1.0, 1.0)
    assert folded.score.metadata["errored_samples"] == 1


def test_an_interval_that_the_samples_do_not_span_is_refused() -> None:
    with pytest.raises(ValueError, match="not the one its samples span"):
        Score(
            name="check", score=0.5, samples=(0.4, 0.6), sample_min=0.0, sample_max=1.0
        )


def test_half_an_interval_is_refused() -> None:
    """A noise floor built from one end would admit movement in a direction
    nobody measured, and would do it silently."""
    with pytest.raises(ValueError, match="without sample_min and sample_max"):
        Score(name="check", score=0.5, samples=(0.4, 0.6), sample_min=0.4)


def test_an_interval_without_samples_is_refused() -> None:
    with pytest.raises(ValueError, match="without the samples it spans"):
        Score(name="check", score=0.5, sample_min=0.4, sample_max=0.6)


def test_rounding_the_mean_does_not_drop_the_interval() -> None:
    """`Verdict` rebuilds its `Score` when the mean needs rounding, which is
    most sampled checks. A rebuild that dropped the fields would delete the
    noise floor of exactly those, and would do it invisibly."""
    folded = combine_samples([sample(1.0), sample(0.0), sample(1.0)], min_agreement=0.5)
    assert folded.score.score == 0.666667
    assert folded.score.samples == (1.0, 0.0, 1.0)


# -- §4: they travel ------------------------------------------------------- #


def test_the_interval_survives_redaction() -> None:
    """Stated rather than inherited: as `Score` fields they bypass `travels()`,
    so `redact()` copies them explicitly. They measure the system's own
    variability, like `spread`, not what it judged."""
    folded = combine_samples([sample(1.0), sample(0.0), sample(1.0)], min_agreement=0.5)
    run = make_run([folded])
    stripped = redact(run)
    kept = stripped.results[0].verdicts[0].score
    assert kept.samples == (1.0, 0.0, 1.0)
    assert (kept.sample_min, kept.sample_max) == (0.0, 1.0)
    # And the payload still went.
    assert stripped.results[0].verdicts[0].reason == "<redacted>"


# -- §4 and §11: the document ---------------------------------------------- #


def test_a_sampled_verdict_round_trips_through_the_document() -> None:
    folded = combine_samples([sample(1.0), sample(0.0), sample(1.0)], min_agreement=0.5)
    back = run_from_json(run_to_json(make_run([folded])))
    restored = back.results[0].verdicts[0].score
    assert restored.samples == (1.0, 0.0, 1.0)
    assert (restored.sample_min, restored.sample_max) == (0.0, 1.0)


def test_an_unsampled_run_writes_none_of_the_three_keys() -> None:
    """Absent, never `null`. This is what keeps a run file from a suite at
    `samples=1` byte for byte the file it was before this ADR."""
    document = run_to_json(make_run([sample(0.9)]))
    assert "sample_min" not in document
    assert '"samples"' not in document


def test_migration_derives_the_interval_from_the_scores_already_recorded() -> None:
    """§11. Reading a list that is in the document is not the guessing
    `migrate.py` refuses, and it is the difference between every promoted
    baseline being a noise floor on the day of the release and being one after
    everybody re-promotes."""
    old: dict[str, Any] = {
        "schema_version": 8,
        "tenant": "acme",
        "environment": "staging",
        "redacted": False,
        "suite": "s",
        "config_hash": "h",
        "created_at": CREATED,
        "git_commit": None,
        "metadata": {},
        "artifacts": {},
        "target_config": {},
        "judge_config": {},
        "aggregate": [],
        "results": [
            {
                "case_id": "c1",
                "suspended": False,
                "verdicts": [
                    {
                        "assertion": "check",
                        "assertion_id": "id-check",
                        "score": 0.4,
                        "status": "fail",
                        "threshold": 0.5,
                        "tolerance": 0.0,
                        "reason": "mean of 5 samples",
                        "metadata": {
                            "samples": 5,
                            "agreement": 0.6,
                            "spread": 1.0,
                            "errored_samples": 0,
                            "scores": [1.0, 1.0, 0.0, 0.0, 0.0],
                        },
                    }
                ],
            }
        ],
    }
    upgraded = upgrade_document(old)
    assert upgraded["schema_version"] == SCHEMA_VERSION
    verdict = upgraded["results"][0]["verdicts"][0]
    assert verdict["samples"] == [1.0, 1.0, 0.0, 0.0, 0.0]
    assert verdict["sample_min"] == 0.0
    assert verdict["sample_max"] == 1.0


def test_migration_invents_no_interval_for_an_unsampled_verdict() -> None:
    """At one sample there is no interval. `[score, score]` would hand a check a
    noise floor of zero width dressed as a measurement."""
    old: dict[str, Any] = {
        "schema_version": 8,
        "tenant": "acme",
        "environment": "staging",
        "redacted": False,
        "suite": "s",
        "config_hash": "h",
        "created_at": CREATED,
        "git_commit": None,
        "metadata": {},
        "artifacts": {},
        "target_config": {},
        "judge_config": {},
        "aggregate": [],
        "results": [
            {
                "case_id": "c1",
                "suspended": False,
                "verdicts": [
                    {
                        "assertion": "check",
                        "assertion_id": "id-check",
                        "score": 0.9,
                        "status": "pass",
                        "threshold": 0.5,
                        "tolerance": 0.0,
                        "reason": "scored 0.9",
                        "metadata": {},
                    }
                ],
            }
        ],
    }
    verdict = upgrade_document(old)["results"][0]["verdicts"][0]
    assert "samples" not in verdict
    assert "sample_min" not in verdict


# -- §5 and §6: where the floor reaches, and where it does not ------------- #


def compare_one(now: Verdict, before: Verdict) -> AssertionDelta:
    """One check, one case, on both sides."""
    comparison = compare(make_run([now]), make_run([before]))
    assert len(comparison.deltas) == 1
    return comparison.deltas[0]


def folded(*scores: float, threshold: float = 0.5) -> Verdict:
    return combine_samples(
        [sample(value, threshold=threshold) for value in scores], min_agreement=0.0
    )


def test_a_drop_inside_the_baselines_interval_is_unchanged() -> None:
    """The rule this ADR exists for. The baseline wobbled between 0.6 and 1.0
    over its own five samples; a run landing at 0.7 has not said anything the
    baseline did not already say."""
    before = folded(1.0, 1.0, 0.6, 1.0, 0.8)
    now = folded(0.7, 0.7, 0.7, 0.7, 0.7)
    delta = compare_one(now, before)
    assert delta.outcome == "unchanged"
    assert delta.within_noise
    assert (delta.noise_min, delta.noise_max, delta.noise_samples) == (0.6, 1.0, 5)


def test_a_drop_outside_the_interval_is_still_a_regression() -> None:
    before = folded(1.0, 1.0, 0.9, 1.0, 0.9)
    now = folded(0.6, 0.6, 0.6, 0.6, 0.6)
    delta = compare_one(now, before)
    assert delta.outcome == "regressed"
    assert not delta.within_noise
    # The interval rides along anyway: the report says what the movement left.
    assert (delta.noise_min, delta.noise_max) == (0.9, 1.0)
    assert "beyond the noise" in delta.reason


def test_the_floor_is_the_baselines_and_never_this_runs() -> None:
    """A run that got less stable must not widen its own excuse. The baseline is
    the promoted, reviewed measurement; this one is not."""
    before = folded(0.9, 0.9, 0.9, 0.9, 0.9)
    now = folded(1.0, 1.0, 0.6, 0.6, 0.6)  # spans 0.6-1.0, mean 0.76
    delta = compare_one(now, before)
    assert delta.outcome == "regressed"
    assert not delta.within_noise


def test_a_rise_inside_the_interval_is_not_an_improvement_either() -> None:
    """One test for both directions. Noise explains a movement whichever way it
    went, and calling this an improvement would be the same false finding with
    a friendlier name."""
    before = folded(0.6, 1.0, 0.6, 0.6, 0.6)
    now = folded(0.9, 0.9, 0.9, 0.9, 0.9)
    delta = compare_one(now, before)
    assert delta.outcome == "unchanged"
    assert delta.within_noise


def test_an_unanimous_baseline_has_no_floor() -> None:
    """§6. Five out of five is the ordinary case away from the boundary, and it
    leaves an interval of zero width — so every later change of mind is still
    reported. That is right rather than unfortunate."""
    before = folded(1.0, 1.0, 1.0, 1.0, 1.0)
    now = folded(1.0, 1.0, 1.0, 0.0, 1.0)
    delta = compare_one(now, before)
    assert delta.outcome == "regressed"
    assert not delta.within_noise
    assert (delta.noise_min, delta.noise_max) == (1.0, 1.0)


def test_a_baseline_with_no_samples_keeps_the_absolute_rule() -> None:
    """The third branch of §5: a baseline that predates this ADR, or a suite at
    `samples=1`. Today's rule, unchanged, and nothing pretends to know the
    noise."""
    before = Verdict(
        score=Score(name="check", score=0.9),
        threshold=0.5,
        status="pass",
        reason="scored 0.9",
        assertion_id="id-check",
    )
    now = Verdict(
        score=Score(name="check", score=0.7),
        threshold=0.5,
        status="pass",
        reason="scored 0.7",
        assertion_id="id-check",
    )
    delta = compare_one(now, before)
    assert delta.outcome == "regressed"
    assert delta.noise_min is None and delta.noise_samples == 0
    assert "beyond the noise" not in delta.reason


def test_a_flip_is_never_within_noise() -> None:
    """§6, and the guardrail that needs no extra code: rule 3 of `compare()`
    sits above rule 4, so a drop through the threshold is reported whatever the
    samples did."""
    before = folded(1.0, 0.0, 1.0, 1.0, 1.0)  # mean 0.8, spans 0.0-1.0
    now = folded(0.0, 0.0, 1.0, 0.0, 0.0)  # mean 0.2, inside that interval
    delta = compare_one(now, before)
    assert delta.outcome == "regressed"
    assert not delta.within_noise


def test_the_declared_tolerance_is_checked_before_the_measured_floor() -> None:
    """Both produce `unchanged`, and the reason says which one spoke."""
    before = combine_samples(
        [sample(v, threshold=0.5) for v in (1.0, 0.6, 1.0, 1.0, 1.0)],
        min_agreement=0.0,
    )
    now = combine_samples(
        [
            Verdict(
                score=Score(name="check", score=0.9),
                threshold=0.5,
                tolerance=0.2,
                status="pass",
                reason="s",
                assertion_id="id-check",
            )
            for _ in range(2)
        ],
        min_agreement=0.0,
    )
    delta = compare_one(now, before)
    assert delta.outcome == "unchanged"
    assert not delta.within_noise
    assert "within tolerance" in delta.reason


# -- §7: the aggregate gets an interval of its own ------------------------- #


def outcome(case_id: str, label: Label, *scores: float) -> CaseOutcome:
    return CaseOutcome(case_id=case_id, label=label, verdict=folded(*scores))


def test_an_aggregate_records_what_a_single_sample_would_have_said() -> None:
    """An aggregate is computed once per run from the folded verdicts, so it has
    no samples and §5 would never reach it. Evaluating it once per sample index
    is what gives it an interval — and it costs no call to anything."""
    outcomes = [
        outcome("a", "positive", 1.0, 1.0, 1.0),
        outcome("b", "positive", 1.0, 0.0, 1.0),
        outcome("c", "negative", 1.0, 1.0, 0.0),
    ]
    verdict = with_noise_interval(
        Accuracy(over="check", threshold="1/2", tolerance=0.0), outcomes
    )
    # Sample 0: all three agree with the mark. Sample 1: two of three.
    # Sample 2: two of three.
    assert verdict.score.samples == (1.0, 0.666667, 0.666667)
    assert verdict.score.sample_min == 0.666667
    assert verdict.score.sample_max == 1.0


def test_the_recorded_aggregate_score_is_the_folded_one_and_does_not_move() -> None:
    """The per-sample values answer a different question — "what would a single
    run have said" — and their only job is to size the noise. Every threshold
    measured against the current definition stays valid."""
    outcomes = [
        outcome("a", "positive", 1.0, 1.0, 1.0),
        outcome("b", "positive", 1.0, 0.0, 1.0),
        outcome("c", "negative", 1.0, 1.0, 0.0),
    ]
    accuracy = Accuracy(over="check", threshold="1/2", tolerance=0.0)
    assert (
        with_noise_interval(accuracy, outcomes).score.score
        == accuracy(outcomes).score.score
    )


def test_an_unsampled_run_gives_its_aggregate_no_interval() -> None:
    plain = Verdict(
        score=Score(name="check", score=1.0),
        threshold=0.5,
        status="pass",
        reason="scored 1.0",
        assertion_id="id-check",
    )
    outcomes = [CaseOutcome(case_id="a", label="positive", verdict=plain)]
    verdict = with_noise_interval(
        Accuracy(over="check", threshold="1/2", tolerance=0.0), outcomes
    )
    assert not verdict.score.sampled


def test_cases_that_do_not_agree_on_how_many_samples_give_no_interval() -> None:
    """Sample 2 of one case and sample 3 of another are not one run. An
    aggregate is a statement about the whole run: it is either the same run N
    times or it is nothing."""
    outcomes = [
        outcome("a", "positive", 1.0, 1.0, 1.0),
        outcome("b", "positive", 1.0, 0.0),
    ]
    assert per_sample_outcomes(outcomes) == ()
    verdict = with_noise_interval(
        Accuracy(over="check", threshold="1/2", tolerance=0.0), outcomes
    )
    assert not verdict.score.sampled


def test_a_suspended_case_is_excluded_from_every_sample() -> None:
    outcomes = [
        outcome("a", "positive", 1.0, 1.0, 0.0),
        CaseOutcome(case_id="b", label="negative", verdict=None),
    ]
    slices = per_sample_outcomes(outcomes)
    assert len(slices) == 3
    assert all(one[1].verdict is None for one in slices)


def test_the_aggregates_interval_reaches_compare() -> None:
    """End to end: the aggregate of a run that wobbled by one case is `unchanged`
    against a baseline whose own samples covered that much."""
    baseline_outcomes = [
        outcome("a", "positive", 1.0, 1.0, 1.0),
        outcome("b", "positive", 1.0, 0.0, 1.0),
        outcome("c", "negative", 1.0, 1.0, 1.0),
    ]
    now_outcomes = [
        outcome("a", "positive", 1.0, 1.0, 1.0),
        outcome("b", "positive", 0.0, 0.0, 0.0),
        outcome("c", "negative", 1.0, 1.0, 1.0),
    ]
    accuracy = Accuracy(over="check", threshold="1/2", tolerance=0.0)
    before = with_noise_interval(accuracy, baseline_outcomes)
    now = with_noise_interval(accuracy, now_outcomes)
    assert before.score.score == 1.0 and now.score.score == 0.666667
    comparison = compare(
        Run(
            tenant="acme",
            environment="staging",
            suite="s",
            config_hash="h",
            created_at=CREATED,
            aggregate=(now,),
        ),
        Run(
            tenant="acme",
            environment="staging",
            suite="s",
            config_hash="h",
            created_at=CREATED,
            aggregate=(before,),
        ),
    )
    delta = comparison.deltas[0]
    assert delta.scope == "run"
    assert delta.outcome == "unchanged"
    assert delta.within_noise
