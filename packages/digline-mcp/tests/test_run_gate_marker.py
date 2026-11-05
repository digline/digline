"""A run from this surface keeps the gate's marker too, under the server's
root, so an application that records itself marks the run's calls as the
gate's here as it does under `digline run`. (ADR 0058 §4, as amended
2026-11-05)"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import anyio
from mcp.types import CallToolResult

from digline_mcp.server import build_server

SUITE = """\
from pathlib import Path

from digline.core import Contains
from digline.host.gate import gate_markers
from digline.run import Case, Response, Suite

HERE = Path(__file__).parent

suite = Suite(
    tenant="acme-bank", environment="staging", name="marked",
    assertions=[Contains(needle="fine")], cases=[Case(id="one")],
)


def target(case):
    (HERE / "seen.txt").write_text(str(gate_markers(HERE, "acme-bank").run_id))
    return Response(output="fine", latency_ms=1.0)
"""


def call(root: Path, tool: str, **arguments: Any) -> dict[str, Any]:
    async def go() -> dict[str, Any]:
        server = build_server(str(root), None, None, names="clear", table=None)
        result = await server.call_tool(tool, arguments)
        assert isinstance(result, CallToolResult)
        assert result.structured_content is not None
        return dict(result.structured_content)

    return anyio.run(go)


def test_a_run_through_the_server_is_marked_while_it_calls(repo: Path) -> None:
    (repo / "suite_marked.py").write_text(SUITE, encoding="utf-8")
    written = call(
        repo, "run", suite=str(repo / "suite_marked.py"), acknowledge_calls=1
    )
    assert (repo / "seen.txt").read_text(encoding="utf-8") == written["key"]
    assert not (repo / ".digline" / "acme-bank" / "runs" / ".gate").exists()
