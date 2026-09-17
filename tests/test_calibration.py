"""The calibration case: a fixed answer, a declared band, and exit 2 when the
judge places it outside.

The shape is the canary's (ADR 0016 §2) with the differences ADR 0024 §4 names,
so this file follows `test_canary.py`'s order: the declaration and what it
refuses, the driver, every denominator, what fires, the sentence and the wire.
"""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tarfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest
from tests._helpers import cli
from tests._vocabulary import ADVICE, SPECULATION, spoken

from digline.core import (
    JUDGE_OUTPUT_LABEL,
    NOTHING_EXTRA,
    Accuracy,
    CalibrationBand,
    CaseResult,
    ClaimReply,
    Contains,
    CostBudget,
    EvaluatorInputs,
    Faithfulness,
    JudgeReply,
    LatencyBudget,
    LlmRubric,
    Repeated,
    Run,
    Score,
    ToolsCalled,
    Verdict,
    compare,
    redact,
    run_from_json,
    run_to_json,
    scale_lost,
)
from digline.core.run import SCHEMA_VERSION, run_to_dict
from digline.report import (
    explain_text,
    facts,
    headline,
    render_html,
    render_run_html,
    run_tally,
)
from digline.run import (
    Calibration,
    Case,
    Response,
    Suite,
    default_mapper,
    execute,
    planned_calls,
    rejudge,
)
from digline.store import FileResultStore, UncalibratedRunError
from digline.store.migrate import upgrade_document
from digline.targets import CompletionResult, ModelPrice, Pricing, ScoreJudge, Usage
from digline.wire import (
    EXIT_OK,
    EXIT_UNJUDGED,
    EXIT_WORSE,
    compare_json,
    exit_code,
    explain_json,
    run_document,
)

CREATED = "2026-01-01T00:00:00+00:00"
LATER = "2026-01-02T00:00:00+00:00"

#: The answer the author knows to be half right. Shouted so a fake judge can
#: find it in the composed prompt without colliding with a rubric.
HALF = "HALF-RIGHT: refunds take 30 days and need no receipt."


def judge_scoring(score: float) -> Any:
    """A judge that places the calibration answer at `score` and every real
    answer at 1.0, and remembers what it was shown."""
    seen: list[str] = []

    def judge(prompt: str) -> JudgeReply:
        seen.append(prompt)
        return JudgeReply(score=score if "HALF-RIGHT" in prompt else 1.0, reason="r")

    judge.seen = seen  # type: ignore[attr-defined]
    return judge


def rubric(score: float = 0.5) -> LlmRubric:
    return LlmRubric(
        rubric="is it right?",
        judge=judge_scoring(score),
        threshold=0.7,
        tolerance=0.05,
    )


def calibration(**overrides: Any) -> Calibration:
    fields: dict[str, Any] = {
        "output": HALF,
        "check": "llm_rubric",
        "low": 0.3,
        "high": 0.7,
        "input": "How do refunds work?",
    }
    fields.update(overrides)
    return Calibration(**fields)


def suite(
    *,
    score: float = 0.5,
    assertions: Sequence[Any] | None = None,
    cases: Sequence[Case] | None = None,
    samples: int = 2,
    **extra: Any,
) -> Suite:
    return Suite(
        tenant="acme",
        environment="dev",
        name="qa",
        assertions=list(assertions) if assertions is not None else [rubric(score)],
        cases=list(cases)
        if cases is not None
        else [Case(id="one"), Case(id="half", calibration=calibration())],
        samples=samples,
        min_agreement=f"{samples}/{samples}" if samples > 1 else None,
        **extra,
    )


class Counting:
    """A target that counts how often it is asked, per case."""

    def __init__(self) -> None:
        self.asked: list[str] = []

    def __call__(self, case: Case) -> Response:
        self.asked.append(case.id)
        return Response(output="Rome", input="q", cost_usd=0.01, latency_ms=10.0)


# --------------------------------------------------------------------------- #
# §4.2 — the declaration, and what it refuses
# --------------------------------------------------------------------------- #


def test_the_declaration_that_succeeds() -> None:
    """Beside every refusal below, so each refusal is visibly narrow."""
    built = suite()
    assert built.cases[1].calibration is not None


@pytest.mark.parametrize(
    ("low", "high"),
    [(0.0, 0.7), (0.3, 1.0), (0.0, 1.0), (0.8, 0.2), (-0.1, 0.5)],
    ids=["touches-0", "touches-1", "both", "inverted", "below-0"],
)
def test_a_band_that_contains_an_extreme_is_refused(low: float, high: float) -> None:
    """Fixed decision 3, applied to the instrument: an extreme in band cannot
    detect the extreme."""
    with pytest.raises(ValueError, match="strictly between 0"):
        calibration(low=low, high=high)


def test_the_band_is_compared_at_storage_precision() -> None:
    """A low that rounds to 0 at storage precision is 0 by the time the document
    holds it, so it is refused as 0."""
    with pytest.raises(ValueError, match="strictly between 0"):
        CalibrationBand("llm_rubric", 0.0000001, 0.5)
    assert CalibrationBand("llm_rubric", 0.5, 0.5).holds(0.5000001)


def test_a_calibration_case_is_not_a_canary() -> None:
    with pytest.raises(ValueError, match="both a canary and a calibration"):
        Case(id="half", canary=True, calibration=calibration())


def test_a_calibration_case_declares_no_group() -> None:
    with pytest.raises(ValueError, match="counted in no aggregate"):
        Case(id="half", group="refunds", calibration=calibration())


def test_the_check_must_be_declared() -> None:
    with pytest.raises(ValueError, match="no assertion in suite"):
        suite(cases=[Case(id="half", calibration=calibration(check="faithfulness"))])


def test_the_check_must_be_unambiguous() -> None:
    with pytest.raises(ValueError, match="share"):
        suite(assertions=[rubric(), rubric()])


def test_a_deterministic_check_is_refused() -> None:
    """A calibration of a deterministic check is a calibration of arithmetic."""
    with pytest.raises(ValueError, match="not a judged check"):
        suite(
            assertions=[rubric(), Contains(needle="Rome")],
            cases=[Case(id="half", calibration=calibration(check="contains"))],
        )


def test_a_judged_check_inside_repeated_is_read_through_it() -> None:
    """`Repeated` declares `wrapper`: its nature is the thing it wraps."""
    wrapped = Repeated(inner=rubric(), samples=2, min_agreement="2/2", name="rubric")
    suite(
        assertions=[wrapped],
        cases=[Case(id="half", calibration=calibration(check="rubric"))],
    )


def test_a_suite_with_a_calibration_case_has_to_sample() -> None:
    with pytest.raises(ValueError, match="one draw of a noisy instrument"):
        suite(samples=1)
    # Scoped: without one, a suite still runs at one sample.
    suite(samples=1, cases=[Case(id="one")])


@pytest.mark.parametrize("check", ["llm_rubric", "faithfulness"])
def test_a_judge_that_is_shown_the_question_needs_one_declared(check: str) -> None:
    """Graded blind, the control would fail for a reason unrelated to what it
    controls. `""` is a declaration — the real cases have no question either —
    and `None` is not."""
    judged = [
        rubric(),
        Faithfulness(
            judge=lambda prompt: ClaimReply(supported=1, total=2, reason=prompt[:1]),
            threshold=0.5,
            tolerance=0.05,
        ),
    ]
    with pytest.raises(ValueError, match="declares no input"):
        suite(
            assertions=judged,
            cases=[
                Case(
                    id="half",
                    context=("refunds take 30 days",),
                    calibration=calibration(check=check, input=None),
                )
            ],
        )
    suite(
        assertions=judged,
        cases=[
            Case(
                id="half",
                context=("refunds take 30 days",),
                calibration=calibration(check=check, input=""),
            )
        ],
    )


def test_an_empty_answer_is_refused() -> None:
    with pytest.raises(ValueError, match="empty output"):
        calibration(output="")


def test_a_calibration_case_needs_no_label() -> None:
    Suite(
        tenant="acme",
        environment="dev",
        name="qa",
        assertions=[rubric()],
        cases=[
            Case(id="one", label="positive"),
            Case(id="half", calibration=calibration()),
        ],
        samples=2,
        min_agreement="2/2",
        run_assertions=[Accuracy(over="llm_rubric", threshold="1/2", tolerance=0.0)],
    )


# --------------------------------------------------------------------------- #
# §4.1, §4.3 — the target is not called, and only the named check runs
# --------------------------------------------------------------------------- #


def test_the_target_is_never_asked_for_it() -> None:
    target = Counting()
    run = execute(suite(), target, created_at=CREATED)
    assert target.asked == ["one", "one"]
    assert run.results[1].calibration == CalibrationBand("llm_rubric", 0.3, 0.7)


def test_only_the_named_check_runs() -> None:
    """A budget and a trajectory check would each error on a call nobody made,
    and every run of such a suite would exit 2 for nothing."""
    checks = [
        rubric(),
        CostBudget(max_usd=0.10, tolerance=0.0),
        LatencyBudget(max_ms=1000.0, tolerance=0.0),
        ToolsCalled(expected=("lookup",)),
    ]
    run = execute(suite(assertions=checks), Counting(), created_at=CREATED)
    half = run.results[1]
    assert [v.score.name for v in half.verdicts] == ["llm_rubric"]
    assert all(v.status != "error" for v in half.verdicts)


def test_the_call_plan_bills_the_judge_and_not_the_target() -> None:
    plan = planned_calls(suite())
    assert plan.cases == 1
    assert plan.calibration == 1
    assert plan.target_calls == 2
    assert "1 calibration case judged 2 times, with no call to the target" in (
        plan.sentence()
    )
    # And nothing at all where there is none.
    assert "calibration" not in planned_calls(suite(cases=[Case(id="one")])).sentence()


def test_the_mapper_is_on_the_path_and_sees_the_declared_answer() -> None:
    seen: list[Response] = []

    def mapper(response: Response, case: Case) -> EvaluatorInputs:
        seen.append(response)
        return default_mapper(response, case)

    execute(suite(), Counting(), created_at=CREATED, mapper=mapper)
    declared = [r for r in seen if r.output == HALF]
    assert len(declared) == 2
    assert declared[0].input == "How do refunds work?"
    assert declared[0].cost_usd is None and declared[0].latency_ms is None


def test_the_judge_is_shown_the_declared_question() -> None:
    check = rubric()
    execute(suite(assertions=[check]), Counting(), created_at=CREATED)
    prompts = [p for p in check.judge.seen if "HALF-RIGHT" in p]  # type: ignore[attr-defined]
    assert prompts and "How do refunds work?" in prompts[0]


def test_a_mapper_that_raises_errors_the_named_check_only() -> None:
    def mapper(response: Response, case: Case) -> EvaluatorInputs:
        if response.output == HALF:
            raise KeyError("retrieved")
        return default_mapper(response, case)

    checks = [rubric(), CostBudget(max_usd=0.10, tolerance=0.0)]
    run = execute(
        suite(assertions=checks), Counting(), created_at=CREATED, mapper=mapper
    )
    half = run.results[1]
    assert [(v.score.name, v.status) for v in half.verdicts] == [
        ("llm_rubric", "error")
    ]
    # Unjudged, and so not a lost scale: two facts, never counted as one.
    assert scale_lost(run) == ()


def test_the_answer_is_never_written_recorded_responses_or_not() -> None:
    """Payload, and already in the committed cases file."""
    run = execute(suite(record_responses=True), Counting(), created_at=CREATED)
    assert run.results[1].responses == ()
    document = run_to_json(run)
    assert "HALF-RIGHT" not in document
    assert "How do refunds work?" not in document


# --------------------------------------------------------------------------- #
# §4.4 — excluded from the metrics, counted where what happened is reported
# --------------------------------------------------------------------------- #


def test_no_aggregate_counts_it_and_the_exclusion_is_stated() -> None:
    labelled = Suite(
        tenant="acme",
        environment="dev",
        name="qa",
        assertions=[rubric(score=0.0)],
        cases=[
            Case(id="one", label="positive"),
            Case(id="half", calibration=calibration()),
        ],
        samples=2,
        min_agreement="2/2",
        run_assertions=[Accuracy(over="llm_rubric", threshold="1/2", tolerance=0.0)],
    )
    run = execute(labelled, Counting(), created_at=CREATED)
    accuracy = run.aggregate[0]
    assert accuracy.score.score == 1.0
    assert accuracy.score.metadata["considered"] == 1
    assert accuracy.score.metadata["calibration_excluded"] == 1
    assert accuracy.score.metadata["suspended_excluded"] == 0
    assert "1 calibration" in accuracy.reason
    # The per-sample interval survives it, which is the canary's §4 trap.
    assert accuracy.score.sampled


def test_the_exclusion_key_is_silent_at_zero() -> None:
    """Written always, it would add a key to every aggregate verdict in every
    committed baseline."""
    labelled = Suite(
        tenant="acme",
        environment="dev",
        name="qa",
        assertions=[rubric()],
        cases=[Case(id="one", label="positive")],
        run_assertions=[Accuracy(over="llm_rubric", threshold="1/2", tolerance=0.0)],
    )
    run = execute(labelled, Counting(), created_at=CREATED)
    assert "calibration_excluded" not in run.aggregate[0].score.metadata
    assert "calibration" not in run.aggregate[0].reason


def test_it_is_in_the_run_tally() -> None:
    run = execute(suite(), Counting(), created_at=CREATED)
    assert run_tally(run).cases == 2


# --------------------------------------------------------------------------- #
# §4.5 — when it fires
# --------------------------------------------------------------------------- #


def band_run(
    scores: Sequence[float],
    *,
    created_at: str = LATER,
    extra: Sequence[CaseResult] = (),
) -> Run:
    mean = sum(scores) / len(scores)
    verdict = Verdict(
        score=Score(
            name="llm_rubric",
            score=mean,
            samples=tuple(scores),
            sample_min=min(scores),
            sample_max=max(scores),
        ),
        threshold=0.7,
        status="pass" if mean >= 0.7 else "fail",
        reason="judged",
        assertion_id="id-rubric",
    )
    return Run(
        tenant="acme",
        environment="dev",
        suite="qa",
        config_hash="h",
        created_at=created_at,
        results=(
            *extra,
            CaseResult(
                "half",
                (verdict,),
                calibration=CalibrationBand("llm_rubric", 0.3, 0.7),
            ),
        ),
    )


@pytest.mark.parametrize(
    ("scores", "fires"),
    [
        ((1.0, 1.0, 1.0), True),
        ((0.0, 0.0), True),
        ((0.8, 0.8), True),
        ((0.3, 0.3), False),
        ((0.7, 0.7), False),
        ((0.5, 0.5), False),
    ],
    ids=["above-at-1", "below-at-0", "just-above", "on-low", "on-high", "middle"],
)
def test_it_fires_outside_the_band_in_both_directions(
    scores: tuple[float, ...], fires: bool
) -> None:
    run = band_run(scores)
    assert bool(scale_lost(run)) is fires


def test_an_errored_verdict_is_unjudged_and_not_a_lost_scale() -> None:
    errored = Run(
        tenant="acme",
        environment="dev",
        suite="qa",
        config_hash="h",
        created_at=LATER,
        results=(
            CaseResult(
                "half",
                (
                    Verdict(
                        score=Score(name="llm_rubric", score=None),
                        threshold=0.7,
                        status="error",
                        reason="the judge raised",
                        assertion_id="id-rubric",
                    ),
                ),
                calibration=CalibrationBand("llm_rubric", 0.3, 0.7),
            ),
        ),
    )
    assert scale_lost(errored) == ()


def test_a_run_with_no_calibration_case_says_nothing_about_one() -> None:
    run = execute(suite(cases=[Case(id="one")]), Counting(), created_at=CREATED)
    assert scale_lost(run) == ()
    assert "calibration" not in run_to_json(run)
    head = headline(compare(run, run), run, run, locale="en")
    assert not head.scale_lost
    assert "calibration" not in head.sentence
    assert "calibration" not in render_run_html(run, locale="en")
    assert "calibration" not in render_html(compare(run, run), run, run, locale="en")
    assert "calibration" not in [getattr(f, "kind", None) for f in facts(run)]


def test_it_needs_no_reference() -> None:
    """It compares a score with a declared band, not with a past."""
    run = execute(suite(score=1.0), Counting(), created_at=CREATED)
    kinds = [getattr(f, "kind", None) for f in facts(run)]
    assert kinds[0] == "calibration"
    assert "outside its declared band" in render_run_html(run, locale="en")


# --------------------------------------------------------------------------- #
# §4.4 amended — a calibration delta is not a verdict about the system
# --------------------------------------------------------------------------- #


def test_movement_inside_the_band_is_not_a_regression() -> None:
    """0.60 → 0.35 is beyond tolerance and outside the reference's interval,
    and still inside the band: the target was never asked, so no check of the
    system got worse. (ADR 0024 §4.4, amended 2026-09-17)"""
    baseline = band_run((0.6, 0.6), created_at=CREATED)
    run = band_run((0.35, 0.35))
    comparison = compare(run, baseline)
    [delta] = comparison.deltas
    assert delta.outcome == "regressed"
    assert delta.calibration

    head = headline(comparison, run, baseline, locale="en")
    assert not head.worse
    assert head.counts["regressed"] == 0
    assert exit_code(head) == EXIT_OK

    payload = compare_json(comparison, head, full=True)
    assert payload["counts"]["regressed"] == 0  # type: ignore[index]
    rows = payload["deltas"]
    assert isinstance(rows, list)
    assert rows[0]["calibration"] is True  # type: ignore[index]
    assert rows[0]["outcome"] == "regressed"  # type: ignore[index]

    document = render_html(comparison, run, baseline, locale="en")
    worse = document.split("What got worse")[1].split("</details>")[0]
    assert "half" not in worse
    assert "What got worse (0)" in document


# --------------------------------------------------------------------------- #
# §4.5 — exit 2, and precedence
# --------------------------------------------------------------------------- #


def regressed_beside(run: Run) -> tuple[Run, Run]:
    def one(score: float) -> CaseResult:
        return CaseResult(
            "one",
            (
                Verdict(
                    score=Score(name="contains", score=score),
                    threshold=0.5,
                    status="pass" if score >= 0.5 else "fail",
                    reason="r",
                    assertion_id="id-contains",
                ),
            ),
        )

    now = band_run((1.0, 1.0), extra=(one(0.0),))
    before = band_run((0.5, 0.5), created_at=CREATED, extra=(one(1.0),))
    return now, before


def test_a_lost_scale_alone_exits_two() -> None:
    baseline = band_run((0.5, 0.5), created_at=CREATED)
    run = band_run((1.0, 1.0))
    head = headline(compare(run, baseline), run, baseline, locale="en")
    assert head.scale_lost
    assert not head.worse
    assert exit_code(head) == EXIT_UNJUDGED


def test_a_regression_still_returns_one_and_the_calibration_clause_leads() -> None:
    run, baseline = regressed_beside(band_run((1.0,)))
    head = headline(compare(run, baseline), run, baseline, locale="en")
    assert head.worse and head.scale_lost
    assert exit_code(head) == EXIT_WORSE
    assert head.sentence.startswith("The calibration case half scored 1.000000")
    assert head.sentence.index("calibration") < head.sentence.index("got worse")


@pytest.mark.parametrize("locale", ["en", "it"])
def test_the_clause_exists_in_both_locales_and_names_the_samples(locale: str) -> None:
    baseline = band_run((0.5, 0.5), created_at=CREATED)
    run = band_run((1.0, 1.0, 1.0))
    head = headline(compare(run, baseline), run, baseline, locale=locale)  # type: ignore[arg-type]
    assert "half" in head.sentence
    assert "1.000000, 1.000000, 1.000000" in head.sentence
    assert "0.300000–0.700000" in head.sentence


@pytest.mark.parametrize("locale", ["en", "it"])
def test_nothing_it_says_is_a_guess_or_advice(locale: str) -> None:
    """*Likely* is the canary's word; here the band was declared and the score
    observed. And no advice word, under ADR 0012 §5's gate."""
    baseline = band_run((0.5, 0.5), created_at=CREATED)
    run = band_run((1.0, 1.0))
    comparison = compare(run, baseline)
    head = headline(comparison, run, baseline, locale=locale)  # type: ignore[arg-type]
    reading = " ".join(explain_text(facts(run, comparison), locale=locale))  # type: ignore[arg-type]
    clause = head.sentence.split(":")[0] + reading
    assert not spoken(SPECULATION, clause)
    assert not spoken(ADVICE, clause)


def test_the_reading_puts_it_first_before_a_moved_judge() -> None:
    baseline = band_run((0.5, 0.5), created_at=CREATED)
    run = band_run((1.0, 1.0))
    kinds = [getattr(f, "kind", None) for f in facts(run, compare(run, baseline))]
    assert kinds[0] == "calibration"


def test_the_wire_carries_the_fact() -> None:
    baseline = band_run((0.5, 0.5), created_at=CREATED)
    run = band_run((1.0, 1.0))
    comparison = compare(run, baseline)
    payload = compare_json(
        comparison, headline(comparison, run, baseline, locale="en"), full=False
    )
    assert payload["scale_lost"] is True
    assert payload["exit_code"] == EXIT_UNJUDGED


# --------------------------------------------------------------------------- #
# §4.5 — not promotable; §4.7 — a replay re-judges it from its own answer
# --------------------------------------------------------------------------- #


def test_a_run_whose_scale_was_lost_is_not_promotable(tmp_path: Path) -> None:
    store = FileResultStore(str(tmp_path))
    declared = suite(score=1.0)
    run = execute(declared, Counting(), created_at=CREATED)
    ref = store.write_run(run)
    with pytest.raises(UncalibratedRunError, match="calibration case"):
        store.promote_baseline(ref, declared.config_hash(), promoted_at=LATER)

    held = execute(suite(score=0.5), Counting(), created_at=LATER)
    promoted = store.promote_baseline(
        store.write_run(held), declared.config_hash(), promoted_at=LATER
    )
    assert promoted.results[1].calibration is not None


def test_a_replay_rejudges_it_from_the_declaration(tmp_path: Path) -> None:
    """The source recorded no answer for it — none is ever recorded — and the
    replay does not refuse: the case carries its own."""
    declared = suite(score=0.5, record_responses=True)
    source = execute(declared, Counting(), created_at=CREATED)
    assert source.results[1].responses == ()
    assert source.results[0].responses

    collapsed = suite(score=1.0, record_responses=True)
    replayed = rejudge(collapsed, source, key="k", created_at=LATER)
    assert replayed.rejudged_from == "k"
    assert scale_lost(replayed)


# --------------------------------------------------------------------------- #
# §9 — the document
# --------------------------------------------------------------------------- #


def test_the_band_round_trips_and_is_absent_when_unset() -> None:
    run = execute(suite(), Counting(), created_at=CREATED)
    document = json.loads(run_to_json(run))
    assert "calibration" not in document["results"][0]
    assert document["results"][1]["calibration"] == {
        "check": "llm_rubric",
        "low": 0.3,
        "high": 0.7,
    }
    assert run_from_json(run_to_json(run)) == run


def test_redaction_keeps_the_band() -> None:
    """A name and two numbers, and a redacted document that lost them would
    report an exit code its own contents could not account for."""
    run = execute(suite(score=1.0), Counting(), created_at=CREATED)
    hidden = redact(run)
    assert hidden.results[1].calibration == run.results[1].calibration
    assert scale_lost(hidden)


def test_the_migration_to_twelve_writes_nothing() -> None:
    run = execute(suite(cases=[Case(id="one")]), Counting(), created_at=CREATED)
    current = run_to_dict(run)
    at_eleven = {**current, "schema_version": 11}
    # Through 12 and on to 13, whose step writes nothing either (ADR 0018 §1,
    # amended 2026-09-17): what 11 -> 12 adds is still nothing.
    assert SCHEMA_VERSION == 13
    assert upgrade_document(at_eleven) == current


def test_a_suite_without_one_writes_no_new_byte() -> None:
    """Modulo the version field: every key the document holds was a key it held
    at 11."""
    run = execute(suite(cases=[Case(id="one")]), Counting(), created_at=CREATED)
    assert "calibration" not in run_to_json(run)


def test_a_document_carrying_an_unreadable_band_is_refused_by_name() -> None:
    run = execute(suite(), Counting(), created_at=CREATED)
    document = json.loads(run_to_json(run))
    document["results"][1]["calibration"] = {
        "check": "llm_rubric",
        "low": 0.0,
        "high": 1.0,
    }
    with pytest.raises(ValueError, match="strictly between 0"):
        run_from_json(json.dumps(document))


# --------------------------------------------------------------------------- #
# End to end — the declarative form, and exit 2 on a first run with no baseline
# --------------------------------------------------------------------------- #


SUITE_TOML = """
[suite]
tenant = "acme"
environment = "staging"
name = "calibrated"
cases = "cases.json"
samples = 2
min_agreement = "2/2"

[[assertion]]
type = "contains"
needle = "Rome"
"""


def test_the_cases_file_declares_it_and_refuses_an_unknown_key(tmp_path: Path) -> None:
    from digline.host import UsageError
    from digline.host.toml_suite import _cases  # pyright: ignore[reportPrivateUsage]

    path = tmp_path / "cases.json"
    path.write_text(
        json.dumps(
            [
                {"id": "one"},
                {
                    "id": "half",
                    "calibration": {
                        "output": HALF,
                        "check": "llm_rubric",
                        "low": 0.3,
                        "high": 0.7,
                        "input": "",
                    },
                },
            ]
        ),
        encoding="utf-8",
    )
    cases = _cases(path, "suite.toml")
    assert cases[1].calibration == calibration(input="")

    path.write_text(
        json.dumps(
            [
                {
                    "id": "half",
                    "calibration": {
                        "output": HALF,
                        "check": "x",
                        "low": 0.3,
                        "hihg": 0.7,
                    },
                }
            ]
        ),
        encoding="utf-8",
    )
    with pytest.raises(UsageError, match="hihg"):
        _cases(path, "suite.toml")


SUITE_PY = """
from pathlib import Path

from digline.core import Contains, JudgeReply, LlmRubric
from digline.run import Calibration, Case, Response, Suite


def judge(prompt):
    placed = float(Path("placed.txt").read_text().strip())
    return JudgeReply(score=placed if "HALF-RIGHT" in prompt else 1.0, reason="r")


suite = Suite(
    tenant="acme-bank",
    environment="staging",
    name="calibrated",
    assertions=[
        Contains(needle="Rome"),
        LlmRubric(rubric="right?", judge=judge, threshold=0.7, tolerance=0.05),
    ],
    cases=[
        Case(id="one"),
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


def target(case):
    return Response(output="Rome", input="capital?")
"""


def test_a_first_run_that_lost_its_scale_exits_two_from_report_and_explain(
    repo: Path,
) -> None:
    (repo / "suite_calibrated.py").write_text(SUITE_PY, encoding="utf-8")
    (repo / "placed.txt").write_text("1.0\n", encoding="utf-8")

    ran = cli(repo, "run", "--suite", "suite_calibrated.py")
    assert ran.returncode == EXIT_OK, ran.stderr
    assert "1 calibration case judged 2 times" in ran.stderr
    key = ran.stdout.strip()

    reported = cli(
        repo, "report", "--suite", "suite_calibrated.py", "--run", key, "--locale", "en"
    )
    assert reported.returncode == EXIT_UNJUDGED, reported.stderr
    assert "outside its declared band" in reported.stdout

    explained = cli(
        repo, "explain", "--suite", "suite_calibrated.py", "--run", key, "--json"
    )
    assert explained.returncode == EXIT_UNJUDGED, explained.stderr
    payload = json.loads(explained.stdout)
    assert payload["exit_code"] == EXIT_UNJUDGED
    assert payload["facts"][0]["kind"] == "calibration"

    promoted = cli(repo, "promote", "--suite", "suite_calibrated.py", "--run", key)
    assert promoted.returncode != EXIT_OK
    assert "UncalibratedRunError" in promoted.stderr


def test_a_run_whose_calibration_held_compares_clean(repo: Path) -> None:
    (repo / "suite_calibrated.py").write_text(SUITE_PY, encoding="utf-8")
    (repo / "placed.txt").write_text("0.5\n", encoding="utf-8")
    key = cli(repo, "run", "--suite", "suite_calibrated.py").stdout.strip()
    promoted = cli(repo, "promote", "--suite", "suite_calibrated.py", "--run", key)
    assert promoted.returncode == EXIT_OK, promoted.stderr

    (repo / "placed.txt").write_text("1.0\n", encoding="utf-8")
    later = cli(repo, "run", "--suite", "suite_calibrated.py").stdout.strip()
    compared = cli(
        repo, "compare", "--suite", "suite_calibrated.py", "--run", later, "--json"
    )
    payload = json.loads(compared.stdout)
    assert payload["scale_lost"] is True
    assert payload["worse"] is False
    assert compared.returncode == EXIT_UNJUDGED


def test_a_0_13_1_reader_refuses_a_document_carrying_one(tmp_path: Path) -> None:
    """Why this is a bump and not a key added quietly.

    A 0.13.1 reader that accepted the document would count the calibration case
    as an ordinary case — no band, no lost scale — and exit 0 where this tree
    exits 2. What keeps that from happening is the version, so it is checked
    against 0.13.1's own source, taken from its tag; skipped where the tags are
    absent, as `test_recorded_output.py` skips its own. (ADR 0014 §1, ADR 0024
    §9)
    """
    root = Path(__file__).resolve().parents[1]
    archive = subprocess.run(  # noqa: S603
        ["git", "archive", "v0.13.1", "src"],  # noqa: S607
        cwd=root,
        capture_output=True,
        check=False,
    )
    if archive.returncode != 0:
        pytest.skip("v0.13.1 is not in this checkout (shallow clone, no tags)")
    with tarfile.open(fileobj=io.BytesIO(archive.stdout)) as tar:
        tar.extractall(tmp_path / "old", filter="data")

    # Stamped 12, the schema that brought the calibration case: a document at
    # 13 would be refused on its version too, for a bump that is not this one.
    written = json.loads(
        run_to_json(execute(suite(score=1.0), Counting(), created_at=CREATED))
    )
    written["schema_version"] = 12
    document = tmp_path / "run.json"
    document.write_text(json.dumps(written), encoding="utf-8")
    read = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-c",
            "import sys, digline.core as c; print(c.__file__); "
            "c.run_from_json(open(sys.argv[1], encoding='utf-8').read())",
            str(document),
        ],
        env={**os.environ, "PYTHONPATH": str(tmp_path / "old" / "src")},
        capture_output=True,
        text=True,
        check=False,
    )
    assert read.stdout.startswith(str(tmp_path / "old")), read.stdout
    assert read.returncode != 0
    assert "schema_version 12 is not supported (expected 11)" in read.stderr, (
        read.stderr
    )


def test_declaring_one_moves_no_config_hash() -> None:
    """ADR 0014 §1's first question: case data, outside the hash, as the canary
    is. Adding a calibration case, or moving its band, re-promotes nothing."""
    check = rubric()
    plain = suite(assertions=[check], cases=[Case(id="one")])
    calibrated = suite(assertions=[check])
    moved = suite(
        assertions=[check],
        cases=[Case(id="one"), Case(id="half", calibration=calibration(low=0.4))],
    )
    assert plain.config_hash() == calibrated.config_hash() == moved.config_hash()


# --------------------------------------------------------------------------- #
# §4.7, amended after 0.14.0 — the fields never, a reason inside, no boundary
# --------------------------------------------------------------------------- #


class RamblingJudge(ScoreJudge):
    """The shipped `ScoreJudge`, over a model that answers the calibration case in
    prose: it restates the answer and the question and gives no JSON, so every
    judgement is refused with its reply quoted — the one path on which a reason
    carries the declared payload into a document."""

    def __init__(self) -> None:
        super().__init__(
            "fake-1",
            max_tokens=100,
            pricing=Pricing(per_model={"fake-1": ModelPrice(1.0, 1.0)}),
        )

    def _complete(self, system: str, prompt: str) -> CompletionResult:
        if "HALF-RIGHT" in prompt:
            output = prompt.split(JUDGE_OUTPUT_LABEL)[-1].strip()
            return (
                f"I will not score this. The answer says {output!r} to "
                "'How do refunds work?'.",
                Usage(input_tokens=10, output_tokens=10),
            )
        return ('{"score": 1.0, "reason": "fine"}', Usage(10, 10))


def rambling_suite() -> Suite:
    return suite(
        assertions=[
            LlmRubric(
                rubric="is it right?",
                judge=RamblingJudge(),
                threshold=0.7,
                tolerance=0.05,
            )
        ],
        record_responses=True,
    )


def test_the_fields_are_never_written_and_a_quoting_reason_stays_inside() -> None:
    """The corrected promise, both halves at once. The quote does reach the
    complete document — that is what a reason is, for any case — and no
    boundary sink carries it: redacted document, redacted report, both JSON
    readings, the MCP run document. If this starts failing on a boundary sink,
    decision 9 is broken; if the quote stops reaching the complete document,
    the test has stopped exercising the path."""
    held = execute(suite(record_responses=True), Counting(), created_at=CREATED)
    run = execute(rambling_suite(), Counting(), created_at=LATER)
    half = run.results[1]
    assert half.responses == ()
    [verdict] = half.verdicts
    assert verdict.status == "error"

    complete = run_to_json(run)
    assert "HALF-RIGHT" in complete
    assert "How do refunds work?" in complete
    assert "responses" not in json.loads(complete)["results"][1]

    comparison = compare(run, held)
    head = headline(comparison, run, held, locale="en")
    boundary = {
        "run_to_json(redacted=True)": run_to_json(run, redacted=True),
        "report --redacted": render_run_html(redact(run), locale="en"),
        "report --redacted, compared": render_html(
            compare(redact(run), redact(held)), redact(run), redact(held), locale="en"
        ),
        "compare --json full": json.dumps(compare_json(comparison, head, full=True)),
        "explain --json": json.dumps(
            explain_json(facts(run, comparison), scope="comparison", exit_code=2)
        ),
        "explain --json, alone": json.dumps(
            explain_json(facts(run), scope="run", exit_code=2)
        ),
        "MCP run document": json.dumps(run_document(run, NOTHING_EXTRA)),
        "headline sentence": head.sentence,
    }
    for sink, text in boundary.items():
        assert "HALF-RIGHT" not in text, sink
        assert "How do refunds work?" not in text, sink
