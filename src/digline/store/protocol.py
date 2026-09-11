"""The persistence protocol. Depends on the core; the core does not depend on it."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from typing import Protocol, runtime_checkable

from digline.core.run import (
    SCHEMA_VERSION,
    CaseProgress,
    CaseResult,
    Run,
    SystemConfig,
)
from digline.core.types import Cause

__all__ = [
    "JOURNAL_VERSION",
    "ConfigMismatchError",
    "ErroredRunError",
    "Journal",
    "JournalBusyError",
    "JournalHeader",
    "JournalRefusedError",
    "Listing",
    "Pending",
    "ReplayedRunError",
    "ResultStore",
    "RunRef",
    "SupportsJournal",
    "TenantMismatchError",
]

#: The journal's own format version, independent of `SCHEMA_VERSION` and
#: deliberately so. A journal is a **format**, so it has a version; it is a
#: *work file* and not a document, so it has no migration. A journal this
#: digline cannot read is one it does not resume — it is left on disk, named,
#: and the run it belongs to is started again. (ADR 0017 §2)
JOURNAL_VERSION = 1


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


class ReplayedRunError(Exception):
    """Raised when promoting a run whose answers were replayed from another.

    A replay has **zero target variance** by construction: the answers are
    fixed, so the interval it records is the judge's wobble alone. Promoted, it
    would become the reference every future real run is measured against — and
    ADR 0006 §5 judges a movement against the *baseline's* interval, so every
    ordinary wobble of the target would then read as a movement beyond the
    noise. A replay promoted as a reference is a noise floor measured without
    the noise. (ADR 0015 §7)
    """


class JournalRefusedError(Exception):
    """Raised when a pending journal may not be resumed.

    The rule it enforces is one sentence: **a resumed run may only be assembled
    when every fact the run document asserts is true of both legs.** Half a run
    under one prompt and half under another is not a run, and a document that
    said otherwise would be wrong in the one file this product exists to make
    trustworthy. (ADR 0017 §6)

    Raised *before the first call of the new leg*, always, so a refused resume
    costs nothing and leaves the journal exactly where it was.
    """


class JournalBusyError(JournalRefusedError):
    """Raised when another process already holds the leg this one would write.

    The whole of the concurrency story, and it needs no lock file: the leg is
    created with `O_CREAT|O_EXCL`, so the loser of the race is told. A lock
    would be the wrong instrument here — the process this feature exists for is
    one that was *killed*, and a lock it could not release would block the very
    rescue it was meant to protect. (ADR 0017 §5)
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

    def advice(self) -> tuple[str, ...]:
        """What to do about what was skipped, in the direction the numbers say.

        Both sentences can be owed at once — a store holding runs from before an
        upgrade *and* runs written by a colleague who is ahead — so this returns
        what is true rather than the first thing that is.

        The second sentence is the one that did not exist until schema 10. Until
        then 9 was the ceiling of the world, so no released digline had ever met
        a newer document, and the advice was unconditionally "run digline
        migrate" — which, pointed backwards, tells a reader to do the one thing
        nothing can do. `upgrade_document` has always refused in the right words;
        the listing never reached it. (ADR 0014 §5)
        """
        lines: list[str] = []
        if any(version < SCHEMA_VERSION for version in self.skipped):
            lines.append("run `digline migrate` to bring them up to date")
        if any(version > SCHEMA_VERSION for version in self.skipped):
            lines.append(
                "upgrade digline to read them: a newer document cannot be "
                "rewritten backwards without discarding what the newer schema "
                "added"
            )
        return tuple(lines)


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

    def promote_baseline(
        self, ref: RunRef, expected_config_hash: str, *, promoted_at: str
    ) -> Run:
        """Promote a run to be the baseline of its suite, within its tenant.

        `promoted_at` is **passed in and not read here**, for the reason
        `created_at` is passed into `execute()`: the clock belongs to the layer
        that touches the world, and a store that read it would make its own
        output untestable and its own tests dependent on the hour they run at.
        It is mandatory rather than defaulted so that a caller decides — a
        default would make *not recorded* the ordinary outcome, which is the gap
        the field exists to close. Empty is legal and means exactly that.
        (ADR 0014 §3)

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
        4. `ReplayedRunError` if the run declares `rejudged_from` — the answers
           must have been *measured*, or the interval promoted with them was
           measured without the target in it (ADR 0015 §7).

        What is written carries `promoted_at`: `created_at` says when the run was
        measured, and this says when a person signed it off.

        What is written is `without_responses(run)`: a baseline is committed,
        and a reference of verdicts has no business carrying the model's answers
        into somebody's git history (ADR 0015 §5).
        """
        ...


@dataclass(frozen=True, slots=True)
class JournalHeader:
    """Line 1 of every leg: what the run this journal belongs to claims to be.

    Every field but `started_at` and `leg` is checked on resume, and the list is
    not a collection of good ideas — it is **exactly the set of facts the run
    document asserts**, plus the two that make the journal readable. That is
    what makes the run document need no marker for having been resumed: a
    document that asserts nothing untrue of either leg has nothing to declare.
    (ADR 0017 §6, §10)

    `created_at` is the run's birth and is carried unchanged by every leg — it
    is what the finished run is stamped with and what its key is built from, so
    a resumed run writes the file the killed run was always going to write.
    `started_at` is this leg's own clock reading, which lives here and dies with
    the journal.
    """

    tenant: str
    environment: str
    suite: str
    config_hash: str
    cases_digest: str
    created_at: str
    started_at: str
    digline_version: str
    record_responses: bool
    git_commit: str | None = None
    #: Declared path -> sha256, as `read_artifacts` found them. The digests
    #: only: a journal holds no more of the thing under test than it needs to
    #: know that it did not move.
    artifacts: Mapping[str, str] = field(default_factory=dict[str, str])
    #: What the target and the judges *declared* before the first call. The
    #: observed half cannot be known at header time and is recorded as it
    #: arrives, in its own record.
    target_config: SystemConfig = field(default_factory=SystemConfig)
    judge_config: SystemConfig = field(default_factory=SystemConfig)
    journal_version: int = JOURNAL_VERSION
    leg: int = 1

    def differences(self, other: JournalHeader) -> tuple[str, ...]:
        """Which asserted facts differ from `other`'s, in the order read.

        A method on the value rather than a function in the store, because what
        a resume may not change is a property of what a run claims — and the
        day a field is added to `Run`, the question to ask is not *should this
        be checked* but *does the document assert it*.
        """
        mine, theirs = (
            replace(self, started_at="", leg=0),
            replace(other, started_at="", leg=0),
        )
        return tuple(
            name
            for name in (
                "journal_version",
                "digline_version",
                "tenant",
                "environment",
                "suite",
                "config_hash",
                "cases_digest",
                "artifacts",
                "target_config",
                "judge_config",
                "record_responses",
                "git_commit",
            )
            if getattr(mine, name) != getattr(theirs, name)
        )


@dataclass(frozen=True, slots=True)
class Pending:
    """A run that was started and never written, as the store found it.

    `header` and the rest are absent when `refusal` is set: a journal this
    digline cannot read still has to be *named* — it holds paid work, so it is
    never deleted on a guess — and naming it is what this shape does.
    """

    key: str
    header: JournalHeader | None = None
    #: Why it cannot be resumed, or empty. Set for an unreadable journal, a
    #: corrupt one, and one written by a digline that knows a format this one
    #: does not.
    refusal: str = ""
    legs: int = 0
    #: `case_id` -> the last result journalled for it. A case appears twice in a
    #: journal only when it was retried, and the last record is the one that
    #: counts: the file is append-only, so a retry adds a line rather than
    #: editing one. (ADR 0017 §3)
    done: Mapping[str, CaseResult] = field(default_factory=dict[str, CaseResult])
    errored: frozenset[str] = frozenset()
    #: `case_id` -> which layer errored it, for the cases that errored. Read by
    #: the announcement before the new leg and by nothing else: digline never
    #: selects what to re-pay for from it, because which of a user's failures
    #: are worth money is the user's decision. (ADR 0017 §9)
    causes: Mapping[str, Cause] = field(default_factory=dict[str, "Cause"])
    #: What the provider *said* answered, as the earlier legs saw it. Seeded
    #: back into the target and the judges before the new leg's first call, so
    #: an alias that rolled across the seam raises instead of being averaged
    #: away. (ADR 0017 §7)
    observed_target: SystemConfig = field(default_factory=SystemConfig)
    observed_judge: SystemConfig = field(default_factory=SystemConfig)
    #: The run file already exists: the process was killed after `write_run` and
    #: before the delete. Not resumable and not evidence of anything.
    finished: bool = False


class Journal(Protocol):
    """A run being recorded as it goes.

    Owned by the store, never by the driver: `execute()` is handed `append` as a
    callback and learns nothing about where the record lands.
    """

    @property
    def key(self) -> str:
        """The key the finished run will be stored under. The journal is named
        after it, so the run lands where the journal said it would."""
        ...

    @property
    def leg(self) -> int: ...

    def append(self, progress: CaseProgress) -> None:
        """Record one finished case, durably, before the next one starts."""
        ...

    def complete(self) -> None:
        """The run is written; delete every leg.

        Named for what it means rather than for what it does. A journal that is
        deleted for any other reason is paid work thrown away.
        """
        ...


@runtime_checkable
class SupportsJournal(Protocol):
    """A store that can record a run as it goes.

    A **separate protocol, asked for rather than required**, the way `Preflight`
    is asked of a target. `ResultStore` is the contract every backend meets, and
    the planned production store has no business being obliged to implement an
    append-only file in a repository: a store that cannot journal is used
    exactly as it is used today, and the front end says so once. (ADR 0017 §5)
    """

    def open_journal(self, header: JournalHeader) -> Journal:
        """Begin a leg. Raises `JournalBusyError` if another process holds it."""
        ...

    def pending(self, tenant: str, suite: str) -> tuple[Pending, ...]:
        """Every run of this suite that was started and never written."""
        ...

    def drop_pending(self, tenant: str, suite: str, key: str) -> None:
        """Delete a journal without finishing it.

        For the one case that has an answer: a journal whose run file already
        exists, left by a kill between `write_run` and the delete. It is not
        resumable and not evidence of anything, so the next `run` removes it and
        says so. Never called on a journal that might still be finished — that
        is paid work. (ADR 0017 §12)
        """
        ...
