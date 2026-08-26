"""Helpers shared by the tests that drive the CLI in a subprocess.

Plain functions, deliberately not fixtures and deliberately not a test module.
A test module that imports another test module makes collection order matter:
`conftest.py` is imported before any test, so a fixture reached through
`tests.test_cli` is a fixture that depends on a file pytest has not read yet.
Everything shared lives here, `conftest.py` builds the fixtures on top, and no
test module imports another.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from digline.cli import EXIT_OK

__all__ = ["SUITE_SOURCE", "cli", "git", "run_key", "write_suite"]

SUITE_SOURCE = """\
from digline.core import Contains, CostBudget, Disclosure, JudgeReply, LlmRubric
from digline.run import Case, Response, Suite

QUALITY = {"capital-fr": %(fr)s}


def _judge(prompt):
    score = QUALITY.get(_judge.case, 1.0)
    return JudgeReply(score=score, reason="judged: " + prompt[:12])


_judge.case = "capital-it"

suite = Suite(
    tenant="acme-bank",
    environment="staging",
    name="qa",
    assertions=[
        Contains(needle="Rome"),
        CostBudget(max_usd=0.10, tolerance=0.02),
        LlmRubric(rubric="answers?", judge=_judge, threshold=0.7, tolerance=0.05),
    ],
    cases=[Case(id="capital-it"), Case(id="capital-fr")%(extra)s],
    disclosure=Disclosure(run_metadata=frozenset({"model"})),
)


def target(case):
    if case.id == "flaky":
        raise TimeoutError("provider did not answer")
    _judge.case = case.id
    return Response(
        output="The capital is Rome.",
        input="What is the capital?",
        cost_usd=0.01,
        latency_ms=100.0,
    )
"""


def write_suite(root: Path, *, fr_score: str = "1.0", extra: str = "") -> Path:
    path = root / "suite_qa.py"
    path.write_text(SUITE_SOURCE % {"fr": fr_score, "extra": extra}, encoding="utf-8")
    return path


def cli(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "digline.cli", *args],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )


def git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def run_key(root: Path, *extra: str) -> str:
    done = cli(root, "run", "--suite", "suite_qa.py", *extra)
    assert done.returncode == EXIT_OK, done.stderr
    return done.stdout.strip()
