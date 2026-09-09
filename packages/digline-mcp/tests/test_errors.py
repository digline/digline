"""Every refusal digline writes has to survive the boundary.

The SDK discards the message of anything that is not a `ToolError`: a custom
exception reaches the caller as the bare string "Error executing tool <name>".
So without the translation in `digline_mcp.errors`, every carefully written
refusal in this repository — the perimeter messages, the three promotion
conditions, "no runs stored for suite … run it first" — arrives as five
identical words. (ADR 0011 §10, §13)
"""

from __future__ import annotations

import pytest
from mcp.server.mcpserver.exceptions import ToolError, UnexpectedToolError

from digline.core import DifferentJudgesError, DifferentSuitesError
from digline.host import UsageError
from digline.store import ConfigMismatchError, ErroredRunError, TenantMismatchError
from digline.targets import ProviderNotFound
from digline_mcp.errors import TRANSLATED, translated

MESSAGE = "the sentence a reader was supposed to see"


@pytest.mark.parametrize("kind", TRANSLATED, ids=lambda k: k.__name__)
def test_a_deliberate_refusal_keeps_its_message(kind: type[Exception]) -> None:
    @translated
    def raises() -> None:
        raise kind(MESSAGE)

    with pytest.raises(ToolError) as caught:
        raises()
    assert MESSAGE in str(caught.value)


def test_the_list_covers_what_digline_raises_deliberately() -> None:
    """A guard on the guard. The parametrized test above proves the listed types
    are translated; this one proves the list is the right list, so a type added
    to digline and forgotten here fails rather than reaching an agent as five
    words."""
    assert set(TRANSLATED) == {
        UsageError,
        TenantMismatchError,
        ConfigMismatchError,
        ErroredRunError,
        DifferentSuitesError,
        DifferentJudgesError,
        ProviderNotFound,
    }


def test_an_unexpected_exception_stays_unexpected() -> None:
    """Nothing else is caught. Dressing a bug as a tool result hides it behind a
    sentence, and a caller cannot tell a refusal it should act on from a crash
    it should report."""

    @translated
    def raises() -> None:
        raise ZeroDivisionError("a bug, not a refusal")

    with pytest.raises(ZeroDivisionError):
        raises()


def test_the_wrapper_keeps_the_signature_the_schema_is_built_from() -> None:
    """The decorator sits between the function and `add_tool`, which reads the
    signature to build the input schema. A wrapper that flattened it to
    `(*args, **kwargs)` would produce a tool taking no named arguments — and it
    would do so silently."""
    import inspect

    @translated
    def tool(suite: str, run: str = "latest") -> None: ...

    assert list(inspect.signature(tool).parameters) == ["suite", "run"]


def test_an_unexpected_exception_reaches_the_caller_as_one() -> None:
    """The SDK's own half of the contract, pinned so a change in it is noticed
    here rather than in somebody's transcript."""
    import anyio
    from mcp.server.mcpserver import MCPServer

    server = MCPServer(name="probe", version="0")

    def boom() -> dict[str, str]:
        raise ZeroDivisionError(MESSAGE)

    server.add_tool(boom, name="boom", description="raises")

    async def go() -> None:
        with pytest.raises(UnexpectedToolError) as caught:
            await server.call_tool("boom", {})
        assert MESSAGE not in str(caught.value)

    anyio.run(go)
