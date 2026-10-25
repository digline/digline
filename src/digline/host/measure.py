"""Running a suite and recording it as it goes: one composition, two front ends.

`execute()` produces a `Run` and knows nothing else; `write_run` stores one. The
four steps between them — open the journal, execute with a callback, write the
run, delete the journal — are what a *launch* is, and each front end used to
spell them out for itself. Journaling wired in two places is journaling that
drifts in one of them, so it lives here: the layer that touches the world and
the layer both front ends already sit on (ADR 0011 §7, ADR 0017 §11).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Protocol

from digline import __version__
from digline.core import (
    Artifact,
    CallTotals,
    CaseResult,
    DocumentRefusedError,
    Run,
    SystemConfig,
)
from digline.core.run import SCHEMA_VERSION
from digline.host.environment import this_process
from digline.run import (
    CallPlan,
    Mapper,
    Suite,
    Target,
    default_mapper,
    execute,
    judge_config,
    judges,
    planned_calls,
    price_digest_of,
    target_config,
)
from digline.store import (
    JournalHeader,
    JournalRefusedError,
    NotAReferenceError,
    Pending,
    ResultStore,
    RunRef,
    SuiteMismatchError,
    SupportsJournal,
    TenantMismatchError,
)
from digline.targets import HasObserved

__all__ = [
    "JournallingStore",
    "Measured",
    "Prepared",
    "measure",
    "prepare",
    "refuse_unreadable_baseline",
    "seed_observed",
]


class JournallingStore(ResultStore, SupportsJournal, Protocol):
    """A store that holds runs *and* can record one as it goes.

    The two halves are separate protocols on purpose — a backend may implement
    `ResultStore` and no journal (ADR 0017 §5) — and this is the pair a launch
    needs, named once here rather than spelled out at every call site.
    """


@dataclass(frozen=True, slots=True)
class Prepared:
    """What the launch will be, decided before anything is called.

    Separate from `measure()` so a front end can refuse, and *announce*, before
    the first call: a refused resume must cost nothing, and the bill has to be
    stated before it is run up (`AGENTS.md` §7).
    """

    header: JournalHeader
    plan: CallPlan
    #: Cases a journal already holds and this launch will not call again.
    done: Mapping[str, CaseResult] = field(default_factory=dict[str, CaseResult])
    #: The journal being continued, or `None` for a fresh run.
    resume: Pending | None = None
    #: What the earlier legs already spent, carried into this leg's totals so
    #: the finished document bills the whole run. `None` on a fresh run, which
    #: is what `execute()` requires beside an empty `done`. (ADR 0025 §11)
    spent: CallTotals | None = None
    #: Errored cases being paid for a second time, `case_id` -> the layer that
    #: errored them. Named rather than counted so the announcement can say
    #: which, and digline can go on not deciding for the user. (ADR 0017 §9)
    retrying: Mapping[str, str] = field(default_factory=dict[str, str])

    @property
    def created_at(self) -> str:
        """The run's birth: a resumed run carries the original (ADR 0017 §8)."""
        return self.header.created_at


@dataclass(frozen=True, slots=True)
class Measured:
    """A run, where it was stored, and what it was announced as costing."""

    ref: RunRef
    run: Run
    plan: CallPlan


def prepare(
    suite: Suite,
    target: object,
    *,
    now: str,
    git_commit: str | None,
    artifacts: Mapping[str, Artifact],
    pinned: Sequence[str] = (),
    resume: Pending | None = None,
    retry_errors: bool = True,
) -> Prepared:
    """Decide what this launch is, and refuse a resume that would not be one.

    `now` is the only clock reading, and what becomes of it is the rule: a fresh
    run is born now, a resumed one keeps the `created_at` of the run it is
    finishing and records this leg's start beside it. So the resumed run writes
    the file the killed run was always going to write.

    Every refusal here happens **before the first call of the new leg** — and
    before the journal is opened at all, which is the other half of the same
    promise: a refused resume costs no call *and* leaves no file behind.
    """
    header = JournalHeader(
        tenant=suite.tenant,
        environment=suite.environment,
        suite=suite.name,
        # The same digest `execute()` stamps, or a resume would be refused for a
        # rule that did not move. (ADR 0022 §4)
        config_hash=suite.config_hash(pricing=price_digest_of(target)),
        cases_digest=suite.cases_digest(),
        created_at=now,
        started_at=now,
        digline_version=__version__,
        record_responses=suite.record_responses,
        git_commit=git_commit,
        artifacts={path: item.sha for path, item in artifacts.items()},
        pinned=tuple(pinned),
        target_config=target_config(target),
        judge_config=judge_config(suite),
    )
    # Which process opens this leg, and on which host: what tells a journal
    # whose process is still running from one that was killed. Read here, where
    # the world is read, and outside `differences`. (#478)
    pid, host = this_process()
    header = replace(header, pid=pid, host=host)
    if resume is None:
        return Prepared(header=header, plan=planned_calls(suite))

    if resume.refusal:
        raise JournalRefusedError(resume.refusal)
    if resume.finished:
        raise JournalRefusedError(
            f"run {resume.key} is already written: the journal outlived the run "
            "it recorded, which is what a kill between the write and the delete "
            "leaves. There is nothing to finish"
        )
    assert resume.header is not None  # `refusal` is set when it is absent
    differences = header.differences(resume.header)
    if differences:
        raise JournalRefusedError(
            f"run {resume.key} cannot be resumed: "
            f"{', '.join(differences)} changed since it started. Every one of "
            "those is a fact the run document states, and half a run under one "
            f"of them and half under another is not a run. Start a new run, or "
            "put back what moved"
        )

    ghosts = sorted(set(resume.done) - {case.id for case in suite.cases})
    if ghosts:
        # The last refusal, and the one the delta-pass over 0.11.0 found
        # missing. `execute()` refuses the same thing — it is an invariant of
        # the driver, and a library caller building `done` by hand meets it
        # there (ADR 0017 §4) — but by then the journal has been opened and a
        # leg written, so a refused resume cost a file and answered in a
        # `ValueError`. Both halves of §6's promise are the point: refused
        # *before the first call*, and the journal left exactly where it was.
        raise JournalRefusedError(
            f"run {resume.key} cannot be resumed: its journal holds a verdict "
            f"for {len(ghosts)} case(s) the suite does not declare "
            f"({', '.join(ghosts)}). The header agreed with this suite, so "
            "the disagreement is in the records themselves — a journal edited "
            "by hand, or one that is not the journal its header claims. A run "
            "may not be assembled out of two case sets"
        )

    empty = sorted(
        case_id
        for case_id, result in resume.done.items()
        if not result.verdicts and result.suspended is None
    )
    if empty:
        # Beside the refusal above and for its reason: the record, not the
        # suite, is what is wrong. A suite cannot declare a case with no
        # questions — one with no assertions is refused outright — so an entry
        # that answers nothing and was not set aside is a damaged record, and
        # recording an error for it would be a verdict about a question the
        # record does not say was asked. (ADR 0027 §5)
        raise JournalRefusedError(
            f"run {resume.key} cannot be resumed: its journal holds "
            f"{len(empty)} case(s) with no verdict and no suspension "
            f"({', '.join(empty)}). A case that ran answers every check it was "
            "asked, and one set aside says so; an entry that does neither is a "
            "journal edited by hand or cut short. Start a new run"
        )

    keep = dict(resume.done)
    retrying: dict[str, str] = {}
    if retry_errors:
        # An errored verdict exits 2 and cannot be promoted, so a resume that
        # kept them would spend its remaining calls finishing a run nobody can
        # use. What the cause is stays a fact to report, never a filter.
        # (ADR 0017 §9)
        retrying = {
            case_id: resume.causes.get(case_id, "")
            for case_id in sorted(resume.errored)
        }
        for case_id in retrying:
            keep.pop(case_id, None)
    return Prepared(
        header=replace(
            header, created_at=resume.header.created_at, leg=resume.legs + 1
        ),
        plan=planned_calls(suite, done=keep, retried=len(retrying)),
        done=keep,
        # The whole journal's bill, including the cases being retried: their
        # earlier calls were paid for, and paying twice costs twice. `keep` is
        # about what will not be *called* again, which is a different question
        # from what has already been *spent*. (ADR 0025 §11)
        spent=resume.spent,
        resume=resume,
        retrying=retrying,
    )


def seed_observed(suite: Suite, target: object, pending: Pending) -> None:
    """Give the target and the judges back what an earlier leg observed.

    The object that held *the provider answered as X* died with the killed
    process. Seeded, an alias that rolled across the seam raises on the first
    call of the new leg exactly as it would have raised on the next call of the
    old one — the run is still written, that one case errors, and nothing is
    averaged (ADR 0017 §7).

    The judges are seeded from one merged configuration, which is what
    `judge_config` produces: with a single instrument it is that instrument's,
    and with several there are no shared values to seed and nothing happens.
    """
    _seed(target, pending.observed_target)
    for judge in judges(suite.assertions):
        _seed(judge, pending.observed_judge)


def _seed(holder: object, observed: SystemConfig) -> None:
    if isinstance(holder, HasObserved):
        holder.observed.resume(observed.values)


def refuse_unreadable_baseline(
    store: ResultStore, suite: Suite, *, accepting_schema: int | None = None
) -> None:
    """Refuse to spend where the comparison the spending is for cannot be read.

    A baseline at a schema this digline does not read makes every `compare`
    of this suite exit 64, so a run made now is paid for and cannot be
    compared. `run` and `rejudge` call this before their first call to a
    target or a judge, and `pytest-digline` before `--digline-run`. (#621)

    **Only the schema is read here, and that is a choice.** `read_baseline`
    also refuses a file that is not JSON, a baseline of another tenant or suite
    and a projection nobody promoted. Those stay with `compare`: anticipating
    them would make spending depend on the whole shape of the baseline, which
    is `compare`'s work. The schema refusal is told apart by
    `DocumentRefusedError.declared_schema`, since a broken file raises the
    same class.

    **No baseline is no refusal.** A first run has nothing to be compared with.

    **Both directions, and the advice differs** (ADR 0014 §5). A newer baseline
    asks for a newer digline, and `migrate` would be the wrong advice there: it
    never moves a document backwards. An older one asks for `migrate`.

    `accepting_schema` runs anyway when it names exactly the schema the
    baseline declares, as `--accepting-pin` accepts exactly the paths a
    promotion implicates. Naming another schema, or one where nothing is
    unreadable, is refused: an acceptance of nothing is a mistake, not a no-op.
    """
    try:
        store.read_baseline(suite.tenant, suite.name)
    except DocumentRefusedError as exc:
        # `None` for a broken file, which is left to `compare`. See above.
        declared, unreadable = exc.declared_schema, exc
    except (TenantMismatchError, SuiteMismatchError, NotAReferenceError):
        # `compare`'s, by the same choice: the read raises them after the
        # schema has already been read and found readable.
        declared, unreadable = None, None
    else:
        declared, unreadable = None, None

    flag = "--accepting-baseline-schema"
    if accepting_schema is not None:
        if declared is None:
            raise DocumentRefusedError(
                f"{flag} {accepting_schema} names schema {accepting_schema}, and "
                f"the baseline of suite {suite.name!r} for tenant {suite.tenant!r} "
                "is not at a schema this digline cannot read: there is nothing to "
                "accept"
            )
        if accepting_schema != declared:
            raise DocumentRefusedError(
                f"{flag} {accepting_schema} names schema {accepting_schema}, and "
                f"the baseline declares schema {declared}",
                declared_schema=declared,
            )
        return
    if declared is None:
        return
    remedy = (
        "Upgrade digline to one that reads it"
        if declared > SCHEMA_VERSION
        else "Run `digline migrate` to bring it up to date"
    )
    raise DocumentRefusedError(
        f"the baseline of suite {suite.name!r} for tenant {suite.tenant!r} is at "
        f"schema {declared}, and this digline reads schema {SCHEMA_VERSION}, so "
        "a run now would be paid for and could not be compared. Nothing was "
        f"called. {remedy}, or accept it by name with `{flag} {declared}` on "
        "`digline run` or `digline rejudge`",
        declared_schema=declared,
    ) from unreadable


def measure(
    suite: Suite,
    target: Target,
    *,
    store: JournallingStore,
    prepared: Prepared,
    run_metadata: Mapping[str, object] | None = None,
    artifacts: Mapping[str, Artifact] | None = None,
    pinned: Sequence[str] = (),
    modules_unchecked: Sequence[str] | None = None,
    mapper: Mapper = default_mapper,
    accepting_baseline_schema: int | None = None,
) -> Measured:
    """Run the suite, recording as it goes, and store what came out.

    The journal is deleted only once the run file exists, and by `complete()`,
    which is named for what it means: a journal removed for any other reason is
    paid work thrown away.

    First, before anything is called: a baseline at a schema this digline
    cannot read is refused unless `accepting_baseline_schema` names it — see
    `refuse_unreadable_baseline`. (#621)
    """
    refuse_unreadable_baseline(store, suite, accepting_schema=accepting_baseline_schema)
    if prepared.resume is not None:
        seed_observed(suite, target, prepared.resume)
    journal = store.open_journal(prepared.header)
    run = execute(
        suite,
        target,
        created_at=prepared.created_at,
        mapper=mapper,
        git_commit=prepared.header.git_commit,
        run_metadata=run_metadata,
        artifacts=artifacts,
        pinned=pinned,
        modules_unchecked=modules_unchecked,
        done=prepared.done,
        spent=prepared.spent,
        on_case=journal.append,
    )
    ref = store.write_run(run)
    journal.complete()
    return Measured(ref=ref, run=run, plan=prepared.plan)
