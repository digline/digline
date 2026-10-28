"""A verdict without an `assertion_id` is refused, by a name that says so.

It used to default to the score's name. `Score.name` is never empty, so after
construction no verdict could lack one, and the fallback fired only where a
verdict was *built* with `""`. That happens on two routes: a document carrying
`""`, which the reader then read by deriving the identity ADR 0001 says must be
refused; and an assertion that did not pass one, which the driver then recorded
as an unreconciled gap instead of naming the cause. On a projected document the
first route copied a verdict name's token into `assertion_id`, a field that
crosses in clear, and the §8 check let it through. (#263, check 4)
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import pytest

from digline.core import (
    AssertionBase,
    DocumentRefusedError,
    EvaluatorInputs,
    Score,
    UnidentifiedVerdictError,
    Verdict,
    project,
    run_from_json,
    run_to_json,
)
from digline.host import REFUSALS
from digline.run import Case, Response, Suite, execute
from test_projection import Table, promoted


def test_an_empty_assertion_id_is_refused_by_name() -> None:
    with pytest.raises(UnidentifiedVerdictError, match="carries no assertion_id"):
        Verdict(
            score=Score(name="contains", score=1.0),
            threshold=0.5,
            status="pass",
            reason="r",
            assertion_id="",
        )


def test_the_refusal_is_classified() -> None:
    assert UnidentifiedVerdictError in REFUSALS


def _emptied(document: str) -> str:
    raw = json.loads(document)
    raw["results"][0]["verdicts"][0]["assertion_id"] = ""
    return json.dumps(raw)


def test_a_document_carrying_an_empty_identity_is_refused() -> None:
    """Was: read, with the check's name as its identity. Refused as a document
    since ADR 0054 §8, so the store's reader adds the path and the `role`;
    the verdict's own refusal is what it quotes."""
    with pytest.raises(DocumentRefusedError) as refused:
        run_from_json(_emptied(run_to_json(promoted())))
    assert isinstance(refused.value.__cause__, UnidentifiedVerdictError)


def test_a_projected_document_carrying_an_empty_identity_is_refused() -> None:
    """Was: read green, with a verdict name's token in `assertion_id`."""
    with pytest.raises(DocumentRefusedError) as refused:
        run_from_json(_emptied(run_to_json(project(promoted(), Table()))))
    assert isinstance(refused.value.__cause__, UnidentifiedVerdictError)


@dataclass(frozen=True, slots=True)
class Unidentified(AssertionBase):
    """What the protocol permits and `AssertionBase`'s constructors never do: a
    verdict built without the identity."""

    name: str = "unidentified"
    threshold: float = 0.5
    tolerance: float = 0.0

    def __call__(self, inputs: EvaluatorInputs) -> Verdict:
        return Verdict(
            score=Score(name=self.name, score=1.0),
            threshold=self.threshold,
            status="pass",
            reason="r",
            assertion_id="",
        )


def test_an_assertion_that_omits_it_errors_on_its_own_line_naming_why() -> None:
    """Was: an `unreconciled` gap, which named a hole in the record rather than
    the assertion that made it."""
    suite = Suite(
        tenant="acme",
        environment="test",
        name="triage",
        assertions=[Unidentified()],
        cases=[Case(id="c1")],
    )
    run = execute(suite, lambda case: Response(output="ok"), created_at="2026-09-30")
    (verdict,) = run.results[0].verdicts
    assert verdict.status == "error"
    assert verdict.assertion_id == Unidentified().identity
    assert "UnidentifiedVerdictError" in verdict.reason
