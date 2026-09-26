"""The calibration case, as the document holds it: a check, a band, and whether
the score stayed inside it.

The canary watches whether the model is still that model; the calibration case
watches whether the scale is still a scale. Its answer is known to be partially
correct, so a judge that still places values on a scale scores it somewhere in
the middle — and a judge that has gone binary scores it at an extreme, which is
the one thing a repeatability figure cannot see (ADR 0024 §1, §4).

What lives here is the half that crosses into a run: which check, by identity
and by name, and two numbers. The answer itself is payload and is declared in
`digline.run.Calibration`; it is never written.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from digline.core.types import at_precision

if TYPE_CHECKING:
    # Only for the annotation: `run.py` imports `CalibrationBand` from here, so
    # a runtime import the other way would be a cycle.
    from digline.core.run import Run

__all__ = ["CalibrationBand", "ScaleLost", "scale_lost"]


@dataclass(frozen=True, slots=True)
class CalibrationBand:
    """Which judged check a calibration case calibrates, and where its score has
    to land.

    **Both ends strictly inside `(0, 1)`**, compared at storage precision. A
    band that contains 0 or 1 counts an extreme as in band, so it cannot detect
    the one thing it exists for: a judge that has collapsed onto the extremes
    passes it forever. That is fixed decision 3, applied to the instrument
    rather than to the system. (ADR 0024 §4.2)

    **`assertion_id` is what binds, `check` is what is said.** The suite
    resolves the declared name to exactly one assertion when it loads, and the
    identity it resolved to is what a verdict carries; a verdict's
    `score.name` is whatever the assertion chose to call its `Score`, and a
    third-party one may call it otherwise. Binding on the name let such a band
    match nothing and read as *no band was lost*. (ADR 0024 §4.7, amended
    2026-09-26)
    """

    check: str
    low: float
    high: float
    assertion_id: str

    def __post_init__(self) -> None:
        if not self.check:
            raise ValueError(
                "a calibration names no check: the band has to belong to the "
                "judged assertion it calibrates"
            )
        if not self.assertion_id:
            raise ValueError(
                f"the calibration of {self.check!r} carries no assertion_id: a "
                "band binds to its verdict by identity, and one with none "
                "binds to nothing"
            )
        low, high = self.bounds(self.check, self.low, self.high)
        object.__setattr__(self, "low", low)
        object.__setattr__(self, "high", high)

    @staticmethod
    def bounds(check: str, low: float, high: float) -> tuple[float, float]:
        """`low` and `high` at storage precision, or the refusal of the band.

        Separate from the constructor because a declaration is checked before
        any identity exists: `Calibration` refuses a malformed band when the
        suite is written, and the band itself is built only once the suite has
        resolved which assertion it belongs to.
        """
        low, high = at_precision(low), at_precision(high)
        if not (0.0 < low <= high < 1.0):
            raise ValueError(
                f"the calibration of {check!r} declares the band "
                f"{low:.6f}–{high:.6f}. Both ends must lie strictly between 0 "
                "and 1, with low no greater than high: a band that contains an "
                "extreme counts a judge that has collapsed onto that extreme as "
                "in band, so it cannot detect the one thing it exists for"
            )
        return low, high

    def holds(self, score: float) -> bool:
        """Whether `score` lies inside the band, both ends inclusive."""
        value = at_precision(score)
        return self.low <= value <= self.high


@dataclass(frozen=True, slots=True)
class ScaleLost:
    """One calibration case whose score landed outside its declared band.

    Everything the sentence needs and nothing it does not. `samples` is the raw
    per-sample scores, because *every one at an extreme* and *a mean just outside
    the band* are different pictures, and the reader is owed which one it is.
    Empty where the verdict recorded none.
    """

    case_id: str
    check: str
    score: float
    samples: Sequence[float]
    low: float
    high: float


def scale_lost(run: Run) -> tuple[ScaleLost, ...]:
    """Every calibration case in `run` whose score is outside its band.

    From the run alone, like `unjudged_cases`: it compares a score with a
    declared band rather than with a past, so it needs no reference and a first
    run can be stopped by it.

    An errored verdict does not fire it. That case is unjudged, which is already
    exit 2 and already said; a lost scale is a real score in the wrong place,
    and the two must not be counted as one. A suspended calibration case has no
    verdict and says nothing either. (ADR 0024 §4.5)

    The score read is the recorded one — the folded mean, which is what every
    other verdict is judged on.

    **The band binds by `assertion_id`, and a band that binds nothing cannot
    reach here**: `Run` refuses it at construction. Empty therefore means *every
    band was checked and held*, never *no band was checked* — the two used to be
    the same value. (ADR 0024 §4.7, amended 2026-09-26)
    """
    lost: list[ScaleLost] = []
    for case in run.results:
        band = case.calibration
        if band is None:
            continue
        for verdict in case.verdicts:
            if verdict.assertion_id != band.assertion_id or verdict.status == "error":
                continue
            score = verdict.score.score
            if score is None or band.holds(score):
                continue
            lost.append(
                ScaleLost(
                    case_id=case.case_id,
                    check=band.check,
                    score=score,
                    samples=tuple(verdict.score.samples),
                    low=band.low,
                    high=band.high,
                )
            )
    return tuple(lost)
