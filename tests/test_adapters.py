"""The autoevals adapter, and the one point where interoperability cannot bend.

In autoevals `score is None` means "skip". Here it becomes `error`: a skip
turning green would be a vacuously green assertion in disguise.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from digline.core import EvaluatorInputs, FromAutoevals, score_from_autoevals


@dataclass(frozen=True)
class FakeScore:
    """The shape of `autoevals.Score` — reproduced, not imported: the protocol
    is structural and the core does not take on the dependency."""

    name: str
    score: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict[str, Any])


def fixed_scorer(score: float | None, name: str = "Levenshtein") -> Any:
    def _scorer(output: Any, expected: Any = None, **kwargs: Any) -> FakeScore:
        return FakeScore(name=name, score=score, metadata={"expected": expected})

    return _scorer


def test_it_converts_an_autoevals_score() -> None:
    converted = score_from_autoevals(FakeScore(name="Levenshtein", score=0.75))
    assert converted.name == "Levenshtein"
    assert converted.score == 0.75


def test_a_scorer_that_passes() -> None:
    a = FromAutoevals(scorer=fixed_scorer(0.9), threshold=0.7, tolerance=0.05)
    v = a(EvaluatorInputs(output="Rome", expected="Rome"))
    assert v.status == "pass"
    assert v.score.score == 0.9


def test_a_scorer_that_fails() -> None:
    a = FromAutoevals(scorer=fixed_scorer(0.4), threshold=0.7, tolerance=0.05)
    assert a(EvaluatorInputs(output="Milan", expected="Rome")).status == "fail"


def test_an_autoevals_skip_becomes_an_error_not_a_pass() -> None:
    a = FromAutoevals(scorer=fixed_scorer(None), threshold=0.7, tolerance=0.05)
    v = a(EvaluatorInputs(output="Rome", expected="Rome"))
    assert v.status == "error"
    assert v.passed is False
    assert "skip" in v.reason


def test_a_scorer_that_blows_up_is_an_error_not_a_failure() -> None:
    def broken_scorer(output: Any, expected: Any = None, **kwargs: Any) -> Any:
        raise ValueError("model unreachable")

    a = FromAutoevals(scorer=broken_scorer, threshold=0.7, tolerance=0.05)
    v = a(EvaluatorInputs(output="Rome"))
    assert v.status == "error"
    assert "ValueError" in v.reason


def test_it_preserves_the_scorer_metadata() -> None:
    a = FromAutoevals(scorer=fixed_scorer(0.9), threshold=0.7, tolerance=0.05)
    v = a(EvaluatorInputs(output="Rome", expected="Rome"))
    assert v.score.metadata["expected"] == "Rome"


def test_it_rejects_non_textual_output() -> None:
    a = FromAutoevals(scorer=fixed_scorer(0.9), threshold=0.7, tolerance=0.05)
    assert a(EvaluatorInputs(output={"city": "Rome"})).status == "error"
