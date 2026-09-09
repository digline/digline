"""Naming a stored run, and finding the baseline. Resolution, never shape.

Both front ends need these and neither should grow its own: `latest` resolved
two ways is `latest` meaning two things. They bind `FileResultStore` concretely
and raise `UsageError`, which is why they are here rather than in
`digline.wire`, which is pure and knows no store. (ADR 0011 §7)

`resolve_key` **returns** what the scan could not read instead of printing it.
In the CLI that note goes to stderr, where it cannot break a pipeline reading
JSON on stdout; over MCP there is no stderr and it becomes a response field
(ADR 0011 §4). A layer that touches the world is still not a layer that talks to
a user, so it hands the sentence back and lets the front end decide where it
goes.
"""

from __future__ import annotations

from dataclasses import dataclass

from digline.core import Run
from digline.host.errors import UsageError
from digline.run import Suite
from digline.store import FileResultStore, RunRef

__all__ = ["LATEST", "Resolved", "need_baseline", "read_run", "resolve_key"]

LATEST = "latest"


@dataclass(frozen=True, slots=True)
class Resolved:
    """A run key, and what the scan that found it had to step over.

    `note` is empty when nothing was left out, so a caller prints it only when
    there is something to say and a reader is never made to read a reassurance —
    the same rule `Listing.note()` follows.
    """

    key: str
    note: str = ""


def resolve_key(store: FileResultStore, suite: Suite, key: str) -> Resolved:
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
        raise UsageError(
            f"no runs stored for suite {suite.name!r} in tenant {suite.tenant!r}, "
            "so there is no latest one. Run it first."
        )
    newest = max(
        (store.read_run(ref) for ref in listing.runs), key=lambda r: r.created_at
    )
    return Resolved(store.key_for(newest), listing.note())


def read_run(store: FileResultStore, suite: Suite, key: str) -> Run:
    return store.read_run(RunRef(tenant=suite.tenant, suite=suite.name, key=key))


def need_baseline(store: FileResultStore, suite: Suite) -> Run:
    baseline = store.read_baseline(suite.tenant, suite.name)
    if baseline is None:
        raise UsageError(
            f"suite {suite.name!r} has no baseline for tenant {suite.tenant!r} yet. "
            "Run it, look at the result, then 'digline promote --run <key>'."
        )
    return baseline
