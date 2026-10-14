"""`run_exit_code`: the first round's exit code, as one function. (#318)

The rule was written inline twice, behind `digline report` and `digline
explain`. Written from the mistake each test prevents: the first round
answering `1`, which needs a relation it does not have; a cause of `2` that
the first round misses; and the restricted rule drifting from `exit_code`,
which is the rule it restricts.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

import pytest
from tests.test_project_served import unpromoted
from tests.test_projection import Table, promoted

from digline.core import NOTHING_EXTRA, Run, compare, project_served, redact
from digline.report import headline
from digline.wire import EXIT_OK, EXIT_UNJUDGED, EXIT_WORSE, exit_code, run_exit_code


def clean() -> Run:
    """Nothing errored, every band held: the fixture as a reference has it."""
    return replace(promoted(), promoted_at="")


def errored() -> Run:
    """One case could not be judged."""
    return unpromoted()


def band_lost(run: Run) -> Run:
    """`run` with its calibration case scored outside its band."""
    calibration = run.results[1]
    assert calibration.calibration is not None
    outside = replace(
        calibration,
        verdicts=tuple(
            replace(v, score=replace(v.score, score=0.95)) for v in calibration.verdicts
        ),
    )
    return replace(run, results=(run.results[0], outside, *run.results[2:]))


RUNS = {
    "clean": clean(),
    "errored": errored(),
    "band lost": band_lost(clean()),
    "errored and band lost": band_lost(errored()),
}


def test_a_clean_first_round_proceeds() -> None:
    assert run_exit_code(clean(), declared=None) == EXIT_OK


def test_a_case_that_could_not_be_judged_stops_it() -> None:
    assert run_exit_code(errored(), declared=None) == EXIT_UNJUDGED


def test_a_lost_scale_stops_it_on_its_own() -> None:
    """No case errored here: the band alone is the cause."""
    assert run_exit_code(band_lost(clean()), declared=None) == EXIT_UNJUDGED


def test_a_first_round_never_says_worse() -> None:
    assert EXIT_WORSE not in {
        run_exit_code(run, declared=None) for run in RUNS.values()
    }


def as_read(run: Run) -> Run:
    return run


def redacted(run: Run) -> Run:
    return redact(run, NOTHING_EXTRA)


def served(run: Run) -> Run:
    return project_served(run, Table())


SHAPES: dict[str, Callable[[Run], Run]] = {
    "as read": as_read,
    "redacted": redacted,
    "served": served,
}


@pytest.mark.parametrize("shape", list(SHAPES))
@pytest.mark.parametrize("name", list(RUNS))
def test_it_is_exit_code_on_a_comparison_with_no_relation_in_it(
    name: str, shape: str
) -> None:
    """A run compared with itself has nothing worse, no canary moved and no
    pin drifted, so `exit_code` answers there on the run's facts alone, and
    that is the question `run_exit_code` answers without a reference. In
    clear, redacted and projected, as `report --redacted` and a served page
    hand it."""
    run = SHAPES[shape](RUNS[name])
    head = headline(compare(run, run), run, run, locale="en", declared=None)
    assert run_exit_code(run, declared=None) == exit_code(head)
