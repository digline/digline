"""Interoperability with autoevals.

`Score` deliberately has the same shape as `autoevals.Score`, so adapting costs
a handful of lines and an existing scorer taxonomy becomes compatibility
instead of work to redo.

Nothing here imports `autoevals`: the protocol is structural, so the core does
not acquire a dependency for a compatibility shim.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol, cast

from digline.core.assertions import AssertionBase
from digline.core.types import (
    TEXT_ONLY,
    EvaluatorInputs,
    OutputKind,
    Score,
    Verdict,
)

__all__ = ["AutoevalsScore", "AutoevalsScorer", "FromAutoevals", "score_from_autoevals"]


class AutoevalsScore(Protocol):
    """The shape of `autoevals.Score`, seen structurally."""

    @property
    def name(self) -> str: ...
    @property
    def score(self) -> float | None: ...
    @property
    def metadata(self) -> Mapping[str, object]: ...


class AutoevalsScorer(Protocol):
    """The shape of `autoevals.Scorer.__call__`."""

    def __call__(self, output: Any, expected: Any = None, **kwargs: Any) -> Any: ...


def score_from_autoevals(raw: AutoevalsScore) -> Score:
    return Score(
        name=raw.name,
        score=raw.score,
        metadata=dict(raw.metadata or {}),
    )


@dataclass(frozen=True, slots=True)
class FromAutoevals(AssertionBase):
    """Wraps an autoevals scorer as a digline `Assertion`.

    There is exactly one delicate point, and it is the ADR 0001 constraint: in
    autoevals `score is None` means "skip". Here it becomes **`status="error"`
    with a mandatory reason**, never `pass`. A skip turning green would be a
    vacuously green assertion dressed up as interoperability.

    A legitimate skip — "this assertion does not apply to this case" — remains a
    driver decision: the driver simply does not invoke the assertion.
    """

    scorer: AutoevalsScorer
    threshold: float
    tolerance: float
    name: str = "autoevals"
    accepts: frozenset[OutputKind] = TEXT_ONLY

    def __post_init__(self) -> None:
        if not (0.0 <= self.threshold <= 1.0):
            raise ValueError(f"threshold must be within [0, 1], got {self.threshold}")

    def __call__(self, inputs: EvaluatorInputs) -> Verdict:
        if (err := self._accept(inputs.output)) is not None:
            return err

        try:
            raw = cast(AutoevalsScore, self.scorer(inputs.output, inputs.expected))
        except Exception as exc:  # noqa: BLE001 — a scorer that blows up is `error`, not `fail`
            return self._error(f"the scorer raised {type(exc).__name__}: {exc}")

        converted = score_from_autoevals(raw)
        if converted.score is None:
            return self._error(
                f"scorer '{converted.name}' produced no score "
                "(in autoevals that means 'skip'; here it cannot mean 'pass')"
            )
        return self._graded(
            converted.score,
            f"scorer '{converted.name}': {converted.score:.6f}",
            metadata=converted.metadata,
        )
