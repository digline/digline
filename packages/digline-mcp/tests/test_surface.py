"""The absence is the thesis, so it is the first thing tested.

`AGENTS.md` §1 asks an agent not to promote. This package makes that a fact
about what the agent can reach rather than a rule it is asked to follow, and
these are the checks that keep it true. (ADR 0011 §1, §13)
"""

from __future__ import annotations

import ast
from pathlib import Path

import anyio
import pytest

from digline_mcp.server import build_server

SRC = Path(__file__).resolve().parents[1] / "src"

#: The whole surface. Adding a seventh entry has to happen here first, which is
#: the point: a tool that appears without somebody editing this line is a tool
#: nobody decided on.
TOOLS = {"list_runs", "get_run", "get_baseline", "compare", "diff", "run"}


def tool_names(root: str) -> set[str]:
    async def go() -> set[str]:
        return {t.name for t in await build_server(root, None, None).list_tools()}

    return anyio.run(go)


def test_the_surface_is_exactly_six_tools(tmp_path: Path) -> None:
    assert tool_names(str(tmp_path)) == TOOLS


@pytest.mark.parametrize("absent", ["promote", "migrate", "view", "report"])
def test_the_missing_tools_are_missing(absent: str, tmp_path: Path) -> None:
    """Named one at a time so a failure says which one came back.

    `promote` is the thesis: a baseline is an approved reference, it is written
    into a committed directory, and an agent that promotes dissolves the word —
    the file still says `baseline` and nobody decided anything. The other three
    are upgrade maintenance and two human-facing documents.
    """
    assert absent not in tool_names(str(tmp_path))


def test_the_absence_holds_at_the_import_graph_too() -> None:
    """Not only the tool list. A surface that omitted `promote` while the module
    still imported `promote_baseline` would be one editor away from offering it,
    and the reviewer of that edit would see a two-line diff.
    """
    forbidden = {"promote_baseline", "migrate_paths", "serve", "render_html"}
    for source in sorted(SRC.rglob("*.py")):
        tree = ast.parse(source.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                reached = {a.name for a in node.names} & forbidden
                assert not reached, (
                    f"{source.name} imports {sorted(reached)}: this surface "
                    "reads and measures. It does not promote, migrate, or "
                    "render a document for a person."
                )


def test_every_reading_tool_says_it_is_read_only() -> None:
    """A hint and not the enforcement — the enforcement is the absence — but a
    client that surfaces annotations should show the same shape."""

    async def go() -> None:
        tools = {t.name: t for t in await build_server(".", None, None).list_tools()}
        for name in TOOLS - {"run"}:
            hints = tools[name].annotations
            assert hints is not None, name
            assert hints.read_only_hint is True, name
        measures = tools["run"].annotations
        assert measures is not None
        assert measures.read_only_hint is False
        assert measures.idempotent_hint is False

    anyio.run(go)


def test_the_run_tool_requires_the_count_in_its_schema() -> None:
    """`acknowledge_calls` is on the schema, so a caller sees it before calling
    rather than discovering it in a refusal."""

    async def go() -> None:
        tools = {t.name: t for t in await build_server(".", None, None).list_tools()}
        assert "acknowledge_calls" in tools["run"].input_schema["properties"]

    anyio.run(go)
