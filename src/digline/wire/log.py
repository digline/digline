"""What `digline log` says to a program: the identity reading, and no prose.

The other rendering of `digline.report.log`'s reading, as `explain_json` is of
the fact list. It adds nothing and filters nothing, and it does not have to:
the fold already reduced every configuration with `SystemConfig.redacted()`
before a span existed, so a perimeter field never reaches a shape here to be
left out of (ADR 0020 §6).

**No score crosses here, because none exists.** The types have no field a
measurement could occupy (ADR 0020 §4), and no case id either — the reading is
about the system, and has no reason to name a case.
"""

from __future__ import annotations

from digline.core import RegisterEntry
from digline.report.log import IdentityLog, IdentitySpan, Roll, Sighting
from digline.wire.contract import OUTPUT_VERSION

__all__ = [
    "log_json",
    "register_entry_json",
    "roll_json",
    "sighting_json",
    "span_json",
]


def sighting_json(found: Sighting) -> dict[str, object]:
    """One side of one run. `answered` is null exactly when `absence` names why."""
    return {
        "provider": found.provider,
        "sent": list(found.sent),
        "answered": found.answered,
        "absence": found.absence,
    }


def span_json(span: IdentitySpan) -> dict[str, object]:
    return {
        "side": span.side,
        "provider": span.provider,
        "sent": list(span.sent),
        "answered": span.answered,
        "absence": span.absence,
        "first_seen": span.first_seen,
        "last_seen": span.last_seen,
        "runs": span.runs,
        "environments": list(span.environments),
    }


def roll_json(roll: Roll) -> dict[str, object]:
    """A roll carries a window and never a moment: `last_before` and
    `first_after` bound it, and `silent_between` says how much went unrecorded
    inside it."""
    return {
        "side": roll.side,
        "provider": roll.provider,
        "sent": roll.sent,
        "before": roll.before,
        "after": roll.after,
        "last_before": roll.last_before,
        "first_after": roll.first_after,
        "silent_between": roll.silent_between,
    }


def register_entry_json(entry: RegisterEntry) -> dict[str, object]:
    """One recorded disposition, in the register's own shape without its format
    number.

    **The one named exception to "the wire never learns its name"** (ADR 0021
    §8): the register enters the wire here, and only here, while the decision
    journal and `.pending/` stay unknown to it. What crosses is what the value
    can hold — counts and keys, by type — so there is nothing to leave out.
    """
    outcome = entry.outcome
    return {
        "recorded_at": entry.recorded_at,
        "digline_version": entry.digline_version,
        "disposition": entry.disposition,
        "run": {
            "key": entry.run_key,
            "created_at": entry.run_created_at,
            "config_hash": entry.run_config_hash,
            "environment": entry.run_environment,
            "digline_version": entry.run_digline_version,
            "rejudged": entry.run_rejudged,
        },
        "baseline": {
            "key": entry.baseline_key,
            "config_hash": entry.baseline_config_hash,
            "promoted_at": entry.baseline_promoted_at or None,
        },
        "outcome": {
            "regressed": outcome.regressed,
            "improved": outcome.improved,
            "unchanged": outcome.unchanged,
            "new": outcome.new,
            "missing": outcome.missing,
            "errored": outcome.errored,
            "unjudged": outcome.unjudged,
            "suspended": outcome.suspended,
            "within_noise": outcome.within_noise,
            "on_the_line": outcome.on_the_line,
            "worse": outcome.worse,
            "canary_moved": outcome.canary_moved,
            "config_changed": outcome.config_changed,
            "artifacts_changed": outcome.artifacts_changed,
            "target_config_changed": outcome.target_config_changed,
            "judge_config_changed": outcome.judge_config_changed,
            "rejudged": outcome.rejudged,
        },
        "exit_code": entry.exit_code,
    }


def log_json(log: IdentityLog) -> dict[str, object]:
    """The whole reading, for a program.

    `runs` is the count **read in this store**, and a `0` is stated rather than
    folded into an empty list of rolls: a runner with no history and a history
    with no roll are different facts, and a consumer must not have to deduce
    which one it is holding.

    There is no `exit_code`. `log` is not a gate — a roll is a fact about the
    system, and the verdict about a suite belongs to `compare` (ADR 0020 §5).
    """
    reference = log.reference
    return {
        "output_version": OUTPUT_VERSION,
        "tenant": log.tenant,
        "suite": log.suite,
        "window": {"since": log.since or None, "until": log.until or None},
        "runs": log.runs,
        "first": log.first or None,
        "last": log.last or None,
        "spans": [span_json(span) for span in log.spans],
        "rolls": [roll_json(roll) for roll in log.rolls],
        "replays": [
            {"key": r.key, "created_at": r.created_at, "source": r.source}
            for r in log.replays
        ],
        "skipped": {str(version): n for version, n in sorted(log.skipped.items())},
        "unreadable": log.unreadable,
        "reference": (
            None
            if reference is None
            else {
                "key": reference.key,
                "created_at": reference.created_at,
                # Empty where the reference was promoted before the field
                # existed: *not recorded*, and never filled in from git.
                "promoted_at": reference.promoted_at or None,
                "target": sighting_json(reference.target),
                "judge": sighting_json(reference.judge),
            }
        ),
        "register": [register_entry_json(entry) for entry in log.register],
        "register_torn": log.register_torn,
        "register_unreadable": log.register_unreadable,
    }
