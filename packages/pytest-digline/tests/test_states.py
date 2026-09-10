"""The four states, and the precedence between two of them. (ADR 0013 §1)

Every state here is produced by moving what the application answers and letting
the engine decide what that means. Nothing is hand-written into a document: a
fixture that asserted "this delta is regressed" would be testing the fixture.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

Baseline = Callable[[dict[str, str], dict[str, str]], Path]

FINE = {"alpha": "Acme, SATISFIED", "beta": "Acme, SATISFIED"}


def test_nothing_moved_is_a_green_run(
    pytester: pytest.Pytester, baseline: Baseline
) -> None:
    path = baseline(FINE, FINE)
    result = pytester.runpytest_subprocess("--digline-suite", str(path))
    # Four checks over two live cases, and the third case is set aside.
    result.assert_outcomes(passed=4, skipped=1)
    assert result.ret == pytest.ExitCode.OK


def test_a_check_that_got_worse_is_a_failure(
    pytester: pytest.Pytester, baseline: Baseline
) -> None:
    path = baseline(FINE, {**FINE, "alpha": "Acme, unhappy"})
    result = pytester.runpytest_subprocess("--digline-suite", str(path), "-v")

    result.assert_outcomes(passed=3, failed=1, skipped=1)
    result.stdout.fnmatch_lines(["*alpha::llm_rubric*FAILED*"])


def test_a_check_that_could_not_be_judged_is_an_error_and_not_a_failure(
    pytester: pytest.Pytester, baseline: Baseline
) -> None:
    """ADR 0001 §1: an error is neither green nor a regression.

    pytest has a state for "this never ran", and using it is the whole reason
    the mapping is worth writing down. `assert_outcomes` counts `errors`
    separately from `failed`, so this fails if the two are ever merged.
    """
    path = baseline(FINE, {**FINE, "alpha": "Acme, BOOM"})
    result = pytester.runpytest_subprocess("--digline-suite", str(path), "-v")

    result.assert_outcomes(passed=3, errors=1, skipped=1)
    result.stdout.fnmatch_lines(["*alpha::llm_rubric*ERROR*"])


def test_a_suspended_case_is_skipped_and_carries_its_reason(
    pytester: pytest.Pytester, baseline: Baseline
) -> None:
    """The state the exit code cannot express.

    A suspension never fails, so it disappears into `0`. Here it is visible, in
    its own state, with the reason the suite was made to declare.
    """
    path = baseline(FINE, FINE)
    result = pytester.runpytest_subprocess("--digline-suite", str(path), "-rs")

    result.stdout.fnmatch_lines(["SKIPPED*the refund API is down, ticket 412*"])
    # Located at the suite that declared it, never at this plugin's own source.
    assert "plugin.py" not in result.stdout.str()


def test_an_error_is_never_reported_as_a_regression(
    pytester: pytest.Pytester, baseline: Baseline
) -> None:
    """A check that was passing and now cannot be judged is an ERROR, not an F.

    This is rule 2 of `compare()` arriving at a pytest row: an error reported as
    a regression fails a pull request for the wrong reason, and one reported as
    unchanged hides a suite that stopped working. Rule 2 runs before rule 3, so
    a check cannot be both `regressed` and errored — the ordering inside
    `Check.setup()` is defensive, and this is the case that is reachable.
    """
    path = baseline(FINE, {**FINE, "alpha": "Acme, BOOM"})
    result = pytester.runpytest_subprocess("--digline-suite", str(path))

    outcomes = result.parseoutcomes()
    assert outcomes.get("errors", 0) == 1, outcomes
    assert outcomes.get("failed", 0) == 0, (
        "a check that could not be judged was reported as a regression: "
        "ADR 0001 §1 says an error is neither green nor a regression"
    )


def test_a_case_new_since_the_baseline_that_errors_is_unjudged(
    pytester: pytest.Pytester,
    repo: Callable[[dict[str, str]], Path],
    pytestconfig: pytest.Config,
) -> None:
    """The trap `_summarized()` documents, checked per row.

    Rule 1 of `compare()` classifies an absent counterpart as `new` before rule
    2 can call it `errored`, so a case added since the baseline that fails on
    its first day is `new` **and** unjudged. Selecting on the outcome alone
    would report it as a pass, and the headline would count a case the rows do
    not.
    """
    from _cycle import cycle

    path = repo(FINE)
    # A baseline with `delta` absent from the suite entirely...
    original = path.read_text(encoding="utf-8")
    cycle(path, pytester.path, promote=True)

    # ...then the case is added, and its judge cannot reach its model.
    path.write_text(
        original.replace(
            'Case(id="beta"),', 'Case(id="beta"),\n        Case(id="delta"),'
        ),
        encoding="utf-8",
    )
    (pytester.path / "answers.json").write_text(
        '{"alpha": "Acme, SATISFIED", "beta": "Acme, SATISFIED",'
        ' "delta": "Acme, BOOM"}',
        encoding="utf-8",
    )
    cycle(path, pytester.path, promote=False)

    result = pytester.runpytest_subprocess("--digline-suite", str(path), "-v")
    result.stdout.fnmatch_lines(["*delta::llm_rubric*ERROR*"])
