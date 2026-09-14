"""The escalation policy: what the operator reads and never decides.

`operator.toml` has always held the four numbers an agent could otherwise talk
itself into. This is the grown-up form of the same idea: the rules that decide
**who is woken**, as data, beside the rules that decide what is run.

One module rather than two, and `loop.py` and `decide.py` both import it. The
digest a cycle reports and the digest a decision is taken under have to be the
same function, or a cycle can name a policy it did not apply — which is the one
failure this artifact exists to make impossible.

Three things this file refuses, and each is a rule from the record:

- **an unknown key**, naming it and the ones that exist. A silently dropped
  clause key is a hold nobody declared;
- **a key that names payload** — `vars`, an output, a reason, an artifact. A
  clause may name identifiers and never contents, because whatever a clause
  names ends up written into the journal, cycle after cycle;
- **a key that would raise a floor** — `max_reruns` and its neighbours. The
  policy may only narrow, so the keys that widen are absent rather than
  refused at use.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import time
from typing import Any, cast

#: The shape of a policy, so a reader can tell when it moved. The policy is the
#: example's own artifact, like `CYCLE_FORMAT`, and separate from anything the
#: tool versions.
POLICY_FORMAT = 1

#: What a clause may say. Everything here is an **identifier** or a number:
#: nothing in this list can carry the customer's data, which is what makes the
#: journal safe to keep forever.
MATCH_KEYS = ("verdict", "case", "assertion", "assertion_id", "aggregate")
CLAUSE_KEYS = frozenset({"name", "because", "max_cycles", "during", *MATCH_KEYS})

#: Keys that would name contents rather than identifiers. Refused by name, with
#: their own sentence, because "unknown key" would be a true answer to the
#: wrong question — the author was not misspelling something, they were
#: reaching for the payload.
PAYLOAD_KEYS = frozenset(
    {"vars", "output", "text", "reason", "artifact", "prompt", "input", "expected"}
)

#: Keys that belong to the stopping rule and the budget, which the policy may
#: not reach. They are absent from `CLAUSE_KEYS` anyway; naming them here is
#: what turns a puzzling "unknown key" into the sentence that says why.
FLOOR_KEYS = frozenset({"max_reruns", "structural_flip_cases", "max_target_calls"})

#: The one value `during` takes today. A clause that names the window applies
#: only inside it; one that does not applies whenever it matches.
QUIET = "quiet_hours"


class PolicyError(ValueError):
    """A policy that cannot be read. Raised at load, before anything is run."""


@dataclass(frozen=True, slots=True)
class QuietHours:
    """The window a decision records having been taken in.

    Recorded whether or not any clause uses it: a decision that turns on the
    hour is reviewable only if the hour it turned on is written down.
    """

    start: time
    end: time
    tz: str

    def covers(self, moment: time) -> bool:
        """Inclusive of the start, exclusive of the end, and it wraps midnight —
        which is the ordinary case for a quiet window and the one a naive
        comparison gets wrong."""
        if self.start <= self.end:
            return self.start <= moment < self.end
        return moment >= self.start or moment < self.end

    def as_json(self) -> dict[str, str]:
        return {
            "from": self.start.isoformat(timespec="minutes"),
            "to": self.end.isoformat(timespec="minutes"),
            "tz": self.tz,
        }


@dataclass(frozen=True, slots=True)
class Clause:
    """One reason a cycle may not wake anybody, with the name it is cited by."""

    name: str
    because: str
    verdict: str | None = None
    case: str | None = None
    assertion: str | None = None
    assertion_id: str | None = None
    aggregate: str | None = None
    max_cycles: int | None = None
    during: str | None = None

    def covers(self, case_id: str, assertion: str, assertion_id: str) -> bool:
        """Whether this clause accounts for one escalating check.

        Every declared key has to agree. A clause naming a case and an
        assertion covers that pair and not the case's other checks — which is
        the strict reading, and the one that keeps a narrow clause from
        absorbing a regression nobody looked at.
        """
        if self.case is not None and self.case != case_id:
            return False
        if self.assertion is not None and self.assertion != assertion:
            return False
        if self.assertion_id is not None and self.assertion_id != assertion_id:
            return False
        # An aggregate is a run-scoped check, which carries an empty case id.
        return not (self.aggregate is not None and self.aggregate != assertion)


@dataclass(frozen=True, slots=True)
class Policy:
    """The parsed `[policy]` table, and the identity a cycle reports."""

    name: str
    digest: str
    clauses: tuple[Clause, ...]
    quiet_hours: QuietHours | None = None

    def clause(self, name: str) -> Clause | None:
        return next((c for c in self.clauses if c.name == name), None)


# --------------------------------------------------------------------------- #
# Reading it
# --------------------------------------------------------------------------- #


def digest_of(table: Mapping[str, Any]) -> str:
    """The identity of a policy, over the **parsed** document.

    Not over the file's bytes, and the difference is the whole point: reflowing
    a comment must not move an identity, and two policies that say the same
    thing must have the same one. It is `Suite.cases_digest()`'s move, for the
    same reason — a digest that churned would make every cycle report a change
    nobody made.

    It never joins `config_hash` and is never written to a run document. A
    policy judges the measurement; it does not change what was measured.
    """
    payload = json.dumps(table, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _hhmm(value: object, field: str) -> time:
    text = str(value)
    try:
        hour, minute = (int(part) for part in text.split(":", 1))
        return time(hour=hour, minute=minute)
    except ValueError as exc:
        raise PolicyError(
            f"[policy] quiet_hours.{field} is {text!r}, which is not a time of "
            "day. Write it as HH:MM, in 24-hour form."
        ) from exc


def _quiet_hours(raw: object) -> QuietHours:
    if not isinstance(raw, dict):
        raise PolicyError("[policy] quiet_hours must be a table: { from, to, tz }")
    table = cast("dict[str, object]", raw)
    missing = {"from", "to", "tz"} - set(table)
    if missing:
        raise PolicyError(
            f"[policy] quiet_hours is missing {', '.join(sorted(missing))}. A "
            "window with no zone is a window nobody can reproduce."
        )
    return QuietHours(
        start=_hhmm(table["from"], "from"),
        end=_hhmm(table["to"], "to"),
        tz=str(table["tz"]),
    )


def _clause(raw: object, index: int) -> Clause:
    where = f"[[policy.hold]] #{index}"
    if not isinstance(raw, dict):
        raise PolicyError(f"{where} is not a table")
    entry = cast("dict[str, object]", raw)

    for key in sorted(entry):
        if key in CLAUSE_KEYS:
            continue
        if key in PAYLOAD_KEYS:
            raise PolicyError(
                f"{where}: `{key}` names the contents of a case, not a case. A "
                "clause may name identifiers — a case id, an assertion, an "
                "aggregate — and never what the system said or was asked, "
                "because whatever a clause names is written into the decision "
                "journal on every cycle."
            )
        if key in FLOOR_KEYS:
            raise PolicyError(
                f"{where}: `{key}` belongs to the stopping rule, not to the "
                "policy. The policy may only narrow what wakes somebody; it "
                "cannot raise what the loop is allowed to spend or re-run. "
                "Change it in [stopping_rule] or [budget], deliberately."
            )
        raise PolicyError(
            f"{where}: unknown key `{key}`. A clause takes: "
            f"{', '.join(sorted(CLAUSE_KEYS))}."
        )

    for required in ("name", "because"):
        if not str(entry.get(required, "")).strip():
            raise PolicyError(
                f"{where} has no `{required}`. A clause is cited by name in "
                "every decision it rules, and `because` is the sentence "
                "whoever reads the diff needs."
            )

    if not any(key in entry for key in MATCH_KEYS):
        raise PolicyError(
            f"{where} declares nothing to match on. A clause that matches "
            "everything is a policy that holds everything, which is a pager "
            f"nobody is carrying. Declare one of: {', '.join(MATCH_KEYS)}."
        )

    during = entry.get("during")
    if during is not None and str(during) != QUIET:
        raise PolicyError(f"{where}: `during` takes {QUIET!r} and nothing else today.")

    cycles = entry.get("max_cycles")
    if cycles is not None and (not isinstance(cycles, int) or cycles < 1):
        raise PolicyError(f"{where}: `max_cycles` is a count of cycles, so at least 1")

    return Clause(
        name=str(entry["name"]),
        because=str(entry["because"]),
        verdict=None if "verdict" not in entry else str(entry["verdict"]),
        case=None if "case" not in entry else str(entry["case"]),
        assertion=None if "assertion" not in entry else str(entry["assertion"]),
        assertion_id=(
            None if "assertion_id" not in entry else str(entry["assertion_id"])
        ),
        aggregate=None if "aggregate" not in entry else str(entry["aggregate"]),
        max_cycles=None if cycles is None else int(cycles),
        during=None if during is None else str(during),
    )


def load_policy(document: Mapping[str, Any]) -> Policy | None:
    """The `[policy]` table of a parsed `operator.toml`, or `None` where there
    is none.

    A configuration with no policy is not an error and never becomes one: the
    cycle then escalates exactly as the verdict says, which is what the loop
    did before this file existed.
    """
    raw = document.get("policy")
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise PolicyError("[policy] must be a table")
    table = cast("dict[str, Any]", raw)

    known = {"name", "quiet_hours", "hold"}
    unknown = sorted(set(table) - known)
    if unknown:
        raise PolicyError(
            f"[policy]: unknown key `{unknown[0]}`. It takes: "
            f"{', '.join(sorted(known))}."
        )
    if not str(table.get("name", "")).strip():
        raise PolicyError(
            "[policy] has no `name`. A cycle reports the policy that ruled it, "
            "and a policy with no name cannot be reported."
        )

    holds = table.get("hold", [])
    if not isinstance(holds, list):
        raise PolicyError("[[policy.hold]] must be an array of tables")
    clauses = tuple(
        _clause(entry, index)
        for index, entry in enumerate(cast("Sequence[object]", holds), start=1)
    )
    names = [clause.name for clause in clauses]
    duplicated = sorted({name for name in names if names.count(name) > 1})
    if duplicated:
        raise PolicyError(
            f"two clauses are called {duplicated[0]!r}. A decision cites a "
            "clause by name, so the names have to be unique or a journal line "
            "cannot say which one ruled it."
        )

    return Policy(
        name=str(table["name"]),
        digest=digest_of(table),
        clauses=clauses,
        quiet_hours=(
            None if "quiet_hours" not in table else _quiet_hours(table["quiet_hours"])
        ),
    )
