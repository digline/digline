"""The MCP `run` tool carries the same count as `digline run --json`. (#654)

`test_tools.py`'s `test_run_matches_the_cli_field_for_field` holds the two key
sets equal; this holds the value, on a run where a case check and an aggregate
both errored.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import anyio
from mcp.types import CallToolResult
from tests._helpers import cli

from digline_mcp.server import build_server

ERRORED = """
from digline.core import Contains, Recall
from digline.run import Case, Response, Suite

suite = Suite(
    tenant="acme-bank",
    environment="staging",
    name="errored",
    assertions=[Contains(needle="Rome")],
    run_assertions=[Recall(over="contains", threshold="1/2", tolerance=0.0)],
    cases=[
        Case(id="a", label="negative"),
        Case(id="b", label="negative"),
        Case(id="flaky", label="positive"),
    ],
)


def target(case):
    if case.id == "flaky":
        raise TimeoutError("provider did not answer")
    return Response(output="Paris")
"""


def call(root: Path, tool: str, **arguments: Any) -> dict[str, Any]:
    async def go() -> dict[str, Any]:
        server = build_server(str(root), None, None, names="clear", table=None)
        result = await server.call_tool(tool, arguments)
        assert isinstance(result, CallToolResult)
        assert result.structured_content is not None
        return dict(result.structured_content)

    return anyio.run(go)


def test_the_run_tool_counts_what_the_cli_counts(repo: Path) -> None:
    (repo / "suite_errored.py").write_text(ERRORED, encoding="utf-8")
    through_the_tool = call(
        repo, "run", suite=str(repo / "suite_errored.py"), acknowledge_calls=3
    )
    done = cli(repo, "run", "--suite", "suite_errored.py", "--json")
    through_the_cli = json.loads(done.stdout)
    assert through_the_tool["errored_checks"] == 2, through_the_tool
    assert through_the_tool["errored_checks"] == through_the_cli["errored_checks"]
