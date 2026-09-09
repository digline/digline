"""The limits of ADR 0009, each pinned at its edge.

**Every limit in digline is compared at `FLOAT_PRECISION`, and every limit is
inclusive.** That is the whole rule (ADR 0009 §1), and this file is where it is
checkable: the record lists seventeen sites, and every one of them that has an
edge is held here with three values — the limit itself, one `STORAGE_STEP`
inside it, one outside.

Two halves, and each fails differently. A `>=` becoming a `>` reddens 112 of the
280 verdicts in the committed baselines, which sit exactly on their threshold. A
comparison that stops rounding fails almost nothing — one value in that whole
corpus — which is exactly how four call sites acquired the rounding and three
did not, and why the rule now has one home instead of seven spellings.

Two edges are pinned elsewhere and are not repeated here:
`test_types.py::test_the_boundary_counts_as_a_pass` holds the `Verdict`
invariant, and `test_assertions.py` holds the budgets at their cap.
"""

from __future__ import annotations

from digline.core import (
    CaseOutcome,
    CaseResult,
    CostBudget,
    EvaluatorInputs,
    JudgeReply,
    LatencyBudget,
    LlmRubric,
    Precision,
    Run,
    Score,
    Verdict,
    compare,
    diff,
)
from digline.core.types import STORAGE_STEP, at_precision

CREATED = "2026-01-01T00:00:00+00:00"

#: One unit at storage precision, from the core rather than restated here:
#: ADR 0009 §3 gave the rule one home, and a test that kept its own copy could
#: drift from the thing it is testing.
STEP = STORAGE_STEP


# --------------------------------------------------------------------------- #
# 1. The threshold: `score >= threshold`
# --------------------------------------------------------------------------- #


def graded_at(value: float, *, threshold: float) -> Verdict:
    """One per-case assertion whose score is dictated, through the real
    `AssertionBase._graded` path rather than a hand-built `Verdict`: the edge is
    decided there, and `Verdict` only checks that the two agree."""

    def judge(prompt: str) -> JudgeReply:
        return JudgeReply(score=value, reason="fixed")

    assertion = LlmRubric(
        rubric="polite?", judge=judge, threshold=threshold, tolerance=0.0
    )
    return assertion(EvaluatorInputs(output="hello"))


def test_the_case_threshold_is_inclusive_at_the_edge() -> None:
    assert graded_at(0.7, threshold=0.7).status == "pass"
    assert graded_at(0.7 - STEP, threshold=0.7).status == "fail"
    assert graded_at(0.7 + STEP, threshold=0.7).status == "pass"


def precision_at(threshold: float) -> Verdict:
    """`3 / (3 + 2)` — three marked cases kept, two unmarked ones kept — so the
    score is exactly `0.6` and the threshold is what moves around it."""
    kept = Verdict(
        score=Score(name="agrees", score=1.0),
        threshold=1.0,
        status="pass",
        reason="judged",
        assertion_id="id-agrees",
    )
    dropped = Verdict(
        score=Score(name="agrees", score=0.0),
        threshold=1.0,
        status="fail",
        reason="judged",
        assertion_id="id-agrees",
    )
    outcomes = [CaseOutcome(f"tp-{i}", "positive", kept) for i in range(3)] + [
        CaseOutcome(f"fp-{i}", "negative", dropped) for i in range(2)
    ]
    return Precision(over="agrees", threshold=threshold, tolerance=0.0)(outcomes)


def test_the_aggregate_threshold_is_inclusive_at_the_edge() -> None:
    """The same rule one level up, in `RunAssertionBase._graded`. Written with
    the threshold moving and the score standing still, because `3/5` is the
    number the matrix produces and there is no way to nudge it by one step."""
    assert precision_at(0.6).score.score == 0.6
    assert precision_at(0.6).status == "pass"
    assert precision_at(0.6 - STEP).status == "pass"
    assert precision_at(0.6 + STEP).status == "fail"


# --------------------------------------------------------------------------- #
# 2. The declared tolerance: `abs(delta) <= tolerance`
# --------------------------------------------------------------------------- #


def verdict(name: str, score: float, *, threshold: float, tolerance: float) -> Verdict:
    return Verdict(
        score=Score(name=name, score=score),
        threshold=threshold,
        status="pass" if score >= threshold else "fail",
        reason="test reason",
        tolerance=tolerance,
        assertion_id=f"id-{name}",
    )


def run_of(*verdicts: Verdict) -> Run:
    return Run(
        tenant="acme",
        environment="test",
        suite="test-suite",
        config_hash="hash-a",
        created_at=CREATED,
        results=(CaseResult(case_id="case-1", verdicts=verdicts),),
    )


def outcome_of(now: Verdict, before: Verdict) -> str:
    comparison = compare(run_of(now), run_of(before))
    assert len(comparison.deltas) == 1, comparison.deltas
    return comparison.deltas[0].outcome


def moved_to(score: float, *, tolerance: float) -> str:
    """`0.5` down to `score`, against a baseline with no samples — so the noise
    floor cannot reach the answer and the tolerance is the only rule left. The
    two halves are exact in binary, which is what makes the edge itself
    reachable at all; see the test below for what happens when they are not."""
    return outcome_of(
        verdict("rubric", score, threshold=0.125, tolerance=tolerance),
        verdict("rubric", 0.5, threshold=0.125, tolerance=tolerance),
    )


def test_the_tolerance_is_inclusive_at_the_edge() -> None:
    assert moved_to(0.25, tolerance=0.25) == "unchanged"
    assert moved_to(0.25 + STEP, tolerance=0.25) == "unchanged"
    assert moved_to(0.25 - STEP, tolerance=0.25) == "regressed"


def test_the_tolerance_edge_is_the_printed_numbers_and_not_the_subtraction() -> None:
    """The test ADR 0009 was written to invert.

    Both movements are one case in twenty-one against a tolerance of one case in
    twenty-one, and all four numbers print — and are stored — at six decimals.
    Before ADR 0009 they landed on **opposite sides** of the edge, because
    `delta` was the difference of two rounded scores and the difference was not
    itself rounded:

        0.761905 - 0.714286 = 0.04761900000000008   >  0.047619   -> regressed
        0.714286 - 0.666667 = 0.04761899999999997  <=  0.047619   -> unchanged

    One was a finding and the other was not, and no reader of the document could
    tell why. `0.761905 -> 0.714286` is the movement ADR 0006's fixtures were
    written about: it reached the noise floor only because it missed this edge
    by 7.6e-17.

    Now the delta is rounded where it is computed (§4), so both read the same
    way — and the number the rule tests is the number the wire carries.
    """
    one_case = at_precision(1 / 21)
    assert one_case == 0.047619

    def moved(now: float, before: float) -> str:
        return outcome_of(
            verdict("accuracy", now, threshold=0.65, tolerance=one_case),
            verdict("accuracy", before, threshold=0.65, tolerance=one_case),
        )

    assert moved(0.714286, 0.761905) == "unchanged"
    assert moved(0.714286, 0.666667) == "unchanged"


def test_the_same_pair_reads_the_same_way_through_diff() -> None:
    """The defect existed in two files, so the test covers both.

    `diff()` was written in 0.6.0 with the same unrounded subtraction, in a new
    file, while the record describing it sat parked — which is the argument of
    ADR 0009's context section. A test that pinned only `compare()` would let it
    come back here.
    """
    one_case = at_precision(1 / 21)

    def differed(left: float, right: float) -> tuple[str, str]:
        comparison = diff(
            run_of(verdict("accuracy", left, threshold=0.65, tolerance=one_case)),
            run_of(verdict("accuracy", right, threshold=0.65, tolerance=one_case)),
        )
        assert len(comparison.checks) == 1, comparison.checks
        check = comparison.checks[0]
        return check.outcome, check.favours

    assert differed(0.761905, 0.714286) == ("same", "neither")
    assert differed(0.666667, 0.714286) == ("same", "neither")


def test_the_delta_the_rule_tests_is_the_delta_the_wire_carries() -> None:
    """§4: rounded where it is computed, not where it is tested.

    `AssertionDelta.delta` is a public field. A delta that compared as
    `0.047619` and serialized as `0.04761900000000008` would have moved the
    inconsistency out of the verdict and into the JSON, where a second reader
    would have found it again.
    """
    comparison = compare(
        run_of(verdict("accuracy", 0.714286, threshold=0.65, tolerance=0.0)),
        run_of(verdict("accuracy", 0.761905, threshold=0.65, tolerance=0.0)),
    )
    assert comparison.deltas[0].delta == -0.047619


# --------------------------------------------------------------------------- #
# 3. The measured noise floor: `sample_min <= score <= sample_max`
# --------------------------------------------------------------------------- #


def sampled(score: float, *samples: float) -> Verdict:
    """A baseline that wobbled, with the interval its samples span. `tolerance`
    is zero throughout this section so the declared rule cannot answer first —
    `compare()` checks it before the measured floor."""
    return Verdict(
        score=Score(
            name="rubric",
            score=score,
            samples=samples,
            sample_min=min(samples),
            sample_max=max(samples),
        ),
        threshold=0.5,
        status="pass",
        reason="folded",
        tolerance=0.0,
        assertion_id="id-rubric",
    )


def against(score: float, baseline: Verdict) -> tuple[str, bool]:
    comparison = compare(
        run_of(verdict("rubric", score, threshold=0.5, tolerance=0.0)),
        run_of(baseline),
    )
    delta = comparison.deltas[0]
    return delta.outcome, delta.within_noise


def test_the_noise_floor_is_inclusive_at_the_low_end() -> None:
    baseline = sampled(0.8, 0.6, 0.8, 1.0, 0.8, 0.8)
    assert against(0.6, baseline) == ("unchanged", True)
    assert against(0.6 + STEP, baseline) == ("unchanged", True)
    assert against(0.6 - STEP, baseline) == ("regressed", False)


def test_the_noise_floor_is_inclusive_at_the_high_end() -> None:
    """The other end of the same expression, and worth its own test: `covers()`
    is one comparison for both directions, so a change to the upper `<=` alone
    would leave the test above green while turning a rise the baseline had
    already shown into an `improved`."""
    baseline = sampled(0.78, 0.6, 0.8, 0.9, 0.8, 0.8)
    assert against(0.9, baseline) == ("unchanged", True)
    assert against(0.9 - STEP, baseline) == ("unchanged", True)
    assert against(0.9 + STEP, baseline) == ("improved", False)


# --------------------------------------------------------------------------- #
# 4. The rule's floor: a run compared with itself
# --------------------------------------------------------------------------- #


def test_a_run_compared_with_itself_is_unchanged_at_zero_tolerance() -> None:
    """The reason the tolerance edge is inclusive and stays that way.

    The default tolerance is `0.0` and the ordinary delta is `0.0`, so an
    exclusive `<` here would report **every assertion of every run** as a
    regression when compared against itself. ADR 0009 records that alternative
    as rejected on sight; this is the test that would catch anyone re-proposing
    it.
    """
    run = run_of(
        verdict("rubric", 0.5, threshold=0.5, tolerance=0.0),
        verdict("accuracy", 0.714286, threshold=0.65, tolerance=0.0),
    )
    comparison = compare(run, run)
    assert [d.outcome for d in comparison.deltas] == ["unchanged", "unchanged"]
    assert comparison.regressed == ()


# --------------------------------------------------------------------------- #
# 5. The budget cap: `measured <= cap`, and one comparison deciding it
# --------------------------------------------------------------------------- #


def spent(amount: float, *, cap: float = 1.0) -> Verdict:
    return CostBudget(max_usd=cap, tolerance=0.0)(
        EvaluatorInputs(output="hello", cost_usd=amount)
    )


def test_a_budget_exactly_at_its_cap_is_within_budget() -> None:
    """`budget_score` is built so the cap scores exactly `0.5` against a
    threshold of `0.5`, which is how "within budget" is encoded once rather than
    twice. The edge is inclusive like every other."""
    at_cap = spent(1.0)
    assert at_cap.score.score == 0.5
    assert at_cap.status == "pass"
    assert "within budget" in at_cap.reason


def test_a_budget_over_its_cap_fails_and_says_the_same_thing_twice() -> None:
    """The defect ADR 0009 §6 records, and the fixed decision it was breaking.

    `CostBudget` used to compute the word in its reason from `measured <= cap`
    on the raw values and its status from the rounded score. Near the cap those
    disagree: `budget_score` is exactly `0.5` at the cap and rounds to `0.5` for
    any overrun below about 2e-6 relative, so this run **passed** while its own
    reason read "over budget". Fixed decision 4 says a declared ceiling fails
    the run; it did not, and the document contradicted the gate.
    """
    over = spent(1.000002)
    assert over.status == "fail"
    assert "over budget" in over.reason
    # The two halves are now one comparison, so no input can separate them.
    for amount in (1.0, 1.000001, 1.000002, 1.5, 0.5, 0.999999):
        verdict = spent(amount)
        said_within = "within budget" in verdict.reason
        assert said_within == (verdict.status == "pass"), (amount, verdict.reason)


def test_the_budget_score_yields_to_the_fact_at_storage_precision() -> None:
    """Where the compressed proxy cannot express the difference, it is moved one
    `STORAGE_STEP` to the side the cap puts it on — rather than the status being
    moved to the side the proxy rounded to."""
    assert spent(1.0).score.score == 0.5
    assert spent(1.0 + STEP).score.score == 0.5 - STEP
    # And a cost that rounds to the cap at six decimals *is* at the cap: that is
    # the rule, not an exception to it.
    assert spent(1.0 + STEP / 10).status == "pass"


def test_a_latency_budget_holds_the_same_edge() -> None:
    """The same scale and the same rule, on the other budget. Written out rather
    than parametrized: a copy of the cost path that silently stopped being a
    copy is exactly how `diff` acquired its own unrounded subtraction."""
    at_cap = LatencyBudget(max_ms=30_000.0, tolerance=0.0)(
        EvaluatorInputs(output="hello", latency_ms=30_000.0)
    )
    assert (at_cap.score.score, at_cap.status) == (0.5, "pass")
    assert "within budget" in at_cap.reason

    over = LatencyBudget(max_ms=30_000.0, tolerance=0.0)(
        EvaluatorInputs(output="hello", latency_ms=30_000.05)
    )
    assert over.status == "fail"
    assert "over budget" in over.reason
