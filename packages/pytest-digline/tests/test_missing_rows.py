"""A check the baseline judged and this run did not is never a `PASSED` row. (#574)

`compare()` reports such a check as `missing`: present in the baseline, absent
from the run. Nothing judged it, so a row that read `PASSED` said something
nobody measured. Three causes produce it, and each is a `SKIPPED` row that says
which:

- the case was suspended after the baseline: the reason the suite declares;
- the case is no longer in the suite;
- the check is no longer in the suite.

The rows stay, and keep their nodeids: `-k`, `--deselect` and `--lf` name
them, and a row that vanished would break a CI configuration that named it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from _cycle import cycle

SUITE = """
import json, pathlib
from digline.core import Contains, Regex
from digline.run import Case, Response, Suite

suite = Suite(
    tenant="acme",
    environment="staging",
    name="support",
    assertions=[{assertions}],
    cases=[{cases}],
)

def target(case: Case) -> Response:
    here = pathlib.Path(__file__).parent
    return Response(output=json.loads((here / "answers.json").read_text())[case.id])
"""

BOTH_CHECKS = 'Contains(needle="Acme"), Regex(pattern="^Acme")'
BOTH_CASES = 'Case(id="alpha"), Case(id="beta")'


def write(directory: Path, *, assertions: str, cases: str) -> Path:
    path = directory / "eval" / "suite.py"
    path.parent.mkdir(exist_ok=True)
    path.write_text(SUITE.format(assertions=assertions, cases=cases), "utf-8")
    (path.parent / "answers.json").write_text(
        json.dumps({"alpha": "Acme", "beta": "Acme"}), "utf-8"
    )
    return path


@pytest.fixture
def promoted(pytester: pytest.Pytester) -> Path:
    """Two cases, two checks, all four judged and passing, then promoted."""
    path = write(pytester.path, assertions=BOTH_CHECKS, cases=BOTH_CASES)
    cycle(path, pytester.path, promote=True)
    return path


def rows(pytester: pytest.Pytester, path: Path) -> pytest.RunResult:
    return pytester.runpytest_subprocess(
        "-p", "no:cacheprovider", "--digline-suite", str(path), "-v", "-rs"
    )  # fmt: skip


def outcome_of(result: pytest.RunResult, nodeid: str) -> str:
    """The word pytest's verbose line gives this row, or "" if there is none."""
    for line in result.stdout.lines:
        if line.startswith(f"{nodeid} "):
            return line[len(nodeid) + 1 :].split()[0]
    return ""


def test_a_case_suspended_after_the_baseline_skips_its_checks_with_its_reason(
    pytester: pytest.Pytester, promoted: Path
) -> None:
    write(
        pytester.path,
        assertions=BOTH_CHECKS,
        cases='Case(id="alpha", suspended="the refund API is down"), Case(id="beta")',
    )
    cycle(promoted, pytester.path, promote=False)
    result = rows(pytester, promoted)
    for check in ("contains", "regex"):
        assert outcome_of(result, f"eval/suite.py::alpha::{check}") == "SKIPPED", (
            result.stdout.str()
        )
    result.stdout.fnmatch_lines(["*alpha::contains*the refund API is down*"])
    # The judged case is untouched.
    assert outcome_of(result, "eval/suite.py::beta::contains") == "PASSED"


def test_a_case_no_longer_in_the_suite_skips_its_checks_and_says_so(
    pytester: pytest.Pytester, promoted: Path
) -> None:
    write(pytester.path, assertions=BOTH_CHECKS, cases='Case(id="alpha")')
    cycle(promoted, pytester.path, promote=False)
    result = rows(pytester, promoted)
    for check in ("contains", "regex"):
        assert outcome_of(result, f"eval/suite.py::beta::{check}") == "SKIPPED", (
            result.stdout.str()
        )
    result.stdout.fnmatch_lines(["*beta::contains*no longer declares this case*"])
    assert outcome_of(result, "eval/suite.py::alpha::contains") == "PASSED"


def test_a_check_no_longer_in_the_suite_skips_its_rows_and_says_so(
    pytester: pytest.Pytester, promoted: Path
) -> None:
    write(pytester.path, assertions='Contains(needle="Acme")', cases=BOTH_CASES)
    cycle(promoted, pytester.path, promote=False)
    result = rows(pytester, promoted)
    for case in ("alpha", "beta"):
        assert outcome_of(result, f"eval/suite.py::{case}::regex") == "SKIPPED", (
            result.stdout.str()
        )
    result.stdout.fnmatch_lines(["*alpha::regex*no longer declares this check*"])
    assert outcome_of(result, "eval/suite.py::alpha::contains") == "PASSED"
