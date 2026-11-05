"""Who contradicted a person: the judge, or a check on the steps. (P-1537)

The case a user pass met after #935: a yes on an episode whose steps violate `Before`,
and a judge that also says yes. `run` and `explain` said *the judge
contradicted a person*, which it had not, and explain's list of what it found
left the contradiction out, because it read only the named check's verdict.
Both say the check now, from one sentence, and the list has every
contradiction, the judge's and the steps'. (ADR 0059 §1, amended 2026-11-05)
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from digline.cli import EXIT_OK
from digline.core import Before, Judge, JudgeReply, LlmRubric, Run
from digline.core.reviewed import contradicted
from digline.core.run import RecordedStep, RecordedToolCall
from digline.report import contradicted_said, explain_text, facts
from digline.run import Case, Response, ReviewedAnswer, Suite, execute

CREATED = "2026-11-05T00:00:00+00:00"


def says(word: str) -> Judge:
    def judge(prompt: str) -> JudgeReply:
        return JudgeReply(score=1.0 if word == "yes" else 0.0, reason="r")

    return judge


def call(tool: str) -> RecordedToolCall:
    return RecordedToolCall(tool=tool, arguments='{"order": "103"}')


def refund_without_lookup() -> tuple[RecordedStep, ...]:
    """The reported turn: the refund, and no lookup before it."""
    return (
        RecordedStep(index=0, actor="model", finish="tool_use"),
        RecordedStep(index=1, actor="tool", call=call("issue_refund")),
        RecordedStep(index=2, actor="model", finish="stop"),
    )


def suite(judge_says: str, *, good: bool = True) -> Suite:
    return Suite(
        tenant="acme",
        environment="dev",
        name="pluto",
        assertions=[
            LlmRubric(
                rubric="handled?", judge=says(judge_says), threshold=0.7, tolerance=0.05
            ),
            Before(first="lookup_order", then="issue_refund"),
        ],
        cases=[
            Case(id="by-hand"),
            Case(
                id="T3",
                reviewed_answer=ReviewedAnswer(
                    output="Done: issue_refund for 103.",
                    check="llm_rubric",
                    good=good,
                    input="T3 refund-quick order 103",
                    steps=refund_without_lookup(),
                ),
            ),
        ],
        samples=2,
        min_agreement="2/2",
    )


def target(case: Case) -> Response:
    return Response(
        output="Done.",
        metadata={"tools": ["lookup_order", "issue_refund"]},
    )


def ran(judge_says: str) -> Run:
    return execute(suite(judge_says), target, created_at=CREATED)


def test_the_reported_case_names_the_check_on_the_steps_not_the_judge() -> None:
    found = contradicted(ran("yes"))
    assert contradicted_said(found, "en") == (
        "a check on the steps contradicted a person on 1 reviewed answer: "
        "before, on case T3"
    )


def test_both_are_named_where_both_contradicted() -> None:
    found = contradicted(ran("no"))
    assert contradicted_said(found, "en") == (
        "the judge contradicted a person on 1 reviewed answer; a check on the "
        "steps contradicted a person on 1 reviewed answer: before, on case T3"
    )


def test_the_judge_alone_is_said_as_before() -> None:
    plain = execute(
        Suite(
            tenant="acme",
            environment="dev",
            name="pluto",
            assertions=[
                LlmRubric(
                    rubric="handled?", judge=says("no"), threshold=0.7, tolerance=0.05
                )
            ],
            cases=[
                Case(id="by-hand"),
                Case(
                    id="T1",
                    reviewed_answer=ReviewedAnswer(
                        output="Done.", check="llm_rubric", good=True, input="q"
                    ),
                ),
            ],
            samples=2,
            min_agreement="2/2",
        ),
        target,
        created_at=CREATED,
    )
    assert contradicted_said(contradicted(plain), "en") == (
        "the judge contradicted a person on 1 reviewed answer"
    )


def test_explain_opens_with_the_same_sentence_and_lists_the_check() -> None:
    lines = explain_text(facts(ran("yes")), locale="en")
    said = [line for line in lines if "contradicted a person" in line]
    assert said == [
        "A check on the steps contradicted a person on 1 reviewed answer: "
        "before, on case T3, and the case fails: T3 for before, failed where "
        "the person said yes. It is counted in no aggregate, and the target "
        "was not asked for it."
    ], lines
    assert any(
        line.startswith("T3 · before failed at 0.000000")
        and "its steps contradict the person" in line
        for line in lines
    ), lines


def test_explain_lists_every_contradiction_the_judges_and_the_steps() -> None:
    lines = explain_text(facts(ran("no")), locale="en")
    found = [line for line in lines if "contradict" in line and "·" in line]
    assert len(found) == 2, lines
    assert any("T3 · llm_rubric" in line for line in found), found
    assert any("T3 · before" in line for line in found), found


def test_the_italian_sentence_names_the_check_too() -> None:
    assert contradicted_said(contradicted(ran("yes")), "it") == (
        "un controllo sui passi ha contraddetto una persona su 1 risposta "
        "rivista: before, sul caso T3"
    )


def test_run_says_the_sentence_beside_the_bill(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """In this process, so a change to the line is the line read here."""
    (tmp_path / "suite.py").write_text(
        f"""
from digline.core import Before, JudgeReply, LlmRubric
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
        Before(first="lookup_order", then="issue_refund"),
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
                steps={refund_without_lookup()!r},
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
    err = capsys.readouterr().err
    assert (
        "digline: a check on the steps contradicted a person on 1 reviewed "
        "answer: before, on case T3." in err.splitlines()
    ), err


def test_two_checks_on_one_answer_are_one_answer() -> None:
    """`before` and `max_steps` both red on T3: two checks, one reviewed
    answer. The turn took two model steps."""
    from digline.core import MaxSteps

    declared = suite("yes")
    two = Suite(
        tenant=declared.tenant,
        environment=declared.environment,
        name=declared.name,
        assertions=[*declared.assertions, MaxSteps(limit=1, count="model")],
        cases=list(declared.cases),
        samples=2,
        min_agreement="2/2",
    )
    found = contradicted(execute(two, target, created_at=CREATED))
    assert contradicted_said(found, "en") == (
        "checks on the steps contradicted a person on 1 reviewed answer: "
        "before, on case T3; max_steps, on case T3"
    )


def test_the_minimal_case_with_the_judge_repeated() -> None:
    """The minimal case as reported, a judge wrapped in `Repeated` that always
    says 1.0 beside `Before`, and a yes on a turn that refunds without a
    lookup. The report gave `samples=1` for `Repeated`, which is refused at
    declaration ("repeating once is the assertion itself"); 2 is the least it
    takes. Measured before the fix: `contradicted` gave `(T3, before,
    failed_yes)`, the line said the judge, and explain listed nothing."""
    from digline.core import Repeated

    declared = Suite(
        tenant="acme",
        environment="dev",
        name="pluto",
        assertions=[
            Repeated(
                inner=LlmRubric(
                    rubric="handled?", judge=says("yes"), threshold=0.7, tolerance=0.05
                ),
                samples=2,
                min_agreement="2/2",
            ),
            Before(first="lookup_order", then="issue_refund"),
        ],
        cases=[
            Case(id="by-hand"),
            Case(
                id="T3",
                reviewed_answer=ReviewedAnswer(
                    output="Done.",
                    check="llm_rubric",
                    good=True,
                    input="T3 refund-quick order 103",
                    steps=refund_without_lookup(),
                ),
            ),
        ],
        samples=2,
        min_agreement="2/2",
    )
    found_run = execute(declared, target, created_at=CREATED)
    (case,) = [r for r in found_run.results if r.case_id == "T3"]
    assert {v.score.name: v.status for v in case.verdicts} == {
        "llm_rubric": "pass",
        "before": "fail",
    }
    found = contradicted(found_run)
    assert [(c.case_id, c.check, c.direction) for c in found] == [
        ("T3", "before", "failed_yes")
    ]
    assert contradicted_said(found, "en") == (
        "a check on the steps contradicted a person on 1 reviewed answer: "
        "before, on case T3"
    )
    lines = explain_text(facts(found_run), locale="en")
    assert any(line.startswith("T3 · before failed at") for line in lines), lines
    assert not any("The judge contradicted" in line for line in lines), lines
