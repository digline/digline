"""The refusal digline writes in words, as a type of its own."""

from __future__ import annotations

__all__ = ["RefusedError"]


class RefusedError(ValueError):
    """Raised on purpose, with a sentence written for whoever made the request:
    a check declared so that it could never fail, a suite that names a check it
    does not have, an endpoint that did not answer at preflight.

    A `ValueError` before it was a class of its own, and still one, so a caller
    that catches `ValueError` catches it. **The type is what says *on purpose*.**
    A deliberate refusal and a bug both start inside digline, so the frame
    cannot tell them apart. A bare `ValueError` that reaches a front end is a
    failure nobody anticipated, and exits 70. (ADR 0041 §4.2)

    Not every deliberate `ValueError` is one. A site raises this when its error
    reaches a front end along the user's road. It stays bare when the same
    `raise` also guards digline's own computation (`Score`, `Verdict`, the `Run`
    family), and when it is raised inside a run-time catch. There the type name
    is written into a committed verdict's reason, and an internal class name has
    no place in it.
    """
