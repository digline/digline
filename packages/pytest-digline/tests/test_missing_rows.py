"""A check the baseline judged and this run did not is never a `PASSED` row. (#574)

`compare()` reports such a check as `missing`: present in the baseline, absent
from the run. Nothing judged it, so a row that read `PASSED` said something
nobody measured. Three causes produce it, and each is a `SKIPPED` row that says
which:

- the case was suspended after the baseline: the reason the suite declares;
- the case is no longer in the suite;
- the check is no longer in the suite, a run-level check included;
- and anything else: the stored run has no verdict for it. This is the
  remainder, not a fourth condition, so a cause nobody foresaw gets an honest
  `SKIPPED` instead of a false `PASSED`.

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
from digline.core import Contains, Precision, Regex
from digline.run import Case, Response, Suite

suite = Suite(
    tenant="acme",
    environment="staging",
    name="support",
    assertions=[{assertions}],
    run_assertions=[{run_assertions}],
    cases=[{cases}],
)

def target(case: Case) -> Response:
    here = pathlib.Path(__file__).parent
    return Response(output=json.loads((here / "answers.json").read_text())[case.id])
"""

BOTH_CHECKS = 'Contains(needle="Acme"), Regex(pattern="^Acme")'
AGGREGATE = 'Precision(over="contains", threshold="1/2", tolerance=0.0, by_group=True)'
ALPHA = 'Case(id="alpha", label="positive", group="desk")'
BETA = 'Case(id="beta", label="positive", group="desk")'
BOTH_CASES = f"{ALPHA}, {BETA}"


def write(
    directory: Path, *, assertions: str, cases: str, run_assertions: str = AGGREGATE
) -> Path:
    path = directory / "eval" / "suite.py"
    path.parent.mkdir(exist_ok=True)
    path.write_text(
        SUITE.format(assertions=assertions, cases=cases, run_assertions=run_assertions),
        "utf-8",
    )
    (path.parent / "answers.json").write_text(
        json.dumps({"alpha": "Acme", "beta": "Acme"}), "utf-8"
    )
    return path


@pytest.fixture
def promoted(pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Two cases, two checks, all four judged and passing, then promoted.

    The terminal is made wide, which the pytest subprocess inherits: pytest
    cuts a skip's reason on the verbose line to the terminal's width, and a
    test that matched a cut reason would depend on where it runs.
    """
    monkeypatch.setenv("COLUMNS", "240")
    path = write(pytester.path, assertions=BOTH_CHECKS, cases=BOTH_CASES)
    cycle(path, pytester.path, promote=True)
    return path


def rows(pytester: pytest.Pytester, path: Path) -> pytest.RunResult:
    return pytester.runpytest_subprocess(
        "-p", "no:cacheprovider", "--digline-suite", str(path), "-v", "-rs"
    )  # fmt: skip


def says(result: pytest.RunResult, nodeid: str, reason: str) -> bool:
    """The row's verbose line is SKIPPED with this reason, whole, and `-rs`
    carries it too. The verbose line is what ties the reason to the row: the
    `-rs` line names the suite's file, not the row."""
    row = any(
        line.startswith(f"{nodeid} SKIPPED ({reason})") for line in result.stdout.lines
    )
    whole = any(
        line.startswith("SKIPPED [") and line.endswith(f": {reason}")
        for line in result.stdout.lines
    )
    return row and whole


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
        cases=(
            'Case(id="alpha", label="positive", group="desk",'
            f' suspended="the refund API is down"), {BETA}'
        ),
    )
    cycle(promoted, pytester.path, promote=False)
    result = rows(pytester, promoted)
    for check in ("contains", "regex"):
        assert outcome_of(result, f"eval/suite.py::alpha::{check}") == "SKIPPED", (
            result.stdout.str()
        )
    assert says(result, "eval/suite.py::alpha::contains", "the refund API is down"), (
        result.stdout.str()
    )
    # The judged case is untouched.
    assert outcome_of(result, "eval/suite.py::beta::contains") == "PASSED"


def test_a_case_no_longer_in_the_suite_skips_its_checks_and_says_so(
    pytester: pytest.Pytester, promoted: Path
) -> None:
    write(pytester.path, assertions=BOTH_CHECKS, cases=ALPHA)
    cycle(promoted, pytester.path, promote=False)
    result = rows(pytester, promoted)
    for check in ("contains", "regex"):
        assert outcome_of(result, f"eval/suite.py::beta::{check}") == "SKIPPED", (
            result.stdout.str()
        )
    assert says(
        result,
        "eval/suite.py::beta::contains",
        "the suite no longer declares this case",
    ), result.stdout.str()
    assert outcome_of(result, "eval/suite.py::alpha::contains") == "PASSED"


def test_a_check_no_longer_in_the_suite_skips_its_rows_and_says_so(
    pytester: pytest.Pytester, promoted: Path
) -> None:
    """A case-level check and a run-level one, both withdrawn."""
    write(
        pytester.path,
        assertions='Contains(needle="Acme")',
        cases=BOTH_CASES,
        run_assertions="",
    )
    cycle(promoted, pytester.path, promote=False)
    result = rows(pytester, promoted)
    for case in ("alpha", "beta"):
        assert outcome_of(result, f"eval/suite.py::{case}::regex") == "SKIPPED", (
            result.stdout.str()
        )
    assert says(
        result,
        "eval/suite.py::alpha::regex",
        "the suite no longer declares this check",
    ), result.stdout.str()
    run_level = "eval/suite.py::<run>::precision[group=desk]"
    assert outcome_of(result, run_level) == "SKIPPED", result.stdout.str()
    assert says(
        result,
        run_level,
        "the suite no longer declares this check",
    ), result.stdout.str()
    assert outcome_of(result, "eval/suite.py::alpha::contains") == "PASSED"


def test_a_check_the_stored_run_lacks_is_skipped_as_the_remainder(
    pytester: pytest.Pytester, promoted: Path
) -> None:
    """None of the three causes: the case is declared and not suspended, the
    check is declared, and the stored run has no verdict for it. A case was
    suspended, a run was stored, and the case was taken back; pytest, without
    `--digline-run`, reads that stored run."""
    write(
        pytester.path,
        assertions=BOTH_CHECKS,
        cases=(
            'Case(id="alpha", label="positive", group="desk",'
            f' suspended="the refund API is down"), {BETA}'
        ),
    )
    cycle(promoted, pytester.path, promote=False)
    write(pytester.path, assertions=BOTH_CHECKS, cases=BOTH_CASES)
    result = rows(pytester, promoted)
    for check in ("contains", "regex"):
        assert outcome_of(result, f"eval/suite.py::alpha::{check}") == "SKIPPED", (
            result.stdout.str()
        )
    assert says(
        result,
        "eval/suite.py::alpha::contains",
        "the stored run has no verdict for this check: run it again, or pass "
        "--digline-run",
    ), result.stdout.str()
    assert "the refund API is down" not in result.stdout.str()


COUNTER = (
    'Case(id="alpha", label="positive", group="counter"), '
    'Case(id="beta", label="positive", group="counter")'
)


def test_a_group_no_case_declares_any_more_is_a_check_no_longer_declared(
    pytester: pytest.Pytester, promoted: Path
) -> None:
    """The aggregate is still declared; the group is not, because no case
    carries it. Its slice is a check the suite no longer declares, and saying
    "run it again" would be false: a new run would not bring it back."""
    write(pytester.path, assertions=BOTH_CHECKS, cases=COUNTER)
    cycle(promoted, pytester.path, promote=False)
    result = rows(pytester, promoted)
    assert says(
        result,
        "eval/suite.py::<run>::precision[group=desk]",
        "the suite no longer declares this check",
    ), result.stdout.str()


def test_a_run_level_check_the_stored_run_lacks_is_the_remainder_too(
    pytester: pytest.Pytester, promoted: Path
) -> None:
    """The run-level twin of the remainder, and the test that holds it as an
    `else`: a fourth condition written for cases alone would let this row pass.
    The cases moved to another group, a run was stored, and they moved back:
    the aggregate and the group are both declared, and the stored run has no
    slice for it."""
    write(pytester.path, assertions=BOTH_CHECKS, cases=COUNTER)
    cycle(promoted, pytester.path, promote=False)
    write(pytester.path, assertions=BOTH_CHECKS, cases=BOTH_CASES)
    result = rows(pytester, promoted)
    assert says(
        result,
        "eval/suite.py::<run>::precision[group=desk]",
        "the stored run has no verdict for this check: run it again, or pass "
        "--digline-run",
    ), result.stdout.str()
