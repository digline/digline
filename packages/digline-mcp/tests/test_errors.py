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


# --------------------------------------------------------------------------- #
# The message is a rendered document, and this door is not `digline.wire`
# --------------------------------------------------------------------------- #

#: DEL and the C1 block, built from code points so this file stays readable and
#: greppable. C0 is deliberately absent: a JSON encoder escapes it and the SDK
#: serialises this message as JSON, which is the division of labour
#: `json_visible` documents and the reason it covers exactly these two ranges.
CSI = ""  # U+009B *is* CSI: it opens on a terminal what ESC [ opens
DEL = ""
HOSTILE = f"{CSI}2K{DEL}digline: everything matched"


@pytest.mark.parametrize("kind", TRANSLATED, ids=lambda k: k.__name__)
def test_a_refusal_carries_no_raw_control_byte_to_the_client(
    kind: type[Exception],
) -> None:
    """Parametrized over the whole surface rather than over the one message that
    was found to leak.

    0.18.0 added the names of the moved rules to `DifferentSuitesError`, and
    those arrive inside a stored run document somebody else may have written.
    But the defect was never that string: a refusal's text is interpolated from
    tenants, suite names, provider ids and now rule names, and **this door is
    not `digline.wire`** — so the neutralising every rendered document gets had
    never applied here. Pinning `DifferentSuitesError` alone would test the
    instance and leave the door open.
    """

    @translated
    def raises() -> None:
        raise kind(f"refused: {HOSTILE}")

    with pytest.raises(ToolError) as caught:
        raises()
    message = str(caught.value)
    assert CSI not in message, "U+009B is CSI and reached the client raw"
    assert DEL not in message, "DEL reached the client raw"
    # Shown, not stripped: the escape spelling is what a reader should see.
    assert "\\u009b" in message
    assert "refused:" in message, "the sentence a reader needs is still there"


def test_a_refusal_this_server_makes_is_neutralised_too() -> None:
    """`refuse()` is the other door out of this module.

    Its messages are this module's own sentences today, so this is belt beside
    braces — and it is the door being closed, not the strings that happen to
    walk through it now.
    """
    from digline_mcp.errors import refuse

    with pytest.raises(ToolError) as caught:
        refuse(f"no runs stored for suite {HOSTILE}")
    assert CSI not in str(caught.value)


def test_the_control_that_must_fail() -> None:
    """The hostile string really does carry what the assertions look for.

    Without it, every assertion above would pass just as well on a string that
    never had a control byte in it — the vacuously green assertion, one level
    up from the code it is checking.
    """
    assert CSI in HOSTILE
    assert DEL in HOSTILE
    assert len(CSI) == 1, "a single code point, not a six-character spelling"
