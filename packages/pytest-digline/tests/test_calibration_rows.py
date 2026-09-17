"""The calibration case as a pytest row. (ADR 0024 §4.7)

A lost scale is the plugin's unjudged state: ERROR, with the report's sentence.
A calibration case that moved inside its band fails nothing — its only gate is
the band, and the target was never asked for it.

Produced the way `test_states.py` produces every state: by moving what the judge
does and letting the engine decide what that means.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from _cycle import cycle

SUITE = """
import pathlib

from digline.core import Contains, JudgeReply, LlmRubric
from digline.run import Calibration, Case, Response, Suite

HERE = pathlib.Path(__file__).parent


def judge(prompt: str) -> JudgeReply:
    placed = float((HERE / "placed.txt").read_text().strip())
    return JudgeReply(score=placed if "HALF-RIGHT" in prompt else 1.0, reason="looked")


suite = Suite(
    tenant="acme",
    environment="staging",
    name="calibrated",
    assertions=[
        Contains(needle="Acme"),
        LlmRubric(rubric="acceptable?", judge=judge, threshold=0.7, tolerance=0.05),
    ],
    cases=[
        Case(id="alpha"),
        Case(
            id="half",
            calibration=Calibration(
                output="HALF-RIGHT", check="llm_rubric", low=0.3, high=0.7, input=""
            ),
        ),
    ],
    samples=2,
    min_agreement="2/2",
)


def target(case: Case) -> Response:
    return Response(output="Acme, fine", cost_usd=0.001, latency_ms=10.0)
"""


def calibrated(pytester: pytest.Pytester, before: float, after: float) -> Path:
    path = pytester.path / "suite.py"
    path.write_text(SUITE, encoding="utf-8")
    placed = pytester.path / "placed.txt"
    placed.write_text(f"{before}\n", encoding="utf-8")
    cycle(path, pytester.path, promote=True)
    placed.write_text(f"{after}\n", encoding="utf-8")
    cycle(path, pytester.path, promote=False)
    return path


def test_a_lost_scale_is_an_error_with_the_reports_sentence(
    pytester: pytest.Pytester,
) -> None:
    path = calibrated(pytester, 0.5, 1.0)
    result = pytester.runpytest_subprocess("--digline-suite", str(path), "-v")

    outcomes = result.parseoutcomes()
    assert outcomes.get("errors", 0) == 1, outcomes
    assert outcomes.get("failed", 0) == 0, outcomes
    result.stdout.fnmatch_lines(
        [
            "*half::llm_rubric*ERROR*",
            "*The calibration case half scored 1.000000 across 2 samples*",
        ]
    )


def test_movement_inside_the_band_fails_nothing(pytester: pytest.Pytester) -> None:
    """0.6 → 0.35 is beyond tolerance and inside the band. The engine calls the
    delta `regressed`; it is not a check of the system, so no row fails."""
    path = calibrated(pytester, 0.6, 0.35)
    result = pytester.runpytest_subprocess("--digline-suite", str(path), "-v")

    outcomes = result.parseoutcomes()
    assert outcomes.get("failed", 0) == 0, outcomes
    assert outcomes.get("errors", 0) == 0, outcomes
    assert result.ret == pytest.ExitCode.OK
