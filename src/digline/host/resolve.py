"""Naming a stored run, and finding the baseline. Resolution, never shape.

Both front ends need these and neither should grow its own: `latest` resolved
two ways is `latest` meaning two things. They take any `ResultStore` and raise
`UsageError`, which is why they are here rather than in `digline.wire`, which
is pure and knows no store. (ADR 0011 §7)

`resolve_key` **returns** what the scan could not read instead of printing it.
In the CLI that note goes to stderr, where it cannot break a pipeline reading
JSON on stdout; over MCP there is no stderr and it becomes a response field
(ADR 0011 §4). A layer that touches the world is still not a layer that talks to
a user, so it hands the sentence back and lets the front end decide where it
goes.
"""

from __future__ import annotations

from dataclasses import dataclass

from digline.core import NO_BASELINE, Run, key_of
from digline.host.errors import UsageError
from digline.run import Suite
from digline.store import (
    RegisterRefusedError,
    ResultStore,
    RunRef,
    SupportsRegister,
    TenantMismatchError,
)

__all__ = [
    "LATEST",
    "NO_BASELINE",
    "Resolved",
    "need_baseline",
    "read_run",
    "replacing",
    "resolve_key",
]

LATEST = "latest"


def replacing(value: str) -> str | None:
    """The reference a promotion names, as `promote_baseline` takes it: a key, or
    `None` for `NO_BASELINE`."""
    return None if value == NO_BASELINE else value


@dataclass(frozen=True, slots=True)
class Resolved:
    """A run key, and what the scan that found it had to step over.

    `note` is empty when nothing was left out, so a caller prints it only when
    there is something to say and a reader is never made to read a reassurance —
    the same rule `Listing.note()` follows.
    """

    key: str
    note: str = ""


def resolve_key(store: ResultStore, suite: Suite, key: str) -> Resolved:
    """`latest` means the most recent run of this suite in this perimeter.

    Not a guess and not a default: the caller still names a run, and `latest` is
    a value they type. It exists because copying a key by hand right after `run`
    printed it is the friction of minute three, and a tool people abandon at
    minute three has no other qualities worth discussing.

    Resolved over a **scan**, which steps over documents this version cannot
    read. A stored history outlives the schema that wrote it, and the morning
    after a release `latest` used to fail on yesterday's files — a refusal about
    a run nobody had asked for. What was skipped is stated, never swallowed.

    Within what can be read, the newest is chosen on `created_at`, the recorded
    fact, rather than on the filename that encodes it.

    A file whose name is not its run's key is left out by the scan, so one such
    file no longer stops `latest` for the whole suite (#429). The scan's note
    names it, says whether its key is among the runs read, and never says it
    was newer: that would need a `created_at` read from a document nobody
    validated (ADR 0040 §5.2).

    **A newer run that is gone is said only where something recorded it.** A
    scan sees what is there, not what was: with the newest file removed,
    `latest` is the one before it, and the listing looks exactly as if the
    removed run had never been written. So the note names a missing run only
    where a committed artifact of this store remembers one newer than the
    pick. The baseline was promoted from a run, and every register line names
    one. Where neither does, the note stays empty and says nothing about
    whether a run is missing. **An empty note does not mean nothing is
    missing.** Widening that needs a record of what existed. The one such
    record is the deletion ledger, which ADR 0035 proposes and keeps off every
    read path (§10), so this function may not read it. A note that claimed to
    detect a removal it cannot see would be worse than none. (#286)
    """
    if key != LATEST:
        return Resolved(key)
    listing = store.scan_runs(suite.tenant, suite.name)
    if not listing.runs:
        # Two different situations, and telling them apart is the whole value of
        # the message: an empty store needs a run, a store full of old schemas
        # needs a migration. "No readable runs" on an empty store would suggest
        # unreadable ones exist.
        if listing.skipped or listing.unreadable:
            raise UsageError(
                f"no readable runs stored for suite {suite.name!r} in tenant "
                f"{suite.tenant!r} — {listing.note()}. "
                "Run `digline migrate` to bring them up to date."
            )
        if listing.misfiled:
            # Not a migration: a file named otherwise is put right by its
            # name, and the note says which. (ADR 0040 §5.3)
            raise UsageError(
                f"no runs stored under their key for suite {suite.name!r} in "
                f"tenant {suite.tenant!r} — {listing.note()}."
            )
        raise UsageError(
            f"no runs stored for suite {suite.name!r} in tenant {suite.tenant!r}, "
            "so there is no latest one. Run it first."
        )
    newest = max(
        (store.read_run(ref) for ref in listing.runs), key=lambda r: r.created_at
    )
    key = key_of(newest.created_at, newest.config_hash)
    notes = [listing.note(), *_newer_on_record(store, suite, newest, key)]
    return Resolved(key, "; ".join(note for note in notes if note))


def _newer_on_record(
    store: ResultStore, suite: Suite, picked: Run, key: str
) -> list[str]:
    """What this store's committed artifacts remember that is newer than the
    run `latest` picked, one sentence per artifact, or nothing.

    Newer than the pick means not among the runs read: had it been read, it
    would have been the pick. It can be absent or unreadable, which is why the
    sentence says *not read here* and not *removed*. An artifact that cannot be
    read is named rather than passed over, as `scan_runs` does for a run:
    silence there would read as *nothing newer on record*.
    """
    found: list[str] = []
    try:
        baseline = store.read_baseline(suite.tenant, suite.name)
    except (OSError, ValueError, TenantMismatchError) as exc:
        found.append(f"the baseline could not be read to check for a newer run: {exc}")
    else:
        if baseline is not None and baseline.created_at > picked.created_at:
            found.append(
                "the baseline was promoted from run "
                f"{key_of(baseline.created_at, baseline.config_hash)}, newer than "
                f"{key}, and that run was not read here"
            )
    if isinstance(store, SupportsRegister):
        try:
            entries = store.read_register(suite.tenant, suite.name).entries
        except RegisterRefusedError as exc:
            found.append(
                f"the register could not be read to check for a newer run: {exc}"
            )
        else:
            newer = [e for e in entries if e.run_created_at > picked.created_at]
            if newer:
                last = max(newer, key=lambda e: e.run_created_at)
                found.append(
                    f"the register names run {last.run_key}, newer than {key}, "
                    "and that run was not read here"
                )
    return found


def read_run(store: ResultStore, suite: Suite, key: str) -> Run:
    return store.read_run(RunRef(tenant=suite.tenant, suite=suite.name, key=key))


def need_baseline(store: ResultStore, suite: Suite) -> Run:
    baseline = store.read_baseline(suite.tenant, suite.name)
    if baseline is None:
        raise UsageError(
            f"suite {suite.name!r} has no baseline for tenant {suite.tenant!r} yet. "
            "Run it, look at the result, then "
            "'digline promote --run <key> --replacing none'."
        )
    return baseline
