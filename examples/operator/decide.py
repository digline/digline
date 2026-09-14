"""The judgment seat: whether this cycle wakes anybody, and under which clause.

`loop.py` classifies — clean, draw, drift, structural, system error — and that
does not move: it is deterministic, reproducible, and four tests hold it. What
this file decides is the question a classification cannot answer on its own,
which is whether *this* drift, *this* week, is worth a person's evening.

    python decide.py --cycle cycle.json --config operator.toml --out decision.json

The rule the whole file is built around:

> A reason that cites no clause is the model's opinion; a reason that cites one
> is the policy being exercised.

So there is no branch in which this holds a cycle because the week looked
quiet. Either one clause accounts for everything that would have woken
somebody — and the decision names it — or the verdict's own escalation stands.

**No model is called here.** The seat is deterministic given a cycle and a
policy, which is what lets a decision be re-derived by anyone holding both.
Layer 3 of the alert is still the only part a model writes, and it interprets
this rather than producing it.
"""

from __future__ import annotations

import argparse
import json
import tomllib
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from journal import JOURNAL_VERSION, append, holds_in_a_row, journal_path, read_journal
from policy import QUIET, Policy, PolicyError, digest_of, load_policy

#: The shape of `decision.json`. The example's own file, like `CYCLE_FORMAT`.
DECISION_FORMAT = 1

#: The cycle shape this can read. A cycle written before the seat existed
#: carries no tenant and no policy digest, so it is refused by name rather than
#: decided about on a guess.
NEEDS_CYCLE_FORMAT = 4

#: The three floors, in the words a decision reports them by. No clause lowers
#: any of them, and the list is closed: a fourth would be a new decision, taken
#: in a record, and not a key somebody added.
FLOOR_CANARY = "canary"
FLOOR_UNJUDGED = "unjudged"
FLOOR_DIGEST = "policy-moved"


# --------------------------------------------------------------------------- #
# What would wake somebody
# --------------------------------------------------------------------------- #


def _facts(run: Mapping[str, Any], about: str) -> list[Mapping[str, Any]]:
    facts = cast("Sequence[Mapping[str, Any]]", run["explain"]["facts"])
    return [fact for fact in facts if fact["about"] == about]


def _regressed(run: Mapping[str, Any]) -> list[tuple[str, str, str]]:
    """`(case_id, assertion, assertion_id)` for every check that got worse."""
    return [
        (str(f["case_id"]), str(f["assertion"]), str(f["assertion_id"]))
        for f in _facts(run, "check")
        if f["kind"] == "regressed"
    ]


def _canary_moved(cycle: Mapping[str, Any]) -> bool:
    """Whether any run of this cycle reports a canary that moved.

    `explain` states the canary tally **only** when one did — silent otherwise,
    like the judge clause — so its presence is the fact and no count has to be
    read. A canary outside its interval is evidence about *which system
    answered*, and re-running cannot settle it: the second run asks the same
    alias the same thing.
    """
    return any(
        fact["kind"] == "canary" and fact.get("state") is True
        for run in cast("Sequence[Mapping[str, Any]]", cycle["runs"])
        for fact in _facts(run, "run")
    )


def escalating(cycle: Mapping[str, Any]) -> list[tuple[str, str, str]]:
    """Everything a clause would have to account for to hold this cycle.

    Derived from the classification rather than re-derived from the facts: a
    drift is what repeated in *every* run, and a structural flip is what one run
    showed. Reading these differently here would be a second opinion about what
    the cycle was, which is exactly what `loop.py` exists to settle.
    """
    runs = cast("Sequence[Mapping[str, Any]]", cycle["runs"])
    verdict = str(cycle["verdict"])
    if verdict == "structural":
        return _regressed(runs[0])
    if verdict == "drift":
        # `reproduced` carries the pairs; the identity comes from the run that
        # reported them, so a clause may be written against either.
        identities = {
            (case, assertion): assertion_id
            for case, assertion, assertion_id in _regressed(runs[0])
        }
        return [
            (str(case), str(assertion), identities.get((str(case), str(assertion)), ""))
            for case, assertion in cast("Sequence[Sequence[str]]", cycle["reproduced"])
        ]
    return []


# --------------------------------------------------------------------------- #
# The decision
# --------------------------------------------------------------------------- #


def _moment(policy: Policy | None, now: datetime) -> tuple[str, bool | None]:
    """When this was decided, and whether that was inside the quiet window.

    The window is recorded whether or not a clause uses it. A decision that
    turns on the hour is reviewable only if the hour it turned on is written
    down — which is the whole reason this file is allowed to read a clock at
    all.
    """
    stamp = now.astimezone(UTC).isoformat(timespec="seconds")
    if policy is None or policy.quiet_hours is None:
        return stamp, None
    try:
        zone = ZoneInfo(policy.quiet_hours.tz)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise PolicyError(
            f"[policy] quiet_hours.tz is {policy.quiet_hours.tz!r}, which this "
            "machine has no zone for. A window nobody can place is a window "
            "nobody can reproduce."
        ) from exc
    return stamp, policy.quiet_hours.covers(now.astimezone(zone).time())


def decide(
    cycle: Mapping[str, Any],
    policy: Policy | None,
    *,
    on_disk: str,
    records: Sequence[Mapping[str, Any]],
    now: datetime,
    streak_known: bool = True,
) -> dict[str, Any]:
    """The seat. A cycle and a policy in, a decision out — and no model.

    `streak_known` is False when the journal *should* hold earlier cycles and
    could not be produced — a hosted runner whose restore failed. `records` is
    then empty for a reason that is not "nothing happened", and a clause with
    `max_cycles` cannot count against it: an empty history read as a streak of
    zero would let that clause hold forever, one cycle at a time.
    """
    verdict = str(cycle["verdict"])
    proposed = bool(cycle["escalate"])
    wanted = escalating(cycle)
    evaluated_at, quiet = _moment(policy, now)

    decision: dict[str, Any] = {
        "decision_format": DECISION_FORMAT,
        "verdict": verdict,
        "verdict_escalates": proposed,
        "escalate": proposed,
        "clause": None,
        "floor": None,
        "reason": "",
        "evaluated_at": evaluated_at,
        "in_quiet_hours": quiet,
        "facts": [[case, assertion] for case, assertion, _id in wanted],
        "policy": (
            None
            if policy is None
            else {
                "name": policy.name,
                "digest": policy.digest,
                "quiet_hours": (
                    None if policy.quiet_hours is None else policy.quiet_hours.as_json()
                ),
            }
        ),
    }

    if not proposed:
        decision["reason"] = (
            f"The cycle is {verdict} and the classification wakes nobody. "
            "No clause was consulted."
        )
        return decision

    # ---- the floors, in the order a reader meets them ---------------------- #
    recorded = str(cast("Mapping[str, Any]", cycle["policy"])["digest"])
    if policy is not None and recorded != on_disk:
        decision["floor"] = FLOOR_DIGEST
        decision["reason"] = (
            f"The policy moved between the run and this decision: the cycle was "
            f"measured under {recorded} and the file on disk is {on_disk}. A "
            "hold taken under a policy nobody can produce is not a hold, so the "
            "classification stands."
        )
        return decision
    if _canary_moved(cycle):
        decision["floor"] = FLOOR_CANARY
        decision["reason"] = (
            "A canary moved, so no clause may hold this cycle: the score is a "
            "fingerprint of which model answered rather than a measure of "
            "quality, and re-running asks the same alias the same thing."
        )
        return decision
    if verdict == "system-error":
        decision["floor"] = FLOOR_UNJUDGED
        decision["reason"] = (
            "The run could not be judged, so no clause may hold this cycle: "
            "nothing downstream of an unjudged run is meaningful, the green "
            "checks beside it included."
        )
        return decision

    if policy is None:
        decision["reason"] = (
            f"The cycle is {verdict} and there is no policy, so the "
            "classification stands."
        )
        return decision

    # ---- one clause, and it has to cover everything ------------------------ #
    for clause in policy.clauses:
        if clause.verdict is not None and clause.verdict != verdict:
            continue
        if clause.during == QUIET and not quiet:
            continue
        if not wanted or not all(
            clause.covers(case, assertion, assertion_id)
            for case, assertion, assertion_id in wanted
        ):
            continue
        if clause.max_cycles is not None and not streak_known:
            decision["reason"] = (
                f"`{clause.name}` allows {clause.max_cycles} cycle(s), and its "
                "streak is unknown: the decision journal could not be restored, "
                "so this cycle cannot be shown to be within it. A streak nobody "
                "can count is not a streak of zero, so this one wakes somebody."
            )
            return decision
        held = holds_in_a_row(records, clause.name)
        if clause.max_cycles is not None and held >= clause.max_cycles:
            decision["reason"] = (
                f"`{clause.name}` has held this for {held} cycle(s) and allows "
                f"{clause.max_cycles}. A dip that is still here is not a dip, "
                "so this one wakes somebody."
            )
            return decision
        decision["escalate"] = False
        decision["clause"] = clause.name
        span = (
            ""
            if clause.max_cycles is None
            else f" ({held + 1} of {clause.max_cycles} allowed)"
        )
        decision["reason"] = f"Held by `{clause.name}`{span}: {clause.because}."
        return decision

    decision["reason"] = (
        f"The cycle is {verdict} and no single clause accounts for all of it, "
        "so the classification stands. A hold is one clause's responsibility."
    )
    return decision


def record_of(cycle: Mapping[str, Any], decision: Mapping[str, Any]) -> dict[str, Any]:
    """One journal line. The two label fields are born empty, and that is the
    question `answer.py` asks."""
    runs = cast("Sequence[Mapping[str, Any]]", cycle["runs"])
    policy = cast("Mapping[str, Any] | None", decision["policy"])
    return {
        "journal_version": JOURNAL_VERSION,
        "cycle_key": str(runs[0]["key"]),
        "decided_at": decision["evaluated_at"],
        "policy": None if policy is None else policy["name"],
        "policy_digest": None if policy is None else policy["digest"],
        "verdict": decision["verdict"],
        "verdict_escalates": decision["verdict_escalates"],
        "escalate": decision["escalate"],
        "clause": decision["clause"],
        "floor": decision["floor"],
        "reason": decision["reason"],
        "in_quiet_hours": decision["in_quiet_hours"],
        "facts": decision["facts"],
        # Asked later, by a person, about a hold as much as an escalation.
        "wanted": None,
        "answered_at": None,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cycle", default="cycle.json", type=Path)
    parser.add_argument("--config", default="operator.toml", type=Path)
    parser.add_argument("--out", default="decision.json", type=Path)
    parser.add_argument(
        "--now",
        default=None,
        help="ISO-8601, for a reproducible decision; defaults to the clock",
    )
    parser.add_argument(
        "--streak-unknown",
        action="store_true",
        help=(
            "the journal of earlier cycles could not be restored, so no "
            "clause's streak is known and none with max_cycles may hold"
        ),
    )
    args = parser.parse_args(argv)

    root = Path(args.config).resolve().parent
    cycle = cast(
        "Mapping[str, Any]",
        json.loads(Path(args.cycle).read_text(encoding="utf-8")),
    )
    if int(cycle.get("cycle_format", 0)) < NEEDS_CYCLE_FORMAT:
        raise SystemExit(
            f"{args.cycle} is cycle_format "
            f"{cycle.get('cycle_format', 'unset')}, and the seat needs "
            f"{NEEDS_CYCLE_FORMAT}: a cycle written before the policy existed "
            "carries neither the tenant nor the digest a decision is taken "
            "under. Re-run the loop."
        )

    with Path(args.config).open("rb") as handle:
        document = cast("Mapping[str, Any]", tomllib.load(handle))
    policy = load_policy(document)
    # The fourth check's other half: the digest of what is on disk *now*,
    # against what the cycle recorded having been measured under.
    on_disk = "" if policy is None else digest_of(document["policy"])

    path = journal_path(root, str(cycle["tenant"]), Path(str(cycle["suite"])).stem)
    records = read_journal(path)
    now = (
        datetime.now(UTC) if args.now is None else datetime.fromisoformat(str(args.now))
    )

    decision = decide(
        cycle,
        policy,
        on_disk=on_disk,
        records=records,
        now=now,
        streak_known=not args.streak_unknown,
    )
    Path(args.out).write_text(
        json.dumps(decision, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    # Written whatever it says. A hold nobody records is indistinguishable from
    # a cycle that never ran.
    append(path, record_of(cycle, decision))

    cited = "" if decision["clause"] is None else f" [{decision['clause']}]"
    print(
        f"decision: {'escalate' if decision['escalate'] else 'hold'}{cited} — "
        f"{decision['reason']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
