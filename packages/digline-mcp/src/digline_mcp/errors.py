"""digline's refusals, translated so they survive the boundary.

The SDK is bimodal about this and the difference is total. A `ToolError`
reaches the caller with its message, as a `CallToolResult` carrying the text and
`is_error`. **Anything else is wrapped and its message is discarded** — a custom
exception arrives as the bare string "Error executing tool <name>".

So every carefully written refusal in digline — the perimeter messages, the
three promotion conditions, "no runs stored for suite … run it first" — would
reach an agent as five identical words unless it is translated here. That is the
whole reason this module exists, and `tests/test_errors.py` is parametrized over
the list so a new exception type added to digline without a translation fails
here rather than in front of somebody.

Nothing else is caught. An unexpected exception should stay an unexpected
exception: dressing one as a tool result hides a bug behind a sentence.
(ADR 0011 §10)
"""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import NoReturn

from mcp.server.mcpserver.exceptions import ToolError

from digline.core import DifferentJudgesError, DifferentSuitesError
from digline.host import UsageError
from digline.store import ConfigMismatchError, ErroredRunError, TenantMismatchError
from digline.targets import ProviderNotFound

__all__ = ["TRANSLATED", "translated"]

#: The exceptions digline raises deliberately, each carrying a message written
#: for a reader. Anything not in here is a bug and travels as one.
TRANSLATED: tuple[type[Exception], ...] = (
    UsageError,
    TenantMismatchError,
    ConfigMismatchError,
    ErroredRunError,
    DifferentSuitesError,
    DifferentJudgesError,
    ProviderNotFound,
)


# PEP 695 syntax (Python 3.12+): `[**P, R]` declares the type parameters inline
# instead of the older module-level `ParamSpec`/`TypeVar` pair. `**P` is the
# parameter *list* of the wrapped function, so the decorator keeps each tool's
# real signature — which is what the SDK reads to build the input schema.
def translated[**P, R](fn: Callable[P, R]) -> Callable[P, R]:
    """Re-raise digline's own refusals as `ToolError`, message intact."""

    @wraps(fn)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return fn(*args, **kwargs)
        except TRANSLATED as exc:
            raise ToolError(str(exc)) from exc

    return wrapper


def refuse(message: str) -> NoReturn:
    """A refusal this server itself makes, in the one shape that reaches an
    agent."""
    raise ToolError(message)
