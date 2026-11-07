"""A contradiction reaches the agent as `notes` on the `run` tool, as `digline
run` says it on stderr beside the bill. (P-1582; ADR 0059 §1, ADR 0011 §4)

The run exits 0 and `compare`, `explain` and `report` exit 1 on it, so the
person who ran the command hears it first from the run. Over MCP there is no
stderr, and until P-1582 the tool's `notes` were empty on such a run.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import anyio
from mcp.types import CallToolResult
from tests._helpers import cli

from digline_mcp.server import build_server

#: Only the recorded answer and its question hold these.
ANSWER = "MARK-ANSWER-c3e"
QUESTION = "MARK-QUESTION-c3e"

#: The case of the story `story-python-many-prompts`: a person said no, and
#: the judge passes the answer.
SAID_NO = f"""
from digline.core import JudgeReply, LlmRubric
from digline.run import Case, Response, ReviewedAnswer, Suite


def judge(prompt):
    return JudgeReply(score=1.0, reason="looked")


suite = Suite(
    tenant="acme-bank",
    environment="staging",
    name="said_no",
    assertions=[
        LlmRubric(rubric="ok?", judge=judge, threshold=0.7, tolerance=0.05),
    ],
    cases=[
        Case(id="by-hand"),
        Case(
            id="refused-by-a-person",
            reviewed_answer=ReviewedAnswer(
                output="{ANSWER}", check="llm_rubric", good=False,
                input="{QUESTION}",
            ),
        ),
    ],
    samples=2,
    min_agreement="2/2",
)


def target(case):
    return Response(output="fine", input="q")
"""

#: A yes whose steps break `before`, which names the check and the case.
ON_THE_STEPS = """
from digline.core import Before, JudgeReply, LlmRubric
from digline.core.run import RecordedStep, RecordedToolCall
from digline.run import Case, Response, ReviewedAnswer, Suite


def judge(prompt):
    return JudgeReply(score=1.0, reason="looked")


suite = Suite(
    tenant="acme-bank",
    environment="staging",
    name="steps",
    assertions=[
        LlmRubric(rubric="ok?", judge=judge, threshold=0.7, tolerance=0.05),
        Before(first="lookup_order", then="issue_refund"),
    ],
    cases=[
        Case(id="by-hand"),
        Case(
            id="refund-turn",
            reviewed_answer=ReviewedAnswer(
                output="Done.", check="llm_rubric", good=True, input="q",
                steps=(
                    RecordedStep(index=0, actor="model", finish="tool_use"),
                    RecordedStep(index=1, actor="tool", call=RecordedToolCall(
                        tool="issue_refund", arguments="{}")),
                    RecordedStep(index=2, actor="model", finish="stop"),
                ),
            ),
        ),
    ],
    samples=2,
    min_agreement="2/2",
)


def target(case):
    return Response(output="fine", metadata={"tools": ["lookup_order"]})
"""


def run_tool(root: Path, suite: str, table: Any = None) -> dict[str, Any]:
    async def go() -> dict[str, Any]:
        server = build_server(
            str(root),
            None,
            None,
            names="clear" if table is None else "project",
            table=table,
        )
        arguments = {"suite": str(root / suite), "acknowledge_calls": 2}
        result = await server.call_tool("run", arguments)
        assert isinstance(result, CallToolResult)
        assert result.structured_content is not None
        return dict(result.structured_content)

    return anyio.run(go)


def test_the_run_tool_says_the_contradiction_as_stderr_does(repo: Path) -> None:
    (repo / "suite_said_no.py").write_text(SAID_NO, encoding="utf-8")

    through_the_tool = run_tool(repo, "suite_said_no.py")
    done = cli(repo, "run", "--suite", "suite_said_no.py", "--json")
    assert done.returncode == 0, done.stderr
    through_the_cli = json.loads(done.stdout)
    terminal = cli(repo, "run", "--suite", "suite_said_no.py")
    assert terminal.returncode == 0, terminal.stderr

    said = "the judge contradicted a person on 1 reviewed answer"
    assert through_the_tool["notes"] == [said]
    # One rendering for every front end: the tool, `run --json`, and the line
    # the terminal prints beside the bill.
    assert through_the_cli["notes"] == [said]
    assert f"digline: {said}." in terminal.stderr.splitlines()
    # Facts and no recorded word.
    answered = json.dumps(through_the_tool)
    assert ANSWER not in answered
    assert QUESTION not in answered


def test_a_run_nobody_was_contradicted_in_has_no_such_note(repo: Path) -> None:
    """The control: the shipped suite reviews nothing, and its notes stay
    empty."""
    written = run_tool(repo, "suite_qa.py")
    assert written["notes"] == []


def test_under_project_the_note_names_check_and_case_by_their_tokens(
    repo: Path,
) -> None:
    from _names import RecordingTable

    (repo / "suite_steps.py").write_text(ON_THE_STEPS, encoding="utf-8")
    in_clear = run_tool(repo, "suite_steps.py")["notes"]
    assert in_clear == [
        "a check on the steps contradicted a person on 1 reviewed answer: "
        "before, on case refund-turn"
    ]

    table = RecordingTable()
    (note,) = run_tool(repo, "suite_steps.py", table=table)["notes"]
    assert "before" not in note, note
    assert "refund-turn" not in note, note
    assert table.mint("verdict_name", "before") in note, note
    assert table.mint("case_id", "refund-turn") in note, note
