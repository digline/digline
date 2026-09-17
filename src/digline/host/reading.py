"""Two readings, composed once for both front ends. (ADR 0020 §5, §8)

`cmd_explain` and the MCP `explain` tool held a run against the store's
baseline the same way, and `digline log` and the MCP `log` tool read the same
history. Composed twice, they are two answers waiting to happen; composed here,
in the layer both front ends already sit on (ADR 0011 §7), they are one.

The window bounds are normalised here too, because this is the layer allowed
to know what a time zone is: the fold below compares strings, and only strings
of one shape compare as instants.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from digline.core import Run, compare
from digline.host.errors import UsageError
from digline.host.resolve import read_run
from digline.report import (
    Fact,
    IdentityLog,
    facts,
    headline,
    identity_log,
    scale_lost,
    unjudged_cases,
)
from digline.run import Suite
from digline.store import FileResultStore, Register, RegisterRefusedError
from digline.wire import EXIT_OK, EXIT_UNJUDGED, exit_code

__all__ = ["Explained", "explained", "history", "instant"]

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


def explained(store: FileResultStore, suite: Suite, key: str) -> Explained:
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
        code = EXIT_UNJUDGED if unjudged_cases(run) or scale_lost(run) else EXIT_OK
        return Explained(run, None, facts(run), "run", code)
    comparison = compare(run, baseline)
    head = headline(comparison, run, baseline, locale="en")
    return Explained(
        run, baseline, facts(run, comparison), "comparison", exit_code(head)
    )


def history(
    store: FileResultStore, suite: Suite, *, since: str = "", until: str = ""
) -> IdentityLog:
    """Every readable run of the suite, folded into the identity reading.

    What the scan could not read is passed on as counts, so the reading can say
    *N runs were not read* instead of describing a shorter history.

    The register rides along (ADR 0021 §8). A register that cannot be read is
    not a reason to refuse the reading of the runs: it is passed on as a flag,
    and the reading says so rather than showing an empty register.
    """
    listing = store.scan_runs(suite.tenant, suite.name)
    rows = [(ref.key, store.read_run(ref)) for ref in listing.runs]
    baseline = store.read_baseline(suite.tenant, suite.name)
    try:
        register = store.read_register(suite.tenant, suite.name)
        register_unreadable = False
    except RegisterRefusedError:
        register, register_unreadable = Register(), True
    return identity_log(
        rows,
        tenant=suite.tenant,
        suite=suite.name,
        since=since,
        until=until,
        skipped=listing.skipped,
        unreadable=len(listing.unreadable),
        baseline=None if baseline is None else (store.key_for(baseline), baseline),
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
