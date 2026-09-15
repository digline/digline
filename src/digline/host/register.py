"""The register's writer: a person's disposition, beside the verdict it was taken
against. (ADR 0021)

**The register is the human's memory; the decision journal is the machine's.**
This is the one place a line of it is written, and it is reached from the CLI
alone: the MCP surface has no writer (ADR 0011 §1), and the operator never
records a disposition, because a disposition is by definition a person's.

The comparison is computed here with the same `compare()`, `headline()` and
`exit_code()` the gate uses, against the baseline in force now — so the verdict
an entry records is the verdict the person was looking at, and the digline that
computed it is written beside it.
"""

from __future__ import annotations

from pathlib import Path

from digline import __version__
from digline.core import (
    DISPOSITIONS,
    Disposition,
    RecordedOutcome,
    RegisterEntry,
    Run,
    compare,
)
from digline.host.errors import UsageError
from digline.host.resolve import need_baseline, read_run
from digline.report import headline
from digline.run import Suite
from digline.store import FileResultStore, RegisterRefusedError
from digline.wire import exit_code

__all__ = ["entry_for", "record"]


def entry_for(
    run: Run,
    run_key: str,
    baseline: Run,
    baseline_key: str,
    *,
    disposition: Disposition,
    recorded_at: str,
    digline_version: str,
) -> RegisterEntry:
    """The entry, from the two documents and the person's answer. Pure.

    The headline is built in `en` because only its facts are kept: the sentence
    is the one thing a register entry refuses (ADR 0021 §3).
    """
    head = headline(compare(run, baseline), run, baseline, locale="en")
    counts = head.counts
    return RegisterEntry(
        recorded_at=recorded_at,
        digline_version=digline_version,
        disposition=disposition,
        run_key=run_key,
        run_created_at=run.created_at,
        run_config_hash=run.config_hash,
        run_environment=run.environment,
        run_digline_version=run.digline_version,
        run_rejudged=run.rejudged_from is not None,
        baseline_key=baseline_key,
        baseline_config_hash=baseline.config_hash,
        baseline_promoted_at=baseline.promoted_at,
        outcome=RecordedOutcome(
            regressed=counts.get("regressed", 0),
            improved=counts.get("improved", 0),
            unchanged=counts.get("unchanged", 0),
            new=counts.get("new", 0),
            missing=counts.get("missing", 0),
            errored=counts.get("errored", 0),
            unjudged=head.unjudged,
            suspended=head.suspended,
            within_noise=head.within_noise,
            on_the_line=head.on_the_line,
            worse=head.worse,
            canary_moved=head.canary_moved,
            config_changed=head.config_changed,
            artifacts_changed=head.artifacts_changed,
            target_config_changed=head.target_config_changed,
            judge_config_changed=head.judge_config_changed,
            rejudged=head.rejudged,
        ),
        exit_code=exit_code(head),
    )


def record(
    store: FileResultStore,
    suite: Suite,
    key: str,
    *,
    disposition: str,
    recorded_at: str,
) -> tuple[RegisterEntry, Path]:
    """Append one disposition to the suite's register, and say where.

    Mandatory, with no default: a defaulted disposition is a disposition nobody
    gave. An unjudged run may be recorded — rejecting a run that could not be
    judged is a real act — and a suite with no baseline may not, because there
    is no verdict to have decided about.
    """
    if disposition not in DISPOSITIONS:
        raise UsageError(
            f"disposition {disposition!r} is not one of {', '.join(DISPOSITIONS)}"
        )
    run = read_run(store, suite, key)
    baseline = need_baseline(store, suite)
    entry = entry_for(
        run,
        key,
        baseline,
        store.key_for(baseline),
        # Narrowed by the membership check above: `in DISPOSITIONS` over a tuple
        # of literals is a check pyright reads as the literal type itself.
        disposition=disposition,
        recorded_at=recorded_at,
        digline_version=__version__,
    )
    try:
        store.append_register(suite.tenant, suite.name, entry)
    except RegisterRefusedError as exc:
        raise UsageError(str(exc)) from exc
    return entry, store.register_path(suite.tenant, suite.name)
