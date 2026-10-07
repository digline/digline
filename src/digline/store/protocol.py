"""The persistence protocol. Depends on the core; the core does not depend on it."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from typing import Protocol, runtime_checkable

from digline.core.register import RegisterEntry
from digline.core.run import (
    SCHEMA_VERSION,
    CallTotals,
    CaseProgress,
    CaseResult,
    DocumentRefusedError,
    Run,
    SystemConfig,
)
from digline.core.types import Cause

__all__ = [
    "JOURNAL_VERSION",
    "REGISTER_VERSION",
    "Register",
    "RegisterRefusedError",
    "SupportsRegister",
    "ConfigMismatchError",
    "ErroredRunError",
    "Journal",
    "JournalBusyError",
    "JournalHeader",
    "JournalRefusedError",
    "KeylessRunError",
    "Listing",
    "Misfiled",
    "MisfiledRunError",
    "Pending",
    "PromotedRunError",
    "Removal",
    "RemovedRun",
    "ReplayedRunError",
    "UncalibratedRunError",
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
#:
#: **2 — the bill line** (ADR 0025 §11, corrected 2026-09-18). Every `case`
#: record carries what that case's target calls consumed, so a resumed run
#: states the whole run's bill instead of the last leg's.
#:
#: The move is what makes the refusal exist, and the refusal is the point. An
#: added key alone would be *ignored* by a 0.15.x reader, which would then
#: resume and write a run whose totals silently omit every leg it did not run —
#: an undercount in the good-news direction, and invisible in the document it
#: produces. With the version moved, that reader refuses the journal by name,
#: says which format it met, and leaves the paid work on disk. Same shape as
#: `sample_means` (ADR 0024 §6.5): where a reader that ignores a key would
#: misread rather than miss, the version moves.
#:
#: **Two format versions move inside one release, and they stay uncoupled.**
#: `SCHEMA_VERSION` goes to 14 for the same ADR. That is a coincidence of one
#: train and not a new rule: this constant is independent of that one by
#: design (ADR 0017 §2), it did not move for schemas 11, 12 or 13, and nothing
#: here makes it move for 15.
JOURNAL_VERSION = 3

#: The register's own format version, independent of `SCHEMA_VERSION` and of
#: the journal's. A register is a **format** and not a document: nothing
#: migrates it, and a line this digline cannot read is refused by name and left
#: on disk — it is a committed record, and a committed record is never rewritten
#: by a command. (ADR 0021 §5)
REGISTER_VERSION = 1


class RegisterRefusedError(Exception):
    """Raised when a register may not be read, or may not be appended to.

    A line that does not parse anywhere but at the end is a corrupt register; a
    line at a format this digline does not know is a register it cannot read;
    and an incomplete last line is one it will not append after, because the
    new line would bury it in the middle. Each is refused by name and the file is
    left exactly as it was. (ADR 0021 §5)
    """


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


class UncalibratedRunError(Exception):
    """Raised when promoting a run whose calibration case left its band.

    The scores in that run are not placed on the scale they are compared on:
    the judge graded an answer known to be partially correct and put it at an
    extreme, or somewhere else the author declared it cannot be. Promoted, it
    would become the reference a later run's shape is read against — and a
    baseline scored by a judge that has gone binary makes a collapse invisible
    for as long as it stands. (ADR 0024 §4.5)
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


class PathRefusedError(ValueError):
    """Raised when a name is not one safe segment, or leads outside the store.

    The two refusals `_check_name` and `_inside` make. Both are deliberate and
    both carry a sentence written for a reader — `_inside`'s is the one that
    explains the 0.7.2 rule to whoever met it.

    **It subclasses `ValueError` because that is what it already was**, so every
    caller that catches `ValueError` is unchanged: the CLI's handler tuple,
    `migrate_paths`' per-file collection, and the loader. Nothing about the
    control flow moves.

    What the name adds is the ability to say *this is a refusal, not a bug*, at
    a boundary where the difference is the whole point. `digline-mcp` translates
    the exceptions digline raises on purpose and lets everything else travel as
    a crash; these two were indistinguishable from a crash because they had no
    type of their own, so the store's written sentence reached an agent as
    "Error executing tool get_run" and the reason stayed on stderr.
    """


class DirectoryUnreadableError(Exception):
    """Raised when a directory the store lists exists and cannot be opened.

    `Path.glob` catches the `OSError` that `os.scandir` raises and returns no
    matches, on 3.12, 3.13 and 3.14 alike, so a run directory at mode `000` was
    listed as a suite with no runs and a journal directory as nothing pending:
    "there is nothing" and "I could not look" printed the same. On 3.14
    `exists()` answers the same way for a file inside such a directory, so a
    baseline there read as no baseline. (#365)

    **Refused, not counted.** `Listing` counts what a scan opened and could not
    place, one file of many. Here nothing was opened, so no count is true: the
    directory may hold no runs or two hundred, and a survey that cannot say
    which has no survey to return.
    """


class RunNotFoundError(FileNotFoundError):
    """Raised when a run key names no stored run.

    Subclasses `FileNotFoundError` for the reason `PathRefusedError` subclasses
    `ValueError`: it already was one, every handler keeps working, and the type
    exists so a refusal can be told from a missing file nobody meant to open.
    """


class SuiteMismatchError(ValueError):
    """Raised when a stored document declares a suite other than the one it is
    filed under.

    Not a perimeter — the tenant is that — but the same shape of fault one level
    down: `promote_baseline` writes to the suite the *document* names, so a run
    filed under `qa` declaring `"suite": "other"` overwrote `other`'s baseline
    with exit 0 and no output. (Security pass of 2026-09-23, finding 7.)

    **Refused, not redirected**, because digline does not repair documents.
    Writing the baseline to the suite the run was *addressed* through would
    accept a document that lies about itself and file it where it does not
    claim to belong — after which `read_baseline`, which checks the same thing,
    refuses what was just written. A document that contradicts itself is
    refused, not corrected.

    A `ValueError`, so a front end that already refused a malformed document
    refused this one the same way. **That sentence used to end "with no handler
    to add", and it was not true of every front end**: `digline view`'s one route
    that writes listed its refusals by name and never learned this one, so the
    browser got a closed connection (friction 59). Front ends now catch
    `digline.host.REFUSALS`, which a test holds complete."""


class NotAReferenceError(ValueError):
    """Raised when a projected document stands where a reference belongs and
    is not one.

    A served projection may be of a run nobody promoted (ADR 0038 §1). It is
    meant for a page, and nothing reads a page back. **Written as the condition
    it rests on**: a served projection reaches a baseline's place only if
    something writes it there, by hand or by a commit. If that ever happens,
    `compare()` would hold a run against a document nobody approved, and read
    green. So the place where a reference is read refuses it.

    **What tells the two apart is what the document already says**: a
    projected reference carries `promoted_at` and no recorded answer, and a
    served projection of a run nobody promoted carries no `promoted_at`, and may
    carry answers as withheld placeholders. Both fields are verified on a
    projected document, the stamp for its form. Like `project`, this reads what
    the document says and nothing more: a document built by hand with a stamp
    and no answers passes.

    Only a projected document is held to it. A baseline in clear without a
    stamp is one written before promotion stamped its time, and is read as it
    always was."""


class BaselineMovedError(Exception):
    """Raised when a promotion would replace a baseline other than the one the
    run was compared against.

    The lost update a reader found in `promote` (ADR 0031): two people compare
    two runs against one reference, both promote, and the second silently
    replaces the first's reference with a run nobody compared against it. The
    caller names the reference it expects to replace — the key `compare` printed,
    or `None` for a suite with no baseline yet — and this is raised when the one
    present at write time is another.

    **It guarantees that replacing a moved reference is never silent, not that
    it cannot happen**: the refusal names the key it found, and somebody can
    pass that key back without comparing anything. What it stops is the
    replacement nobody noticed.
    """


class PromotedRunError(Exception):
    """Raised when a delete names the run its suite's current baseline was
    promoted from.

    A baseline is the complete run without its responses, so a baseline that
    survived the run under it would keep that run's verdicts, reasons,
    artifacts and configuration, and a delete that reached the baseline would
    be a reference vanishing from under a gate (ADR 0034 §1). So the delete
    reaches neither: it refuses, and the sentence names the one way past, which
    is to promote another run first. No flag overrides it (ADR 0031 §3).

    **A refusal about the key, not about the run**: a baseline promoted from a
    run that is no longer there still names its key, and the delete of that
    key is refused the same way. (ADR 0044 §3.2)
    """


class KeylessRunError(DocumentRefusedError):
    """Raised when a delete meets a run document with no key of its own.

    The key is `key_of(created_at, config_hash)`, and a document that lacks
    either field, or holds one that is not a string or is empty, has none.
    Not `MisfiledRunError`: there the key contradicts the name, here there is
    no key to contradict it, and the reader needs to know which.

    Raised in the plan, before anything is removed, for the file under the key
    asked for and for a document elsewhere in the tenant whose `rejudged_from`
    puts it on that key's chain: what cannot be named is not removed, and
    naming it by its file would contradict `RemovedRun.ref`. (ADR 0044 §3.3,
    §3.4)
    """


@dataclass(frozen=True, slots=True)
class RunRef:
    """An opaque reference to a persisted run.

    `key` is the document's `key_of(created_at, config_hash)`, not a path: a
    store files the run wherever it likes, and answers to that key alone. A
    store backed by a database or by remote object storage uses this same type.
    `tenant` is part of the address because no run exists outside a perimeter.
    (ADR 0040)
    """

    tenant: str
    suite: str
    key: str


@dataclass(frozen=True, slots=True)
class RemovedRun:
    """One run a delete removed, as a document, as journal legs, or as both.

    `ref` is the run's own identity: its key is `key_of(created_at,
    config_hash)` read from the document, never a file's name, and its tenant
    and suite are the ones the document declares. Where the run was filed
    otherwise — under a name that is not its key, or in a tenant or suite it
    does not declare — `found_in` is the address it was filed at, so a reader
    learns both the run and the defect in the store. `None` where it was filed
    where it says it is. (ADR 0044 §1, §3.4)

    `created_at` is read before removing, from the document or from a leg's
    header, and is `None` only for a run with no document whose every leg was
    unreadable: the key's slug does not reverse. It is what a ledger entry
    names (ADR 0035 §4, proposed).
    """

    ref: RunRef
    created_at: str | None
    #: Journal legs removed.
    legs: int
    #: Whether a run document was removed.
    document: bool
    found_in: RunRef | None = None


@dataclass(frozen=True, slots=True)
class Removal:
    """What `delete_run` removed, and how much of the tenant it could not read.

    `unread` counts documents of the tenant the scan could not read, **not
    missed replays**: it is a count of unknowns. `unread: 3` says three
    documents were not read, and nothing about whether any of them was a
    replay of the run removed. (ADR 0044 §1, §5)
    """

    #: The run that was asked for.
    run: RemovedRun
    #: In the order removed: leaves first.
    replays: tuple[RemovedRun, ...] = ()
    unread: int = 0

    @property
    def nothing(self) -> bool:
        """No document, no legs and no replay: nothing was filed under the key.

        A key that was removed before and a key that never existed read the
        same here, because nothing remembers a removal (ADR 0044 §1)."""
        return not self.run.document and not self.run.legs and not self.replays


class MisfiledRunError(DocumentRefusedError):
    """A run addressed by a name that is not its key.

    The file holds a run, and the run's key is `key_of(created_at,
    config_hash)`. A file named otherwise, renamed or copied by hand, is
    refused by the read as it is left out by the scan: one key per run, and the
    store answers to that one alone. The sentence is the scan's, so the two say
    the same thing about the same file. (ADR 0040 §4)
    """


@dataclass(frozen=True, slots=True)
class Misfiled:
    """A file a scan left out because its name is not its run's key.

    `key` is `key_of` of the two fields read from the parsed document. **No
    `Run` is built from the file** (ADR 0040 §5.2), so nothing else in it is
    trusted, and in particular not its `created_at` as a time: the sentence
    never says the run is newer.

    `stem` is the file's name, and appears in clear only. `taken` says a file
    named `<key>.json` is in the directory, whether or not the scan listed it:
    it decides the instruction, because *rename it* would collide. Whether the
    key is among the *listed* runs is a different question, asked for `latest`,
    and `Listing` answers it (§5.1, ruled 2026-10-05). `safe` says the key is a
    file name the store accepts. Where it is not, there is no name to propose
    (§5.4). `sharing` counts the left-out files that hold the same key where no
    file is named by it: above one, which is the original is not known, so no
    file is told to take the name.
    """

    stem: str
    key: str
    taken: bool
    safe: bool
    sharing: int = 1

    def sentence(self, *, listed: bool) -> str:
        """What is wrong with this file, and what to do where something can be
        said. `listed` is whether a run filed under `key` is among the runs
        the scan listed.

        The key is said once, in the file name that holds it or should: it is
        49 characters, and a reader asked to compare two of them by eye is
        asked to find what the sentence could have said. (#440)"""
        if not self.safe:
            return (
                f"{self.stem!r} is not named by its key, and its key is not a "
                "safe file name"
            )
        if self.taken:
            where = "" if listed else ", which is not among the listed runs"
            return f"{self.stem!r} holds a run already filed as {self.key}.json{where}"
        if self.sharing > 1:
            return (
                f"{self.stem!r}: {self.sharing} files hold the same run, and none "
                f"is named {self.key}.json"
            )
        return (
            f"{self.stem!r} holds a run not among the listed runs: rename it to "
            f"{self.key}.json"
        )


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
    #: Files this version cannot place: not JSON, not an object, outside the
    #: store, or declaring a `schema_version` that is not an integer. Not a
    #: schema question, because nothing — `migrate` or an upgrade — recovers
    #: them, so `advice()` has nothing true to say about them. (#350)
    unreadable: tuple[str, ...] = ()
    #: Files left out because their name is not their run's key, checked
    #: before the schema. Names, so in clear only. (ADR 0040 §4, §5)
    misfiled: tuple[Misfiled, ...] = ()

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
        notes = [f"ignored: {', '.join(parts)}"] if parts else []
        if self.misfiled:
            notes.append(
                f"left out for their name: {'; '.join(self.misfiled_sentences())}"
            )
        return "; ".join(notes)

    def misfiled_sentences(self) -> tuple[str, ...]:
        """One sentence per file left out for its name. Whether its key is
        among the listed runs is answered here, for `latest`, and is never
        *it was newer*: that needs a `created_at` nobody can trust."""
        listed = {ref.key for ref in self.runs}
        return tuple(m.sentence(listed=m.key in listed) for m in self.misfiled)

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
    filesystem then enforces the addressing that a field could only describe:
    one end customer's results cannot be filed or read *as* another's, and a
    document that says otherwise is refused (`TenantMismatchError`). That is
    addressing, not access: one OS user reads every tenant's path, and keeping
    them apart is the operator's job (fixed decision 8).
    """

    def write_run(self, run: Run) -> RunRef:
        """File a run and return the reference it is addressed by.

        **The key is the document's, not the backend's:**

            write_run(run).key == key_of(run.created_at, run.config_hash)

        Stated here because nothing checks it. It held while one store existed
        and computed the key itself; a second backend is free to file the run
        wherever it likes, and not free to name it something else. Three things
        already depend on the rule rather than on this implementation of it:
        `compare --json` prints the key through `digline.core.key_of` and a
        person passes it straight back to `promote --replacing`, so a backend
        answering differently would refuse every promotion made after a
        comparison (`BaselineMovedError`); `journal_key` restates it over the
        journal header, so a resumed run writes the file the killed run was
        always going to write (ADR 0017 §8); and the register commits keys to
        git, where they outlive whichever backend wrote them.

        The rule lives in the core because it names a *reference* and not a
        file — `key_of`'s own docstring — and the report and the wire, which
        import nothing but the core, print the same string.
        """
        ...

    def scan_runs(self, tenant: str, suite: str) -> Listing:
        """Survey the runs of a suite, skipping what this version cannot read.

        The counterpart of `read_run`, which refuses a foreign schema because
        the caller named that file. Here nothing was named, so an unreadable
        file is reported and stepped over. A directory that exists and cannot
        be opened is not stepped over: it raises `DirectoryUnreadableError`,
        because nothing in it was surveyed. (#365)
        """
        ...

    def read_run(self, ref: RunRef) -> Run: ...

    def read_baseline(self, tenant: str, suite: str) -> Run | None:
        """`None` when the suite has no baseline yet in that perimeter — the
        first round is not an error.

        A projected document that is not a reference is refused, as
        `NotAReferenceError`: a served projection must not stand where a
        reference belongs (ADR 0038 §1)."""
        ...

    def promote_baseline(
        self,
        ref: RunRef,
        expected_config_hash: str,
        *,
        expected_baseline: str | None,
        promoted_at: str,
    ) -> Run:
        """Promote a run to be the baseline of its suite, within its tenant.

        `expected_baseline` is the key of the reference this promotion replaces,
        as `compare` printed it, or `None` where the suite has no baseline yet.
        Mandatory with no default, for `promoted_at`'s reason: a default would
        make *not checked* the ordinary outcome, and the ordinary outcome is
        where the lost update happens (ADR 0031 §2).

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
        a file that updates itself. Its conditions are named below, and each of
        them exists because breaking it produces a comparison that still runs
        and still returns numbers, which is the worst way to be wrong.

        Named and not counted: this said "five conditions" and listed five while
        there were six, because the sixth shares an exception type with the
        third and is invisible to anyone counting types. (ADR 0002 §8)

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
        5. `UncalibratedRunError` if a calibration case scored outside its
           declared band — the numbers exist and are not measurements
           (ADR 0024 §4.5).
        6. `ErroredRunError` again, before 3, if the run recorded a gap between
           what its suite asked and what came back — what it measured is not
           known, and the refusal names the case and the check rather than only
           the case (ADR 0027 §3).
        7. `SuiteMismatchError`, raised with 1 as the run is read, if the stored
           run declares a suite other than the one it was addressed through — a
           document that contradicts itself is refused, not filed where it
           claims to belong.
        8. `BaselineMovedError`, **last**, if the baseline present now is not
           `expected_baseline`. Last because every refusal above is about the
           run and holds whatever the reference, so a person sent to compare
           again first would be sent round twice; and last because it sits
           beside the write, which is as narrow as the window gets without a
           lock (ADR 0031 §2, *Not decided here*).
        9. `CrossingRefusedError` if the run records an artifact under
           `.digline` or `.git`, in any case and at any depth, or keyed
           outside the perimeter — a baseline carries every artifact's text
           into a versioned file, so this holds **whatever the `Disclosure`**
           (ADR 0042 §3).

        **Where each is met, and what this protocol obliges you to write
        yourself.** They are three questions, not one list:

        - **1 and 7 belong to the reading** — whether the document says it is
          where it was found — and are met as you read the run.
        - **2 to 6, and 9, answer from the document alone.** They are
          `digline.store.refusals_for(run, expected_config_hash)`, which returns
          them in the order they are owed. **Call it rather than restating
          them**: a second copy drifts from this one the first time a condition
          lands, and the miscount above is what that looks like.
        - **8 is yours, beside your own write**, because it asks what the store
          holds *now*. Read the baseline and compare it inside whatever makes
          your write atomic — an in-process lock, a transaction. A parameter
          carrying the current key into `refusals_for` would look like a complete
          check while reporting a fact one instant old, which is why it is not
          one. `digline.store.refusal_for_a_moved_baseline` writes its sentence;
          the read, and the window around it, are yours.

        **Nothing checks that you did 8**, and this is the honest form of that:
        an obligation stated where an implementer reads it, beside the key
        invariant on `write_run`. Two things hold it up rather than one — this
        sentence, and `tests/test_promotion_conditions.py`, which fails if a
        class in this repository defines `promote_baseline` without reaching
        `refusal_for_a_moved_baseline`. That walk reaches implementations here;
        yours, if it lives elsewhere, is held by this paragraph alone.

        **And no test may assert 8's behaviour through a fake store.** A fake
        that skips the condition proves nothing about promotions, so a green
        obtained through one is a green about the fake — exactly the case the
        condition exists for. Test it against a store that really writes.

        What is written carries `promoted_at`: `created_at` says when the run was
        measured, and this says when a person signed it off.

        What is written is `without_responses(run)`: a baseline is committed,
        and a reference of verdicts has no business carrying the model's answers
        into somebody's git history (ADR 0015 §5).
        """
        ...

    def delete_run(self, ref: RunRef) -> Removal:
        """Remove a run, its journal legs, and every replay chained from it.

        **The contract.** After this returns, neither `ref` nor any replay
        chained from it through documents the scan could read is returned by
        `read_run`, `scan_runs`, `list_runs` or `pending`, in any suite of
        `ref.tenant`. A document the scan could not read is not reached, and is
        counted in `Removal.unread`. (ADR 0044 §1)

        **Its reach is the tenant, and no other method's is.** The replays it
        must reach can be filed under any suite of `ref.tenant`, so a backend
        has to list the suites of a tenant and read every run document in each
        — including one that keeps suites apart. Replays are found by their
        `rejudged_from`, read from the raw document so an older schema is
        reached, and followed down the chain.

        **Two phases.** A plan that only reads and is the one place a refusal
        is raised, then a removal that raises none. In the plan, in this order:

        1. `PathRefusedError` for a tenant, suite or key that is not one safe
           segment.
        2. The baseline. One that cannot be read refuses with the error reading
           it raised. One whose key is `ref.key` refuses with
           `PromotedRunError`, whether or not the run is still there — **this
           is yours to write**, and `digline.store.refusal_for_a_promoted_run`
           writes its sentence. `tests/test_promotion_conditions.py` fails if a
           class in this repository defines `delete_run` without raising it.
        3. The run asked for, verified to be the run `ref.key` names:
           `MisfiledRunError`, `TenantMismatchError`, `SuiteMismatchError` as
           `read_run` raises them, `KeylessRunError` for a file that lacks
           either key field, and `DocumentRefusedError` for one that is not a
           JSON object. Legs are not verified: a leg's name is its key.
        4. The tenant: `DirectoryUnreadableError` for a directory that cannot
           be listed, `PathRefusedError` for a path to remove that leads
           outside the store, and `KeylessRunError` for a document on the chain
           with no key of its own. A document on the chain filed under another
           name, or declaring another tenant or suite than its directory, is
           removed and named with `RemovedRun.found_in`.

        **The removal**: each replay from the leaves towards `ref`, each one's
        legs before its document, then `ref`'s legs, then its document. An
        interruption at any point leaves a state the same call repeats (ADR
        0044 §4).

        **Nothing to remove is not an error**: a `Removal` whose `nothing` is
        true. A delete that already finished, repeated, succeeds; the cost is
        that a mistyped key and a removed one return the same value.

        **No lock**, so a delete racing a write loses: a live run writes its
        document after, `promote` can write a baseline from a run this removed,
        and `rejudge` can file a replay after the plan (ADR 0044 §5).
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
    #: Which of those the suite declared must not drift. Here because
    #: `differences` below checks **exactly the facts the run document asserts**,
    #: and since ADR 0029 the document asserts this one: a run killed, its pin
    #: edited, and resumed would write a document claiming a control that was not
    #: in force for its first leg. (ADR 0029 §3)
    pinned: tuple[str, ...] = ()
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
                "pinned",
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
    #: What the earlier legs' target calls consumed, summed over every `case`
    #: record in every leg.
    #:
    #: **Every record, not the last one per case.** `done` keeps the last result
    #: for a case because a retried case has one outcome; the bill keeps both,
    #: because a case that was paid for twice cost twice. It is carried into the
    #: new leg's totals so the finished document states the whole run's bill and
    #: is byte for byte the one the kill prevented (ADR 0017 §10).
    spent: CallTotals = field(default_factory=CallTotals)
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

        Named for what it means rather than for what it does. A journal is
        deleted for one other reason only: a person deleted the run it belongs
        to, through `ResultStore.delete_run`. Deleted for any reason besides
        those two, it is paid work thrown away. (ADR 0044 §4)
        """
        ...


@dataclass(frozen=True, slots=True)
class Register:
    """Every disposition recorded for one suite, in `recorded_at` order.

    Ordered by the recorded fact and not by file order: two branches that each
    appended a line meet in a union merge, and the merged file's order is git's
    and not time's. A line that is byte-identical to one already read is read
    once. (ADR 0021 §4)

    `torn` is an incomplete last line, which was not read. It is stated rather
    than dropped in silence, so a reading can say so.
    """

    entries: tuple[RegisterEntry, ...] = ()
    torn: bool = False


@runtime_checkable
class SupportsRegister(Protocol):
    """A store that can hold the register.

    Asked for rather than required, the way `SupportsJournal` is: the planned
    production store has no business being obliged to write an append-only
    file into a repository. (ADR 0021 §5)
    """

    def read_register(self, tenant: str, suite: str) -> Register:
        """Raises `RegisterRefusedError` for a corrupt line or an unknown format."""
        ...

    def append_register(self, tenant: str, suite: str, entry: RegisterEntry) -> None:
        """One line, durably, after every line already there — never an edit.

        Refuses, leaving the file untouched, where the register cannot be read
        or its last line is incomplete.
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
        """Every run of this suite that was started and never written.

        Raises `DirectoryUnreadableError` when the journal directory exists and
        cannot be opened, rather than answering that nothing is pending. (#365)
        """
        ...

    def drop_pending(self, tenant: str, suite: str, key: str) -> None:
        """Delete a journal without finishing it.

        A journal is removed unfinished in two cases. This method is the first:
        a journal whose run file already exists, left by a kill between
        `write_run` and the delete. It is not resumable and not evidence of
        anything, so the next `run` removes it and says so (ADR 0017 §12). The
        second is `ResultStore.delete_run`, which removes the legs of a run a
        person deleted, whether or not its document exists, because nothing the
        store holds tells a live journal from a killed one (ADR 0044 §4). Never
        called on a journal that might still be finished — that is paid work.
        """
        ...
