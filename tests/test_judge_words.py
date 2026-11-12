"""The judge's words where its samples disagreed: kept in the run, read under
the case by `explain`'s terminal reading, and in no fact. (ADR 0012 §4, as
amended 2026-11-12)

Found in a first use outside the project, on a Java application with a judged
suite: a judge passed an answer twice and failed it once, the run kept the
mean, and nothing a person could read said what the judge had said. The suite
here records no answers (`record_responses` is off, its default): the reasons
are the verdict's, not the answer's.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from tests._helpers import cli

SUITE_PY = """\
import itertools

from digline.core import JudgeReply, LlmRubric
from digline.run import Case, Response, Suite

SAID = itertools.cycle([
    (1.0, "MARK-A polite and right"),
    (0.0, "MARK-B it never names the date"),
    (1.0, "MARK-C right, if terse"),
    (1.0, "MARK-D clean"),
    (1.0, "MARK-D clean"),
    (1.0, "MARK-D clean"),
])


def judge(prompt):
    score, reason = next(SAID)
    return JudgeReply(score=score, reason=reason)


def target(case):
    return Response(output="yes", cost_usd=0.0)


suite = Suite(
    tenant="acme", environment="dev", name="support",
    assertions=[
        LlmRubric(rubric="polite?", judge=judge, threshold=0.5, tolerance=0.05)
    ],
    cases=[Case(id="torn"), Case(id="agreed")],
    samples=3,
    min_agreement="2/3",
)
"""


@pytest.fixture
def root(tmp_path: Path) -> Path:
    (tmp_path / "suite.py").write_text(SUITE_PY, encoding="utf-8")
    done = cli(tmp_path, "run", "--suite", "suite.py")
    assert done.returncode == 0, done.stderr
    return tmp_path


def reasons(root: Path) -> dict[str, str]:
    """Each case's one verdict's reason, read from the run document."""
    [path] = (root / ".digline" / "acme" / "runs" / "support").glob("*.json")
    document = json.loads(path.read_text(encoding="utf-8"))
    return {
        str(result["case_id"]): str(result["verdicts"][0]["reason"])
        for result in document["results"]
    }


def test_the_run_keeps_what_each_sample_said_where_they_disagreed(root: Path) -> None:
    found = reasons(root)
    torn, agreed = {"reason": found["torn"]}, {"reason": found["agreed"]}
    for mark in ("MARK-A", "MARK-B", "MARK-C"):
        assert mark in torn["reason"]
    # Unanimous: the mean's reason alone, as before.
    assert "MARK-D" not in agreed["reason"]


def test_explain_says_them_under_the_case_after_the_facts(root: Path) -> None:
    done = cli(root, "explain", "--suite", "suite.py", "--run", "latest")
    assert done.returncode == 0, done.stderr
    lines = done.stdout.splitlines()
    heading = lines.index("What the judge said, where its samples disagreed")
    assert lines[heading + 1] == "torn · llm_rubric"
    assert "MARK-B it never names the date" in lines[heading + 2]
    assert "agreed · llm_rubric" not in lines
    # After every fact: nothing of the facts' groups follows it.
    assert "What it found" in lines[:heading]


def test_no_fact_and_no_json_carries_them(root: Path) -> None:
    done = cli(root, "explain", "--suite", "suite.py", "--run", "latest", "--json")
    assert done.returncode == 0, done.stderr
    for mark in ("MARK-A", "MARK-B", "MARK-C", "What the judge said"):
        assert mark not in done.stdout


def test_the_run_report_shows_the_same_reason(root: Path) -> None:
    done = cli(
        root, "report", "--suite", "suite.py", "--run", "latest", "--locale", "en"
    )
    assert done.returncode == 0, done.stderr
    assert "MARK-B it never names the date" in done.stdout


def test_a_sample_that_could_not_judge_is_said_under_its_case() -> None:
    """The second half of the amendment: a sample in error, beside two that
    agreed, is said under the case too, with the words its error carried."""
    from digline.core import JudgeReply, LlmRubric
    from digline.report import judge_words
    from digline.run import Case, Response, Suite, execute

    replies = iter([1.0, "boom", 1.0])

    def judge(prompt: str) -> JudgeReply:
        reply = next(replies)
        if isinstance(reply, str):
            raise ValueError("MARK-E the judge replied with no JSON object")
        return JudgeReply(score=reply, reason="fine")

    suite = Suite(
        tenant="acme",
        environment="dev",
        name="support",
        assertions=[
            LlmRubric(rubric="polite?", judge=judge, threshold=0.5, tolerance=0.05)
        ],
        cases=[Case(id="one-failed")],
        samples=3,
        min_agreement="2/3",
    )
    run = execute(
        suite,
        lambda case: Response(output="yes", cost_usd=0.0),
        created_at="2026-11-12T00:00:00+00:00",
    )
    lines = judge_words(run, locale="en")
    assert lines[1] == "one-failed · llm_rubric"
    assert "MARK-E" in lines[2]
