"""A gate that was not compared, as a pytest row. (ADR 0012 §3)

digline 0.15.2 stopped counting a delta whose two sides were measured over
different numbers of cases: it is an incomparability, so `Comparison.counts`
leaves it out and `exit_code()` cannot read one. This plugin kept reading
`outcome == "regressed"` and failed the row anyway — one fact answered twice,
which is exactly what `_failing`'s docstring says must not happen.

Produced the way `test_states.py` produces every state: by moving what the
application answers and letting the engine decide what that means. Here the
move is the one the advisory describes — a case the endpoint makes unjudgeable,
which leaves the confusion matrix and shrinks the denominator underneath a
run-level gate.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from _cycle import cycle

#: Four labelled cases and a lenient run-level gate. Lenient on purpose: at
#: `threshold=0.5` the score below stays a *movement* rather than a flip, which
#: is the shape the drift was in. The rubric's own threshold does the failing.
SUITE = """
import json
import pathlib

from digline.core import JudgeReply, LlmRubric, Recall
from digline.run import Case, Response, Suite


def judge(prompt: str) -> JudgeReply:
    if "BOOM" in prompt:
        # The endpoint's move: the check cannot be judged, so the case leaves
        # the matrix. No repository access is needed for this.
        raise RuntimeError("the judge could not reach its model")
    return JudgeReply(score=1.0 if "SATISFIED" in prompt else 0.0, reason="looked")


suite = Suite(
    tenant="acme",
    environment="staging",
    name="support",
    assertions=[
        LlmRubric(
            rubric="acceptable reply?", judge=judge, threshold=0.7, tolerance=0.05
        ),
    ],
    run_assertions=[Recall(over="llm_rubric", threshold=0.5, tolerance=0.0)],
    cases=[
        Case(id="alpha", label="positive"),
        Case(id="beta", label="positive"),
        Case(id="gamma", label="positive"),
        Case(id="delta", label="positive"),
    ],
)


def target(case: Case) -> Response:
    table = json.loads(
        (pathlib.Path(__file__).with_name("answers.json")).read_text()
    )
    return Response(output=table[case.id], cost_usd=0.001, latency_ms=10.0)
"""

ALL_WELL = {c: "Acme, SATISFIED" for c in ("alpha", "beta", "gamma", "delta")}

#: One case the endpoint made unjudgeable and one that genuinely got worse. The
#: gate reads 2/3 here against 4/4 in the reference — a drop, over a denominator
#: that moved, with both sides still above 0.5.
SHRUNKEN = {**ALL_WELL, "gamma": "Acme, BOOM", "delta": "Acme, unhappy"}


def written(pytester: pytest.Pytester, answers: dict[str, str]) -> Path:
    path = pytester.path / "suite.py"
    path.write_text(SUITE, encoding="utf-8")
    (pytester.path / "answers.json").write_text(json.dumps(answers), encoding="utf-8")
    return path


def compared(pytester: pytest.Pytester) -> Path:
    path = written(pytester, ALL_WELL)
    cycle(path, pytester.path, promote=True)
    written(pytester, SHRUNKEN)
    cycle(path, pytester.path, promote=False)
    return path


def test_a_gate_that_was_not_compared_does_not_fail_its_row(
    pytester: pytest.Pytester,
) -> None:
    """The drift, and the whole of this release.

    `recall` fell from 1.000000 over four cases to 0.666667 over three, which is
    not a fall: the two are not the same measurement. digline says so — the row
    is in `Comparison.incomparable`, it is in none of the `counts`, and the run's
    own exit code does not read it. Before this fix the plugin failed the row
    regardless, so `digline compare` and `pytest` disagreed about one run.
    """
    path = compared(pytester)
    result = pytester.runpytest_subprocess("--digline-suite", str(path), "-v")

    result.stdout.fnmatch_lines(["*recall*PASSED*"])
    result.stdout.no_fnmatch_line("*recall*FAILED*")


def test_the_case_that_could_not_be_judged_is_still_an_error(
    pytester: pytest.Pytester,
) -> None:
    """The control this needs, and the reason the run is not quietly green.

    Nothing here excuses the case the endpoint broke: its own row is ERROR, the
    state ADR 0001 §1 reserves for a check that could not be judged, and the run
    still exits 2. What the fix withdraws is a *comparison*, never a verdict.
    """
    path = compared(pytester)
    result = pytester.runpytest_subprocess("--digline-suite", str(path), "-v")

    result.stdout.fnmatch_lines(["*gamma::llm_rubric*ERROR*"])
    assert result.ret != pytest.ExitCode.OK


def test_a_check_that_really_got_worse_still_fails(
    pytester: pytest.Pytester,
) -> None:
    """The other control, and the one that keeps this from being a licence.

    `delta` answered worse and nothing about its denominator moved, so its row
    is FAILED exactly as it was. The exclusion is keyed on the incomparability
    and on nothing else.
    """
    path = compared(pytester)
    result = pytester.runpytest_subprocess("--digline-suite", str(path), "-v")

    result.stdout.fnmatch_lines(["*delta::llm_rubric*FAILED*"])
