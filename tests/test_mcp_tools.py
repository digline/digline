"""`.github/mcp_tools.py`, the client the examples' CI leg runs against the
published digline-mcp: it starts the server, calls every tool the server
registers, and fails on any tool that does not answer. Held here against this
tree's server, over a copy of `examples/operator`. (P-950)

No model and no credential: a tool call is JSON-RPC, and the operator's suite
answers and judges with `fake.py`.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from tests._helpers import cli, copy_tracked, git

ROOT = Path(__file__).resolve().parents[1]
CLIENT = ROOT / ".github" / "mcp_tools.py"
EXAMPLE = ROOT / "examples" / "operator"


@pytest.fixture(scope="module")
def operator(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The example as git tracks it, with one run beside its baseline, which is
    what the CI leg leaves before it runs the client."""
    root = tmp_path_factory.mktemp("operator") / "operator"
    copy_tracked(EXAMPLE, root)
    git(root, "init", "-q")
    git(root, "config", "user.email", "test@example.invalid")
    git(root, "config", "user.name", "Test")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "initial")
    done = cli(root, "run", "--suite", "suite.py")
    assert done.stdout.strip(), done.stderr
    return root


def drive(root: Path, *server: str) -> subprocess.CompletedProcess[str]:
    command = [sys.executable, str(CLIENT), "--root", str(root)]
    if server:
        command += ["--", *server]
    return subprocess.run(command, capture_output=True, text=True, check=False)


def test_every_tool_the_server_registers_answers(operator: Path) -> None:
    """The eight, each called once, each with an answer and no error."""
    done = drive(
        operator,
        sys.executable,
        "-m",
        "digline_mcp",
        "--root",
        str(operator),
        "--tenant",
        "northwind",
        "--names",
        "clear",
    )
    assert done.returncode == 0, done.stdout + done.stderr
    answered = [
        line.split()[1] for line in done.stdout.splitlines() if line.startswith("ok ")
    ]
    assert sorted(answered) == sorted(
        [
            "compare",
            "diff",
            "explain",
            "get_baseline",
            "get_run",
            "list_runs",
            "log",
            "run",
        ]
    ), done.stdout


def test_the_server_is_started_as_the_example_s_mcp_json_starts_it() -> None:
    """Without a command, the client reads the one `.mcp.json` names: the
    server a reader of the example would start."""
    declared = json.loads((EXAMPLE / ".mcp.json").read_text(encoding="utf-8"))
    (server,) = declared["mcpServers"].values()
    shown = subprocess.run(
        [sys.executable, str(CLIENT), "--root", str(EXAMPLE), "--show-server"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert shown.returncode == 0, shown.stderr
    assert json.loads(shown.stdout) == [server["command"], *server["args"]]
