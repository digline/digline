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

from digline.core import (
    CaseOutcome,
    CaseResult,
    Recall,
    Run,
    Score,
    Verdict,
    case_count,
    checked_denominator,
    compare,
    denominator,
)
from digline.report import (
    SECTIONS,
    explain_text,
    facts,
    headline,
    render_html,
    summary_lines,
)
from digline.wire import (
    EXIT_OK,
    EXIT_UNJUDGED,
    EXIT_WORSE,
    compare_json,
    exit_code,
    explain_json,
)

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
    document = compare_json(comparison, head, baseline=REFERENCE, full=True)
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


def test_a_flip_down_is_not_an_incomparability_and_still_exits_one() -> None:
    """The half of rule 3 that survived the pass after this one.

    A gate that read `pass 1.0` and now reads `fail 0.666667` is failing against
    **its own threshold** over the cases it counted. So the run is red and exits
    1, with the denominator unmentioned — not because a shrunken denominator
    cannot move this reading (below a threshold of 1.0 it can, and
    `test_a_flip_down_can_be_a_false_alarm_and_still_exits_one` pins that), but
    because withdrawing it would be the rule making a run *greener*, and red is
    the side this product chooses to be wrong on.

    *The pass that wrote this test read that argument as covering both
    directions and it does not* — `fail` to `pass` is the sentence the advisory
    is about, and it is the section below. What is asserted here is the
    downward flip, which is unchanged. (ADR 0012 §3, amended again 2026-09-18)
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


# --------------------------------------------------------------------------- #
# The delta-pass over 0.15.2: the flip the rule exempted
# --------------------------------------------------------------------------- #
#
# Everything above this line passed on 0.15.2, and the sentence the advisory is
# about was still being printed. `compare()`'s rule 3 classified every flip
# before a denominator was so much as computed, on the argument that a flip is
# not a distance. Downward that is right. Upward it is not: `fail` to `pass` is
# also the sentence *"the gate got better"*, which is a claim about the pair,
# and a pair that counted different numbers of cases is not one. The gate in
# GHSA-8c38-f965-cgww's own table — recall raised from `fail` over four cases to
# `pass` over three by an endpoint erroring the case it was failing — was
# counted under `improved` and filed in the report under "What got better".


#: The reference of the advisory's table: the gate is red, over four cases, and
#: somebody is working on it. A failing run is a promotable baseline — `promote`
#: refuses an *errored* run, never a failing one — so this is the ordinary shape
#: of a suite with a known regression, not a contrived one.
RED_REFERENCE = run_with(aggregate(0.75, 4))


def test_a_flip_up_over_a_moved_denominator_is_not_an_improvement() -> None:
    """The defect, in one row. `fail 0.75` over four cases against `pass 1.0`
    over three: the score rose because the case it was failing left the
    denominator, and `improved` says the system got better."""
    run = run_with(aggregate(1.0, 3))
    comparison = compare(run, RED_REFERENCE)
    (delta,) = comparison.deltas

    assert delta.denominator_moved is True
    # The direction the arithmetic pointed stays on the row, as it does for a
    # movement: what it may no longer do is count.
    assert delta.outcome == "improved"
    assert comparison.counts.get("improved", 0) == 0
    assert comparison.incomparable == (delta,)
    # The reason says both numbers, in the words the movement branch uses.
    assert "outcome flipped from 'fail' to 'pass'" in delta.reason
    assert "measured over 3 cases against 4 in the reference" in delta.reason


def test_the_flip_itself_is_untouched_and_the_run_is_not_made_redder() -> None:
    """What this rule may not do, in either direction.

    The gate really did pass in this run — `now.status` is its own measurement
    against its own threshold — and an incomparability withdraws the comparison,
    never the verdict. So nothing here goes red: `improved` never made a run
    `worse`, and removing it from the tally must not either.
    """
    run = run_with(aggregate(1.0, 3))
    comparison = compare(run, RED_REFERENCE)
    (delta,) = comparison.deltas
    assert delta.current is not None and delta.current.status == "pass"

    head = headline(comparison, run, RED_REFERENCE, locale="en")
    assert head.worse is False
    assert exit_code(head) != EXIT_WORSE


def test_an_honest_flip_up_is_still_an_improvement() -> None:
    """The control. Four cases counted on both sides and the gate crossed its
    threshold: that is a system that got better, and it still says so."""
    run = run_with(aggregate(1.0, 4))
    comparison = compare(run, RED_REFERENCE)
    (delta,) = comparison.deltas
    assert delta.denominator_moved is False
    assert comparison.counts["improved"] == 1
    assert comparison.incomparable == ()


def test_a_reference_that_counted_fewer_cases_is_incomparable_too() -> None:
    """The denominator's own direction is not asked about.

    Here the *reference* is the smaller measurement — three counted there, four
    here — and the gate still flipped up. What is unequal is what the two sides
    measured, and inequality has no direction: reading only the shrinking side
    would leave a reference recorded through a bad afternoon as a licence to
    call anything an improvement.
    """
    (delta,) = compare(
        run_with(aggregate(1.0, 4)), run_with(aggregate(2 / 3, 3))
    ).deltas
    assert delta.denominator_moved is True
    assert delta.outcome == "improved"
    assert "measured over 4 cases against 3 in the reference" in delta.reason


def test_the_flip_predicate_is_the_denominator_and_not_the_error() -> None:
    """The same rule the movement branch has: five things take a case out of a
    denominator, and keying on the error would leave the other four open."""
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
    (delta,) = compare(run_with(suspended), RED_REFERENCE).deltas
    assert delta.denominator_moved is True


def test_a_suite_that_grew_does_not_make_a_flip_incomparable() -> None:
    """The cry-wolf guard reaches the flip branch too, because it is the same
    predicate: two cases were added and the gate went green over six of them.
    That is a bigger suite and a better system, and it is counted as one."""
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
    comparison = compare(run_with(grown), RED_REFERENCE)
    (delta,) = comparison.deltas
    assert delta.denominator_moved is False
    assert comparison.counts["improved"] == 1


def test_a_moved_threshold_and_a_moved_denominator_both_reach_the_reason() -> None:
    """Two facts a reviewer needs and one sentence to hold them: the gate was
    lowered *and* it was measured over fewer cases. Neither excuses leaving the
    other out, and the clause is appended to the sentence rather than replacing
    it."""
    lowered = aggregate(1.0, 3, threshold=0.5)
    (delta,) = compare(run_with(lowered), RED_REFERENCE).deltas
    assert delta.denominator_moved is True
    assert "the threshold moved from 1.000000 to 0.500000" in delta.reason
    assert "measured over 3 cases against 4 in the reference" in delta.reason


def test_the_surfaces_say_it_with_the_sentences_they_already_had() -> None:
    """No new phrase was written for the flip, and this is what that means.

    An incomparable flip is an incomparability, so the terminal, the document,
    the reading and the wire each print what they already print for one. A
    second wording for one fact would be a second fact to reconcile — and it
    would have to be written in both locales, which is where a variant goes
    stale first.
    """
    run = run_with(aggregate(1.0, 3))
    comparison = compare(run, RED_REFERENCE)
    head = headline(comparison, run, RED_REFERENCE, locale="en")

    # The terminal sentence.
    assert head.denominator_moved == 1
    assert "1 run-level check was measured over a different number of cases" in (
        head.sentence
    )
    # The terminal list: named in the incomparable group, not as an improvement.
    (line,) = summary_lines(comparison, run, RED_REFERENCE, locale="en")
    assert "easured over 3 cases here and 4 in the reference" in line
    for claim in ("rose", "got better", "flipped"):
        assert claim not in line

    # The document.
    document = render_html(comparison, run, RED_REFERENCE, locale="en")
    assert "What was not compared" in document
    assert "not a movement of one another" in document
    assert "improved <b>0</b>" in document
    better = document.split("What got better")[1]
    assert better.startswith(' (0)</summary><p class="empty"')

    # The reading.
    said = "\n".join(explain_text(facts(run, comparison), locale="en"))
    assert "measured over 3 cases here and 4 in the reference" in said
    assert "got better" not in said

    # The wire.
    payload = explain_json(facts(run, comparison), scope="comparison", exit_code=0)
    (row,) = [
        f
        for f in cast("list[dict[str, object]]", payload["facts"])
        if f.get("about") == "check"
    ]
    assert row["denominator_moved"] is True
    assert row["kind"] == "improved"


# --------------------------------------------------------------------------- #
# The whole chain, on the real assertion
# --------------------------------------------------------------------------- #


TRAJECTORY = "tools_called"


def judged(case_id: str, *, kept: bool) -> CaseOutcome:
    """A case the trajectory check judged, and the mark it carried."""
    return CaseOutcome(
        case_id,
        "positive",
        Verdict(
            score=Score(name=TRAJECTORY, score=1.0 if kept else 0.0),
            threshold=1.0,
            tolerance=0.0,
            status="pass" if kept else "fail",
            reason="the tool call was named" if kept else "the wrong tool was called",
            assertion_id=f"id-{TRAJECTORY}",
        ),
    )


def unjudgeable(case_id: str) -> CaseOutcome:
    """The same case after the endpoint returned a shape digline cannot read.

    This is the whole of the attacker's move, and it needs no repository access:
    the check errors, so the case leaves the matrix — which is `errored_excluded`
    and not a judgement of any kind.
    """
    return CaseOutcome(
        case_id,
        "positive",
        Verdict(
            score=Score(name=TRAJECTORY, score=None),
            threshold=1.0,
            tolerance=0.0,
            status="error",
            reason="the provider returned a tool call with no name",
            assertion_id=f"id-{TRAJECTORY}",
        ),
    )


def set_aside(case_id: str) -> CaseOutcome:
    """A case somebody suspended: no verdict, so it leaves the matrix as
    `suspended_excluded` rather than being judged."""
    return CaseOutcome(case_id, "positive", None)


def run_of(*outcomes: CaseOutcome, threshold: float = 1.0) -> Run:
    """A run whose run-level `recall` is computed by the real assertion over the
    real confusion matrix, with the cases it was computed from beside it."""
    recall = Recall(over=TRAJECTORY, threshold=threshold, tolerance=0.0)(outcomes)
    return Run(
        tenant="acme",
        environment="test",
        suite="agent-suite",
        config_hash="hash-a",
        created_at=CREATED,
        results=tuple(
            CaseResult(
                case_id=o.case_id,
                verdicts=() if o.verdict is None else (o.verdict,),
                suspended="set aside while it is investigated"
                if o.verdict is None
                else None,
            )
            for o in outcomes
        ),
        aggregate=(recall,),
    )


def test_the_advisory_scenario_end_to_end_with_the_real_recall() -> None:
    """GHSA-8c38-f965-cgww's table, built by the code the advisory is about.

    Four cases, all marked worth keeping. The reference is honest and red: the
    system got `c4` wrong, so `recall` reads `fail 0.750000 = 3/4` and a team is
    working on it. Then the endpoint returns a tool call with no name for `c4`,
    that check errors, the case leaves the matrix, and `recall` reads
    `pass 1.000000 = 3/3` — the gate raised from `fail` to `pass` by whoever
    operates the endpoint, with no access to the repository.

    Every number here is the real assertion's. The helpers above this section
    write the matrix metadata by hand, which is the right economy for a rule
    about reading it and the wrong one for the claim that the rule fires on what
    digline actually records — `considered`, `errored_excluded` and the four
    cells come out of `Matrix.as_metadata()` here, and nothing in the test
    spells them.
    """
    reference = run_of(
        judged("c1", kept=True),
        judged("c2", kept=True),
        judged("c3", kept=True),
        judged("c4", kept=False),
    )
    attacked = run_of(
        judged("c1", kept=True),
        judged("c2", kept=True),
        judged("c3", kept=True),
        unjudgeable("c4"),
    )

    # The premise, measured rather than assumed: the gate really does flip.
    (was,) = reference.aggregate
    (is_now,) = attacked.aggregate
    assert (was.status, was.score.score) == ("fail", 0.75)
    assert (is_now.status, is_now.score.score) == ("pass", 1.0)
    assert was.score.metadata["considered"] == 4
    assert is_now.score.metadata["considered"] == 3
    assert is_now.score.metadata["errored_excluded"] == 1

    comparison = compare(attacked, reference)
    (recall_delta,) = [d for d in comparison.deltas if d.assertion == "recall"]
    assert recall_delta.denominator_moved is True
    assert comparison.counts.get("improved", 0) == 0
    assert comparison.incomparable == (recall_delta,)

    # What a person reads. The gate is not among the improvements, and the
    # sentence names the two numbers of cases instead of a direction.
    head = headline(comparison, attacked, reference, locale="en")
    assert head.denominator_moved == 1
    assert "1 run-level check was measured over a different number of cases" in (
        head.sentence
    )
    document = render_html(comparison, attacked, reference, locale="en")
    assert "What was not compared" in document
    assert "improved <b>0</b>" in document

    # And what does not change: the case that could not be judged is still
    # unjudged, so the run does not go green. That was true before this fix and
    # is the reason the advisory scores I:L — the exit code was never the defect,
    # the reading was.
    assert head.unjudged == 1
    assert exit_code(head) == EXIT_UNJUDGED


def test_a_flip_down_can_be_a_false_alarm_and_still_exits_one() -> None:
    """The price of the asymmetry, pinned so that it stays a decision.

    The gate is at 0.75 and `c3` fails on both sides, so the reference reads
    `pass 0.750000 = 3/4`. Then `c4` — a case that *passed* — leaves the count,
    and the run reads `fail 0.666667 = 2/3`. No case got worse, and with `c4`
    counted the gate would hold; the run is red and exits 1 anyway, with the
    denominator unmentioned. So a gate failing its own threshold is **not**
    failing whatever the reference counted — below 1.0 it need not be — and the
    reading stays only because withdrawing it would make a run *greener*.
    (ADR 0012 §3, as corrected 2026-09-18; GHSA-8c38-f965-cgww)
    """
    held = (judged("c1", kept=True), judged("c2", kept=True))
    failing = judged("c3", kept=False)
    reference = run_of(*held, failing, judged("c4", kept=True), threshold=0.75)

    # Errored and suspended are the two ways a case leaves the count without a
    # repository edit, and the run would otherwise exit 2 and 0 respectively.
    for leaving, would_exit in (
        (unjudgeable("c4"), EXIT_UNJUDGED),
        (set_aside("c4"), EXIT_OK),
    ):
        run = run_of(*held, failing, leaving, threshold=0.75)

        # The premise, measured: the gate crosses its bar on the way down.
        (was,) = reference.aggregate
        (is_now,) = run.aggregate
        assert (was.status, was.score.score) == ("pass", 0.75)
        assert (is_now.status, is_now.score.score) == ("fail", 0.666667)

        comparison = compare(run, reference)
        (recall_delta,) = [d for d in comparison.deltas if d.assertion == "recall"]
        assert recall_delta.outcome == "regressed"
        assert recall_delta.denominator_moved is False
        # No case got worse: the only regression in the run is the gate.
        assert comparison.regressed == (recall_delta,)

        head = headline(comparison, run, reference, locale="en")
        assert head.worse is True
        assert head.denominator_moved == 0
        assert exit_code(head) == EXIT_WORSE

        # The counterfactual, which is what makes it a false alarm rather than a
        # regression: the same cases under a bar both sides clear are an
        # incomparability, nothing is worse, and the run exits what it would
        # have exited without the gate. The exit code moved because of the
        # denominator and only because of it.
        lenient = run_of(*held, failing, leaving, threshold=0.5)
        lenient_reference = run_of(
            *held, failing, judged("c4", kept=True), threshold=0.5
        )
        lenient_comparison = compare(lenient, lenient_reference)
        lenient_head = headline(
            lenient_comparison, lenient, lenient_reference, locale="en"
        )
        assert lenient_head.denominator_moved == 1
        assert lenient_head.worse is False
        assert exit_code(lenient_head) == would_exit


# --------------------------------------------------------------------------- #
# The number checked against its own parts, and against the run:
# F-4 of the second 0.17.0 delta-pass
# --------------------------------------------------------------------------- #


def counted_verdict(**metadata: object) -> Verdict:
    """A run-level verdict carrying exactly the metadata given."""
    return Verdict(
        score=Score(name="precision", score=1.0, metadata=metadata),
        threshold=0.9,
        tolerance=0.0,
        status="pass",
        reason="r",
        assertion_id="id-precision",
    )


def run_of_cases(*, cases: int, suspended: int = 0) -> Run:
    return Run(
        tenant="acme",
        environment="test",
        suite="agent-suite",
        config_hash="hash-a",
        created_at=CREATED,
        results=tuple(
            CaseResult(
                case_id=f"c{i:02}",
                verdicts=(),
                suspended="set aside" if i < suspended else None,
            )
            for i in range(cases)
        ),
    )


def test_a_total_its_own_parts_contradict_is_not_read() -> None:
    """`as_metadata()` writes the four cells beside `considered`, and
    `considered` is their sum by construction — so the document carries the
    total *and* the addition that produced it. Nothing checked that they agree.
    """
    assert denominator(counted_verdict(considered=4, **_cells(2, 0, 2, 0))) is not None
    assert denominator(counted_verdict(considered=9, **_cells(2, 0, 2, 0))) is None


def test_the_cells_are_checked_only_when_they_are_all_there() -> None:
    """An aggregate is identified by `considered`, not by the cells: requiring
    them would unmake every figure written by an assertion that records a total
    and no matrix, which is a reading this pass had no mandate to withdraw."""
    assert denominator(counted_verdict(considered=3, suspended_excluded=1)) is not None
    # One cell missing and the addition cannot be done at all, which is not the
    # same as an addition that disagrees.
    assert (
        denominator(counted_verdict(considered=9, true_positive=2, false_positive=0))
        is not None
    )


def _cells(tp: int, fp: int, tn: int, fn: int) -> dict[str, object]:
    return {
        "true_positive": tp,
        "false_positive": fp,
        "true_negative": tn,
        "false_negative": fn,
    }


def test_a_negative_count_is_refused_like_a_boolean() -> None:
    """ "-5 of 2 cases counted" and "43 of 36 cases counted; -7 could not be
    judged." were both printed. Both numbers add up; neither can be true."""
    assert denominator(counted_verdict(considered=-5)) is None
    assert denominator(counted_verdict(considered=43, errored_excluded=-7)) is None


def test_a_denominator_larger_than_the_run_is_refused() -> None:
    """The first run-aware check: a whole-run aggregate saw every case the run
    holds, so 50 counted beside 7 excluded cannot come out of a 50-case run."""
    verdict = counted_verdict(considered=50, errored_excluded=7)

    assert denominator(verdict) is not None, "the verdict alone cannot tell"
    assert checked_denominator(verdict, case_count(run_of_cases(cases=50))) is None


def test_no_aggregate_may_count_a_suspended_case() -> None:
    """The second, and the one that caught the sentence worth catching: a
    suspended case carries no verdict, so nothing can have counted it. This is
    the shape that printed "All 20 cases counted." over a run where five were
    set aside."""
    claiming_all = counted_verdict(considered=20)
    run = run_of_cases(cases=20, suspended=5)

    assert checked_denominator(claiming_all, case_count(run)) is None
    honest = counted_verdict(considered=15, suspended_excluded=5)
    assert checked_denominator(honest, case_count(run)) is not None


def test_a_grouped_aggregate_is_not_asked_to_match_the_whole_run() -> None:
    """The exception that keeps the first check honest. A `by_group` aggregate
    is computed over its own group's cases, so its `seen` is *meant* to be
    smaller — and a stored run records no group per case, so the run cannot
    settle it. Checking anyway would strip the sentence from every grouped
    figure in every report."""
    grouped = Verdict(
        score=Score(
            name="precision[group=travel]", score=1.0, metadata={"considered": 4}
        ),
        threshold=0.9,
        tolerance=0.0,
        status="pass",
        reason="r",
        assertion_id="id-precision-travel",
    )

    assert checked_denominator(grouped, case_count(run_of_cases(cases=20))) is not None
    # The suspension bound still applies to it, as an upper bound.
    assert (
        checked_denominator(grouped, case_count(run_of_cases(cases=20, suspended=18)))
        is None
    )


def test_the_three_surfaces_state_the_checked_number_or_none_at_all() -> None:
    """ADR 0012 §3's same-truth rule, over the number rather than the sentence:
    the report's cell, `compare`'s line and `explain`'s reading now read one
    checked figure. The delta carries it because a delta holds no run."""
    run = run_of_cases(cases=20, suspended=5)
    lying = counted_verdict(considered=20)
    run = Run(
        tenant=run.tenant,
        environment=run.environment,
        suite=run.suite,
        config_hash=run.config_hash,
        created_at=run.created_at,
        results=run.results,
        aggregate=(lying,),
    )

    comparison = compare(run, run)
    (delta,) = [d for d in comparison.deltas if d.scope == "run"]
    assert delta.counted is None, "the row carries the checked number"

    document = render_html(comparison, run, run, locale="en")
    assert "All 20 cases counted" not in document
    assert "20 of 20" not in document

    for line in summary_lines(comparison, run, run, locale="en"):
        assert "All 20 cases counted" not in line
    for line in explain_text(facts(run, comparison), locale="en"):
        assert "All 20 cases counted" not in line
