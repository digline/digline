"""A reviewed answer: an answer the application gave, and a person's yes or
no about it, declared and loaded, and not run yet. (ADR 0059 §1)

What is held here:

- the type refuses an empty output, check or input, and a `good` that is not
  a `bool`;
- a case that is a reviewed answer refuses every field that would make it
  another kind of case, naming both;
- the suite refuses a check it does not declare, one two assertions share,
  one that is not judged, and a single sample;
- the cases file reads it, `good` as JSON's `true` or `false`, and refuses an
  unknown key inside it;
- a run of a suite that declares one is refused before anything is called
  and before anything is written: no run, no journal, from `execute`, from
  the host and from `digline run`; a replay is refused the same way.
"""

from __future__ import annotations

import dataclasses
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from digline.core import Contains, JudgeReply, LlmRubric, Repeated
from digline.core.refused import RefusedError
from digline.host import UsageError, load_suite, read_cases
from digline.host.measure import prepare
from digline.run import (
    Calibration,
    Case,
    Response,
    ReviewedAnswer,
    Suite,
    execute,
    refuse_reviewed_answers,
)
from digline.run.replay import Replay
from digline.wire import EXIT_USAGE

CREATED = "2026-01-01T00:00:00+00:00"
ANSWER = "Refunds take 14 days from the day the parcel is back."
QUESTION = "How long does a refund take?"


def judge(prompt: str) -> JudgeReply:
    return JudgeReply(score=1.0, reason="r")


def rubric(name: str = "llm_rubric") -> LlmRubric:
    return LlmRubric(
        rubric="is it right?", judge=judge, threshold=0.7, tolerance=0.05, name=name
    )


def answer(**changes: Any) -> ReviewedAnswer:
    fields: dict[str, Any] = {
        "output": ANSWER,
        "check": "llm_rubric",
        "good": True,
        "input": QUESTION,
    }
    fields.update(changes)
    return ReviewedAnswer(**fields)


def suite(*cases: Case, samples: int = 2, assertions: Any = None) -> Suite:
    return Suite(
        tenant="acme",
        environment="dev",
        name="support",
        assertions=[rubric()] if assertions is None else assertions,
        cases=[Case(id="by-hand"), *cases],
        samples=samples,
        min_agreement=None if samples == 1 else "2/2",
    )


def reviewed(case_id: str = "cap-1", **changes: Any) -> Case:
    return Case(id=case_id, reviewed_answer=answer(), **changes)


# -- the type ----------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("changes", "said"),
    [
        ({"output": ""}, "declares an empty output"),
        ({"check": ""}, "a reviewed answer names no check"),
        ({"input": ""}, "declares no input"),
        ({"good": 1}, "gives good=1: good is true or false"),
        ({"good": "yes"}, "gives good='yes': good is true or false"),
        ({"good": None}, "gives good=None: good is true or false"),
    ],
    ids=[
        "empty output",
        "empty check",
        "empty input",
        "good 1",
        "good yes",
        "good None",
    ],
)
def test_the_type_refuses_what_says_nothing(changes: dict[str, Any], said: str) -> None:
    with pytest.raises(RefusedError, match=said):
        answer(**changes)


def test_good_is_either_bool() -> None:
    assert answer(good=True).good is True
    assert answer(good=False).good is False


@pytest.mark.parametrize(
    ("field", "value"),
    [
        (
            "calibration",
            Calibration(output="half", check="llm_rubric", low=0.3, high=0.7),
        ),
        ("canary", True),
        ("label", "positive"),
        ("group", "refunds"),
        ("expected", ANSWER),
    ],
)
def test_a_reviewed_answer_is_no_other_kind_of_case(field: str, value: object) -> None:
    with pytest.raises(
        RefusedError, match=f"declares both reviewed_answer and {field}: "
    ):
        Case(id="cap-1", reviewed_answer=answer(), **{field: value})  # pyright: ignore[reportArgumentType]


# -- the suite ---------------------------------------------------------------- #


def test_a_suite_loads_a_reviewed_answer_and_names_its_check() -> None:
    loaded = suite(reviewed())
    [case] = [c for c in loaded.cases if c.reviewed_answer is not None]
    assert case.reviewed_answer is not None
    assert loaded.reviewed(case.reviewed_answer) is loaded.assertions[0]


def test_a_check_the_suite_does_not_declare_is_refused() -> None:
    with pytest.raises(RefusedError, match="which no assertion in suite 'support'"):
        suite(Case(id="cap-1", reviewed_answer=answer(check="faithfulness")))


def test_a_check_two_assertions_share_is_refused() -> None:
    with pytest.raises(RefusedError, match="which 2 assertions in suite 'support'"):
        suite(reviewed(), assertions=[rubric(), rubric()])


def test_a_check_that_is_not_judged_is_refused() -> None:
    with pytest.raises(RefusedError, match="which is not a judged check"):
        suite(
            Case(id="cap-1", reviewed_answer=answer(check="contains")),
            assertions=[rubric(), Contains(needle="days")],
        )


def test_a_judged_check_inside_repeated_is_judged() -> None:
    wrapped = Repeated(
        inner=rubric(), samples=2, min_agreement="2/2", name="llm_rubric"
    )
    suite(reviewed(), assertions=[wrapped])


def test_one_sample_is_refused_with_the_reason() -> None:
    with pytest.raises(
        RefusedError, match="a single disagreement would fail the gate for noise"
    ):
        suite(reviewed(), samples=1)


# -- the cases file ----------------------------------------------------------- #


def entry(**changes: Any) -> dict[str, Any]:
    reviewed_answer: dict[str, Any] = {
        "output": ANSWER,
        "check": "llm_rubric",
        "good": False,
        "input": QUESTION,
    }
    reviewed_answer.update(changes)
    return {"id": "cap-1", "reviewed_answer": reviewed_answer}


def test_the_cases_file_reads_a_reviewed_answer(tmp_path: Path) -> None:
    path = tmp_path / "cases.json"
    path.write_text(json.dumps([entry(), {**entry(good=True), "id": "cap-2"}]))
    no, yes = read_cases(path)
    assert no.reviewed_answer == answer(good=False)
    assert yes.reviewed_answer == answer(good=True)


@pytest.mark.parametrize(
    ("changes", "said"),
    [
        ({"good": 0}, "gives good=0"),
        ({"band": 1}, "band"),
        ({"output": ""}, "declares an empty output"),
    ],
    ids=["good 0", "unknown key", "empty output"],
)
def test_the_cases_file_refuses_by_name(
    tmp_path: Path, changes: dict[str, Any], said: str
) -> None:
    path = tmp_path / "cases.json"
    path.write_text(json.dumps([entry(**changes)]))
    with pytest.raises(UsageError, match=f"cases.json #1, reviewed_answer: .*{said}"):
        read_cases(path)


def test_the_cases_file_refuses_a_reviewed_answer_that_is_not_an_object(
    tmp_path: Path,
) -> None:
    path = tmp_path / "cases.json"
    path.write_text(json.dumps([{"id": "cap-1", "reviewed_answer": True}]))
    with pytest.raises(UsageError, match="this is an object — output, check, good"):
        read_cases(path)


# -- not run yet -------------------------------------------------------------- #

REFUSED = (
    r"reviewed answers run from schema 23 \(ADR 0059 §1\); this build is on "
    r"schema 22"
)


def test_execute_refuses_the_suite_before_the_first_call() -> None:
    calls: list[str] = []

    def target(case: Case) -> Response:
        calls.append(case.id)
        return Response(output="x")

    with pytest.raises(RefusedError, match=REFUSED):
        execute(suite(reviewed()), target, created_at=CREATED)
    assert calls == []
    with pytest.raises(
        RefusedError, match="declares reviewed answers \\(cap-1, cap-2\\)"
    ):
        refuse_reviewed_answers(suite(reviewed(), reviewed("cap-2")))
    # The control: the same suite without it runs.
    execute(suite(), target, created_at=CREATED)
    assert calls == ["by-hand", "by-hand"]


def test_the_host_refuses_it_before_a_journal_is_opened() -> None:
    with pytest.raises(RefusedError, match=REFUSED):
        prepare(
            suite(reviewed()),
            object(),
            now=CREATED,
            git_commit=None,
            artifacts={},
        )


def test_a_replay_is_refused_for_it_and_not_for_a_missing_answer() -> None:
    run = execute(
        dataclasses.replace(suite(), record_responses=True),
        lambda case: Response(output="x", input="q"),
        created_at=CREATED,
    )
    with pytest.raises(RefusedError, match=REFUSED):
        Replay(suite(reviewed()), run)


SUITE_PY = """\
from digline.core import JudgeReply, LlmRubric
from digline.run import Case, Response, ReviewedAnswer, Suite


def judge(prompt):
    return JudgeReply(score=1.0, reason="r")


suite = Suite(
    tenant="acme",
    environment="dev",
    name="support",
    assertions=[
        LlmRubric(rubric="is it right?", judge=judge, threshold=0.7, tolerance=0.05)
    ],
    cases=[
        Case(id="by-hand"),
        Case(
            id="cap-1",
            reviewed_answer=ReviewedAnswer(
                output="Fourteen days.",
                check="llm_rubric",
                good=True,
                input="How long?",
            ),
        ),
    ],
    samples=2,
    min_agreement="2/2",
)


def target(case):
    raise AssertionError("the target was called")
"""


def test_digline_run_refuses_it_and_writes_nothing(tmp_path: Path) -> None:
    (tmp_path / "suite.py").write_text(SUITE_PY, encoding="utf-8")
    done = subprocess.run(
        [sys.executable, "-m", "digline.cli", "run", "--suite", "suite.py"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == EXIT_USAGE, done.stderr
    assert "reviewed answers run from schema 23 (ADR 0059 §1)" in done.stderr
    assert "the target was called" not in done.stderr
    assert done.stdout == ""
    # No run and no journal: nothing under the store at all.
    store = tmp_path / ".digline"
    written = [p for p in store.rglob("*") if p.is_file()] if store.exists() else []
    assert written == []


def test_the_suite_loads_from_a_file_and_only_running_it_is_refused(
    tmp_path: Path,
) -> None:
    (tmp_path / "suite.py").write_text(SUITE_PY, encoding="utf-8")
    loaded, _ = load_suite(str(tmp_path / "suite.py"), root=tmp_path)
    assert [c.id for c in loaded.cases if c.reviewed_answer is not None] == ["cap-1"]
