"""A run directory git would commit is said in the server's log. (#523)

The person who started the server is the one who commits the repository, and
reads its standard error. The answer an agent reads does not carry it: whether
a directory is committed is the operator's business, not a fact about the run.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import anyio
import pytest
from mcp.types import CallToolResult

from digline_mcp.server import build_server


def call(root: Path, tool: str, **arguments: Any) -> CallToolResult:
    async def go() -> CallToolResult:
        result = await build_server(str(root), None, None).call_tool(tool, arguments)
        assert isinstance(result, CallToolResult)
        return result

    return anyio.run(go)


def test_the_run_tool_says_it_in_the_log_and_not_in_the_answer(
    repo: Path, caplog: pytest.LogCaptureFixture
) -> None:
    (repo / ".digline").mkdir(exist_ok=True)
    (repo / ".digline" / ".gitignore").write_text("my-own-entry\n", encoding="utf-8")
    with caplog.at_level("WARNING", logger="digline_mcp"):
        result = call(repo, "run", suite=str(repo / "suite_qa.py"), acknowledge_calls=2)
    assert not result.is_error
    assert "git does not ignore .digline/acme-bank/runs/" in caplog.text
    assert "git does not ignore .digline/acme-bank/name-table/" in caplog.text
    answered = str(result.structured_content) + "".join(
        getattr(block, "text", "") for block in result.content
    )
    assert "git does not ignore" not in answered


def test_the_generated_rules_leave_the_log_quiet(
    repo: Path, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level("WARNING", logger="digline_mcp"):
        call(repo, "run", suite=str(repo / "suite_qa.py"), acknowledge_calls=2)
    assert "git does not ignore" not in caplog.text
