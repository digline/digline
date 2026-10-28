"""digline's refusals, translated so they survive the boundary.

The SDK is bimodal about this and the difference is total. A `ToolError`
reaches the caller with its message, as a `CallToolResult` carrying the text and
`is_error`. **Anything else is wrapped and its message is discarded** — a custom
exception arrives as the bare string "Error executing tool <name>".

So every carefully written refusal in digline — the perimeter messages, the
three promotion conditions, "no runs stored for suite … run it first" — would
reach an agent as five identical words unless it is translated here. That is the
whole reason this module exists. The list is digline's classification of its
own refusals, and digline's `tests/test_refusals.py` fails on any exception
class it defines that is not classified — which is what makes a new refusal
added without a translation impossible to ship. Parametrizing a test over the
list, as `tests/test_errors.py` does, proves the listed types are translated,
and could never have caught one that was not listed.

Nothing else is caught. An unexpected exception should stay an unexpected
exception: dressing one as a tool result hides a bug behind a sentence.
(ADR 0011 §10)

*Changed with #507.* Everything else is now caught, and said as what it is:
a failure nobody anticipated, never a refusal. The SDK's own text for it,
"Error executing tool <name>", was the same for a failure of digline and a
bug in this server, so a client could not tell whose it was. The sentence
names whose code raised it, read from the innermost frame, its type and its
`file:line`, and sends the reader to this server's log, where the traceback
is written. **Never its message**, even when the frame is digline's: a
`KeyError` in our own code has a datum for a message. That is narrower than
ADR 0043 §3, which lets digline's own message cross, and §3 is amended to
say so. (ADR 0011 §10 and ADR 0043 §3, amended 2026-10-23)

**And a message that travels is a rendered document.** Every refusal leaving
here goes through `json_visible`, because a refusal's text is not all digline's
own words: it quotes tenants, suite names, provider ids and — since 0.18.0 —
the names of the rules that moved, each of which arrives in a stored run
document somebody else may have written. `digline.wire` neutralises the
documents it renders; an exception message is not one of them and reached the
client raw. (the release delta-pass over 0.18.0)

**And a refusal is classified twice: by type, then by frame.** Being in
`REFUSALS` says a refusal is deliberate, not that digline wrote what it says.
A suite can raise `RefusedError` with a case in its message, and digline wraps
other code's exceptions in refusals of its own. So the message of an exception
digline did not write never reaches the agent: it gets the type, the location
and the command that prints the traceback, rendered by `digline.wire`. Until
this, it did (#445, GHSA-x6w8-q92m-23h3). (ADR 0043 §1, §3)

**And an `OSError` is translated beside them.** It is not in `REFUSALS`, and it
is not a bug either: a file that cannot be read is the environment, which is
why the command line refuses it in words (ADR 0041 §4, (B)). Untranslated, it
reached an agent as "Error executing tool" while the command line said what
was wrong. It is rendered by the same rule: its message crosses when digline
asked and the system wrote the words, and otherwise the agent gets the type and
the location. (#451, ADR 0043 §1, amended)
"""

from __future__ import annotations

import logging
import sysconfig
import traceback
from collections.abc import Callable
from functools import wraps
from pathlib import Path
from typing import NoReturn

from mcp.server.mcpserver.exceptions import ToolError

import digline
from digline.core import (
    Minter,
    ProjectionRefusedError,
    json_visible,
)
from digline.host import REFUSALS, refused_exit, to_withhold
from digline.wire import refusal_text

__all__ = ["TRANSLATED", "translated"]

#: The exceptions digline raises deliberately, each carrying a message written
#: for a reader. Anything not in here is a bug and travels as one.
#:
#: **digline's own classification, not a list kept here.** This was eleven names
#: written in this file, and it lagged twice: `PathRefusedError` and
#: `RunNotFoundError` were missing until the standing-code pass of 2026-09-23,
#: and arrived as "Error executing tool get_run" with the reason on stderr where
#: no client reads it. `digline.host.REFUSALS` is checked against every
#: exception class digline defines, so a refusal added there reaches an agent as
#: its sentence without this file changing. Types no tool here can raise — the
#: promotion's own refusals, since there is no `promote` — cost nothing to
#: translate and get in nobody's way. (friction 59)
TRANSLATED: tuple[type[Exception], ...] = REFUSALS

#: This server's own code. A refusal caught here has this directory's frames on
#: its traceback, above the code digline ran: the wrapper below, and the tool
#: that called into digline. Neither is where the user's code was reached from,
#: and "reached from …/digline_mcp/errors.py" is what an agent read before
#: #452. Named here and handed down, because nothing shipped with digline may
#: name a plugin. (ADR 0043 §2, amended with #452)
_HERE = Path(__file__).resolve().parent

#: digline's code, for whose failure an unexpected exception was. The same
#: directory `digline.host` reads for who wrote a message. (ADR 0043 §1)
_DIGLINE = Path(digline.__file__).resolve().parent

#: Where the traceback of a failure nobody anticipated is written: this
#: server's log, on its standard error, which the person who started the
#: server reads. The sentence an agent gets sends it there.
_LOG = logging.getLogger("digline_mcp")

#: Where a location is read from, for code that lives in a package: this
#: server's, digline's, and the installed libraries'. A path is said relative
#: to one of these, because where a package is installed is the reader's
#: machine and not the failure. Code in none of them, such as the user's,
#: keeps the path its frame was compiled under, as the refusals of ADR 0043
#: show it.
_PACKAGE_ROOTS = (
    _HERE.parent,
    _DIGLINE.parent,
    *{Path(sysconfig.get_paths()[key]).resolve() for key in ("purelib", "platlib")},
)


# PEP 695 syntax (Python 3.12+): `[**P, R]` declares the type parameters inline
# instead of the older module-level `ParamSpec`/`TypeVar` pair. `**P` is the
# parameter *list* of the wrapped function, so the decorator keeps each tool's
# real signature — which is what the SDK reads to build the input schema.
def translated[**P, R](
    fn: Callable[P, R], *, minter: Callable[[], Minter | None] | None = None
) -> Callable[P, R]:
    """Re-raise digline's own refusals as `ToolError`, rendered for the agent
    and neutralised.

    *Neutralised*, where this said *intact* — and the two differ only in the
    two ranges `json_visible` names, DEL and C1. *Rendered*: whole, except for
    the message of an exception digline did not write (ADR 0043 §3). With a
    `minter` that hands one, each name the refusal quotes is its token, as an
    answer under `project` names it (ADR 0054 §8).
    """

    @wraps(fn)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return fn(*args, **kwargs)
        except (*TRANSLATED, OSError) as exc:
            raise ToolError(json_visible(_for_the_agent(exc, minter))) from exc
        # This server's own refusals (`refuse`), already in the one shape that
        # reaches an agent: through as they are, and before the catch-all.
        except ToolError:
            raise
        # Code the tool ran asked to end the process. Uncaught, it passed
        # through the SDK's worker thread: the call never answered, the server
        # ended at the next request, and the agent read an EOF. The tool stops,
        # as asked, and the session goes on. (ADR 0041 §4.3)
        except SystemExit as exc:
            refused = refused_exit(exc, front_end=_HERE)
            if refused is None:
                raise
            raise ToolError(json_visible(_for_the_agent(refused, minter))) from exc
        # Anything else is a failure nobody anticipated (ADR 0041 §4 rule 2):
        # said as one, in this server's words, with the traceback in the log
        # and never the message in the answer. (#507)
        except Exception as exc:
            _LOG.exception("a tool failed, and nobody anticipated it")
            raise ToolError(json_visible(unanticipated(exc))) from exc

    return wrapper


def unanticipated(exc: BaseException) -> str:
    """Whose code raised `exc`, its type and its `file:line`, and where the
    traceback is. Never its message. (#507; ADR 0043 §3, amended)"""
    frames = traceback.extract_tb(exc.__traceback__)
    if not frames:
        return (
            f"something failed, and nobody anticipated it: {type(exc).__name__}, "
            "raised from no frame. It is not a verdict on the suite and not a "
            "refusal of the request: report it. Its message is not shown here; "
            "the traceback is in this server's log, on its standard error."
        )
    inner = frames[-1]
    at = Path(inner.filename).resolve()
    if at.is_relative_to(_HERE):
        whose = "digline-mcp, this server, failed"
    elif at.is_relative_to(_DIGLINE):
        whose = "digline failed"
    else:
        whose = "code this server ran failed"
    return (
        f"{whose}, and nobody anticipated it: {type(exc).__name__} at "
        f"{_where(at, inner.filename)}:{inner.lineno}. It is not a verdict on the "
        "suite and not a refusal of the request: report it. Its message is not "
        "shown here, because an exception's message can quote the data it was "
        "handling; the traceback is in this server's log, on its standard error."
    )


def _for_the_agent(
    refusal: BaseException, minter: Callable[[], Minter | None] | None = None
) -> str:
    mint = None if minter is None else minter()
    try:
        return refusal_text(refusal, to_withhold(refusal, front_end=_HERE), mint=mint)
    # The table answered a name with something that is not a token. Its own
    # refusal names nothing, so it is what the agent reads. (ADR 0054 §7)
    except ProjectionRefusedError as fault:
        return refusal_text(fault, None)


def refuse(message: str) -> NoReturn:
    """A refusal this server itself makes, in the one shape that reaches an
    agent.

    Neutralised like a translated one. These messages are this module's own
    sentences today, so it is belt beside braces — but the door is what is being
    closed, not the strings that happen to walk through it now, and the next
    caller to interpolate a suite name into one will not come back here to ask.
    """
    raise ToolError(json_visible(message))


def _where(at: Path, written: str) -> str:
    """`at` relative to the package root it lies under, or `written` as the
    frame had it when it lies under none."""
    for root in _PACKAGE_ROOTS:
        if at.is_relative_to(root):
            return at.relative_to(root).as_posix()
    return written
