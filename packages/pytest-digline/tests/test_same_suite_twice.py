"""Two specs that resolve to the same suite are refused before anything loads.

The last case #566 left open: one suite named twice collected its rows twice,
printed two identical `FAILED` lines and two identical summary lines. Passing a
suite twice asks for nothing, so it is refused as a usage error, naming both
specs. The comparison is on the suite the spec resolves to, not on its text:
`./both.py:support` and `both.py:support` are one suite, and so are `plain.py`
and `plain.py:suite`, because `suite` is the attribute a file spec defaults to.

Two different suites from one file are not the same suite, and keep working:
that is what #571 made possible, and why this refusal takes nothing legitimate.

Every test runs pytest as a real process. Each suite has a promoted baseline, so
that a refusal for a missing baseline, which is exit 4 too, cannot pass for this
one.
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

def _suite(name: str) -> Suite:
    return Suite(
        tenant="acme",
        environment="staging",
        name=name,
        assertions=[Contains(needle="Acme")],
        cases=[Case(id="alpha")],
    )

suite = _suite("plain")
support = _suite("support")
billing = _suite("billing")

def target(case: Case) -> Response:
    here = pathlib.Path(__file__).parent
    with (here / "calls.log").open("a", encoding="utf-8") as log:
        log.write(case.id + "\\n")
    return Response(output=json.loads((here / "answers.json").read_text())[case.id])
"""


@pytest.fixture
def both(pytester: pytest.Pytester) -> Path:
    """`both.py`, whose three suites each have a promoted baseline."""
    path = pytester.path / "both.py"
    path.write_text(SUITES, encoding="utf-8")
    (pytester.path / "answers.json").write_text(
        json.dumps({"alpha": "Acme"}), encoding="utf-8"
    )
    for attribute in ("suite", "support", "billing"):
        cycle(Path(f"{path}:{attribute}"), pytester.path, promote=True)
    (pytester.path / "calls.log").unlink()
    return path


def refused(result: pytest.RunResult) -> str:
    printed = result.stdout.str() + result.stderr.str()
    assert result.ret == pytest.ExitCode.USAGE_ERROR, printed
    assert "INTERNALERROR" not in printed, printed
    return printed


def test_one_spec_given_twice_is_refused_naming_it(
    pytester: pytest.Pytester, both: Path
) -> None:
    result = pytester.runpytest_subprocess(
        "-p", "no:cacheprovider",
        "--digline-suite", "both.py:support",
        "--digline-suite", "both.py:support",
    )  # fmt: skip
    printed = refused(result)
    assert "both.py:support" in printed, printed
    assert "same suite" in printed, printed


def test_one_suite_written_two_ways_is_refused(
    pytester: pytest.Pytester, both: Path
) -> None:
    """The identity is the resolved suite, not the text of the spec."""
    result = pytester.runpytest_subprocess(
        "-p", "no:cacheprovider",
        "--digline-suite", "./both.py:support",
        "--digline-suite", f"{both}:support",
    )  # fmt: skip
    printed = refused(result)
    assert "./both.py:support" in printed, printed
    assert f"{both}:support" in printed, printed
    assert "same suite" in printed, printed


def test_a_file_and_its_default_attribute_are_one_suite(
    pytester: pytest.Pytester, both: Path
) -> None:
    result = pytester.runpytest_subprocess(
        "-p", "no:cacheprovider",
        "--digline-suite", "both.py",
        "--digline-suite", "both.py:suite",
    )  # fmt: skip
    printed = refused(result)
    assert "same suite" in printed, printed


def test_the_same_path_twice_in_the_ini_is_refused(
    pytester: pytest.Pytester, both: Path
) -> None:
    pytester.makeini(
        "[pytest]\ndigline_suites =\n    both.py:support\n    both.py:support\n"
    )
    printed = refused(pytester.runpytest_subprocess("-p", "no:cacheprovider"))
    assert "same suite" in printed, printed


def test_nothing_is_run_before_the_refusal(
    pytester: pytest.Pytester, both: Path
) -> None:
    """Refused before any suite loads, so `--digline-run` calls no target: a
    session that is refused must not have spent a call first."""
    result = pytester.runpytest_subprocess(
        "-p", "no:cacheprovider", "--digline-run",
        "--digline-suite", "both.py:support",
        "--digline-suite", "both.py:support",
    )  # fmt: skip
    refused(result)
    assert not (pytester.path / "calls.log").exists()


def test_two_suites_from_one_file_are_not_the_same_suite(
    pytester: pytest.Pytester, both: Path
) -> None:
    """The perimeter: what #571 made work keeps working."""
    result = pytester.runpytest_subprocess(
        "-p", "no:cacheprovider",
        "--digline-suite", "both.py:support",
        "--digline-suite", "both.py:billing",
    )  # fmt: skip
    result.assert_outcomes(passed=2)
