"""What `digline run` says about the suite before the first call reaches the
agent, as `notes` on the `run` tool. (#396)

The CLI prints them on stderr: a check whose class declares no `KIND`, which
the shape reading leaves out, and a tolerance that switches its check off.
Over MCP there is no stderr, so until #396 an agent never heard either, and
the default decided in silence. (ADR 0011 §4, ADR 0024 §6.4)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import anyio
from mcp.types import CallToolResult
from tests._helpers import cli

from digline_mcp.descriptions import DESCRIPTIONS
from digline_mcp.server import build_server

NOTED = """
from dataclasses import dataclass

from digline.core import (
    TEXT_ONLY,
    AssertionBase,
    Contains,
    EvaluatorInputs,
    JudgeReply,
    LlmRubric,
    OutputKind,
    Verdict,
)
from digline.run import Case, Response, Suite


@dataclass(frozen=True, slots=True)
class NoKind(AssertionBase):
    name: str = "no_kind"
    threshold: float = 0.5
    tolerance: float = 0.0
    accepts: frozenset[OutputKind] = TEXT_ONLY

    def __call__(self, inputs: EvaluatorInputs) -> Verdict:
        return self._binary(True, "fine")


def judge(prompt):
    return JudgeReply(score=1.0, reason="looked")


suite = Suite(
    tenant="acme-bank",
    environment="staging",
    name="noted",
    assertions=[
        Contains(needle="Rome"),
        NoKind(),
        LlmRubric(rubric="ok?", judge=judge, threshold=0.5, tolerance=0.5,
                  name="loose"),
    ],
    cases=[Case(id="one")],
)


def target(case):
    return Response(output="Rome", input="capital?")
"""


def call(root: Path, tool: str, **arguments: Any) -> dict[str, Any]:
    async def go() -> dict[str, Any]:
        result = await build_server(str(root), None, None).call_tool(tool, arguments)
        assert isinstance(result, CallToolResult)
        assert result.structured_content is not None
        return dict(result.structured_content)

    return anyio.run(go)


def test_run_carries_the_lines_the_cli_prints_on_stderr(repo: Path) -> None:
    (repo / "suite_noted.py").write_text(NOTED, encoding="utf-8")

    through_the_tool = call(
        repo, "run", suite=str(repo / "suite_noted.py"), acknowledge_calls=1
    )
    done = cli(repo, "run", "--suite", "suite_noted.py", "--json")
    through_the_cli = json.loads(done.stdout)

    notes = through_the_tool["notes"]
    assert len(notes) == 2, notes
    assert notes[0].startswith("no_kind declares no KIND")
    assert notes[1].startswith("tolerance 0.5 on 'loose' (threshold 0.5)")
    # One rendering for both front ends, and the same lines stderr says.
    assert notes == through_the_cli["notes"]
    for note in notes:
        assert f"digline: {note}\n" in done.stderr


def test_an_empty_list_is_a_suite_with_nothing_to_say(repo: Path) -> None:
    """The control, and the reason the key is always there: an empty list is a
    suite that was read, not a digline that did not look."""
    written = call(repo, "run", suite=str(repo / "suite_qa.py"), acknowledge_calls=2)
    assert written["notes"] == []


def test_the_description_says_what_notes_are() -> None:
    text = " ".join(DESCRIPTIONS["run"].split())
    assert "`notes` holds what `digline run` says about the suite" in text
    assert "A note stops nothing and is not a verdict" in text
