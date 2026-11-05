"""The reviewed answer as a pytest row. (ADR 0059 §1)

A reviewed answer's gate is the person's verdict, read off the run alone: its
row fails where the judge contradicted the person, and never on a movement
against the reference. Two cases the movement gets wrong, and one it gets
right by accident:

- a no the judge agreed with, and agreed with harder: the score fell beyond
  the tolerance, which the comparison calls `regressed`, and nothing is wrong;
- a no the judge failed in the reference and passes now: the comparison calls
  it `improved`, and the judge contradicts the person. (The reference cannot
  contradict: promotion refuses such a run, `ContradictedRunError`.)

And one the movement gets right by accident: a yes the judge failed, now and
not in the reference.

Produced the way `test_calibration_rows.py` produces its states: by moving
what the judge does and letting the engine decide what that means.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from _cycle import cycle

SUITE = """
import pathlib

from digline.core import Contains, JudgeReply, LlmRubric
from digline.run import Case, Response, ReviewedAnswer, Suite

HERE = pathlib.Path(__file__).parent


def judge(prompt: str) -> JudgeReply:
    placed = float((HERE / "placed.txt").read_text().strip())
    return JudgeReply(score=placed if "REVIEWED" in prompt else 1.0, reason="looked")


suite = Suite(
    tenant="acme",
    environment="staging",
    name="reviewed",
    assertions=[
        Contains(needle="Acme"),
        LlmRubric(rubric="acceptable?", judge=judge, threshold=0.7, tolerance=0.05),
    ],
    cases=[
        Case(id="alpha"),
        Case(
            id="said",
            reviewed_answer=ReviewedAnswer(
                output="REVIEWED, Acme", check="llm_rubric", good=%(good)s,
                input="Is this right?",
            ),
        ),
    ],
    samples=2,
    min_agreement="2/2",
)


def target(case: Case) -> Response:
    return Response(output="Acme, fine", cost_usd=0.001, latency_ms=10.0)
"""


def reviewed(
    pytester: pytest.Pytester, *, good: bool, before: float, after: float
) -> Path:
    path = pytester.path / "suite.py"
    path.write_text(SUITE % {"good": good}, encoding="utf-8")
    placed = pytester.path / "placed.txt"
    placed.write_text(f"{before}\n", encoding="utf-8")
    cycle(path, pytester.path, promote=True)
    placed.write_text(f"{after}\n", encoding="utf-8")
    cycle(path, pytester.path, promote=False)
    return path


def test_a_no_the_judge_agreed_with_harder_fails_nothing(
    pytester: pytest.Pytester,
) -> None:
    """0.5 → 0.0 is beyond tolerance: the comparison calls it `regressed`. The
    judge failed the answer both times, which is what the person said."""
    path = reviewed(pytester, good=False, before=0.5, after=0.0)
    result = pytester.runpytest_subprocess("--digline-suite", str(path), "-v")

    outcomes = result.parseoutcomes()
    assert outcomes.get("failed", 0) == 0, outcomes
    assert outcomes.get("errors", 0) == 0, outcomes
    result.stdout.fnmatch_lines(["*said::llm_rubric*PASSED*"])
    assert result.ret == pytest.ExitCode.OK


def test_a_no_the_judge_now_passes_fails_though_it_improved(
    pytester: pytest.Pytester,
) -> None:
    """0.5 → 1.0: a fail that became a pass, which the comparison calls
    `improved`. The person said no, so the judge contradicts them now, and
    the row fails, with exit 1."""
    path = reviewed(pytester, good=False, before=0.5, after=1.0)
    result = pytester.runpytest_subprocess("--digline-suite", str(path), "-v")

    outcomes = result.parseoutcomes()
    assert outcomes.get("failed", 0) == 1, outcomes
    result.stdout.fnmatch_lines(["*said::llm_rubric*FAILED*"])
    assert result.ret == pytest.ExitCode.TESTS_FAILED


def test_a_yes_the_judge_failed_fails_its_row(pytester: pytest.Pytester) -> None:
    path = reviewed(pytester, good=True, before=1.0, after=0.0)
    result = pytester.runpytest_subprocess("--digline-suite", str(path), "-v")

    outcomes = result.parseoutcomes()
    assert outcomes.get("failed", 0) == 1, outcomes
    result.stdout.fnmatch_lines(["*said::llm_rubric*FAILED*"])
    assert result.ret == pytest.ExitCode.TESTS_FAILED
