"""Who wrote a message, read from the frame that raised it. (ADR 0043 §1)

The type of an exception says *on purpose*, and only that (ADR 0041 §4.2).
`RefusedError` is exported from `digline.core` and `UsageError` from
`digline.host`, so a suite can raise either one, with a message quoting a
case. The innermost frame says who raised it. So **a message is digline's when
the innermost frame of the exception that carries it is in digline's code**,
and that holds through every wrap. A refusal that quotes another exception
carries it as a `Quoted`, and the author of what it quotes is the author of
that exception, by its own frame.

Here in `host` because reading a frame's file is the filesystem, and the core
does no I/O. *Digline's code* is the directory of `digline.__file__`; whether
`digline_mcp` and `pytest_digline` belong in it is #452's question.
"""

from __future__ import annotations

import traceback
from pathlib import Path

import digline
from digline.core import Quoted

__all__ = [
    "frames_outside",
    "quoted_in",
    "raised_inside_digline",
    "to_withhold",
    "written_by_digline",
]

#: Where digline's own code lives. A frame under it is digline's; anything else,
#: a provider plugin included, is the suite's or something the suite called.
_DIGLINE = Path(digline.__file__).resolve().parent


def _is_digline(filename: str) -> bool:
    return Path(filename).resolve().is_relative_to(_DIGLINE)


def raised_inside_digline(exc: BaseException) -> bool:
    """Whether the innermost frame of `exc` is digline's. An exception that was
    never raised has no frame, and is nobody's."""
    frames = traceback.extract_tb(exc.__traceback__)
    return bool(frames) and _is_digline(frames[-1].filename)


def written_by_digline(exc: BaseException) -> bool:
    """Whether digline wrote everything this exception says, message included.

    Its own innermost frame has to be digline's. A refusal that quotes another
    exception is then digline's only as far as what it quotes is: the quoted
    exception's own frame decides, unless the site declared that the frame
    cannot, as a builtin's (§6)."""
    if not raised_inside_digline(exc):
        return False
    quoted = quoted_in(exc)
    return quoted is None or (not quoted.builtin and written_by_digline(quoted.cause))


def to_withhold(exc: BaseException) -> Quoted | None:
    """The refusal in fields, when part of what it says is not digline's to
    ship; `None` when all of it is. (ADR 0043 §3)

    A refusal raised outside digline's code with a plain sentence, such as a
    `preflight` raising `RefusedError`, has no wrap to split. It is rendered as
    a wrapped one is: its type and its location, and the message set apart."""
    if written_by_digline(exc):
        return None
    quoted = quoted_in(exc)
    if quoted is not None:
        return quoted
    return Quoted.of(
        exc, "code digline ran raised ", ".", locations=frames_outside(exc)
    )


def quoted_in(exc: BaseException) -> Quoted | None:
    """The `Quoted` a refusal was built from, or `None` for a sentence that is
    a plain string."""
    if len(exc.args) == 1 and isinstance(exc.args[0], Quoted):
        return exc.args[0]
    return None


def frames_outside(exc: BaseException) -> tuple[str, ...]:
    """`file:line` of the innermost frame that is not digline's, and of the
    outermost when it is another: where the raise was, and where the suite's
    code was entered. Nothing when every frame is digline's."""
    frames = [
        frame
        for frame in traceback.extract_tb(exc.__traceback__)
        if not _is_digline(frame.filename) and not frame.filename.startswith("<")
    ]
    if not frames:
        return ()
    inner, outer = frames[-1], frames[0]
    at = (f"{inner.filename}:{inner.lineno}",)
    if (outer.filename, outer.lineno) != (inner.filename, inner.lineno):
        at += (f"{outer.filename}:{outer.lineno}",)
    return at
