"""The causes of exit code 2, written once for every reader of them.

`2` says the numbers beside it are not what they look like: a case could not be
judged, a calibration case left its band, a pinned file drifted, a pin lost its
path, or the run judged nothing. Two readers ask for the set and need it to be
the same set. `exit_code()` turns it into a number, behind a regression that
outranks it; and promotion refuses a run while any cause holds, **whatever the
number says**, because a regression beside a drifted pin exits 1 and the drift
is no less there. (ADR 0053)

Here and not beside either reader, because they sit in two layers that cannot
import each other: `exit_code` is in `wire`, promotion's write step in `store`,
and `core` is the one layer both may import (`tests/test_layering.py`). Pure,
like everything here: no I/O, no clock.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from digline.core.calibration import scale_lost
from digline.core.declared import Declared, nothing_judged

if TYPE_CHECKING:
    from digline.core.compare import Comparison
    from digline.core.run import Run

__all__ = ["CauseOfTwo", "causes_of_two", "pins_implicated", "unjudged_cases"]

#: A cause of exit code 2, named as the headline's own field for it is named,
#: so the list on the wire reads as a list of keys beside it.
type CauseOfTwo = Literal[
    "unjudged", "scale_lost", "pinned_drifted", "pinned_lost", "nothing_judged"
]


def unjudged_cases(run: Run) -> int:
    """How many cases this run could not judge.

    Counted from the run and from nothing else, which is what makes it usable
    without a reference: a case the suite could not judge is a fact about the
    harness, true whether or not there is anything to compare against. It is
    what `digline report` exits on when there is no baseline.

    Cases, not verdicts, because that is what every sentence built on it says.

    In `core` since ADR 0053, which needed it beside the other causes of 2;
    `digline.report` still exports it.
    """
    return sum(
        1
        for case in run.results
        if any(verdict.status == "error" for verdict in case.verdicts)
    )


def causes_of_two(
    run: Run, comparison: Comparison | None, *, declared: Declared | None
) -> tuple[CauseOfTwo, ...]:
    """Every cause of exit code 2 that holds, in the order `exit_code` has
    always read them. Empty when none does.

    `comparison` is `run` held against its reference, or `None` where there is
    none — a first round, or a first promotion. The two pin causes are
    relations, so without a reference they cannot hold. `declared` is the
    suite's declaration, for `nothing_judged`'s reason: a run document does not
    carry it. (ADR 0049 §3)

    **Causes, not the code.** Whether a regression outranks them is
    `exit_code`'s question, and promotion does not ask it. (ADR 0053)
    """
    causes: list[CauseOfTwo] = []
    if unjudged_cases(run):
        causes.append("unjudged")
    if scale_lost(run):
        causes.append("scale_lost")
    if comparison is not None and comparison.pinned_drifted:
        causes.append("pinned_drifted")
    if comparison is not None and comparison.pinned_lost:
        causes.append("pinned_lost")
    if nothing_judged(run, declared):
        causes.append("nothing_judged")
    return tuple(causes)


def pins_implicated(comparison: Comparison | None) -> tuple[str, ...]:
    """The paths behind the two pin causes, sorted: what a promotion has to
    name to accept them. Empty when neither holds.

    A drifted pin implicates its own path. A lost pin implicates both halves:
    the path the reference pinned and the run no longer records, and the pinned
    path with no reference, because nothing in either document says whether one
    became the other, so accepting one is accepting both. (ADR 0051 §3,
    ADR 0053)
    """
    if comparison is None:
        return ()
    paths = set(comparison.pinned_changed)
    if comparison.pinned_lost:
        paths.update(comparison.pinned_gone, comparison.pinned_unreferenced)
    return tuple(sorted(paths))
