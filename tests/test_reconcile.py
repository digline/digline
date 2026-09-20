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

from dataclasses import dataclass
from pathlib import Path

import pytest

from digline.core import (
    UNRECONCILED,
    Accuracy,
    CallTotals,
    CaseResult,
    Contains,
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
from digline.run import Case, Response, Suite, execute
from digline.store import ErroredRunError, FileResultStore
from digline.wire import EXIT_UNJUDGED, compare_json, exit_code, explain_json

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
