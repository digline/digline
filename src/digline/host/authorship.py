"""Who wrote a message, read from the frame that raised it. (ADR 0043 §1)

The type of an exception says *on purpose*, and only that (ADR 0041 §4.2).
`RefusedError` is exported from `digline.core` and `UsageError` from
`digline.host`, so a suite can raise either one, with a message quoting a
case. The innermost frame says who raised it. So **a message is digline's when
the innermost frame of the exception that carries it is in digline's code**,
and that holds through every wrap. A refusal that quotes another exception
carries it as a `Quoted`, and the author of what it quotes is the author of
that exception, by its own frame.

**An `OSError` is read the same way, from one frame further out.** Its message
is composed below Python from an `errno` and the file names its caller passed,
so the standard library between the caller and the system writes none of it.
Read from the innermost frame, digline's own read through `pathlib` and the
suite's read through `pathlib` have the same frame, and digline's `os.replace`
has its own. So for an `OSError` the frame that counts is the innermost one
outside the standard library: whoever asked. **The type chooses which frame is
read, and the frame still says who wrote the message.** And it is digline's
only when it is exactly the sentence the system writes from the exception's
attributes, as `ImportError`'s is (§5): a message in free text, or one a peer
on the network wrote, is somebody else's whoever asked. (ADR 0043 §1, amended
with #451)

Here in `host` because reading a frame's file is the filesystem, and the core
does no I/O. *Digline's code* is the directory of `digline.__file__`, for who
wrote a message. **A location leaves out the front end's frames as well**: a
front end that catches a refusal is on the traceback above the code digline
ran, and "reached from" it named the server's wrapper instead of the user's
code. The front end names its own directory, because nothing shipped with
digline names a plugin. (ADR 0043 §2, amended with #452)
"""

from __future__ import annotations

import os
import sysconfig
import traceback
from collections.abc import Iterator
from pathlib import Path
from types import FrameType
from typing import TypeGuard

import digline
from digline.core import Quoted
from digline.host.refusals import REFUSALS

__all__ = [
    "frames_outside",
    "quoted_in",
    "raised_inside_digline",
    "system_said",
    "to_withhold",
    "written_by_digline",
]

#: Where digline's own code lives. A frame under it is digline's; anything else,
#: a provider plugin included, is the suite's or something the suite called.
_DIGLINE = Path(digline.__file__).resolve().parent


#: Where the standard library lives, and where installed packages live, which
#: can be a directory inside it: on a Python uv installs, used without a
#: virtual environment (measured). Digline is installed there,
#: so without the second its own frames would be skipped as the first's.
_PATHS = sysconfig.get_paths()
_STDLIB = tuple({Path(_PATHS[key]).resolve() for key in ("stdlib", "platstdlib")})
_INSTALLED = tuple({Path(_PATHS[key]).resolve() for key in ("purelib", "platlib")})


def _is_digline(filename: str) -> bool:
    return Path(filename).resolve().is_relative_to(_DIGLINE)


def _in_stdlib(frame: FrameType) -> bool:
    """Whether a frame is the standard library's: a file where the standard
    library is and installed packages are not, or a module frozen into the
    interpreter (`os` is, since 3.11). By the file and not by the module's
    name, because a suite's helper can take a standard module's name: a
    `colorsys.py` beside the suite is the suite's."""
    filename = frame.f_code.co_filename
    if filename.startswith("<frozen "):
        return True
    where = Path(filename).resolve()
    return any(where.is_relative_to(p) for p in _STDLIB) and not any(
        where.is_relative_to(p) for p in _INSTALLED
    )


# `TypeGuard` and not `TypeIs`: `True` says *an `OSError`*, and `False` does not
# say *not one*, since `RunNotFoundError` is one.
def _the_system_s(exc: BaseException) -> TypeGuard[OSError]:
    """Whether `exc` is an `OSError` the system raised. `RunNotFoundError` is a
    `FileNotFoundError` so that a caller catching one catches it, and it is a
    refusal digline writes in words: read like every refusal, by its own
    frame."""
    return isinstance(exc, OSError) and not isinstance(exc, REFUSALS)


def _counted(exc: BaseException) -> Iterator[tuple[FrameType, int]]:
    """The frames that say who raised `exc`, outermost first: every one, or for
    an `OSError` the system raised every one outside the standard library."""
    system = _the_system_s(exc)
    for frame, line in traceback.walk_tb(exc.__traceback__):
        if system and _in_stdlib(frame):
            continue
        yield frame, line


def raised_inside_digline(exc: BaseException) -> bool:
    """Whether the innermost frame of `exc` is digline's, or for an `OSError`
    the system raised the innermost frame outside the standard library. An
    exception that was never raised has no frame, and is nobody's."""
    frames = list(_counted(exc))
    return bool(frames) and _is_digline(frames[-1][0].f_code.co_filename)


def system_said(exc: OSError) -> str | None:
    """The sentence the system writes for `exc`, rebuilt from `errno`,
    `strerror` and the file names, when `str(exc)` is exactly that; `None`
    otherwise. `strerror` has to be the system's own for that `errno`, so
    `OSError(2, "…")` with words of its own is not."""
    if exc.errno is None or exc.strerror != os.strerror(exc.errno):
        return None
    said = f"[Errno {exc.errno}] {exc.strerror}"
    if exc.filename is not None:
        said += f": {exc.filename!r}"
        if exc.filename2 is not None:
            said += f" -> {exc.filename2!r}"
    return said if said == str(exc) else None


def written_by_digline(exc: BaseException) -> bool:
    """Whether digline wrote everything this exception says, message included.

    Its own innermost frame has to be digline's. A refusal that quotes another
    exception is then digline's only as far as what it quotes is: the quoted
    exception's own frame decides, unless the site declared that the frame
    cannot, as a builtin's (§6). An `OSError` is digline's when digline asked
    and the system wrote the words (the module's docstring)."""
    if not raised_inside_digline(exc):
        return False
    if _the_system_s(exc) and system_said(exc) is None:
        return False
    quoted = quoted_in(exc)
    return quoted is None or (not quoted.builtin and written_by_digline(quoted.cause))


def to_withhold(exc: BaseException, *, front_end: Path | None = None) -> Quoted | None:
    """The refusal in fields, when part of what it says is not digline's to
    ship; `None` when all of it is. (ADR 0043 §3)

    A refusal raised outside digline's code with a plain sentence, such as a
    `preflight` raising `RefusedError`, has no wrap to split. It is rendered as
    a wrapped one is: its type and its location, and the message set apart.
    `front_end` is the directory of the front end that caught it, whose frames
    are not a location (`frames_outside`)."""
    if written_by_digline(exc):
        return None
    quoted = quoted_in(exc)
    if quoted is not None:
        return quoted
    return Quoted.of(
        exc,
        "code digline ran raised ",
        ".",
        locations=frames_outside(exc, front_end=front_end),
    )


def quoted_in(exc: BaseException) -> Quoted | None:
    """The `Quoted` a refusal was built from, or `None` for a sentence that is
    a plain string."""
    if len(exc.args) == 1 and isinstance(exc.args[0], Quoted):
        return exc.args[0]
    return None


def frames_outside(
    exc: BaseException, *, front_end: Path | None = None
) -> tuple[str, ...]:
    """`file:line` of the innermost frame that is not digline's, and of the
    outermost when it is another: where the raise was, and where the suite's
    code was entered. Nothing when every frame is digline's. For an `OSError`
    the system raised, the standard library's frames are not counted, as they
    are not for who raised it: a location in `pathlib` says nothing about who
    asked.

    Nor are the frames under `front_end`, the directory of the front end that
    caught `exc`. Its wrapper and its tool are on the traceback above the code
    digline ran, so the outermost frame was the MCP server's
    `errors.py`, and without the wrapper it would have been the server's
    `run` tool: the whole directory goes, not one file. Who wrote the message
    is not read from this, and stays `_is_digline`'s: a front end that raised
    a refusal of its own would not have its message taken for digline's.
    (ADR 0043 §2, amended with #452)"""
    frames = [
        (filename, line)
        for frame, line in _counted(exc)
        if not _is_digline(filename := frame.f_code.co_filename)
        and not filename.startswith("<")
        and not (
            front_end is not None and Path(filename).resolve().is_relative_to(front_end)
        )
    ]
    if not frames:
        return ()
    inner, outer = frames[-1], frames[0]
    at = (f"{inner[0]}:{inner[1]}",)
    if outer != inner:
        at += (f"{outer[0]}:{outer[1]}",)
    return at
