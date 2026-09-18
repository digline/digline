"""An errored check must not silently shrink a run-level denominator.

The defect, as the 0.15.0 delta-pass measured it: a run-level `Recall` gated at
1.0 read `fail 0.75` (3 of 4 cases) when the provider named its tool call, and
`pass 1.0` (3 of 3) when it did not — because the errored case left the matrix.
`compare` then reported that gate as **`unchanged 1.0 -> 1.0`** and the headline
said *"Nothing got worse."* over a real regression, triggerable by whoever
operates the endpoint, with no repo access.

The rule is `Matrix.considered`, not "a case errored": five things remove a case
from a denominator and the error is one of them. And a moved denominator is an
**incomparability, not a regression** — it never makes `worse` true and moves no
exit code. (ADR 0012 §3, amended 2026-09-18)
"""

from __future__ import annotations

from typing import cast

from digline.core import CaseResult, Run, Score, Verdict, compare
from digline.report import headline
from digline.wire import EXIT_WORSE, compare_json, exit_code

CREATED = "2026-01-01T00:00:00+00:00"


def aggregate(score: float, considered: int, *, threshold: float = 1.0) -> Verdict:
    """A run-level aggregate carrying the matrix metadata `Recall` records."""
    return Verdict(
        score=Score(
            name="recall",
            score=score,
            metadata={
                "considered": considered,
                "errored_excluded": 4 - considered,
                "true_positive": considered,
            },
        ),
        threshold=threshold,
        tolerance=0.0,
        status="pass" if score >= threshold else "fail",
        reason="measured over the cases that could be judged",
        assertion_id="recall#tools",
    )


def run_with(*aggregates: Verdict) -> Run:
    return Run(
        tenant="acme",
        environment="test",
        suite="agent-suite",
        config_hash="hash-a",
        created_at=CREATED,
        results=(CaseResult(case_id="c1", verdicts=()),),
        aggregate=aggregates,
    )


REFERENCE = run_with(aggregate(1.0, 4))


def test_the_honest_regression_is_still_a_regression() -> None:
    """The control: when the denominator holds, nothing about this is new."""
    (delta,) = compare(run_with(aggregate(0.75, 4)), REFERENCE).deltas
    assert delta.outcome == "regressed"
    assert delta.denominator_moved is False


def test_a_shrunken_denominator_is_never_reported_as_unchanged() -> None:
    """The defect itself. The score is identical to the reference's and the old
    reading called it `unchanged`; what makes that false is the denominator."""
    (delta,) = compare(run_with(aggregate(1.0, 3)), REFERENCE).deltas
    assert delta.denominator_moved is True
    assert delta.outcome != "unchanged"
    # The reason says what happened, rather than quoting a tolerance that never
    # applied to a comparison this was not.
    assert "3 cases against 4" in delta.reason


def test_a_moved_denominator_is_an_incomparability_and_not_a_regression() -> None:
    """It never makes the run worse and never moves an exit code: two scores over
    different case sets are not a movement, in either direction."""
    run = run_with(aggregate(1.0, 3))
    comparison = compare(run, REFERENCE)
    head = headline(comparison, run, REFERENCE, locale="en")
    assert head.worse is False
    assert exit_code(head) != EXIT_WORSE


def test_the_predicate_is_the_denominator_and_not_the_error() -> None:
    """A suspended case shrinks the same denominator and must be caught by the
    same rule — this is why `errored_excluded` is not the predicate."""
    suspended = Verdict(
        score=Score(
            name="recall",
            score=1.0,
            metadata={"considered": 3, "suspended_excluded": 1},
        ),
        threshold=1.0,
        tolerance=0.0,
        status="pass",
        reason="one case was set aside",
        assertion_id="recall#tools",
    )
    (delta,) = compare(run_with(suspended), REFERENCE).deltas
    assert delta.denominator_moved is True


def test_an_absent_denominator_is_not_a_difference() -> None:
    """A reference written before aggregates recorded their matrix carries no
    `considered`, and an absence is not a change."""
    bare = Verdict(
        score=Score(name="recall", score=1.0),
        threshold=1.0,
        tolerance=0.0,
        status="pass",
        reason="no matrix recorded",
        assertion_id="recall#tools",
    )
    (delta,) = compare(run_with(aggregate(1.0, 3)), run_with(bare)).deltas
    assert delta.denominator_moved is False


def test_the_fact_crosses_the_wire() -> None:
    """A pipeline could not detect the old silence: the row simply read
    `"outcome": "unchanged"`. Now it reads a field."""
    run = run_with(aggregate(1.0, 3))
    comparison = compare(run, REFERENCE)
    head = headline(comparison, run, REFERENCE, locale="en")
    document = compare_json(comparison, head, full=True)
    deltas = document["deltas"]
    assert isinstance(deltas, list)
    rows = cast("list[dict[str, object]]", deltas)
    (row,) = rows
    assert row["denominator_moved"] is True
    assert row["outcome"] != "unchanged"


def test_a_suite_that_grew_is_not_an_incomparability() -> None:
    """The cry-wolf guard, and the reason the predicate has two halves.

    Adding a case grows every aggregate's denominator, and that is not a
    comparison gone bad — it is a suite that got bigger, which `compare` already
    reports as a new case. A first cut of this rule flagged it, which would have
    fired on the most ordinary edit anybody makes; `tests/test_groups.py` caught
    it. So the rule is *same cases seen, different number counted*: cases that
    dropped out of being judged, never cases that were never there.
    """
    # Four cases seen, four counted — against six seen, six counted.
    grown = Verdict(
        score=Score(
            name="recall",
            score=1.0,
            metadata={"considered": 6, "errored_excluded": 0},
        ),
        threshold=1.0,
        tolerance=0.0,
        status="pass",
        reason="two more cases were added to the suite",
        assertion_id="recall#tools",
    )
    (delta,) = compare(run_with(grown), REFERENCE).deltas
    assert delta.denominator_moved is False
    assert delta.outcome == "unchanged"
