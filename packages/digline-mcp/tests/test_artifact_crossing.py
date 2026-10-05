"""ADR 0042 §3 at the MCP: a run recording `.git/config` under a suite that
discloses artifacts reaches the agent as the refusal's sentence, not as a
document and not as an untranslated crash.

`run_document` builds its artifacts section itself and does not call
`redact()`, so this is the leg that turns red when the predicate's call is
removed from `run_document` alone.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import anyio
import pytest
from mcp.server.mcpserver.exceptions import ToolError, UnexpectedToolError
from tests._helpers import cli, git

from digline_mcp.server import build_server

SUITE = """\
from pathlib import Path

from digline.core import Contains, Disclosure
from digline.run import Case, Response, Suite

suite = Suite(
    tenant="acme",
    environment="staging",
    name="qa",
    assertions=[Contains(needle="Rome")],
    cases=[Case(id="capital-it")],
    artifacts=[Path(".git/config")],
    disclosure=Disclosure(%s),
)


def target(case):
    return Response(output="Rome", cost_usd=0.01)
"""


def _repository(root: Path, disclosure: str) -> Path:
    if shutil.which("git") is None:  # pragma: no cover - CI always has git
        pytest.skip("git is not installed")
    git(root, "init", "-q")
    (root / "suite.py").write_text(SUITE % disclosure, encoding="utf-8")
    done = cli(root, "run", "--suite", "suite.py")
    assert done.returncode == 0, done.stderr
    return root


def _call(root: Path, tool: str, **arguments: Any) -> Any:
    async def go() -> Any:
        return await build_server(str(root), None, None).call_tool(tool, arguments)

    return anyio.run(go)


def test_get_run_refuses_in_words_when_artifacts_are_disclosed(tmp_path: Path) -> None:
    root = _repository(tmp_path, "artifacts=True")
    with pytest.raises(ToolError) as caught:
        _call(root, "get_run", suite=str(root / "suite.py"))
    assert type(caught.value) is not UnexpectedToolError, caught.value
    assert ".git/config" in str(caught.value)


def test_get_run_answers_when_artifacts_are_not_disclosed(tmp_path: Path) -> None:
    """Nothing crosses, so nothing is refused: the control on the test above."""
    root = _repository(tmp_path, "")
    assert _call(root, "get_run", suite=str(root / "suite.py"))
