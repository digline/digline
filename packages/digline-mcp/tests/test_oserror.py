"""An `OSError` digline raised reaches an agent whole. (#451)

`packages/digline-mcp/tests/test_boundary.py` holds the other half: an
`OSError` the suite raises, P1 to P3 of #451 and a `preflight`'s, reaches an
agent with its type and location and without its message. These are P4 to P6,
digline's own reads, which before #451 reached an agent as *Error executing
tool* (P6) or with a sentence saying digline had not written them (P4, P5).
(ADR 0043 §1, amended with #451)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import anyio
import pytest
from mcp.server.mcpserver.exceptions import ToolError
from tests._helpers import git

from digline.wire import WITHHELD
from digline_mcp.server import build_server

SUITE_PY = """
from digline.core import Contains
from digline.run import Case, Response, Suite

suite = Suite(
    tenant="acme",
    environment="staging",
    name="qa",
    assertions=[Contains(needle="Rome")],
    cases=[Case(id="one", vars={})],
)

def target(case):
    return Response(output="Rome", input="q", cost_usd=0.0, latency_ms=1.0)
"""

SUITE_TOML = """
[suite]
tenant = "acme"
environment = "staging"
name = "qa"
cases = "cases.json"

[target]
type = "http"
url = "http://127.0.0.1:9/answer"
output_path = "answer"

[[assertions]]
type = "contains"
needle = "Rome"
"""

without_mode_000 = pytest.mark.skipif(
    sys.platform == "win32" or os.geteuid() == 0,
    reason="mode 000 denies nothing to root, and Windows has no such mode",
)


def refused(root: Path, tool: str, suite: Path) -> str:
    async def go() -> str:
        server = build_server(str(root), None, None)
        try:
            await server.call_tool(tool, {"suite": str(suite)})
        except ToolError as refusal:
            return str(refusal).removeprefix(f"Error executing tool {tool}: ")
        pytest.fail(f"{tool} answered")

    return anyio.run(go)


def whole(said: str, words: str) -> None:
    """Refused in words, digline's, with the system's description in them."""
    assert words in said, said
    assert WITHHELD not in said, said
    assert not said.startswith("Error executing tool"), said


def test_p4_a_cases_file_that_is_not_there(tmp_path: Path) -> None:
    git(tmp_path, "init", "-q")
    (tmp_path / "suite.toml").write_text(SUITE_TOML, encoding="utf-8")
    said = refused(tmp_path, "list_runs", tmp_path / "suite.toml")
    whole(said, "No such file or directory")


@without_mode_000
def test_p5_a_suite_file_digline_cannot_read(tmp_path: Path) -> None:
    git(tmp_path, "init", "-q")
    suite = tmp_path / "suite.toml"
    suite.write_text(SUITE_TOML, encoding="utf-8")
    suite.chmod(0)
    try:
        said = refused(tmp_path, "list_runs", suite)
    finally:
        suite.chmod(0o644)
    whole(said, "Permission denied")


@without_mode_000
def test_p6_a_baseline_digline_cannot_read(tmp_path: Path) -> None:
    """Bare: no wrap, so before #451 the server did not translate it at all."""
    git(tmp_path, "init", "-q")
    (tmp_path / "suite.py").write_text(SUITE_PY, encoding="utf-8")
    baselines = tmp_path / ".digline" / "acme" / "baselines"
    baselines.mkdir(parents=True)
    baseline = baselines / "qa.json"
    baseline.write_text("{}", encoding="utf-8")
    baseline.chmod(0)
    try:
        said = refused(tmp_path, "get_baseline", tmp_path / "suite.py")
    finally:
        baseline.chmod(0o644)
    whole(said, "Permission denied")
    assert "pathlib" not in said, said
