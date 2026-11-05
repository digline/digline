"""The gate's marker: what a run in progress leaves in its tenant's directory,
so that a writer of recordings in another process can tell the gate's calls
from the application's. (ADR 0058, as amended 2026-11-05; ADR 0062)

In one process `running()` keeps the recorder from writing a run's calls at
all (#910). Out of it nothing can: an application behind `digline record
proxy`, or one that records through `recorders/java`, is called by the run's
`[target] http` and has no way to know the call came from the gate. So the
run says so where every writer looks:

    .digline/<tenant>/runs/.gate/<pid>-<run_id>.json
    {"run_id": "<key_of(created_at, config_hash)>", "pid": 4242,
     "started_at": "2026-11-05T12:30:00.123456+00:00", "suite": "refunds"}

Under `runs/`, which is ignored by git like everything a run leaves, and in a
directory whose name starts with a dot, which no listing of suites reads.

**Live is a recent modification time, not the content.** The run touches its
marker every `HEARTBEAT_SECONDS` and removes it when it ends, in error too,
with the directory where no other run's marker is left in it. A
marker not touched for `STALE_SECONDS` is a run that was killed before it
could remove it: ignored by every writer, and said by `digline record status`.
The pid is written for a person to read and is never checked, because a proxy
in a container does not share the run's process table.

**A writer that finds a live marker still records**, and marks the recording
`origin: "gate"` with the marker's `run_id`. Where two runs are live the call
cannot say which made it, and `run_id` is left out. A live marker that cannot
be read is a run in progress all the same: `origin` without `run_id`. The rule
errs towards the gate, because a recording marked as the gate's is kept apart
and never deleted, while one taken for the application's would be imported as
a case the gate asked itself.
"""

from __future__ import annotations

import json
import os
import threading
from collections.abc import Generator
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from pathlib import Path

from digline.host.environment import seconds_now
from digline.store.file_store import FileResultStore, PathRefusedError

__all__ = [
    "GATE_DIRECTORY",
    "HEARTBEAT_SECONDS",
    "STALE_SECONDS",
    "GateMarker",
    "GateMarkers",
    "gate_markers",
    "marking",
]

#: Where the markers are, under `.digline/<tenant>/`.
GATE_DIRECTORY = ("runs", ".gate")
#: How often a run in progress touches its marker.
HEARTBEAT_SECONDS = 30.0
#: How long a marker is live without being touched: four heartbeats missed.
STALE_SECONDS = 120.0


@dataclass(frozen=True, slots=True)
class GateMarker:
    """One marker as it was read. `run_id` is `None` where the file could not
    be read as a marker, which a live one still counts as."""

    run_id: str | None
    started_at: str | None
    suite: str | None
    #: Seconds since the run last touched it.
    age: float


@dataclass(frozen=True, slots=True)
class GateMarkers:
    live: tuple[GateMarker, ...]
    #: Left by a run that did not remove them, older than `STALE_SECONDS`.
    stale: tuple[GateMarker, ...]

    @property
    def run_id(self) -> str | None:
        """What a recording made now carries: the one live run's key, or
        `None` where there is none, more than one, or one not readable."""
        if len(self.live) != 1:
            return None
        return self.live[0].run_id


def directory_of(root: Path, tenant: str) -> Path:
    """`.digline/<tenant>/runs/.gate/`, the tenant checked as the store checks
    every name it is given, and the directory resolved and held inside the
    store, as the store holds every file it reads (`FileResultStore._inside`):
    a `.gate` that is a link out of `.digline/` is refused."""
    store = FileResultStore(root)
    # The name first, as a string: normalised and held under the store before
    # anything on disk is asked, the form CodeQL's path check reads as a guard
    # (alerts 133-135). Then the disk: a link out of the store is refused.
    base = os.path.normpath(store.root)
    candidate = os.path.normpath(
        os.path.join(store.tenant_dir(tenant), *GATE_DIRECTORY)
    )
    if not candidate.startswith(base + os.sep):
        raise PathRefusedError(f"the gate's markers at {candidate} are outside {base}")
    place = Path(candidate).resolve()
    if not place.is_relative_to(store.root.resolve()):
        raise PathRefusedError(
            f"the gate's markers at {place} are outside {store.root}: a link "
            "out of the store is not read or written"
        )
    return place


def gate_markers(root: Path, tenant: str) -> GateMarkers:
    """The markers in the tenant's directory, live and stale. Nothing there,
    or no directory, is none of either. A listing the filesystem refuses is
    none too: the reader is a writer of recordings, which never fails the
    application's call."""
    try:
        place = directory_of(root, tenant)
        entries = list(os.scandir(place))
    except (OSError, PathRefusedError):
        return GateMarkers((), ())
    now = seconds_now()
    live: list[GateMarker] = []
    stale: list[GateMarker] = []
    for entry in sorted(entries, key=lambda entry: entry.name):
        if entry.name.startswith(".") or not entry.name.endswith(".json"):
            continue
        path = Path(entry.path).resolve()
        if not path.is_relative_to(place):
            # A marker that is a link out of the directory is not read.
            continue
        try:
            age = now - entry.stat().st_mtime
        except OSError:
            continue
        marker = _read(path, age)
        (live if age <= STALE_SECONDS else stale).append(marker)
    return GateMarkers(tuple(live), tuple(stale))


def _read(path: Path, age: float) -> GateMarker:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return GateMarker(None, None, None, age)
    if not isinstance(document, dict):
        return GateMarker(None, None, None, age)
    fields = {
        key: value if isinstance(value, str) and value else None
        for key, value in document.items()  # pyright: ignore[reportUnknownVariableType]
        if key in ("run_id", "started_at", "suite")
    }
    return GateMarker(
        fields.get("run_id"), fields.get("started_at"), fields.get("suite"), age
    )


@contextmanager
def marking(
    root: Path, tenant: str, *, run_id: str, started_at: str, suite: str
) -> Generator[None]:
    """A marker for as long as the block runs, touched by a thread every
    `HEARTBEAT_SECONDS` and removed when the block ends, however it ends.

    Written whole under a name no reader reads and moved into place, so a
    writer never reads half of one. A run that cannot write its marker stops
    before its first call: the gate measuring an application that records
    itself would otherwise file its calls as the application's, silently.
    """
    place = directory_of(root, tenant)
    pid = os.getpid()
    path = place / f"{pid}-{run_id}.json"
    partial = place / f".{path.name}.partial"
    text = (
        json.dumps(
            {"run_id": run_id, "pid": pid, "started_at": started_at, "suite": suite}
        )
        + "\n"
    )
    # Twice at most: another run ending may remove the directory, empty,
    # between this one making it and writing into it.
    for attempt in (1, 2):
        place.mkdir(parents=True, exist_ok=True)
        try:
            partial.write_text(text, encoding="utf-8")
            break
        except FileNotFoundError:
            if attempt == 2:
                raise
    os.replace(partial, path)
    stop = threading.Event()

    def beat() -> None:
        while not stop.wait(HEARTBEAT_SECONDS):
            # A beat that fails leaves the marker to go stale, which is what
            # a run that died would leave: never a reason to stop the run.
            with suppress(OSError):
                os.utime(path)

    heart = threading.Thread(target=beat, name="digline-gate-marker", daemon=True)
    heart.start()
    try:
        yield
    finally:
        stop.set()
        heart.join()
        with suppress(FileNotFoundError):
            path.unlink()
        # Left empty, the directory goes too, so a run leaves nothing behind;
        # another run's marker in it keeps it, which is the refusal here.
        with suppress(OSError):
            place.rmdir()
