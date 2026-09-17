"""Shape: the share of a judged check's raw scores at 0 or 1, in the run and in
the reference — printed, and not yet judged. (ADR 0024 §6, amended in §6.4)

Two halves. `"judged": true` is the one fact the reading needs from the
document, stamped from the check's `KIND`. The reading is the two shares and
their counts, with no threshold and no exit code.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from tests._helpers import cli
from tests._vocabulary import ADVICE, MULTI_RUN, SPECULATION, spoken

from digline.core import (
    TEXT_ONLY,
    AssertionBase,
    CalibrationBand,
    CaseResult,
    Contains,
    EvaluatorInputs,
    FromAutoevals,
    JudgeReply,
    LlmRubric,
    OutputKind,
    Repeated,
    Run,
    Score,
    Verdict,
    compare,
    judged,
    redact,
    run_from_json,
    run_to_json,
)
from digline.report import explain_text, facts, headline, shape
from digline.run import Case, Response, Suite, execute, undeclared_kinds
from digline.wire import EXIT_OK, compare_json, exit_code

CREATED = "2026-01-01T00:00:00+00:00"
LATER = "2026-01-02T00:00:00+00:00"


def rubric(score: float = 1.0) -> LlmRubric:
    return LlmRubric(
        rubric="right?",
        judge=lambda prompt: JudgeReply(score=score, reason=prompt[:1]),
        threshold=0.5,
        tolerance=0.05,
    )


def answering(case: Case) -> Response:
    return Response(output="Rome", input="capital?")


def suite(assertions: Sequence[Any], **extra: Any) -> Suite:
    fields: dict[str, Any] = {
        "tenant": "acme",
        "environment": "dev",
        "name": "qa",
        "assertions": list(assertions),
        "cases": [Case(id="one"), Case(id="two")],
    }
    fields.update(extra)
    return Suite(**fields)


@dataclass(frozen=True, slots=True)
class NoKind(AssertionBase):
    """A third-party check written before KIND: it declares none."""

    name: str = "no_kind"
    threshold: float = 0.5
    tolerance: float = 0.0
    accepts: frozenset[OutputKind] = TEXT_ONLY

    def __call__(self, inputs: EvaluatorInputs) -> Verdict:
        return self._binary(True, "fine")


# --------------------------------------------------------------------------- #
# §6.4 — the key
# --------------------------------------------------------------------------- #


def test_a_judged_verdict_carries_the_key_and_nothing_else_does() -> None:
    run = execute(
        suite([Contains(needle="Rome"), rubric()]), answering, created_at=CREATED
    )
    contains, judged_verdict = run.results[0].verdicts
    assert judged_verdict.judged and not contains.judged
    document = json.loads(run_to_json(run))
    verdicts = document["results"][0]["verdicts"]
    assert verdicts[1]["judged"] is True
    assert "judged" not in verdicts[0]
    assert run_from_json(run_to_json(run)) == run


def test_a_suite_with_no_judged_check_writes_no_new_byte() -> None:
    run = execute(suite([Contains(needle="Rome")]), answering, created_at=CREATED)
    assert "judged" not in run_to_json(run)


def test_the_key_is_read_through_repeated_and_kept_on_an_error() -> None:
    wrapped = Repeated(inner=rubric(), samples=2, min_agreement="2/2")

    def raising(case: Case) -> Response:
        raise TimeoutError("no answer")

    assert (
        execute(suite([wrapped]), answering, created_at=CREATED)
        .results[0]
        .verdicts[0]
        .judged
    )
    errored = (
        execute(suite([rubric()]), raising, created_at=CREATED).results[0].verdicts[0]
    )
    assert errored.status == "error" and errored.judged


def test_redaction_keeps_the_key() -> None:
    run = execute(suite([rubric()]), answering, created_at=CREATED)
    assert redact(run).results[0].verdicts[0].judged


def test_the_key_moves_no_comparison() -> None:
    """A baseline written before schema 12 has no key; the run has one. Nothing
    pairs differently and nothing moves. (ADR 0024 §9)"""
    run = execute(suite([rubric()]), answering, created_at=LATER)
    document = json.loads(run_to_json(run))
    for case in document["results"]:
        for verdict in case["verdicts"]:
            verdict.pop("judged", None)
    older = run_from_json(json.dumps(document))
    comparison = compare(run, older)
    assert {d.outcome for d in comparison.deltas} == {"unchanged"}


# --------------------------------------------------------------------------- #
# §6.1 amended — undeclared is announced, and the known hole is pinned
# --------------------------------------------------------------------------- #


def test_a_class_with_no_kind_is_named_and_not_stamped() -> None:
    checks = [
        NoKind(),
        rubric(),
        Repeated(inner=NoKind(), samples=2, min_agreement="2/2", name="wrapped"),
    ]
    assert undeclared_kinds(suite(checks)) == ("no_kind", "wrapped")
    run = execute(suite(checks), answering, created_at=CREATED)
    assert not run.results[0].verdicts[0].judged
    assert undeclared_kinds(suite([rubric(), Contains(needle="x")])) == ()


def test_from_autoevals_is_the_known_hole() -> None:
    """Pinned so that closing it is a decision someone makes, not a side effect:
    an autoevals scorer that calls a model is neither judged nor announced, so
    the shape reading cannot see it. (ADR 0024 §6.4)"""

    def scorer(output: Any, expected: Any = None, **kwargs: Any) -> Any:
        return None

    adapter = FromAutoevals(scorer=scorer, threshold=0.5, tolerance=0.0)
    assert not judged(adapter)
    assert undeclared_kinds(suite([adapter])) == ()


# --------------------------------------------------------------------------- #
# §6.2 — what is read
# --------------------------------------------------------------------------- #


def verdict(
    scores: Sequence[float],
    *,
    name: str = "llm_rubric",
    is_judged: bool = True,
    claims: float | None = None,
    status: str | None = None,
) -> Verdict:
    mean = round(sum(scores) / len(scores), 6)
    metadata: dict[str, object] = {} if claims is None else {"claims_total": claims}
    sampled = len(scores) > 1
    if status == "error":
        return Verdict(
            score=Score(name=name, score=None),
            threshold=0.5,
            status="error",
            reason="r",
            assertion_id=f"id-{name}",
            judged=is_judged,
        )
    return Verdict(
        score=Score(
            name=name,
            score=mean,
            metadata=metadata,
            samples=tuple(scores) if sampled else (),
            sample_min=min(scores) if sampled else None,
            sample_max=max(scores) if sampled else None,
        ),
        threshold=0.5,
        status="pass" if mean >= 0.5 else "fail",
        reason="r",
        assertion_id=f"id-{name}",
        judged=is_judged,
    )


def run_of(*cases: CaseResult, created_at: str = LATER) -> Run:
    return Run(
        tenant="acme",
        environment="dev",
        suite="qa",
        config_hash="h",
        created_at=created_at,
        results=cases,
    )


def test_raw_samples_are_read_never_the_folded_mean() -> None:
    now = run_of(CaseResult("one", (verdict((1.0, 0.0, 1.0, 1.0, 0.0)),)))
    before = run_of(
        CaseResult("one", (verdict((0.4, 0.6, 1.0, 0.5, 0.5)),)), created_at=CREATED
    )
    [item] = shape(compare(now, before))
    assert (item.run.extremes, item.run.scores) == (5, 5)
    assert item.reference is not None
    assert (item.reference.extremes, item.reference.scores) == (1, 5)


def test_a_binary_check_that_is_not_judged_is_never_read() -> None:
    """At samples=5 its folded scores are 0.2 … 0.8 and look graded; it is
    deterministic, so shape does not read it at all."""
    now = run_of(
        CaseResult(
            "one", (verdict((1.0, 0.0, 1.0, 0.0, 1.0), name="agrees", is_judged=False),)
        )
    )
    assert shape(compare(now, now)) == ()


def test_canary_calibration_and_errored_verdicts_are_left_out() -> None:
    band = CalibrationBand("llm_rubric", 0.3, 0.7)
    now = run_of(
        CaseResult("one", (verdict((0.5,)),)),
        CaseResult("probe", (verdict((1.0,)),), canary=True),
        CaseResult("half", (verdict((1.0, 1.0)),), calibration=band),
        CaseResult("broken", (verdict((0.0,), status="error"),)),
    )
    [item] = shape(compare(now, now))
    assert (item.run.extremes, item.run.scores) == (0, 1)


def test_single_claim_faithfulness_is_left_out_and_counted() -> None:
    now = run_of(
        CaseResult("exact", (verdict((1.0,), name="faithfulness", claims=1),)),
        CaseResult("mean", (verdict((1.0, 0.0), name="faithfulness", claims=1.5),)),
        CaseResult("read", (verdict((1.0, 0.5), name="faithfulness", claims=2.0),)),
        CaseResult("plain", (verdict((0.5,), name="faithfulness", claims=3),)),
    )
    [item] = shape(compare(now, now))
    assert item.run.single_claim == 2
    assert item.run.claims_unrecorded == 1
    assert (item.run.extremes, item.run.scores) == (1, 3)


def test_a_reference_written_before_twelve_has_nothing_to_set_beside() -> None:
    now = run_of(CaseResult("one", (verdict((1.0,)),)))
    before = run_of(
        CaseResult("one", (verdict((1.0,), is_judged=False),)), created_at=CREATED
    )
    [item] = shape(compare(now, before))
    assert item.reference is None
    line = explain_text(facts(now, compare(now, before)), locale="en")
    assert any("the reference records no judged score" in ln for ln in line)


# --------------------------------------------------------------------------- #
# §6.3 — where it goes, and what it never does
# --------------------------------------------------------------------------- #


def collapsed() -> tuple[Run, Run]:
    now = run_of(*(CaseResult(f"c{i}", (verdict((1.0,)),)) for i in range(4)))
    before = run_of(
        *(CaseResult(f"c{i}", (verdict((0.6,)),)) for i in range(3)),
        CaseResult("c3", (verdict((1.0,)),)),
        created_at=CREATED,
    )
    return now, before


@pytest.mark.parametrize("locale", ["en", "it"])
def test_the_reading_prints_both_shares_and_no_verdict_on_them(locale: str) -> None:
    now, before = collapsed()
    comparison = compare(now, before)
    lines = explain_text(facts(now, comparison), locale=locale)  # type: ignore[arg-type]
    [line] = [ln for ln in lines if ln.startswith("llm_rubric:")]
    assert "100.0%" in line and "25.0%" in line and "4" in line
    assert not spoken(ADVICE, line)
    assert not spoken(SPECULATION, line)
    assert not spoken(MULTI_RUN, line)
    assert "more" not in line.lower()


def test_it_is_never_in_the_headline_and_never_an_exit_code() -> None:
    now, before = collapsed()
    comparison = compare(now, before)
    head = headline(comparison, now, before, locale="en")
    assert "0 or 1" not in head.sentence
    worse = sum(1 for d in comparison.deltas if d.outcome == "regressed")
    assert worse == 0
    assert exit_code(head) == EXIT_OK


def test_the_wire_carries_counts_under_full_only() -> None:
    now, before = collapsed()
    comparison = compare(now, before)
    head = headline(comparison, now, before, locale="en")
    assert "shape" not in compare_json(comparison, head, full=False)
    [item] = compare_json(comparison, head, full=True)["shape"]  # type: ignore[misc]
    assert item == {
        "check": "llm_rubric",
        "assertion_id": "id-llm_rubric",
        "run": {"extremes": 4, "scores": 4, "single_claim": 0, "claims_unrecorded": 0},
        "reference": {
            "extremes": 1,
            "scores": 4,
            "single_claim": 0,
            "claims_unrecorded": 0,
        },
    }


def test_explain_json_carries_the_numbers_only_on_its_own_facts() -> None:
    from digline.wire import explain_json

    now, before = collapsed()
    payload = explain_json(
        facts(now, compare(now, before)), scope="comparison", exit_code=0
    )
    kinds = {f["kind"]: f for f in payload["facts"]}  # type: ignore[union-attr]
    assert kinds["shape"]["shape"]["run"]["extremes"] == 4
    assert "shape" not in kinds["cases"]


# --------------------------------------------------------------------------- #
# End to end — the announcement
# --------------------------------------------------------------------------- #


SUITE_PY = """
from dataclasses import dataclass

from digline.core import AssertionBase, Contains, TEXT_ONLY
from digline.run import Case, Response, Suite


@dataclass(frozen=True, slots=True)
class AgreesWithMark(AssertionBase):
    name: str = "agrees_with_mark"
    threshold: float = 0.5
    tolerance: float = 0.0
    accepts: frozenset = TEXT_ONLY

    def __call__(self, inputs):
        return self._binary(True, "agrees")


suite = Suite(
    tenant="acme-bank",
    environment="staging",
    name="announced",
    assertions=[Contains(needle="Rome"), AgreesWithMark()],
    cases=[Case(id="one")],
)


def target(case):
    return Response(output="Rome", input="capital?")
"""


def test_digline_run_names_a_check_that_declares_no_kind(repo: Path) -> None:
    (repo / "suite_announced.py").write_text(SUITE_PY, encoding="utf-8")
    done = cli(repo, "run", "--suite", "suite_announced.py")
    assert done.returncode == 0, done.stderr
    assert (
        "digline: agrees_with_mark declares no KIND, so the shape reading leaves it out"
        in done.stderr
    )

    quiet = cli(repo, "run", "--suite", "suite_qa.py")
    assert "declare" not in quiet.stderr
