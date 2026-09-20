"""Comparison between a run and the recorded baseline.

A pure function, no I/O, callable without a driver. A threshold check only
catches "below 0.7"; this catches "was 0.91, now 0.78, still above the
threshold". See `docs/adr/0001-verdict-not-score.md`.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Literal

from digline.core.run import Run, SystemConfig
from digline.core.types import ConfigValue, Verdict, at_precision, meets, within

__all__ = [
    "IDENTITY_FIELD",
    "ArtifactDelta",
    "ArtifactOutcome",
    "AssertionDelta",
    "Comparison",
    "ConfigDelta",
    "Denominator",
    "ConfigOutcome",
    "Noise",
    "Outcome",
    "Scope",
    "artifact_deltas",
    "compare",
    "considered_cases",
    "config_deltas",
    "denominator",
    "index_verdicts",
    "withhold_artifacts",
]

type Outcome = Literal[
    "regressed", "improved", "unchanged", "new", "missing", "errored"
]

type Scope = Literal["case", "run"]

type ArtifactOutcome = Literal["same", "changed", "new", "missing", "unknown"]

#: The `field` an identity row carries, in place of a parameter name. One row
#: per instrument rather than one row per parameter, because "which graded this"
#: is not a setting of anything — it is the thing the settings belong to.
IDENTITY_FIELD = "judge"

#: Deliberately the same five words as an artifact's. A parameter and a file are
#: two things under test, and a reader who has learnt what `unknown` means in
#: one place has learnt it in both.
type ConfigOutcome = ArtifactOutcome

type _Key = tuple[Scope, str, str, int]


@dataclass(frozen=True, slots=True)
class ArtifactDelta:
    """What happened to one file under examination between two runs.

    `before` and `after` are the texts, and either may be `None` — because the
    file was not there, or because redaction withheld it. `withheld` says which,
    so a reader is never left to guess whether a prompt was absent or kept back.

    A withheld artifact carries no digest either, so the outcome is `unknown`:
    the comparison cannot say whether it moved, and saying `same` would be a
    guess dressed as a finding. That is the price of ADR 0003 §4 and it is
    stated rather than hidden.
    """

    path: str
    outcome: ArtifactOutcome
    before: str | None = None
    after: str | None = None
    before_sha: str = ""
    after_sha: str = ""
    withheld: bool = False


@dataclass(frozen=True, slots=True)
class ConfigDelta:
    """What happened to one configuration parameter between two runs.

    Named, by value, and that is the whole point of ADR 0005: "the configuration
    differs" sends a reader off to reconstruct what differed, while
    `temperature 0.3 -> 0.7` is a sentence they can act on.

    `unknown` covers the two absences that are not changes — the value was
    withheld at a boundary, or the other side recorded no configuration at all
    because it predates ADR 0005. Neither may be reported as a change: a
    baseline promoted last month must not need re-promoting.

    A row whose `field` is `IDENTITY_FIELD` names an **instrument** rather than
    a parameter: `before` and `after` hold the `provider/model` label, and the
    outcome is `new` for one that started judging and `missing` for one that
    stopped. A judge cannot be `changed` — a different model is a different
    instrument, added and removed, not a value that moved.
    """

    field: str
    outcome: ConfigOutcome
    before: ConfigValue = None
    after: ConfigValue = None
    withheld: bool = False


@dataclass(frozen=True, slots=True)
class AssertionDelta:
    """The comparison outcome for one assertion on one case.

    `within_noise` is a fact beside the verdict, not a sixth `Outcome`. A
    movement within noise **is** `unchanged`, which is what it is; the fact
    rides alongside so a reader who has learnt the vocabulary does not have to
    learn it again. `noise_min` and `noise_max` are the interval it was judged
    against — the baseline's, always, so a noisy new run cannot widen its own
    excuse. (ADR 0006 §5, §9)
    """

    case_id: str
    assertion: str
    outcome: Outcome
    #: `"run"` for a verdict about the whole run — precision, recall — which
    #: belongs to no case and carries an empty `case_id`.
    scope: Scope
    current: Verdict | None
    baseline: Verdict | None
    delta: float | None
    reason: str
    within_noise: bool = False
    noise_min: float | None = None
    noise_max: float | None = None
    #: How many samples the interval was measured over, for the sentence the
    #: report prints: "0.85–0.95 across 5 samples".
    noise_samples: int = 0
    #: This delta belongs to a case that watches the model rather than measuring
    #: it. A fact beside the outcome, like `within_noise` and for the same
    #: reason: `Outcome` gains no sixth member, and a reader who has learnt the
    #: five does not have to learn a sixth. What it changes is what the movement
    #: *means* — see `Comparison.canary_moved`. (ADR 0016 §5)
    canary: bool = False
    #: This delta belongs to a case that measures the **instrument**: the target
    #: was never asked, and the only gate on the case is its declared band. So
    #: the delta is computed and kept in `deltas`, where movement inside the
    #: band stays readable, and it is left out of `counts` and of every outcome
    #: selection — a calibration case that moved is not a check of the system
    #: that got better or worse. (ADR 0024 §4.4, amended 2026-09-17)
    calibration: bool = False
    #: This delta sets two run-level aggregates side by side that were computed
    #: over **different numbers of cases**, so there is no movement to measure:
    #: the thing measured is not the same thing. A fact beside the outcome for
    #: the third time, and for the reason the first two give — but where
    #: `within_noise` says a movement *is* `unchanged`, this one says
    #: `unchanged` was never available.
    #:
    #: The predicate is `Matrix.considered`, never "a case errored": a case
    #: leaves the denominator for five reasons — errored, suspended, unlabelled,
    #: canary, calibration — and a rule keyed on the error would leave four doors
    #: open and need rewriting the first time somebody suspended a case.
    #:
    #: It is an **incomparability, not a regression**: it never makes `worse`
    #: true, never reclassifies a check, and moves no exit code. What it does is
    #: stop a comparison that was never valid from being reported as `unchanged`.
    #: `config_changed` is the precedent — the same shape, and the same answer:
    #: state the condition, convert nothing, and leave the reader to judge what
    #: the comparison is worth. (ADR 0012 §3, amended 2026-09-18)
    #:
    #: **That paragraph was a promise the code kept only half of**, and the half
    #: it kept was the half nobody could see. `outcome` still points wherever the
    #: arithmetic points, so a moved denominator whose score happened to *drop*
    #: was counted as `regressed`, which made `worse` true and exited 1 — the
    #: very conversion this says never happens. It is enforced now rather than
    #: described: `of` and `counts` leave these deltas out, exactly as they leave
    #: out a calibration delta, so `worse` cannot read one in either direction.
    #: The outcome is kept on the row because a reader who wants to know which
    #: way the arithmetic pointed is owed it; what it may no longer do is count.
    #: (the delta-pass over 0.15.1)
    #:
    #: It rides on a **flip from `fail` to `pass`** as well, which the release
    #: after that one had to add: `improved` is a claim about the pair, and a
    #: pair that counted different numbers of cases is not one. A flip the other
    #: way never carries it, and that is an asymmetry rather than a proof: a
    #: gate that fails over the cases it counted stays red because withdrawing
    #: it would make a run *greener*. Below a threshold of 1.0 it can be a false
    #: alarm — a case that passed leaves the count and takes the gate under its
    #: bar — and that is accepted. (the delta-pass over 0.15.2; ADR 0012 §3)
    denominator_moved: bool = False


@dataclass(frozen=True, slots=True)
class Comparison:
    """The full comparison. `deltas` is ordered by (case, assertion) so two
    equivalent comparisons read identically."""

    tenant: str
    suite: str
    config_changed: bool
    #: Where each side ran. Reported, never constrained: comparing staging
    #: against a production baseline is the pre-release check, not a mistake.
    #: A reader who needs to know they are looking across environments can; a
    #: caller who does not care is not stopped.
    environment: str = ""
    baseline_environment: str = ""
    deltas: Sequence[AssertionDelta] = ()
    #: What changed in the files that *are* the thing under test, before what it
    #: did to the scores. Rendered above the deltas for that reason. (ADR 0003)
    artifact_deltas: Sequence[ArtifactDelta] = ()
    #: What changed in the system that answered — model, temperature, token cap,
    #: region, endpoint host. Reported, never a refusal: two temperatures must
    #: stay comparable, which is the experiment. (ADR 0005 §5)
    target_config_deltas: Sequence[ConfigDelta] = ()
    #: What changed in the instrument that graded. Reported more strongly: a
    #: judge that moved makes the scores less comparable with the baseline
    #: whatever the target did. (ADR 0005 §4)
    judge_config_deltas: Sequence[ConfigDelta] = ()

    @property
    def artifacts_changed(self) -> bool:
        """Whether a file under test is known to have moved.

        `unknown` is not a change: a redacted comparison has no digest to
        compare, and answering "changed" would report a fact nobody has.
        """
        return any(d.outcome not in ("same", "unknown") for d in self.artifact_deltas)

    @property
    def target_config_changed(self) -> bool:
        """Whether the system under test is known to have been configured
        differently. `unknown` is not a change, for the same reason as above."""
        return _changed(self.target_config_deltas)

    @property
    def judge_config_changed(self) -> bool:
        return _changed(self.judge_config_deltas)

    @property
    def canary_moved(self) -> bool:
        """Whether a case that watches the model moved at all.

        **Movement, not direction.** A canary that improved is a changed model
        just as loudly as one that got worse: its score is a fingerprint, not a
        quality. `errored` is not movement — that is a broken instrument, and it
        is already `unjudged`; `new` and `missing` are not movement either — a
        case was added or removed, which is an edit to the suite.

        It is deliberately **not** folded into `worse`. Folding it would make the
        headline say *one check got worse* about a check that got better, which
        is the report telling a reader something untrue in order to produce the
        right exit code. Two facts, one number: `exit_code()` returns 1 for
        either. (ADR 0016 §5)
        """
        return any(
            delta.canary and delta.outcome in ("regressed", "improved")
            for delta in self.deltas
        )

    @property
    def moved_canaries(self) -> Sequence[AssertionDelta]:
        """The canary deltas that moved, for the sentence that names one."""
        return tuple(
            d
            for d in self.deltas
            if d.canary and d.outcome in ("regressed", "improved")
        )

    @property
    def comparability_reduced(self) -> bool:
        """Whether the scores are less comparable than the numbers suggest.

        A judge change and nothing else. When the *target* moves, the thing
        being measured moved and the deltas are the finding; when the *judge*
        moves, the scale moved, and a delta measured on two scales is not a
        delta. The report says so instead of leaving a reader to notice.
        """
        return self.judge_config_changed

    @property
    def config_changes(self) -> Sequence[ConfigDelta]:
        """The target parameters that are known to have moved, by name.

        What the "this drop coincides with …" sentence is built from — only
        `changed`, never `new` or `unknown`: a parameter that appeared, or one
        nobody recorded, has no before-and-after to coincide with.
        """
        return tuple(d for d in self.target_config_deltas if d.outcome == "changed")

    def of(self, *outcomes: Outcome) -> Sequence[AssertionDelta]:
        """The deltas about the system with these outcomes.

        A calibration delta is never among them: its outcome is a relation
        between two gradings of an answer nobody generated, and selecting it as
        `regressed` is how "1 check got worse" would come to be said about a
        case the target was never asked. (ADR 0024 §4.4)

        Neither is an incomparable one, and for a reason one step stronger: a
        calibration delta measures something real that is not the system, while
        this measures nothing at all — two scores over different case sets are
        not a movement, so there is no direction to select on. Selecting it as
        `improved` is how "recall got better, 1.000000 to 1.000000" came to be
        printed under a line saying the two were not comparable.
        (ADR 0012 §3, amended by the delta-pass over 0.15.1)
        """
        wanted = frozenset(outcomes)
        return tuple(
            d
            for d in self.deltas
            if d.outcome in wanted and not d.calibration and not d.denominator_moved
        )

    @property
    def regressed(self) -> Sequence[AssertionDelta]:
        return self.of("regressed")

    @property
    def errored(self) -> Sequence[AssertionDelta]:
        return self.of("errored")

    @property
    def has_regressions(self) -> bool:
        return bool(self.regressed)

    @property
    def counts(self) -> dict[Outcome, int]:
        """How many deltas about the system landed in each outcome.

        Without the calibration deltas, for `of`'s reason — and the headline's
        counts, the `worse` flag and the wire's `counts` are all read from here,
        so a machine consumer reading the number and a person reading the
        sentence cannot be told two different things. (ADR 0024 §4.4)

        Without the incomparable ones either, which is the single edit that
        makes the paragraph on `AssertionDelta.denominator_moved` true: this is
        the one place `worse` is computed from, so removing them here is what
        stops a moved denominator from exiting 1 when its arithmetic points down
        — and, at the same tally, what stops the document from counting one
        under `improved` when it points up. The count of what was withheld is
        `incomparable`, beside the six and never inside them.
        """
        tally: Counter[Outcome] = Counter(
            d.outcome
            for d in self.deltas
            if not d.calibration and not d.denominator_moved
        )
        return dict(tally)

    @property
    def incomparable(self) -> Sequence[AssertionDelta]:
        """The deltas whose two sides were measured over different numbers of
        cases, which `counts` and `of` leave out.

        Beside `calibration_deltas` and read the same way: a reader or a
        renderer that wants them asks for them, and nothing has to know the
        predicate to find them.
        """
        return tuple(d for d in self.deltas if d.denominator_moved)

    @property
    def calibration_deltas(self) -> Sequence[AssertionDelta]:
        """The deltas of the calibration cases, which `counts` leaves out."""
        return tuple(d for d in self.deltas if d.calibration)


def _changed(deltas: Sequence[ConfigDelta]) -> bool:
    return any(d.outcome not in ("same", "unknown") for d in deltas)


def index_verdicts(run: Run) -> dict[_Key, Verdict]:
    """Index by (case, assertion identity, occurrence).

    Public, and it now serves two consumers: `compare()`, which pairs a run
    against an approved baseline, and `diff()`, which pairs two runs neither of
    which was approved by anybody (ADR 0008 §5). The pairing rule is the same
    for both and has to be, because **identity is identity whether or not one
    side was approved**: what makes two verdicts the same check is the
    assertion's fingerprint, and approval is a fact about a file rather than
    about a check. A second, subtly different pairing would mean two answers to
    "is this the same check", which is how a diff and a comparison of one pair
    of runs come to disagree about how many checks there are.

    Keying on `Verdict.assertion_id` rather than on the name is what keeps the
    pairing honest. Position is not identity: with two `contains` on one case,
    pairing by order would turn a reordering of the suite into a fabricated
    `regressed` plus a fabricated `improved`, and deleting the first of three
    would report the third as `missing` while silently comparing the second
    against the first's baseline.

    The occurrence counter survives, but only as a tiebreaker between verdicts
    that share an identity — the same assertion, identically configured, applied
    twice to the same case. There, order is the only thing left to pair on, and
    pairing by order is correct because the two are interchangeable.
    """
    out: dict[_Key, Verdict] = {}
    for case in run.results:
        seen: Counter[str] = Counter()
        for verdict in case.verdicts:
            key = verdict.assertion_id
            out[("case", case.case_id, key, seen[key])] = verdict
            seen[key] += 1

    # Aggregates belong to no case, so they carry an empty `case_id` and are
    # kept in a scope of their own rather than filed under a sentinel name that
    # would one day collide with a real one.
    seen_run: Counter[str] = Counter()
    for verdict in run.aggregate:
        key = verdict.assertion_id
        out[("run", "", key, seen_run[key])] = verdict
        seen_run[key] += 1
    return out


@dataclass(frozen=True, slots=True)
class Noise:
    """The interval a movement is judged against, or the absence of one.

    A value rather than three loose variables because the absence is a case in
    its own right and has to be handled everywhere the presence is: a baseline
    that predates ADR 0006, or a suite running at `samples=1`, has no interval,
    and there today's absolute rule holds unchanged. The report then says the
    noise of this check is not known, rather than implying there is none.
    """

    low: float | None = None
    high: float | None = None
    count: int = 0

    @property
    def known(self) -> bool:
        return self.low is not None and self.high is not None

    def covers(self, score: float) -> bool:
        """Whether `score` is inside the interval the baseline observed.

        One test for both directions, and that is the asymmetry of §5 rather
        than an omission of it: noise is not mirrored onto the side that did not
        show any. A check whose baseline only ever dropped has `high` equal to
        its own score, so a rise is outside the interval and reported. And an
        interval of zero width — five samples out of five agreeing, the ordinary
        case away from the boundary — covers nothing but the score itself, so
        every later change of mind is still a finding. (ADR 0006 §6)
        """
        if self.low is None or self.high is None:
            return False
        return meets(score, self.low) and within(score, self.high)

    def rendered(self) -> str:
        assert self.low is not None and self.high is not None
        return f"{self.low:.6f}-{self.high:.6f} across {self.count} samples"

    def beyond(self) -> str:
        """The clause added to a movement that left the interval. Nothing at all
        where there is no interval: silence is what "not known" sounds like, and
        a sentence about an absent measurement would read as a measurement."""
        return (
            f", beyond the noise of this check ({self.rendered()})"
            if self.known
            else ""
        )


def considered_cases(verdict: Verdict) -> int | None:
    """How many cases the aggregate behind `verdict` was computed over, or `None`
    where the verdict is not an aggregate.

    Public since the delta-pass over 0.15.1, because two renderers now print the
    pair of numbers and the guard below is the part that is easy to get wrong:
    `True` is an `int` in Python, so a metadata key holding a boolean would read
    as an aggregate computed over one case. One definition, rather than that
    subtlety copied into `report/`.

    `Matrix.as_metadata()` writes `considered` on every run-level aggregate and
    nothing else writes it, so its presence is also what identifies one. Read
    rather than trusted: a run document is written by whoever holds it, and a
    `considered` that is not a whole number tells us nothing, so it is treated
    as *not an aggregate* rather than as a reason to raise — this is a reading,
    and a reading that refuses a document cannot report on it.
    """
    value = verdict.score.metadata.get("considered")
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


#: Every count `Matrix.as_metadata()` writes for a case it left out. Named in
#: full rather than derived, because the set is the rule: a case leaves the
#: denominator for exactly these reasons and each one moves the score.
#:
#: In the order a sentence names them, which is not the order the matrix writes
#: them: a case that could not be judged is the exclusion the denominator trap
#: is made of, so it is read first, and the two exclusions a suite declares on
#: purpose come last.
_EXCLUSIONS = (
    "errored_excluded",
    "suspended_excluded",
    "unlabelled_excluded",
    "canary_excluded",
    "calibration_excluded",
)


@dataclass(frozen=True, slots=True)
class Denominator:
    """The cases an aggregate counted, out of the cases it saw, and why the rest
    were left out.

    `excluded` holds only the non-zero counts, keyed by the metadata name, in
    `_EXCLUSIONS` order: a renderer that walks it names every exclusion there
    was and nothing that did not happen, which is what lets a run with none say
    nothing at all.
    """

    considered: int
    excluded: tuple[tuple[str, int], ...] = ()

    @property
    def seen(self) -> int:
        return self.considered + sum(count for _, count in self.excluded)


def denominator(verdict: Verdict) -> Denominator | None:
    """What the aggregate behind `verdict` was computed over, or `None` where
    the verdict is not an aggregate.

    One reading of the numbers `Matrix.as_metadata()` writes, for the renderers
    that state them in a sentence and for `_seen` below, so that "43 of 50" in
    a report and "the same cases seen" in `compare()` are one sum. A count that
    is not a whole number is skipped rather than raised on, for the reason
    `considered_cases` gives.
    """
    considered = considered_cases(verdict)
    if considered is None:
        return None
    excluded: list[tuple[str, int]] = []
    for key in _EXCLUSIONS:
        value = verdict.score.metadata.get(key)
        if not isinstance(value, bool) and isinstance(value, int) and value:
            excluded.append((key, value))
    return Denominator(considered, tuple(excluded))


def _seen(verdict: Verdict) -> int | None:
    """How many cases the aggregate behind `verdict` looked at — those it counted
    plus those it left out."""
    counted = denominator(verdict)
    return None if counted is None else counted.seen


def _denominator_moved(now: Verdict, before: Verdict) -> bool:
    """True where two aggregates looked at the same cases and **counted**
    different numbers of them.

    The second half is what keeps this from crying wolf, and it was not obvious:
    a suite that gains a case grows every aggregate's denominator too, and that
    is not an incomparability — it is a suite that grew, which `compare` already
    reports as a new case and a reader already understands. Flagging it would
    fire on the most ordinary edit anybody makes, and a fact that fires on
    everything says nothing. Found by `tests/test_groups.py`, which had this
    exact shape already written down.

    So the predicate is: the same number of cases *seen*, a different number
    *counted* — cases that dropped out of being judged, which is the movement
    nobody declared. Both sides must be aggregates and both numbers known: a
    reference written before aggregates recorded their matrix has no
    `considered`, and an absence is not a difference.
    """
    here, there = considered_cases(now), considered_cases(before)
    if here is None or there is None or here == there:
        return False
    return _seen(now) == _seen(before)


def _incomparable_clause(now: Verdict, before: Verdict) -> str:
    """The clause a reason earns once `_denominator_moved` is true, appended to
    whatever said what the two scores did.

    A function because two branches say it — a score that moved, and a gate that
    flipped from `fail` to `pass` — and one fact said in two wordings is a fact
    the reader has to reconcile before believing either. `Noise.beyond` is the
    same shape for the same reason. (the delta-pass over 0.15.2)
    """
    return (
        f", but it was measured over {considered_cases(now)} cases against "
        f"{considered_cases(before)} in the reference: the two are not the same "
        "measurement"
    )


def _noise(verdict: Verdict) -> Noise:
    score = verdict.score
    if not score.sampled:
        return Noise()
    return Noise(score.sample_min, score.sample_max, len(score.samples))


def compare(run: Run, baseline: Run) -> Comparison:
    """Compare `run` against `baseline`.

    Rule order is deliberately non-commutative:

    1. present on one side only -> `new` / `missing`
    2. either side in error -> `errored`
    3. the outcome flipped (pass <-> fail) -> `regressed` / `improved`,
       **regardless of tolerance**: a flipped outcome is never noise
    4. otherwise a numeric comparison against the tolerance

    Rule 2 upholds the constraint that `error` is neither green nor a
    regression: an error reported as a regression would fail a PR for the wrong
    reason, and one reported as `unchanged` would hide a suite that stopped
    working.

    The tolerance used is the current run's. Comparing two runs with different
    tolerances is legitimate and is in fact the interesting case — seeing the
    effect of a configuration change — but `promote_baseline` will refuse to
    promote the result until the configuration matches again.

    Comparing across tenants raises. Two perimeters produce numbers on the same
    scale, so the mistake is arithmetically valid and factually nonsense — one
    end customer's results read as another's history.

    Comparing across *environments* does not raise, and must not: running the
    staging suite against the production baseline is the pre-release check the
    whole product exists for. Both environments are reported on the
    `Comparison` so a reader can see what was held against what.

    A redacted run compares against a complete baseline: everything read here —
    score, status, threshold, tolerance, identity — survives redaction. The
    `Comparison` returned, however, holds the verdicts it was given, so it
    inherits the payload of its inputs.
    """
    if run.tenant != baseline.tenant:
        raise ValueError(
            f"cannot compare across tenants: run is {run.tenant!r}, "
            f"baseline is {baseline.tenant!r}"
        )
    current, previous = index_verdicts(run), index_verdicts(baseline)
    # Which cases watch the model, as **this run** declares it. The baseline is
    # read only for a case that is no longer in the run at all, so that a flag
    # flipped between the two is read from the side being judged. (ADR 0016 §1)
    canaries = {case.case_id for case in run.results if case.canary}
    canaries |= {
        case.case_id
        for case in baseline.results
        if case.canary and case.case_id not in {c.case_id for c in run.results}
    }
    # The same reading for the calibration case, and for the same reason.
    calibrated = {case.case_id for case in run.results if case.calibration is not None}
    calibrated |= {
        case.case_id
        for case in baseline.results
        if case.calibration is not None
        and case.case_id not in {c.case_id for c in run.results}
    }
    deltas: list[AssertionDelta] = []

    for key in sorted(current.keys() | previous.keys()):
        scope, case_id, _identity, _ = key
        now, before = current.get(key), previous.get(key)
        # The key carries identity; the delta carries the readable name.
        named = now if now is not None else before
        assert named is not None
        assertion = named.score.name

        if before is None:
            assert now is not None
            deltas.append(
                AssertionDelta(
                    case_id,
                    assertion,
                    "new",
                    scope,
                    now,
                    None,
                    None,
                    "absent from the baseline",
                    canary=case_id in canaries,
                    calibration=case_id in calibrated,
                )
            )
            continue
        if now is None:
            deltas.append(
                AssertionDelta(
                    case_id,
                    assertion,
                    "missing",
                    scope,
                    None,
                    before,
                    None,
                    "present in the baseline but not in this run",
                    canary=case_id in canaries,
                    calibration=case_id in calibrated,
                )
            )
            continue

        if now.status == "error" or before.status == "error":
            side = "in this run" if now.status == "error" else "in the baseline"
            culprit = now if now.status == "error" else before
            deltas.append(
                AssertionDelta(
                    case_id,
                    assertion,
                    "errored",
                    scope,
                    now,
                    before,
                    None,
                    f"assertion errored {side}: {culprit.reason}",
                    canary=case_id in canaries,
                    calibration=case_id in calibrated,
                )
            )
            continue

        # Past this point both statuses are pass or fail, so both scores are
        # numeric: Verdict.__post_init__ guarantees it.
        assert now.score.score is not None and before.score.score is not None
        # Rounded where it is computed, not where it is tested (ADR 0009 §4).
        # `AssertionDelta.delta` is a public field: a delta that compared as
        # 0.047619 and serialized as 0.04761900000000008 would have moved the
        # inconsistency out of the verdict and into the JSON.
        delta = at_precision(now.score.score - before.score.score)
        was, is_now = f"{before.score.score:.6f}", f"{now.score.score:.6f}"

        if now.status != before.status:
            # **A flip is not a distance**, which is ADR 0006 §6's argument one
            # register over: a flip is each side measured against *its own
            # threshold*. That decides the two directions differently, and
            # 0.15.2 wrote it here as though it decided both the same way.
            #
            # *Downward* the run is red, exits 1, and says so with the
            # denominator unmentioned — by an asymmetry, not a proof. A gate
            # reading `fail 0.666667` over three cases is not failing whatever
            # the reference counted: below a threshold of 1.0 the case that left
            # the count may have been a pass, and with it counted the gate would
            # hold. The reading stays because withdrawing it would make a run
            # *greener*, and red is the side this product chooses to be wrong
            # on. The false alarm is the price, paid knowingly, and
            # `tests/test_denominator.py` pins it.
            #
            # *Upward* it settles nothing, and this is the sentence the advisory
            # is about. `fail` over four cases to `pass` over three is the shape
            # an endpoint can produce by erroring the case it was failing: the
            # flip is true of this run — `now.status` is `pass`, and nothing
            # here touches it — while `improved` is a claim about the pair, and
            # the pair was never a comparison. So the flag is computed on the
            # way up, the row stops counting, and `compare` says which two
            # numbers of cases it is holding side by side.
            # (ADR 0012 §3, amended by the delta-pass over 0.15.2)
            #
            # No interval rides along here, and its absence is the point. A
            # flipped outcome is never within noise (ADR 0006 §6), so it was
            # not judged against an interval — and attaching one would invite
            # a reader to check the score against it and find, quite often,
            # that the score is *inside* it. `0.8 -> 0.4` across a threshold of
            # 0.5, on a check whose baseline votes ran 0.0 to 1.0, is exactly
            # that shape: reported, and inside. The delta carries what decided
            # it, and nothing that did not.
            outcome: Outcome = "regressed" if before.status == "pass" else "improved"
            # Read in whichever direction the denominator moved: a reference
            # that counted *fewer* cases is the same incomparability as one that
            # counted more, because what is unequal is what the two sides
            # measured and inequality has no direction. Only the flip's own
            # direction is asked about, on the line above.
            flipped_incomparably = before.status == "fail" and _denominator_moved(
                now, before
            )
            # A flip caused by a moved threshold reads exactly like a flip
            # caused by a worse model. Saying so is the difference between a
            # reviewer blaming the prompt and a reviewer checking the config.
            if now.threshold != before.threshold:
                why = (
                    f"outcome flipped from '{before.status}' to '{now.status}', "
                    f"but the threshold moved from {before.threshold:.6f} to "
                    f"{now.threshold:.6f} — the score went from {was} to {is_now}"
                )
            else:
                why = f"outcome flipped from '{before.status}' to '{now.status}'"
            if flipped_incomparably:
                why += _incomparable_clause(now, before)
            deltas.append(
                AssertionDelta(
                    case_id,
                    assertion,
                    outcome,
                    scope,
                    now,
                    before,
                    delta,
                    why,
                    canary=case_id in canaries,
                    calibration=case_id in calibrated,
                    denominator_moved=flipped_incomparably,
                )
            )
            continue

        # The interval is the **baseline's**, never this run's. The baseline is
        # the promoted, reviewed measurement; letting a noisy new run widen its
        # own excuse is how a regression hides inside a model that got less
        # stable. (ADR 0006 §5)
        floor = _noise(before)
        within_noise = False

        # Before every branch below, because it decides whether `unchanged` is
        # an answer this comparison is allowed to give at all. Two aggregates
        # computed over different numbers of cases are not the same measurement,
        # so there is no movement for a tolerance or an interval to excuse.
        # (ADR 0012 §3, amended 2026-09-18)
        denominator_moved = _denominator_moved(now, before)

        if denominator_moved:
            # Not a regression and not an improvement: the delta between two
            # different measurements is not a number about the system. The
            # outcome stays whichever direction the arithmetic points so that a
            # reader who wants it still has it, except that `unchanged` — the
            # one answer that would be an affirmative false claim — is off the
            # table, and the reason says why rather than quoting a tolerance
            # that never applied.
            moved_to: Outcome = "regressed" if delta < 0 else "improved"
            why = f"score moved from {was} to {is_now}" + _incomparable_clause(
                now, before
            )
        elif within(abs(delta), now.tolerance):
            # Declared before measured, and the reason says which one spoke. A
            # tolerance is what a reviewer decided is acceptable; the interval
            # is what the system does. A reader is never left to guess which of
            # the two called this unchanged.
            moved_to = "unchanged"
            why = f"delta {delta:+.6f} within tolerance {now.tolerance:.6f}"
        elif floor.covers(now.score.score):
            moved_to = "unchanged"
            within_noise = True
            why = (
                f"score moved from {was} to {is_now}, within the noise of this "
                f"check ({floor.rendered()})"
            )
        elif delta < 0:
            moved_to = "regressed"
            why = f"score dropped from {was} to {is_now}{floor.beyond()}"
        else:
            moved_to = "improved"
            why = f"score rose from {was} to {is_now}{floor.beyond()}"

        # The interval rides along whichever outcome won — a regression
        # included, because "beyond the noise of this case (0.85-0.95 across 5
        # samples)" is the sentence ADR 0006 §10 asks the report to print, and
        # it needs the interval the movement left.
        deltas.append(
            AssertionDelta(
                case_id,
                assertion,
                moved_to,
                scope,
                now,
                before,
                delta,
                why,
                denominator_moved=denominator_moved,
                within_noise=within_noise,
                noise_min=floor.low,
                noise_max=floor.high,
                noise_samples=floor.count,
                canary=case_id in canaries,
                calibration=case_id in calibrated,
            )
        )

    return Comparison(
        tenant=run.tenant,
        environment=run.environment,
        baseline_environment=baseline.environment,
        suite=run.suite,
        config_changed=run.config_hash != baseline.config_hash,
        deltas=tuple(deltas),
        artifact_deltas=artifact_deltas(run, baseline),
        target_config_deltas=config_deltas(run.target_config, baseline.target_config),
        judge_config_deltas=config_deltas(run.judge_config, baseline.judge_config),
    )


def config_deltas(now: SystemConfig, before: SystemConfig) -> tuple[ConfigDelta, ...]:
    """One delta per declared parameter, on either side, ordered by name.

    Three rules, and each of them exists to avoid reporting a change nobody
    established (ADR 0005 §5, §7):

    1. **Neither side recorded anything** — a plain-function target, or two runs
       that both predate ADR 0005 — and there is nothing to say. Absent stays
       absent, and absent is not a change.
    2. **One side recorded nothing at all**: every field is `unknown`. This is
       the legacy baseline, and it is the case that decides whether a year of
       promoted baselines has to be promoted again. It does not.
    3. **A field withheld on either side** is `unknown` too: redaction took the
       value, so whether it moved is not knowable from here — `same` would be a
       guess wearing the clothes of a finding (ADR 0003 §5).

    **Both sides are reduced through `redacted()` first, and that is a boundary
    rather than a courtesy.** A `Comparison` is not an inside-the-perimeter
    value: `compare_json(full=True)` ships these deltas to a CI job, and the MCP
    server returns the same object to a model. Reading `.values` raw meant the
    perimeter fields — `base_url`, `fingerprint`, and `resolved_model` at a
    named endpoint — travelled in clear through the delta while the very same
    server's `get_run` correctly withheld them, so one field got two answers out
    of one run. `config_json`'s docstring asserted the opposite ("a withheld
    field carries no value to print in the first place"), which was true only
    when both runs had already been redacted.

    Doing it here rather than at the four call sites is what makes it hold:
    `diff()` builds its deltas through this same function, so the door closes
    once. And it needs no new rule — reducing first turns a perimeter field into
    a withheld one, and rule 3 above already answers `unknown` for those.
    (ADR 0005 §2; the 0.12.1 delta-pass)
    """
    now, before = now.redacted(), before.redacted()
    if not now.recorded and not before.recorded:
        return ()

    deltas: list[ConfigDelta] = [
        _identity_delta(label, now, before)
        for label in sorted(set(now.identities) | set(before.identities))
    ]

    # With more than one instrument in play, neither side has a single set-up to
    # compare and the identity rows above are the whole change. Emitting scalar
    # rows here would report a `max_tokens` as `missing` when what happened is
    # that a second judge joined — a fabricated fact about a real event.
    if len(now.identities) > 1 or len(before.identities) > 1:
        return tuple(deltas)

    fields = sorted(
        set(now.values) | set(before.values) | now.withheld | before.withheld
    )
    for name in fields:
        withheld = name in now.withheld or name in before.withheld
        after = now.values.get(name)
        prior = before.values.get(name)
        if withheld:
            outcome: ConfigOutcome = "unknown"
        elif not now.recorded or not before.recorded:
            outcome = "unknown"
        elif name not in before.values:
            outcome = "new"
        elif name not in now.values:
            outcome = "missing"
        else:
            outcome = "same" if after == prior else "changed"
        deltas.append(
            ConfigDelta(
                field=name,
                outcome=outcome,
                before=prior,
                after=after,
                withheld=withheld,
            )
        )
    return tuple(deltas)


def _identity_delta(label: str, now: SystemConfig, before: SystemConfig) -> ConfigDelta:
    """One instrument, and whether it graded both sides.

    `unknown` where the other side recorded nothing at all: a baseline that
    predates ADR 0005 has no instrument list, and reading its absence as "this
    judge was added" would report a change to a suite that never touched its
    judge.
    """
    here, there = label in now.identities, label in before.identities
    if not now.recorded or not before.recorded:
        outcome: ConfigOutcome = "unknown"
    elif here and there:
        outcome = "same"
    elif here:
        outcome = "new"
    else:
        outcome = "missing"
    return ConfigDelta(
        field=IDENTITY_FIELD,
        outcome=outcome,
        before=label if there else None,
        after=label if here else None,
    )


def withhold_artifacts(comparison: Comparison) -> Comparison:
    """Keep *that* each file moved, drop *what* it was.

    For the party that holds both runs and is producing a document for someone
    who will not. `redact()` cannot do this job and must not try: it works on
    one run, and one run has nothing to compare itself with — which is why a
    redacted run file reports `unknown` and stays honest about it (ADR 0003 §5).

    Here both sides are in hand, so the outcome is a fact this caller
    established rather than a guess. The outcome travels and the payload does
    not, which is decision 9 applied to a file instead of to a reason: the same
    shape as the count of suspended cases, or the PII counts that travel while
    the matched text never does.

    Not a serializer option. A document rendered from the result of this
    function cannot print a line it was never given.
    """
    return replace(
        comparison,
        artifact_deltas=tuple(
            ArtifactDelta(
                path=delta.path,
                outcome=delta.outcome,
                before=None,
                after=None,
                before_sha="",
                after_sha="",
                withheld=True,
            )
            for delta in comparison.artifact_deltas
        ),
    )


def artifact_deltas(run: Run, baseline: Run) -> tuple[ArtifactDelta, ...]:
    """One delta per declared file, on either side, ordered by path.

    Compared on the **digest**, never on the text — a file may be large and two
    identical texts are two identical digests.

    Where either side was withheld there is no digest to compare, and the
    outcome is `unknown`. Redaction takes the digest with the text (ADR 0003
    §4), so this is the one question a redacted comparison cannot answer; the
    alternative was a travelling digest, and a digest verifies a guessed prompt
    in milliseconds.
    """
    deltas: list[ArtifactDelta] = []
    for path in sorted(run.artifacts.keys() | baseline.artifacts.keys()):
        now, before = run.artifacts.get(path), baseline.artifacts.get(path)
        withheld = (now is not None and now.withheld) or (
            before is not None and before.withheld
        )
        if withheld:
            outcome: ArtifactOutcome = "unknown"
        elif before is None:
            assert now is not None
            outcome = "new"
        elif now is None:
            outcome = "missing"
        else:
            outcome = "same" if now.sha == before.sha else "changed"
        deltas.append(
            ArtifactDelta(
                path=path,
                outcome=outcome,
                before=None if before is None else before.text,
                after=None if now is None else now.text,
                before_sha="" if before is None else before.sha,
                after_sha="" if now is None else now.sha,
                withheld=withheld,
            )
        )
    return tuple(deltas)
