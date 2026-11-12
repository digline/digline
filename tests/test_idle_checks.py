"""A check no case is asked judges nothing, and says so.

Found in a Java application with a judged suite: every subject case was taken
out or replaced by reviewed answers for one check, and the suite's other check
stayed declared, judged no case, and nothing said it. `idle_checks` reads the
same dispatch the driver follows (`checks_asked`), `suite_notes` says it on
standard error before the first call, and `where` carries it among its facts.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from tests._helpers import cli
from tests.test_reviewed_run import AGREES, CREATED, suite, target

from digline.core.tokens import TokenKind
from digline.run import Case, execute, suite_notes
from digline.run.suite import checks_asked, idle_checks

ONLY_REVIEWED = {"cases": list(AGREES)}


def test_a_suite_with_a_subject_case_has_no_idle_check() -> None:
    assert idle_checks(suite(*AGREES)) == ()


def test_reviewed_answers_for_one_check_leave_the_other_idle() -> None:
    assert idle_checks(suite(**ONLY_REVIEWED)) == ("contains",)


def test_the_idle_check_is_one_the_run_does_not_ask() -> None:
    """The control: what `idle_checks` names is what the driver did not ask,
    so no verdict of the run carries it."""
    checked = suite(**ONLY_REVIEWED)
    found = execute(checked, target, created_at=CREATED)
    [idle] = [a for a in checked.assertions if a.name == "contains"]
    assert all(idle.identity not in checks_asked(checked, c) for c in checked.cases)
    assert not any(
        verdict.assertion_id == idle.identity
        for result in found.results
        for verdict in result.verdicts
    )
    assert any(result.verdicts for result in found.results)


def test_every_case_suspended_leaves_every_check_idle() -> None:
    checked = suite(cases=[Case(id="by-hand", suspended="under review")])
    assert idle_checks(checked) == ("llm_rubric", "contains")


def test_the_suite_notes_say_it_in_one_sentence() -> None:
    [note] = [n for n in suite_notes(suite(**ONLY_REVIEWED)) if "judges no case" in n]
    assert note.startswith("contains judges no case: ")
    assert not any("no case" in n for n in suite_notes(suite(*AGREES)))


def test_the_suite_notes_name_it_by_its_token_under_a_projection() -> None:
    def mint(kind: TokenKind, value: str) -> str:
        return f"<{kind}:{len(value)}>"

    notes = suite_notes(suite(**ONLY_REVIEWED), mint=mint)
    [note] = [n for n in notes if "judges no case" in n]
    assert "contains" not in note


SUITE_PY = """\
from digline.core import Contains, JudgeReply, LlmRubric
from digline.run import Case, Response, ReviewedAnswer, Suite


def judge(prompt):
    return JudgeReply(score=1.0 if "14 days" in prompt else 0.0, reason="r")


def target(case):
    raise AssertionError("a reviewed answer calls no target")


def reviewed(case_id, output, good):
    return Case(
        id=case_id,
        reviewed_answer=ReviewedAnswer(
            output=output, check="llm_rubric", good=good, input="refund?"
        ),
    )


suite = Suite(
    tenant="acme", environment="dev", name="support",
    assertions=[
        LlmRubric(rubric="right?", judge=judge, threshold=0.7, tolerance=0.05),
        Contains(needle="days"),
    ],
    cases=[reviewed("yes", "in 14 days", True), reviewed("no", "never", False)],
    samples=2,
    min_agreement="2/2",
)
"""


@pytest.fixture
def root(tmp_path: Path) -> Path:
    (tmp_path / "suites").mkdir()
    (tmp_path / "suites" / "suite.py").write_text(SUITE_PY, encoding="utf-8")
    return tmp_path


def test_digline_run_says_it_on_stderr(root: Path) -> None:
    done = cli(root, "run", "--suite", "suites/suite.py")
    assert done.returncode == 0, done.stderr
    assert "digline: contains judges no case: " in done.stderr
    assert "judges no case" not in done.stdout


def test_where_carries_it_among_the_facts(root: Path) -> None:
    done = cli(
        root, "where", "--tenant", "acme", "--suite", "suites/suite.py", "--json"
    )
    assert done.returncode == 0, done.stderr
    found: dict[str, Any] = json.loads(done.stdout)
    assert found["idle_checks"] == ["contains"]
    said = cli(root, "where", "--tenant", "acme", "--suite", "suites/suite.py")
    assert "Checks that judge no case: contains" in said.stdout


def test_where_without_a_suite_names_none(root: Path) -> None:
    done = cli(root, "where", "--tenant", "acme", "--json")
    assert done.returncode == 0, done.stderr
    assert json.loads(done.stdout)["idle_checks"] == []
