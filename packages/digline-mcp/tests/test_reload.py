"""The three manifestations ADR 0052 measured through this server (#513).

One server, many tool calls, one process: a suite loaded again must read its
application again. Each test is one of the record's measured cases, (a), (b)
and (c), driven through the `run` tool as the record measured it, with the
answer read from the store, where `record_responses=True` puts it.

The server is built in this process, so these tests share `sys.modules` and
the import state with it, and `process_state` puts that state back afterwards.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import anyio
import pytest
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import CallToolResult, TextContent

from digline.host import loader as loader_module
from digline_mcp.server import build_server

SUITE = """import {module}
from digline.core import Contains
from digline.run import Case, Response, Suite

suite = Suite(
    tenant="probe",
    environment="probe",
    name="{name}",
    assertions=[Contains(needle="{needle}")],
    cases=[Case(id="c1")],
    record_responses=True,
)


def target(case):
    return Response(output={module}.reply(case.id), cost_usd=0.0, latency_ms=1.0)
"""

PLAIN = """from digline.core import Contains
from digline.run import Case, Response, Suite

suite = Suite(
    tenant="probe",
    environment="probe",
    name="{name}",
    assertions=[Contains(needle="answer")],
    cases=[Case(id="c1")],
    record_responses=True,
)


def target(case):
    return Response(output="{text}", cost_usd=0.0, latency_ms=1.0)
"""

REPLY = """def reply(case_id):
    return "{text}" + {suffix}
"""


@pytest.fixture
def process_state(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Put back what loading a suite changes in this process."""
    monkeypatch.setattr(sys, "path", list(sys.path))
    monkeypatch.setattr(sys, "path_hooks", list(sys.path_hooks))
    monkeypatch.setattr(sys, "path_importer_cache", dict(sys.path_importer_cache))
    monkeypatch.setattr(
        loader_module,
        "_scoped",
        set(loader_module._scoped),  # pyright: ignore[reportPrivateUsage]
    )
    modules = dict(sys.modules)
    yield
    for name in [name for name in sys.modules if name not in modules]:
        del sys.modules[name]
    for name, module in modules.items():
        sys.modules[name] = module


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def a_suite(
    root: Path,
    directory: str,
    *,
    name: str,
    needle: str = "answer",
    module: str = "brief",
) -> Path:
    path = root / directory / "suite.py"
    write(path, SUITE.format(module=module, name=name, needle=needle))
    return path


def a_reply(root: Path, directory: str, text: str, *, module: str = "brief") -> None:
    write(
        root / directory / f"{module}.py",
        REPLY.format(text=text, suffix='" to " + case_id'),
    )


def run_tools(root: Path, suites: list[Path], between: Any = None) -> list[str]:
    """Run each suite through one server's `run` tool, in order, and return
    what each target answered, read from the store. A refusal is returned as
    its text. `between`, if given, is called after the first run."""

    async def go() -> list[str]:
        server = build_server(str(root), None, None, names="clear", table=None)
        answers: list[str] = []
        for index, suite in enumerate(suites):
            if index == 1 and between is not None:
                between()
            try:
                result = await server.call_tool(
                    "run", {"suite": str(suite), "acknowledge_calls": 1}
                )
            except ToolError as refusal:
                answers.append(f"refused: {refusal}")
                continue
            assert isinstance(result, CallToolResult)
            content = result.content[0]
            assert isinstance(content, TextContent)
            answers.append(stored_answer(root, json.loads(content.text)["key"]))
        return answers

    return anyio.run(go)


def stored_answer(root: Path, key: str) -> str:
    (path,) = [p for p in (root / ".digline").rglob("*.json") if p.stem == key]
    found: list[str] = []

    def walk(node: object) -> None:
        if isinstance(node, dict):
            for k, v in cast("dict[str, object]", node).items():
                if k == "output" and isinstance(v, str):
                    found.append(v)
                walk(v)
        elif isinstance(node, list):
            for v in cast("list[object]", node):
                walk(v)

    walk(json.loads(path.read_text(encoding="utf-8")))
    (output,) = found
    return output


@pytest.mark.usefixtures("process_state")
def test_a_one_suite_edited_between_two_runs_reads_the_edit(tmp_path: Path) -> None:
    """ADR 0052, (a): *"`run`, same session — the target answered `answer v1 to
    c1`, and the store recorded that answer, in a run that declares
    `git_commit = 1d811f4…-dirty`: the edited tree, which the target did not
    execute"*."""
    suite = a_suite(tmp_path, "a", name="alpha")
    a_reply(tmp_path, "a", "answer v1")

    def edit() -> None:
        a_reply(tmp_path, "a", "answer v2")

    first, second = run_tools(tmp_path, [suite, suite], between=edit)
    assert first == "answer v1 to c1"
    assert second == "answer v2 to c1", (
        f"after brief.py was edited to answer v2, the second run in the same "
        f"session answered {second!r}: the application loaded first, not the one "
        "on disk (ADR 0052, (a))"
    )


@pytest.mark.usefixtures("process_state")
def test_b_a_second_suite_reads_its_own_application(tmp_path: Path) -> None:
    """ADR 0052, (b): *"`run two/suite.py`, same session — the target answered
    `answer from one to c1`, and `two`'s store recorded it: the answer of
    `one/brief.py`"*."""
    one, two = (
        a_suite(tmp_path, "one", name="one"),
        a_suite(tmp_path, "two", name="two"),
    )
    a_reply(tmp_path, "one", "answer from one")
    a_reply(tmp_path, "two", "answer from two")
    first, second = run_tools(tmp_path, [one, two])
    assert first == "answer from one to c1"
    assert second == "answer from two to c1", (
        f"two's run answered {second!r}: the application of one/brief.py, "
        "loaded by the first suite of the session (ADR 0052, (b))"
    )


@pytest.mark.usefixtures("process_state")
def test_c_a_name_only_an_earlier_suite_holds_is_not_found(tmp_path: Path) -> None:
    """ADR 0052, (c): *"`run second/suite.py`, same session — the import
    **succeeded**: `second`'s target answered **`answer from first/helper.py`**,
    and `second`'s store recorded it"*, where alone it is refused with *"could
    not import 'helper': No module named 'helper'"*."""
    first = tmp_path / "first" / "suite.py"
    write(first, PLAIN.format(name="first", text="answer from first"))
    write(
        tmp_path / "first" / "helper.py",
        'def reply(case_id):\n    return "answer from first/helper.py"\n',
    )
    second = a_suite(tmp_path, "second", name="second", module="helper")
    answers = run_tools(tmp_path, [first, second])
    assert answers[0] == "answer from first"
    assert (
        answers[1].startswith("refused: ") and "could not import 'helper'" in answers[1]
    ), (
        f"second/suite.py imports helper, which exists only in first/, and in the "
        f"same session it answered {answers[1]!r}: first/ was left on sys.path "
        "(ADR 0052, (c))"
    )
