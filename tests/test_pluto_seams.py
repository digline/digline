"""The seams C's pluto pass found where an agent meets the gate. (P-1530)

- A check on the steps names the tools, and a sampled one kept a mean of 0 and
  0 instead: it keeps what each sample said now. (ADR 0018 §1)
- A reviewed answer of an episode carries its steps, and the suite's
  trajectory checks run on it; on a yes, a red one is a contradiction.
  (ADR 0059 §1, amended 2026-11-05)
- `run`'s `next:` never names `promote` where the run's own exit is not 0, and
  names `explain` on a contradiction.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from digline.cli import EXIT_OK
from digline.core import (
    Before,
    Contains,
    JudgeReply,
    LlmRubric,
    MaxSteps,
    Never,
    Run,
    Subsequence,
    combine_samples,
)
from digline.core.reviewed import contradicted
from digline.core.run import RecordedStep, RecordedToolCall, recorded_step_to_dict
from digline.host import read_cases
from digline.run import Case, Response, ReviewedAnswer, Suite, execute
from digline.run.suite import TRAJECTORY_CHECKS

CREATED = "2026-11-05T00:00:00+00:00"
QUESTION = "refund order 103"


def judge(prompt: str) -> JudgeReply:
    return JudgeReply(score=1.0, reason="fine")


def rubric() -> LlmRubric:
    return LlmRubric(rubric="handled?", judge=judge, threshold=0.7, tolerance=0.05)


# -- 1. a sampled check on the steps says what each sample said ------------------ #


def calling(*tools: str) -> Any:
    def target(case: Case) -> Response:
        return Response(output="done", metadata={"tools": list(tools)})

    return target


def sampled(check: Any, target: Any, samples: int = 2) -> Run:
    suite = Suite(
        tenant="acme",
        environment="dev",
        name="pluto",
        assertions=[check],
        cases=[Case(id="one")],
        samples=samples,
        min_agreement=f"{samples}/{samples}" if samples > 1 else None,
    )
    return execute(suite, target, created_at=CREATED)


def reason(found: Run) -> str:
    (case,) = found.results
    (verdict,) = case.verdicts
    return verdict.reason


@pytest.mark.parametrize(
    ("check", "said"),
    [
        (
            Subsequence(tools=["search", "answer"]),
            "every sample: expected 'search', 'answer' in this order, saw "
            "'answer', 'search': 1 of 2 found in order",
        ),
        (
            Before(first="lookup_order", then="issue_refund"),
            "every sample: 1 call(s) to 'issue_refund' with no call to "
            "'lookup_order' before it, in 'answer', 'search'",
        ),
        (Never(tool="search"), "every sample: 'search' was called 1 time(s)"),
    ],
    ids=["subsequence", "before", "never"],
)
def test_a_sampled_check_on_the_steps_names_the_tools_after_the_mean(
    check: Any, said: str
) -> None:
    target = calling("answer", "search")
    if isinstance(check, Before):
        target = calling("answer", "search", "issue_refund")
        said = said.replace("'answer', 'search'", "'answer', 'search', 'issue_refund'")
    found = reason(sampled(check, target))
    assert found.startswith("mean of 2 samples (0.000000, 0.000000)"), found
    assert found.endswith(said), found


def test_max_steps_says_how_many_and_the_limit() -> None:
    def stepping(case: Case) -> Response:
        steps = [{"index": i, "actor": "model", "finish": "stop"} for i in range(3)]
        return Response(output="done", metadata={"steps": steps})

    found = reason(sampled(MaxSteps(limit=2, count="model"), stepping))
    assert found.endswith("every sample: 3 model step(s), at most 2 allowed"), found


def test_samples_that_said_different_things_are_each_said_once() -> None:
    answers = iter([["search", "answer"], ["answer"]])

    def target(case: Case) -> Response:
        return Response(output="done", metadata={"tools": next(answers)})

    check = Never(tool="search")
    suite = Suite(
        tenant="acme",
        environment="dev",
        name="pluto",
        assertions=[check],
        cases=[Case(id="one")],
        samples=2,
        min_agreement="1/2",
    )
    found = reason(execute(suite, target, created_at=CREATED))
    assert found.endswith(
        "; 1 sample: 'search' was called 1 time(s); 1 sample: 'search' was not called"
    ), found


def test_a_check_not_on_the_steps_keeps_the_mean_alone() -> None:
    found = reason(sampled(Contains(needle="done"), calling("search")))
    assert found == "mean of 2 samples (1.000000, 1.000000)"


def test_only_the_four_on_the_steps_say_each_sample() -> None:
    sayers = {
        cls.__name__
        for cls in (*TRAJECTORY_CHECKS, Contains, LlmRubric)
        if getattr(cls, "SAYS_EACH_SAMPLE", False)
    }
    assert sayers == {"Subsequence", "Before", "Never", "MaxSteps"}


def test_the_fold_says_nothing_more_unless_asked() -> None:
    verdict = Never(tool="x")
    from digline.core import EvaluatorInputs

    raw = [
        verdict(EvaluatorInputs(output="o", metadata={"response": {"tools": []}}))
    ] * 2
    assert combine_samples(raw, min_agreement=1.0).reason.startswith("mean of 2")
    assert ";" not in combine_samples(raw, min_agreement=1.0).reason
    assert combine_samples(raw, min_agreement=1.0, each=True).reason.endswith(
        "; every sample: 'x' was not called"
    )


# -- 2. a reviewed episode carries its steps ------------------------------------ #


def call(tool: str) -> RecordedToolCall:
    return RecordedToolCall(
        tool=tool,
        arguments='{"order": "103"}',
        result=None,
        result_absence="not_recorded",
    )


def steps(*tools: str) -> tuple[RecordedStep, ...]:
    found: list[RecordedStep] = []
    for tool in tools:
        found.append(RecordedStep(index=len(found), actor="model", finish="tool_use"))
        found.append(RecordedStep(index=len(found), actor="tool", call=call(tool)))
    found.append(RecordedStep(index=len(found), actor="model", finish="stop"))
    return tuple(found)


def reviewed_suite(*cases: Case) -> Suite:
    return Suite(
        tenant="acme",
        environment="dev",
        name="pluto",
        assertions=[
            rubric(),
            Before(first="lookup_order", then="issue_refund"),
            Never(tool="delete_account"),
            # Read off the steps and nothing else: no fallback on the names.
            MaxSteps(limit=6, count="model"),
        ],
        cases=[Case(id="by-hand"), *cases],
        samples=2,
        min_agreement="2/2",
    )


def reviewed(case_id: str, *, good: bool, trajectory: Any) -> Case:
    return Case(
        id=case_id,
        reviewed_answer=ReviewedAnswer(
            output="Done.",
            check="llm_rubric",
            good=good,
            input=QUESTION,
            steps=trajectory,
        ),
    )


def target(case: Case) -> Response:
    assert case.reviewed_answer is None, "a reviewed answer's target is never called"
    return Response(output="Done.", input=QUESTION, metadata={"tools": []})


def ran(*cases: Case) -> Run:
    return execute(reviewed_suite(*cases), target, created_at=CREATED)


def verdicts(found: Run, case_id: str) -> dict[str, str]:
    (case,) = [r for r in found.results if r.case_id == case_id]
    return {v.score.name: v.status for v in case.verdicts}


def test_a_reviewed_episode_is_asked_its_trajectory_checks_beside_its_check() -> None:
    found = ran(
        reviewed("good", good=True, trajectory=steps("lookup_order", "issue_refund"))
    )
    assert verdicts(found, "good") == {
        "llm_rubric": "pass",
        "before": "pass",
        "never": "pass",
        "max_steps": "pass",
    }
    assert contradicted(found) == ()


def test_a_yes_whose_steps_fail_a_check_is_a_contradiction() -> None:
    found = ran(reviewed("quick", good=True, trajectory=steps("issue_refund")))
    assert verdicts(found, "quick")["before"] == "fail"
    (against,) = contradicted(found)
    assert (against.case_id, against.check, against.direction) == (
        "quick",
        "before",
        "failed_yes",
    )


def test_a_no_whose_steps_fail_a_check_is_no_contradiction() -> None:
    """The judge passed it: that is the no's contradiction, and the red check
    beside it agrees with the person."""
    found = ran(reviewed("quick", good=False, trajectory=steps("issue_refund")))
    assert verdicts(found, "quick")["before"] == "fail"
    assert [(c.check, c.direction) for c in contradicted(found)] == [
        ("llm_rubric", "passed_no")
    ]


def test_an_answer_without_steps_is_asked_its_check_alone() -> None:
    found = ran(reviewed("plain", good=True, trajectory=None))
    assert verdicts(found, "plain") == {"llm_rubric": "pass"}


def test_steps_out_of_order_are_refused() -> None:
    from digline.core import RefusedError

    shuffled = tuple(reversed(steps("lookup_order")))
    with pytest.raises(RefusedError, match="in order from 0"):
        ReviewedAnswer(output="x", check="c", good=True, input="q", steps=shuffled)


def test_a_cases_file_carries_the_steps_in_the_run_documents_form(
    tmp_path: Path,
) -> None:
    written = steps("lookup_order", "issue_refund")
    path = tmp_path / "captured.json"
    path.write_text(
        json.dumps(
            [
                {
                    "id": "ep",
                    "reviewed_answer": {
                        "output": "Done.",
                        "check": "llm_rubric",
                        "good": True,
                        "input": QUESTION,
                        "steps": [recorded_step_to_dict(s) for s in written],
                    },
                }
            ]
        ),
        encoding="utf-8",
    )
    (case,) = read_cases(path)
    assert case.reviewed_answer is not None
    assert case.reviewed_answer.steps == written


# -- 4. next: never promote on a run whose own exit is not 0 -------------------- #

NEXT = "digline: next: "

CONTRADICTED = """
from digline.core import Contains, JudgeReply, LlmRubric
from digline.run import Case, Response, ReviewedAnswer, Suite


def judge(prompt):
    return JudgeReply(score=1.0, reason="fine")


def target(case):
    return Response(output="hello")


suite = Suite(
    tenant="t",
    environment="e",
    name="said",
    assertions=[
        LlmRubric(rubric="good?", judge=judge, threshold=0.5, tolerance=0.1),
        Contains("hello"),
    ],
    cases=[
        Case(id="c1"),
        Case(
            id="r1",
            reviewed_answer=ReviewedAnswer(
                output="hello there", check="llm_rubric", good=GOOD, input="q"
            ),
        ),
    ],
    samples=2,
    min_agreement="2/2",
)
"""


def next_line(
    root: Path,
    good: bool,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> str:
    """In this process, so a change to the line is the line read here: a
    `digline` started as a process of its own imports the installed one."""
    import importlib

    # `digline.cli` exports a function `main`, which hides the module of the
    # same name from an attribute lookup.
    cli_main = importlib.import_module("digline.cli.main")
    (root / "suite.py").write_text(
        CONTRADICTED.replace("GOOD", str(good)), encoding="utf-8"
    )
    monkeypatch.chdir(root)
    assert cli_main.main(["run", "--suite", "suite.py"]) == EXIT_OK
    (line,) = [x for x in capsys.readouterr().err.splitlines() if x.startswith(NEXT)]
    return line


def test_a_contradicted_run_is_told_to_explain_and_why(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert next_line(tmp_path, False, monkeypatch, capsys) == (
        "digline: next: digline explain --suite suite.py --run latest"
        "  # reads this run back; the judge contradicted a person"
    )


def test_the_same_run_agreed_with_is_told_to_promote(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert next_line(tmp_path, True, monkeypatch, capsys).startswith(
        "digline: next: digline promote --suite suite.py --run latest --replacing none"
    )


def test_the_runs_own_exit_decides_even_where_promote_would_take_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Measured on 2026-11-05: every cause that makes a lone run exit 1 or 2
    is also a refusal of `promote`, so the rule held through #844's. It is
    held here on its own: with `promote` made to take anything, a
    contradicted run is still told to `explain`."""
    import importlib

    # `digline.cli` exports a function `main`, which hides the module of the
    # same name from an attribute lookup.
    cli_main = importlib.import_module("digline.cli.main")

    def takes_anything(*args: object, **kwargs: object) -> tuple[str, ...]:
        return ()

    monkeypatch.setattr(cli_main, "refusals_for", takes_anything)
    (tmp_path / "suite.py").write_text(
        CONTRADICTED.replace("GOOD", "False"), encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)
    assert cli_main.main(["run", "--suite", "suite.py"]) == EXIT_OK
    (line,) = [x for x in capsys.readouterr().err.splitlines() if x.startswith(NEXT)]
    assert "digline explain" in line, line
    assert "digline promote" not in line, line


@pytest.fixture
def root(tmp_path: Path) -> Path:
    """The import tests' recordings and suite, an episode with steps among
    them."""
    from tests.test_recorder_import import recorded, suite_file

    recorded(tmp_path)
    suite_file(tmp_path)
    return tmp_path


def test_the_import_writes_an_episodes_steps_and_a_calls_none(root: Path) -> None:
    """The yes and the no a person gives at the import: the episode's answer
    goes into the cases file with the steps it was recorded with, in the run
    document's form, and a single call's goes without any."""
    from tests.test_recorder_import import ID_C, ID_E, listed

    from digline.host import import_elect

    import_elect(listed(root), good=[ID_E], bad=[ID_C], by="Ada")
    written = {
        entry["id"]: entry["reviewed_answer"]
        for entry in json.loads((root / "captured.json").read_text(encoding="utf-8"))
        if "reviewed_answer" in entry
    }
    assert written[ID_E]["steps"] == [
        {"index": 0, "actor": "model"},
        {"index": 1, "actor": "tool", "tool": "lookup", "arguments": "{}"},
        {"index": 2, "actor": "model", "finish": "end_turn"},
    ]
    assert "steps" not in written[ID_C]
    by_id = {case.id: case for case in read_cases(root / "captured.json")}
    answer = by_id[ID_E].reviewed_answer
    assert answer is not None and answer.steps is not None
    assert [step.actor for step in answer.steps] == ["model", "tool", "model"]


def test_samples_that_did_not_agree_say_what_each_said_too() -> None:
    answers = iter([["search"], []])

    def target(case: Case) -> Response:
        return Response(output="done", metadata={"tools": next(answers)})

    suite = Suite(
        tenant="acme",
        environment="dev",
        name="pluto",
        assertions=[Never(tool="search")],
        cases=[Case(id="one")],
        samples=2,
        min_agreement="2/2",
    )
    found = reason(execute(suite, target, created_at=CREATED))
    assert found.startswith("the samples did not agree"), found
    assert found.endswith(
        "; 1 sample: 'search' was called 1 time(s); 1 sample: 'search' was not called"
    ), found


def test_the_names_and_the_calls_are_read_off_the_steps_too() -> None:
    """`ToolsCalled` reads names and `ToolCalledWith` calls, never steps: the
    reviewed answer hands both, read off its steps, as a replay does."""
    from digline.core import ToolCalledWith, ToolsCalled

    suite = Suite(
        tenant="acme",
        environment="dev",
        name="pluto",
        assertions=[
            rubric(),
            ToolsCalled(expected=["lookup_order", "issue_refund"]),
            ToolCalledWith(tool="lookup_order", arguments={"order": "103"}),
        ],
        cases=[
            Case(id="by-hand"),
            reviewed("ep", good=True, trajectory=steps("lookup_order", "issue_refund")),
        ],
        samples=2,
        min_agreement="2/2",
    )
    found = execute(suite, target, created_at=CREATED)
    assert verdicts(found, "ep") == {
        "llm_rubric": "pass",
        "tools_called": "pass",
        "tool_called_with": "pass",
    }


def test_the_import_takes_the_newest_steps_under_the_setup_in_force() -> None:
    from tests.test_recorder_import import case, recording

    from digline.host.importing import _steps_of  # pyright: ignore[reportPrivateUsage]

    old, new = steps("lookup_order"), steps("lookup_order", "issue_refund")
    asked = case("refund?")
    group = [
        recording(asked, "s1", "Done.", "01", steps=old, id="a" * 32),
        recording(asked, "s2", "Done.", "02", steps=new, id="b" * 32),
        recording(asked, "s2", "Done.", "03", steps=old, id="c" * 32),
        recording(asked, "s1", "Done.", "04", steps=new, id="d" * 32),
    ]
    assert _steps_of(group, "s2") == old
    assert _steps_of(group, "s1") == new
    assert _steps_of(group, "elsewhere") == old
    # A single call is recorded with its steps too, and a reviewed answer of
    # one carries none: the amendment is an episode's. (ADR 0059 §1)
    single = [recording(asked, "s1", "Done.", "05", steps=new)]
    assert _steps_of(single, "s1") is None
