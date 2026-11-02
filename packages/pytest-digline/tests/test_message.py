"""What a row says, and where the words come from. (ADR 0013 §6)

Two rules, and both are about not having a second source of truth: the sentence
on a row is the report's own, and the headline is `headline().sentence`. A
plugin that composed either would be a fourth prose rendering of one comparison
with nothing binding it to the other three.
"""

from __future__ import annotations

import re
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

#: A row's header in the FAILURES or ERRORS section, `___ alpha::llm_rubric ___`
#: or `___ ERROR at setup of alpha::llm_rubric ___`; a block ends at the next
#: row's header or at the next section's `=== … ===`.
_ROW_HEADER = re.compile(r"^_{3,} (?P<title>.+?) _{3,}$")
_SECTION = re.compile(r"^={3,} .+ ={3,}$")


def _row_message(text: str, title: str) -> str:
    """What pytest printed for one row: the lines under its header, up to the
    next header or section.

    The traceback rule is about the row's message, so it is read there and not
    in the whole of stdout, where another plugin's warning may name `_pytest`
    or a file called `plugin.py` with nothing leaking from this one.
    """
    lines = text.splitlines()
    starts = [
        i
        for i, line in enumerate(lines)
        if (m := _ROW_HEADER.match(line)) and m["title"] == title
    ]
    assert len(starts) == 1, f"no single row headed {title!r} in:\n{text}"
    block: list[str] = []
    for line in lines[starts[0] + 1 :]:
        if _ROW_HEADER.match(line) or _SECTION.match(line):
            break
        block.append(line)
    assert block, f"the row {title!r} printed nothing under its header:\n{text}"
    return "\n".join(block)


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

    message = _row_message(result.stdout.str(), "alpha::llm_rubric")
    assert "Traceback" not in message, message
    assert "_pytest" not in message, message
    assert "plugin.py" not in message, message


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
    message = _row_message(text, "ERROR at setup of alpha::llm_rubric")
    assert "Traceback" not in message, message
    assert "_pytest" not in message, message
    assert "CouldNotJudge" not in message, (
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
    sentence = headline(comparison, run, base, locale="en", declared=None).sentence

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


def _rewrite_baseline(root: Path, edit: Callable[[str], str]) -> None:
    (stored,) = root.glob(".digline/*/baselines/*.json")
    stored.write_text(edit(stored.read_text(encoding="utf-8")), encoding="utf-8")


def _projected(document: str) -> str:
    import secrets

    from digline.core import project, run_from_json, run_to_json

    rows: dict[tuple[str, str], str] = {}
    return run_to_json(
        project(
            run_from_json(document),
            lambda kind, text: rows.setdefault((kind, text), secrets.token_urlsafe(16)),
        )
    )


def _unidentified(document: str) -> str:
    import json

    raw = json.loads(document)
    raw["results"][0]["verdicts"][0]["assertion_id"] = ""
    return json.dumps(raw)


@pytest.mark.parametrize(
    ("edit", "named"),
    [
        pytest.param(_projected, "DifferentRegimesError", id="compare-refuses"),
        # The verdict's refusal arrives as the document's, since ADR 0054 §8:
        # the store's reader names the file it could not read.
        pytest.param(_unidentified, "DocumentRefusedError", id="read-refuses"),
    ],
)
def test_a_refusal_from_digline_is_a_usage_error_not_a_crash(
    pytester: pytest.Pytester,
    baseline: Baseline,
    edit: Callable[[str], str],
    named: str,
) -> None:
    """Every refusal in `digline.host.REFUSALS` is the front end declining the
    request, which is pytest's exit 4, as `UsageError` already was. Was:
    `INTERNALERROR` and exit 3, which reads as a crash of pytest or of this
    plugin. (Delta-pass over 0.25.1)"""
    path = baseline(FINE, FINE)
    _rewrite_baseline(pytester.path, edit)

    result = pytester.runpytest_subprocess("--digline-suite", str(path))

    assert result.ret == pytest.ExitCode.USAGE_ERROR
    result.stderr.fnmatch_lines([f"*digline: {named}:*"])
    assert "INTERNALERROR" not in result.stdout.str() + result.stderr.str()
