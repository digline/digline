"""The rules that moved. (ADR 0028)

`config_hash` moving used to give a reader one boolean and one sentence, so a
threshold lowered from 0.6 to 0.5 and a test case added read identically. These
tests are about the table that tells them apart — derived from the two stored
documents, never recorded, and reported without ever gating.

The two that matter most are the quiet ones: a **tolerance** raised, which never
produces a flip and so was invisible to the one sentence that named a moved bar;
and `samples`, which takes no verb and must not acquire one.
"""

from __future__ import annotations

from dataclasses import replace

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
    """Rule 1, inherited from `config_deltas`: absent is not a change."""
    empty = run(cases=("s1",))
    assert suite_deltas(empty, empty) == ()
    assert suite_deltas(empty, run(verdicts=(verdict("contains"),))) != ()


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
# `samples` takes no verb, and this is the test that keeps it that way
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(("before_n", "after_n"), [(3, 5), (5, 3)])
def test_samples_moves_without_a_direction(before_n: int, after_n: int) -> None:
    """Neither way, and deliberately.

    More samples is a better-founded score **and**, because the interval a
    sampled check records is measured rather than declared, usually a wider
    noise floor — which `compare()` then forgives more movement inside. The two
    halves run opposite ways and nothing here can weigh them. A release that
    gives this a verb is making a claim ADR 0028 §4 examined and refused.
    """
    now = run(verdicts=(verdict("rubric", samples=after_n),), config_hash="hash-b")
    before = run(verdicts=(verdict("rubric", samples=before_n),))
    assert rows(now, before) == [("rubric", "samples", "changed", "")]


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
    head = headline(comparison, now, before, locale="en")
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
    head = headline(comparison, now, before, locale="en")
    assert "suite_deltas" not in compare_json(comparison, head, full=False)
    payload = compare_json(comparison, head, full=True)
    assert payload["suite_deltas"] == [
        {
            "rule": "contains",
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
    head = headline(compare(now, before), now, before, locale="en")
    payload = compare_json(compare(now, before), head, full=True)
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
    html = render_html(compare(now, before), now, before, locale="en")
    assert "What the rules were" in html
    assert "looser" in html
