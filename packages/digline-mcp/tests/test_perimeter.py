"""The suite a tool names has to be inside this server's repository.

ADR 0011 §8 says "one server, one repository", and until 0.1.1 nothing enforced
it: `suite` arrived from a tool call and went to `load_suite`, which **executes**
a `.py`. Every tool was therefore a way to run a file from anywhere on the disk —
including the five that declare `read_only_hint=True`, which is the annotation a
client reads to decide it may call something without asking a person first.

So the test that matters is not "was it refused" but **"did it run"**: the suite
outside the root writes a file, and every case here asserts that file was never
written. A refusal that arrived after the exec would look identical from the
outside and would be worth nothing.
"""

from __future__ import annotations

from pathlib import Path

import anyio
import pytest
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import CallToolResult

from digline_mcp.server import build_server

#: A suite that is valid — it loads, it has a target, it would run — so that
#: what is being tested is the boundary and not a parse error somewhere.
OUTSIDE_SUITE = """
from pathlib import Path

Path({sentinel!r}).write_text("executed")

from digline.core import Contains
from digline.run import Case, Response, Suite

suite = Suite(
    tenant="acme-bank",
    environment="staging",
    name="qa",
    assertions=[Contains(needle="Rome")],
    cases=[Case(id="one")],
)


def target(case):
    return Response(output="The capital is Rome.", input="q", cost_usd=0.01,
                    latency_ms=100.0)
"""

#: Every tool, with the arguments it needs beyond `suite`. All six, because the
#: defect was in the funnel they all cross and a fix that reached five of them
#: would leave the sixth as the whole vulnerability.
TOOLS: tuple[tuple[str, dict[str, object]], ...] = (
    ("list_runs", {}),
    ("get_run", {}),
    ("get_baseline", {}),
    ("compare", {}),
    ("diff", {"run1": "latest", "run2": "latest"}),
    ("run", {"acknowledge_calls": 1}),
)


@pytest.fixture
def outside(tmp_path: Path) -> tuple[Path, Path, Path]:
    """A root, a suite that is not in it, and the file that suite would write."""
    root = tmp_path / "repo"
    root.mkdir()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    sentinel = tmp_path / "executed"
    suite = elsewhere / "suite_qa.py"
    suite.write_text(OUTSIDE_SUITE.format(sentinel=str(sentinel)), encoding="utf-8")
    return root, suite, sentinel


def call(root: Path, name: str, arguments: dict[str, object]) -> str:
    async def go() -> str:
        server = build_server(str(root), None, None)
        try:
            result = await server.call_tool(name, arguments)
        except ToolError as refusal:
            return str(refusal)
        assert isinstance(result, CallToolResult)
        return ""

    return anyio.run(go)


@pytest.mark.parametrize(("name", "extra"), TOOLS, ids=[n for n, _ in TOOLS])
def test_a_suite_outside_the_root_is_refused_and_never_runs(
    outside: tuple[Path, Path, Path], name: str, extra: dict[str, object]
) -> None:
    root, suite, sentinel = outside
    refusal = call(root, name, {"suite": str(suite), **extra})
    assert "one server, one repository" in refusal, refusal
    assert "ADR 0011 §8" in refusal
    # The line the whole file exists for.
    assert not sentinel.exists(), f"{name} executed a suite outside {root}"


@pytest.mark.parametrize(("name", "extra"), TOOLS, ids=[n for n, _ in TOOLS])
def test_a_traversal_out_of_the_root_is_refused_and_never_runs(
    outside: tuple[Path, Path, Path], name: str, extra: dict[str, object]
) -> None:
    """The same escape written relatively, which is how it would actually
    arrive: a path that looks like it is inside until it is resolved."""
    root, _suite, sentinel = outside
    spec = "../elsewhere/suite_qa.py"
    refusal = call(root, name, {"suite": spec, **extra})
    assert "one server, one repository" in refusal, refusal
    assert not sentinel.exists(), f"{name} executed a suite outside {root}"


def test_the_refusal_names_the_path_it_resolved_to(
    outside: tuple[Path, Path, Path],
) -> None:
    """A relative spec and the file it lands on are different sentences, and the
    one worth printing is the second: `../elsewhere/suite_qa.py` tells a reader
    nothing about which repository it left."""
    root, suite, _sentinel = outside
    refusal = call(root, "list_runs", {"suite": "../elsewhere/suite_qa.py"})
    assert str(suite) in refusal
    assert str(root.resolve()) in refusal


def test_a_module_path_is_refused_because_it_cannot_be_placed(
    outside: tuple[Path, Path, Path],
) -> None:
    """The dotted form resolves through `sys.path`, so this server cannot say it
    is in the repository — and a perimeter that cannot check is not one. The CLI
    still takes it: a person's tool has no perimeter to keep."""
    root, _suite, _sentinel = outside
    refusal = call(root, "list_runs", {"suite": "some.installed.module"})
    assert "names no file inside" in refusal
    assert "sys.path" in refusal


def test_a_suite_inside_the_root_still_loads(repo: Path) -> None:
    """The guard on the guard: a containment check that refused everything would
    pass every test above and ship a server that does nothing."""
    assert call(repo, "list_runs", {"suite": "suite_qa.py"}) == ""
    assert call(repo, "list_runs", {"suite": str(repo / "suite_qa.py")}) == ""
