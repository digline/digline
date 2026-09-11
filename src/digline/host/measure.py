"""Running a suite and recording it as it goes: one composition, two front ends.

`execute()` produces a `Run` and knows nothing else; `write_run` stores one. The
four steps between them — open the journal, execute with a callback, write the
run, delete the journal — are what a *launch* is, and each front end used to
spell them out for itself. Journaling wired in two places is journaling that
drifts in one of them, so it lives here: the layer that touches the world and
the layer both front ends already sit on (ADR 0011 §7, ADR 0017 §11).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from typing import Protocol

from digline import __version__
from digline.core import Artifact, CaseResult, Run, SystemConfig
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
    target_config,
)
from digline.store import (
    JournalHeader,
    JournalRefusedError,
    Pending,
    ResultStore,
    RunRef,
    SupportsJournal,
)
from digline.targets import HasObserved

__all__ = [
    "JournallingStore",
    "Measured",
    "Prepared",
    "measure",
    "prepare",
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
    resume: Pending | None = None,
    retry_errors: bool = True,
) -> Prepared:
    """Decide what this launch is, and refuse a resume that would not be one.

    `now` is the only clock reading, and what becomes of it is the rule: a fresh
    run is born now, a resumed one keeps the `created_at` of the run it is
    finishing and records this leg's start beside it. So the resumed run writes
    the file the killed run was always going to write.

    Every refusal here happens **before the first call of the new leg**, which
    is what makes a refused resume free.
    """
    header = JournalHeader(
        tenant=suite.tenant,
        environment=suite.environment,
        suite=suite.name,
        config_hash=suite.config_hash(),
        cases_digest=suite.cases_digest(),
        created_at=now,
        started_at=now,
        digline_version=__version__,
        record_responses=suite.record_responses,
        git_commit=git_commit,
        artifacts={path: item.sha for path, item in artifacts.items()},
        target_config=target_config(target),
        judge_config=judge_config(suite),
    )
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


def measure(
    suite: Suite,
    target: Target,
    *,
    store: JournallingStore,
    prepared: Prepared,
    run_metadata: Mapping[str, object] | None = None,
    artifacts: Mapping[str, Artifact] | None = None,
    mapper: Mapper = default_mapper,
) -> Measured:
    """Run the suite, recording as it goes, and store what came out.

    The journal is deleted only once the run file exists, and by `complete()`,
    which is named for what it means: a journal removed for any other reason is
    paid work thrown away.
    """
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
        done=prepared.done,
        on_case=journal.append,
    )
    ref = store.write_run(run)
    journal.complete()
    return Measured(ref=ref, run=run, plan=prepared.plan)
