"""What this package must not drag in, and what it must not do on import.

`mcp` brings twenty-five packages with it — pydantic, starlette, uvicorn,
httpx2, cryptography, python-multipart. digline's core has one runtime
dependency, `jsonschema`. None of that may land on somebody who ran
`pip install digline` to check whether their prompt got worse, which is the
whole reason this is a separate package. (ADR 0011 §3, §13)
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DIGLINE = ROOT / "src" / "digline"


def test_installing_digline_does_not_install_mcp() -> None:
    """Asserted here as well as by the layering gate, because the dependency is
    heavy enough to be worth naming in the package that introduces it."""
    for source in sorted(DIGLINE.rglob("*.py")):
        tree = ast.parse(source.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                assert name.split(".")[0] != "mcp", (
                    f"{source.relative_to(DIGLINE)} imports {name}: digline must "
                    "not depend on a package that depends on it, and `mcp` "
                    "would arrive for every user of the core."
                )


def test_importing_the_server_opens_no_socket_and_exports_no_telemetry() -> None:
    """Fixed decision 5: no network call the user has not configured.

    `opentelemetry-api` arrives unconditionally as a transitive dependency of
    `mcp`. It is an API-only package whose default implementation is a no-op —
    it sends nothing without an SDK and an exporter, neither of which is
    installed — and this asserts that rather than trusting it. The socket check
    is the same rule facing the other way: building a server must not bind
    anything, because the transport is stdio and a client launches the process.
    """
    probe = """
import socket, sys

opened = []
real = socket.socket.bind
def watched(self, address):
    opened.append(address)
    return real(self, address)
socket.socket.bind = watched

import digline_mcp.server as server
server.build_server(".", None, None)

from opentelemetry import trace
provider = type(trace.get_tracer_provider()).__name__

print(opened, provider)
"""
    # A subprocess does not inherit pytest's `pythonpath`, and this has to be a
    # subprocess: the question is what a *fresh interpreter* does on import, and
    # this one has already imported everything.
    env = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join(
            [str(ROOT / "src"), str(ROOT / "packages" / "digline-mcp" / "src")]
        ),
    }
    done = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        check=True,
        cwd=ROOT,
        env=env,
    )
    opened, provider = done.stdout.strip().rsplit(" ", 1)
    assert opened == "[]", f"building the server bound {opened}"
    # The no-op default. `TracerProvider` here would mean something configured
    # an exporter, and an exporter is a network call nobody asked for.
    assert provider in {"ProxyTracerProvider", "NoOpTracerProvider"}, provider


def test_the_package_declares_both_halves_of_the_mcp_floor() -> None:
    """Unpinned, a resolver could hand somebody 1.x, where `MCPServer` does not
    exist. The cap is the same lesson: a major version that renames the entry
    point is not hypothetical, it is what 2.0 did."""
    import tomllib

    with (ROOT / "packages" / "digline-mcp" / "pyproject.toml").open("rb") as handle:
        dependencies = tomllib.load(handle)["project"]["dependencies"]
    mcp = next(d for d in dependencies if str(d).replace(" ", "").startswith("mcp"))
    assert ">=2.2" in mcp and "<3" in mcp, mcp
