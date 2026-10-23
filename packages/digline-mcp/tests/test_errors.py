"""Every refusal digline writes has to survive the boundary.

The SDK discards the message of anything that is not a `ToolError`: a custom
exception reaches the caller as the bare string "Error executing tool <name>".
So without the translation in `digline_mcp.errors`, every carefully written
refusal in this repository — the perimeter messages, the three promotion
conditions, "no runs stored for suite … run it first" — arrives as five
identical words. (ADR 0011 §10, §13)
"""

from __future__ import annotations

from pathlib import Path

import pytest
from mcp.server.mcpserver.exceptions import ToolError, UnexpectedToolError

import digline
from digline.host import REFUSALS
from digline.wire import WITHHELD
from digline_mcp.errors import TRANSLATED, translated

MESSAGE = "the sentence a reader was supposed to see"

#: A file name inside digline's own directory. Nothing is written there: the
#: frame rule reads the name a frame was compiled under, and that is all this
#: has to give it. (ADR 0043 §1)
INSIDE_DIGLINE = str(Path(digline.__file__).resolve().parent / "_raised_by_a_test.py")


def raise_inside_digline(exc: Exception) -> None:
    """Raise `exc` from a frame the frame rule reads as digline's: a refusal
    digline wrote, as far as the translation can tell."""
    exec(compile("raise exc", INSIDE_DIGLINE, "exec"), {"exc": exc})  # noqa: S102


@pytest.mark.parametrize("kind", TRANSLATED, ids=lambda k: k.__name__)
def test_a_deliberate_refusal_keeps_its_message(kind: type[Exception]) -> None:
    @translated
    def raises() -> None:
        raise_inside_digline(kind(MESSAGE))

    with pytest.raises(ToolError) as caught:
        raises()
    assert MESSAGE in str(caught.value)


@pytest.mark.parametrize("kind", TRANSLATED, ids=lambda k: k.__name__)
def test_a_refusal_raised_outside_digline_keeps_its_type_and_not_its_message(
    kind: type[Exception],
) -> None:
    """The other half, and #445's: being in `REFUSALS` says *on purpose*, not
    *written by digline*. A suite or a `preflight` can raise any of these with
    a case in its message, so the frame decides, and here it is this file's.
    (ADR 0043 §1, §3)"""

    @translated
    def raises() -> None:
        raise kind(MESSAGE)

    with pytest.raises(ToolError) as caught:
        raises()
    said = str(caught.value)
    assert MESSAGE not in said
    assert f"raised {kind.__name__} at {Path(__file__).resolve()}:" in said, said
    assert WITHHELD in said, said


def test_the_list_is_the_classification() -> None:
    """A guard on the guard. The parametrized test above proves the listed types
    are translated; this one proves the list is digline's own classification of
    its refusals — which `tests/test_refusals.py` holds complete — and not a copy
    kept here, which lagged twice before it stopped being one."""
    assert TRANSLATED is REFUSALS


#: What an unexpected exception carries as its message here: a key, which is
#: what a `KeyError` in digline's own code quotes, and which is the data it was
#: handling. It must never reach the agent. (#507)
DATA = "case-id-from-the-customers-data"

#: A file name inside this server's own directory, for the same trick as
#: `INSIDE_DIGLINE`: the frame rule reads the name, and nothing is written.
INSIDE_THE_SERVER = str(
    Path(translated.__code__.co_filename).resolve().parent / "_raised_by_a_test.py"
)
ELSEWHERE = str(Path(__file__).resolve().parent / "_raised_by_a_test.py")


@pytest.mark.parametrize(
    ("filename", "whose", "where"),
    [
        (INSIDE_DIGLINE, "digline failed", "digline/_raised_by_a_test.py"),
        (
            INSIDE_THE_SERVER,
            "digline-mcp, this server, failed",
            "digline_mcp/_raised_by_a_test.py",
        ),
        (ELSEWHERE, "code this server ran failed", ELSEWHERE),
    ],
    ids=["digline", "the server", "other code"],
)
def test_an_unexpected_exception_says_whose_it_was_and_never_its_message(
    filename: str, whose: str, where: str
) -> None:
    """A failure nobody anticipated is said in this server's own words: whose
    code raised it, read from the innermost frame, its type and its
    `file:line`, and where the traceback is. Never its message, even when the
    frame is digline's: a `KeyError` in our code has a datum for a message.
    Before #507 all three arrived as the SDK's bare *Error executing tool*.
    (ADR 0011 §10, ADR 0043 §3, both amended)"""

    @translated
    def raises() -> None:
        exec(compile("raise KeyError(data)", filename, "exec"), {"data": DATA})  # noqa: S102

    with pytest.raises(ToolError) as caught:
        raises()
    said = str(caught.value)
    assert type(caught.value) is ToolError
    assert said.startswith(f"{whose}, and nobody anticipated it: KeyError at "), said
    # Relative to the package for digline's code and the server's: where it is
    # installed is the reader's machine, not the failure. Code in no package,
    # such as the user's, keeps the path its frame was compiled under, as the
    # refusals of ADR 0043 show it.
    assert f"KeyError at {where}:1. " in said, said
    assert "the traceback is in this server's log" in said, said
    assert DATA not in said, said


def test_the_traceback_with_its_message_goes_to_the_servers_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The sentence sends the reader to the log, so the log has to have it: the
    person who started the server reads the message there, and nobody else.
    (ADR 0043, decision 9)"""

    @translated
    def raises() -> None:
        raise ZeroDivisionError(DATA)

    with caplog.at_level("ERROR"), pytest.raises(ToolError):
        raises()
    (record,) = [r for r in caplog.records if r.exc_info]
    assert record.exc_info is not None
    assert record.exc_info[0] is ZeroDivisionError
    assert DATA in caplog.text


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
        raise_inside_digline(kind(f"refused: {HOSTILE}"))

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
