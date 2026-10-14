"""Each line of the summary names its suite, the way pytest names its rows.

With more than one `--digline-suite`, the summary printed one sentence per
suite with nothing to say which was which: the reader could only count. Each
line now starts with the path pytest prints for that suite's rows, so the rows,
the sentence and its note are joined by the one string the reader already has.

The prefix is computed the way pytest renders a row's path, relative to the
directory pytest was started from, so these tests read it off pytest's own
progress lines rather than restating the rule. Until these tests, nothing pinned
the shape of a summary line: every assertion on the summary was a substring.
"""

from __future__ import annotations

import json
import re
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
    name={name!r},
    assertions=[Contains(needle="Acme")],
    cases=[Case(id="alpha"), Case(id="beta")],
)

def target(case: Case) -> Response:
    table = json.loads(pathlib.Path(__file__).with_name("answers.json").read_text())
    return Response(output=table[case.id])
"""

FINE = {"alpha": "Acme", "beta": "Acme"}
WORSE = {"alpha": "Acme", "beta": "nothing"}

#: A progress line: the path pytest prints, then the outcome characters.
PROGRESS = re.compile(r"^(?P<path>\S+) [.FEsx]+(\s+\[\s*\d+%\])?$")
SEPARATOR = re.compile(r"^=+ (?P<title>.+?) =+$")


def suite_at(pytester: pytest.Pytester, relative: str, name: str) -> Path:
    """A suite with a promoted baseline and a later run, `beta` regressed in
    the later one when the name is `billing`."""
    path = pytester.path / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(SUITE.format(name=name), encoding="utf-8")
    answers = path.with_name("answers.json")
    answers.write_text(json.dumps(FINE), encoding="utf-8")
    cycle(path, pytester.path, promote=True)
    answers.write_text(json.dumps(WORSE if name == "billing" else FINE), "utf-8")
    cycle(path, pytester.path, promote=False)
    return path


def progress_paths(text: str) -> list[str]:
    return [m["path"] for line in text.splitlines() if (m := PROGRESS.match(line))]


def summary(text: str) -> list[str]:
    """The lines of the `digline` section, between its separator and the next."""
    lines = text.splitlines()
    start = next(
        i
        for i, line in enumerate(lines)
        if (m := SEPARATOR.match(line)) and m["title"] == "digline"
    )
    rest = lines[start + 1 :]
    end = next((i for i, line in enumerate(rest) if SEPARATOR.match(line)), len(rest))
    return rest[:end]


def test_one_suite_its_line_starts_with_the_path_of_its_rows(
    pytester: pytest.Pytester,
) -> None:
    """Uniform, so a single suite is named too: the rule that a line is joined
    to its rows by name holds with one suite as with two."""
    path = suite_at(pytester, "support.py", "support")
    result = pytester.runpytest_subprocess(
        "--digline-suite", str(path), "-p", "no:cacheprovider"
    )
    text = result.stdout.str()
    (row_path,) = progress_paths(text)
    (line,) = summary(text)
    assert line.startswith(f"{row_path}: "), line
    assert line.removeprefix(f"{row_path}: ").startswith("Nothing got worse"), line


def test_two_suites_each_line_names_its_own(pytester: pytest.Pytester) -> None:
    """Two files with the same name in different directories: pytest renders
    them as two paths, and so does the summary."""
    support = suite_at(pytester, "support/suite.py", "support")
    billing = suite_at(pytester, "billing/suite.py", "billing")
    result = pytester.runpytest_subprocess(
        "--digline-suite",
        str(support),
        "--digline-suite",
        str(billing),
        "-p",
        "no:cacheprovider",
    )
    text = result.stdout.str()
    rows = progress_paths(text)
    assert rows == ["support/suite.py", "billing/suite.py"], rows
    lines = summary(text)
    assert len(lines) == 2, lines
    assert lines[0].startswith("support/suite.py: Nothing got worse"), lines[0]
    assert lines[1].startswith("billing/suite.py: 1 check got worse"), lines[1]


def test_the_note_carries_the_prefix_of_its_suite(pytester: pytest.Pytester) -> None:
    """The note `latest` leaves is about one suite, so it is named the same way."""
    path = suite_at(pytester, "support.py", "support")
    newer = cycle(path, pytester.path, promote=True)
    (gone,) = (pytester.path / ".digline").glob(f"*/runs/**/{newer}.json")
    gone.unlink()
    result = pytester.runpytest_subprocess(
        "--digline-suite", str(path), "-p", "no:cacheprovider"
    )
    text = result.stdout.str()
    (row_path,) = progress_paths(text)
    lines = summary(text)
    assert len(lines) == 2, lines
    assert lines[0].startswith(f"{row_path}: "), lines[0]
    assert lines[1].startswith(f"{row_path}: note: "), lines[1]


def test_the_prefix_follows_the_rows_not_the_nodeid(pytester: pytest.Pytester) -> None:
    """Started from a directory that is not the rootdir, pytest prints a row's
    path relative to where it was started, not the nodeid. The prefix has to be
    the string the reader sees on the rows."""
    path = suite_at(pytester, "project/suites/support.py", "support")
    result = pytester.runpytest_subprocess(
        "--digline-suite",
        str(path),
        "--rootdir",
        str(pytester.path / "project"),
        "--digline-root",
        str(pytester.path),
        "-p",
        "no:cacheprovider",
    )
    text = result.stdout.str()
    (row_path,) = progress_paths(text)
    assert row_path == "project/suites/support.py", row_path
    (line,) = summary(text)
    assert line.startswith("project/suites/support.py: "), line
