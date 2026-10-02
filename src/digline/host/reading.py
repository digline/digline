"""Three readings, composed once for every front end. (ADR 0020 §5, §8)

`cmd_explain` and the MCP `explain` tool held a run against the store's
baseline the same way, and `digline log` and the MCP `log` tool read the same
history. Composed twice, they are two answers waiting to happen; composed here,
in the layer both front ends already sit on (ADR 0011 §7), they are one.

`reported` is the third, and the only one that produces a document: the report
`digline report` prints, composed here so a second front end renders it the
same way, redaction included. Printing it, or writing it to a file, stays with
the front end, which is the only layer allowed to do either.

The window bounds are normalised here too, because this is the layer allowed
to know what a time zone is: the fold below compares strings, and only strings
of one shape compare as instants.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Literal

from digline.core import Run, compare, key_of, redact, withhold_artifacts
from digline.host.errors import UsageError
from digline.host.listing import suite_runs
from digline.host.resolve import read_run
from digline.report import (
    Fact,
    IdentityLog,
    Locale,
    facts,
    headline,
    identity_log,
    render_html,
    render_run_html,
)
from digline.run import Suite
from digline.store import (
    FileResultStore,
    Register,
    RegisterRefusedError,
    ResultStore,
)
from digline.wire import exit_code, run_exit_code

__all__ = ["Explained", "Reported", "explained", "history", "instant", "reported"]

_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass(frozen=True, slots=True)
class Explained:
    """A run read back, and the reference it was read against if there is one.

    `run` and `baseline` ride along because the CLI warns when either came from
    a newer digline; the reading itself is `reading`, `scope` and `exit_code`.
    """

    run: Run
    baseline: Run | None
    reading: tuple[Fact, ...]
    scope: Literal["comparison", "run"]
    exit_code: int


def explained(store: ResultStore, suite: Suite, key: str) -> Explained:
    """The scope follows the store, never a flag (ADR 0012 §1).

    With no baseline, "worse" is a relation with nothing on the other side, so
    only an unjudged case or a lost scale can move the code. With one, the code
    is `compare`'s, computed by the same function. The headline is built in
    `en` because only its number is used, and the number does not depend on
    the locale.
    """
    run = read_run(store, suite, key)
    baseline = store.read_baseline(suite.tenant, suite.name)
    if baseline is None:
        # A lost scale needs no reference either: it compares a score with a
        # declared band, not with a past. (ADR 0024 §4.5)
        return Explained(run, None, facts(run), "run", run_exit_code(run))
    comparison = compare(run, baseline)
    head = headline(comparison, run, baseline, locale="en")
    return Explained(
        run, baseline, facts(run, comparison), "comparison", exit_code(head)
    )


@dataclass(frozen=True, slots=True)
class Reported:
    """The report, and the exit code its own contents account for.

    `run` is the run as read, never the redacted copy the document was rendered
    from, and it rides along with `baseline` for `Explained`'s reason: the front
    end warns when either came from a newer digline.
    """

    document: str
    exit_code: int
    run: Run
    baseline: Run | None


def reported(
    store: ResultStore, suite: Suite, key: str, *, locale: Locale, redacted: bool
) -> Reported:
    """The document `digline report` prints, composed where every front end can.

    Both keywords are mandatory. `locale` because this is a document with a
    recipient who did not choose English: the first locale in `host/` that
    reaches the reader, where `explained` and the register entry build `en` for
    a number only. `redacted` because whether a document is complete is decided
    by the caller, never inherited from a default.

    Comparative or not follows from whether a reference exists, never a flag.
    """
    read = read_run(store, suite, key)
    baseline = store.read_baseline(suite.tenant, suite.name)

    if baseline is None:
        # Not a refusal, and this is the whole point of the command existing.
        # `need_baseline` — which `compare` still uses, rightly — says "run it,
        # look at the result, then promote", and `report` *was* the only way to
        # look. Naming looking as the prerequisite for looking is a dead end,
        # and the first person to hit it is always someone on their first run.
        #
        # Automatic rather than a flag, for the reason `--redacted` is not a
        # choice about what the document says: complete or redacted follows
        # from `run.redacted`, and comparative or not follows from whether a
        # reference exists. A flag would have to be an error when a baseline is
        # present, and would leave the dead end intact for whoever has not yet
        # learned the flag.
        return _reported_single(read, suite, locale=locale, redacted=redacted)

    run = read
    comparison = compare(run, baseline)

    if redacted:
        # Applied to the input, so the document can never claim to be complete:
        # `render_html` reads `Run.redacted`, it is not told what to print.
        #
        # The artifact outcomes are the exception, and deliberately: they are
        # computed *here*, where both runs are in hand, then stripped of their
        # payload. A redacted run compared on its own reports `unknown` because
        # it has no digest and must not guess; this caller does not have to
        # guess, so the document can say that a file moved without saying what
        # it was. Decision 9 on a file instead of on a reason. (ADR 0003 §5)
        complete_artifacts = comparison.artifact_deltas
        run = redact(run, suite.disclosure)
        comparison = compare(run, baseline)
        if not suite.disclosure.artifacts:
            comparison = replace(
                comparison,
                artifact_deltas=withhold_artifacts(
                    replace(comparison, artifact_deltas=complete_artifacts)
                ).artifact_deltas,
            )

    document = render_html(comparison, run, baseline, locale=locale)
    # From the comparison the document was rendered from, never a fresh one:
    # over a redacted run a fresh `compare` has lost the digests, reads a moved
    # pin as `unknown`, and exits 0 under a page saying the file moved.
    code = exit_code(headline(comparison, run, baseline, locale=locale))
    return Reported(document, code, read, baseline)


def _reported_single(
    read: Run, suite: Suite, *, locale: Locale, redacted: bool
) -> Reported:
    """The run on its own, and an exit code that claims no more than it can.

    Never `EXIT_WORSE`: "worse" is a relation and there is nothing here to be
    worse than. `EXIT_UNJUDGED` survives, because a case the suite could not
    judge is a fact about the harness rather than about a reference — the
    partial contract mirrors what the document itself claims.
    """
    run = read
    if redacted:
        # No artifact-outcome rescue here, unlike the comparison path: those
        # outcomes are computed from two runs, and the reason that code exists
        # — a redacted run compared alone reports `unknown` — cannot arise
        # where nothing is compared.
        run = redact(run, suite.disclosure)

    document = render_run_html(run, locale=locale)
    # And so does a lost scale: a band is declared, not referenced. (ADR 0024
    # §4.5)
    return Reported(document, run_exit_code(run), read, None)


def history(
    store: FileResultStore, suite: Suite, *, since: str = "", until: str = ""
) -> IdentityLog:
    """Every readable run of the suite, folded into the identity reading.

    What the scan could not read is passed on as counts, so the reading can say
    *N runs were not read* instead of describing a shorter history. So is what
    the store refused to read after the scan passed it: the runs come through
    `suite_runs`, and until #314 one such run failed the whole reading.

    **A baseline that cannot be read still refuses the reading**, as it did
    before #314. The fold needs the baseline's run, not only its key, to count
    the run it names among those not read, and `suite_runs` keeps only the key.
    So it is read again here, bare.

    The register rides along (ADR 0021 §8). A register that cannot be read is
    not a reason to refuse the reading of the runs: it is passed on as a flag,
    and the reading says so rather than showing an empty register.
    """
    listed = suite_runs(store, suite.tenant, suite.name, mint=None)
    baseline = store.read_baseline(suite.tenant, suite.name)
    try:
        register = store.read_register(suite.tenant, suite.name)
        register_unreadable = False
    except RegisterRefusedError:
        register, register_unreadable = Register(), True
    return identity_log(
        listed.runs,
        tenant=suite.tenant,
        suite=suite.name,
        since=since,
        until=until,
        skipped=listed.skipped,
        unreadable=listed.unreadable_count,
        refused=len(listed.refused),
        baseline=(
            None
            if baseline is None
            else (key_of(baseline.created_at, baseline.config_hash), baseline)
        ),
        register=register.entries,
        register_torn=register.torn,
        register_unreadable=register_unreadable,
    )


def instant(value: str | None, *, name: str) -> str:
    """A window bound, as the fold compares it: a UTC date, or a UTC instant to
    the second. Empty stays empty — an open end.

    An instant with no time zone is refused rather than assumed: a stored
    `created_at` is UTC, and `2026-09-14T08:00` could be any of twenty-four
    hours of it. A date needs no zone, because it is compared as a day.
    """
    if not value:
        return ""
    if _DATE.match(value):
        try:
            datetime.strptime(value, "%Y-%m-%d")
        except ValueError as exc:
            raise UsageError(f"{name} {value!r} is not a calendar date") from exc
        return value
    try:
        moment = datetime.fromisoformat(value)
    except ValueError as exc:
        raise UsageError(
            f"{name} {value!r} is neither a date (2026-09-14) nor an ISO 8601 "
            "instant with a time zone (2026-09-14T08:00:00+02:00)"
        ) from exc
    if moment.tzinfo is None:
        raise UsageError(
            f"{name} {value!r} names no time zone. A stored run is dated in UTC, "
            "and an instant without a zone could be any hour of that day: add "
            "one, such as +00:00, or give a date."
        )
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S")
