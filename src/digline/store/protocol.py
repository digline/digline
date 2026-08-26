"""The persistence protocol. Depends on the core; the core does not depend on it."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Protocol

from digline.core.run import Run

__all__ = [
    "ConfigMismatchError",
    "ErroredRunError",
    "Listing",
    "ResultStore",
    "RunRef",
    "TenantMismatchError",
]


class ConfigMismatchError(Exception):
    """Raised when promoting a run produced under a configuration other than the
    one currently in force."""


class ErroredRunError(Exception):
    """Raised when promoting a run whose verdicts include errors.

    A baseline is an *approved reference*. An error is not a reference: it means
    the suite could not judge, so there is nothing to hold a later run against.
    Promoting one would freeze a permanent red line that no reader could tell
    apart from a new failure — the remedy for a flaky case is to fix it or to
    remove it, not to enshrine it.
    """


class TenantMismatchError(Exception):
    """Raised when an operation would cross a perimeter: a run filed under one
    tenant promoted as another's baseline, or read back through the wrong one."""


@dataclass(frozen=True, slots=True)
class RunRef:
    """An opaque reference to a persisted run.

    `key` is a string chosen by the store, not a path: a store backed by a
    database or by remote object storage must be able to use this same type.
    `tenant` is part of the address because no run exists outside a perimeter.
    """

    tenant: str
    suite: str
    key: str


@dataclass(frozen=True, slots=True)
class Listing:
    """What a scan of a run directory found, including what it could not read.

    A store outlives the schema that wrote into it. The first version of
    `list_runs` raised on the first file of a foreign schema, which made
    `--run latest` fail the morning after a release for a reason that had
    nothing to do with the run being asked for. Refusing an *explicitly named*
    key is right — the caller asked for that file and must be told it cannot be
    read. Refusing a *scan* is not: a scan is a survey, and a survey stops at
    nothing it merely fails to recognise.

    What it must never do is skip in silence. `skipped` counts by schema
    version, so the listing can say "3 runs at schema 5 ignored" and the reader
    knows both that history is missing and what would recover it.
    """

    runs: tuple[RunRef, ...]
    #: schema version -> how many files carried it. Never emptied silently.
    skipped: Mapping[int, int] = field(default_factory=dict[int, int])
    #: Files that are not readable JSON at all. Not a schema question.
    unreadable: tuple[str, ...] = ()

    @property
    def skipped_total(self) -> int:
        return sum(self.skipped.values())

    def note(self) -> str:
        """One line naming what was left out, or empty when nothing was.

        Empty rather than "nothing skipped": a caller prints it only when there
        is something to say, and a reader is never made to read a reassurance.
        """
        parts = [
            f"{count} run(s) at schema {version}"
            for version, count in sorted(self.skipped.items())
        ]
        if self.unreadable:
            parts.append(f"{len(self.unreadable)} unreadable file(s)")
        if not parts:
            return ""
        return f"ignored: {', '.join(parts)}"


class ResultStore(Protocol):
    """Where runs and baselines live.

    The default implementation writes into `.digline/<tenant>/` inside the
    user's repository. Never a database in the home directory, never
    machine-global state (fixed decision 2): state held outside the repository
    cannot be committed with the code it judges, so a baseline stops being
    reviewable and two branches stop being comparable.

    The tenant is a directory rather than a field inside the file because the
    filesystem then enforces the separation that a field could only describe:
    one end customer's results cannot be read by pointing at another's path.
    """

    def write_run(self, run: Run) -> RunRef: ...

    def scan_runs(self, tenant: str, suite: str) -> Listing:
        """Survey the runs of a suite, skipping what this version cannot read.

        The counterpart of `read_run`, which refuses a foreign schema because
        the caller named that file. Here nothing was named, so an unreadable
        file is reported and stepped over.
        """
        ...

    def read_run(self, ref: RunRef) -> Run: ...

    def read_baseline(self, tenant: str, suite: str) -> Run | None:
        """`None` when the suite has no baseline yet in that perimeter — the
        first round is not an error."""
        ...

    def promote_baseline(self, ref: RunRef, expected_config_hash: str) -> Run:
        """Promote a run to be the baseline of its suite, within its tenant.

        Promotion is a deliberate act and never a side effect of running: that
        is what makes the baseline a committed, reviewable artifact rather than
        a file that updates itself. It has three conditions, and each of them
        exists because breaking it produces a comparison that still runs and
        still returns numbers, which is the worst way to be wrong.

        1. `TenantMismatchError` if the stored run's tenant does not match the
           reference it was addressed by — the perimeter must not be crossed by
           a mistaken copy.
        2. `ConfigMismatchError` if the run's `config_hash` does not match
           `expected_config_hash` — otherwise the baseline would record scores
           obtained under a configuration other than the one in force.
        3. `ErroredRunError` if any verdict in the run is in error — a baseline
           is an approved reference, and an error is not one.
        """
        ...
