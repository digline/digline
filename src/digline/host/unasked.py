"""A suite whose cases never call the target may declare none. (ADR 0059 §1)

A reviewed answer is judged on the answer the application gave, and a
calibration case on the answer its band was written for: the run never asks
the target for either (`digline.run.driver`). A suite made of them alone,
which is what `digline record import` writes into a suite declared for it, has
nothing to call. So its target may be left out, and the run, a replay and a
promotion treat it as they treat any suite.

A suite with one case the target answers needs one, and the refusal names
that case: it is why a target is needed now when it was not before.
"""

from __future__ import annotations

from digline.core import RefusedError
from digline.host.errors import UsageError
from digline.run import Case, Response, Suite

__all__ = ["NoTarget", "asking_case", "no_target"]


def asking_case(suite: Suite) -> Case | None:
    """The first case the run calls the target for, or `None` where it calls
    it for none: every case is a reviewed answer or a calibration case."""
    return next(
        (
            case
            for case in suite.cases
            if case.reviewed_answer is None and case.calibration is None
        ),
        None,
    )


class NoTarget:
    """The target of a suite that declares none, because it calls none. It is
    never called; called, it refuses, rather than answer for a target nobody
    wrote."""

    def __call__(self, case: Case) -> Response:
        raise RefusedError(
            f"case {case.id!r} asked for a target, and the suite declares none: "
            "a suite with no target holds reviewed answers and calibration "
            "cases alone, which the run never calls the target for"
        )


def no_target(suite: Suite, missing: str) -> NoTarget:
    """`NoTarget` for `suite`, or the refusal where one of its cases calls the
    target. `missing` is how the suite's form says what is absent, a table or
    an attribute, and it begins the sentence."""
    asking = asking_case(suite)
    if asking is not None:
        raise UsageError(
            f"{missing}, and every suite needs one that has a case the target "
            f"answers: case {asking.id!r} is neither a reviewed answer nor a "
            "calibration case, so the run calls the target for it. A suite "
            "whose cases are all reviewed answers or calibration cases needs "
            "none (ADR 0059 §1)"
        )
    return NoTarget()
