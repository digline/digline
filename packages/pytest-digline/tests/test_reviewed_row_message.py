"""A reviewed answer's failing row says the contradiction. (P-1582; ADR 0059 §1)

The row fails on the person's verdict, never on a movement against the
reference. Its FAILURES line said the movement all the same, and on the case
of the story `story-python-many-prompts`, a reviewed no added after the
reference and a judge that passes it, the movement is *"Checked here, not
present in the reference"*, which names nothing that failed.
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
    return JudgeReply(score=%(score)s, reason="looked")


reviewed = [
    Case(
        id="said",
        reviewed_answer=ReviewedAnswer(
            output="Acme, a reviewed answer", check="llm_rubric", good=%(good)s,
            input="Is this right?",
        ),
    ),
]

suite = Suite(
    tenant="acme",
    environment="staging",
    name="reviewed",
    assertions=[
        Contains(needle="Acme"),
        LlmRubric(rubric="acceptable?", judge=judge, threshold=0.7, tolerance=0.05),
    ],
    cases=[Case(id="alpha"), *(reviewed if (HERE / "added").exists() else [])],
    samples=2,
    min_agreement="2/2",
)


def target(case: Case) -> Response:
    return Response(output="Acme, fine", cost_usd=0.001, latency_ms=10.0)
"""


def added_after_the_reference(
    pytester: pytest.Pytester, *, good: bool, score: float
) -> Path:
    """A reference without the reviewed answer, then a run with it."""
    path = pytester.path / "suite.py"
    path.write_text(SUITE % {"good": good, "score": score}, encoding="utf-8")
    cycle(path, pytester.path, promote=True)
    (pytester.path / "added").write_text("", encoding="utf-8")
    cycle(path, pytester.path, promote=False)
    return path


@pytest.mark.parametrize(
    ("good", "score", "said"),
    [
        (False, 1.0, "llm_rubric passed where the person said no."),
        (True, 0.0, "llm_rubric failed where the person said yes."),
    ],
    ids=["a-no-the-judge-passes", "a-yes-the-judge-fails"],
)
def test_the_failing_row_says_the_contradiction(
    pytester: pytest.Pytester, good: bool, score: float, said: str
) -> None:
    path = added_after_the_reference(pytester, good=good, score=score)
    result = pytester.runpytest_subprocess("--digline-suite", str(path), "-v")

    result.stdout.fnmatch_lines(["*said::llm_rubric*FAILED*"])
    result.stdout.fnmatch_lines(["digline: said · llm_rubric", f"  {said}"])
    result.stdout.no_fnmatch_line("*Checked here, not present in the reference*")
    assert result.ret == pytest.ExitCode.TESTS_FAILED


def test_a_reviewed_answer_added_and_agreed_with_passes(
    pytester: pytest.Pytester,
) -> None:
    """The control: added after the reference, and the judge agrees with the
    person. Its row passes, so what fails a row is the contradiction, not
    that the case is new."""
    path = added_after_the_reference(pytester, good=True, score=1.0)
    result = pytester.runpytest_subprocess("--digline-suite", str(path), "-v")

    result.stdout.fnmatch_lines(["*said::llm_rubric*PASSED*"])
    assert result.ret == pytest.ExitCode.OK
