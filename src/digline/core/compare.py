"""Comparison between a run and the recorded baseline.

A pure function, no I/O, callable without a driver. A threshold check only
catches "below 0.7"; this catches "was 0.91, now 0.78, still above the
threshold". See `docs/adr/0001-verdict-not-score.md`.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace
from typing import Literal

from digline.core.aggregate import split_grouped_name
from digline.core.reconcile import unreconciled
from digline.core.run import Run, SystemConfig
from digline.core.types import ConfigValue, Verdict, at_precision, meets, within

__all__ = [
    "AGREEMENT_FIELD",
    "IDENTITY_FIELD",
    "ArtifactDelta",
    "ArtifactOutcome",
    "AssertionDelta",
    "CaseCount",
    "Comparison",
    "ConfigDelta",
    "Denominator",
    "ConfigOutcome",
    "Direction",
    "Expansion",
    "Noise",
    "Outcome",
    "Scope",
    "SuiteDelta",
    "artifact_deltas",
    "case_count",
    "checked_denominator",
    "compare",
    "considered_cases",
    "config_deltas",
    "denominator",
    "index_verdicts",
    "suite_deltas",
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
#:
#: A **rule** wears them too, from ADR 0028 on. Three things under one
#: vocabulary rather than three vocabularies: the fourth would have been the one
#: that made a reader check which table they were looking at.
type ConfigOutcome = ArtifactOutcome

#: Which way a rule moved, where the movement has a way. A fact **beside** the
#: outcome and never a sixth word inside it — `AssertionDelta.within_noise`'s
#: shape, for `within_noise`'s reason: the five words are shared across
#: configurations, artifacts and rules, and a reader who has learnt them must
#: not have to learn a variant. (ADR 0028 §4)
type Direction = Literal["loosened", "tightened", ""]

#: Why a per-group gate is in the table, when it is new. `""` for every row that
#: is not one. See `_expansion`, and ADR 0028 §6 for why the *case* behind it is
#: not named here or anywhere.
type Expansion = Literal["new_group", "now_grouped", ""]

#: The `field` of the row that says the agreement floor cannot be compared. Not
#: an assertion and not a parameter: it is the one member of `config_hash` no
#: document holds, and the row exists to say exactly that. (ADR 0028 §5)
AGREEMENT_FIELD = "min_agreement"

type _Key = tuple[Scope, str, str, int]

type _RuleKey = tuple[Scope, str, int]


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
    #: Whether the suite declared that this path must not drift.
    #:
    #: On the **row of a comparison**, not on the `Artifact` it describes, and
    #: the difference is the whole mechanism: `redact()` replaces every artifact
    #: with a withheld one, so a flag living there would be dropped exactly for
    #: the reader who cannot check for themselves, while a row survives
    #: `withhold_artifacts` with its outcome intact. (ADR 0029 §3, §5)
    pinned: bool = False


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
class SuiteDelta:
    """What happened to one of the **rules** between two runs.

    `ConfigDelta` names the system that answered; this names the bar it was
    held to. Together they are the two halves of *why these numbers may not
    compare*, and until ADR 0028 only one of them was ever said out loud: a
    moved `config_hash` printed one sentence, so a lowered threshold and an
    added test case read identically.

    `rule` is the readable name, `assertion_id` the identity it was paired on —
    the same split as `AssertionDelta`, and for the same reason: a name is for
    the sentence, an identity is for the pairing.

    `field` names the value that moved — `threshold`, `tolerance`, `samples` —
    and is empty for a rule that arrived or left whole. One row per moved value
    rather than per rule, because a check whose threshold and tolerance both
    moved moved them in possibly opposite directions, and one row would have to
    choose a verb.

    `before` and `after` are floats or `None`, and `None` here means **not
    established** rather than zero: the sample count of a rule whose verdicts
    all errored before their fold is genuinely unknown, and the row says so.
    """

    rule: str
    assertion_id: str
    scope: Scope
    outcome: ConfigOutcome
    #: Which way the bar moved, where moving it has a way. Beside the outcome,
    #: never inside it.
    #:
    #: A threshold lowered, a tolerance raised, a rule removed: **loosened** —
    #: the run is held to less than the reference was approved under. The
    #: inverses: **tightened**. And `""` for `samples`, which takes no verb: more
    #: samples is a better-founded score *and*, because the interval a sampled
    #: check records is measured rather than declared, usually a **wider** noise
    #: floor — which `compare()` then forgives more movement inside. The two
    #: halves run opposite ways, nothing here can weigh them, so the row prints
    #: both counts and stops. (ADR 0028 §4)
    direction: Direction = ""
    field: str = ""
    before: float | None = None
    after: float | None = None
    #: Why a per-group gate appeared, for the one edit that adds a rule without
    #: anybody rewriting one. `""` everywhere else. (ADR 0028 §6)
    expansion: Expansion = ""

    @property
    def loosened(self) -> bool:
        """Derived, so nothing can claim a direction it was not given."""
        return self.direction == "loosened"


@dataclass(frozen=True, slots=True)
class _Rule:
    """One rule as the document remembers it: what it was called, and the three
    numbers that decide how it judged.

    `None` is *not established* in every one of them, never zero and never one.
    """

    name: str
    threshold: float | None
    tolerance: float | None
    samples: float | None


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
    #: What this run's side of the pair counted, **checked against the run it
    #: came from** — or `None` where no aggregate stands behind it, or where the
    #: run disproves the number it claimed.
    #:
    #: Carried rather than re-derived, and that is the whole reason it exists:
    #: the report's per-delta sentence called `denominator(delta.current)`
    #: itself, and a delta does not hold its run, so it was the one surface that
    #: could not check the arithmetic. Reading the fact off the row puts the
    #: three places a denominator is stated — `compare`'s line, the report's
    #: cell and `explain`'s reading — back on one number, which is the property
    #: `denominator()`'s own docstring claims for them. (F-4, the second 0.17.0
    #: delta-pass)
    counted: Denominator | None = None


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

    #: The `(case_id, check)` gaps the **reference** recorded, in its own order.
    #:
    #: On the comparison rather than read off the baseline by each renderer,
    #: because `facts()` is handed a run and a comparison and never the
    #: baseline: a fact only one of the two readers could see is how the report
    #: and the reading come to say different things. ADR 0027 §3 refuses to
    #: *promote* a run that does not reconcile, and that refusal runs once, on
    #: the machine that promoted; nothing asked the question again, so a
    #: reference admitting it did not know what it measured was compared against
    #: in silence. (F-10, the second 0.17.0 delta-pass)
    reference_unreconciled: tuple[tuple[str, str], ...] = ()

    #: What changed in the **rules** — the thresholds, tolerances, sample counts
    #: and gates `config_hash` fingerprints. The other half of the sentence
    #: `config_changed` has been saying alone since there was a comparison at
    #: all: it says *the rules moved*, and these say which ones and which way.
    #: Reported and never gated, because where the bar sits is a person's
    #: declaration and `promote_baseline` is where they sign it. (ADR 0028)
    suite_deltas: Sequence[SuiteDelta] = ()

    @property
    def artifacts_changed(self) -> bool:
        """Whether a file under test is known to have moved.

        `unknown` is not a change: a redacted comparison has no digest to
        compare, and answering "changed" would report a fact nobody has.
        """
        return any(d.outcome not in ("same", "unknown") for d in self.artifact_deltas)

    @property
    def pinned_drifted(self) -> bool:
        """Whether a path the author declared must not drift is known to have
        moved. The fact `exit_code()` reads, and the only one that returns 2.

        **`changed` only.** `new` is a path the reference never had — commonly
        the comparison right after the pin was declared — and `missing` is one
        this run does not record. Neither is drift, by the rule every outcome in
        this module is read by: absent is not a change. `unknown` is the
        question a redacted comparison cannot answer, and it is counted rather
        than guessed. (ADR 0029 §7, §8)
        """
        return any(d.pinned and d.outcome == "changed" for d in self.artifact_deltas)

    @property
    def pinned_unchecked(self) -> tuple[str, ...]:
        """The pinned paths this comparison could not answer for, by path.

        Never silent, and never a failure either. The author said *this must not
        drift*; redaction means nobody here can tell, and that is not *it did not
        drift*. A control that reported success when it could not run would
        produce the same green as one that ran, which is worse than no control —
        so the count travels and every surface prints it. The reader who *can*
        answer is the one holding both runs, and `withhold_artifacts` is how they
        answer it for the reader who cannot. (ADR 0029 §8)
        """
        return tuple(
            d.path for d in self.artifact_deltas if d.pinned and d.outcome == "unknown"
        )

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

    @property
    def loosened_rules(self) -> Sequence[SuiteDelta]:
        """The rules this run is held to less strictly than the reference was.

        What the headline names, and it is named on its own rather than netted
        against the tightenings. There is no *tightened on balance*: the
        quantity does not exist, and computing one would let three cosmetic
        tightenings bury the edit that matters. (ADR 0028 §4)
        """
        return tuple(d for d in self.suite_deltas if d.loosened)

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

    `considered` is also **checked against its own parts.** `as_metadata()`
    writes the four cells beside it and `considered` is exactly their sum, so a
    document carries the total and the addition that produced it; nothing used
    to check that the two agree. Where all four are present and do not sum to
    it, the number is not read: a total contradicted by its own parts is not a
    denominator, and reading it would put a figure in a sentence that the same
    document disproves. Where they are absent it is read as before — the cells
    are not what identifies an aggregate, `considered` is. (F-4, the second
    0.17.0 delta-pass)
    """
    value = verdict.score.metadata.get("considered")
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    # A negative count is refused for the reason a `bool` is: it is arithmetic
    # that cannot have happened, and "-5 of 2 cases counted" is a sentence
    # nobody can act on.
    if value < 0:
        return None
    cells: list[int] = []
    for name in _CELLS:
        cell = verdict.score.metadata.get(name)
        if isinstance(cell, bool) or not isinstance(cell, int):
            # One cell missing or not a number and the addition cannot be done
            # at all, which is not the same as an addition that disagrees.
            break
        cells.append(cell)
    else:
        if sum(cells) != value:
            return None
    return value


#: The four cells of the confusion matrix, as `Matrix.as_metadata()` writes
#: them. Their sum is `considered` by construction, which makes them the one
#: check on it a single verdict can carry out on its own.
_CELLS = (
    "true_positive",
    "false_positive",
    "true_negative",
    "false_negative",
)


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

    An exclusion that is **negative** takes the whole reading down rather than
    being skipped, and the asymmetry with a non-integer one is the point: a
    string tells us nothing and is ignorable, while `-7` is a number that makes
    `seen` smaller than `considered` and produced "43 of 36 cases counted; -7
    could not be judged." — two numbers that add up and cannot both be true.
    (F-4, the second 0.17.0 delta-pass)
    """
    considered = considered_cases(verdict)
    if considered is None:
        return None
    excluded: list[tuple[str, int]] = []
    for key in _EXCLUSIONS:
        value = verdict.score.metadata.get(key)
        if isinstance(value, bool) or not isinstance(value, int):
            continue
        if value < 0:
            return None
        if value:
            excluded.append((key, value))
    return Denominator(considered, tuple(excluded))


@dataclass(frozen=True, slots=True)
class CaseCount:
    """How many cases a run holds, and how many of them nobody judged.

    The two numbers an aggregate's own denominator can be checked against, read
    off the run rather than off the aggregate that is making the claim. A value
    rather than the `Run` itself so that `denominator` stays a function of
    numbers and the core keeps one direction of dependency. (F-4, the second
    0.17.0 delta-pass)
    """

    held: int
    suspended: int


def case_count(run: Run) -> CaseCount:
    """What `run` can be asked about any aggregate's denominator."""
    return CaseCount(
        held=len(run.results),
        suspended=sum(1 for case in run.results if case.suspended),
    )


def checked_denominator(verdict: Verdict, cases: CaseCount) -> Denominator | None:
    """`denominator(verdict)`, refused where the run it came from disproves it.

    Two checks, and both are arithmetic the run can settle on its own:

    1. a whole-run aggregate saw every case the run holds, so `seen` must equal
       `held`. A `considered` of 50 beside a 7-case exclusion, in a run of 50,
       was accepted and printed "50 of 57 cases counted" — a denominator larger
       than the suite it was measured on;
    2. a suspended case has no verdict, so no aggregate can have counted it:
       `considered` cannot exceed the cases that were not suspended. This is
       the one that caught the sentence worth catching — "All 20 cases
       counted." over a run where five were set aside.

    **The first check does not apply to a grouped aggregate**, and the exception
    is load-bearing rather than cautious: a `by_group` aggregate is computed
    over its own group's cases alone, so its `seen` is *meant* to be smaller
    than the run. A stored run records no group per case — which is why
    `split_grouped_name` exists at all — so the run cannot settle this one, and
    checking it anyway would strip the sentence from every grouped figure in
    every report. The second check still holds there, as an upper bound: a
    group's unsuspended cases cannot outnumber the run's.

    Refused means **not read**, never raised: a reading that refuses a document
    cannot report on it, which is `considered_cases`' rule and the reason the
    contradicted figure simply loses its clause rather than taking the report
    down with it. What it does not do is decide comparability — a denominator
    nobody can read is absent, and an absent one has always compared. That is
    the question this pass left open, not one it answers. (F-4, the second
    0.17.0 delta-pass)
    """
    counted = denominator(verdict)
    if counted is None:
        return None
    _, group = split_grouped_name(verdict.score.name)
    if group is None and counted.seen != cases.held:
        return None
    if counted.considered > cases.held - cases.suspended:
        return None
    return counted


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

    # Once, over every row, rather than at the five places a delta is built:
    # the check needs the run, every branch above has already decided what the
    # row says, and a fact attached in one place cannot be forgotten by the
    # sixth branch somebody adds. (F-4, the second 0.17.0 delta-pass)
    cases = case_count(run)
    deltas = [
        delta
        if delta.current is None
        else replace(delta, counted=checked_denominator(delta.current, cases))
        for delta in deltas
    ]

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
        reference_unreconciled=unreconciled(baseline),
        # Computed whatever `config_hash` says, rather than only when it moved.
        # Gating it on the flag would make the flag the source of truth for the
        # rows and the rows the explanation of the flag, which is two answers to
        # one question; and it is `()` on an unchanged suite anyway, because
        # there is nothing for it to find.
        suite_deltas=suite_deltas(run, baseline),
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


def suite_deltas(run: Run, baseline: Run) -> tuple[SuiteDelta, ...]:
    """What moved in the **rules**, named, when `config_hash` moved.

    The mirror of `config_deltas`, which names the system under test. This names
    the ruler it was held against: the checks, their thresholds and tolerances,
    how many times each case was sampled, and the aggregate gates. (ADR 0028 §2)

    **Derived, never recorded.** Everything read here is already in both
    documents and has been at every schema version: `assertion_id`, `threshold`
    and `tolerance` are mandatory on every verdict, and the sample count rides
    `metadata["samples"]`. So no field was added to the document for this, and a
    baseline promoted a year ago is read as well as one promoted today
    (ADR 0028 §1).

    It inherits `config_deltas`' three rules against reporting a change nobody
    established, and adds a fourth:

    1. **Neither side recorded any rule** — which takes a run whose every case
       is suspended — and the answer is `()`. Absent is not *every rule was
       removed*.
    2. **One side recorded nothing**: `unknown`, never `new` or `missing`. In
       practice unreachable, for the mandatory fields above; kept because the
       day a field here becomes optional is the day its absence in an old
       baseline would otherwise render as an edit.
    3. **A value not established on both sides** is `unknown` rather than
       guessed. The one that arises is the sample count of a rule whose verdicts
       all errored before the fold: an errored verdict may carry no metadata at
       all, and reading its absence as *one sample* would report `5 -> 1` about
       a suite nobody touched.
    4. **`min_agreement` is never named.** It is the one thing in `config_hash`
       that no document holds, and the measured `agreement` beside it is not it.
       Deriving the floor from the vote would be the guess wearing a finding's
       clothes that rule 3 exists to forbid. Where either side sampled, one
       `unknown` row says so; where neither did, nothing is said, because a
       floor that never gated anything is not a silence worth breaking.
       (ADR 0028 §5)

    **A case is not a rule.** The key is the assertion's identity and the rows
    are unioned over the cases, so adding, removing or suspending a case
    produces nothing here. That is the shape of the key rather than a
    convention to be careful about; the case set is named by `compare()`'s own
    `new` and `missing` deltas. §6's grouped gate is the one shape that looks
    like an exception and is not — see `_expansion`.

    Nothing read here is ever withheld: `redact()` keeps the threshold, the
    tolerance and the identity, and a sample count is an `int` that travels on
    its own merit. A redacted run therefore yields the **complete** set of rows,
    which is the point rather than a bonus — the party that holds the signal and
    none of the payload is the one least able to see a bar quietly lowered.
    """
    now, before = _rules(run), _rules(baseline)
    if not now and not before:
        return ()

    deltas: list[SuiteDelta] = []
    for key in sorted(now.keys() | before.keys()):
        here, there = now.get(key), before.get(key)
        if there is None:
            assert here is not None
            deltas.append(
                SuiteDelta(
                    rule=here.name,
                    assertion_id=key[1],
                    scope=key[0],
                    outcome="new",
                    # A rule that was not there is a bar this run is held to and
                    # the reference was not. Direction is about the rule, never
                    # about what it then measured. (ADR 0028 §4)
                    direction="tightened",
                    expansion=_expansion(here.name, key[0], before),
                )
            )
            continue
        if here is None:
            deltas.append(
                SuiteDelta(
                    rule=there.name,
                    assertion_id=key[1],
                    scope=key[0],
                    outcome="missing",
                    direction="loosened",
                )
            )
            continue
        deltas.extend(_moved(key, here, there))

    deltas.extend(
        _agreement_row(now, before, moved=run.config_hash != baseline.config_hash)
    )
    return tuple(deltas)


#: How each field moves when it is **loosened** — the bar admitting more than
#: the reference approved. A threshold falling lets a lower score pass; a
#: tolerance rising forgives a larger drop before it counts as a regression.
#:
#: `samples` is deliberately absent, and `_moved` reads that absence as *no
#: verb*. See `SuiteDelta.direction`.
_LOOSENS: dict[str, int] = {"threshold": -1, "tolerance": +1}


def _moved(key: _RuleKey, here: _Rule, there: _Rule) -> tuple[SuiteDelta, ...]:
    """One row per moved value, never one per rule.

    A check whose threshold and tolerance both moved gets two rows, because they
    may have moved in opposite directions and a single row would have to pick a
    verb. Ordered as `_FIELDS` declares them, so two equivalent comparisons read
    identically.
    """
    out: list[SuiteDelta] = []
    for field in ("threshold", "tolerance", "samples"):
        after, prior = getattr(here, field), getattr(there, field)
        if after is None or prior is None:
            # Rule 3: not established on both sides. The row still appears,
            # because a reader who is told nothing cannot tell "unchanged" from
            # "unknowable", and this is the one field that can be either.
            if after != prior:
                out.append(
                    SuiteDelta(
                        rule=here.name,
                        assertion_id=key[1],
                        scope=key[0],
                        outcome="unknown",
                        field=field,
                        before=prior,
                        after=after,
                    )
                )
            continue
        if after == prior:
            continue
        sign = _LOOSENS.get(field, 0)
        direction: Direction = ""
        if sign:
            loosened = (after < prior) if sign < 0 else (after > prior)
            direction = "loosened" if loosened else "tightened"
        out.append(
            SuiteDelta(
                rule=here.name,
                assertion_id=key[1],
                scope=key[0],
                outcome="changed",
                direction=direction,
                field=field,
                before=prior,
                after=after,
            )
        )
    return tuple(out)


def _expansion(name: str, scope: Scope, before: dict[_RuleKey, _Rule]) -> Expansion:
    """Why a per-group gate is here, when the new rule is one.

    `run_assertions` is the **expanded** list, so a case labelled into a group
    that did not exist adds an aggregate and moves `config_hash`. Left
    unexplained, that reads as somebody rewriting the rules, which is the one
    thing §3 promises an ordinary edit will not do.

    **The case that introduced the group is not named, because it cannot be and
    because it would often be the wrong answer.** Neither document records
    membership — `CaseResult` has no group and `case_to_dict` writes none, which
    is ADR 0010 §1 keeping membership in the repository — and re-labelling an
    existing case produces a group with no new case behind it at all. So the
    question is answered from the one fact both documents do carry, the
    `[group=...]` grammar `split_grouped_name` reads:

    - the reference already gated this aggregate per group, and not on this
      group -> the **group** is new, and a group exists only where a case
      declares it, so a case was labelled and no rule was rewritten;
    - the reference gated this aggregate as a whole and never per group ->
      `by_group` was set on it, which is the author changing the rules.

    Both are derived. Neither is a guess, and no case is accused of anything.
    (ADR 0028 §6)
    """
    _, group = split_grouped_name(name)
    if scope != "run" or group is None:
        return ""
    base, _ = split_grouped_name(name)
    for rule in before.values():
        prefix, other = split_grouped_name(rule.name)
        if other is not None and prefix == base:
            return "new_group"
    return "now_grouped"


def _agreement_row(
    now: dict[_RuleKey, _Rule],
    before: dict[_RuleKey, _Rule],
    *,
    moved: bool,
) -> tuple[SuiteDelta, ...]:
    """The one value in `config_hash` that no document holds.

    Two conditions, and both are about not breaking a silence for nothing:

    - **the fingerprint moved.** On a suite that did not change there is nothing
      this row could be about, and printing *the agreement floor cannot be
      compared* under *the suite is unchanged from the reference* would be the
      table contradicting the sentence above it. Where the hash **did** move and
      every other member of it is accounted for by a row, this is the reader's
      answer to *then what moved?* — and it is the case the row is worth having
      for.
    - **either side sampled.** A floor below one sample gated nothing, so a
      suite left at `samples=1` never meets a row about it.

    The row is `unknown` and carries no values, because there are none to carry:
    the measured `agreement` beside it is what the samples did, not the bar they
    were held to. (ADR 0028 §5)
    """
    sampled = any(
        rule.samples is not None and rule.samples > 1
        for side in (now, before)
        for rule in side.values()
    )
    if not (moved and sampled):
        return ()
    # `field` is left empty on purpose: it names the value of a rule that moved,
    # and here the rule *is* the value. `rule` carries the name so the row reads
    # like every other one, and `assertion_id` is empty because this is a
    # parameter of the suite and not a check it declares.
    return (
        SuiteDelta(
            rule=AGREEMENT_FIELD,
            assertion_id="",
            scope="run",
            outcome="unknown",
        ),
    )


def _rules(run: Run) -> dict[_RuleKey, _Rule]:
    """Every rule the run was judged by, read back off its own verdicts.

    Keyed `(scope, assertion_id, occurrence)`, which is `index_verdicts`' key
    without the case: the driver asks every declared assertion of every case in
    declaration order, so the n-th verdict of a given identity is the n-th
    assertion of that identity in every case it appears on. The occurrence
    matters because `identity` **excludes** threshold and tolerance, so two
    assertions differing only in where their bar sits share one identity and
    would otherwise collapse into a rule that appeared to contradict itself.
    """
    seen: dict[_RuleKey, list[Verdict]] = {}
    for case in run.results:
        counted: Counter[str] = Counter()
        for verdict in case.verdicts:
            ident = verdict.assertion_id
            seen.setdefault(("case", ident, counted[ident]), []).append(verdict)
            counted[ident] += 1
    counted_run: Counter[str] = Counter()
    for verdict in run.aggregate:
        ident = verdict.assertion_id
        seen.setdefault(("run", ident, counted_run[ident]), []).append(verdict)
        counted_run[ident] += 1
    return {key: _rule_from(verdicts) for key, verdicts in seen.items()}


def _rule_from(verdicts: Sequence[Verdict]) -> _Rule:
    """One rule, folded from every verdict that was judged by it.

    Threshold and tolerance come off the assertion, so every case records the
    same pair and folding is a formality — except for a document somebody built
    by hand, where it is not. A value the sides of the run disagree about is
    `None`, meaning *not established*, and the row it produces says `unknown`
    rather than picking the first one it met.
    """
    return _Rule(
        name=verdicts[0].score.name,
        threshold=_agreed(v.threshold for v in verdicts),
        tolerance=_agreed(v.tolerance for v in verdicts),
        samples=_agreed(_samples_of(v) for v in verdicts),
    )


def _samples_of(verdict: Verdict) -> float | None:
    """How many times this check was measured, or `None` where it cannot be told.

    `combine_samples` writes the count into metadata whenever it folds, so its
    absence means one sample — **unless the verdict errored before any fold
    happened**, which is what a case whose target raised records. There the
    count is genuinely unknown, and reading the absence as one would invent a
    `5 -> 1` on a suite nobody edited. (ADR 0028 §1)
    """
    recorded = verdict.score.metadata.get("samples")
    if isinstance(recorded, int) and not isinstance(recorded, bool):
        # Kept an `int`. A count is a count, and `5.0 -> 3.0` in a report is a
        # number wearing a threshold's clothes. The field is typed `float` for
        # the two that really are fractions, and an `int` sits inside it.
        return recorded
    return None if verdict.status == "error" else 1


def _agreed(values: Iterable[float | None]) -> float | None:
    """The one value they all carry, or `None` if they do not agree on one.

    A `None` among them is *not established*, so it does not outvote the rest:
    one case that errored before its fold cannot unknow a sample count every
    other case recorded. Disagreement between two **stated** values is different
    and does produce `None`, because there is no honest way to choose.
    """
    distinct = {value for value in values if value is not None}
    return distinct.pop() if len(distinct) == 1 else None


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
                # Carried beside the outcome, and the pair is the point: this
                # function exists so a party holding both runs can tell someone
                # who holds neither *that* a file moved. Keeping `outcome` and
                # dropping `pinned` would hand them a document that knows a file
                # moved and has forgotten anybody declared it must not — green,
                # type-checked and quietly wrong. Guarded by
                # `test_a_withheld_comparison_still_knows_the_path_was_pinned`
                # and its mutation control. (ADR 0029 §5)
                pinned=delta.pinned,
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
    # Read from `run` and not from the union, because a pin is a declaration
    # about the side being judged: a pin the reference carried and this run
    # dropped is an author withdrawing it, which ADR 0029 §9 reports elsewhere
    # and refuses to enforce — a pin nobody could ever remove is worse than no
    # pin. `diff()` passes its right-hand run here, and gates on nothing.
    pinned = set(run.pinned)
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
                pinned=path in pinned,
            )
        )
    return tuple(deltas)
