"""A session digline did not say green does not end green. (ADR 0049 §7)

`digline compare` exits 1 for a regression and 2 for a run it could not judge,
whose causes include a pinned file that drifted and a run that judged nothing.
A row can pass while digline says 2: a drifted pin fails no check, and a run of
suspended cases is all `SKIPPED`. So the session reads each suite's code, the
`exit_code()` of the same headline the summary prints, and a session that would
end `0` ends `1` when any suite's code is not `0`. pytest's own `2` means
interrupted, so `1` it is. A status that is already not `0` is left as it is.

Each suite that is not green gets one line in the summary, named by the path of
its rows, saying digline's code. That line is the half a reader sees, so it is
tested both ways: present for a session that is not green, absent for one that
is.

Every test runs pytest as a real process and asserts its exit status: a test
that called the hook by hand would pass while the command still exited `0`.
The plugin prints in English only (`LOCALE`), so the line is tested in English;
the Italian sentence is held to the same key by `tests/test_report.py`'s check
that both locales carry exactly the same keys.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from _cycle import cycle

SUITE = """
import json, pathlib
from digline.core import Contains
from digline.run import Case, Response, Suite

suite = Suite(
    tenant="acme",
    environment="staging",
    name="support",
    assertions=[Contains(needle="Acme")],
    cases=[Case(id="alpha"{suspended})],
    artifacts=["tools.json"],
    pinned=["tools.json"],
)

def target(case: Case) -> Response:
    here = pathlib.Path(__file__).parent
    return Response(output=json.loads((here / "answers.json").read_text())[case.id])
"""

LINE = "digline exits {code}, so this session does not end green"


def write_suite(directory: Path, *, suspended: bool = False) -> Path:
    path = directory / "eval" / "suite.py"
    path.parent.mkdir(exist_ok=True)
    flag = ', suspended="the refund API is down"' if suspended else ""
    path.write_text(SUITE.format(suspended=flag), encoding="utf-8")
    return path


def answer(path: Path, text: str) -> None:
    (path.parent / "answers.json").write_text(json.dumps({"alpha": text}), "utf-8")


def pin(path: Path, content: str) -> None:
    (path.parent / "tools.json").write_text(content, encoding="utf-8")


@pytest.fixture
def promoted(pytester: pytest.Pytester) -> Path:
    """`eval/suite.py`, judged and promoted: one case that passes, one pin."""
    path = write_suite(pytester.path)
    answer(path, "Acme")
    pin(path, '{"tools": ["refund"]}')
    cycle(path, pytester.path, promote=True)
    return path


def run(pytester: pytest.Pytester, path: Path, *more: str) -> pytest.RunResult:
    return pytester.runpytest_subprocess(
        "-p", "no:cacheprovider", "--digline-suite", str(path), *more
    )  # fmt: skip


def summary_says(result: pytest.RunResult, code: int) -> bool:
    return any(
        line == f"eval/suite.py: {LINE.format(code=code)}."
        for line in result.stdout.lines
    )


def test_a_pinned_file_that_drifted_fails_the_session(
    pytester: pytest.Pytester, promoted: Path
) -> None:
    """#484: digline exits 2 on a drifted pin, and the row still passes."""
    pin(promoted, '{"tools": ["refund", "delete_account"]}')
    cycle(promoted, pytester.path, promote=False)
    result = run(pytester, promoted)
    result.assert_outcomes(passed=1)
    assert result.ret == pytest.ExitCode.TESTS_FAILED, result.stdout.str()
    assert summary_says(result, 2), result.stdout.str()


def test_a_run_that_judged_nothing_fails_the_session_and_the_case_stays_skipped(
    pytester: pytest.Pytester, promoted: Path
) -> None:
    """The case's row stays `SKIPPED`: §7 changes the session, never a row.

    Only the case's row is asserted. Its check row, `alpha::contains`, comes
    from the comparison's delta against a baseline where `alpha` was judged,
    and reads `PASSED` before and after this change; what it should read is
    not this test's question.
    """
    write_suite(pytester.path, suspended=True)
    cycle(promoted, pytester.path, promote=False)
    result = run(pytester, promoted)
    assert result.parseoutcomes().get("skipped") == 1, result.stdout.str()
    assert result.ret == pytest.ExitCode.TESTS_FAILED, result.stdout.str()
    assert summary_says(result, 2), result.stdout.str()


def test_a_session_digline_says_green_ends_green_and_says_nothing_more(
    pytester: pytest.Pytester, promoted: Path
) -> None:
    """The control, and the other half of the line: absent when green, so a
    key that printed always could not pass."""
    cycle(promoted, pytester.path, promote=False)
    result = run(pytester, promoted)
    result.assert_outcomes(passed=1)
    assert result.ret == pytest.ExitCode.OK, result.stdout.str()
    assert "so this session does not end green" not in result.stdout.str()


def test_a_session_already_failing_stays_as_it_is_and_still_names_the_code(
    pytester: pytest.Pytester, promoted: Path
) -> None:
    """A regression fails its row, so pytest is at 1 already; digline's 1 is
    said, and the status is not rewritten."""
    answer(promoted, "nothing")
    cycle(promoted, pytester.path, promote=False)
    result = run(pytester, promoted)
    result.assert_outcomes(failed=1)
    assert result.ret == pytest.ExitCode.TESTS_FAILED, result.stdout.str()
    assert summary_says(result, 1), result.stdout.str()


def test_a_status_another_plugin_set_is_left_as_it_is(
    pytester: pytest.Pytester, promoted: Path
) -> None:
    """The hook reads `session.exitstatus`, not the value the hook was called
    with: a plugin before it that set 3 is what the session ends with."""
    pin(promoted, '{"tools": ["refund", "delete_account"]}')
    cycle(promoted, pytester.path, promote=False)
    pytester.makeconftest(
        "def pytest_sessionfinish(session):\n    session.exitstatus = 3\n"
    )
    result = run(pytester, promoted)
    assert result.ret == pytest.ExitCode.INTERNAL_ERROR, result.stdout.str()


def test_with_no_suite_named_the_session_is_untouched(
    pytester: pytest.Pytester,
) -> None:
    """Nothing opened, nothing stashed: the status is pytest's own. A passing
    session, so that both a hook that fails on the missing stash and one that
    set 1 regardless would show."""
    pytester.makepyfile(test_plain="def test_passes():\n    assert True\n")
    result = pytester.runpytest_subprocess("-p", "no:cacheprovider")
    result.assert_outcomes(passed=1)
    assert result.ret == pytest.ExitCode.OK, result.stdout.str()
    assert "so this session does not end green" not in result.stdout.str()
