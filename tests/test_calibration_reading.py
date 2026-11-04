"""The reading of a lost band: which case, which check, what score, which band
and which side, in `explain`'s text and in its `--json`, as the report's
section shows it. (ADR 0024 §4.5)

Rebuilt from the measurement of 2026-11-03: six calibration cases, three with
a high band and three with a low one, a judge that answers from a table, and
two cases outside their band, one on each side. Before this the text said a
count and the document carried one, and the names and the side were in the
HTML report alone.
"""

from __future__ import annotations

import json
from collections.abc import Mapping

import pytest

from digline.core import JudgeReply, LlmRubric, Run, compare
from digline.report.explain import TallyFact, explain_text, facts
from digline.report.render import calibration_section
from digline.run import Calibration, Case, Response, Suite, execute
from digline.wire import explain_json

CREATED = "2026-11-04T00:00:00+00:00"

#: The answer each calibration case declares, and the score the judge gives
#: it. A key the prompt carries, so the table finds it.
TABLE: Mapping[str, float] = {
    "ANSWER-H1": 0.75,
    "ANSWER-H2": 0.80,
    "ANSWER-H3": 0.50,  # below its band 0.60–0.90
    "ANSWER-L1": 0.20,
    "ANSWER-L2": 0.30,
    "ANSWER-L3": 0.55,  # above its band 0.10–0.40
}
HIGH, LOW = (0.6, 0.9), (0.1, 0.4)


def judge(prompt: str) -> JudgeReply:
    for answer, score in TABLE.items():
        if answer in prompt:
            return JudgeReply(score=score, reason="from the table")
    return JudgeReply(score=1.0, reason="an ordinary answer")


def suite() -> Suite:
    cases = [Case(id="by-hand")]
    for answer in TABLE:
        low, high = HIGH if answer.startswith("ANSWER-H") else LOW
        cases.append(
            Case(
                id=answer.lower().replace("answer-", "cal-"),
                calibration=Calibration(
                    output=f"{answer}: a partly right answer",
                    check="llm_rubric",
                    low=low,
                    high=high,
                    input="How do refunds work?",
                ),
            )
        )
    return Suite(
        tenant="acme",
        environment="dev",
        name="bench",
        assertions=[
            LlmRubric(rubric="is it right?", judge=judge, threshold=0.7, tolerance=0.05)
        ],
        cases=cases,
        samples=2,
        min_agreement="2/2",
    )


def run() -> Run:
    return execute(
        suite(), lambda case: Response(output="fine", input="q"), created_at=CREATED
    )


def test_the_text_names_each_case_its_check_score_band_and_side() -> None:
    [line] = [
        line
        for line in explain_text(facts(run()), locale="en")
        if "calibration case" in line
    ]
    assert line.startswith("2 calibration cases scored outside their declared bands: ")
    assert "cal-h3 for llm_rubric at 0.500000, below 0.600000–0.900000" in line
    assert "cal-l3 for llm_rubric at 0.550000, above 0.100000–0.400000" in line
    for held in ("cal-h1", "cal-h2", "cal-l1", "cal-l2"):
        assert held not in line


def test_the_italian_text_names_the_side_too() -> None:
    [line] = [
        line
        for line in explain_text(facts(run()), locale="it")
        if "calibrazione" in line
    ]
    assert "cal-h3 per llm_rubric a 0.500000, sotto 0.600000–0.900000" in line
    assert "cal-l3 per llm_rubric a 0.550000, sopra 0.100000–0.400000" in line


def test_the_json_lists_each_case_beside_the_count() -> None:
    found = run()
    document = json.loads(
        json.dumps(explain_json(facts(found), reading="run", exit_code=2, run=found))
    )
    [fact] = [f for f in document["facts"] if f.get("kind") == "calibration"]
    assert fact["count"] == 2
    assert fact["bands"] == [
        {
            "case_id": "cal-h3",
            "check": "llm_rubric",
            "score": 0.5,
            "low": 0.6,
            "high": 0.9,
            "side": "below",
        },
        {
            "case_id": "cal-l3",
            "check": "llm_rubric",
            "score": 0.55,
            "low": 0.1,
            "high": 0.4,
            "side": "above",
        },
    ]


def test_a_comparison_names_them_too() -> None:
    """The reading against a reference carries the same list as the reading
    of a run alone: the bands are read off the run either way."""
    found = run()
    [fact] = [
        f
        for f in facts(found, compare(found, found))
        if isinstance(f, TallyFact) and f.kind == "calibration"
    ]
    assert [(item.case_id, item.side) for item in fact.bands] == [
        ("cal-h3", "below"),
        ("cal-l3", "above"),
    ]


def test_the_reading_and_the_section_name_the_same_cases() -> None:
    """One run, two surfaces: the cases the reading names are the ones the
    report's section marks outside."""
    found = run()
    section = calibration_section(found, "en", reasons=False)
    outside = {
        row.split("<code>")[1].split("</code>")[0]
        for row in section.split("<tr>")
        if "outside" in row
    }
    assert outside == {"cal-h3", "cal-l3"}


def test_a_run_whose_bands_held_carries_no_list() -> None:
    held = {**TABLE, "ANSWER-H3": 0.7, "ANSWER-L3": 0.3}
    found = _with(held)
    document = json.loads(
        json.dumps(explain_json(facts(found), reading="run", exit_code=0, run=found))
    )
    for fact in document["facts"]:
        assert "bands" not in fact
        assert fact.get("kind") != "calibration"


def _with(table: Mapping[str, float]) -> Run:
    def scored(prompt: str) -> JudgeReply:
        for answer, score in table.items():
            if answer in prompt:
                return JudgeReply(score=score, reason="from the table")
        return JudgeReply(score=1.0, reason="an ordinary answer")

    declared = suite()
    rubric = LlmRubric(
        rubric="is it right?", judge=scored, threshold=0.7, tolerance=0.05
    )
    return execute(
        Suite(
            tenant=declared.tenant,
            environment=declared.environment,
            name=declared.name,
            assertions=[rubric],
            cases=list(declared.cases),
            samples=2,
            min_agreement="2/2",
        ),
        lambda case: Response(output="fine", input="q"),
        created_at=CREATED,
    )


@pytest.mark.parametrize(("score", "side"), [(0.95, "above"), (0.05, "below")])
def test_the_side_is_read_off_the_score_and_the_band(score: float, side: str) -> None:
    from digline.core import ScaleLost

    lost = ScaleLost(case_id="c", check="k", score=score, samples=(), low=0.3, high=0.7)
    assert lost.side == side
