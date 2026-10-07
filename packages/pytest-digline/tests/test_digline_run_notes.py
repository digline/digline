"""`--digline-run` says what `digline run` says about the suite. (#396)

Before the first call the CLI names a check whose class declares no `KIND` and
a tolerance that switches its check off. Whoever writes a suite in pytest may
never run the CLI, and is the one both lines are for. Until #396 the plugin
said neither, under a rule against raising its floor for a line on stderr; the
rule was withdrawn on 2026-10-07. (ADR 0024 §6.4)
"""

from __future__ import annotations

import pytest

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
    tenant="acme",
    environment="staging",
    name="noted",
    assertions=[
        Contains(needle="Acme"),
        NoKind(),
        LlmRubric(rubric="ok?", judge=judge, threshold=0.5, tolerance=0.5,
                  name="loose"),
    ],
    cases=[Case(id="alpha")],
)


def target(case):
    return Response(output="Acme", input="who?")
"""


def test_the_notes_follow_the_count_on_stderr(pytester: pytest.Pytester) -> None:
    path = pytester.path / "suite.py"
    path.write_text(NOTED, encoding="utf-8")

    result = pytester.runpytest_subprocess(
        "--digline-suite", str(path), "--digline-run"
    )

    # The order `digline run` prints: the count, the KIND note, each blind
    # tolerance. The session itself ends on the missing baseline, which is not
    # what is under test here.
    result.stderr.fnmatch_lines(
        [
            "digline: tenant 'acme' * = 1 call to the target",
            "digline: no_kind declares no KIND, so the shape reading leaves it out*",
            "digline: tolerance 0.5 on 'loose' (threshold 0.5) covers every movement*",
        ],
        consecutive=True,
    )


def test_a_suite_with_nothing_to_say_says_only_the_count(
    pytester: pytest.Pytester,
) -> None:
    """The control: a note on every run would be a line people learn to skip,
    and would pass the test above."""
    path = pytester.path / "suite.py"
    plain = NOTED.replace("        NoKind(),\n", "").replace(
        "tolerance=0.5", "tolerance=0.05"
    )
    path.write_text(plain, encoding="utf-8")

    result = pytester.runpytest_subprocess(
        "--digline-suite", str(path), "--digline-run"
    )

    text = result.stderr.str()
    assert "= 1 call to the target" in text
    assert "KIND" not in text
    assert "covers every movement" not in text
