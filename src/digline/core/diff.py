"""The two-run report: what differs between two runs neither of which was
approved by anybody.

A pure function, no I/O, callable without a driver — the same shape as
`compare()` and deliberately **not** the same vocabulary. `compare()` answers
*did it get worse?* against a promoted, reviewed baseline, and its words say so:
`regressed`, `improved`, `current`, `baseline`. Here there is no reference, so
there is no direction of travel, and every name in this module is symmetric:
`left` and `right`, `favours`, `differs`.

See `docs/adr/0008-the-two-run-report.md`. The three sentences it turns on:

- **A verdict exists only against an approved reference** (§1), so nothing here
  produces one and nothing built on it may gate.
- **Swapping the arguments swaps the columns and nothing else** (§2), which is a
  property of every value in this file and is tested as one.
- **A diff has no baseline, so no interval has the standing to command** (§4):
  the intervals are reported beside the count, never in place of it.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from digline.core.compare import (
    ArtifactDelta,
    ConfigDelta,
    Noise,
    Scope,
    artifact_deltas,
    config_deltas,
    index_verdicts,
)
from digline.core.run import Run
from digline.core.types import Verdict

__all__ = [
    "CheckDifference",
    "DiffOutcome",
    "Difference",
    "DifferentJudgesError",
    "DifferentSuitesError",
    "Favours",
    "diff",
]

#: Which run a difference favours, or neither. `neither` is not a hedge: an
#: errored check and a check present on one side only genuinely favour nobody,
#: and recording them as favouring the side that has a number would be counting
#: a missing measurement as a win.
type Favours = Literal["left", "right", "neither"]

#: What happened to one check across the two runs. Five words, all symmetric
#: under a swap — `only_left` and `only_right` exchange, the other three are
#: fixed points. There is deliberately no `flipped`: a flip is a *reason* a
#: check differs, carried as `CheckDifference.flipped`, not a sixth outcome
#: competing with the one that says whether it differs at all.
type DiffOutcome = Literal["differs", "same", "errored", "only_left", "only_right"]


class DifferentSuitesError(ValueError):
    """Raised when the two runs were produced under different suites.

    A `ValueError`, so the CLI's existing handler maps it to `EXIT_USAGE`
    without new plumbing, and so a caller that catches `ValueError` around
    `diff()` — as it already does around `compare()` — keeps working.
    """


class DifferentJudgesError(ValueError):
    """Raised when the two runs were not graded by the same instrument.

    Including the case where one side recorded no instrument and the other did.
    That is ADR 0005's `unknown`, and refusing on it is **not** reporting
    unknown-as-a-change — it is declining to report, which is the thing §5 of
    that ADR protects. `compare()` may not refuse, because it is the gate and
    the cure would be re-promoting a baseline; `diff()` may, because the cure is
    one re-run. (ADR 0008 §3)
    """


@dataclass(frozen=True, slots=True)
class CheckDifference:
    """One check, as the two runs answered it.

    `left` and `right` are the two verdicts, either of which may be absent. They
    are not `current` and `baseline`: neither run is the standard, and a field
    named `baseline` would make one of them the standard by grammar.

    `delta` is `right - left`, so it **negates** under a swap. That is the
    columns exchanging, not the fact changing, and it is what the symmetry
    property asserts.

    `tolerance` is `max(left, right)` — see `_tolerance` for why it is a max
    and not either side's own.

    `left_interval` and `right_interval` are the two measured intervals, and
    both are read. `compare()` reads one, the baseline's, because the baseline
    has the standing to say what its own noise is; here neither does, so both
    are reported and neither decides. `intervals_overlap` and
    `intervals_disjoint` are both false where either side is unsampled — the
    question was not answered, which is a third state and not a `False`.
    """

    case_id: str
    assertion: str
    #: `"run"` for a verdict about the whole run — precision, recall — which
    #: belongs to no case and carries an empty `case_id`.
    scope: Scope
    outcome: DiffOutcome
    left: Verdict | None
    right: Verdict | None
    favours: Favours
    #: `right - left`, or `None` where one side has no number to subtract.
    delta: float | None = None
    tolerance: float = 0.0
    #: Whether one run passes this check and the other does not. Always counts
    #: as a difference, whatever the delta: a tolerance is a statement about
    #: scores and a flip is a statement about outcomes. (ADR 0008 §4)
    flipped: bool = False
    left_interval: Noise = Noise()
    right_interval: Noise = Noise()
    intervals_overlap: bool = False
    intervals_disjoint: bool = False

    @property
    def differs(self) -> bool:
        return self.outcome != "same"

    @property
    def measured_on_both(self) -> bool:
        """Whether both sides recorded an interval, and so whether this check is
        in the population the "exceeds both intervals" sentence counts over."""
        return self.left_interval.known and self.right_interval.known


@dataclass(frozen=True, slots=True)
class Difference:
    """What differs between two runs. `checks` is ordered by (scope, case,
    assertion) so two equivalent reports read identically.

    The counts are properties rather than stored fields because there is no
    headline value here to store them on. `compare()` has `Headline`, which
    carries `worse`; a diff has no such object **and its absence is the point**
    (ADR 0008 §1) — nothing to serialise, so no `worse` field for a pipeline to
    find and gate on.
    """

    tenant: str
    suite: str
    #: Where each side ran. Reported, never constrained, exactly as in a
    #: comparison: two environments is a fact about the pair, not a mistake.
    left_environment: str = ""
    right_environment: str = ""
    checks: Sequence[CheckDifference] = ()
    #: What differs in the system that answered — the freedom §3 grants, and the
    #: reason the reader opened the report. `left` is `before` and `right` is
    #: `after`, so a swap exchanges the columns here too.
    target_config_deltas: Sequence[ConfigDelta] = ()
    #: What differs in the files that *are* the thing under test. (ADR 0003)
    artifact_deltas: Sequence[ArtifactDelta] = ()
    #: The instruments that graded — identical on both sides by §3, so this is
    #: one list rather than a delta. Printed as context, never as a change.
    judges: tuple[str, ...] = ()

    @property
    def total(self) -> int:
        return len(self.checks)

    @property
    def differing(self) -> int:
        return sum(1 for c in self.checks if c.differs)

    @property
    def favours_left(self) -> int:
        return sum(1 for c in self.checks if c.favours == "left")

    @property
    def favours_right(self) -> int:
        return sum(1 for c in self.checks if c.favours == "right")

    @property
    def within_tolerance(self) -> int:
        return sum(1 for c in self.checks if c.outcome == "same")

    @property
    def only_left(self) -> int:
        return sum(1 for c in self.checks if c.outcome == "only_left")

    @property
    def only_right(self) -> int:
        return sum(1 for c in self.checks if c.outcome == "only_right")

    @property
    def errored(self) -> int:
        return sum(1 for c in self.checks if c.outcome == "errored")

    @property
    def interval_pairs(self) -> int:
        """How many differing checks were measured on both sides.

        The population of the "exceeds both intervals" sentence. When it is zero
        the sentence is not printed at all — a suite at `samples=1` measured no
        intervals, and "0 of …" would report an absent measurement as a null
        result. (ADR 0008 §4)
        """
        return sum(1 for c in self.checks if c.differs and c.measured_on_both)

    @property
    def left_exceeds(self) -> int:
        """Differences favouring the left run whose two intervals are disjoint.

        The strongest honest figure: on these checks the left run scored higher
        *and* the difference is larger than the wobble either run showed. It is
        not a claim that the left run is better.
        """
        return sum(
            1 for c in self.checks if c.favours == "left" and c.intervals_disjoint
        )

    @property
    def right_exceeds(self) -> int:
        return sum(
            1 for c in self.checks if c.favours == "right" and c.intervals_disjoint
        )

    @property
    def systems_differ(self) -> bool:
        """Whether the two systems are known to have been configured
        differently. `unknown` is not a difference, for ADR 0005 §5's reason."""
        return any(
            d.outcome not in ("same", "unknown") for d in self.target_config_deltas
        )

    @property
    def artifacts_differ(self) -> bool:
        return any(d.outcome not in ("same", "unknown") for d in self.artifact_deltas)


def _tolerance(left: Verdict, right: Verdict) -> float:
    """The tolerance a difference is measured against: the larger of the two.

    By ADR 0008 §3 the two runs share a `config_hash`, which is built from the
    sorted `(identity, threshold, tolerance)` of every assertion — so for any
    paired check the two tolerances are the same value and this is a no-op.

    It is a `max` for the one case where they are not. A suite may declare the
    *same assertion identity twice with different tolerances*, which leaves the
    multiset equal on both sides while `index_verdicts`' occurrence counter
    could pair them across. Taking the max is swap-invariant — a requirement of
    §2, which a `left.tolerance` would break — and it reads in the only way the
    data supports: **a difference counts only if it exceeds both declared
    tolerances.**
    """
    return max(left.tolerance, right.tolerance)


def _overlap(left: Noise, right: Noise) -> tuple[bool, bool]:
    """`(overlap, disjoint)` for two intervals, and `(False, False)` where
    either side did not measure one.

    Two falses rather than one boolean, because "these intervals do not
    overlap" and "nobody measured an interval" are different facts and a single
    flag would collapse them into the one that sounds like a finding.

    Touching endpoints count as overlapping. A zero-width interval — five
    samples out of five agreeing, the ordinary case away from the boundary —
    then overlaps another that contains its point, which is right: the two runs
    are not distinguishable by a check that one of them never saw move.
    """
    if not (left.known and right.known):
        return False, False
    assert left.low is not None and left.high is not None
    assert right.low is not None and right.high is not None
    overlaps = left.low <= right.high and right.low <= left.high
    return overlaps, not overlaps


def _noise(verdict: Verdict) -> Noise:
    score = verdict.score
    if not score.sampled:
        return Noise()
    return Noise(score.sample_min, score.sample_max, len(score.samples))


def _refuse(left: Run, right: Run) -> None:
    """The four refusals of ADR 0008 §3, in the order a reader would ask them.

    Every message names the remedy. A refusal whose message does not is a
    refusal that gets worked around.
    """
    if left.tenant != right.tenant:
        # Fixed decision 8, and it does not become negotiable because the output
        # is a report rather than a verdict: one end customer's numbers read as
        # another's is arithmetically valid and factually nonsense in any
        # document.
        raise ValueError(
            f"cannot diff across tenants: one run is {left.tenant!r}, the other "
            f"is {right.tenant!r}"
        )
    if left.suite != right.suite:
        # Two suites can legitimately share a fingerprint — the same checks at
        # the same bars over different cases — so this is checked on the name
        # and not left to the hash below.
        raise ValueError(
            f"cannot diff across suites: one run is {left.suite!r}, the other "
            f"is {right.suite!r}"
        )
    if left.config_hash != right.config_hash:
        raise DifferentSuitesError(
            f"the two runs were produced under different suites (config_hash "
            f"{left.config_hash} against {right.config_hash}): a diff between "
            "them would compare the rulers, not the systems — re-run one side "
            "under the other's suite"
        )
    _refuse_judges(left, right)


def _refuse_judges(left: Run, right: Run) -> None:
    """The identity set has four states and only two of them pass.

    Both empty is allowed and has to be: a suite of `Contains`, `Regex` and
    `JsonSchema` declares no instrument, and so does a plain-function judge.
    Refusing there would exclude most suites from the feature.

    One empty and one not is ADR 0005's `unknown`, and it is refused — see
    `DifferentJudgesError` for why declining to report is not reporting.
    """
    here, there = left.judge_config.identities, right.judge_config.identities
    if here == there:
        return
    if not here or not there:
        recorded, blank = ("second", "first") if here == () else ("first", "second")
        raise DifferentJudgesError(
            f"the {recorded} run records the judge "
            f"{', '.join(here or there)} and the {blank} records none: it "
            "cannot be established that the two were graded by the same "
            "instrument, and a difference measured on two scales is not a "
            "difference — re-run one side under the other's judge"
        )
    raise DifferentJudgesError(
        f"the two runs were graded by different judges ({', '.join(here)} "
        f"against {', '.join(there)}): the instruments differ, so a difference "
        "between these scores is not a difference in the systems — re-run one "
        "side under the other's judge"
    )


def diff(left: Run, right: Run) -> Difference:
    """What differs between `left` and `right`. Neither is a reference.

    **Symmetric**: `diff(a, b)` and `diff(b, a)` are the same report with the
    two columns exchanged — the same set of differing checks, the same counts
    with the two "favours" figures exchanged, the same intervals, the same
    refusal or lack of one. Nothing here reads one side preferentially.

    **Refuses** where the two runs were not measured the same way: a crossed
    tenant, a different suite name, a different `config_hash`, or a judge
    identity set that does not match (ADR 0008 §3). The target is free, and that
    freedom is the feature — two models, two temperatures, two prompts is the
    question this function exists to answer.

    **Never produces a verdict.** There is no `worse`, no `regressed`, no exit
    code to derive. A check differs or it does not, and where it does the report
    says which run the number favours, which is a statement about two numbers
    rather than about a direction of travel.

    The rule order mirrors `compare()`'s deliberately, because the questions
    "are these the same check" and "did this check answer differently" have the
    same shape whether or not one side was approved:

    1. present on one side only -> `only_left` / `only_right`
    2. either side in error -> `errored`
    3. the outcomes flip (pass on one side, fail on the other) -> `differs`,
       **regardless of tolerance**
    4. otherwise numeric, against `max` of the two declared tolerances

    The one place it parts company is what happens *after* rule 4 finds a
    difference. `compare()` consults the baseline's interval and may call the
    movement `unchanged`; here the difference stands, and the two intervals ride
    beside it as evidence. A diff has no baseline, so no interval has the
    standing to command. (ADR 0008 §4)
    """
    _refuse(left, right)
    here, there = index_verdicts(left), index_verdicts(right)
    checks: list[CheckDifference] = []

    for key in sorted(here.keys() | there.keys()):
        scope, case_id, _identity, _ = key
        one, other = here.get(key), there.get(key)
        # The key carries identity; the row carries the readable name.
        named = one if one is not None else other
        assert named is not None
        checks.append(_check(case_id, named.score.name, scope, one, other))

    return Difference(
        tenant=left.tenant,
        suite=left.suite,
        left_environment=left.environment,
        right_environment=right.environment,
        checks=tuple(checks),
        # `left` is `before` and `right` is `after`, so the ADR 0005 machinery
        # renders into two columns in argument order and a swap exchanges them.
        target_config_deltas=config_deltas(right.target_config, left.target_config),
        artifact_deltas=artifact_deltas(right, left),
        # Identical on both sides by §3, so either one is the answer.
        judges=left.judge_config.identities,
    )


def _check(
    case_id: str,
    assertion: str,
    scope: Scope,
    left: Verdict | None,
    right: Verdict | None,
) -> CheckDifference:
    """One row, by the four rules of `diff()`."""
    if right is None:
        assert left is not None
        return CheckDifference(
            case_id, assertion, scope, "only_left", left, None, "neither"
        )
    if left is None:
        return CheckDifference(
            case_id, assertion, scope, "only_right", None, right, "neither"
        )

    if left.status == "error" or right.status == "error":
        # Neither green nor a difference in the systems (ADR 0001 §1): a check
        # that could not run says nothing about which run to pick, so it favours
        # nobody and is counted apart from both.
        return CheckDifference(
            case_id, assertion, scope, "errored", left, right, "neither"
        )

    # Past this point both statuses are pass or fail, so both scores are
    # numeric: Verdict.__post_init__ guarantees it.
    assert left.score.score is not None and right.score.score is not None
    delta = right.score.score - left.score.score
    tolerance = _tolerance(left, right)
    low, high = _noise(left), _noise(right)
    overlap, disjoint = _overlap(low, high)

    flipped = left.status != right.status
    if flipped:
        # A flip carries no interval, for ADR 0006 §6's reason unchanged: the
        # intervals did not decide it, and printing them beside it would invite
        # a reader to check the scores against them and find, quite often, that
        # both are inside.
        return CheckDifference(
            case_id,
            assertion,
            scope,
            "differs",
            left,
            right,
            "right" if right.status == "pass" else "left",
            delta=delta,
            tolerance=tolerance,
            flipped=True,
        )

    if abs(delta) <= tolerance:
        outcome: DiffOutcome = "same"
        favours: Favours = "neither"
    else:
        outcome = "differs"
        favours = "right" if delta > 0 else "left"

    return CheckDifference(
        case_id,
        assertion,
        scope,
        outcome,
        left,
        right,
        favours,
        delta=delta,
        tolerance=tolerance,
        left_interval=low,
        right_interval=high,
        # Carried on a `same` row too. Two runs that agree within tolerance and
        # whose intervals overlap agree twice over, and a reader comparing rows
        # should not have to work out that the absence of a note on one row
        # means something different from its absence on another.
        intervals_overlap=overlap,
        intervals_disjoint=disjoint,
    )
