"""A contradiction is counted per answer, and named by who made it. (P-1572)

The story's case: one reviewed answer, a person's yes, a judge that agrees,
and two checks on the steps, `never` and `max_steps`, red on it. `compare`
said *"The judge contradicted a person on 2 reviewed answers: it passed 0 the
person said no to and failed 2 the person said yes to"*: the judge had
contradicted nobody, and there was one answer, not two. `run`, `explain` and
`compare` now say one sentence, `contradicted_said`'s, and count answers.
(ADR 0059 §1, amended 2026-11-05)
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from digline.cli import EXIT_OK, EXIT_WORSE
from digline.core import (
    Judge,
    JudgeReply,
    LlmRubric,
    MaxSteps,
    Never,
    Run,
    compare,
)
from digline.core.reviewed import contradicted
from digline.core.run import RecordedStep, RecordedToolCall
from digline.report import contradicted_said, explain_text, facts, headline
from digline.report.explain import TallyFact
from digline.run import Case, Response, ReviewedAnswer, Suite, execute
from digline.wire.contract import exit_code

CREATED = "2026-11-06T00:00:00+00:00"

#: The one sentence the three front ends say of the story's run.
SAID = (
    "checks on the steps contradicted a person on 1 reviewed answer: "
    "never, on case T3; max_steps, on case T3"
)


def says_yes() -> Judge:
    def judge(prompt: str) -> JudgeReply:
        return JudgeReply(score=1.0, reason="r")

    return judge


def steps() -> tuple[RecordedStep, ...]:
    """Two model steps, and a call to the tool `never` forbids."""
    return (
        RecordedStep(index=0, actor="model", finish="tool_use"),
        RecordedStep(
            index=1,
            actor="tool",
            call=RecordedToolCall(tool="issue_refund", arguments='{"order": "103"}'),
        ),
        RecordedStep(index=2, actor="model", finish="stop"),
    )


def suite() -> Suite:
    return Suite(
        tenant="acme",
        environment="dev",
        name="pluto",
        assertions=[
            LlmRubric(
                rubric="handled?", judge=says_yes(), threshold=0.7, tolerance=0.05
            ),
            Never(tool="issue_refund"),
            MaxSteps(limit=1, count="model"),
        ],
        cases=[
            Case(id="by-hand"),
            Case(
                id="T3",
                reviewed_answer=ReviewedAnswer(
                    output="Done: issue_refund for 103.",
                    check="llm_rubric",
                    good=True,
                    input="T3 refund-quick order 103",
                    steps=steps(),
                ),
            ),
        ],
        samples=2,
        min_agreement="2/2",
    )


def target(case: Case) -> Response:
    return Response(output="Done.")


def ran() -> Run:
    return execute(suite(), target, created_at=CREATED)


def test_the_story_is_one_answer_and_two_checks_on_its_steps() -> None:
    found = contradicted(ran())
    assert [(c.case_id, c.check, c.on_the_steps) for c in found] == [
        ("T3", "never", True),
        ("T3", "max_steps", True),
    ]
    assert contradicted_said(found, "en") == SAID


def test_compare_says_the_same_sentence_and_counts_the_answer_once() -> None:
    found = ran()
    head = headline(
        compare(found, found), found, found, locale="en", declared=suite().declared()
    )
    assert (
        f"{SAID[:1].upper()}{SAID[1:]}, and the case fails: T3 for never, "
        "failed where the person said yes; T3 for max_steps, failed where the "
        "person said yes." in head.sentence
    ), head.sentence
    assert "The judge" not in head.sentence, head.sentence
    assert "2 reviewed answers" not in head.sentence, head.sentence
    # Answers, by direction, as ADR 0059 §1 counts the cases.
    assert (head.reviewed_passed_no, head.reviewed_failed_yes) == (0, 1)
    assert exit_code(head) == EXIT_WORSE


def test_explain_says_the_same_sentence_for_one_case() -> None:
    reading = facts(ran())
    (tally,) = [f for f in reading if isinstance(f, TallyFact) and f.kind == "reviewed"]
    assert tally.count == 1
    assert len(tally.contradictions) == 2
    lines = explain_text(reading, locale="en")
    said = [line for line in lines if "contradicted a person" in line]
    assert said == [
        f"{SAID[:1].upper()}{SAID[1:]}, and the case fails: T3 for never, "
        "failed where the person said yes; T3 for max_steps, failed where the "
        "person said yes. It is counted in no aggregate, and the target was "
        "not asked for it."
    ], lines


def test_the_italian_compare_sentence_counts_one_answer() -> None:
    found = ran()
    head = headline(compare(found, found), found, found, locale="it", declared=None)
    assert (
        "Dei controlli sui passi hanno contraddetto una persona su 1 risposta "
        "rivista: never, sul caso T3; max_steps, sul caso T3, e il caso "
        "fallisce:" in head.sentence
    ), head.sentence


def test_run_says_the_same_sentence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """In this process, so the line read is the line `run` prints."""
    (tmp_path / "suite.py").write_text(
        f"""
from digline.core import JudgeReply, LlmRubric, MaxSteps, Never
from digline.core.run import RecordedStep, RecordedToolCall
from digline.run import Case, Response, ReviewedAnswer, Suite


def judge(prompt):
    return JudgeReply(score=1.0, reason="r")


def target(case):
    return Response(output="Done.")


suite = Suite(
    tenant="acme",
    environment="dev",
    name="pluto",
    assertions=[
        LlmRubric(rubric="handled?", judge=judge, threshold=0.7, tolerance=0.05),
        Never(tool="issue_refund"),
        MaxSteps(limit=1, count="model"),
    ],
    cases=[
        Case(id="by-hand"),
        Case(
            id="T3",
            reviewed_answer=ReviewedAnswer(
                output="Done.",
                check="llm_rubric",
                good=True,
                input="q",
                steps={steps()!r},
            ),
        ),
    ],
    samples=2,
    min_agreement="2/2",
)
""",
        encoding="utf-8",
    )
    # `digline.cli` exports a function `main`, which hides the module of the
    # same name from an attribute lookup.
    cli_main = importlib.import_module("digline.cli.main")
    monkeypatch.chdir(tmp_path)
    assert cli_main.main(["run", "--suite", "suite.py"]) == EXIT_OK
    err = capsys.readouterr().err.splitlines()
    assert f"digline: {SAID}." in err, err
    assert not any("the judge contradicted" in line for line in err), err
