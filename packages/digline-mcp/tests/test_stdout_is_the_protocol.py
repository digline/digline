"""On the stdio transport standard output is the protocol, and it carries the
protocol alone (ADR 0043 §8, amended 2026-10-18; ADR 0011 §8).

The server is launched as a client launches it, and spoken to in raw JSON-RPC
lines rather than through the SDK's client, which would read past a line that
is not a message and hide the very thing under test. The suite prints in the
windows a tool call reaches: when it and a module it imports are loaded, at
each target call and at each judge call. The three late writes the amendment
declares (a thread after the answer, `atexit`, `__del__`) are not here: they
are declared, not closed.

Standard output is read **until the server exits on its own**, after stdin
closes, and never cut short with `terminate()`. The leak this guards against
was Python's buffer for standard output, written when the server stopped and
the SDK pointed descriptor 1 back at the protocol: a test that killed the
server would kill the leak with it and pass.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

import pytest
from tests._helpers import MARKS, printing_repo

ROOT = Path(__file__).resolve().parents[3]
TIMEOUT = 60


@pytest.fixture
def printing(tmp_path: Path) -> Path:
    if shutil.which("git") is None:  # pragma: no cover - CI always has git
        pytest.skip("git is not installed")
    return printing_repo(tmp_path)


def _message(line: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(line)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    return cast(dict[str, Any], parsed)


def test_the_protocol_stream_carries_json_rpc_and_nothing_else(printing: Path) -> None:
    suite = str(printing / "suite_qa.py")
    calls: list[tuple[str, dict[str, Any]]] = [
        ("compare", {"suite": suite}),
        ("run", {"suite": suite, "acknowledge_calls": 2}),
        ("list_runs", {"suite": suite}),
    ]
    server = subprocess.Popen(
        [sys.executable, "-m", "digline_mcp", "--root", str(printing)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=printing,
        env={
            **os.environ,
            "PYTHONPATH": os.pathsep.join(
                [str(ROOT / "src"), str(ROOT / "packages" / "digline-mcp" / "src")]
            ),
        },
    )
    assert server.stdin is not None and server.stdout is not None

    def send(message: dict[str, Any]) -> None:
        assert server.stdin is not None
        server.stdin.write((json.dumps(message) + "\n").encode())
        server.stdin.flush()

    lines: list[str] = []

    def answer(wanted: int) -> dict[str, Any]:
        assert server.stdout is not None
        while raw := server.stdout.readline():
            lines.append(raw.decode("utf-8", errors="replace").rstrip("\n"))
            message = _message(lines[-1])
            if message is not None and message.get("id") == wanted:
                return message
        raise AssertionError(f"the server closed before answering {wanted}")

    try:
        send(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "0"},
                },
            }
        )
        answer(1)
        send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        for number, (name, arguments) in enumerate(calls, start=2):
            send(
                {
                    "jsonrpc": "2.0",
                    "id": number,
                    "method": "tools/call",
                    "params": {"name": name, "arguments": arguments},
                }
            )
            reply = answer(number)
            assert not reply["result"].get("isError"), (
                f"{name} was refused, so its windows were never reached: {reply}"
            )
        # The client goes away; the server stops by itself, and whatever it still
        # holds for standard output is written now or never.
        rest, err = server.communicate(timeout=TIMEOUT)
    finally:
        if server.poll() is None:
            server.kill()

    lines += [line for line in rest.decode("utf-8", errors="replace").splitlines()]
    stray = [line for line in lines if line.strip() and _message(line) is None]
    assert not stray, (
        f"{len(stray)} line(s) on the protocol stream are not JSON-RPC (ADR 0043 "
        f"§8, ADR 0011 §8): {stray}"
    )
    stderr = err.decode("utf-8", errors="replace")
    for window in ("suite import", "module print", "target call", "judge call"):
        assert MARKS[window] in stderr, (
            f"{MARKS[window]} reached neither stream: the user's output was "
            f"dropped, not moved to standard error."
        )
