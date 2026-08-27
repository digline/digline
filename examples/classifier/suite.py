"""What "under control" means for this classifier, declared.

The gate is not "did case 14 pass". Individual cases near the boundary change
their mind between runs and always will; the number that decides a release is
precision over the whole set. The per-case verdicts are how you find out *why*
it moved, once it has.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from digline.core import (
    STRUCTURED_ONLY,
    Accuracy,
    AssertionBase,
    EvaluatorInputs,
    OutputKind,
    Precision,
    Verdict,
)
from digline.run import Case, Response, Suite

import app

CASES = json.loads((Path(__file__).parent / "cases.json").read_text(encoding="utf-8"))

#: The widest the aggregates moved across eight runs of an unchanged
#: classifier: three cases. Measured, not chosen — the README shows the runs.
#:
#: A fraction and not `0.15`, so it still says "three cases" when somebody adds
#: the twenty-first. And three rather than one: one case is what *accuracy*
#: moves by when a single report changes its mind, but precision divides by the
#: eleven it kept, so the same flip moves it by about `1/11`. One tolerance,
#: two denominators — set it from the wider.
THREE_CASES = f"3/{len(CASES)}"


@dataclass(frozen=True, slots=True)
class AgreesWithMark(AssertionBase):
    """The classifier decided what the human decided.

    Binary per sample. With `samples=5` the driver folds the five into
    0, 0.2, … 1.0, so `threshold=0.5` is "the majority agreed" and
    `tolerance=0.4` is "up to two samples changing their mind is noise, three
    is a change". Both measured, not chosen — see the README.
    """

    name: str = "agrees_with_mark"
    threshold: float = 0.5
    tolerance: float = 0.4
    accepts: frozenset[OutputKind] = STRUCTURED_ONLY

    def __call__(self, inputs: EvaluatorInputs) -> Verdict:
        if (err := self._accept(inputs.output)) is not None:
            return err
        # `_accept` has just guaranteed this is structured, but it returns
        # `Verdict | None` rather than a `TypeGuard`, so a type checker still
        # sees the whole `Output` union. The cast says what the line above
        # already proved. (digline friction 30)
        output = cast(Mapping[str, object], inputs.output)
        if (
            not isinstance(inputs.expected, Mapping)
            or "needs_review" not in inputs.expected
        ):
            return self._error("expected must be {'needs_review': bool}")
        decision = output.get("decision")
        if decision not in ("review", "approve"):
            return self._error(f"decision was {decision!r}, not review or approve")
        predicted = decision == "review"
        marked = bool(inputs.expected["needs_review"])
        return self._binary(
            predicted == marked,
            f"classifier said {decision}, the human said "
            f"{'review' if marked else 'approve'}",
        )


def target(case: Case) -> Response:
    """Called five times per case, because that is what `samples=5` means."""
    verdict: dict[str, Any] = app.classify(case.id, dict(case.vars))
    return Response(
        output=verdict,
        input=f"{case.vars['category']} {case.vars['amount_eur']} EUR",
        cost_usd=0.0004,
    )


suite = Suite(
    tenant="northwind",
    environment="staging",
    name="expense-triage",
    assertions=[AgreesWithMark()],
    # Precision: of the reports it sent to a human, how many should have gone.
    # That is the one the finance team feels, because it is their afternoon.
    # Accuracy: counts the correct approvals too, which nobody ever notices.
    # Both thresholds sit where the system measurably is; see the README.
    # Thresholds below the lowest run seen, not where anyone wishes the
    # classifier were: measured 0.667 and 0.800 at worst over eight runs.
    run_assertions=[
        Precision(over="agrees_with_mark", threshold="3/5", tolerance=THREE_CASES),
        Accuracy(over="agrees_with_mark", threshold="7/10", tolerance=THREE_CASES),
    ],
    cases=[
        Case(
            id=case["id"],
            vars=case["vars"],
            expected=case["expected"],
            label=case["label"],
            metadata=case["metadata"],
        )
        for case in CASES
    ],
    samples=5,
    min_agreement="3/5",
)
