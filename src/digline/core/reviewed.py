"""The reviewed answer, as the document holds it: a check, a person's yes or
no, and whether the judge agreed. (ADR 0059 §1)

A reviewed answer is an answer the application gave and a person's yes or no
about it. Only the judged check it names runs on it, and the expected verdict
is the person's: for a yes the check passes, for a no it does not. A judge that
contradicts the person fails the case, in the gate. It is a failure of its own,
exit `1`, and not `scale_lost`: a calibration band sits strictly between 0 and
1, and a yes or a no asks for an extreme.

What lives here is the half that crosses into a run: which check, by identity
and by name, and the person's yes or no. The answer itself is payload, declared
in `digline.run.ReviewedAnswer`, and it is never written.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from digline.core.refused import NameRef, Written

if TYPE_CHECKING:
    # Only for the annotation: `run.py` imports `Reviewed` from here, so a
    # runtime import the other way would be a cycle.
    from digline.core.run import Run

__all__ = ["Against", "Contradiction", "Reviewed", "contradicted"]

#: How a judge contradicted a person: it passed an answer the person said no
#: to, or failed one the person said yes to. The two are counted apart, because
#: a judge too lenient and a judge too strict are two different faults.
type Against = Literal["passed_no", "failed_yes"]


@dataclass(frozen=True, slots=True)
class Reviewed:
    """Which judged check a reviewed answer is for, and what the person said.

    **`assertion_id` is what binds, `check` is what is said**, for the reason
    `CalibrationBand` gives: a verdict's `score.name` is the assertion's
    choice, and binding on it could match nothing and read as *the judge
    agreed*. (ADR 0024 §4.7, amended 2026-09-26)

    `good` is the person's yes, `True`, or no, `False`, and nothing else.
    """

    check: str
    assertion_id: str
    good: bool

    def __post_init__(self) -> None:
        if not self.check:
            raise ValueError(
                "a reviewed answer names no check: the person's yes or no is "
                "about one judged assertion"
            )
        if not self.assertion_id:
            raise ValueError(
                Written.said(
                    "the reviewed answer for ",
                    NameRef("calibration_check", self.check),
                    " carries no assertion_id: it binds to its verdict by "
                    "identity, and one with none binds to nothing",
                )
            )
        # `bool` and nothing that is merely truthy: a person said yes or no.
        if type(self.good) is not bool:  # pyright: ignore[reportUnnecessaryComparison]
            raise ValueError(
                Written.said(
                    "the reviewed answer for ",
                    NameRef("calibration_check", self.check),
                    f" carries good={self.good!r}: good is true or false, the "
                    "person's yes or no",
                )
            )


@dataclass(frozen=True, slots=True)
class Contradiction:
    """One reviewed answer the judge disagreed with the person about.

    `score` is the judge's, the folded mean the verdict was judged on, and
    `None` where the check reported none.
    """

    case_id: str
    check: str
    good: bool
    score: float | None

    @property
    def direction(self) -> Against:
        """`passed_no` where the person said no and the judge passed the
        answer; `failed_yes` where the person said yes and it did not."""
        return "failed_yes" if self.good else "passed_no"


def contradicted(run: Run) -> tuple[Contradiction, ...]:
    """Every reviewed answer in `run` whose verdict is not the person's.

    From the run alone, like `scale_lost`: it compares a verdict with what a
    person said rather than with a past, so a first run is stopped by it.

    **An errored verdict does not fire it.** That case is unjudged, which is
    already exit `2` and already said, and a judge that could not answer has
    neither agreed nor disagreed. A suspended case has no verdict and says
    nothing either.

    The verdict binds by `assertion_id`, and `Run` refuses a reviewed answer
    that binds none, so empty means *every judge agreed*, never *nothing was
    checked*.
    """
    found: list[Contradiction] = []
    for case in run.results:
        reviewed = case.reviewed
        if reviewed is None:
            continue
        for verdict in case.verdicts:
            if (
                verdict.assertion_id != reviewed.assertion_id
                or verdict.status == "error"
            ):
                continue
            if (verdict.status == "pass") == reviewed.good:
                continue
            found.append(
                Contradiction(
                    case_id=case.case_id,
                    check=reviewed.check,
                    good=reviewed.good,
                    score=verdict.score.score,
                )
            )
    return tuple(found)
