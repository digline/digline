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
from digline.core.types import ConfigValue, Verdict

__all__ = [
    "IDENTITY_FIELD",
    "ArtifactDelta",
    "AssertionDelta",
    "Comparison",
    "ConfigDelta",
    "Outcome",
    "Scope",
    "compare",
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
        wanted = frozenset(outcomes)
        return tuple(d for d in self.deltas if d.outcome in wanted)

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
        tally: Counter[Outcome] = Counter(d.outcome for d in self.deltas)
        return dict(tally)


def _changed(deltas: Sequence[ConfigDelta]) -> bool:
    return any(d.outcome not in ("same", "unknown") for d in deltas)


def _index(run: Run) -> dict[_Key, Verdict]:
    """Index by (case, assertion identity, occurrence).

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
class _Noise:
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
        return self.low <= score <= self.high

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


def _noise(verdict: Verdict) -> _Noise:
    score = verdict.score
    if not score.sampled:
        return _Noise()
    return _Noise(score.sample_min, score.sample_max, len(score.samples))


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
    current, previous = _index(run), _index(baseline)
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
                )
            )
            continue

        # Past this point both statuses are pass or fail, so both scores are
        # numeric: Verdict.__post_init__ guarantees it.
        assert now.score.score is not None and before.score.score is not None
        delta = now.score.score - before.score.score
        was, is_now = f"{before.score.score:.6f}", f"{now.score.score:.6f}"

        if now.status != before.status:
            outcome: Outcome = "regressed" if before.status == "pass" else "improved"
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
            deltas.append(
                AssertionDelta(
                    case_id, assertion, outcome, scope, now, before, delta, why
                )
            )
            continue

        # The interval is the **baseline's**, never this run's. The baseline is
        # the promoted, reviewed measurement; letting a noisy new run widen its
        # own excuse is how a regression hides inside a model that got less
        # stable. (ADR 0006 §5)
        floor = _noise(before)
        within_noise = False

        if abs(delta) <= now.tolerance:
            # Declared before measured, and the reason says which one spoke. A
            # tolerance is what a reviewer decided is acceptable; the interval
            # is what the system does. A reader is never left to guess which of
            # the two called this unchanged.
            moved_to: Outcome = "unchanged"
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
                within_noise=within_noise,
                noise_min=floor.low,
                noise_max=floor.high,
                noise_samples=floor.count,
            )
        )

    return Comparison(
        tenant=run.tenant,
        environment=run.environment,
        baseline_environment=baseline.environment,
        suite=run.suite,
        config_changed=run.config_hash != baseline.config_hash,
        deltas=tuple(deltas),
        artifact_deltas=_artifact_deltas(run, baseline),
        target_config_deltas=_config_deltas(run.target_config, baseline.target_config),
        judge_config_deltas=_config_deltas(run.judge_config, baseline.judge_config),
    )


def _config_deltas(now: SystemConfig, before: SystemConfig) -> tuple[ConfigDelta, ...]:
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
    """
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


def _artifact_deltas(run: Run, baseline: Run) -> tuple[ArtifactDelta, ...]:
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
