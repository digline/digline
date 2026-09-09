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
from tests._helpers import run_key

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
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    listed = await session.list_tools()
                    out: list[Any] = [sorted(t.name for t in listed.tools)]
                    for name, arguments in calls:
                        out.append(await session.call_tool(name, arguments))
                    return out

    return anyio.run(go)


def test_a_real_client_sees_six_tools_and_no_promote(promoted: Path) -> None:
    suite = str(promoted / "suite_qa.py")
    key = run_key(promoted)
    tools, compared, refused = served(
        promoted,
        [
            ("compare", {"suite": suite, "run": key}),
            ("run", {"suite": suite}),
        ],
    )

    assert tools == ["compare", "diff", "get_baseline", "get_run", "list_runs", "run"]
    assert "promote" not in tools

    assert isinstance(compared, CallToolResult)
    assert compared.is_error is False
    assert compared.structured_content is not None
    assert compared.structured_content["exit_code"] == 0
    assert compared.structured_content["output_version"] == 1

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
