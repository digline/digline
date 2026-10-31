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

# --------------------------------------------------------------------------- #
# The table (P-1206d, its two open cells decided by P-1206e), cell by cell
# --------------------------------------------------------------------------- #
#
# The strings below are the specification, written out by hand: the test does
# not derive them, so a rule the code gets wrong cannot agree with itself here.
# T, F and N are a marker true, false and not recorded.

Marker = bool | None
MARKERS: dict[str, Marker] = {"T": True, "F": False, "N": None}

#: The calls: their own marker only.
CALLS = {
    "T": "3 calls",
    "F": "at least 3 calls, not every call seen",
    "N": "at least 3 calls, completeness not recorded",
}

#: How many calls reported counts, out of the 3.
COUNTED = {"all": 3, "part": 2, "none": 0}

#: The counts: inherited from the calls, and a scope already named is not
#: joined by a second. `none` is the absence of a measurement.
COUNTS = {
    ("all", "T"): "120 in / 40 out",
    ("all", "F"): "120 in / 40 out on the calls seen",
    ("all", "N"): "120 in / 40 out on the calls seen",
    ("part", "T"): "120 in / 40 out, from 2 of 3 calls",
    ("part", "F"): "120 in / 40 out, from 2 of 3 calls",
    ("part", "N"): "120 in / 40 out, from 2 of 3 calls",
    ("none", "T"): "none",
    ("none", "F"): "none",
    ("none", "N"): "none",
}

#: The three states of the figure.
SPENT = {"shown": 0.00899, "unshown": 4e-7, "zero": 0.0}

#: The cost where every call was seen, by its own marker and the figure.
_COST_SEEN = {
    ("T", "shown"): "0.008990 USD",
    ("T", "unshown"): "under 0.000001 USD",
    ("T", "zero"): "0.000000 USD",
    ("F", "shown"): "at least 0.008990 USD, not every call priced",
    ("F", "unshown"): "more than zero, not every call priced",
    ("F", "zero"): "not known",
    ("N", "shown"): "at least 0.008990 USD, completeness not recorded",
    ("N", "unshown"): "more than zero, completeness not recorded",
    ("N", "zero"): "completeness not recorded",
}

#: The cost whose only incompleteness is the calls': exact on a named scope.
_COST_INHERITED = {
    "shown": "0.008990 USD on the calls seen",
    "unshown": "under 0.000001 USD on the calls seen",
    "zero": "0.000000 USD on the calls seen",
}

#: The cost, by its own marker, the calls' marker and the figure's state.
#: Where both are incomplete, its own marker wins.
COST = {
    (own, seen, state): (
        _COST_SEEN[(own, state)]
        if seen == "T" or own != "T"
        else _COST_INHERITED[state]
    )
    for own in ("T", "F", "N")
    for seen in ("T", "F", "N")
    for state in ("shown", "unshown", "zero")
}

CELLS = [
    (seen, own, counted, state)
    for seen in MARKERS
    for own in MARKERS
    for counted in COUNTED
    for state in SPENT
]


def _cell(seen: str, own: str, counted: str, state: str) -> CallTotals:
    return CallTotals(
        calls=3,
        counted=COUNTED[counted],
        tokens=TOKENS if COUNTED[counted] else Usage(0, 0),
        spent_usd=SPENT[state],
        every_call_seen=MARKERS[seen],
        every_cost_known=MARKERS[own],
    )


@pytest.mark.parametrize("side", ["target", "judge"])
@pytest.mark.parametrize(
    ("seen", "own", "counted", "state"),
    CELLS,
    ids=[f"seen={s}-cost={o}-counted={c}-{f}" for s, o, c, f in CELLS],
)
def test_every_cell_of_the_table(
    side: str, seen: str, own: str, counted: str, state: str
) -> None:
    """Each combination of the three markers, the counts and the figure, on
    both sides, against the string the table gives it."""
    expected = (
        f"{side}: {CALLS[seen]} · counts: {COUNTS[(counted, seen)]}"
        f" · cost: {COST[(own, seen, state)]}"
    )
    assert said(_cell(seen, own, counted, state), side=side) == expected


def test_the_table_is_whole() -> None:
    """Every cell has a string: 3 x 3 x 3 x 3."""
    assert len(CELLS) == 81
    assert len(COST) == 27 and len(COUNTS) == 9 and len(CALLS) == 3


def test_a_line_with_one_call_says_call() -> None:
    assert said(_cell("T", "T", "all", "shown")).startswith("target: 3 calls ")
    one = CallTotals(
        calls=1,
        counted=1,
        tokens=TOKENS,
        spent_usd=0.00899,
        every_call_seen=True,
        every_cost_known=True,
    )
    assert said(one) == "target: 1 call · counts: 120 in / 40 out · cost: 0.008990 USD"


@pytest.mark.parametrize(
    "spent",
    # 5e-7 is among them: as a float it is just below half a millionth,
    # and six decimals round it to zero.
    [1e-12, 1e-7, 4e-7, 4.9e-7, 5e-7],
)
def test_a_figure_that_cannot_be_shown_says_so(spent: float) -> None:
    """The other half of F-1. Every call was priced, so the bill's ceiling is
    known: where the sum is above zero and reads `0.000000` at six decimals,
    the line says `under 0.000001 USD` instead of printing a zero that is not
    one. The threshold is the line's own precision: the figure is shown
    exactly when its six decimals are not all zero."""
    text = said(line(calls=2, spent_usd=spent))
    assert "cost: under 0.000001 USD" in text, text
    assert "0.000000" not in text, text


@pytest.mark.parametrize(
    ("known", "clause"),
    [(False, "not every call priced"), (None, "completeness not recorded")],
)
@pytest.mark.parametrize(
    "spent",
    [1e-12, 1e-7, 4e-7, 4.9e-7, 5e-7],
)
def test_an_unshowable_sum_beside_an_unpriced_call_states_no_ceiling(
    spent: float, known: bool | None, clause: str
) -> None:
    """F-1. Not every call was priced, or that was not recorded, so the bill
    has a floor and no known ceiling: *under 0.000001 USD* would state one.
    Six decimals cannot show the floor, so the line says the cost is more
    than zero, with no figure, and never `0.000000`, which reads as a run
    that cost nothing."""
    text = said(line(calls=2, spent_usd=spent, every_cost_known=known))
    assert text.endswith(f"cost: more than zero, {clause}"), text
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
