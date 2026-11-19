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

**Since schema 25 (ADR 0067 §1, §2, §4)** a reviewed answer may also be:

- **awaiting a verdict**: `good` is `None`. The judge judged it and the person
  has not yet, so it is in no gate: `contradicted` passes over it;
- **about the whole answer**: `check` is `None`, and every judged check of the
  suite ran on it, by identity in `judged`. `good` is the overall yes or no,
  and `failing` the identities of the checks the person expected to fail on a
  no; every other judged check is expected to pass;
- **revised**: `good` and `failing` are then the person's verdict after she
  read the disagreements, the one the gate holds, and `revised` says so;
- **held out**: `held_out` is the role the person chose for it when she chose
  it.
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

    `good` is the person's yes, `True`, or no, `False`, and nothing else; or
    `None`, an answer awaiting the person's verdict, which no gate reads
    (ADR 0067 §1 (a)). Where the person revised her verdict it is the revised
    one, the verdict the gate holds, and `revised` is `True` (ADR 0067 §2).

    **Two forms** (ADR 0067 §4). About one check: `check` and `assertion_id`
    name it, and `judged` and `failing` are empty. About the whole answer:
    `check` and `assertion_id` are `None`, `judged` holds the identity of
    every judged check that ran on it, and `failing`, a part of `judged`, the
    ones the person expected to fail. Only a no names any.
    """

    check: str | None
    assertion_id: str | None
    good: bool | None
    revised: bool = False
    held_out: bool = False
    judged: tuple[str, ...] = ()
    failing: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        whole = self.check is None
        if whole != (self.assertion_id is None):
            raise ValueError(
                "a reviewed answer names a check and its identity together, or "
                "neither, for an answer reviewed as a whole"
            )
        if self.check is not None and not self.check:
            raise ValueError(
                "a reviewed answer names no check: the person's yes or no is "
                "about one judged assertion, or about the whole answer"
            )
        if self.assertion_id is not None and not self.assertion_id:
            raise ValueError(
                Written.said(
                    "the reviewed answer for ",
                    NameRef("calibration_check", self.check or ""),
                    " carries no assertion_id: it binds to its verdict by "
                    "identity, and one with none binds to nothing",
                )
            )
        # `bool` and nothing that is merely truthy: a person said yes or no,
        # or has not said yet.
        if self.good is not None and type(self.good) is not bool:  # pyright: ignore[reportUnnecessaryComparison]
            raise ValueError(
                Written.said(
                    "the reviewed answer for ",
                    NameRef("calibration_check", self.check or ""),
                    f" carries good={self.good!r}: good is true or false, the "
                    "person's yes or no",
                )
            )
        object.__setattr__(self, "judged", tuple(self.judged))
        object.__setattr__(self, "failing", tuple(self.failing))
        if not whole and (self.judged or self.failing):
            raise ValueError(
                "a reviewed answer about one check carries no `judged` and no "
                "`failing`: those are the whole answer's"
            )
        if whole and not self.judged:
            raise ValueError(
                "a reviewed answer about the whole answer names no judged "
                "check: every judged check of the suite runs on it"
            )
        if not set(self.failing) <= set(self.judged):
            raise ValueError(
                "a reviewed answer expects a check to fail that did not run on "
                "it: `failing` is a part of `judged`"
            )
        if self.failing and self.good is not False:
            raise ValueError(
                "a reviewed answer names checks expected to fail beside a "
                "verdict that is not a no"
            )
        if whole and self.good is False and not self.failing:
            raise ValueError(
                "a no about the whole answer names no check expected to fail: "
                "a no that does not say which part was wrong expects nothing "
                "of any check"
            )
        if self.good is None and self.revised:
            raise ValueError(
                "a reviewed answer awaiting a verdict cannot have been revised"
            )

    @property
    def awaiting(self) -> bool:
        """No verdict from the person yet: in no gate. (ADR 0067 §1 (a))"""
        return self.good is None

    def expects_pass(self, assertion_id: str) -> bool | None:
        """Whether the person expected the check with this identity to pass,
        or `None` where she said nothing about it: awaiting, or a check the
        reviewed answer did not ask."""
        if self.good is None:
            return None
        if self.assertion_id is not None:
            return self.good if assertion_id == self.assertion_id else None
        if assertion_id not in self.judged:
            return None
        return assertion_id not in self.failing


@dataclass(frozen=True, slots=True)
class Contradiction:
    """One reviewed answer the judge disagreed with the person about.

    `score` is the judge's, the folded mean the verdict was judged on, and
    `None` where the check reported none.

    `on_the_steps` says who contradicted: the judge, through the check the
    answer was reviewed for, or a check on the steps beside it, which only an
    episode's answer is asked (ADR 0059 §1, amended 2026-11-05).
    `assertion_id` is that check's, so a reader finds its verdict.
    """

    case_id: str
    check: str
    good: bool
    score: float | None
    assertion_id: str = ""
    on_the_steps: bool = False

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

    **An episode's answer is asked its trajectory checks too** (ADR 0059 §1,
    amended 2026-11-05), and they are the case's other verdicts. On a yes
    each of them must pass, as the check must: a person who said yes to the
    turn said yes to the steps it took. On a no they say nothing, because a
    no does not say which part of the turn was wrong.
    """
    found: list[Contradiction] = []
    for case in run.results:
        reviewed = case.reviewed
        if reviewed is None or reviewed.good is None:
            # Awaiting the person's verdict: the judge's stands alone, and no
            # gate reads it. (ADR 0067 §1 (a))
            continue
        for verdict in case.verdicts:
            if verdict.status == "error":
                continue
            expected = reviewed.expects_pass(verdict.assertion_id)
            if expected is None:
                # A trajectory check beside the ones reviewed: only a yes
                # binds it, and only a red one contradicts it.
                if not reviewed.good or verdict.status == "pass":
                    continue
                check, good, on_the_steps = verdict.score.name, True, True
            elif (verdict.status == "pass") == expected:
                continue
            else:
                check = (
                    reviewed.check
                    if reviewed.check is not None
                    else verdict.score.name
                )
                good, on_the_steps = expected, False
            found.append(
                Contradiction(
                    case_id=case.case_id,
                    check=check,
                    good=good,
                    score=verdict.score.score,
                    assertion_id=verdict.assertion_id,
                    on_the_steps=on_the_steps,
                )
            )
    return tuple(found)
