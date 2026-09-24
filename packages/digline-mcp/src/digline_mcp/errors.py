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

**And a message that travels is a rendered document.** Every refusal leaving
here goes through `json_visible`, because a refusal's text is not all digline's
own words: it quotes tenants, suite names, provider ids and — since 0.18.0 —
the names of the rules that moved, each of which arrives in a stored run
document somebody else may have written. `digline.wire` neutralises the
documents it renders; an exception message is not one of them and reached the
client raw. (the release delta-pass over 0.18.0)
"""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import NoReturn

from mcp.server.mcpserver.exceptions import ToolError

from digline.core import (
    json_visible,
)
from digline.host import REFUSALS

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


# PEP 695 syntax (Python 3.12+): `[**P, R]` declares the type parameters inline
# instead of the older module-level `ParamSpec`/`TypeVar` pair. `**P` is the
# parameter *list* of the wrapped function, so the decorator keeps each tool's
# real signature — which is what the SDK reads to build the input schema.
def translated[**P, R](fn: Callable[P, R]) -> Callable[P, R]:
    """Re-raise digline's own refusals as `ToolError`, message neutralised.

    *Neutralised*, where this said *intact* — and the two differ only in the
    two ranges `json_visible` names, DEL and C1. Everything a reader is meant
    to read is untouched.
    """

    @wraps(fn)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return fn(*args, **kwargs)
        except TRANSLATED as exc:
            raise ToolError(json_visible(str(exc))) from exc

    return wrapper


def refuse(message: str) -> NoReturn:
    """A refusal this server itself makes, in the one shape that reaches an
    agent.

    Neutralised like a translated one. These messages are this module's own
    sentences today, so it is belt beside braces — but the door is what is being
    closed, not the strings that happen to walk through it now, and the next
    caller to interpolate a suite name into one will not come back here to ask.
    """
    raise ToolError(json_visible(message))
