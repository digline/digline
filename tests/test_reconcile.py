"""The run reconciles with what it was asked. (ADR 0027)

Two checks, in the driver, reading its own dispatch back: every declared case
has exactly one result, and every result carries exactly one verdict per
question it was asked and none it was not. A gap becomes a named errored
verdict, so the run exits 2, cannot be promoted and says it does not know what
it measured — and is never a regression.

The pressure behind it was named by nitish-kmr: a hard refusal on errors
rewards wrapping them so the run finishes. §2 of the record says what no count
can see; these tests are about what one can.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import pytest

from digline.core import (
    UNRECONCILED,
    Accuracy,
    CallTotals,
    CaseResult,
    Contains,
    Disclosure,
    EvaluatorInputs,
    Gap,
    OutputKind,
    Run,
    Score,
    Verdict,
    compare,
    reconcile,
    redact,
    run_from_json,
    run_to_json,
    unreconciled,
)
from digline.report import explain_text, facts, headline, render_run_html
from digline.report.render import NAMED_GAPS, unreconciled_fact
from digline.run import Case, Response, Suite, execute
from digline.store import ErroredRunError, FileResultStore
from digline.wire import (
    EXIT_UNJUDGED,
    compare_json,
    exit_code,
    explain_json,
    run_document,
)

CREATED = "2026-09-19T10:00:00+00:00"
ASKED = frozenset({"id-a", "id-b"})


def verdict(assertion_id: str, *, status: str = "pass") -> Verdict:
    return Verdict(
        score=Score(name=assertion_id.removeprefix("id-"), score=1.0),
        threshold=1.0,
        status="pass" if status == "pass" else "fail",
        reason="it answered",
        assertion_id=assertion_id,
    )


# --------------------------------------------------------------------------- #
# The comparison: pure, named, in a fixed order
# --------------------------------------------------------------------------- #


def test_a_run_that_answered_everything_reconciles() -> None:
    results = [
        CaseResult("c1", (verdict("id-a"), verdict("id-b"))),
        CaseResult("s1", suspended="set aside"),
    ]
    assert reconcile({"c1": ASKED, "s1": frozenset()}, results) == ()


def test_a_missing_verdict_and_a_missing_case_are_named() -> None:
    results = [CaseResult("c1", (verdict("id-a"),))]
    assert reconcile({"c1": ASKED, "c2": ASKED}, results) == (
        Gap("missing", "c1", "id-b"),
        Gap("missing", "c2"),
    )


def test_an_answer_nobody_asked_for_is_a_gap_too() -> None:
    """A verdict for a check the case was not put, and a second verdict for one
    it was: the run may not keep an answer to a question it did not ask."""
    results = [
        CaseResult("c1", (verdict("id-a"), verdict("id-a"), verdict("id-b"))),
        CaseResult("s1", (verdict("id-a"),)),
    ]
    assert reconcile({"c1": ASKED, "s1": frozenset()}, results) == (
        Gap("unasked", "c1", "id-a"),
        Gap("unasked", "s1", "id-a"),
    )


def test_a_result_twice_or_for_an_undeclared_case_is_named() -> None:
    results = [
        CaseResult("c1", (verdict("id-a"), verdict("id-b"))),
        CaseResult("c1", (verdict("id-a"),)),
        CaseResult("ghost", ()),
    ]
    assert reconcile({"c1": ASKED}, results) == (
        Gap("unasked", "c1", "id-a"),
        Gap("unasked", "ghost"),
    )


# --------------------------------------------------------------------------- #
# The driver: what it asks, and what it records when the answer is not there
# --------------------------------------------------------------------------- #


def a_suite(*cases: Case, samples: int = 1) -> Suite:
    return Suite(
        samples=samples,
        min_agreement=1.0 if samples > 1 else None,
        tenant="acme",
        environment="test",
        name="triage",
        assertions=[Contains(needle="yes", name="agrees")],
        run_assertions=[Accuracy(over="agrees", threshold=0.5, tolerance=0.0)],
        cases=list(cases) or [Case(id=f"c{n}", label="positive") for n in range(1, 4)],
    )


def answering(case: Case) -> Response:  # noqa: ARG001 — the Target protocol names it
    return Response(output="yes")


def test_every_kind_of_case_reconciles_as_the_driver_dispatches_it() -> None:
    """Suspended asks nothing, canary asks everything: the dispatch read back.
    A run the shipped driver produces carries no marker at all."""
    run = execute(
        a_suite(
            Case(id="c1", label="positive"),
            Case(id="s1", label="positive", suspended="set aside"),
            Case(id="k1", canary=True),
            # A canary is read against its own noise, so it needs samples.
            samples=2,
        ),
        answering,
        created_at=CREATED,
    )
    assert unreconciled(run) == ()
    assert all(
        UNRECONCILED not in v.score.metadata for c in run.results for v in c.verdicts
    )


def lost_one() -> tuple[Suite, Run]:
    """A `done` entry built by hand that answers nothing and was not set aside.
    The journal refuses this shape before the first call (ADR 0027 §5); a
    library caller reaches `execute` with it, and the check catches it."""
    suite = a_suite()
    run = execute(
        suite,
        answering,
        created_at=CREATED,
        done={"c2": CaseResult("c2")},
        spent=CallTotals(),
    )
    return suite, run


def test_a_verdict_that_never_came_back_is_recorded_as_a_named_error() -> None:
    _suite, run = lost_one()
    assert unreconciled(run) == (("c2", "agrees"),)
    (row,) = [c for c in run.results if c.case_id == "c2"]
    (missing,) = row.verdicts
    assert missing.status == "error"
    assert missing.score.metadata[UNRECONCILED] is True
    assert "agrees was asked of case c2 and no verdict came back" in missing.reason
    # Counted as what it is — a check that could not be judged — and not as a
    # case somebody set aside, which is the flattering bucket it used to land in.
    (accuracy,) = run.aggregate
    assert accuracy.score.metadata["errored_excluded"] == 1
    assert accuracy.score.metadata["suspended_excluded"] == 0


def test_it_says_so_first_names_the_check_and_exits_two() -> None:
    _suite, run = lost_one()
    head = headline(compare(run, run), run, run, locale="en")
    assert head.sentence.startswith(
        "The run does not reconcile with what the suite asked, at 1 check: "
        "c2 · agrees. This is not a regression: what the run measured is not "
        "known."
    )
    assert head.worse is False
    assert head.unreconciled == 1
    assert exit_code(head) == EXIT_UNJUDGED
    assert compare_json(compare(run, run), head, full=False)["unreconciled"] == 1

    # Alone and compared: the fact is about this run, so both readings open
    # with it, above even a lost scale.
    for reading in (facts(run), facts(run, compare(run, run))):
        first = explain_text(reading, locale="en")[1]
        assert first.startswith("1 check does not reconcile with what the suite asked.")
    reading = facts(run)
    assert "c2 · agrees could not be judged." in explain_text(reading, locale="en")
    wire = explain_json(reading, scope="run", exit_code=2)
    assert wire["facts"][0] == {  # type: ignore[index]
        "about": "run",
        "kind": "unreconciled",
        "count": 1,
        "state": None,
    }
    assert "does not reconcile" in render_run_html(run, locale="en")


def test_the_italian_clause() -> None:
    _suite, run = lost_one()
    head = headline(compare(run, run), run, run, locale="it")
    assert head.sentence.startswith(
        "L'esecuzione non torna con ciò che la suite ha chiesto, in 1 controllo: "
        "c2 · agrees. Non è una regressione"
    )


def test_it_can_never_be_promoted_and_the_refusal_names_it(tmp_path: Path) -> None:
    suite, run = lost_one()
    store = FileResultStore(tmp_path)
    ref = store.write_run(run)
    with pytest.raises(ErroredRunError, match=r"c2 · agrees") as caught:
        store.promote_baseline(
            ref, suite.config_hash(), promoted_at="2026-09-19T11:00:00+00:00"
        )
    assert "not a regression" in str(caught.value)
    assert store.read_baseline("acme", "triage") is None


def test_an_answer_nobody_asked_for_is_not_kept() -> None:
    suite = a_suite()
    (agrees,) = suite.assertions
    asked = agrees(EvaluatorInputs(output="yes"))
    run = execute(
        suite,
        answering,
        created_at=CREATED,
        done={"c1": CaseResult("c1", (asked, asked))},
        spent=CallTotals(),
    )
    (row,) = [c for c in run.results if c.case_id == "c1"]
    assert [v.status for v in row.verdicts] == ["pass", "error"]
    assert unreconciled(run) == (("c1", "agrees"),)


def test_the_marker_survives_the_boundary_and_the_round_trip() -> None:
    _suite, run = lost_one()
    assert unreconciled(redact(run)) == (("c2", "agrees"),)
    assert unreconciled(run_from_json(run_to_json(run))) == (("c2", "agrees"),)


def test_the_marker_counts_only_on_an_errored_verdict() -> None:
    """An assertion may write any key it likes; on a verdict that answered, the
    key claims nothing."""
    answered = Verdict(
        score=Score(name="agrees", score=1.0, metadata={UNRECONCILED: True}),
        threshold=1.0,
        status="pass",
        reason="it answered",
        assertion_id="id-agrees",
    )
    run = Run(
        tenant="acme",
        environment="test",
        suite="triage",
        config_hash="cfg",
        created_at=CREATED,
        results=(CaseResult("c1", (answered,)),),
    )
    assert unreconciled(run) == ()


# --------------------------------------------------------------------------- #
# §6: an aggregate finds its verdict by identity
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Renamed:
    """A third-party assertion whose `Score` is named otherwise than itself."""

    name: str = "agrees"
    threshold: float = 1.0
    tolerance: float = 0.0
    KIND = "deterministic"

    @property
    def identity(self) -> str:
        return "renamed01"

    @property
    def accepts(self) -> frozenset[OutputKind]:
        return frozenset({"text"})

    def __call__(self, inputs: EvaluatorInputs) -> Verdict:
        passed = inputs.output == "yes"
        return Verdict(
            score=Score(name="agrees_v2", score=1.0 if passed else 0.0),
            threshold=1.0,
            tolerance=0.0,
            status="pass" if passed else "fail",
            reason="compared",
            assertion_id="renamed01",
        )


def test_an_aggregate_counts_a_renamed_score_rather_than_setting_it_aside() -> None:
    """Before this, every case landed in `suspended_excluded` with no case
    suspended, and the aggregate errored on an empty denominator."""
    suite = Suite(
        tenant="acme",
        environment="test",
        name="triage",
        assertions=[Renamed()],
        run_assertions=[Accuracy(over="agrees", threshold=0.5, tolerance=0.0)],
        cases=[Case(id=f"c{n}", label="positive") for n in range(1, 4)],
    )
    run = execute(
        suite,
        lambda case: Response(output="no" if case.id == "c3" else "yes"),
        created_at=CREATED,
    )
    (accuracy,) = run.aggregate
    assert accuracy.score.metadata["suspended_excluded"] == 0
    assert accuracy.score.metadata["considered"] == 3
    assert accuracy.score.score == pytest.approx(2 / 3)
    assert unreconciled(run) == ()


# --------------------------------------------------------------------------- #
# The clause has a ceiling: F-5 of the second 0.17.0 delta-pass
# --------------------------------------------------------------------------- #


def gapped(count: int) -> Run:
    """A run carrying `count` gap verdicts, built directly."""
    marked = Verdict(
        score=Score(name="agrees", score=None, metadata={UNRECONCILED: True}),
        threshold=1.0,
        status="error",
        reason="agrees was asked and no verdict came back",
        assertion_id="id-agrees",
    )
    return Run(
        tenant="acme",
        environment="test",
        suite="triage",
        config_hash="cfg",
        created_at=CREATED,
        results=tuple(
            CaseResult(case_id=f"case-{i:04}", verdicts=(marked,)) for i in range(count)
        ),
    )


def test_a_run_within_the_cap_names_every_gap_as_it_always_did() -> None:
    """The property the cap must not cost: the shape a dispatch defect actually
    produces is one to three gaps, and those sentences are unchanged."""
    clause = unreconciled_fact(unreconciled(gapped(3)), "en")
    assert "case-0000 · agrees" in clause
    assert "case-0001 · agrees" in clause
    assert "case-0002 · agrees" in clause
    assert "including" not in clause


def test_a_run_that_gaps_a_whole_suite_stops_naming_and_counts() -> None:
    """ADR 0027 §3 argued for the names and did not consider the thousand-gap
    run. Every pair joined, this clause leads `Headline.sentence`, which
    `compare_json` copies whole and the MCP `compare` tool returns — so the
    names went into a model's context and into the document a customer reads.
    Measured at 1 000 gaps before the cap: 20 131 characters."""
    gaps = unreconciled(gapped(1000))
    clause = unreconciled_fact(gaps, "en")

    assert "1000 checks" in clause
    assert len(clause) < 500, "the clause is bounded"
    assert clause.count("agrees") == NAMED_GAPS
    # The count is still there, which is what makes the naming a sample rather
    # than a silence.
    assert "case-0000 · agrees" in clause
    assert "case-0999" not in clause


def test_the_bounded_clause_bounds_the_headline_and_the_wire() -> None:
    """The consequence where it was actually paid."""
    run = gapped(1000)
    head = headline(compare(run, run), run, run, locale="en")
    payload = compare_json(compare(run, run), head, full=False)

    assert head.unreconciled == 1000
    assert len(head.sentence) < 1000
    assert len(json.dumps(payload)) < 4000


@pytest.mark.parametrize("locale", ["en", "it"])
def test_both_locales_have_the_capped_wording(locale: str) -> None:
    clause = unreconciled_fact(unreconciled(gapped(50)), locale)  # pyright: ignore[reportArgumentType]
    assert clause
    assert "{gaps}" not in clause and "{count}" not in clause


# --------------------------------------------------------------------------- #
# A reference that does not reconcile: F-10 of the second 0.17.0 delta-pass
# --------------------------------------------------------------------------- #


def test_the_reference_is_asked_the_same_question_as_the_run() -> None:
    """`unreconciled()` was called on the run at every site and on the baseline
    at none, so the refusal in `promote_baseline` was the only reader that ever
    asked — and it runs once, on the machine that promoted."""
    _suite, unreconciled_run = lost_one()
    clean = execute(a_suite(), answering, created_at=CREATED)

    assert compare(clean, unreconciled_run).reference_unreconciled == (
        ("c2", "agrees"),
    )
    assert compare(clean, clean).reference_unreconciled == ()


def test_the_headline_no_longer_claims_every_case_could_be_judged() -> None:
    """The sharpest symptom: the document said "Every case could be judged."
    about a comparison whose reference admits it did not know what it
    measured."""
    _suite, reference = lost_one()
    clean = execute(a_suite(), answering, created_at=CREATED)
    head = headline(compare(clean, reference), clean, reference, locale="en")

    assert head.reference_unreconciled == 1
    assert "The reference does not reconcile" in head.sentence
    assert "c2 · agrees" in head.sentence
    # And it says nothing about *this* run, which reconciled perfectly.
    assert "The run does not reconcile" not in head.sentence


def test_it_moves_no_exit_code() -> None:
    """Deliberate, and the reason is whose fault it is: this run may reconcile
    perfectly, and failing it for the state of a baseline promoted weeks ago
    would fail the wrong run. The clause withdraws the standing of the
    comparison, which is `config_changed`'s shape."""
    _suite, reference = lost_one()
    clean = execute(a_suite(), answering, created_at=CREATED)
    head = headline(compare(clean, reference), clean, reference, locale="en")

    assert head.worse is False
    assert exit_code(head) != EXIT_UNJUDGED or head.unjudged > 0


def test_the_reading_says_it_too_rather_than_contradicting_itself() -> None:
    """`explain` printed "Every case could be judged." three lines above
    "c2 · agrees could not be judged." — the second read off an errored delta
    whose error belonged to the reference, and nothing in the tally accounting
    for it."""
    _suite, reference = lost_one()
    clean = execute(a_suite(), answering, created_at=CREATED)
    lines = explain_text(facts(clean, compare(clean, reference)), locale="en")

    assert any("reference does not reconcile" in line for line in lines)


def test_the_count_crosses_on_the_wire_as_an_added_key() -> None:
    """An added key under `OUTPUT_VERSION`'s own rule, and a number rather than
    a name: a pipeline that wants to refuse a comparison standing on a
    measurement nobody can state now has something to refuse on."""
    _suite, reference = lost_one()
    clean = execute(a_suite(), answering, created_at=CREATED)
    comparison = compare(clean, reference)
    head = headline(comparison, clean, reference, locale="en")

    payload = compare_json(comparison, head, full=False)
    assert payload["reference_unreconciled"] == 1

    reading = explain_json(facts(clean, comparison), scope="comparison", exit_code=0)
    emitted = cast("list[dict[str, object]]", reading["facts"])
    kinds = {fact["kind"] for fact in emitted if fact["about"] == "run"}
    assert "reference_unreconciled" in kinds


# --------------------------------------------------------------------------- #
# What the prose now claims, pinned: F-6 and F-7 of the second 0.17.0 pass
# --------------------------------------------------------------------------- #
#
# These two changed **no behaviour** — they corrected docstrings that described
# a barrier and a wire route the code does not have. So they pass against
# 0.17.0 by construction, and they are here for the other direction: the next
# edit that makes either sentence true again has to come past them.


def test_an_errored_verdict_is_not_a_barrier_because_it_is_forced() -> None:
    """The old wording read as a guarantee: the marker "counts only on an
    errored verdict: on anything else it would be a key an assertion happened to
    write". But an errored verdict is not a state an assertion has to reach
    for — `Verdict` forces it, because a missing score may carry neither `pass`
    nor `fail`. So any assertion that declines to score produces exactly the
    shape the marker is read off."""
    for status in ("pass", "fail"):
        with pytest.raises(ValueError, match="missing score must produce"):
            Verdict(
                score=Score(name="agrees", score=None),
                threshold=1.0,
                status=status,  # pyright: ignore[reportArgumentType]
                reason="r",
                assertion_id="id-agrees",
            )


@pytest.mark.parametrize("value", [1, "true", "True", [], {}, {"unreconciled": True}])
def test_the_narrowing_that_does_work_is_the_identity_check(value: object) -> None:
    """`is True`, so nothing truthy claims a gap and nothing falsy hides one."""
    forged = Verdict(
        score=Score(name="agrees", score=None, metadata={UNRECONCILED: value}),
        threshold=1.0,
        status="error",
        reason="r",
        assertion_id="id-agrees",
    )
    run = Run(
        tenant="acme",
        environment="test",
        suite="triage",
        config_hash="cfg",
        created_at=CREATED,
        results=(CaseResult(case_id="c1", verdicts=(forged,)),),
    )
    assert unreconciled(run) == ()


def test_the_marker_does_not_cross_on_the_wire_unless_disclosed() -> None:
    """`travels()` admits a boolean, and the note on `UNRECONCILED` used to say
    so — but the run projection never consults `travels()`: it filters verdict
    metadata to the suite's `Disclosure` alone. So a run read through MCP
    carries `status: "error"` and nothing that tells a gap from a judge that
    failed. The *readings* do carry the count, because they are computed from
    the verdicts rather than projected from them."""
    _suite, run = lost_one()

    closed = run_document(run, Disclosure())
    assert UNRECONCILED not in json.dumps(closed)

    opened = run_document(run, Disclosure(score_metadata=frozenset({UNRECONCILED})))
    assert UNRECONCILED in json.dumps(opened)
