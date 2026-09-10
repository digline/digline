"""What a row says, and where the words come from. (ADR 0013 §6)

Two rules, and both are about not having a second source of truth: the sentence
on a row is the report's own, and the headline is `headline().sentence`. A
plugin that composed either would be a fourth prose rendering of one comparison
with nothing binding it to the other three.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from _cycle import cycle

from digline.core import compare
from digline.host import load_suite, need_baseline, read_run, resolve_key
from digline.report import check_line, config_changes, headline
from digline.store import FileResultStore

Baseline = Callable[[dict[str, str], dict[str, str]], Path]

FINE = {"alpha": "Acme, SATISFIED", "beta": "Acme, SATISFIED"}


def _compared(path: Path, root: Path):
    """The comparison the plugin will have made, made again out here.

    The test computes it from the same stored documents through the same public
    functions, so what it asserts is "the plugin printed the report's sentence"
    and not "the plugin printed the sentence this test also hardcodes".
    """
    suite, _loaded = load_suite(str(path), root=root)
    store = FileResultStore(str(root))
    run = read_run(store, suite, resolve_key(store, suite, "latest").key)
    baseline_run = need_baseline(store, suite)
    return compare(run, baseline_run), run, baseline_run


def test_a_failing_row_prints_the_report_s_own_sentence(
    pytester: pytest.Pytester, baseline: Baseline
) -> None:
    path = baseline(FINE, {**FINE, "alpha": "Acme, unhappy"})
    comparison, _run, _base = _compared(path, pytester.path)
    coincides = config_changes(comparison.config_changes, "en")
    regressed = comparison.regressed
    assert regressed, "the fixture produced no regression to check the line of"
    expected = check_line(regressed[0], locale="en", coincides=coincides)

    result = pytester.runpytest_subprocess("--digline-suite", str(path))

    assert expected in result.stdout.str(), (
        f"the row did not carry the report's line.\nexpected: {expected!r}"
    )


def test_a_failing_row_carries_no_traceback(
    pytester: pytest.Pytester, baseline: Baseline
) -> None:
    path = baseline(FINE, {**FINE, "alpha": "Acme, unhappy"})
    result = pytester.runpytest_subprocess("--digline-suite", str(path))

    text = result.stdout.str()
    assert "Traceback" not in text
    assert "_pytest" not in text
    assert "plugin.py" not in text


def test_an_errored_row_carries_no_traceback_either(
    pytester: pytest.Pytester, baseline: Baseline
) -> None:
    """The half that fails without `pytest_runtest_makereport`.

    pytest consults `repr_failure` for the `call` phase alone, so a setup-phase
    exception — which is the only way to produce an ERROR — goes through
    `_repr_failure_py` and prints a full traceback with pytest's own frames in
    it. Remove the wrapper in `plugin.py` and this is the test that goes red.
    """
    path = baseline(FINE, {**FINE, "alpha": "Acme, BOOM"})
    result = pytester.runpytest_subprocess("--digline-suite", str(path))

    text = result.stdout.str()
    assert "ERROR at setup" in text, "the fixture produced no errored check"
    assert "Traceback" not in text
    assert "_pytest" not in text
    assert "CouldNotJudge" not in text, (
        "the exception class leaked into the report: the reader is being shown "
        "this plugin's internals instead of what happened to their check"
    )


def test_the_headline_is_printed_once_and_is_the_report_s(
    pytester: pytest.Pytester, baseline: Baseline
) -> None:
    """Once, and byte for byte.

    Once because it is a statement about the run: forty copies of one sentence
    is forty lines a reader learns to skip, taking the row detail beside it.
    Byte for byte because a gate and the document a customer opens must never
    say two different things about one run.
    """
    path = baseline(FINE, {**FINE, "alpha": "Acme, unhappy", "beta": "Acme, unhappy"})
    comparison, run, base = _compared(path, pytester.path)
    sentence = headline(comparison, run, base, locale="en").sentence

    result = pytester.runpytest_subprocess("--digline-suite", str(path))

    text = result.stdout.str()
    assert text.count(sentence) == 1, (
        f"the headline appeared {text.count(sentence)} times, not once"
    )
    assert comparison.counts.get("regressed", 0) >= 2, (
        "the fixture produced fewer than two failing rows, so 'once' would be "
        "true by accident"
    )


def test_a_missing_baseline_refuses_loudly_instead_of_collecting_nothing(
    pytester: pytest.Pytester, repo: Callable[[dict[str, str]], Path]
) -> None:
    """Fixed decision 3, at the front end.

    A suite with no baseline cannot be gated. Collecting zero rows would let a
    green pytest run mean "nothing to check", which is the vacuously green
    assertion this project refuses. It is pytest's usage error — exit 4 — which
    is what digline's own `64` means: the front end refusing the request.
    """
    path = repo(FINE)
    cycle(path, pytester.path, promote=False)

    result = pytester.runpytest_subprocess("--digline-suite", str(path))

    assert result.ret == pytest.ExitCode.USAGE_ERROR
    result.stderr.fnmatch_lines(["*no baseline*"])


def test_a_suite_that_does_not_exist_refuses_by_name(
    pytester: pytest.Pytester,
) -> None:
    result = pytester.runpytest_subprocess("--digline-suite", "nope/suite.py")
    assert result.ret == pytest.ExitCode.USAGE_ERROR
    result.stderr.fnmatch_lines(["*no such file*"])
