"""What every front end that runs a suite says about it before the first call.
(#396; ADR 0024 §6.1, §6.4; #386)

`suite_notes` is the one place the lines are composed: a check whose class
declares no `KIND`, then each tolerance that switches its check off. Until #396
the `KIND` sentence was the CLI's own, so the other front ends could not say
it, and `run --json` and `rejudge` said neither. The MCP `run` tool and
`pytest --digline-run` are held to the same lines in their own packages.
"""

from __future__ import annotations

import json
from pathlib import Path

from tests._helpers import cli

from digline.run import suite_notes
from digline.run.suite import BlindTolerance

SUITE_PY = """
from dataclasses import dataclass

from digline.core import (
    TEXT_ONLY,
    AssertionBase,
    Contains,
    EvaluatorInputs,
    JudgeReply,
    LlmRubric,
    OutputKind,
    Verdict,
)
from digline.run import Case, Response, Suite


@dataclass(frozen=True, slots=True)
class NoKind(AssertionBase):
    name: str = "no_kind"
    threshold: float = 0.5
    tolerance: float = 0.0
    accepts: frozenset[OutputKind] = TEXT_ONLY

    def __call__(self, inputs: EvaluatorInputs) -> Verdict:
        return self._binary(True, "fine")


def judge(prompt):
    return JudgeReply(score=1.0, reason="looked")


suite = Suite(
    tenant="acme-bank",
    environment="staging",
    name="noted",
    assertions=[
        Contains(needle="Rome"),
        NoKind(),
        NoKind(name="other_kind"),
        LlmRubric(rubric="ok?", judge=judge, threshold=0.5, tolerance=0.5,
                  name="loose"),
    ],
    cases=[Case(id="one")],
    record_responses=True,
)


def target(case):
    return Response(output="Rome", input="capital?")
"""

KIND = (
    "no_kind, other_kind declare no KIND, so the shape reading leaves them out; "
    'declare KIND = "judged" or "deterministic" on their classes to have them read'
)
BLIND = BlindTolerance("loose", 0.5, 0.5).sentence()


def test_the_cli_and_its_json_say_the_same_lines(repo: Path) -> None:
    (repo / "suite_noted.py").write_text(SUITE_PY, encoding="utf-8")

    done = cli(repo, "run", "--suite", "suite_noted.py", "--json")

    assert done.returncode == 0, done.stderr
    assert json.loads(done.stdout)["notes"] == [KIND, BLIND]
    assert f"digline: {KIND}\ndigline: {BLIND}\n" in done.stderr


def test_rejudge_says_them_too(repo: Path) -> None:
    """A re-judge loads the suite and judges with it, and under
    `--judge-samples` a judge whose class declares no `KIND` is not repeated:
    the default decides there as well, so it is said there as well."""
    (repo / "suite_noted.py").write_text(SUITE_PY, encoding="utf-8")
    source = cli(repo, "run", "--suite", "suite_noted.py").stdout.strip()

    done = cli(repo, "rejudge", "--suite", "suite_noted.py", "--run", source, "--json")

    assert done.returncode == 0, done.stderr
    assert json.loads(done.stdout)["notes"] == [KIND, BLIND]
    assert f"digline: {KIND}\ndigline: {BLIND}\n" in done.stderr


def test_a_suite_with_nothing_to_say_has_an_empty_list(repo: Path) -> None:
    """The control, and why the key is always present: an empty list is a
    suite that was read, not a digline that did not look."""
    done = cli(repo, "run", "--suite", "suite_qa.py", "--json")

    assert done.returncode == 0, done.stderr
    assert json.loads(done.stdout)["notes"] == []
    assert "KIND" not in done.stderr
    assert "covers every movement" not in done.stderr


def test_an_ordinary_suite_has_no_notes() -> None:
    """The function itself, without a front end: every check declares its kind
    and no tolerance is blind."""
    from digline.core import Contains, JudgeReply, LlmRubric
    from digline.run import Case, Suite

    def judge(prompt: str) -> JudgeReply:
        return JudgeReply(score=1.0, reason="looked")

    suite = Suite(
        tenant="acme-bank",
        environment="staging",
        name="plain",
        assertions=[
            Contains(needle="Rome"),
            LlmRubric(rubric="ok?", judge=judge, threshold=0.5, tolerance=0.05),
        ],
        cases=[Case(id="one")],
    )
    assert suite_notes(suite) == ()
