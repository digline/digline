"""One test per each of the six outcomes, plus the two precedence rules.

`compare()` is where digline differs: a threshold catches "below 0.7", this
catches "was 0.91, now 0.78, still above the threshold".
"""

from __future__ import annotations

import pytest

from digline.core import (
    CaseResult,
    EvaluatorInputs,
    JudgeReply,
    LlmRubric,
    Run,
    Score,
    Verdict,
    compare,
    config_hash,
)

CREATED = "2026-01-01T00:00:00+00:00"


def verdict(
    name: str,
    score: float | None,
    *,
    threshold: float = 0.5,
    tolerance: float = 0.0,
    assertion_id: str = "",
) -> Verdict:
    """`status` is derived, never passed in: `Verdict.__post_init__` now refuses
    a status that contradicts score-against-threshold, so there is nothing left
    for a caller to override."""
    if score is None:
        return Verdict(
            score=Score(name=name, score=None),
            threshold=threshold,
            tolerance=tolerance,
            status="error",
            reason="test reason",
            assertion_id=assertion_id,
        )
    resolved = "pass" if score >= threshold else "fail"
    return Verdict(
        score=Score(name=name, score=score),
        threshold=threshold,
        tolerance=tolerance,
        status=resolved,  # type: ignore[arg-type]
        reason="test reason",
        assertion_id=assertion_id,
    )


def run_of(*verdicts: Verdict, case: str = "case-1", cfg: str = "hash-a") -> Run:
    return Run(
        tenant="acme",
        environment="test",
        suite="test-suite",
        config_hash=cfg,
        created_at=CREATED,
        results=(CaseResult(case_id=case, verdicts=verdicts),),
    )


def only(run: Run, baseline: Run) -> str:
    result = compare(run, baseline)
    assert len(result.deltas) == 1, result.deltas
    return result.deltas[0].outcome


# --------------------------------------------------------------------------- #
# The six outcomes
# --------------------------------------------------------------------------- #


def test_regressed_when_the_score_drops_beyond_tolerance() -> None:
    # Both stay above the threshold: exactly the regression a threshold alone
    # would never see.
    assert (
        only(run_of(verdict("rubric", 0.78)), run_of(verdict("rubric", 0.91)))
        == "regressed"
    )


def test_improved_when_the_score_rises_beyond_tolerance() -> None:
    assert (
        only(run_of(verdict("rubric", 0.91)), run_of(verdict("rubric", 0.78)))
        == "improved"
    )


def test_unchanged_when_the_delta_is_within_tolerance() -> None:
    current = run_of(verdict("rubric", 0.89, tolerance=0.05))
    baseline = run_of(verdict("rubric", 0.91, tolerance=0.05))
    assert only(current, baseline) == "unchanged"


def test_new_when_the_assertion_is_absent_from_the_baseline() -> None:
    assert only(run_of(verdict("contains", 1.0)), run_of()) == "new"


def test_missing_when_the_assertion_vanished_from_the_run() -> None:
    assert only(run_of(), run_of(verdict("contains", 1.0))) == "missing"


def test_errored_when_either_side_is_in_error() -> None:
    assert (
        only(run_of(verdict("rubric", None)), run_of(verdict("rubric", 0.91)))
        == "errored"
    )


# --------------------------------------------------------------------------- #
# The two precedence rules from ADR 0001
# --------------------------------------------------------------------------- #


def test_an_error_is_neither_a_regression_nor_green() -> None:
    result = compare(run_of(verdict("rubric", None)), run_of(verdict("rubric", 0.91)))
    assert result.errored and not result.has_regressions
    assert result.deltas[0].delta is None


def test_an_error_in_the_baseline_counts_just_the_same() -> None:
    assert (
        only(run_of(verdict("rubric", 0.91)), run_of(verdict("rubric", None)))
        == "errored"
    )


def test_a_flipped_outcome_beats_the_tolerance() -> None:
    """A pass turning into a fail is a regression even under a huge tolerance:
    a flipped outcome is never noise."""
    current = run_of(verdict("rubric", 0.69, threshold=0.70, tolerance=0.9))
    baseline = run_of(verdict("rubric", 0.71, threshold=0.70, tolerance=0.9))
    assert only(current, baseline) == "regressed"


def test_a_flip_towards_green_is_an_improvement() -> None:
    current = run_of(verdict("rubric", 0.71, threshold=0.70, tolerance=0.9))
    baseline = run_of(verdict("rubric", 0.69, threshold=0.70, tolerance=0.9))
    assert only(current, baseline) == "improved"


def test_a_flip_within_a_realistic_tolerance_is_still_a_regression() -> None:
    """0.71 -> 0.69 is a delta of 0.02, well inside a tolerance of 0.05. Rule 4
    would call it `unchanged`; rule 3 fires first because the gate flipped."""
    current = run_of(verdict("rubric", 0.69, threshold=0.70, tolerance=0.05))
    baseline = run_of(verdict("rubric", 0.71, threshold=0.70, tolerance=0.05))
    assert only(current, baseline) == "regressed"


def test_an_error_wins_over_what_would_look_like_a_regression() -> None:
    """The score fell far enough to be a regression by rule 4, but one side
    errored: rule 2 fires first and the outcome is neither green nor a
    regression."""
    current = run_of(verdict("rubric", None))
    baseline = run_of(verdict("rubric", 0.99))
    result = compare(current, baseline)
    assert result.counts == {"errored": 1}
    assert not result.has_regressions
    assert result.deltas[0].delta is None


def test_a_flip_caused_by_a_moved_threshold_says_so() -> None:
    """Otherwise a config change reads in the PR like a worse model, and the
    reviewer blames the prompt."""
    current = run_of(verdict("rubric", 0.80, threshold=0.90))
    baseline = run_of(verdict("rubric", 0.80, threshold=0.70))
    delta = compare(current, baseline).deltas[0]
    assert delta.outcome == "regressed"
    assert "threshold moved" in delta.reason
    assert delta.delta == pytest.approx(0.0)


def test_a_raised_threshold_pairs_the_verdicts_instead_of_splitting_them() -> None:
    """Built from real assertions, because this is exactly what breaks if
    `identity` folds the threshold in: the two verdicts would stop meeting and
    the comparison would report `new` + `missing` instead of the flip.

    It also proves the "threshold moved" branch is reachable at all — with the
    threshold inside `identity` it was dead code.
    """

    def judge(prompt: str) -> JudgeReply:
        return JudgeReply(score=0.8, reason="fixed")

    lenient = LlmRubric(rubric="polite?", judge=judge, threshold=0.7, tolerance=0.0)
    strict = LlmRubric(rubric="polite?", judge=judge, threshold=0.9, tolerance=0.0)
    probe = EvaluatorInputs(output="hello")

    def as_run(a: LlmRubric) -> Run:
        return Run(
            tenant="acme",
            environment="test",
            suite="s",
            config_hash=config_hash([a]),
            created_at=CREATED,
            results=(CaseResult("c", (a(probe),)),),
        )

    result = compare(as_run(strict), as_run(lenient))

    assert result.counts == {"regressed": 1}  # not {"new": 1, "missing": 1}
    assert result.config_changed is True
    assert "threshold moved" in result.deltas[0].reason
    # The model did not get worse; the bar moved. The score is identical.
    assert result.deltas[0].delta == pytest.approx(0.0)


def test_identity_survives_a_threshold_change_but_config_hash_does_not() -> None:
    """The split the correction rests on: comparable, but not promotable."""

    def judge(prompt: str) -> JudgeReply:
        return JudgeReply(score=0.8, reason="fixed")

    lenient = LlmRubric(rubric="polite?", judge=judge, threshold=0.7, tolerance=0.0)
    strict = LlmRubric(rubric="polite?", judge=judge, threshold=0.9, tolerance=0.0)

    assert lenient.identity == strict.identity
    assert config_hash([lenient]) != config_hash([strict])


def test_a_flip_at_a_stable_threshold_does_not_mention_it() -> None:
    current = run_of(verdict("rubric", 0.69, threshold=0.70))
    baseline = run_of(verdict("rubric", 0.71, threshold=0.70))
    assert "threshold moved" not in compare(current, baseline).deltas[0].reason


# --------------------------------------------------------------------------- #
# Shape of the comparison
# --------------------------------------------------------------------------- #


def test_a_repeated_assertion_does_not_overwrite_itself() -> None:
    current = run_of(verdict("contains", 1.0), verdict("contains", 0.0))
    baseline = run_of(verdict("contains", 1.0), verdict("contains", 1.0))
    result = compare(current, baseline)
    assert len(result.deltas) == 2
    assert result.counts == {"unchanged": 1, "regressed": 1}


# --------------------------------------------------------------------------- #
# Pairing by identity, not by position
# --------------------------------------------------------------------------- #


def rome(score: float) -> Verdict:
    return verdict("contains", score, assertion_id="id-rome")


def milan(score: float) -> Verdict:
    return verdict("contains", score, assertion_id="id-milan")


def naples(score: float) -> Verdict:
    return verdict("contains", score, assertion_id="id-naples")


def test_reordering_two_assertions_changes_nothing() -> None:
    """Positional pairing would turn a reordering into a fabricated `regressed`
    plus a fabricated `improved`, both invented and both silent."""
    baseline = run_of(rome(1.0), milan(0.0))
    current = run_of(milan(0.0), rome(1.0))
    result = compare(current, baseline)
    assert result.counts == {"unchanged": 2}
    assert not result.has_regressions


def test_removing_the_first_of_three_reports_exactly_that_one_missing() -> None:
    """Positional pairing would report the third as `missing` while comparing
    the second against the first's baseline."""
    baseline = run_of(rome(1.0), milan(0.5), naples(0.0))
    current = run_of(milan(0.5), naples(0.0))
    result = compare(current, baseline)
    assert result.counts == {"missing": 1, "unchanged": 2}
    gone = result.of("missing")[0]
    assert gone.baseline is not None
    assert gone.baseline.assertion_id == "id-rome"


def test_identical_assertions_still_pair_by_position() -> None:
    """Two verdicts sharing an identity are the same assertion applied twice:
    there is nothing but order left to pair on, and order is correct because
    the two are interchangeable."""
    baseline = run_of(rome(1.0), rome(1.0))
    current = run_of(rome(1.0), rome(0.0))
    result = compare(current, baseline)
    assert result.counts == {"unchanged": 1, "regressed": 1}


def test_a_renamed_assertion_is_not_silently_matched() -> None:
    baseline = run_of(rome(1.0))
    current = run_of(milan(1.0))
    assert compare(current, baseline).counts == {"new": 1, "missing": 1}


def test_it_reports_a_changed_configuration() -> None:
    current = run_of(verdict("rubric", 0.9), cfg="hash-b")
    baseline = run_of(verdict("rubric", 0.9), cfg="hash-a")
    assert compare(current, baseline).config_changed is True


def test_deltas_are_ordered_stably() -> None:
    current = Run(
        tenant="acme",
        environment="test",
        suite="s",
        config_hash="h",
        created_at=CREATED,
        results=(
            CaseResult("case-2", (verdict("b", 1.0),)),
            CaseResult("case-1", (verdict("a", 1.0),)),
        ),
    )
    result = compare(current, current)
    assert [(d.case_id, d.assertion) for d in result.deltas] == [
        ("case-1", "a"),
        ("case-2", "b"),
    ]


def test_a_run_compared_with_itself_has_no_regressions() -> None:
    r = run_of(verdict("contains", 1.0), verdict("rubric", 0.83, tolerance=0.02))
    result = compare(r, r)
    assert result.counts == {"unchanged": 2}
    assert not result.has_regressions
