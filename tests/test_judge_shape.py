"""A judge of the wrong shape is refused when declared, or named as the judge's.

Measured at `e82dc2b` and again at `f8a88e5` (#423). `LlmRubric(judge='nope')`
exited 0, with an errored verdict on every case, after the target had been
paid for every one. A judge that returned a `dict` errored every case too, and
the reason said *assertion raised AttributeError: 'dict' object has no
attribute 'score'*. The reply was read outside the `try` that catches the
judge, so the driver's catch named the check for the judge's defect.

The first half is the shape check of #420, carried to the one field of a check
that is called after the target: refuse before paying. The second half cannot
be seen before the judge answers, so it stays an errored verdict, with the
judge named in its reason.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from tests._helpers import cli, git, suite_source

from digline.cli import EXIT_USAGE
from digline.core import (
    AssertionShapeError,
    ClaimReply,
    EvaluatorInputs,
    Faithfulness,
    JudgeReply,
    LlmRubric,
)

SUITE = ("--suite", "suite_qa.py")


def rubric(judge: object) -> LlmRubric:
    return LlmRubric(
        rubric="answers?",
        judge=judge,  # pyright: ignore[reportArgumentType]
        threshold=0.7,
        tolerance=0.05,
    )


def faithful(judge: object) -> Faithfulness:
    return Faithfulness(
        judge=judge,  # pyright: ignore[reportArgumentType]
        threshold=0.8,
        tolerance=0.1,
    )


def answering(reply: object) -> Callable[[str], object]:
    """A judge that answers every prompt with `reply`."""

    def judge(prompt: str) -> object:
        return reply

    return judge


INPUTS = EvaluatorInputs(output="Paris.", input="Capital?", context=("Paris.",))


@pytest.mark.parametrize("judge", ["nope", 3, None])
@pytest.mark.parametrize("build", [rubric, faithful], ids=["LlmRubric", "Faithfulness"])
def test_a_judge_that_cannot_be_called_is_refused_when_declared(
    build: object, judge: object
) -> None:
    owner = "LlmRubric" if build is rubric else "Faithfulness"
    with pytest.raises(AssertionShapeError) as refused:
        build(judge)  # pyright: ignore[reportCallIssue]

    assert (
        f"{owner}.judge is of type {type(judge).__name__}, which cannot be called"
        in str(refused.value)
    )
    assert "before anything is paid for" in str(refused.value)


def test_a_rubric_judge_returning_the_wrong_type_is_named_as_the_judges() -> None:
    verdict = rubric(answering({"score": 1.0}))(INPUTS)

    assert verdict.status == "error"
    assert verdict.reason == "the judge returned a value of type dict, not a JudgeReply"


def test_a_claim_judge_returning_the_wrong_type_is_named_as_the_judges() -> None:
    """A `JudgeReply` handed to `Faithfulness` is the wrong reply too: it is the
    other judge protocol's, and it has no counts."""
    verdict = faithful(answering(JudgeReply(score=1.0, reason="ok")))(INPUTS)

    assert verdict.status == "error"
    assert (
        verdict.reason
        == "the judge returned a value of type JudgeReply, not a ClaimReply"
    )


def test_the_right_reply_types_still_grade() -> None:
    """The control: the check refuses a wrong type and nothing else."""
    graded = rubric(answering(JudgeReply(score=0.9, reason="ok")))(INPUTS)
    counted = faithful(answering(ClaimReply(supported=1, total=1, reason="ok")))(INPUTS)

    assert graded.status == "pass"
    assert counted.status == "pass"


def committed(root: Path, source: str) -> Path:
    root.mkdir(exist_ok=True)
    git(root, "init", "-q")
    git(root, "config", "user.email", "test@example.invalid")
    git(root, "config", "user.name", "Test")
    (root / "suite_qa.py").write_text(source, encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "initial")
    return root


def test_a_judge_that_cannot_be_called_exits_64_before_the_target_is_called(
    tmp_path: Path,
) -> None:
    """From the CLI, the way #423 measured it. The shared suite's own judge is
    replaced by a string, and the target counts its calls into a file."""
    calls = tmp_path / "calls"
    source = suite_source(
        preamble=(
            f"import pathlib as _pathlib\n_CALLS = _pathlib.Path({str(calls)!r})\n"
        )
    )
    source = source.replace("judge=_judge", "judge='nope'")
    source = source.replace(
        "def target(case):\n",
        "def target(case):\n"
        "    _CALLS.write_text(_CALLS.read_text() + 'x' if _CALLS.exists() else 'x')\n",
    )
    assert "judge='nope'" in source
    root = committed(tmp_path / "repo", source)

    done = cli(root, "run", *SUITE)

    assert done.returncode == EXIT_USAGE, done.stderr
    assert "LlmRubric.judge is of type str, which cannot be called" in done.stderr
    assert "Traceback" not in done.stderr
    assert not calls.exists()
