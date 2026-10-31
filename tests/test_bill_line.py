"""The bill line: three facts, each with its own qualifier.

`usage_lines` says what a side of the run consumed as three facts — the calls,
the counts, the cost — and puts each qualifier beside the fact it qualifies,
only where it carries information. The forms are derived from `CallTotals`
alone: nothing here needs a field the run document does not record.

The regression this file holds is F-1 of the delta-pass over 1.0.2: a known
sum above zero and below what six decimals can show printed `0.000000 USD`,
which read as a run that cost nothing. A figure that cannot be shown at the
line's precision now says so.
"""

from __future__ import annotations

import pytest

from digline.core import Contains
from digline.core.run import NO_CALLS, CallTotals, RunUsage
from digline.run import Case, Response, Suite, execute
from digline.targets.pricing import Usage
from digline.wire import usage_lines

CREATED = "2026-10-31T09:00:00+00:00"


def line(**fields: object) -> CallTotals:
    """A line with both markers recorded, as the driver writes it; a field
    given here overrides."""
    base: dict[str, object] = {"every_call_seen": True, "every_cost_known": True}
    return CallTotals(**{**base, **fields})  # pyright: ignore[reportArgumentType]


def said(totals: CallTotals, side: str = "target") -> str:
    usage = (
        RunUsage(target=totals, judge=NO_CALLS)
        if side == "target"
        else RunUsage(target=NO_CALLS, judge=totals)
    )
    (only,) = usage_lines(usage)
    return only


TOKENS = Usage(120, 40)

#: Every form the line takes where calls answered, by the facts that make it.
FORMS = [
    # The counts: the totals are the fact, how many calls they are from is
    # what qualifies them, and only when it is not all of them.
    (
        line(calls=3, counted=3, tokens=TOKENS, spent_usd=0.00899),
        "target: 3 calls · counts: 120 in / 40 out · cost: 0.008990 USD",
    ),
    (
        line(calls=3, counted=2, tokens=TOKENS, spent_usd=0.00899),
        (
            "target: 3 calls · counts: 120 in / 40 out, from 2 of 3 calls"
            " · cost: 0.008990 USD"
        ),
    ),
    (
        line(calls=2, counted=0, spent_usd=0.00899),
        "target: 2 calls · counts: none · cost: 0.008990 USD",
    ),
    # The cost, every call priced.
    (
        line(calls=2, spent_usd=4e-7),
        "target: 2 calls · counts: none · cost: under 0.000001 USD",
    ),
    (
        line(calls=2, spent_usd=0.0),
        "target: 2 calls · counts: none · cost: 0.000000 USD",
    ),
    # The cost, not every call priced: a known sum is a lower bound.
    (
        line(calls=3, spent_usd=0.00899, every_cost_known=False),
        (
            "target: 3 calls · counts: none"
            " · cost: at least 0.008990 USD, not every call priced"
        ),
    ),
    (
        line(calls=2, spent_usd=4e-7, every_cost_known=False),
        (
            "target: 2 calls · counts: none"
            " · cost: more than zero, not every call priced"
        ),
    ),
    (
        line(calls=2, spent_usd=0.0, every_cost_known=False),
        "target: 2 calls · counts: none · cost: not known",
    ),
    # The cost, completeness not recorded: a third state, about the record.
    (
        line(calls=2, spent_usd=0.00899, every_cost_known=None),
        (
            "target: 2 calls · counts: none"
            " · cost: 0.008990 USD, completeness not recorded"
        ),
    ),
    (
        line(calls=2, spent_usd=4e-7, every_cost_known=None),
        (
            "target: 2 calls · counts: none"
            " · cost: under 0.000001 USD, completeness not recorded"
        ),
    ),
    (
        line(calls=2, spent_usd=0.0, every_cost_known=None),
        "target: 2 calls · counts: none · cost: completeness not recorded",
    ),
    # The calls: the marker of whether every call was seen goes beside them.
    (
        line(calls=3, spent_usd=0.00899, every_call_seen=False),
        "target: 3 calls, not every call seen · counts: none · cost: 0.008990 USD",
    ),
    (
        line(calls=3, spent_usd=0.00899, every_call_seen=None),
        (
            "target: 3 calls, completeness not recorded · counts: none"
            " · cost: 0.008990 USD"
        ),
    ),
    (
        line(calls=1, counted=1, tokens=TOKENS, spent_usd=0.00899),
        "target: 1 call · counts: 120 in / 40 out · cost: 0.008990 USD",
    ),
]


@pytest.mark.parametrize(("totals", "expected"), FORMS, ids=[e for _, e in FORMS])
def test_each_form_of_the_line(totals: CallTotals, expected: str) -> None:
    assert said(totals) == expected


@pytest.mark.parametrize(("totals", "expected"), FORMS, ids=[e for _, e in FORMS])
def test_the_judge_line_takes_the_same_forms(totals: CallTotals, expected: str) -> None:
    assert said(totals, side="judge") == expected.replace("target:", "judge:", 1)


@pytest.mark.parametrize(
    "spent",
    # 5e-7 is among them: as a float it is just below half a millionth,
    # and six decimals round it to zero.
    [1e-12, 1e-7, 4e-7, 4.9e-7, 5e-7],
)
@pytest.mark.parametrize("known", [True, None])
def test_a_figure_that_cannot_be_shown_says_so(
    spent: float, known: bool | None
) -> None:
    """The other half of F-1. Where the known sum is above zero and reads
    `0.000000` at six decimals, the line says `under 0.000001 USD` instead
    of printing a zero that is not one. The threshold is the line's own
    precision: the figure is shown exactly when its six decimals are not
    all zero."""
    text = said(line(calls=2, spent_usd=spent, every_cost_known=known))
    assert "cost: under 0.000001 USD" in text, text
    assert "0.000000" not in text, text


@pytest.mark.parametrize(
    "spent",
    [1e-12, 1e-7, 4e-7, 4.9e-7, 5e-7],
)
def test_an_unshowable_sum_beside_an_unpriced_call_states_no_ceiling(
    spent: float,
) -> None:
    """F-1. Not every call was priced, so the bill has a floor and no known
    ceiling: *under 0.000001 USD* would state one. Six decimals cannot show
    the floor, so the line says the cost is more than zero, with no figure,
    and never `0.000000`, which reads as a run that cost nothing."""
    text = said(line(calls=2, spent_usd=spent, every_cost_known=False))
    assert text.endswith("cost: more than zero, not every call priced"), text
    assert "USD" not in text, text


@pytest.mark.parametrize("spent", [5.0000001e-7, 6e-7, 1e-6])
def test_a_figure_that_can_be_shown_is_shown(spent: float) -> None:
    """The control: at and above the first figure six decimals can show,
    the figure is printed, and no *under* is said."""
    text = said(line(calls=2, spent_usd=spent))
    assert f"cost: {spent:.6f} USD" in text, text
    assert f"{spent:.6f}" != "0.000000"
    assert "under" not in text, text


def test_no_qualifier_is_said_where_it_carries_nothing() -> None:
    """A whole line of whole facts has no qualifier at all: no *of*, no
    parenthesis, no clause."""
    text = said(line(calls=3, counted=3, tokens=TOKENS, spent_usd=0.00899))
    assert " of " not in text, text
    assert "(" not in text, text
    assert "," not in text, text


# The F-1 probe, `bill_tiny_suite.py` of the delta-pass over 1.0.2, through
# the driver: one call priced below half a millionth of a dollar, one whose
# cost nobody states.


def _tiny_run() -> RunUsage:
    def target(case: Case) -> Response:
        if case.id == "priced":
            return Response(output="hello", cost_usd=4e-7)
        return Response(output="hello")

    suite = Suite(
        tenant="probe",
        environment="dev",
        name="tiny",
        assertions=[Contains(needle="hello")],
        cases=[Case(id="priced"), Case(id="unpriced")],
    )
    usage = execute(suite, target, created_at=CREATED).usage
    assert usage is not None
    return usage


def test_the_f1_probe_does_not_read_as_a_run_that_cost_nothing() -> None:
    usage = _tiny_run()
    assert usage.target.spent_usd == pytest.approx(4e-7)
    assert usage.target.every_cost_known is False
    (text,) = usage_lines(usage)
    assert text == (
        "target: 2 calls · counts: none · cost: more than zero, not every call priced"
    )
