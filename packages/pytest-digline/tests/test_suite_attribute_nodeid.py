"""Two suites from one file are two nodes, by the attribute that names each.

A spec may name a suite inside a file, `both.py:support`. The plugin dropped the
attribute to find the file, so two suites from one file collected rows with
identical nodeids (#566), and three operations a pytest user relies on went
wrong: `--deselect` with an exact nodeid removed a row from both suites, `-k`
with the suite's name selected nothing, and `--lf` reran the failed row of both.
The suite's node now carries the attribute, `both.py:support`, so each of the
three acts on one suite.

A `--deselect` written against the old nodeid matches nothing now, and pytest
says nothing about a prefix that matches nothing. So the plugin does: one
warning per such value, naming the nodeid that replaced it.

Every test runs pytest as a real process: an assertion on a node object would
pass while the command a user types still did the wrong thing.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from _cycle import cycle

SUITES = """
import json, pathlib
from digline.core import Contains
from digline.run import Case, Response, Suite

def _suite(name: str, needle: str) -> Suite:
    return Suite(
        tenant="acme",
        environment="staging",
        name=name,
        assertions=[Contains(needle=needle)],
        cases=[Case(id="alpha"), Case(id="beta")],
    )

support = _suite("support", "Acme")
billing = _suite("billing", "Bill")

def target(case: Case) -> Response:
    table = json.loads(pathlib.Path(__file__).with_name("answers.json").read_text())
    return Response(output=table[case.id])
"""

BEFORE = {"alpha": "Acme Bill", "beta": "Acme Bill"}
#: `billing`'s beta loses its needle; `support` is unchanged.
AFTER = {"alpha": "Acme Bill", "beta": "Acme"}


@pytest.fixture
def both(pytester: pytest.Pytester) -> tuple[str, str]:
    """`both.py` with two suites, each with a baseline and a later run: the two
    specs, `both.py:support` and `both.py:billing`."""
    path = pytester.path / "both.py"
    path.write_text(SUITES, encoding="utf-8")
    answers = pytester.path / "answers.json"
    specs = (f"{path}:support", f"{path}:billing")
    answers.write_text(json.dumps(BEFORE), encoding="utf-8")
    for spec in specs:
        cycle(Path(spec), pytester.path, promote=True)
    answers.write_text(json.dumps(AFTER), encoding="utf-8")
    for spec in specs:
        cycle(Path(spec), pytester.path, promote=False)
    return specs


def suites(*specs: str) -> list[str]:
    return [arg for spec in specs for arg in ("--digline-suite", spec)]


def test_each_suite_from_one_file_has_its_own_nodeids(
    pytester: pytest.Pytester, both: tuple[str, str]
) -> None:
    result = pytester.runpytest_subprocess("--co", "-q", *suites(*both))
    listed = [line for line in result.stdout.lines if "::" in line]
    assert listed == [
        "both.py:support::alpha::contains",
        "both.py:support::beta::contains",
        "both.py:billing::alpha::contains",
        "both.py:billing::beta::contains",
    ], listed


def test_deselect_with_an_exact_nodeid_removes_one_row(
    pytester: pytest.Pytester, both: tuple[str, str]
) -> None:
    result = pytester.runpytest_subprocess(
        "-p",
        "no:cacheprovider",
        *suites(*both),
        "--deselect",
        "both.py:support::alpha::contains",
    )
    result.assert_outcomes(passed=2, failed=1, deselected=1)


def test_k_with_the_suite_name_selects_that_suite(
    pytester: pytest.Pytester, both: tuple[str, str]
) -> None:
    result = pytester.runpytest_subprocess(
        "-p", "no:cacheprovider", *suites(*both), "-k", "support"
    )
    result.assert_outcomes(passed=2, deselected=2)


def test_last_failed_reruns_the_one_row_that_failed(
    pytester: pytest.Pytester, both: tuple[str, str]
) -> None:
    pytester.runpytest_subprocess(*suites(*both))
    result = pytester.runpytest_subprocess(*suites(*both), "--lf")
    result.assert_outcomes(failed=1, deselected=3)
    assert "both.py:billing::beta::contains" in result.stdout.str()


def test_a_suite_named_without_an_attribute_keeps_its_nodeids(
    pytester: pytest.Pytester, both: tuple[str, str]
) -> None:
    """The perimeter: only a spec with `:attribute` changes. `both.py` alone
    loads the file's `suite`, and there is none, so a plain file is used."""
    plain = pytester.path / "plain.py"
    plain.write_text(
        SUITES.replace(
            'support = _suite("support", "Acme")', 'suite = _suite("support", "Acme")'
        ),
        encoding="utf-8",
    )
    cycle(plain, pytester.path, promote=True)
    result = pytester.runpytest_subprocess("--co", "-q", *suites(str(plain)))
    listed = [line for line in result.stdout.lines if "::" in line]
    assert listed == ["plain.py::alpha::contains", "plain.py::beta::contains"], listed


def test_a_deselect_written_for_the_old_nodeid_warns_with_the_new_one(
    pytester: pytest.Pytester, both: tuple[str, str]
) -> None:
    """The old form matches nothing and pytest is silent about it, so the case
    it was meant to exclude runs again. The warning names, for that value, the
    nodeids that replaced it: one per suite of the file."""
    result = pytester.runpytest_subprocess(
        "-p",
        "no:cacheprovider",
        *suites(*both),
        "--deselect",
        "both.py::alpha::contains",
    )
    text = result.stdout.str()
    assert "both.py:support::alpha::contains" in text, text
    assert "both.py:billing::alpha::contains" in text, text
    # Not excluded: the warning says the value is stale, it does not honour it.
    result.assert_outcomes(passed=3, failed=1, warnings=1)


def test_one_warning_per_stale_value_not_one_per_suite(
    pytester: pytest.Pytester, both: tuple[str, str]
) -> None:
    result = pytester.runpytest_subprocess(
        "-p",
        "no:cacheprovider",
        *suites(*both),
        "--deselect",
        "both.py::alpha::contains",
        "--deselect",
        "both.py::beta::contains",
    )
    # Neither value deselects anything now, so all four rows run.
    result.assert_outcomes(passed=3, failed=1, warnings=2)


def test_under_w_error_a_stale_deselect_stops_the_session(
    pytester: pytest.Pytester, both: tuple[str, str]
) -> None:
    """Whoever asked for warnings to be errors asked to be stopped by this."""
    result = pytester.runpytest_subprocess(
        "-p",
        "no:cacheprovider",
        *suites(*both),
        "--deselect",
        "both.py::alpha::contains",
        "-W",
        "error",
    )
    printed = result.stdout.str() + result.stderr.str()
    # A usage error, as every refusal of the request is in this plugin: not
    # INTERNALERROR, which reads as a crash of pytest or of this plugin.
    assert result.ret == pytest.ExitCode.USAGE_ERROR, printed
    assert "INTERNALERROR" not in printed, printed
    assert "both.py:support::alpha::contains" in printed, printed
