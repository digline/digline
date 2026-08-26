"""Sampling: what to do when the same question, asked twice, answers twice.

Two different kinds of noise, and they are not the same problem:

- **The judge varies** on one output. `Repeated` wraps an assertion and asks it
  several times.
- **The system varies** on one input. That needs several calls to the target,
  which only the driver can make; it hands the resulting verdicts here.

Both end at `combine_samples`, so one definition of agreement serves both.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from statistics import fmean

from digline.core.assertions import AssertionBase
from digline.core.protocols import Assertion
from digline.core.ratio import Ratio, as_agreement
from digline.core.types import (
    EvaluatorInputs,
    OutputKind,
    Score,
    Status,
    Verdict,
)

__all__ = ["COST_KEY", "TOTAL_COST_KEY", "Repeated", "combine_samples"]

#: The one metadata key whose *total* across samples is reported.
#:
#: Not a generic rule and not magic: cost is money, and sampling multiplies the
#: bill while `CostBudget` — correctly — keeps judging one call at a time. The
#: value summed here was written by the assertions themselves, so everything in
#: `Score.metadata` still originates from something that measured it.
COST_KEY = "cost_usd"
TOTAL_COST_KEY = "total_cost_usd"


def _agreement(statuses: Sequence[Status]) -> float:
    """The fraction of samples that reached the same verdict as the majority.

    **This is the definition, and it was chosen over the alternatives.** Not the
    variance of the scores, nor the width of the spread, because agreement
    answers the question a reader actually has: *would this check have said the
    same thing if I had run it again?*

    A rubric whose scores wobble between 0.80 and 0.88 is noisy and harmless; one
    that wobbles between 0.69 and 0.71 across a threshold of 0.70 is not, and only
    agreement tells the two apart. The spread is reported alongside for whoever
    wants the other view.

    Ties break on the status name so the result is deterministic. A tie means
    agreement of at most one half, which any sensible `min_agreement` rejects.
    """
    counts = Counter(statuses)
    _status, hits = max(counts.items(), key=lambda kv: (kv[1], kv[0]))
    return hits / len(statuses)


def _numeric(verdicts: Sequence[Verdict], key: str) -> list[float]:
    """The values of `key` across the samples, when every one of them measured
    it as a number. Booleans are excluded: `isinstance(True, int)` is true in
    Python, and averaging flags is meaningless."""
    found: list[float] = []
    for verdict in verdicts:
        value = verdict.score.metadata.get(key)
        if isinstance(value, bool) or not isinstance(value, int | float):
            return []
        found.append(float(value))
    return found


def _folded_metadata(verdicts: Sequence[Verdict]) -> Mapping[str, object]:
    """What the samples measured, carried through the fold.

    Without this the combined verdict would keep only the sampling statistics
    and drop `cost_usd`, `max_usd`, `ratio` — the raw values a budget records,
    and the whole reason its score is graded rather than binary. Sampling must
    not cost the reader the facts.

    The rule matches the one used for the score itself: **numbers are averaged**
    — which leaves a constant like a declared cap untouched and turns a measured
    cost into the mean per call. Anything else is kept when every sample agrees
    on it and dropped when they disagree, because there is no honest way to
    average two different strings.
    """
    if not verdicts:
        return {}
    shared = set(verdicts[0].score.metadata)
    for verdict in verdicts[1:]:
        shared &= set(verdict.score.metadata)

    folded: dict[str, object] = {}
    for key in sorted(shared):
        numbers = _numeric(verdicts, key)
        if numbers:
            folded[key] = fmean(numbers)
            continue
        values = [v.score.metadata[key] for v in verdicts]
        if all(value == values[0] for value in values[1:]):
            folded[key] = values[0]
    return folded


def _rendered(verdicts: Sequence[Verdict]) -> str:
    return ", ".join(
        "error" if v.score.score is None else f"{v.score.score:.6f}" for v in verdicts
    )


def combine_samples(verdicts: Sequence[Verdict], *, min_agreement: float) -> Verdict:
    """Fold repeated verdicts for one check into the one that gets recorded.

    **With a single sample this is the identity function.** Sampling must not
    change a run that does not sample: the verdict is returned untouched, with
    no metadata added, so a suite left at `samples=1` produces the same bytes it
    produced before sampling existed.

    Otherwise:

    - the score is the **mean of the per-sample scores**, so a budget still
      judges what one call cost — which is what the user pays per answer — and
      raising `samples` never trips `CostBudget` on its own;
    - `agreement` and `spread` say how much the samples disagreed;
    - below `min_agreement` the outcome is **`error`**, not `fail`. A judgement
      that does not repeat is not a failure, it is a judgement that could not be
      given — which is what the third state is for, and it means a suite too
      noisy to trust cannot be promoted to a baseline.

    Metadata carries `samples`, `agreement`, `spread`, `errored_samples` and the
    raw `scores`. All numbers, so all of it crosses a boundary: the software
    house sees how unstable a check is without seeing what it judged. What the
    samples themselves measured is folded in alongside — see
    `_folded_metadata` — so sampling does not cost the reader the raw values.
    """
    if not verdicts:
        raise ValueError("combine_samples needs at least one verdict")
    if len(verdicts) == 1:
        return verdicts[0]

    first = verdicts[0]
    scores = [v.score.score for v in verdicts if v.score.score is not None]
    agreement = _agreement([v.status for v in verdicts])

    def failed(reason: str) -> Verdict:
        return Verdict(
            score=Score(name=first.score.name, score=None),
            threshold=first.threshold,
            tolerance=first.tolerance,
            status="error",
            reason=reason,
            assertion_id=first.assertion_id,
        )

    if not scores:
        return failed(f"no sample could be judged over {len(verdicts)} attempts")
    if agreement < min_agreement:
        return failed(
            f"the samples did not agree: {agreement:.2f} of them share the "
            f"majority verdict, below the required {min_agreement:.2f} "
            f"(scores: {_rendered(verdicts)})"
        )

    mean = fmean(scores)
    metadata: dict[str, object] = dict(_folded_metadata(verdicts))
    metadata.update(
        {
            "samples": len(verdicts),
            "agreement": agreement,
            "spread": max(scores) - min(scores),
            "errored_samples": len(verdicts) - len(scores),
            "scores": list(scores),
        }
    )
    costs = _numeric(verdicts, COST_KEY)
    if costs:
        metadata[TOTAL_COST_KEY] = sum(costs)

    return Verdict(
        score=Score(name=first.score.name, score=mean, metadata=metadata),
        threshold=first.threshold,
        tolerance=first.tolerance,
        status="pass" if mean >= first.threshold else "fail",
        reason=f"mean of {len(verdicts)} samples ({_rendered(verdicts)})",
        assertion_id=first.assertion_id,
    )


@dataclass(frozen=True, slots=True)
class Repeated(AssertionBase):
    """Asks `inner` several times and folds the answers. For judge noise.

    Use it around `LlmRubric`: the output is the same each time, so what varies
    is the grader. For *system* noise — the same input answered differently —
    set `Suite.samples`, because that needs several calls to the target and only
    the driver can make those.

    Wrapping an assertion **changes its identity**, so the first comparison
    after wrapping reports a `new` and a `missing` for that check. Deliberate: a
    loud one-off event in a pull request is the right way for "this check is now
    judged three times" to reach a reviewer.
    """

    inner: Assertion
    samples: int
    #: A count of samples, so it may be written as one: `"2/3"` or a Fraction.
    #: A float that no `k/samples` can produce is refused (see `as_agreement`).
    min_agreement: Ratio
    name: str = ""
    # Copied from `inner` rather than declared: two copies of a threshold drift
    # apart, and the wrapper has no opinion of its own about where the bar sits.
    # `init=False` makes it impossible to pass one that contradicts the inner.
    threshold: float = field(init=False, default=0.0)
    tolerance: float = field(init=False, default=0.0)
    accepts: frozenset[OutputKind] = field(init=False, default=frozenset())

    def __post_init__(self) -> None:
        object.__setattr__(self, "threshold", self.inner.threshold)
        object.__setattr__(self, "tolerance", self.inner.tolerance)
        object.__setattr__(self, "accepts", self.inner.accepts)
        if self.samples < 2:
            raise ValueError(
                f"Repeated.samples must be at least 2, got {self.samples}: "
                "repeating once is the assertion itself"
            )
        object.__setattr__(
            self,
            "min_agreement",
            as_agreement(
                self.min_agreement,
                samples=self.samples,
                field="Repeated.min_agreement",
            ),
        )
        if not self.name:
            object.__setattr__(self, "name", self.inner.name)

    def __call__(self, inputs: EvaluatorInputs) -> Verdict:
        combined = combine_samples(
            [self.inner(inputs) for _ in range(self.samples)],
            min_agreement=float(self.min_agreement),
        )
        # Stamped with *this* assertion's name and identity: the fold above
        # carries the inner's, and the record has to name what the suite
        # declared.
        return Verdict(
            score=Score(
                name=self.name,
                score=combined.score.score,
                metadata=combined.score.metadata,
            ),
            threshold=combined.threshold,
            tolerance=combined.tolerance,
            status=combined.status,
            reason=combined.reason,
            assertion_id=self.identity,
        )
