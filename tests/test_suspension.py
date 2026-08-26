"""Suspension: declared, visible, and payload.

A case set aside without a trace is coverage that quietly shrank, and the reader
in world 3 has no code with which to notice. So the reason is mandatory, the run
records it, and it travels through store and report — redacted at a boundary
like any other thing a developer wrote about real data.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from digline.core import (
    REDACTED,
    CaseResult,
    Contains,
    Run,
    Score,
    Verdict,
    compare,
    config_hash,
    redact,
    run_from_json,
    run_to_json,
)
from digline.report import headline, render_html
from digline.run import Case, Response, Suite, execute
from digline.store import FileResultStore

CREATED = "2026-01-01T00:00:00+00:00"
WHY = "fails on the Rossi account until ticket 412 is closed"


def a_suite(*cases: Case) -> Suite:
    return Suite(
        tenant="acme",
        environment="test",
        name="qa",
        assertions=[Contains(needle="Rome")],
        cases=cases,
    )


def answering(case: Case) -> Response:
    return Response(output="Rome", cost_usd=0.01)


# --------------------------------------------------------------------------- #
# The declaration
# --------------------------------------------------------------------------- #


def test_a_suspension_without_a_reason_is_refused() -> None:
    """Refused for the same cause as an empty `Verdict.reason`: nobody can
    review it."""
    with pytest.raises(ValueError, match="without a stated reason"):
        Case(id="one", suspended="")


def test_a_case_result_cannot_be_both_suspended_and_judged() -> None:
    with pytest.raises(ValueError, match="carries verdicts"):
        CaseResult(
            case_id="one",
            verdicts=(
                Verdict(
                    score=Score(name="x", score=1.0),
                    threshold=1.0,
                    status="pass",
                    reason="r",
                ),
            ),
            suspended=WHY,
        )


# --------------------------------------------------------------------------- #
# The driver skips, the run records
# --------------------------------------------------------------------------- #


def test_a_suspended_case_is_not_evaluated_but_is_recorded() -> None:
    """The skip belongs to the driver, per ADR 0001: an assertion is never asked
    a question it then has to decline."""
    suite = a_suite(Case(id="live"), Case(id="parked", suspended=WHY))
    run = execute(suite, answering, created_at=CREATED)

    by_case = {c.case_id: c for c in run.results}
    assert set(by_case) == {"live", "parked"}
    assert by_case["parked"].verdicts == ()
    assert by_case["parked"].suspended == WHY
    assert len(by_case["live"].verdicts) == 1


def test_the_target_is_never_called_for_a_suspended_case() -> None:
    seen: list[str] = []

    def recording(case: Case) -> Response:
        seen.append(case.id)
        return Response(output="Rome", cost_usd=0.01)

    execute(
        a_suite(Case(id="live"), Case(id="parked", suspended=WHY)),
        recording,
        created_at=CREATED,
    )
    assert seen == ["live"]


def test_a_suspended_case_survives_the_round_trip() -> None:
    run = execute(
        a_suite(Case(id="parked", suspended=WHY)), answering, created_at=CREATED
    )
    restored = run_from_json(run_to_json(run))
    assert restored.results[0].suspended == WHY
    assert restored.results[0].verdicts == ()


# --------------------------------------------------------------------------- #
# compare(): no new rule
# --------------------------------------------------------------------------- #


def test_suspending_a_case_that_had_a_baseline_shows_as_missing() -> None:
    """No new rule in `compare()`. The verdicts stopped being produced, so they
    are missing — and it is right that this is visible rather than silent."""
    covered = a_suite(Case(id="one"))
    baseline = execute(covered, answering, created_at=CREATED)

    parked = a_suite(Case(id="one", suspended=WHY))
    run = execute(parked, answering, created_at="2026-01-02T00:00:00+00:00")

    assert compare(run, baseline).counts == {"missing": 1}


# --------------------------------------------------------------------------- #
# The headline and the report
# --------------------------------------------------------------------------- #


def test_the_headline_counts_suspended_cases() -> None:
    suite = a_suite(Case(id="live"), Case(id="parked", suspended=WHY))
    run = execute(suite, answering, created_at=CREATED)
    head = headline(compare(run, run), run, run, locale="en")
    assert head.suspended == 1
    assert "1 case is suspended" in head.sentence


def test_a_suspended_case_is_not_counted_as_unjudged() -> None:
    """Different facts, different actions: unjudged means the suite tried and
    failed, suspended means someone decided not to try."""
    suite = a_suite(Case(id="parked", suspended=WHY))
    run = execute(suite, answering, created_at=CREATED)
    head = headline(compare(run, run), run, run, locale="en")
    assert head.suspended == 1
    assert head.unjudged == 0
    assert head.worse is False


def test_the_report_names_the_suspended_case_and_its_reason() -> None:
    suite = a_suite(Case(id="live"), Case(id="parked", suspended=WHY))
    run = execute(suite, answering, created_at=CREATED)
    document = render_html(compare(run, run), run, run, locale="en")
    assert "What is set aside" in document
    assert "parked" in document
    assert WHY in document


def test_the_reason_is_payload_and_does_not_survive_redaction() -> None:
    """A developer writes "fails on the Rossi account": that is the customer's
    data in a sentence, and it is redacted like any judge's reason."""
    suite = a_suite(Case(id="parked", suspended=WHY))
    run = execute(suite, answering, created_at=CREATED)
    hidden = redact(run)

    assert hidden.results[0].suspended == REDACTED
    document = run_to_json(run, redacted=True)
    assert "Rossi" not in document
    assert WHY not in document
    # The *fact* still travels: coverage shrank and a reader must see it.
    assert '"suspended": true' in document
    assert "suspended_reason" not in document


def test_the_redacted_report_shows_the_case_without_the_reason() -> None:
    suite = a_suite(Case(id="parked", suspended=WHY))
    run = redact(execute(suite, answering, created_at=CREATED))
    document = render_html(compare(run, run), run, run, locale="en")
    assert "parked" in document
    assert "Rossi" not in document
    assert REDACTED not in document
    assert "Not included in this report" in document


# --------------------------------------------------------------------------- #
# The point of the whole thing
# --------------------------------------------------------------------------- #


def test_a_suite_with_a_suspended_case_can_be_promoted(tmp_path: Path) -> None:
    """The reason suspension exists. Before it, a suite holding one unstable
    case had no baseline at all until someone deleted the case — so the fix for
    an inconvenient failure was to make it disappear."""
    suite = a_suite(Case(id="live"), Case(id="parked", suspended=WHY))
    run = execute(suite, answering, created_at=CREATED)
    store = FileResultStore(tmp_path)

    promoted = store.promote_baseline(
        store.write_run(run), config_hash(suite.assertions)
    )
    assert promoted.results[1].suspended == WHY

    stored = store.read_baseline("acme", "qa")
    assert stored is not None
    assert [c.case_id for c in stored.results] == ["live", "parked"]


def test_a_run_marked_redacted_may_not_keep_a_suspension_reason() -> None:
    """Verified, not believed — the same treatment as a verdict's reason."""
    with pytest.raises(ValueError, match="still carries its suspension reason"):
        Run(
            tenant="acme",
            environment="test",
            suite="qa",
            config_hash="h",
            created_at=CREATED,
            results=(CaseResult("parked", (), WHY),),
            redacted=True,
        )
