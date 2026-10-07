"""ADR 0045 through the MCP server: test plan entries 6 and 9.

The server runs in this process, so the working directory a target reads its
prompt against is this process's: each test sets it with `monkeypatch.chdir`,
never inheriting the runner's. The layout is #481's, from `tests/_one_path.py`.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import anyio
import pytest
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import CallToolResult
from tests._one_path import (
    RELATIVE,
    fake_anthropic,
    layout,
    recorded,
    sent,
    sha,
    toml_layout,
)

from digline_mcp.server import build_server


def _run(root: Path, suite: str) -> dict[str, Any]:
    async def go() -> dict[str, Any]:
        result = await build_server(str(root), None, None).call_tool(
            "run", {"suite": suite, "acknowledge_calls": 1}
        )
        assert isinstance(result, CallToolResult)
        assert result.structured_content is not None
        return dict(result.structured_content)

    return anyio.run(go)


def test_1_from_the_root_the_run_records_the_file_it_sent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = layout(tmp_path)
    monkeypatch.chdir(root)
    key = _run(root, "eval/suite.py")["key"]
    assert sent(tmp_path) == ["text of R\n"]
    assert recorded(root, key) == {
        "prompt.txt": {"sha": sha(root / "prompt.txt"), "text": "text of R\n"}
    }


def test_2_from_outside_the_run_is_refused_and_nothing_is_sent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = layout(tmp_path)
    monkeypatch.chdir(tmp_path / "OUT")
    with pytest.raises(ToolError) as caught:
        _run(root, "eval/suite.py")
    assert "the target Stub of suite 'qa'" in str(caught.value)
    assert "(ADR 0042 §2)" in str(caught.value)
    assert sent(tmp_path) == []
    assert not list((root / ".digline").rglob("runs/*/*.json"))


def test_4_a_relative_answer_is_refused_naming_the_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = layout(tmp_path, target=RELATIVE)
    monkeypatch.chdir(root)
    with pytest.raises(ToolError) as caught:
        _run(root, "eval/suite.py")
    assert "the target Naming of suite 'qa'" in str(caught.value)
    assert "a relative path" in str(caught.value)
    assert not list((root / ".digline").rglob("runs/*/*.json"))


@pytest.fixture
def anthropic(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[str]]:
    pytest.importorskip("digline_anthropic")
    with fake_anthropic() as (seen, url):
        monkeypatch.setenv("ANTHROPIC_BASE_URL", url)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "not-a-key")
        yield seen


@pytest.mark.parametrize("cwd", ["R", "R/eval", "OUT"])
def test_6_a_toml_target_sends_and_records_the_suite_s_prompt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, anthropic: list[str], cwd: str
) -> None:
    """Green on `main` too: the server hands the loader an absolute spec, so it
    never produced the false refusal. It guards that the repair keeps that."""
    root = toml_layout(tmp_path)
    monkeypatch.chdir(tmp_path / cwd)
    key = _run(root, "eval/suite.toml")["key"]
    assert anthropic == ["text of R/eval\n"]
    assert recorded(root, key) == {
        "eval/prompt.md": {
            "sha": sha(root / "eval" / "prompt.md"),
            "text": "text of R/eval\n",
        }
    }
