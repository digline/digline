"""`compare()` refuses a pair whose `projected` differs. (Delta-pass over
0.25.0, F-1)

A projected document names its cases by token, and a document in clear names
them by text. Paired across the two, no case meets its counterpart: each one
reads as `new` plus `missing`, which exits 0. So a regression compared against
the projected reference disappeared, and the headline said nothing got worse:
fixed decision 3's vacuous green, reached through pairing. The refusal sits
beside the tenant's, for the same reason: the arithmetic is valid and the
reading is nonsense.

**What this does not close.** Two projections minted from different tables
fail the same way, and both declare `projected`. Nothing in a projected
document says which table minted it, so nothing here can tell them apart.
That is ADR 0036's question, and it is open: the last test below is held as
an expected failure, so that it turns red the day it is answered.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from digline.core import DifferentRegimesError, Run, compare, project, redact
from digline.host import REFUSALS
from digline.report import headline
from digline.wire import exit_code
from test_projection import Table, promoted


def worse(reference: Run) -> Run:
    """The reference with its first case's checks failing: one real regression.
    Still stamped, because the software house compares a projection of the
    current run too, and only a promoted run projects."""
    first = reference.results[0]
    failing = tuple(
        replace(v, score=replace(v.score, score=0.1), status="fail")
        for v in first.verdicts
    )
    return replace(
        reference,
        results=(replace(first, verdicts=failing), *reference.results[1:]),
    )


def gate(run: Run, baseline: Run) -> int:
    return exit_code(
        headline(compare(run, baseline), run, baseline, locale="en", declared=None)
    )


def test_the_regression_fails_the_gate_in_clear() -> None:
    """The control: without it, a refusal below proves nothing about a
    regression that was there to hide."""
    reference = promoted()
    assert gate(worse(reference), reference) == 1


def test_a_clear_run_against_the_projected_reference_is_refused() -> None:
    """Was: `new` plus `missing`, exit 0, *Nothing got worse*."""
    reference = promoted()
    with pytest.raises(DifferentRegimesError, match="projected"):
        compare(worse(reference), project(reference, Table()))


def test_a_projected_run_against_a_clear_reference_is_refused() -> None:
    reference = promoted()
    with pytest.raises(DifferentRegimesError):
        compare(project(worse(reference), Table()), reference)


def test_redacting_the_clear_side_does_not_make_it_comparable() -> None:
    """Redaction removes payload and keeps names. The names are what pair."""
    reference = promoted()
    with pytest.raises(DifferentRegimesError):
        compare(redact(worse(reference)), project(reference, Table()))


def test_two_projections_from_one_table_keep_the_regression() -> None:
    """The comparison the software house is meant to run, and still does."""
    reference = promoted()
    table = Table()
    assert gate(project(worse(reference), table), project(reference, table)) == 1


def test_the_refusal_is_classified() -> None:
    assert DifferentRegimesError in REFUSALS


@pytest.mark.xfail(
    strict=True,
    reason="ADR 0036's open question: a projected document does not say which "
    "table minted it, so two projections from different tables pair as new "
    "plus missing and exit 0",
)
def test_two_projections_from_different_tables_keep_the_regression() -> None:
    reference = promoted()
    assert gate(project(worse(reference), Table()), project(reference, Table())) == 1
