"""The state of a suite, whole: what `digline view` says on its first page for
a suite. (ADR 0066 §1)

**No fact here is computed here.** Each comes from the function a command
already calls, and this module only puts them side by side:

- the cases the suite declares, each with the checks it is asked, from
  `checks_asked`, the dispatch the driver follows, and the checks no case is
  asked from `idle_checks`, which `digline where --json` carries;
- the reviewed answers by yes and no, from `reviewed_counts`, which
  `digline suggest --assist` counts with;
- the newest run and its exit code, from `runs_of` and `run_exit_code`, as
  `where` reads them;
- the reference in force, from `suite_runs` and the store's `read_baseline`,
  as the run list reads them, with the cases excluded at its promotion;
- the recordings waiting, from `recorder_status` and `imported_since`, as
  `digline record status --suite` reads them;
- the next step, from `where` itself.

It reads the store and the suite, writes nothing and renders nothing: the
page lays out what it returns.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

from digline.core.run import Exclusion
from digline.host.importing import imported_since
from digline.host.listing import suite_runs
from digline.host.recording import recorder_status
from digline.host.where import runs_of, where
from digline.run.suite import (
    ReviewedCounts,
    Suite,
    checks_asked,
    idle_checks,
    reviewed_counts,
)
from digline.store.file_store import FileResultStore
from digline.wire.contract import run_exit_code
from digline.wire.recorder import SuiteRecordings
from digline.wire.where import Where

__all__ = ["CaseChecks", "SuiteState", "suite_state"]


@dataclass(frozen=True, slots=True)
class CaseChecks:
    """One declared case and the checks a run asks of it, by name, in the
    order the suite declares them. Empty for a suspended case."""

    case_id: str
    checks: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SuiteState:
    """What the state of a suite shows, each field read where its command
    reads it.

    `newest` is the newest run's key and exit code, `None` before the first
    run. `baseline_key` is `None` where there is no reference, or where one is
    there and could not be read, which `baseline_refused` says. `recordings`
    is the suite's line of `digline record status`, `None` where the tenant
    holds no recording of the suite."""

    where: Where
    cases: tuple[CaseChecks, ...]
    reviewed: ReviewedCounts
    idle_checks: tuple[str, ...]
    newest: tuple[str, int] | None
    baseline_key: str | None
    baseline_refused: str
    promoted_at: str | None
    excluded: tuple[Exclusion, ...]
    recordings: SuiteRecordings | None


def suite_state(
    root: Path,
    suite: Suite,
    module: ModuleType | None,
    *,
    suite_file: Path | None = None,
) -> SuiteState:
    """The state of `suite`, in its own tenant. (ADR 0066 §1)"""
    tenant = suite.tenant
    store = FileResultStore(root)
    found = where(root, tenant, suite=suite, module=module, suite_file=suite_file)
    cases = tuple(
        CaseChecks(
            case.id,
            tuple(
                check.name
                for check in suite.assertions
                if check.identity in checks_asked(suite, case)
            ),
        )
        for case in suite.cases
    )
    runs = runs_of(store, tenant, suite)
    newest = (
        None
        if not runs
        else (runs[-1][0], run_exit_code(runs[-1][1], declared=suite.declared()))
    )
    listed = suite_runs(store, tenant, suite.name, mint=None)
    reference = (
        None if listed.baseline_key is None else store.read_baseline(tenant, suite.name)
    )
    # `digline record status --suite`'s reading: the draft is read only for a
    # suite that declares where captured cases go, as the recorder's page
    # reads it.
    imports: dict[str, tuple[int | None, int]] = {}
    if suite.capture is not None:
        imports[suite.name] = imported_since(root, suite, module, tenant)
    [status] = recorder_status(root, tenant, imports)
    return SuiteState(
        where=found,
        cases=cases,
        reviewed=reviewed_counts(suite.cases),
        idle_checks=idle_checks(suite),
        newest=newest,
        baseline_key=listed.baseline_key,
        baseline_refused=listed.baseline_refused,
        promoted_at=None if reference is None else reference.promoted_at,
        excluded=() if reference is None else reference.excluded_at_promotion,
        recordings=next(
            (entry for entry in status.suites if entry.suite == suite.name), None
        ),
    )
