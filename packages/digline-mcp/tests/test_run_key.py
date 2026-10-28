"""`compare(run="latest")` names the run it compared, and `explain` names both
documents it read (#448).

Before, an agent learned which baseline a comparison used and not which run:
quoting the run, or recommending it for promotion, took a second `get_run` that
could resolve `latest` to a run landed in between.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import anyio
from mcp.types import CallToolResult
from tests._helpers import baseline_in, run_key

from digline_mcp.server import build_server


def call(root: Path, tool: str, **arguments: Any) -> dict[str, Any]:
    async def go() -> dict[str, Any]:
        server = build_server(str(root), None, None, names="clear", table=None)
        result = await server.call_tool(tool, arguments)
        assert isinstance(result, CallToolResult)
        assert result.structured_content is not None
        return dict(result.structured_content)

    return anyio.run(go)


def test_compare_names_the_run_latest_picked(promoted: Path) -> None:
    """A newer run than the promoted one, so `run_key` cannot pass by being
    the reference's key."""
    newer = run_key(promoted)
    answered = call(promoted, "compare", suite=str(promoted / "suite_qa.py"))

    assert answered["run_key"] == newer
    assert answered["baseline_key"] == baseline_in(promoted) != newer


def test_explain_names_the_run_once_and_the_reference_once(promoted: Path) -> None:
    """`run_key` is the run, from inside the document. `key`, the splice it
    replaced, was kept until a bump, and `output_version` 4 is that bump. (#448,
    #678)

    `run_key` is qualified by its role because a second run stands beside it:
    with `reading: "comparison"`, `baseline_key`. A name is qualified by its role
    only where two things of the same kind can stand in one document."""
    newer = run_key(promoted)
    answered = call(promoted, "explain", suite=str(promoted / "suite_qa.py"))

    assert answered["reading"] == "comparison"
    assert answered["run_key"] == newer
    assert answered["baseline_key"] == baseline_in(promoted)
    assert "key" not in answered
