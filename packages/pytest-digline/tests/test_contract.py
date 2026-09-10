"""What survives the translation into pytest, and what does not. (ADR 0013 §7)

The exit codes are digline's contract: `0` proceed, `1` stop and report what got
worse, `2` stop — the run could not be judged. pytest cannot carry that
distinction, and this file records the loss as a property rather than leaving it
to be discovered by somebody building a gate on it.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

Baseline = Callable[[dict[str, str], dict[str, str]], Path]

FINE = {"alpha": "Acme, SATISFIED", "beta": "Acme, SATISFIED"}


def test_a_clean_comparison_exits_zero(
    pytester: pytest.Pytester, baseline: Baseline
) -> None:
    path = baseline(FINE, FINE)
    result = pytester.runpytest_subprocess("--digline-suite", str(path))
    assert result.ret == pytest.ExitCode.OK


def test_a_regression_and_an_unjudged_run_both_exit_one(
    pytester: pytest.Pytester, baseline: Baseline
) -> None:
    """The distinction digline draws and pytest erases.

    `digline compare` exits `1` for a regression and `2` for a run it could not
    judge. Here both are `1`, because pytest's process code says only that
    something was not green. The trichotomy survives in the *report* — `F` and
    `E` are counted apart, `-rE` lists the errored rows, `--junit-xml` keeps
    them apart — and a job that needs `1` versus `2` runs `digline compare`.

    Written as an assertion rather than a comment so that it is a decision
    somebody has to revisit if it ever changes.
    """
    worse = baseline(FINE, {**FINE, "alpha": "Acme, unhappy"})
    regressed = pytester.runpytest_subprocess("--digline-suite", str(worse))

    unjudged_path = baseline(FINE, {**FINE, "alpha": "Acme, BOOM"})
    unjudged = pytester.runpytest_subprocess("--digline-suite", str(unjudged_path))

    assert regressed.ret == pytest.ExitCode.TESTS_FAILED
    assert unjudged.ret == pytest.ExitCode.TESTS_FAILED
    # …and they are still told apart where it matters.
    assert regressed.parseoutcomes().get("failed", 0) == 1
    assert unjudged.parseoutcomes().get("errors", 0) == 1


def test_a_suspension_alone_never_fails_a_run(
    pytester: pytest.Pytester, baseline: Baseline
) -> None:
    """A decision is not an outcome: the set-aside case is visible and green."""
    path = baseline(FINE, FINE)
    result = pytester.runpytest_subprocess("--digline-suite", str(path))
    assert result.ret == pytest.ExitCode.OK
    assert result.parseoutcomes().get("skipped", 0) == 1


def test_k_selects_a_single_check(
    pytester: pytest.Pytester, baseline: Baseline
) -> None:
    """`-k` has to reach these rows, which is why they are injected before the
    hook that implements it rather than after."""
    path = baseline(FINE, {**FINE, "alpha": "Acme, unhappy"})
    result = pytester.runpytest_subprocess(
        "--digline-suite", str(path), "-k", "llm_rubric"
    )
    outcomes = result.parseoutcomes()
    assert outcomes.get("deselected", 0) >= 1
    assert outcomes.get("failed", 0) == 1


def test_the_rows_join_a_repository_s_ordinary_tests(
    pytester: pytest.Pytester, baseline: Baseline
) -> None:
    """The point of the package: one report, not two.

    A repository gating on digline still has its own tests, and both have to be
    in the same run — otherwise this is `digline compare` with extra steps.
    """
    path = baseline(FINE, {**FINE, "alpha": "Acme, unhappy"})
    pytester.makepyfile(test_ordinary="def test_one(): assert True")

    result = pytester.runpytest_subprocess("--digline-suite", str(path))

    result.assert_outcomes(passed=4, failed=1, skipped=1)


def test_the_command_line_replaces_the_ini_list_rather_than_adding_to_it(
    pytester: pytest.Pytester, baseline: Baseline
) -> None:
    """Narrowing a run to one suite has to be expressible.

    A flag that added to the configured list would make it impossible: there
    would be no way to say "this one instead".
    """
    path = baseline(FINE, FINE)
    pytester.makeini(
        f"""
        [pytest]
        digline_suites = {path}
            /nowhere/absent.py
        """
    )
    # The ini alone names a suite that does not exist, so it must refuse…
    assert pytester.runpytest_subprocess().ret == pytest.ExitCode.USAGE_ERROR
    # …and naming one on the command line has to replace the list, not join it.
    assert (
        pytester.runpytest_subprocess("--digline-suite", str(path)).ret
        == pytest.ExitCode.OK
    )
