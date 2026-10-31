"""The rules that moved. (ADR 0028)

`config_hash` moving used to give a reader one boolean and one sentence, so a
threshold lowered from 0.6 to 0.5 and a test case added read identically. These
tests are about the table that tells them apart — derived from the two stored
documents, never recorded, and reported without ever gating.

The two that matter most are the quiet ones: a **tolerance** raised, which never
produces a flip and so was invisible to the one sentence that named a moved bar;
and `samples`, which takes a verb on a case's check and none on an aggregate.
"""

from __future__ import annotations

import re
from dataclasses import replace
from pathlib import Path

import pytest

from digline.core import (
    AGREEMENT_FIELD,
    CaseResult,
    DifferentSuitesError,
    Run,
    Score,
    Verdict,
    compare,
    diff,
    redact,
    run_from_json,
    run_to_json,
    suite_deltas,
)
from digline.report import explain_text, facts, headline, rule_lines
from digline.wire import compare_json

CREATED = "2026-09-21T09:00:00+00:00"


def verdict(
    name: str,
    *,
    assertion_id: str = "",
    threshold: float = 0.5,
    tolerance: float = 0.0,
    score: float | None = 1.0,
    samples: int = 0,
    status: str = "pass",
) -> Verdict:
    """One recorded verdict, with the three numbers a rule is read back from.

    `samples` writes the count the way `combine_samples` does — into the
    metadata — because that is where the derivation reads it, and a test that
    set a field the document does not carry would be testing nothing.
    """
    metadata: dict[str, object] = {"samples": samples} if samples else {}
    return Verdict(
        score=Score(name=name, score=score, metadata=metadata),
        threshold=threshold,
        tolerance=tolerance,
        status=status,  # type: ignore[arg-type]
        reason="it answered",
        assertion_id=assertion_id or f"id-{name}",
    )


def run(
    *,
    verdicts: tuple[Verdict, ...] = (),
    aggregate: tuple[Verdict, ...] = (),
    config_hash: str = "hash-a",
    cases: tuple[str, ...] = ("c1",),
) -> Run:
    return Run(
        tenant="acme",
        environment="staging",
        suite="qa",
        config_hash=config_hash,
        created_at=CREATED,
        results=tuple(CaseResult(case_id, verdicts) for case_id in cases),
        aggregate=aggregate,
    )


def rows(now: Run, before: Run) -> list[tuple[str, str, str, str]]:
    """The table as `(rule, field, outcome, direction)`, for readable asserts.

    The agreement floor's standing `unknown` row is left out here and tested on
    its own below: it is not a rule that moved, it is the one member of
    `config_hash` no document records, and carrying it into every assertion
    would say nothing about the rule each of them is about.
    """
    return [
        (d.rule, d.field, d.outcome, d.direction)
        for d in suite_deltas(now, before)
        if d.rule != AGREEMENT_FIELD
    ]


# --------------------------------------------------------------------------- #
# The control: a suite that did not move says nothing
# --------------------------------------------------------------------------- #


def test_an_unchanged_suite_produces_no_rows() -> None:
    """The control that must produce nothing.

    A table that had rows here would print under *the suite is unchanged from
    the reference* and contradict it.
    """
    base = run(verdicts=(verdict("contains"),))
    assert suite_deltas(base, base) == ()


def test_neither_side_recorded_a_rule_is_not_every_rule_removed() -> None:
    """Rule 1, inherited from `config_deltas`: absent is not a change.

    The control is two sides that both carry case verdicts, where a rule really
    left. Until #671 the control here was an empty side against a full one, and
    it asserted rows: that is the defect, a side with no case verdict read as
    every rule removed, held in place by its own test.
    """
    empty = run(cases=("s1",))
    assert suite_deltas(empty, empty) == ()
    kept = run(verdicts=(verdict("contains"),), config_hash="hash-b")
    both = run(verdicts=(verdict("contains"), verdict("regex")))
    assert rows(kept, both) == [("regex", "", "missing", "loosened")]


# --------------------------------------------------------------------------- #
# Direction: down and up must not read alike
# --------------------------------------------------------------------------- #


def test_a_lowered_threshold_is_loosened() -> None:
    now = run(verdicts=(verdict("contains", threshold=0.5),), config_hash="hash-b")
    before = run(verdicts=(verdict("contains", threshold=0.6),))
    assert rows(now, before) == [("contains", "threshold", "changed", "loosened")]


def test_a_raised_threshold_is_tightened() -> None:
    now = run(verdicts=(verdict("contains", threshold=0.6),), config_hash="hash-b")
    before = run(verdicts=(verdict("contains", threshold=0.5),))
    assert rows(now, before) == [("contains", "threshold", "changed", "tightened")]


def test_a_raised_tolerance_is_loosened() -> None:
    """The quiet one, and the reason the record exists.

    `compare()` judges movement against the **current run's** tolerance, so a
    raised tolerance never produces a flip — it turns a `regressed` into an
    `unchanged`. `detail.threshold_moved`, the one place a moved bar was named
    before this, fires only on a flip, and so was structurally unable to see it.
    """
    now = run(verdicts=(verdict("rubric", tolerance=0.3),), config_hash="hash-b")
    before = run(verdicts=(verdict("rubric", tolerance=0.05),))
    assert rows(now, before) == [("rubric", "tolerance", "changed", "loosened")]


def test_a_lowered_tolerance_is_tightened() -> None:
    now = run(verdicts=(verdict("rubric", tolerance=0.01),), config_hash="hash-b")
    before = run(verdicts=(verdict("rubric", tolerance=0.05),))
    assert rows(now, before) == [("rubric", "tolerance", "changed", "tightened")]


def test_a_rule_added_is_tightened_and_one_removed_is_loosened() -> None:
    before = run(verdicts=(verdict("contains"),))
    added = run(verdicts=(verdict("contains"), verdict("rubric")), config_hash="hash-b")
    assert rows(added, before) == [("rubric", "", "new", "tightened")]
    # And read the other way round, which is the same edit undone.
    assert rows(before, added) == [("rubric", "", "missing", "loosened")]


def test_a_check_whose_threshold_and_tolerance_both_moved_gets_two_rows() -> None:
    """One row per moved value, never one per rule.

    They can move in opposite directions, and a single row would have to pick a
    verb — which is how a tightening would come to hide a loosening.
    """
    now = run(
        verdicts=(verdict("contains", threshold=0.7, tolerance=0.2),),
        config_hash="hash-b",
    )
    before = run(verdicts=(verdict("contains", threshold=0.5, tolerance=0.0),))
    assert rows(now, before) == [
        ("contains", "threshold", "changed", "tightened"),
        ("contains", "tolerance", "changed", "loosened"),
    ]


# --------------------------------------------------------------------------- #
# `samples` takes a verb on a case's check, and none on an aggregate
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("before_n", "after_n", "direction"), [(3, 5, "tightened"), (5, 3, "loosened")]
)
def test_samples_on_a_case_moves_with_a_direction(
    before_n: int, after_n: int, direction: str
) -> None:
    """More samples is stricter, fewer is looser.

    The floor is the dispersion of the mean of the baseline's samples, which
    narrows as K grows, so more samples steadies the score and narrows the floor
    in the same edit: the two halves ADR 0028 §4 once found unweighable point
    the same way. (ADR 0028 §4, as amended 2026-10-15)
    """
    now = run(verdicts=(verdict("rubric", samples=after_n),), config_hash="hash-b")
    before = run(verdicts=(verdict("rubric", samples=before_n),))
    assert rows(now, before) == [("rubric", "samples", "changed", direction)]


@pytest.mark.parametrize(("before_n", "after_n"), [(3, 5), (5, 3)])
def test_samples_on_an_aggregate_moves_without_a_direction(
    before_n: int, after_n: int
) -> None:
    """Neither way: a run-level aggregate's floor is outside ADR 0050.

    The amendment that gives a case's `samples` its verb is framed to the
    dispersion of the mean of a case's samples, and says nothing of which way an
    aggregate's floor moves. So the row prints both counts and stops.
    """
    now = run(aggregate=(verdict("mean", samples=after_n),), config_hash="hash-b")
    before = run(aggregate=(verdict("mean", samples=before_n),))
    assert rows(now, before) == [("mean", "samples", "changed", "")]


def test_an_unsampled_check_reads_as_one_sample() -> None:
    """Absent metadata is one sample, which is what ADR 0006 §4 writes."""
    now = run(verdicts=(verdict("rubric", samples=3),), config_hash="hash-b")
    before = run(verdicts=(verdict("rubric"),))
    delta = suite_deltas(now, before)[0]
    assert (delta.before, delta.after) == (1.0, 3.0)


def test_a_verdict_that_errored_before_its_fold_does_not_invent_one_sample() -> None:
    """Rule 3: a value not established on both sides is `unknown`, not a guess.

    A case whose target raised records an errored verdict with no metadata at
    all. Reading that absence as *one sample* would print `5 -> 1` about a suite
    nobody edited.
    """
    errored = verdict("rubric", score=None, status="error")
    now = run(verdicts=(errored,), config_hash="hash-b")
    before = run(verdicts=(verdict("rubric", samples=5),))
    assert rows(now, before) == [("rubric", "samples", "unknown", "")]


def test_one_errored_case_does_not_unknow_a_count_the_others_recorded() -> None:
    """`None` is *not established*, so it does not outvote a stated value."""
    now = run(
        verdicts=(verdict("rubric", samples=5),),
        cases=("c1", "c2"),
        config_hash="hash-b",
    )
    now = replace(
        now,
        results=(
            now.results[0],
            CaseResult("c2", (verdict("rubric", score=None, status="error"),)),
        ),
    )
    before = run(verdicts=(verdict("rubric", samples=5),))
    assert rows(now, before) == []


# --------------------------------------------------------------------------- #
# A case is not a rule
# --------------------------------------------------------------------------- #


def test_adding_a_case_produces_no_rule_row() -> None:
    """The most ordinary edit there is, and it stays silent here.

    Not a convention to be careful about: the key is the assertion's identity
    and the rows are unioned over the cases, so a case cannot contribute one.
    The case set is named by `compare()`'s own `new` and `missing` deltas.
    """
    before = run(verdicts=(verdict("contains"),), cases=("c1",))
    now = run(verdicts=(verdict("contains"),), cases=("c1", "c2"))
    assert suite_deltas(now, before) == ()


def test_suspending_a_case_produces_no_rule_row() -> None:
    before = run(verdicts=(verdict("contains"),), cases=("c1", "c2"))
    now = replace(
        before,
        results=(before.results[0], CaseResult("c2", (), suspended="set aside")),
    )
    assert suite_deltas(now, before) == ()


def test_two_assertions_sharing_an_identity_do_not_collapse() -> None:
    """`identity` excludes threshold and tolerance, so two checks that differ
    only in where their bar sits share one — and would otherwise fold into a
    rule that appeared to contradict itself."""
    pair = (
        verdict("contains", assertion_id="id-x", threshold=0.5),
        verdict("contains", assertion_id="id-x", threshold=0.9),
    )
    moved = (
        verdict("contains", assertion_id="id-x", threshold=0.5),
        verdict("contains", assertion_id="id-x", threshold=0.8),
    )
    assert rows(run(verdicts=moved, config_hash="hash-b"), run(verdicts=pair)) == [
        ("contains", "threshold", "changed", "loosened")
    ]


# --------------------------------------------------------------------------- #
# §6: a gate that appeared over a group, without naming a case
# --------------------------------------------------------------------------- #


def test_a_new_group_reads_as_a_case_labelled_not_a_rule_rewritten() -> None:
    """The reference already gated per group, and not on this one.

    A group exists only where a case declares it, so a case was labelled. The
    case itself is **not** named: neither document records membership (ADR 0010
    §1), and re-labelling an existing case produces a group with no new case
    behind it at all.
    """
    before = run(
        aggregate=(verdict("precision"), verdict("precision[group=air]")),
        cases=("c1",),
    )
    now = replace(
        before,
        aggregate=(*before.aggregate, verdict("precision[group=hotel]")),
        config_hash="hash-b",
    )
    (delta,) = [d for d in suite_deltas(now, before) if d.outcome == "new"]
    assert (delta.rule, delta.expansion, delta.direction) == (
        "precision[group=hotel]",
        "new_group",
        "tightened",
    )


def test_by_group_newly_set_reads_as_the_author_changing_the_rules() -> None:
    """The reference had no per-group row for this aggregate at all."""
    before = run(aggregate=(verdict("precision"),), cases=("c1",))
    now = replace(
        before,
        aggregate=(*before.aggregate, verdict("precision[group=air]")),
        config_hash="hash-b",
    )
    (delta,) = [d for d in suite_deltas(now, before) if d.outcome == "new"]
    assert delta.expansion == "now_grouped"


def test_an_ordinary_new_check_carries_no_expansion() -> None:
    before = run(verdicts=(verdict("contains"),))
    now = run(verdicts=(verdict("contains"), verdict("rubric")), config_hash="hash-b")
    (delta,) = [d for d in suite_deltas(now, before) if d.outcome == "new"]
    assert delta.expansion == ""


# --------------------------------------------------------------------------- #
# §5: the agreement floor, said where it gated and nowhere else
# --------------------------------------------------------------------------- #


def test_the_agreement_floor_is_named_as_unknown_where_a_side_sampled() -> None:
    now = run(verdicts=(verdict("rubric", samples=3, threshold=0.4),), config_hash="b")
    before = run(verdicts=(verdict("rubric", samples=3, threshold=0.5),))
    floor = [d for d in suite_deltas(now, before) if d.rule == AGREEMENT_FIELD]
    assert [(d.outcome, d.before, d.after) for d in floor] == [("unknown", None, None)]


def test_the_agreement_floor_is_silent_on_a_suite_that_never_sampled() -> None:
    now = run(verdicts=(verdict("contains", threshold=0.4),), config_hash="hash-b")
    before = run(verdicts=(verdict("contains", threshold=0.5),))
    assert all(d.rule != AGREEMENT_FIELD for d in suite_deltas(now, before))


def test_the_agreement_floor_is_silent_where_the_fingerprint_did_not_move() -> None:
    """Otherwise every comparison of every sampled suite carries a standing row
    about a value that did not move, under a sentence saying the suite did
    not."""
    base = run(verdicts=(verdict("rubric", samples=3),))
    assert suite_deltas(base, base) == ()


def test_the_floor_is_never_derived_from_the_measured_agreement() -> None:
    """The vote is in the metadata; the bar it was held to is not, and one is
    not the other."""
    sampled = verdict("rubric", samples=3)
    sampled = replace(
        sampled,
        score=Score(
            name="rubric", score=1.0, metadata={"samples": 3, "agreement": 1.0}
        ),
    )
    now = run(verdicts=(sampled,), config_hash="hash-b")
    before = run(verdicts=(verdict("rubric", samples=3, threshold=0.6),))
    (floor,) = [d for d in suite_deltas(now, before) if d.rule == AGREEMENT_FIELD]
    assert floor.before is None and floor.after is None


# --------------------------------------------------------------------------- #
# The boundary: a redacted run yields the same table
# --------------------------------------------------------------------------- #


def test_a_redacted_run_yields_the_complete_table() -> None:
    """The gap is widest in world 2, and it closes fully there.

    Nothing a rule is made of can be withheld: `threshold`, `tolerance` and
    `assertion_id` survive `redact()`, and a sample count is an `int` that
    travels on its own merit.
    """
    now = run(
        verdicts=(verdict("rubric", threshold=0.4, samples=3),), config_hash="hash-b"
    )
    before = run(verdicts=(verdict("rubric", threshold=0.6, samples=3),))
    assert rows(redact(now), before) == rows(now, before)


def test_the_table_survives_the_disk() -> None:
    now = run(verdicts=(verdict("rubric", threshold=0.4),), config_hash="hash-b")
    before = run(verdicts=(verdict("rubric", threshold=0.6),))
    round_tripped = run_from_json(run_to_json(now))
    assert rows(round_tripped, before) == rows(now, before)


# --------------------------------------------------------------------------- #
# It reports and it never gates
# --------------------------------------------------------------------------- #


def test_a_loosened_rule_moves_no_exit_code_and_no_outcome() -> None:
    """`AGENTS.md` §1: the instrument measures, the human approves. The gate
    already exists and it is `promote_baseline`'s refusal across a changed
    `config_hash` — the signature is the gate."""
    now = run(verdicts=(verdict("contains", threshold=0.1),), config_hash="hash-b")
    before = run(verdicts=(verdict("contains", threshold=0.9, status="pass"),))
    comparison = compare(now, before)
    assert comparison.loosened_rules
    assert not comparison.has_regressions
    head = headline(comparison, now, before, locale="en", declared=None)
    assert not head.worse


# --------------------------------------------------------------------------- #
# §7: the refusal that says what differs
# --------------------------------------------------------------------------- #


def test_the_diff_refusal_names_the_rules() -> None:
    left = run(verdicts=(verdict("contains", threshold=0.6),))
    right = run(verdicts=(verdict("contains", threshold=0.5),), config_hash="hash-b")
    with pytest.raises(DifferentSuitesError) as raised:
        diff(left, right)
    message = str(raised.value)
    assert "re-run one side under the other's suite" in message
    assert "contains threshold 0.6 -> 0.5 (loosened)" in message


def test_the_diff_refusal_is_capped_and_counts_the_rest() -> None:
    """A suite rewritten wholesale must not print a hundred rows into an
    exception: a refusal nobody reads did not say what differs after all."""
    many = tuple(verdict(f"check{n}", threshold=0.5) for n in range(9))
    moved = tuple(verdict(f"check{n}", threshold=0.6) for n in range(9))
    with pytest.raises(DifferentSuitesError) as raised:
        diff(run(verdicts=many), run(verdicts=moved, config_hash="hash-b"))
    assert "and 4 more." in str(raised.value)


def test_a_refusal_with_nothing_nameable_promises_nothing() -> None:
    """Two suites can differ only in the one member of `config_hash` no document
    records. A refusal that promised to say what differs and then said nothing
    would be worse than the one that promised nothing."""
    left = run(verdicts=(verdict("rubric", samples=3),))
    right = replace(left, config_hash="hash-b")
    with pytest.raises(DifferentSuitesError) as raised:
        diff(left, right)
    assert "What differs:" not in str(raised.value)


# --------------------------------------------------------------------------- #
# The reading: wire, explain, terminal
# --------------------------------------------------------------------------- #


def test_the_wire_carries_the_rules_under_full_only() -> None:
    now = run(verdicts=(verdict("contains", threshold=0.4),), config_hash="hash-b")
    before = run(verdicts=(verdict("contains", threshold=0.6),))
    comparison = compare(now, before)
    head = headline(comparison, now, before, locale="en", declared=None)
    assert "suite_deltas" not in compare_json(
        comparison, head, baseline=before, full=False
    )
    payload = compare_json(comparison, head, baseline=before, full=True)
    assert payload["suite_deltas"] == [
        {
            "assertion": "contains",
            "assertion_id": "id-contains",
            "scope": "case",
            "outcome": "changed",
            "direction": "loosened",
            "field": "threshold",
            "before": 0.6,
            "after": 0.4,
            "expansion": "",
        }
    ]


def test_the_wire_never_carries_a_withheld_key_for_a_rule() -> None:
    """`config_json` has one because a configuration can hold a perimeter value.
    A rule cannot, and a key that was always `false` would invite a reader to
    look for the case where it is not."""
    now = run(verdicts=(verdict("contains", threshold=0.4),), config_hash="hash-b")
    before = run(verdicts=(verdict("contains", threshold=0.6),))
    head = headline(compare(now, before), now, before, locale="en", declared=None)
    payload = compare_json(compare(now, before), head, baseline=before, full=True)
    rule = payload["suite_deltas"][0]  # type: ignore[index]
    assert "withheld" not in rule


@pytest.mark.parametrize("locale", ["en", "it"])
def test_explain_names_the_rule_and_its_direction(locale: str) -> None:
    now = run(verdicts=(verdict("contains", threshold=0.4),), config_hash="hash-b")
    before = run(verdicts=(verdict("contains", threshold=0.6),))
    comparison = compare(now, before)
    reading = facts(now, comparison)
    assert any(getattr(f, "kind", "") == "rule" for f in reading)
    text = explain_text(reading, locale=locale)  # type: ignore[arg-type]
    assert any("contains.threshold" in line for line in text)


def test_the_terminal_puts_the_loosened_rule_first() -> None:
    """A suite that tightened three bars and loosened one has nothing to net
    out; the reader scanning the first line is owed the edit that lets more
    through."""
    before = run(
        verdicts=(
            verdict("a_tightened", threshold=0.4),
            verdict("z_loosened", threshold=0.6),
        )
    )
    now = run(
        verdicts=(
            verdict("a_tightened", threshold=0.9),
            verdict("z_loosened", threshold=0.1),
        ),
        config_hash="hash-b",
    )
    (line,) = rule_lines(compare(now, before), locale="en")
    assert line.index("z_loosened") < line.index("a_tightened")
    assert "(looser)" in line and "(stricter)" in line


def test_a_sample_count_is_printed_whole() -> None:
    """`5 → 3`, not `5.0 → 3.0`. A count is a count, and a decimal point here is
    a number wearing a threshold's clothes."""
    now = run(verdicts=(verdict("rubric", samples=3),), config_hash="hash-b")
    before = run(verdicts=(verdict("rubric", samples=5),))
    (line,) = rule_lines(compare(now, before), locale="en")
    assert "samples of rubric 5 → 3" in line
    assert "5.0" not in line


@pytest.mark.parametrize("locale", ["en", "it"])
def test_the_floor_gets_its_own_sentence_not_a_rules(locale: str) -> None:
    """It is not a rule half the runs forgot to record; it is the one member of
    `config_hash` no run has ever recorded."""
    now = run(verdicts=(verdict("rubric", samples=3, threshold=0.4),), config_hash="b")
    before = run(verdicts=(verdict("rubric", samples=3, threshold=0.5),))
    (line,) = rule_lines(compare(now, before), locale=locale)  # type: ignore[arg-type]
    assert AGREEMENT_FIELD not in line


def test_the_terminal_says_nothing_about_an_unchanged_suite() -> None:
    base = run(verdicts=(verdict("contains"),))
    assert rule_lines(compare(base, base), locale="en") == ()


def test_the_report_carries_the_rules_section() -> None:
    from digline.report import render_html

    now = run(verdicts=(verdict("contains", threshold=0.4),), config_hash="hash-b")
    before = run(verdicts=(verdict("contains", threshold=0.6),))
    html = render_html(compare(now, before), now, before, locale="en", declared=None)
    assert "What the rules were" in html
    assert "looser" in html


# --------------------------------------------------------------------------- #
# A side with no case verdict (#671; ADR 0028 §3, rule 1 as corrected)
# --------------------------------------------------------------------------- #


def _suspended(of: Run, *, config_hash: str) -> Run:
    """`of` with every case suspended, so its cases carry no verdict at all."""
    return replace(
        of,
        config_hash=config_hash,
        results=tuple(
            CaseResult(case.case_id, (), suspended="set aside") for case in of.results
        ),
    )


AGGREGATE = (verdict("recall", assertion_id="id-recall"),)


@pytest.mark.parametrize("config_hash", ["hash-a", "hash-b"])
def test_every_case_suspended_is_not_every_check_removed(config_hash: str) -> None:
    """The issue's third form: the suite still declares both checks.

    Run with the fingerprint unchanged and with it moved, because the hash is
    a second proof and not the condition: a suite edited *and* fully suspended
    still has no case verdict on that side to compare.
    """
    before = run(
        verdicts=(verdict("contains"), verdict("llm_rubric")), cases=("c1", "c2")
    )
    now = _suspended(before, config_hash=config_hash)
    assert rows(now, before) == []
    assert rows(before, now) == []


def test_every_case_suspended_beside_an_aggregate_is_no_case_row() -> None:
    """The aggregate still carries a verdict on the suspended side, so a side
    with *no rule at all* is the wrong condition: the cases are what is empty."""
    before = run(
        verdicts=(verdict("contains"), verdict("llm_rubric")),
        aggregate=AGGREGATE,
        cases=("c1", "c2"),
    )
    now = _suspended(before, config_hash="hash-b")
    assert rows(now, before) == []
    assert rows(before, now) == []


def test_removing_the_last_aggregate_is_still_a_rule_removed() -> None:
    """The other direction. A run always carries one verdict per aggregate its
    suite declares, so an empty run scope is the suite's choice and `missing`
    is true there. A repair that also emptied the run scope would hide it."""
    before = run(verdicts=(verdict("contains"),), aggregate=AGGREGATE)
    now = run(verdicts=(verdict("contains"),), config_hash="hash-b")
    assert rows(now, before) == [("recall", "", "missing", "loosened")]
    suspended = _suspended(now, config_hash="hash-b")
    assert rows(suspended, before) == [("recall", "", "missing", "loosened")]


def _unknown_samples() -> tuple[Run, Run]:
    """The issue's first form: a field neither side established, so `unknown`."""
    errored = verdict("contains", score=None, status="error")
    now = run(verdicts=(errored,))
    before = run(verdicts=(verdict("contains", samples=2),))
    assert rows(now, before) == [("contains", "samples", "unknown", "")]
    return now, before


def _cases(*verdicts: Verdict, config_hash: str = "hash-a") -> Run:
    """One case per verdict, so the cases of one side can disagree."""
    return Run(
        tenant="acme",
        environment="staging",
        suite="qa",
        config_hash=config_hash,
        created_at=CREATED,
        results=tuple(
            CaseResult(f"c{i}", (v,)) for i, v in enumerate(verdicts, start=1)
        ),
    )


def _unknown_threshold() -> tuple[Run, Run]:
    """Rule 3's other way in: values stated on one side that disagree between
    its cases, so the side has no single value."""
    now = _cases(verdict("contains", threshold=0.5), verdict("contains", threshold=0.7))
    before = _cases(verdict("contains"), verdict("contains"))
    assert rows(now, before) == [("contains", "threshold", "unknown", "")]
    return now, before


def _unknown_width() -> tuple[Run, Run]:
    """`_width_moved`'s: the cases of one side declare different widths."""
    now = _cases(
        replace(verdict("contains"), floor_standard_errors=2.0),
        replace(verdict("contains"), floor_standard_errors=3.0),
    )
    before = _cases(
        replace(verdict("contains"), floor_standard_errors=2.0),
        replace(verdict("contains"), floor_standard_errors=2.0),
    )
    assert rows(now, before) == [("contains", "floor_standard_errors", "unknown", "")]
    return now, before


def _unknown_width_both() -> tuple[Run, Run]:
    """F-2 of the delta-pass over 1.0.2: the cases of **each** side declare
    different widths. Neither side has one value, and both have values."""
    disagreeing = (
        replace(verdict("contains"), floor_standard_errors=2.0),
        replace(verdict("contains"), floor_standard_errors=3.0),
    )
    now, before = _cases(*disagreeing), _cases(*disagreeing)
    assert rows(now, before) == [("contains", "floor_standard_errors", "unknown", "")]
    return now, before


#: The ways a row reaches `unknown` with a field, each with the name the
#: sentence carries and the sentence that is true of it. A threshold, a
#: tolerance or a count of samples reaches it with exactly one side lacking a
#: single value, none or more than one: `_moved` gives no row where both do.
#: A width reaches it where the cases of one side **or of both** declare
#: different widths, and both sides then have values: "no single value on one
#: side" was false of the second (F-2), so the width has a sentence of its
#: own, true of both, and nothing in the row says which of the two it is.
UNKNOWN = {
    "samples, every verdict errored": (_unknown_samples, "contains.samples", "one"),
    "threshold, the cases disagree": (_unknown_threshold, "contains.threshold", "one"),
    "width, one side's cases disagree": (
        _unknown_width,
        "contains.floor_standard_errors",
        "width",
    ),
    "width, both sides' cases disagree": (
        _unknown_width_both,
        "contains.floor_standard_errors",
        "width",
    ),
}

UNKNOWN_SENTENCE = {
    "one": {
        "en": "{name} has no single value on one side, so whether it moved is "
        "not known",
        "it": "{name} non ha un valore unico su uno dei due lati, quindi non si sa se "
        "si sia mosso",
    },
    "width": {
        "en": "{name} is declared differently by the cases of one side or of both, "
        "so whether it moved is not known",
        "it": "{name} è dichiarato in modo diverso dai casi di un lato o di entrambi, "
        "quindi non si sa se si sia mosso",
    },
}

UNKNOWN_CELL = {
    "one": {
        "en": "no single value on one side, so whether it moved is not known",
        "it": "nessun valore unico su uno dei due lati, quindi non si sa se si "
        "sia mosso",
    },
    "width": {
        "en": "declared differently by the cases of one side or of both, so whether "
        "it moved is not known",
        "it": "dichiarato in modo diverso dai casi di un lato o di entrambi, quindi "
        "non si sa se si sia mosso",
    },
}


@pytest.mark.parametrize("producer", list(UNKNOWN))
@pytest.mark.parametrize("locale", ["en", "it"])
def test_the_terminal_says_an_unknown_field_has_no_single_value(
    locale: str, producer: str
) -> None:
    """`samples of contains 2 → —` read as a declaration that moved to nothing,
    under a sentence saying the suite is unchanged. And *not recorded on both
    sides*, which it said until 1.0.2, was false for two of the three: a
    threshold or a width the cases disagree on was recorded."""
    build, name, sentence = UNKNOWN[producer]
    now, before = build()
    (line,) = rule_lines(compare(now, before), locale=locale)  # type: ignore[arg-type]
    assert "→" not in line
    assert UNKNOWN_SENTENCE[sentence][locale].format(name=name) in line
    if sentence == "width":
        assert "one side," not in line and "uno dei due lati" not in line, line


@pytest.mark.parametrize("producer", list(UNKNOWN))
@pytest.mark.parametrize("locale", ["en", "it"])
def test_the_report_says_an_unknown_field_has_no_single_value(
    locale: str, producer: str
) -> None:
    """The HTML table's own branch on `field`, which the terminal's does not
    share: one test for each, or one of them is green by not being looked at."""
    from digline.report import render_html

    build, name, sentence = UNKNOWN[producer]
    now, before = build()
    html = render_html(compare(now, before), now, before, locale=locale, declared=None)  # type: ignore[arg-type]
    cell = UNKNOWN_CELL[sentence][locale]
    assert f"<td><code>{name}</code></td><td>{cell}</td>" in html
    assert " → —" not in html


ADR_0028 = (
    Path(__file__).resolve().parents[1]
    / "docs"
    / "adr"
    / "0028-the-rules-that-moved.md"
)

#: The titles of §3's first two rules, as approved with #671. The tests above
#: hold the conditions; this holds the words that state them.
RULE_TITLES = {
    "1": "A side with no case verdict → no row about the cases.",
    "2": "A field one side's verdicts did not record → `unknown`, never `new` or "
    "`missing`.",
}


def test_the_record_titles_its_first_two_rules_as_the_code_reads_them() -> None:
    text = ADR_0028.read_text(encoding="utf-8")
    section = text[text.index("### 3. Four rules") : text.index("And one this needs")]
    # Folded first: a title the file wraps over two lines is still one title.
    folded = " ".join(section.split())
    titles = dict(re.findall(r"(?:^| )(\d)\. \*\*(.+?)\*\*", folded))
    assert {n: titles.get(n) for n in RULE_TITLES} == RULE_TITLES
