"""Shape: how much of a judged check's scores sit at the extremes, in this run and
in its reference. (ADR 0024 §6)

A measurement without its sentence. The two shares and their counts are printed
side by side; whether one is *more than* the other is a threshold that has not
been sized on data, and ADR 0024 §6.3 refuses to invent it here. So nothing in
this module compares the two numbers, and nothing reads it as a gate: it is a
diagnosis beside the calibration case, which is the gate.

Read from a `Comparison` alone, because a reading is a function of the documents
it is handed: which verdicts are judged comes from `Verdict.judged`, written by
the driver from the check's `KIND` (§6.4).

**The known hole, stated at its weight.** A check whose class declares no `KIND`
is left out and announced by `digline run`. But `FromAutoevals` declares
`wrapper` and has no inner assertion to read through, so an autoevals scorer
that calls a model is neither judged nor announced: this reading cannot see it
at all. Closing that needs the adapter to declare what its scorer is, which is a
decision of its own and is not taken here.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from digline.core import Comparison, Verdict, at_precision

__all__ = ["Shape", "ShapeSide", "shape"]

#: The metadata key `Faithfulness` records its claim count under. The one key
#: this reading names, and it may: nothing gates on it. (ADR 0024 §6.2)
CLAIMS_KEY = "claims_total"


@dataclass(slots=True)
class ShapeSide:
    """One side of the reading: its raw scores, and what was left out of them."""

    #: Raw per-sample scores at exactly 0.0 or 1.0, at storage precision.
    extremes: int = 0
    #: Raw per-sample scores read.
    scores: int = 0
    #: Verdicts left out because their claim count proves a single claim, so
    #: they can only score 0 or 1 by arithmetic.
    single_claim: int = 0
    #: Sampled verdicts read whose per-sample claim counts were not recorded:
    #: the fold keeps the mean, and a mean of 2 or more does not prove that no
    #: sample made one claim.
    claims_unrecorded: int = 0
    #: Verdicts left out because their per-sample scores are means of
    #: judgements, not judgements: stamped `sample_means`, or — on the
    #: reference side only — sampled, unstamped, and paired by identity with a
    #: stamped verdict of the run. (ADR 0024 §6.5)
    sample_means: int = 0


@dataclass(frozen=True, slots=True)
class Shape:
    """One judged check. `reference` is `None` where the reference records no
    judged verdict for it, which is every reference written before schema 12:
    there is nothing to set the run's share against, and the reading says so."""

    check: str
    assertion_id: str
    run: ShapeSide = field(default_factory=ShapeSide)
    reference: ShapeSide | None = None


def _raw(verdict: Verdict) -> tuple[float, ...]:
    """The per-sample scores, never the folded mean: at `samples=5` a check that
    is binary per sample folds to 0, 0.2, … 1, which reads as graded."""
    if verdict.score.sampled:
        return verdict.score.samples
    assert verdict.score.score is not None
    return (verdict.score.score,)


def _count(side: ShapeSide, verdict: Verdict, *, unstamped_fold: bool = False) -> None:
    if verdict.score.sample_means or (unstamped_fold and verdict.score.sampled):
        # Before the claim count: a verdict whose samples are means is not read
        # at all, so nothing else about it is either. (ADR 0024 §6.5)
        side.sample_means += 1
        return
    claims = verdict.score.metadata.get(CLAIMS_KEY)
    if isinstance(claims, int | float) and not isinstance(claims, bool):
        if claims < 2:
            # At one sample the count is exact; at more, a mean below 2 proves
            # some sample made one claim. Either way, left out and counted.
            side.single_claim += 1
            return
        if verdict.score.sampled:
            side.claims_unrecorded += 1
    for value in _raw(verdict):
        side.scores += 1
        if at_precision(value) in (0.0, 1.0):
            side.extremes += 1


def shape(comparison: Comparison) -> tuple[Shape, ...]:
    """Every judged check of the run, its share at the extremes, and the
    reference's.

    Over the cases that count: not a canary, not a calibration case, and a
    verdict that was judged rather than errored. A suspended case has no
    verdict and so no delta. Ordered by check name, then identity, so two
    readings of one comparison are equal.
    """
    counted = [
        delta
        for delta in comparison.deltas
        if delta.scope == "case" and not delta.canary and not delta.calibration
    ]
    # **The pairing, by identity.** A reference migrated from schema 12 holds
    # folds nobody stamped, and the step could not derive the stamp. Where this
    # run stamped a check's verdicts, a sampled, unstamped reference verdict of
    # the same identity is either such a fold or one taken at a different suite
    # `samples` — and neither can be read as judgements. So it is left out and
    # counted: **the rule errs toward leaving a verdict out, never toward
    # misreading one.** (ADR 0024 §6.5)
    folds = {
        delta.current.assertion_id
        for delta in counted
        if delta.current is not None and delta.current.score.sample_means
    }
    runs: dict[str, tuple[str, ShapeSide]] = {}
    references: dict[str, ShapeSide] = {}
    for delta in counted:
        now, before = delta.current, delta.baseline
        if now is not None and now.judged:
            _, side = runs.setdefault(now.assertion_id, (now.score.name, ShapeSide()))
            if now.status != "error":
                _count(side, now)
        if before is not None and before.judged:
            side = references.setdefault(before.assertion_id, ShapeSide())
            if before.status != "error":
                _count(side, before, unstamped_fold=before.assertion_id in folds)
    return tuple(
        Shape(name, identity, side, references.get(identity))
        for identity, (name, side) in sorted(
            runs.items(), key=lambda item: (item[1][0], item[0])
        )
    )
