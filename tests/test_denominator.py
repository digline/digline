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
from digline.report import (
    SECTIONS,
    explain_text,
    facts,
    headline,
    render_html,
    summary_lines,
)
from digline.wire import EXIT_WORSE, compare_json, exit_code, explain_json

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


# --------------------------------------------------------------------------- #
# The delta-pass over 0.15.1: the half of the rule that was stated and not held
# --------------------------------------------------------------------------- #
#
# Everything above this line passed on 0.15.1, and the defect below shipped with
# it. `AssertionDelta.denominator_moved` said the fact "never makes `worse` true
# ... and moves no exit code", while `compare()` kept `outcome` pointing wherever
# the arithmetic pointed and `counts` counted it: with the score *down*, the row
# read `regressed`, `worse` went true and the run exited 1 — the conversion the
# paragraph promised never happened. The tests above only ever measured 1.0
# against 1.0, where the arithmetic points up, so the promise was never tested in
# the direction that broke it.


def both_pass(score: float, considered: int) -> Verdict:
    """An aggregate whose gate is met on either side, so a movement is judged as
    a distance rather than as a flip. The threshold is the point: at 1.0 a score
    of 0.75 is a *flip*, which is a different rule (see the last test here)."""
    return aggregate(score, considered, threshold=0.5)


LENIENT_REFERENCE = run_with(both_pass(1.0, 4))


def test_a_moved_denominator_pointing_down_is_not_a_regression() -> None:
    """The defect. Same incomparability as the one above, the other way up: 3
    counted here against 4 there, and the score fell. It is not a movement, so
    it is not a movement that got worse, and nothing may exit 1 on it."""
    run = run_with(both_pass(0.75, 3))
    comparison = compare(run, LENIENT_REFERENCE)
    (delta,) = comparison.deltas
    assert delta.denominator_moved is True
    # The direction the arithmetic pointed is kept on the row — a reader who
    # wants it is owed it — and it is the counting that is withdrawn.
    assert delta.outcome == "regressed"
    assert comparison.counts.get("regressed", 0) == 0
    assert comparison.regressed == ()

    head = headline(comparison, run, LENIENT_REFERENCE, locale="en")
    assert head.worse is False
    assert exit_code(head) != EXIT_WORSE


def test_a_moved_denominator_pointing_up_is_not_an_improvement() -> None:
    """The same rule on the side that was visible, stated as a count: before
    this, a gate that never moved was counted under `improved` and filed in the
    report under "What got better"."""
    comparison = compare(run_with(both_pass(1.0, 3)), LENIENT_REFERENCE)
    (delta,) = comparison.deltas
    assert delta.denominator_moved is True
    assert comparison.counts.get("improved", 0) == 0
    assert comparison.incomparable == (delta,)


def test_an_honest_drop_still_exits_one() -> None:
    """The control the test above needs: the exclusion is keyed on the moved
    denominator and on nothing else, so a real drop over the same case set is
    still a regression, still `worse`, still exit 1."""
    run = run_with(both_pass(0.75, 4))
    comparison = compare(run, LENIENT_REFERENCE)
    (delta,) = comparison.deltas
    assert delta.denominator_moved is False
    assert comparison.counts["regressed"] == 1

    head = headline(comparison, run, LENIENT_REFERENCE, locale="en")
    assert head.worse is True
    assert exit_code(head) == EXIT_WORSE


def test_a_flip_is_not_an_incomparability_and_still_exits_one() -> None:
    """The decision this pass made explicit rather than changed.

    A gate that read `pass 1.0` and now reads `fail 0.666667` is failing against
    **its own threshold**, which needs no reference to be true: the flip reaches
    `compare()`'s rule 3 before a denominator is compared at all. So the run is
    red and exits 1, with the denominator unmentioned — what a moved denominator
    withdraws is the meaning of a *distance*, and a flip is not one.
    """
    run = run_with(aggregate(0.666667, 3, threshold=1.0))
    comparison = compare(run, REFERENCE)
    (delta,) = comparison.deltas
    assert delta.outcome == "regressed"
    assert delta.denominator_moved is False

    head = headline(comparison, run, REFERENCE, locale="en")
    assert head.worse is True
    assert exit_code(head) == EXIT_WORSE


# --------------------------------------------------------------------------- #
# The surfaces: what a person reads, which is where the defect was reported
# --------------------------------------------------------------------------- #


def test_the_terminal_headline_says_it_was_not_a_comparison() -> None:
    """`compare` printed `head.sentence` and nothing else about it: the sentence
    read "Nothing got worse compared with the reference." over a gate that had
    not been compared at all. The clause sits with that sentence, not in a
    document one command away."""
    run = run_with(both_pass(1.0, 3))
    head = headline(
        compare(run, LENIENT_REFERENCE), run, LENIENT_REFERENCE, locale="en"
    )
    assert head.denominator_moved == 1
    assert "1 run-level check was measured over a different number of cases" in (
        head.sentence
    )
    # Beside the clause it qualifies, and not instead of it: the other checks
    # really were compared, and that sentence is still true of them.
    assert "Nothing got worse" in head.sentence


def test_the_terminal_names_the_check_it_could_not_compare() -> None:
    """The second half of the terminal fix. `summary_lines` selected regressions
    and unjudged checks, so with the arithmetic pointing up this row appeared
    nowhere at all, and with it pointing down it appeared as a drop."""
    for score in (1.0, 0.75):
        run = run_with(both_pass(score, 3))
        comparison = compare(run, LENIENT_REFERENCE)
        (line,) = summary_lines(comparison, run, LENIENT_REFERENCE, locale="en")
        assert "recall" in line
        assert "easured over 3 cases here and 4 in the reference" in line
        # No verb of movement, in either direction: that is the whole finding.
        for claim in ("rose", "fell", "got better", "got worse", "unchanged"):
            assert claim not in line


def test_the_document_files_it_under_neither_worse_nor_better() -> None:
    """The report is what the end company reads. A gate that never moved was
    filed under "What got better" and counted in the `improved` tally, which is
    a finding stated to a customer that nobody established."""
    run = run_with(both_pass(1.0, 3))
    document = render_html(
        compare(run, LENIENT_REFERENCE), run, LENIENT_REFERENCE, locale="en"
    )
    assert "What was not compared" in document
    assert "not a movement of one another" in document
    # The tally line at the top of the document: the count it is missing from.
    assert "improved <b>0</b>" in document
    # And the section that used to hold it is empty.
    better = document.split("What got better")[1]
    assert better.startswith(' (0)</summary><p class="empty"')


def test_a_report_with_no_moved_denominator_gains_no_section() -> None:
    """Why this is a block and not a seventh `SECTIONS` entry.

    Every section in that list renders whether or not it has rows, so a seventh
    would have added an empty `(0)` to every report ever rendered — including the
    ten committed under `examples/`, which are documents of record. This is the
    shape `calibration_section` chose for the same problem: nothing at all when
    there is nothing.
    """
    run = run_with(both_pass(0.75, 4))
    document = render_html(
        compare(run, LENIENT_REFERENCE), run, LENIENT_REFERENCE, locale="en"
    )
    assert "What was not compared" not in document
    # The shape of the document is the six sections it always had.
    assert document.count("<details") == len(SECTIONS)


def test_explain_stops_contradicting_its_own_tally() -> None:
    """The most visible contradiction: the tally said the two were not the same
    measurement and the line under it said "recall got better: 1.000000 to
    1.000000, a rise of 0.000000"."""
    run = run_with(both_pass(1.0, 3))
    said = "\n".join(
        explain_text(facts(run, compare(run, LENIENT_REFERENCE)), locale="en")
    )
    assert "measured over 3 cases here and 4 in the reference" in said
    assert "got better" not in said
    assert "a rise of" not in said


def test_the_explain_row_carries_the_flag_to_a_program() -> None:
    """Beside the kind rather than inside it: `kind` keeps the values a consumer
    already matches on, and a program can still tell this row apart."""
    run = run_with(both_pass(1.0, 3))
    reading = facts(run, compare(run, LENIENT_REFERENCE))
    payload = explain_json(reading, scope="comparison", exit_code=0)
    rows = [
        f
        for f in cast("list[dict[str, object]]", payload["facts"])
        if f.get("about") == "check"
    ]
    (row,) = rows
    assert row["denominator_moved"] is True
    assert row["kind"] in ("improved", "regressed")
