"""A judged verdict that is not firm, said per case. (P-1685, ADR 0012 §3 as
amended 2026-11-14)

Two ways, either enough: the samples split, or the mean sits within a margin
of the threshold, the check's tolerance where it declares one and 0.05 where
it does not. Read off the run alone; in `explain`'s reading, in the report,
and beside the count in `explain --json`. It moves no exit code.
"""

from __future__ import annotations

import itertools
from collections.abc import Iterator
from typing import Any, cast

import pytest

from digline.core import (
    DEFAULT_MARGIN,
    JudgeReply,
    LlmRubric,
    Run,
    uncertain_cases,
)
from digline.report import render_run_html
from digline.report.explain import TallyFact, explain_text, facts
from digline.run import Case, Response, Suite, execute
from digline.wire import explain_json

TORN: Iterator[float] = itertools.cycle([1.0, 0.0, 1.0])


def judge(prompt: str) -> JudgeReply:
    """The output is the case's id: `torn` splits its samples, `close` sits
    0.02 over the threshold, `firm` is far above it."""
    if "torn" in prompt:
        return JudgeReply(score=next(TORN), reason="it depends")
    if "close" in prompt:
        return JudgeReply(score=0.52, reason="barely")
    return JudgeReply(score=1.0, reason="clearly")


@pytest.fixture(scope="module")
def run() -> Run:
    suite = Suite(
        tenant="acme",
        environment="dev",
        name="support",
        assertions=[
            LlmRubric(rubric="declared?", judge=judge, threshold=0.5, tolerance=0.05),
            LlmRubric(rubric="none?", judge=judge, threshold=0.5, tolerance=0.0),
        ],
        cases=[Case(id="torn"), Case(id="close"), Case(id="firm")],
        samples=3,
        min_agreement="2/3",
    )
    return execute(
        suite,
        lambda case: Response(output=case.id, cost_usd=0.0),
        created_at="2026-11-14T00:00:00+00:00",
    )


def test_a_split_and_a_mean_at_the_threshold_are_found_and_a_firm_one_is_not(
    run: Run,
) -> None:
    found = uncertain_cases(run)
    cases = {item.case_id for item in found}
    assert cases == {"torn", "close"}
    for item in found:
        if item.case_id == "torn":
            assert item.split and not item.near
            assert item.agreement is not None and item.agreement < 1
        else:
            assert item.near and not item.split
            assert item.threshold == 0.5


def test_the_margin_is_the_tolerance_where_declared_and_the_default_otherwise(
    run: Run,
) -> None:
    close = {
        item.declared: item for item in uncertain_cases(run) if item.case_id == "close"
    }
    assert close[True].margin == 0.05
    assert close[False].margin == DEFAULT_MARGIN


def test_the_reading_says_each_case_and_where_the_margin_came_from(run: Run) -> None:
    text = "\n".join(explain_text(facts(run), locale="en"))
    assert "judged checks on cases are uncertain" in text
    assert "torn · " in text and "the samples did not all agree" in text
    assert "the mean 0.520000 is within 0.05 of the threshold 0.500000" in text
    assert "the check's tolerance" in text
    assert "a margin of 0.05, because the check declares no tolerance" in text
    assert "firm · " not in text
    italian = "\n".join(explain_text(facts(run), locale="it"))
    assert "perché il controllo non dichiara una tolleranza" in italian


def test_json_carries_them_beside_the_count(run: Run) -> None:
    read = explain_json(facts(run), reading="run", exit_code=0)
    listed = cast(list[dict[str, Any]], read["facts"])
    [tally] = [fact for fact in listed if fact.get("kind") == "uncertain"]
    items = cast(list[dict[str, Any]], tally["uncertain"])
    assert tally["count"] == len(items)
    first = items[0]
    assert set(first) == {
        "case_id",
        "check",
        "score",
        "threshold",
        "margin",
        "margin_declared",
        "split",
        "near",
        "agreement",
        "errored_samples",
    }


def test_every_other_fact_carries_no_such_key(run: Run) -> None:
    read = explain_json(facts(run), reading="run", exit_code=0)
    for fact in cast(list[dict[str, Any]], read["facts"]):
        if fact.get("kind") != "uncertain":
            assert "uncertain" not in fact


def test_the_report_has_a_section(run: Run) -> None:
    page = render_run_html(run, locale="en")
    assert "Uncertain verdicts (" in page
    assert "torn · llm_rubric" in page


def test_no_uncertain_tally_where_every_verdict_is_firm() -> None:
    suite = Suite(
        tenant="acme",
        environment="dev",
        name="support",
        assertions=[LlmRubric(rubric="r", judge=judge, threshold=0.5, tolerance=0.05)],
        cases=[Case(id="firm")],
        samples=3,
        min_agreement="2/3",
    )
    run = execute(
        suite,
        lambda case: Response(output=case.id, cost_usd=0.0),
        created_at="2026-11-14T00:00:00+00:00",
    )
    assert uncertain_cases(run) == ()
    assert not any(
        isinstance(fact, TallyFact) and fact.kind == "uncertain" for fact in facts(run)
    )
    assert "Uncertain verdicts" not in render_run_html(run, locale="en")
