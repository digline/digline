"""What kind of error errored a case, beside where (#425).

`CaseResult.error_kind` is `"raised"` or `"shape"`, or `None` where the case did
not error at the target or the mapper, or the document did not record it. It is
digline's own word, so it crosses every boundary a case crosses, a projection
included, where it is class (a) of ADR 0034 §4 and checked for its form.

`cause` says *where*, and it is the journal's; `error_kind` says *of what
kind*, and it is the document's. `"shape"` is the target's alone: the mapper
has no check of what it returns, so a mapper errors a case only by raising.

The 20 -> 21 step writes nothing, and absent is `None`.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import replace
from typing import cast

import pytest

from digline.core import (
    CaseProgress,
    CaseResult,
    Contains,
    Disclosure,
    EvaluatorInputs,
    JudgeReply,
    LlmRubric,
    Run,
    compare,
    project,
    project_served,
    redact,
)
from digline.core.run import (
    SCHEMA_VERSION,
    case_from_dict,
    case_to_dict,
    run_from_dict,
    run_from_json,
    run_to_dict,
)
from digline.report import Locale, render_html, render_run_html
from digline.run import Calibration, Case, Response, Suite, execute
from digline.store.migrate import upgrade_document
from digline.wire import run_document
from test_projection import Table, promoted

CREATED = "2026-01-01T00:00:00+00:00"


def suite(*cases: Case, **extra: object) -> Suite:
    return Suite(
        tenant="acme",
        environment="staging",
        name="qa",
        assertions=[
            Contains(needle="yes", threshold=1.0),
            LlmRubric(
                rubric="right?",
                judge=lambda prompt: JudgeReply(score=1.0, reason="fine"),
                threshold=0.5,
                tolerance=0.0,
            ),
        ],
        cases=list(cases) or [Case(id="c1")],
        **extra,  # pyright: ignore[reportArgumentType]
    )


def answering(case: Case) -> Response:
    return Response(output="yes", cost_usd=0.01)


def raising(case: Case) -> Response:
    raise RuntimeError("the endpoint went away")


def shapeless(case: Case) -> Response:
    return "yes"  # pyright: ignore[reportReturnType]


def raising_mapper(response: Response, case: Case) -> EvaluatorInputs:
    raise KeyError("context")


def cases_of(document: Mapping[str, object]) -> list[dict[str, object]]:
    """A document's cases, typed for a test that reads or edits them."""
    return cast(list[dict[str, object]], document["results"])


def measured(
    declared: Suite, target: object, **extra: object
) -> tuple[Run, dict[str, str]]:
    """The run, and the cause the journal would record for each case."""
    causes: dict[str, str] = {}

    def record(progress: CaseProgress) -> None:
        causes[progress.result.case_id] = progress.cause

    run = execute(
        declared,
        target,  # pyright: ignore[reportArgumentType]
        created_at=CREATED,
        on_case=record,
        **extra,  # pyright: ignore[reportArgumentType]
    )
    return run, causes


# --------------------------------------------------------------------------- #
# The driver: which branch writes which word
# --------------------------------------------------------------------------- #


def test_a_target_that_raised_is_raised_and_its_cause_stays_target() -> None:
    run, causes = measured(suite(), raising)
    assert run.results[0].error_kind == "raised"
    assert causes["c1"] == "target"


def test_a_target_that_returned_the_wrong_shape_is_shape() -> None:
    run, causes = measured(suite(), shapeless)
    assert run.results[0].error_kind == "shape"
    assert causes["c1"] == "target"


def test_a_mapper_that_raised_is_raised() -> None:
    run, causes = measured(suite(), answering, mapper=raising_mapper)
    assert run.results[0].error_kind == "raised"
    assert causes["c1"] == "mapper"


def test_a_calibration_mapper_that_raised_is_raised() -> None:
    calibrating = Case(
        id="half",
        calibration=Calibration(
            output="half right", check="llm_rubric", low=0.3, high=0.7, input=""
        ),
    )
    # Two samples, because a calibration case refuses one (ADR 0024 §4.2).
    declared = suite(calibrating, samples=2, min_agreement="2/2")
    run, causes = measured(declared, answering, mapper=raising_mapper)
    assert run.results[0].error_kind == "raised"
    assert causes["half"] == "mapper"


def test_a_case_that_did_not_error_has_no_kind() -> None:
    run, _ = measured(
        suite(Case(id="c1"), Case(id="off", suspended="paused")), answering
    )
    assert [case.error_kind for case in run.results] == [None, None]


def test_an_assertion_that_errored_gives_its_case_no_kind() -> None:
    """The target answered and was paid; the checks' own errors are on their
    verdicts, and the case did not error at the target or the mapper."""

    def broken(prompt: str) -> JudgeReply:
        raise RuntimeError("judge down")

    declared = replace(
        suite(),
        assertions=[
            LlmRubric(rubric="right?", judge=broken, threshold=0.5, tolerance=0.0)
        ],
    )
    run, causes = measured(declared, answering)
    assert causes["c1"] == "assertion"
    assert run.results[0].error_kind is None


# --------------------------------------------------------------------------- #
# The document
# --------------------------------------------------------------------------- #


def test_the_kind_round_trips_and_is_written_only_when_present() -> None:
    errored = CaseResult(case_id="c1", error_kind="shape")
    assert case_to_dict(errored, redacted=False)["error_kind"] == "shape"
    assert case_from_dict(case_to_dict(errored, redacted=False), redacted=False) == (
        errored
    )
    assert "error_kind" not in case_to_dict(CaseResult(case_id="c2"), redacted=False)


@pytest.mark.parametrize("word", ["timeout", "", None, 3])
def test_a_kind_outside_the_vocabulary_is_refused_when_read(word: object) -> None:
    raw = case_to_dict(CaseResult(case_id="c1", error_kind="raised"), redacted=False)
    raw["error_kind"] = word
    with pytest.raises(ValueError, match="error_kind"):
        case_from_dict(raw, redacted=False)


def test_redaction_keeps_the_kind() -> None:
    run, _ = measured(suite(), shapeless)
    assert redact(run).results[0].error_kind == "shape"


def test_the_wire_carries_the_kind_on_every_case() -> None:
    run, _ = measured(suite(Case(id="c1"), Case(id="c2")), raising)
    cases = cases_of(run_document(run, Disclosure()))
    assert [case["error_kind"] for case in cases] == ["raised", "raised"]
    clean, _ = measured(suite(), answering)
    assert cases_of(run_document(clean, Disclosure()))[0]["error_kind"] is None


# --------------------------------------------------------------------------- #
# The projection: class (a), checked for its form
# --------------------------------------------------------------------------- #


def test_a_projection_carries_the_kind_in_clear() -> None:
    base = promoted()
    errored = replace(base.results[0], error_kind="raised")
    run = replace(base, results=(errored, *base.results[1:]))
    assert project(run, Table()).results[0].error_kind == "raised"


def test_a_projection_refuses_a_kind_that_is_not_diglines_word() -> None:
    projected = project(promoted(), Table())
    named = replace(projected.results[0], error_kind="Rossi")  # pyright: ignore[reportArgumentType]
    with pytest.raises(ValueError, match="error kind"):
        replace(projected, results=(named, *projected.results[1:]))


# --------------------------------------------------------------------------- #
# Schema 21, and the step that writes nothing
# --------------------------------------------------------------------------- #


def test_migrating_a_schema_20_case_writes_no_kind() -> None:
    assert SCHEMA_VERSION == 21
    run, _ = measured(suite(), raising)
    current = run_to_dict(run)
    for case in cases_of(current):
        case.pop("error_kind")
    upgraded = upgrade_document({**current, "schema_version": 20})
    assert upgraded == current
    assert run_from_json(json.dumps(upgraded)).results[0].error_kind is None
    assert run_from_dict(upgraded).results[0].error_kind is None


# --------------------------------------------------------------------------- #
# The word is seen where the reason was removed: the report and the served page
# --------------------------------------------------------------------------- #

_WORDS = {
    "en": {
        "raised": "raised an error",
        "shape": "returned something that is not an answer",
    },
    "it": {
        "raised": "ha sollevato un errore",
        "shape": "ha restituito qualcosa che non è una risposta",
    },
}


def _pages(locale: Locale) -> dict[str, str]:
    """Each surface a reader without the reason meets, for a run whose c1
    raised and whose c2 returned the wrong shape, against a clean baseline."""

    def target(case: Case) -> Response:
        if case.id == "c1":
            raise RuntimeError("Rossi's account is locked")
        if case.id == "c2":
            return "yes"  # pyright: ignore[reportReturnType]
        return Response(output="yes", cost_usd=0.01)

    declared = suite(Case(id="c1"), Case(id="c2"), Case(id="c3"))
    run, _ = measured(declared, target)
    baseline, _ = measured(declared, answering)
    hidden, before = redact(run), redact(baseline)
    served = project_served(run, Table())
    return {
        "report of a run": render_run_html(hidden, locale=locale),
        "report of a comparison": render_html(
            compare(hidden, before), hidden, before, locale=locale, declared=None
        ),
        "served page": render_run_html(served, locale=locale),
    }


@pytest.mark.parametrize("locale", ["en", "it"])
def test_the_word_is_said_where_the_reason_was_removed(locale: Locale) -> None:
    for surface, page in _pages(locale).items():
        for kind, words in _WORDS[locale].items():
            assert words in page, f"{surface} does not say {kind} in {locale}"
        assert "Rossi" not in page, f"{surface} carries the removed reason"


def test_a_case_that_did_not_error_gets_no_word() -> None:
    run, _ = measured(suite(), answering)
    page = render_run_html(redact(run), locale="en")
    for words in _WORDS["en"].values():
        assert words not in page
