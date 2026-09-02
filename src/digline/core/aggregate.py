"""Verdicts about the run, not about a case.

With ground truth the question that decides a release is not "did case 14 pass"
but "is precision still above 0.65" — a statement about the whole run. It is a
`Verdict` like any other, so it has a mandatory threshold and is therefore a
gate by construction, and `compare()` tells you whether it regressed. No new
mechanism.

It earns its place on measured grounds. Four runs of one unchanged prompt agreed
with the human mark on 14, 14, 15, 15 of 21 cases while individual cases moved
by three votes: the aggregate is stable exactly where the per-case is not. The
aggregate is the gate; the per-case is the diagnosis.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import ClassVar, Literal, Protocol

from digline.core.assertions import dataclass_identity
from digline.core.ratio import Ratio, as_ratio
from digline.core.types import Score, Verdict

__all__ = [
    "F1",
    "Accuracy",
    "CaseOutcome",
    "Label",
    "Matrix",
    "Precision",
    "Recall",
    "RunAssertion",
    "RunAssertionBase",
    "per_sample_outcomes",
    "with_noise_interval",
]

type Label = Literal["positive", "negative"]


@dataclass(frozen=True, slots=True)
class CaseOutcome:
    """One case as an aggregate sees it: what it was marked, and how it was
    judged.

    **With `samples > 1` the verdict here is the combined one**, not the
    individual samples: its status has already been through the mean and through
    `min_agreement`. That is the answer to "why is precision steady while the
    votes wobble" — the wobble was resolved one level down, and what reaches the
    matrix is a settled verdict per case.

    `verdict` is `None` when the case was suspended, so there is nothing to
    count and the case is excluded rather than guessed at.
    """

    case_id: str
    label: Label | None
    verdict: Verdict | None


@dataclass(frozen=True, slots=True)
class Matrix:
    """The confusion matrix, plus what did not make it in.

    The per-case check named by `over` answers "does this agree with the human
    mark", so a `pass` means agreement: a marked-positive case that passes was
    correctly kept, a marked-negative case that passes was correctly rejected.
    """

    true_positive: int = 0
    false_positive: int = 0
    true_negative: int = 0
    false_negative: int = 0
    suspended_excluded: int = 0
    errored_excluded: int = 0
    unlabelled_excluded: int = 0

    @property
    def considered(self) -> int:
        return (
            self.true_positive
            + self.false_positive
            + self.true_negative
            + self.false_negative
        )

    def as_metadata(self) -> dict[str, object]:
        """All integers, so all of it crosses a boundary: the software house
        sees the shape of the errors without seeing a single case."""
        return {
            "true_positive": self.true_positive,
            "false_positive": self.false_positive,
            "true_negative": self.true_negative,
            "false_negative": self.false_negative,
            "considered": self.considered,
            "suspended_excluded": self.suspended_excluded,
            "errored_excluded": self.errored_excluded,
            "unlabelled_excluded": self.unlabelled_excluded,
        }


def build_matrix(outcomes: Sequence[CaseOutcome]) -> Matrix:
    tp = fp = tn = fn = 0
    suspended = errored = unlabelled = 0
    for outcome in outcomes:
        if outcome.verdict is None:
            suspended += 1
        elif outcome.verdict.status == "error":
            errored += 1
        elif outcome.label is None:
            unlabelled += 1
        elif outcome.label == "positive":
            if outcome.verdict.passed:
                tp += 1
            else:
                fn += 1
        elif outcome.verdict.passed:
            tn += 1
        else:
            fp += 1
    return Matrix(tp, fp, tn, fn, suspended, errored, unlabelled)


class RunAssertion(Protocol):
    """A pure function from every case's outcome to one verdict about the run."""

    @property
    def name(self) -> str: ...

    @property
    def identity(self) -> str: ...

    @property
    def threshold(self) -> Ratio: ...

    @property
    def tolerance(self) -> Ratio: ...

    @property
    def over(self) -> str:
        """The **name** of the per-case assertion whose verdict is counted.

        A name rather than an identity because nobody writes
        `Precision(over="7338b721e2cc00b5")`. The cost of a name is that it can
        be absent or ambiguous, so `Suite` refuses both: it must match exactly
        one declared assertion.
        """
        ...

    @property
    def requires_label(self) -> bool:
        """Whether every case must carry a `label`. True for anything built on a
        confusion matrix; a future metric over raw scores would not need one."""
        ...

    def __call__(self, outcomes: Sequence[CaseOutcome]) -> Verdict: ...


class RunAssertionBase:
    """Shared construction, mirroring `AssertionBase` one level up."""

    __slots__ = ()

    name: str
    over: str
    #: `"1/21"` says "one case out of twenty-one" where `0.047619` says nothing.
    #: The denominator here is the number of cases counted, which the suite
    #: knows and the assertion does not, so the fraction is accepted for what it
    #: expresses rather than checked against a reachable set.
    threshold: Ratio
    tolerance: Ratio

    #: Same rule as for per-case assertions: threshold and tolerance are *how*
    #: a result is judged, not *what* is measured, so raising a bar leaves the
    #: verdicts paired and `compare()` reports the flip.
    IDENTITY_EXCLUDED: ClassVar[frozenset[str]] = frozenset({"threshold", "tolerance"})

    @property
    def requires_label(self) -> bool:
        """True for anything built on a confusion matrix. A property rather
        than a class attribute so it satisfies the protocol as declared: a
        subclass that measures raw scores overrides it."""
        return True

    @property
    def identity(self) -> str:
        return dataclass_identity(self, self.IDENTITY_EXCLUDED)

    def _normalize(self) -> None:
        """Called by every subclass: the stored value is always a float, so the
        fraction is a way of writing it and never a second representation to
        carry around."""
        object.__setattr__(
            self, "threshold", as_ratio(self.threshold, field="threshold")
        )
        object.__setattr__(
            self, "tolerance", as_ratio(self.tolerance, field="tolerance")
        )

    def _error(self, reason: str, matrix: Matrix) -> Verdict:
        return Verdict(
            score=Score(name=self.name, score=None, metadata=matrix.as_metadata()),
            threshold=float(self.threshold),
            tolerance=float(self.tolerance),
            status="error",
            reason=reason,
            assertion_id=self.identity,
        )

    def _graded(self, value: float, reason: str, matrix: Matrix) -> Verdict:
        return Verdict(
            score=Score(name=self.name, score=value, metadata=matrix.as_metadata()),
            threshold=float(self.threshold),
            tolerance=float(self.tolerance),
            status="pass" if value >= float(self.threshold) else "fail",
            reason=reason,
            assertion_id=self.identity,
        )

    def _excluded(self, matrix: Matrix) -> str:
        """The two exclusions, always rendered beside the number.

        `suspended_excluded` is the one figure in this product that can be
        improved by doing *less* work — setting aside a case that fails raises
        the ratio without anyone lying. It is never printed on its own.
        """
        # Worded without a noun so it reads at every count: "1 counted" rather
        # than "1 cases counted".
        return (
            f"{matrix.considered} counted, "
            f"{matrix.suspended_excluded} suspended, "
            f"{matrix.errored_excluded} could not be judged"
        )

    def _ratio(
        self, numerator: int, denominator: int, label: str, matrix: Matrix
    ) -> Verdict:
        if denominator == 0:
            return self._error(
                f"nothing to measure: {label} has an empty denominator "
                f"({self._excluded(matrix)})",
                matrix,
            )
        value = numerator / denominator
        return self._graded(
            value,
            f"{label} {value:.6f} = {numerator}/{denominator} "
            f"({self._excluded(matrix)})",
            matrix,
        )


@dataclass(frozen=True, slots=True)
class Precision(RunAssertionBase):
    """Of the cases the system kept, how many should have been kept.

    `TP / (TP + FP)`. Empty denominator — the system kept nothing — is `error`,
    not a perfect score.
    """

    over: str
    threshold: Ratio
    tolerance: Ratio
    name: str = "precision"

    def __post_init__(self) -> None:
        self._normalize()

    def __call__(self, outcomes: Sequence[CaseOutcome]) -> Verdict:
        m = build_matrix(outcomes)
        return self._ratio(
            m.true_positive, m.true_positive + m.false_positive, "precision", m
        )


@dataclass(frozen=True, slots=True)
class Recall(RunAssertionBase):
    """Of the cases that should have been kept, how many were.

    `TP / (TP + FN)`. Empty denominator — nothing was marked positive — is
    `error`: a recall over no positives is a number with no meaning.
    """

    over: str
    threshold: Ratio
    tolerance: Ratio
    name: str = "recall"

    def __post_init__(self) -> None:
        self._normalize()

    def __call__(self, outcomes: Sequence[CaseOutcome]) -> Verdict:
        m = build_matrix(outcomes)
        return self._ratio(
            m.true_positive, m.true_positive + m.false_negative, "recall", m
        )


@dataclass(frozen=True, slots=True)
class Accuracy(RunAssertionBase):
    """How often the system agreed with the mark: `(TP + TN) / considered`.

    This is the figure that measured 14, 14, 15, 15 out of 21 across four runs
    of an unchanged prompt — the observation that made aggregates the gate.
    """

    over: str
    threshold: Ratio
    tolerance: Ratio
    name: str = "accuracy"

    def __post_init__(self) -> None:
        self._normalize()

    def __call__(self, outcomes: Sequence[CaseOutcome]) -> Verdict:
        m = build_matrix(outcomes)
        return self._ratio(
            m.true_positive + m.true_negative, m.considered, "accuracy", m
        )


@dataclass(frozen=True, slots=True)
class F1(RunAssertionBase):
    """The harmonic mean of precision and recall: `2TP / (2TP + FP + FN)`.

    Written in that form rather than as `2PR / (P + R)` because the two are the
    same number and only this one has a single denominator to check: computing
    it from the two ratios means handling three empty denominators instead of
    one, and deciding what `F1` means when precision itself errored.

    Why it is worth having next to the other three: precision and recall trade
    against each other, so a change that moves both — a stricter prompt that
    keeps fewer items and gets more of them right — makes each of them tell half
    the story. `F1` is the one number that goes down when the trade was a bad
    one. It is a gate on the balance, not a replacement for either.

    Empty denominator means no true positives and no mistakes of either kind —
    nothing was kept and nothing should have been — which is `error`, not a
    perfect score, for the same reason as `Precision`.
    """

    over: str
    threshold: Ratio
    tolerance: Ratio
    name: str = "f1"

    def __post_init__(self) -> None:
        self._normalize()

    def __call__(self, outcomes: Sequence[CaseOutcome]) -> Verdict:
        m = build_matrix(outcomes)
        tp = m.true_positive
        return self._ratio(
            2 * tp, 2 * tp + m.false_positive + m.false_negative, "f1", m
        )


def _at(verdict: Verdict, index: int) -> Verdict:
    """The verdict one sample would have produced on its own.

    `score >= threshold` on a verdict that already carries both, which is why
    §7 costs nothing: no call to a target, no call to a judge, arithmetic over
    numbers the run already recorded.
    """
    score = verdict.score.samples[index]
    return Verdict(
        score=Score(name=verdict.score.name, score=score),
        threshold=verdict.threshold,
        tolerance=verdict.tolerance,
        status="pass" if score >= verdict.threshold else "fail",
        reason=f"sample {index + 1} scored {score:.6f}",
        assertion_id=verdict.assertion_id,
    )


def per_sample_outcomes(
    outcomes: Sequence[CaseOutcome],
) -> tuple[tuple[CaseOutcome, ...], ...]:
    """The same cases as each single sample saw them: one list per sample index.

    Empty — meaning *there is no interval to compute* — unless every case that
    was judged carries the same number of samples. Reading across lists of
    different lengths would align sample 2 of one case with sample 3 of another
    and call the result a measurement, and an aggregate is a statement about the
    whole run: it is either the same run N times or it is nothing.

    A case with no verdict was suspended, and a case whose verdict errored could
    not be judged at all — neither has samples and both pass straight through,
    to be excluded by `build_matrix` exactly as they are in the folded run.
    """
    counts = {
        len(outcome.verdict.score.samples)
        for outcome in outcomes
        if outcome.verdict is not None and outcome.verdict.status != "error"
    }
    if len(counts) != 1:
        return ()
    total = counts.pop()
    if total < 2:
        return ()
    return tuple(
        tuple(
            outcome
            if outcome.verdict is None or not outcome.verdict.score.sampled
            else CaseOutcome(
                case_id=outcome.case_id,
                label=outcome.label,
                verdict=_at(outcome.verdict, index),
            )
            for outcome in outcomes
        )
        for index in range(total)
    )


def with_noise_interval(
    assertion: RunAssertion, outcomes: Sequence[CaseOutcome]
) -> Verdict:
    """The aggregate's verdict, and how far it moves.

    An aggregate is computed once per run from the folded per-case verdicts, so
    it has no samples of its own and the per-case floor of ADR 0006 §5 would
    never reach it. But the event this ADR was written for *is* an aggregate:
    accuracy moved by one case in twenty-one and came back. So the assertion is
    evaluated once more per sample index, and the N results supply the interval.

    **The recorded score does not change.** It stays what it is today — computed
    from the folded per-case verdicts, which are the suite's answers. The
    per-sample values answer a different question, "what would a single run have
    said", and that question's only job here is to size the noise. Keeping the
    two apart is also what leaves every threshold measured against the current
    definition still valid. (ADR 0006 §7)
    """
    verdict = assertion(outcomes)
    if verdict.score.score is None:
        return verdict
    slices = per_sample_outcomes(outcomes)
    if not slices:
        return verdict
    # A sample index whose aggregate could not be computed at all — precision
    # over a sample where the system kept nothing — contributes no value, for
    # the same reason an errored sample contributes none to a per-case interval.
    scores = [
        sampled.score.score
        for sampled in (assertion(one) for one in slices)
        if sampled.score.score is not None
    ]
    if not scores:
        return verdict
    return replace(
        verdict,
        score=Score(
            name=verdict.score.name,
            score=verdict.score.score,
            metadata=verdict.score.metadata,
            samples=tuple(scores),
            sample_min=min(scores),
            sample_max=max(scores),
        ),
    )
