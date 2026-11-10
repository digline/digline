"""An episode's reviewed answer as pytest rows: one per check, and each fails
on its own contradiction. (ADR 0059 §1, amended 2026-11-05)

An episode's reviewed answer is asked the trajectory checks too, so one case
has several rows: the check the answer was reviewed for, and each check on the
steps beside it. A row fails where *its* verdict contradicts the person, and
the case's other rows say what they measured. Every row of the case used to
fail with the one that did, the others with *"Score unchanged"*, while the
headline named a single contradiction.

Both directions are held: the judge contradicting a yes, with the checks on
the steps passing; and a check on the steps failing a yes, with the judge
agreeing.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from _cycle import cycle

SUITE = """
import pathlib

from digline.core import JudgeReply, LlmRubric, Never, Subsequence
from digline.core.run import recorded_steps_from_list
from digline.run import Case, Response, ReviewedAnswer, Suite

HERE = pathlib.Path(__file__).parent


def judge(prompt: str) -> JudgeReply:
    placed = float((HERE / "placed.txt").read_text().strip())
    return JudgeReply(score=placed if "REVIEWED" in prompt else 1.0, reason="looked")


STEPS = recorded_steps_from_list(
    [
        {"index": 0, "actor": "model", "finish": "tool_use"},
        {
            "index": 1,
            "actor": "tool",
            "tool": (HERE / "tool.txt").read_text().strip(),
            "arguments": "{}",
        },
        {"index": 2, "actor": "model", "finish": "stop"},
    ]
)

suite = Suite(
    tenant="acme",
    environment="staging",
    name="reviewed",
    assertions=[
        LlmRubric(rubric="acceptable?", judge=judge, threshold=0.7, tolerance=0.05),
        Never(tool="delete"),
        Subsequence(tools=["lookup"]),
    ],
    cases=[
        Case(id="alpha"),
        Case(
            id="said",
            reviewed_answer=ReviewedAnswer(
                output="REVIEWED, Acme", check="llm_rubric", good=True,
                input="Is this right?", steps=STEPS,
            ),
        ),
    ],
    samples=2,
    min_agreement="2/2",
)


def target(case: Case) -> Response:
    return Response(output="Acme, fine", cost_usd=0.001, latency_ms=10.0,
                    metadata={"tools": ["lookup"]})
"""


def reviewed(pytester: pytest.Pytester, *, score: float, tool: str = "lookup") -> Path:
    """A reference where the judge and the steps agree with the yes, then a
    run with the judge's score and the reviewed answer's tool moved: what a
    person said yes to is the same answer, and what checks it is not."""
    path = pytester.path / "suite.py"
    path.write_text(SUITE, encoding="utf-8")
    placed = pytester.path / "placed.txt"
    called = pytester.path / "tool.txt"
    placed.write_text("1.0\n", encoding="utf-8")
    called.write_text("lookup\n", encoding="utf-8")
    cycle(path, pytester.path, promote=True)
    placed.write_text(f"{score}\n", encoding="utf-8")
    called.write_text(f"{tool}\n", encoding="utf-8")
    cycle(path, pytester.path, promote=False)
    return path


def rows(result: pytest.RunResult) -> dict[str, str]:
    """The reviewed case's rows, by check, as `-v` reports each one, in
    whatever order they were collected."""
    found = re.findall(r"suite\.py::said::(\w+) (PASSED|FAILED)", result.stdout.str())
    return dict(found)


def test_the_judge_contradicting_a_yes_fails_its_row_alone(
    pytester: pytest.Pytester,
) -> None:
    """The judge fails a yes; the steps did what the person said yes to. The
    judge's row fails, and the two rows on the steps pass."""
    path = reviewed(pytester, score=0.0)
    result = pytester.runpytest_subprocess("--digline-suite", str(path), "-v")

    outcomes = result.parseoutcomes()
    assert outcomes.get("failed", 0) == 1, outcomes
    assert rows(result) == {
        "llm_rubric": "FAILED",
        "never": "PASSED",
        "subsequence": "PASSED",
    }
    assert "said · never" not in result.stdout.str()
    assert "said · subsequence" not in result.stdout.str()
    assert result.ret == pytest.ExitCode.TESTS_FAILED


def test_a_check_on_the_steps_contradicting_a_yes_fails_its_row_alone(
    pytester: pytest.Pytester,
) -> None:
    """The judge agrees with the yes; the steps now call `delete`, which one
    check says is never called, and not `lookup`, which the other expects.
    Those two rows fail, and the judge's row passes."""
    path = reviewed(pytester, score=1.0, tool="delete")
    result = pytester.runpytest_subprocess("--digline-suite", str(path), "-v")

    outcomes = result.parseoutcomes()
    assert outcomes.get("failed", 0) == 2, outcomes
    assert rows(result) == {
        "llm_rubric": "PASSED",
        "never": "FAILED",
        "subsequence": "FAILED",
    }
    assert "said · llm_rubric" not in result.stdout.str()
    assert result.ret == pytest.ExitCode.TESTS_FAILED
