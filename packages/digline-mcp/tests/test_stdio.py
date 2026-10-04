"""The server as a client actually meets it: a subprocess, over stdio.

Every other test in this package calls the tools in-process, which is the right
way to test what they answer and the wrong way to learn whether the thing runs
at all. This one launches `python -m digline_mcp`, speaks the protocol to it,
and asserts the contract end to end — the tool list, a response, and a refusal
whose message survives the wire.

It is also the transport check. stdio and not SSE or streamable-HTTP: the client
launches the process, so there is no bound port and no listening socket. Fixed
decision 5 is about network calls the user did not configure, and a server that
listened by default would be that mistake facing outward. (ADR 0011 §8, §13)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import anyio
from mcp import ClientSession, StdioServerParameters, stdio_client
from mcp.types import CallToolResult, TextContent
from tests._helpers import run_key, suite_source

from digline.wire import OUTPUT_VERSION

ROOT = Path(__file__).resolve().parents[3]
TIMEOUT = 60


def served(root: Path, calls: list[tuple[str, dict[str, Any]]]) -> list[Any]:
    """Launch the server, run `calls` against it, return the tool list and the
    results."""

    async def go() -> list[Any]:
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "digline_mcp", "--root", str(root)],
            env={
                **os.environ,
                "PYTHONPATH": os.pathsep.join(
                    [
                        str(ROOT / "src"),
                        str(ROOT / "packages" / "digline-mcp" / "src"),
                    ]
                ),
            },
        )
        with anyio.fail_after(TIMEOUT):
            async with (
                stdio_client(params) as (read, write),
                ClientSession(read, write) as session,
            ):
                await session.initialize()
                listed = await session.list_tools()
                out: list[Any] = [sorted(t.name for t in listed.tools)]
                for name, arguments in calls:
                    out.append(await session.call_tool(name, arguments))
                return out

    return anyio.run(go)


def test_a_real_client_sees_eight_tools_and_no_promote(promoted: Path) -> None:
    suite = str(promoted / "suite_qa.py")
    key = run_key(promoted)
    tools, compared, refused = served(
        promoted,
        [
            ("compare", {"suite": suite, "run": key}),
            ("run", {"suite": suite}),
        ],
    )

    assert tools == [
        "compare",
        "diff",
        "explain",
        "get_baseline",
        "get_run",
        "list_runs",
        "log",
        "run",
    ]
    assert "promote" not in tools

    assert isinstance(compared, CallToolResult)
    assert compared.is_error is False
    assert compared.structured_content is not None
    assert compared.structured_content["exit_code"] == 0
    assert compared.structured_content["output_version"] == OUTPUT_VERSION

    # The refusal reaches the client as a tool error carrying digline's own
    # words. Without the ToolError translation this would read "Error executing
    # tool run" and the agent would have no number to acknowledge.
    assert isinstance(refused, CallToolResult)
    assert refused.is_error is True
    # Narrowed on the type rather than probed with `getattr`: a content block
    # may be an image, a resource link or an embedded resource, and none of
    # those is a refusal. If a refusal ever stops being text, this fails.
    text = "".join(
        block.text for block in refused.content if isinstance(block, TextContent)
    )
    assert "2 calls to the target" in text
    assert "acknowledge_calls=2" in text


EXITING_TARGET = """

_answering = target


def target(case):
    if case.id == "capital-fr":
        import sys

        sys.exit(0)
    return _answering(case)
"""


def text_of(result: Any) -> str:
    assert isinstance(result, CallToolResult)
    return "".join(
        block.text for block in result.content if isinstance(block, TextContent)
    )


def test_code_that_exits_ends_the_call_and_not_the_session(promoted: Path) -> None:
    """Measured for ADR 0041 §4.3 with a client like this one, in another
    process: a suite's `sys.exit` passed through the SDK's worker thread, the
    call never answered, the server ended at the next request, and the agent
    read an EOF. A test that calls the server in its own process cannot see
    that, because there is no server process for the exit to end.

    Before the repair this test does not fail on an assertion: it times out."""
    (promoted / "exits_loading.py").write_text(
        suite_source(preamble="import sys\nsys.exit(0)"), encoding="utf-8"
    )
    (promoted / "exits_running.py").write_text(
        suite_source() + EXITING_TARGET, encoding="utf-8"
    )
    key = run_key(promoted)

    _, loading, running, after = served(
        promoted,
        [
            ("compare", {"suite": str(promoted / "exits_loading.py"), "run": key}),
            (
                "run",
                {
                    "suite": str(promoted / "exits_running.py"),
                    "acknowledge_calls": 2,
                },
            ),
            ("compare", {"suite": str(promoted / "suite_qa.py"), "run": key}),
        ],
    )

    assert isinstance(loading, CallToolResult)
    assert loading.is_error is True
    assert "raised SystemExit(0) at " in text_of(loading)
    assert "while it was being loaded" in text_of(loading)

    assert isinstance(running, CallToolResult)
    assert running.is_error is True
    assert "code digline ran raised SystemExit(0) at " in text_of(running)

    # The session goes on: the next call is answered, by the same server.
    assert isinstance(after, CallToolResult)
    assert after.is_error is False
    assert after.structured_content is not None
    assert after.structured_content["exit_code"] == 0
