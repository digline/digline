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

#: The whole surface. Adding a ninth entry has to happen here first, which is
#: the point: a tool that appears without somebody editing this line is a tool
#: nobody decided on. `explain` and `log` were added together, so the count moved
#: once. (ADR 0020 §9)
TOOLS = {
    "list_runs",
    "get_run",
    "get_baseline",
    "log",
    "compare",
    "diff",
    "explain",
    "run",
}


def tool_names(root: str) -> set[str]:
    async def go() -> set[str]:
        return {t.name for t in await build_server(root, None, None).list_tools()}

    return anyio.run(go)


def test_the_surface_is_exactly_eight_tools(tmp_path: Path) -> None:
    assert tool_names(str(tmp_path)) == TOOLS


@pytest.mark.parametrize("absent", ["promote", "migrate", "view", "report", "register"])
def test_the_missing_tools_are_missing(absent: str, tmp_path: Path) -> None:
    """Named one at a time so a failure says which one came back.

    `promote` is the thesis: a baseline is an approved reference, it is written
    into a committed directory, and an agent that promotes dissolves the word —
    the file still says `baseline` and nobody decided anything. The next three
    are upgrade maintenance and two human-facing documents. `register` is absent
    for `promote`'s reason: it writes a committed file, and a disposition is by
    definition a person's (ADR 0021 §2).
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


#: Every hint on every tool, as (read_only, destructive, idempotent, open_world).
#: All four, because a client acts on each: Codex asks for approval on
#: `destructive_hint` even where `read_only_hint` is true, and VS Code asks to
#: review the results of an open-world tool. `None` is "not declared": the
#: spec gives `idempotent_hint` meaning only when `read_only_hint` is false.
#: The reading tools stay closed world although each loads the suite it is
#: named, and a `suite.py` is the project's code. Open world was tried and
#: withdrawn on 2026-10-12: VS Code then held every read's result for a
#: person to review, where reads had asked nothing, and Codex does not read
#: the hint once `read_only_hint` is true.
READING = (True, False, None, False)
MEASURING = (False, False, False, True)
HINTS = {name: READING for name in TOOLS - {"run"}} | {"run": MEASURING}


def test_every_reading_tool_says_it_is_read_only() -> None:
    """A hint and not the enforcement — the enforcement is the absence — but a
    client that surfaces annotations should show the same shape."""

    async def go() -> None:
        tools = {t.name: t for t in await build_server(".", None, None).list_tools()}
        assert set(tools) == set(HINTS)
        for name, expected in HINTS.items():
            hints = tools[name].annotations
            assert hints is not None, name
            declared = (
                hints.read_only_hint,
                hints.destructive_hint,
                hints.idempotent_hint,
                hints.open_world_hint,
            )
            assert declared == expected, name

    anyio.run(go)


def test_the_run_tool_requires_the_count_in_its_schema() -> None:
    """`acknowledge_calls` is on the schema, so a caller sees it before calling
    rather than discovering it in a refusal."""

    async def go() -> None:
        tools = {t.name: t for t in await build_server(".", None, None).list_tools()}
        assert "acknowledge_calls" in tools["run"].input_schema["properties"]

    anyio.run(go)
