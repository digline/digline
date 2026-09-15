"""A person's disposition about a comparison, as a value. (ADR 0021)

Defined in the core for the reason `CaseProgress` is (ADR 0017 §4): the host
builds it, the store persists it and the reading renders it, and the store may
import neither of the other two. A pure value made of plain types is what the
core is for.

**Counts and keys, by type.** There is no field a case id, a reason, a sentence,
free text or an author could occupy (ADR 0021 §3). In the material this was
checked against, case ids are content with a hyphen in it; the register records
*how much* moved, and the run it names says *what*. The reason for a disposition
is the commit message of the commit that adds it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

__all__ = ["DISPOSITIONS", "Disposition", "RecordedOutcome", "RegisterEntry"]

#: The shape of the decision journal's `wanted` (ADR 0019 §10), for its reason:
#: `unsure` is *I read it and could not decide*, which is a different fact from
#: *nobody read it*, and a register that could not say the first would turn it
#: into the second.
type Disposition = Literal["accepted", "rejected", "unsure"]

DISPOSITIONS: tuple[Disposition, ...] = ("accepted", "rejected", "unsure")


@dataclass(frozen=True, slots=True)
class RecordedOutcome:
    """The verdict a disposition was taken against: `Headline`'s facts, minus the
    one that is prose.

    The sentence is left out on purpose — it names the canary case that moved
    and the files that changed, which are the identifiers this value refuses.
    """

    regressed: int
    improved: int
    unchanged: int
    new: int
    missing: int
    errored: int
    unjudged: int
    suspended: int
    within_noise: int
    on_the_line: int
    worse: bool
    canary_moved: bool
    config_changed: bool
    artifacts_changed: bool
    target_config_changed: bool
    judge_config_changed: bool
    rejudged: bool


@dataclass(frozen=True, slots=True)
class RegisterEntry:
    """One line of the register: what a person decided, and about what.

    `baseline_promoted_at` is empty where the reference was promoted before the
    field existed — *not recorded*, and never filled in from git. `digline_version`
    is the digline that computed the comparison, because what a comparison
    returns for a given pair has moved between releases.
    """

    recorded_at: str
    digline_version: str
    disposition: Disposition
    run_key: str
    run_created_at: str
    run_config_hash: str
    run_environment: str
    run_digline_version: str
    run_rejudged: bool
    baseline_key: str
    baseline_config_hash: str
    baseline_promoted_at: str
    outcome: RecordedOutcome
    exit_code: int

    def __post_init__(self) -> None:
        if self.disposition not in DISPOSITIONS:
            raise ValueError(
                f"disposition {self.disposition!r} is not one of "
                f"{', '.join(DISPOSITIONS)}: a disposition nobody can read back "
                "is a disposition nobody gave"
            )
        for name in ("recorded_at", "run_key", "baseline_key"):
            if not getattr(self, name):
                raise ValueError(f"RegisterEntry.{name} must not be empty")
