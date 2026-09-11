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
    at_precision,
    meets,
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
    """The fraction of *all* the samples that reached the majority judged
    verdict.

    **This is the definition, and it was chosen over the alternatives.** Not the
    variance of the scores, nor the width of the spread, because agreement
    answers the question a reader actually has: *would this check have said the
    same thing if I had run it again?*

    A rubric whose scores wobble between 0.80 and 0.88 is noisy and harmless; one
    that wobbles between 0.69 and 0.71 across a threshold of 0.70 is not, and only
    agreement tells the two apart. The spread is reported alongside for whoever
    wants the other view.

    **Only `pass` and `fail` can be the majority.** An errored sample is in the
    denominator and never in the numerator: it counts against agreement, never
    for it. Counted like the other two, four samples that could not judge would
    "agree" and let the fifth decide the check alone — which is what happened
    until ADR 0006 §12, and which no decision had ever chosen. With no errored
    sample the two definitions are the same number.

    Only the size of the majority matters, not which side it is, so a tie needs
    no breaking.
    """
    judged = Counter(status for status in statuses if status != "error")
    return max(judged.values(), default=0) / len(statuses)


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


def _all_errored(verdicts: Sequence[Verdict]) -> str:
    """The summary sentence, carrying the cause the samples themselves gave.

    "No sample could be judged over 3 attempts" is true and worth saying — it is
    the fact that decides the status — but on its own it *replaced* what each
    sample had reported, and what each sample had reported was the whole
    diagnosis: since 0.8.0 a mute judge says which ending the provider declared
    and what to do about it, and a `Repeated` check was the one place that
    sentence never reached the run file.

    **Grouped on the sentence, not on a cause code**, because the samples give
    sentences and a cause code would be a second vocabulary to keep in step. Two
    samples truncated at the same cap produce the same string and count as one
    reason; two truncated at different token counts do not, and saying so twice
    is more honest than a grouping that pretends to know they are the same.

    **The distribution, not the dominant one.** With a handful of samples the
    whole of it fits in a sentence, and "2 of 3 hit the cap, 1 of 3 was filtered"
    is the shape an operator acts on: the one it hides — a cause that appeared
    once — is exactly the one worth seeing, because the run is not flaky in one
    way, it is failing in two. Most common first, and ties keep the order the
    samples came in, so the sentence is deterministic for a given run.
    """
    attempts = len(verdicts)
    summary = f"no sample could be judged over {attempts} attempts"
    causes = Counter(v.reason.strip() for v in verdicts if v.reason.strip())
    if not causes:
        return summary
    if len(causes) == 1:
        return f"{summary}: {next(iter(causes))}"
    spread = "; ".join(
        f"{count} of {attempts}: {cause}" for cause, count in causes.most_common()
    )
    return f"{summary}, for {len(causes)} different reasons — {spread}"


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
      noisy to trust cannot be promoted to a baseline. An errored sample counts
      against agreement, never for it (ADR 0006 §12), so samples that could not
      judge never outvote the ones that did;
    - with **no** sample judged at all the outcome is `error` too, and the
      reason carries the samples' own cause under the summary — see
      `_all_errored`. Folding must not cost the reader the diagnosis it folded.

    Metadata carries `samples`, `agreement`, `spread`, `errored_samples` and the
    raw `scores`. All numbers, so all of it crosses a boundary: the software
    house sees how unstable a check is without seeing what it judged. What the
    samples themselves measured is folded in alongside — see
    `_folded_metadata` — so sampling does not cost the reader the raw values.

    The raw scores and the interval they span are also written **on the
    `Score`**, where `compare()` reads them as the noise floor of ADR 0006 §5.
    The same numbers as `metadata["scores"]`, deliberately: the metadata half is
    reported and the fields are acted on, and a rule that acted on a
    stringly-keyed bag is a rule one typo disables silently.

    The scalar is unchanged by all of this. ADR 0006 §2 kept the mean where it
    was — the defect was never that the centre sat in the wrong place, it was
    that one number cannot say how far it moves — so every baseline recorded
    before that ADR records the number this function still computes.
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
        return failed(_all_errored(verdicts))
    # Rounded on both sides, like every other limit (ADR 0009 §1 and §7). The
    # reachability guard in `as_agreement` already judged this value at storage
    # precision, and comparing raw quotients here made the two disagree: with
    # three samples `min_agreement=0.666667` was accepted as reachable and then
    # rejected two-of-three as "did not agree: 0.67 ... below the required
    # 0.67". The guard and the gate are one comparison now.
    if not meets(agreement, min_agreement):
        # Said only when it applies, so a vote with no errored sample keeps the
        # sentence it always had. Where it applies it is the sentence a reader
        # needs: four errors in the scores and "0.20 agree" read as a bug
        # unless something says which side an error counts on.
        errored = len(verdicts) - len(scores)
        against = (
            f"; {errored} of {len(verdicts)} could not be judged, and an errored "
            "sample counts against agreement, never for it"
            if errored
            else ""
        )
        return failed(
            f"the samples did not agree: {agreement:.2f} of them share the "
            f"majority verdict, below the required {min_agreement:.2f} "
            f"(scores: {_rendered(verdicts)}){against}"
        )

    # Rounded *before* the status is decided, because `Verdict` rounds the
    # score and then checks the status against it. Deciding from the unrounded
    # mean lets the two disagree at the boundary: three samples of exactly 0.7
    # average to 0.6999999999999998, which is `fail` before rounding and `pass`
    # after — and the Verdict refuses to exist, so a check that passes on its
    # own becomes an `error` the moment it is wrapped. (friction 31)
    mean = at_precision(fmean(scores))
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
        score=Score(
            name=first.score.name,
            score=mean,
            metadata=metadata,
            # The samples that *were judged*, in the order they were produced.
            # An errored sample contributes nothing to an interval it has no
            # value in; `errored_samples` above is where its absence is counted.
            samples=tuple(scores),
            sample_min=min(scores),
            sample_max=max(scores),
        ),
        threshold=first.threshold,
        tolerance=first.tolerance,
        status="pass" if meets(mean, first.threshold) else "fail",
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
                # Re-stamped, not recomputed: this is the same fold under this
                # assertion's name, and an interval dropped here would be a
                # `Repeated` check that silently has no noise floor.
                samples=combined.score.samples,
                sample_min=combined.score.sample_min,
                sample_max=combined.score.sample_max,
            ),
            threshold=combined.threshold,
            tolerance=combined.tolerance,
            status=combined.status,
            reason=combined.reason,
            assertion_id=self.identity,
        )
