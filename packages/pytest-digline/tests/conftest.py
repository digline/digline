"""`pytester`, and a suite to point this plugin at.

Every test here drives a **real pytest run**, in a temporary directory, through
`pytester`. Nothing asserts against the plugin's internals: what this package
is, is what a pytest report says, and a test that read a delta out of a
collector would pass while the report said the wrong thing.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest
from _cycle import cycle

pytest_plugins = ["pytester"]

#: A suite whose target answers from a table, so a run costs nothing and is
#: reproducible. Written into the temporary repository by `repo` below.
SUITE = """
from digline.core import Contains, LlmRubric, JudgeReply
from digline.run import Case, Response, Suite

ANSWERS = {}

def judge(prompt: str) -> JudgeReply:
    # The tokens are shouted so they cannot collide with the rubric, which is
    # part of the composed prompt: a rubric reading "is it good?" made every
    # answer score 1.0 and cost an afternoon.
    if "BOOM" in prompt:
        # An assertion that raises is recorded as an errored verdict by the
        # driver: could not judge, which is neither green nor a regression.
        raise RuntimeError("the judge could not reach its model")
    return JudgeReply(score=1.0 if "SATISFIED" in prompt else 0.0, reason="looked")

suite = Suite(
    tenant="acme",
    environment="staging",
    name="support",
    assertions=[
        Contains(needle="Acme"),
        LlmRubric(
            rubric="acceptable reply?", judge=judge, threshold=0.7, tolerance=0.05
        ),
    ],
    cases=[
        Case(id="alpha"),
        Case(id="beta"),
        Case(id="gamma", suspended="the refund API is down, ticket 412"),
    ],
)

def target(case: Case) -> Response:
    import json, pathlib
    table = json.loads(pathlib.Path(__file__).with_name("answers.json").read_text())
    return Response(output=table[case.id], cost_usd=0.001, latency_ms=10.0)
"""


@pytest.fixture
def repo(pytester: pytest.Pytester) -> Callable[[dict[str, str]], Path]:
    """A repository with a suite in it, and a hook to change what it answers.

    Returns a callable so a test can move an answer and produce a second run:
    the regression, the error and the improvement are all one edit to this
    table, which keeps the fixtures honest — every state is produced by the
    engine rather than hand-written into a document.
    """

    def write(answers: dict[str, str]) -> Path:
        path = pytester.path / "suite.py"
        path.write_text(SUITE, encoding="utf-8")
        (pytester.path / "answers.json").write_text(
            json.dumps(answers), encoding="utf-8"
        )
        return path

    return write


@pytest.fixture
def baseline(
    pytester: pytest.Pytester, repo: Callable[[dict[str, str]], Path]
) -> Callable[[dict[str, str], dict[str, str]], Path]:
    """A suite with a promoted baseline and a later run to compare against it.

    Two tables: what the application answered when the baseline was approved,
    and what it answers now. Every state this plugin reports is produced by
    moving the second one — the engine decides what that means, not the test.
    """

    def build(before: dict[str, str], after: dict[str, str]) -> Path:
        path = repo(before)
        cycle(path, pytester.path, promote=True)
        repo(after)
        cycle(path, pytester.path, promote=False)
        return path

    return build
