"""Where a project is, before its suite gates anything: one state, read from
`.digline/`, and the facts that put it there.

The person who opens `digline view` for the first time does not know what
comes next: record, name a suite, import, run, read the judge, add a
counterexample. Each of those is a fact the store already holds, so the next
step can be read rather than remembered. `where` reads it and returns **one**
state, the first in the order below that holds, with the numbers its sentence
needs. It renders nothing: the view lays the state out, and a command can
print it from the same value tomorrow without a second reading of the store.

The states, in the order they are asked, and the predicate each one is:

1. `nothing_recorded`: the tenant has no recording and the suite has never
   run. A suite whose cases were written by hand and that has run is past
   this, recorder or not.
2. `recording_off`: the switch file is there and says off, the tenant has
   recordings, the suite has never run, and nothing it recorded is waiting to
   be imported. An absent switch is not *off*: `DIGLINE_RECORD=1` records
   without one.
3. `unassigned`: every recording of the tenant named no suite.
4. `no_suite_yet`: the suite has recordings and declares no capture source,
   so nothing reads them as cases. Their shapes are counted
   (`shape_counts`), which needs no declaration.
5. `to_import`: the suite declares a capture source and has recordings made
   after the last import, or was never imported.
6. `never_run`: the suite has never run.
7. `judge_disagrees`: the newest run has a reviewed answer the judge
   contradicted, or a calibration case outside its band.
8. `green_without_red`: the newest run exits 0 and no run of the suite ever
   failed a check. A suite that cannot fail measures nothing.
9. `new_setup`: the setup in force first answered after the newest run,
   and some cases have answers under it and under an earlier setup: what
   changed can be read across setups before the suite runs again. Not
   *answers no reviewed answer was made under*: every recording after the
   last import holds the page at `to_import`, and an import that names one
   records the setup in force, so that state could never be reached.
10. `nothing_to_do`: the newest run exits 0.
11. `last_run_red`: the newest run exits 1 or 2 for a reason none of the
    states above names: `digline explain` reads it.

Never a verdict beyond the state: the numbers are counts the store holds, and
which state holds is the whole of the reading.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Literal

from digline.core.calibration import scale_lost
from digline.core.capture import capture_id
from digline.core.recording import Recording, instant_of
from digline.core.reviewed import contradicted
from digline.core.run import Run
from digline.host.importing import (
    Shape,
    imported_since,
    read_recordings,
    setups_in_force,
    shape_counts,
    split_recordings,
)
from digline.host.listing import suite_runs
from digline.host.recording import recorder_status
from digline.recorder import UNASSIGNED
from digline.run.suite import Suite
from digline.store.file_store import FileResultStore
from digline.wire.contract import run_exit_code

__all__ = ["RECORD_LINES", "STATES", "State", "Where", "where"]

#: Where a person starts recording, by the language of the application: the
#: page that says it, and three lines quoted from it as they stand there,
#: never rewritten here. `tests/test_where_page.py` holds each line to its
#: page. Java's are the writer and a hook copied into the project
#: (`record-java.md`); any other language goes through the proxy.
_PROXY: tuple[str, tuple[str, ...]] = (
    "record.md",
    (
        "$ digline record proxy --tenant acme",
        "    OPENAI_BASE_URL=http://127.0.0.1:8787/v1",
        "X-Digline-Suite: refunds",
    ),
)
RECORD_LINES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "Python",
        "record.md",
        (
            "import digline.recorder as recorder",
            'client = recorder.wrap(anthropic.Anthropic(), app="helpdesk", '
            'tenant="acme")',
            '    suite="category",',
        ),
    ),
    (
        "Java",
        "record-java.md",
        (
            'DiglineRecorder recorder = DiglineRecorder.development(root, "acme", '
            '"support");',
            "        .addInterceptor(new DiglineOkHttp(recorder))",
            'try (var suite = DiglineRecorder.suite("refunds")) {',
        ),
    ),
    (
        "Node",
        "record-node.md",
        (
            "$ digline record proxy --tenant acme",
            "$ ANTHROPIC_BASE_URL=http://127.0.0.1:8787 node app.mjs",
            '  defaultHeaders: { "X-Digline-Suite": "triage", '
            '"X-Digline-App": "node" },',
        ),
    ),
    ("any other", *_PROXY),
)

State = Literal[
    "nothing_recorded",
    "recording_off",
    "unassigned",
    "no_suite_yet",
    "to_import",
    "never_run",
    "judge_disagrees",
    "green_without_red",
    "new_setup",
    "nothing_to_do",
    "last_run_red",
]

#: Every state, in the order `where` asks them.
STATES: tuple[State, ...] = (
    "nothing_recorded",
    "recording_off",
    "unassigned",
    "no_suite_yet",
    "to_import",
    "never_run",
    "judge_disagrees",
    "green_without_red",
    "new_setup",
    "nothing_to_do",
    "last_run_red",
)


@dataclass(frozen=True, slots=True)
class Where:
    """One state and the facts that put the project in it.

    `count` is the number the state's sentence names: recordings, calls,
    reviewed answers, disagreements, answers or cases, by state. `suite` is
    the suite the state is about, `None` where it is about the tenant.
    `shapes` are the output shapes of `no_suite_yet`, each with its count.
    `run_key` and `exit_code` are the newest run's, where the state reads it;
    `last_import` the newest `examined_through` a case of the suite holds.
    """

    state: State
    tenant: str
    count: int = 0
    suite: str | None = None
    shapes: tuple[tuple[Shape, int], ...] = ()
    run_key: str | None = None
    exit_code: int | None = None
    last_import: str | None = None


def where(
    root: Path, tenant: str, *, suite: Suite | None, module: ModuleType | None
) -> Where:
    """The first state that holds for `tenant` under `root`, and `suite` when
    one is given; the module docstring lists them. With no suite, only the
    states read from the recordings can hold, and the last is `no_suite_yet`
    for the first suite name the recordings carry, or `nothing_recorded`.
    Reads, and writes nothing."""
    store = FileResultStore(root)
    everything, _unreadable = read_recordings(store, tenant)
    named = sorted({r.suite for r in everything} - {UNASSIGNED})
    runs = _runs(store, tenant, suite)

    if not everything and not runs:
        return Where("nothing_recorded", tenant, suite=_name(suite))

    mine = [] if suite is None else [r for r in everything if r.suite == suite.name]
    waiting = _waiting(root, tenant, suite, module, mine)
    [status] = recorder_status(root, tenant)
    if (
        everything
        and status.switch == "valid"
        and not status.on
        and not runs
        and not waiting
    ):
        return Where("recording_off", tenant, count=len(everything), suite=_name(suite))

    if everything and not named:
        return Where("unassigned", tenant, count=len(everything))

    if suite is None:
        return Where(
            "no_suite_yet",
            tenant,
            count=sum(1 for r in everything if r.suite == named[0]),
            suite=named[0],
            shapes=shape_counts(everything, named[0]),
        )
    if mine and suite.capture is None:
        return Where(
            "no_suite_yet",
            tenant,
            count=len(mine),
            suite=suite.name,
            shapes=shape_counts(everything, suite.name),
        )
    if waiting:
        return Where("to_import", tenant, count=waiting, suite=suite.name)

    reviewed = [case for case in suite.cases if case.reviewed_answer is not None]
    if not runs:
        return Where("never_run", tenant, count=len(reviewed), suite=suite.name)

    key, newest = runs[-1]
    code = run_exit_code(newest, declared=suite.declared())
    disagreements = len(contradicted(newest)) + len(scale_lost(newest))
    if disagreements:
        return Where(
            "judge_disagrees",
            tenant,
            count=disagreements,
            suite=suite.name,
            run_key=key,
            exit_code=code,
        )

    if code == 0 and not any(_failed(run) for _, run in runs):
        return Where(
            "green_without_red",
            tenant,
            count=len(newest.results),
            suite=suite.name,
            run_key=key,
            exit_code=code,
        )

    changed = _answers_from_a_new_setup(everything, suite.name, newest)
    if changed:
        return Where(
            "new_setup",
            tenant,
            count=changed,
            suite=suite.name,
            run_key=key,
            exit_code=code,
        )

    state: State = "nothing_to_do" if code == 0 else "last_run_red"
    return Where(
        state,
        tenant,
        count=len(newest.results),
        suite=suite.name,
        last_import=_last_import(suite),
        run_key=key,
        exit_code=code,
    )


def _name(suite: Suite | None) -> str | None:
    return None if suite is None else suite.name


def _runs(
    store: FileResultStore, tenant: str, suite: Suite | None
) -> list[tuple[str, Run]]:
    """The suite's readable runs, oldest first, or none without a suite."""
    if suite is None:
        return []
    listed = suite_runs(store, tenant, suite.name, mint=None)
    return sorted(listed.runs, key=lambda pair: (pair[1].created_at, pair[0]))


def _waiting(
    root: Path,
    tenant: str,
    suite: Suite | None,
    module: ModuleType | None,
    mine: list[Recording],
) -> int:
    """How many of the suite's recordings were made after its last import,
    all of them where it was never imported; 0 without a capture source,
    which has no import to be after."""
    if suite is None or suite.capture is None or not mine:
        return 0
    since, total = imported_since(root, suite, module, tenant)
    return total if since is None else since


def _answers_from_a_new_setup(
    everything: list[Recording], suite: str, newest: Run
) -> int:
    """How many answers the setup in force gave to cases that also have an
    answer under an earlier setup, where its first answer came after the
    newest run; 0 otherwise, and where a time is not recorded."""
    in_force = setups_in_force(everything, suite)
    eligible = split_recordings(everything, suite).eligible
    # Per form, as the listing reads it: an episode's setup against the
    # episodes, a single call's against the single calls.
    under = [r for r in eligible if r.setup_digest == in_force[r.id is not None]]
    dated = [r.recorded_at for r in under if r.recorded_at is not None]
    if not dated:
        return 0
    if min(instant_of(at) for at in dated) <= instant_of(newest.created_at):
        return 0
    before = {
        capture_id(r.case)
        for r in eligible
        if r.setup_digest != in_force[r.id is not None]
    }
    return sum(1 for r in under if capture_id(r.case) in before)


def _failed(run: Run) -> bool:
    """Whether any check of any case failed in `run`."""
    return any(
        verdict.status == "fail" for case in run.results for verdict in case.verdicts
    )


def _last_import(suite: Suite) -> str | None:
    marks = [
        str(case.metadata["examined_through"])
        for case in suite.cases
        if "examined_through" in case.metadata
    ]
    return max(marks, key=instant_of) if marks else None
