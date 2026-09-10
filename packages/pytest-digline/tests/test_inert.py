"""Installed and unasked: this plugin changes nothing. (ADR 0013 §8)

The first test written in this package, and the one that protects every other
test in the repository. `uv sync --all-packages` installs this member into
digline's own development environment, so its `pytest11` entry point is **active
for the 1,400 tests that judge it**. A plugin under development that could
change the result of its own gates is not a plugin under development, it is a
variable in the experiment.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest


def test_a_run_with_no_suite_named_collects_the_same_items(
    pytester: pytest.Pytester,
) -> None:
    pytester.makepyfile(
        test_ordinary="""
        def test_one(): assert True
        def test_two(): assert False
        """
    )
    result = pytester.runpytest_subprocess()
    result.assert_outcomes(passed=1, failed=1)


def test_a_run_with_no_suite_named_prints_nothing_of_its_own(
    pytester: pytest.Pytester,
) -> None:
    """Not merely 'collects nothing': says nothing.

    A header line, a section separator or a summary line from a plugin nobody
    asked for is noise in every pytest run on the machine.

    pytest's own `plugins:` banner is excluded, and only that line: naming what
    is installed is pytest's job and is how a reader knows what is loaded. Every
    other mention would be ours.
    """
    pytester.makepyfile(test_ordinary="def test_one(): assert True")
    result = pytester.runpytest_subprocess()
    ours = [
        line
        for line in result.stdout.lines + result.stderr.lines
        if "digline" in line.lower() and not line.startswith("plugins:")
    ]
    assert not ours, ours


def test_the_plugin_is_actually_loaded_while_it_says_nothing(
    pytester: pytest.Pytester,
) -> None:
    """The guard on the guard.

    Both tests above would pass if this package were not installed at all,
    which would make them a check on nothing. `--trace-config` lists what pytest
    loaded, so this fails if silence ever stops being a decision and becomes an
    absence.
    """
    pytester.makepyfile(test_ordinary="def test_one(): assert True")
    result = pytester.runpytest_subprocess("--trace-config")
    assert "digline" in result.stdout.str()


def test_the_options_exist_and_default_to_doing_nothing(
    pytester: pytest.Pytester,
) -> None:
    result = pytester.runpytest_subprocess("--help")
    result.stdout.fnmatch_lines(["*--digline-suite*", "*--digline-run*"])


def test_naming_no_suite_does_not_import_digline_at_all(
    pytester: pytest.Pytester,
) -> None:
    """Inert means the startup too, not only the output. (ADR 0013 §8)

    A `pytest11` entry point is loaded at pytest startup in every environment
    where this package is installed, including projects that never name a
    suite. Importing digline at module level pulled 44 modules — the core, the
    store, the driver, the report, the host, and `jsonschema` behind the
    assertions — into every one of those runs, and measured 138 ms against
    88 ms for a bare collection on an unrelated project. A command people press
    hundreds of times a day is the wrong place to spend 50 ms on a tool they
    are not using.

    So the digline imports live inside the functions that need them, and this
    is what holds them there. It runs in a subprocess because the process
    running *these* tests has digline imported many times over.
    """
    pytester.makepyfile(
        test_startup="""
        import sys

        def test_digline_is_not_imported():
            leaked = sorted(m for m in sys.modules if m.startswith("digline"))
            assert not leaked, (
                f"pytest started and imported {leaked}. This plugin was not "
                "asked to do anything: no --digline-suite, no digline_suites. "
                "Move the import back inside the hook that needs it."
            )
        """
    )
    result = pytester.runpytest_subprocess()
    result.assert_outcomes(passed=1)


def test_naming_a_suite_does_import_it(
    pytester: pytest.Pytester,
    baseline: Callable[[dict[str, str], dict[str, str]], Path],
) -> None:
    """The guard on the guard: laziness that never loads is not laziness."""
    path = baseline(
        {"alpha": "Acme, SATISFIED", "beta": "Acme, SATISFIED"},
        {"alpha": "Acme, SATISFIED", "beta": "Acme, SATISFIED"},
    )
    pytester.makepyfile(
        test_startup="""
        import sys

        def test_digline_is_imported():
            assert any(m.startswith("digline") for m in sys.modules)
        """
    )
    result = pytester.runpytest_subprocess("--digline-suite", str(path))
    result.assert_outcomes(passed=5, skipped=1)
