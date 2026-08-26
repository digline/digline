"""Baseline anchors and deterministic serialization.

The baseline is a committed file: its purpose is to be read in a code review,
so its diff must only churn when a fact actually changes.
"""

from __future__ import annotations

import pytest

from digline.core import (
    CaseResult,
    Contains,
    CostBudget,
    EvaluatorInputs,
    JudgeReply,
    LlmRubric,
    Regex,
    Run,
    Score,
    Verdict,
    config_hash,
    run_from_json,
    run_to_json,
)
from digline.core.run import SCHEMA_VERSION

CREATED = "2026-01-01T00:00:00+00:00"


def sample_run() -> Run:
    return Run(
        tenant="acme",
        environment="test",
        suite="test-suite",
        config_hash="abc123",
        created_at=CREATED,
        git_commit="0f1e2d3",
        results=(
            CaseResult(
                "case-1",
                (
                    Verdict(
                        score=Score(name="contains", score=1.0),
                        threshold=1.0,
                        tolerance=0.0,
                        status="pass",
                        reason="'Rome' found in the output",
                        assertion_id="contains-rome",
                    ),
                    Verdict(
                        score=Score(name="cost_budget", score=None),
                        threshold=0.5,
                        tolerance=0.0,
                        status="error",
                        reason="cost_usd is missing",
                        assertion_id="cost-cap",
                    ),
                ),
            ),
        ),
        metadata={"model": "claude-opus-5", "zeta": 1, "alpha": 2},
    )


# --------------------------------------------------------------------------- #
# config_hash
# --------------------------------------------------------------------------- #


def test_config_hash_is_order_independent() -> None:
    a = Contains(needle="Rome")
    b = Regex(pattern=r"\d+")
    assert config_hash([a, b]) == config_hash([b, a])


def test_config_hash_changes_when_a_threshold_changes() -> None:
    before = config_hash([CostBudget(max_usd=0.10, tolerance=0.02)])
    after = config_hash([CostBudget(max_usd=0.10, tolerance=0.02, threshold=0.9)])
    assert before != after


def test_config_hash_changes_when_a_tolerance_changes() -> None:
    before = config_hash([Contains(needle="Rome")])
    after = config_hash([Contains(needle="Rome", tolerance=0.05)])
    assert before != after


def test_config_hash_changes_when_an_assertion_parameter_changes() -> None:
    """A suite that searches for a different string is a different suite: a
    baseline recorded under the old needle cannot be compared against it."""
    assert config_hash([Contains(needle="Rome")]) != config_hash(
        [Contains(needle="Milan")]
    )


def test_config_hash_changes_when_an_assertion_is_added() -> None:
    one = config_hash([Contains(needle="Rome")])
    two = config_hash([Contains(needle="Rome"), Regex(pattern=r"\d+")])
    assert one != two


def test_identity_distinguishes_assertions_of_the_same_kind() -> None:
    """The property `compare()` relies on: two `contains` are different
    assertions, not two occurrences of one."""
    assert Contains(needle="Rome").identity != Contains(needle="Milan").identity


def test_identity_is_stable_across_instances_and_field_order() -> None:
    assert Contains(needle="Rome").identity == Contains(needle="Rome").identity
    # `accepts` is a frozenset; set iteration order is not stable across
    # processes, so this would be flaky if `canonical` did not sort it.
    assert (
        Contains(needle="Rome", case_sensitive=True).identity
        == Contains(case_sensitive=True, needle="Rome").identity
    )


def test_identity_ignores_which_judge_is_wired_in() -> None:
    """A judge is a property of the run environment, not of the declared suite —
    and a function's repr carries a memory address, so including it would make
    the identity change on every process."""

    def judge_a(prompt: str) -> JudgeReply:
        return JudgeReply(score=1.0, reason="a")

    def judge_b(prompt: str) -> JudgeReply:
        return JudgeReply(score=0.0, reason="b")

    common = {"rubric": "polite?", "threshold": 0.7, "tolerance": 0.05}
    assert (
        LlmRubric(judge=judge_a, **common).identity  # type: ignore[arg-type]
        == LlmRubric(judge=judge_b, **common).identity  # type: ignore[arg-type]
    )


# --------------------------------------------------------------------------- #
# Serialization
# --------------------------------------------------------------------------- #


def test_serialization_is_deterministic() -> None:
    assert run_to_json(sample_run()) == run_to_json(sample_run())


def test_metadata_ordering_does_not_churn_the_diff() -> None:
    one = Run(
        tenant="acme",
        environment="test",
        suite="s",
        config_hash="h",
        created_at=CREATED,
        metadata={"b": 1, "a": 2},
    )
    two = Run(
        tenant="acme",
        environment="test",
        suite="s",
        config_hash="h",
        created_at=CREATED,
        metadata={"a": 2, "b": 1},
    )
    assert run_to_json(one) == run_to_json(two)


def test_floats_have_fixed_precision() -> None:
    r = Run(
        tenant="acme",
        environment="test",
        suite="s",
        config_hash="h",
        created_at=CREATED,
        results=(
            CaseResult(
                "c",
                (
                    Verdict(
                        score=Score(name="x", score=1 / 3),
                        threshold=0.5,
                        tolerance=0.0,
                        status="fail",  # 1/3 < 0.5; the two must agree
                        reason="r",
                    ),
                ),
            ),
        ),
    )
    assert "0.333333" in run_to_json(r)
    assert "0.3333333333" not in run_to_json(r)


def test_round_trip_preserves_everything_that_matters() -> None:
    original = sample_run()
    restored = run_from_json(run_to_json(original))
    assert restored.suite == original.suite
    assert restored.config_hash == original.config_hash
    assert restored.git_commit == original.git_commit
    assert run_to_json(restored) == run_to_json(original)


def test_round_trip_preserves_the_error_state() -> None:
    restored = run_from_json(run_to_json(sample_run()))
    errored = restored.results[0].verdicts[1]
    assert errored.status == "error"
    assert errored.score.score is None
    assert errored.passed is False


def test_an_unknown_schema_version_is_rejected() -> None:
    # Read from the constant rather than spelled out, so a version bump does not
    # silently turn this into a test that checks nothing.
    payload = run_to_json(sample_run()).replace(
        f'"schema_version": {SCHEMA_VERSION}', '"schema_version": 99'
    )
    assert '"schema_version": 99' in payload
    with pytest.raises(ValueError, match="schema_version"):
        run_from_json(payload)


def test_the_assertion_id_survives_the_round_trip() -> None:
    """`compare()` pairs on it, so a baseline that lost it would pair wrongly."""
    original = sample_run()
    restored = run_from_json(run_to_json(original))
    assert restored.results[0].verdicts[0].assertion_id == "contains-rome"


def test_a_verdict_is_stored_at_the_precision_it_is_written_at() -> None:
    """0.10 / 0.11 is a repeating decimal: without rounding at construction the
    in-memory value and the persisted one differ in the eighth digit."""
    v = CostBudget(max_usd=0.10, tolerance=0.02)(
        EvaluatorInputs(output="x", cost_usd=0.01)
    )
    assert v.score.score == 0.909091


def test_a_run_compared_with_its_own_round_trip_shows_no_drift() -> None:
    """The phantom-regression case. The baseline passes through 6-decimal
    rounding on its way to disk while the live run does not, so an unrounded
    score used to produce a delta of ~1e-8 — above the default tolerance of 0,
    hence a regression reported on every single run against a stored baseline.
    In-memory tests miss it because both sides are unrounded."""
    verdicts = tuple(
        a(EvaluatorInputs(output="Rome", cost_usd=0.01, latency_ms=333))
        for a in (Contains(needle="Rome"), CostBudget(max_usd=0.10, tolerance=0.02))
    )
    live = Run(
        tenant="acme",
        environment="test",
        suite="s",
        config_hash="h",
        created_at=CREATED,
        results=(CaseResult("c", verdicts),),
    )
    from digline.core import compare

    stored = run_from_json(run_to_json(live))
    result = compare(live, stored)
    assert result.counts == {"unchanged": 2}
    assert not result.has_regressions


def test_the_assertion_id_defaults_to_the_name() -> None:
    """Correct whenever a case carries one assertion per name, which keeps
    hand-built verdicts readable in tests."""
    v = Verdict(
        score=Score(name="contains", score=1.0),
        threshold=1.0,
        status="pass",
        reason="r",
    )
    assert v.assertion_id == "contains"


# --------------------------------------------------------------------------- #
# Type invariants
# --------------------------------------------------------------------------- #


def test_an_errored_verdict_cannot_carry_a_score() -> None:
    with pytest.raises(ValueError, match="must not carry a score"):
        Verdict(
            score=Score(name="x", score=0.9),
            threshold=0.5,
            status="error",
            reason="r",
        )


def test_a_missing_score_cannot_be_a_pass() -> None:
    with pytest.raises(ValueError, match="must produce status='error'"):
        Verdict(
            score=Score(name="x", score=None),
            threshold=0.5,
            status="pass",
            reason="r",
        )


def test_a_verdict_without_a_reason_is_rejected() -> None:
    with pytest.raises(ValueError, match="reason is mandatory"):
        Verdict(
            score=Score(name="x", score=1.0), threshold=0.5, status="pass", reason=""
        )


def test_an_out_of_range_score_is_rejected() -> None:
    with pytest.raises(ValueError, match=r"\[0, 1\]"):
        Score(name="x", score=1.5)
