"""Standard output carries digline alone (ADR 0043 §8, amended 2026-10-18).

What the suite, the application it imports, a target or a judge prints is
assigned to standard error, the perimeter of the person who ran the command.
Standard output is read by others: a pipeline that takes `digline run`'s key
from it, an action that turns `compare`'s first line into a headline and a
pull request comment.

One test per window, each through the command line in a subprocess, because a
redirection of the process's descriptors is the thing under test and pytest's
own capture would stand in front of it in-process. The module the suite
imports writes through `print` and through `os.write(1, ...)` both: the second
is what tells a redirection of the descriptor from one of the `sys.stdout`
object alone. The last test is the positive control: digline's own answer is
still on standard output, so a fix that silenced everything fails it.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import pytest
from tests._helpers import MARKS, cli, printing_repo

#: A run key as `digline run` prints it: the timestamp, then the config hash.
KEY = re.compile(r"^\d{4}-\d{2}-\d{2}T[\dT-]+-[0-9a-f]{16}$")


@pytest.fixture
def printing(tmp_path: Path) -> Path:
    if shutil.which("git") is None:  # pragma: no cover - CI always has git
        pytest.skip("git is not installed")
    return printing_repo(tmp_path)


def _on_stderr_not_stdout(stdout: str, stderr: str, *marks: str) -> None:
    for mark in marks:
        assert mark not in stdout, (
            f"{mark} reached standard output, which carries digline alone "
            f"(ADR 0043 §8). Standard output was:\n{stdout}"
        )
        assert mark in stderr, (
            f"{mark} reached neither stream: the user's output was dropped, not "
            f"moved to standard error. Standard error was:\n{stderr}"
        )


def test_what_the_suite_prints_when_imported_goes_to_standard_error(
    printing: Path,
) -> None:
    done = cli(printing, "compare", "--suite", "suite_qa.py", "--run", "latest")
    _on_stderr_not_stdout(done.stdout, done.stderr, MARKS["suite import"])


def test_what_a_module_it_imports_writes_goes_to_standard_error_at_the_descriptor(
    printing: Path,
) -> None:
    done = cli(printing, "compare", "--suite", "suite_qa.py", "--run", "latest")
    _on_stderr_not_stdout(
        done.stdout, done.stderr, MARKS["module print"], MARKS["module os.write"]
    )


def test_what_the_target_prints_goes_to_standard_error(printing: Path) -> None:
    done = cli(printing, "run", "--suite", "suite_qa.py")
    _on_stderr_not_stdout(done.stdout, done.stderr, MARKS["target call"])
    assert done.stdout.splitlines() == [done.stdout.strip()], (
        f"`digline run` printed more than its key on standard output:\n{done.stdout}"
    )


def test_what_the_judge_prints_goes_to_standard_error(printing: Path) -> None:
    done = cli(printing, "run", "--suite", "suite_qa.py")
    _on_stderr_not_stdout(done.stdout, done.stderr, MARKS["judge call"])


def test_what_a_target_file_prints_when_imported_goes_to_standard_error(
    printing: Path,
) -> None:
    done = cli(
        printing,
        "run",
        "--suite",
        "suite_qa.py",
        "--target",
        "printing_target.py:target",
    )
    _on_stderr_not_stdout(done.stdout, done.stderr, MARKS["target file import"])


def test_what_a_target_files_target_prints_goes_to_standard_error(
    printing: Path,
) -> None:
    done = cli(
        printing,
        "run",
        "--suite",
        "suite_qa.py",
        "--target",
        "printing_target.py:target",
    )
    _on_stderr_not_stdout(done.stdout, done.stderr, MARKS["target file call"])


def test_digline_still_writes_its_own_answer_to_standard_output(
    printing: Path,
) -> None:
    """The control. It passes before the fix and must pass after it: a fix
    that sent digline's own output to standard error, or nowhere, fails here
    and nowhere else."""
    ran = cli(printing, "run", "--suite", "suite_qa.py")
    keys = [line for line in ran.stdout.splitlines() if KEY.match(line)]
    assert len(keys) == 1, (
        f"`digline run` did not write its key to standard output:\n{ran.stdout}"
    )
    compared = cli(printing, "compare", "--suite", "suite_qa.py", "--run", keys[0])
    assert any(
        line.startswith("Nothing got worse") for line in compared.stdout.splitlines()
    ), (
        "`digline compare` did not write its sentence to standard output:\n"
        f"{compared.stdout}"
    )
