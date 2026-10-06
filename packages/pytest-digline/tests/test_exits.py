"""What the CLI's `main()` catches, caught here too. (#475)

`digline.cli.main()` has four branches: a usage error, a refusal or an
`OSError`, a `SystemExit` from code digline ran, and anything else. Before #475
this plugin had the first two without `OSError`, so after a suite had loaded the
other three reached pytest as `INTERNALERROR` and exit 3, which reads as a crash
of pytest or of this plugin. Each test names the row of the measurement on the
issue it holds.

Every sentence is the whole one, because the reader ran the command (ADR 0043
§3), and passes through `visible()` (ADR 0041 §4.1, rule 3).
"""

from __future__ import annotations

import os
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

Baseline = Callable[[dict[str, str], dict[str, str]], Path]

FINE = {"alpha": "Acme, SATISFIED", "beta": "Acme, SATISFIED"}

MARK = "ROWMARK-IT60X0542811101"

without_mode_000 = pytest.mark.skipif(
    sys.platform == "win32" or os.geteuid() == 0,
    reason="mode 000 denies nothing to root, and Windows has no such mode",
)


def _append(path: Path, code: str) -> None:
    path.write_text(path.read_text(encoding="utf-8") + "\n" + code, encoding="utf-8")


def _preflight(path: Path, body: str) -> None:
    """Replace the suite's target with one whose `preflight` runs `body`."""
    _append(
        path,
        "class _Target:\n"
        "    def __call__(self, case):\n"
        "        return Response(output='Acme, SATISFIED', cost_usd=0.001, "
        "latency_ms=1.0)\n"
        "    def preflight(self, cases):\n"
        f"        {body}\n"
        "target = _Target()\n",
    )


def _no_crash(result: pytest.RunResult) -> str:
    out = result.stdout.str() + result.stderr.str()
    assert "INTERNALERROR" not in out
    return out


@without_mode_000
def test_o1_a_baseline_digline_cannot_read_is_a_usage_error(
    pytester: pytest.Pytester, baseline: Baseline
) -> None:
    """O1: an `OSError` digline asked for, as the CLI refuses it with 64."""
    path = baseline(FINE, FINE)
    (stored,) = pytester.path.glob(".digline/*/baselines/*.json")
    stored.chmod(0)
    try:
        result = pytester.runpytest_subprocess("--digline-suite", str(path))
    finally:
        stored.chmod(0o644)

    assert result.ret == pytest.ExitCode.USAGE_ERROR
    _no_crash(result)
    result.stderr.fnmatch_lines(["*digline: PermissionError: *Errno 13*"])


@without_mode_000
def test_o2_a_run_digline_cannot_write_is_a_usage_error(
    pytester: pytest.Pytester, baseline: Baseline
) -> None:
    """O2: the same, from `write_run` under `--digline-run`."""
    path = baseline(FINE, FINE)
    (runs,) = pytester.path.glob(".digline/*/runs/*")
    runs.chmod(0o555)
    try:
        result = pytester.runpytest_subprocess(
            "--digline-suite", str(path), "--digline-run"
        )
    finally:
        runs.chmod(0o755)

    assert result.ret == pytest.ExitCode.USAGE_ERROR
    _no_crash(result)
    result.stderr.fnmatch_lines(["*digline: PermissionError: *Errno 13*"])


def test_o4_an_oserror_the_suites_code_raises_is_a_usage_error_with_its_message(
    pytester: pytest.Pytester, baseline: Baseline
) -> None:
    """O4: a `preflight`'s `OSError`. The CLI refuses it by its type, and the
    whole sentence reaches the person who ran the command, message included."""
    path = baseline(FINE, FINE)
    _preflight(path, f"open('/nonexistent/{MARK}')")

    result = pytester.runpytest_subprocess(
        "--digline-suite", str(path), "--digline-run"
    )

    assert result.ret == pytest.ExitCode.USAGE_ERROR
    _no_crash(result)
    result.stderr.fnmatch_lines([f"*digline: FileNotFoundError: *{MARK}*"])


def test_s2_a_target_that_calls_sys_exit_is_refused_with_its_location(
    pytester: pytest.Pytester, baseline: Baseline
) -> None:
    """S2: ADR 0041 §4.3. The location is the suite's line, and none of this
    plugin's frames is given as where the code was reached from."""
    path = baseline(FINE, FINE)
    _append(path, f"def target(case):\n    import sys\n    sys.exit({MARK!r})\n")

    result = pytester.runpytest_subprocess(
        "--digline-suite", str(path), "--digline-run"
    )

    assert result.ret == pytest.ExitCode.USAGE_ERROR
    out = _no_crash(result)
    result.stderr.fnmatch_lines(
        [f"*digline: code digline ran raised SystemExit('{MARK}') at *suite.py:*"]
    )
    assert "pytest_digline" not in out


def test_x2_anything_else_is_not_anticipated_and_not_a_crash(
    pytester: pytest.Pytester, baseline: Baseline
) -> None:
    """X2: the CLI exits 70 with the traceback. Here it is pytest's 3, with the
    traceback and digline's sentence in place of `INTERNALERROR`."""
    path = baseline(FINE, FINE)
    _preflight(path, f"raise ValueError({MARK!r})")

    result = pytester.runpytest_subprocess(
        "--digline-suite", str(path), "--digline-run"
    )

    assert result.ret == pytest.ExitCode.INTERNAL_ERROR
    out = _no_crash(result)
    result.stderr.fnmatch_lines(
        ["Traceback (most recent call last):", f"*ValueError: {MARK}"]
    )
    assert "the failure above was not anticipated" in out


@pytest.mark.parametrize(
    "refusal",
    [
        pytest.param("digline.core import RefusedError as R", id="refusal"),
        pytest.param("digline.host import UsageError as R", id="usage-error"),
    ],
)
def test_esc_a_refusals_sentence_reaches_the_terminal_through_visible(
    pytester: pytest.Pytester, baseline: Baseline, refusal: str
) -> None:
    """A refusal can quote what the suite's code wrote. An escape in it is
    shown, not obeyed, as `digline run` shows it. Both branches: `UsageError`
    has one of its own."""
    path = baseline(FINE, FINE)
    _preflight(path, f'from {refusal}; raise R("A\\x1b[2KFORGED")')

    result = pytester.runpytest_subprocess(
        "--digline-suite", str(path), "--digline-run"
    )

    assert result.ret == pytest.ExitCode.USAGE_ERROR
    err = result.stderr.str()
    assert "\x1b" not in err
    assert "A\\x1b[2KFORGED" in err
