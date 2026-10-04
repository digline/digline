"""A failure nobody anticipated exits 70, and the refusals that reached the same
path exit 64. (#412, ADR 0041)

Until ADR 0041 an exception `main()` did not translate ended the process
through Python's default handler, which exits 1: `EXIT_WORSE`, from a gate that
measured nothing and from readings that never gate. What reached that path was
measured as four classes, and only the last is digline failing:

- (A) deliberate refusals raised as a bare `TypeError`;
- (B) the environment, an `OSError` on a file;
- (C) the user's suite raising while it loads;
- (D) a failure nobody anticipated.

(A), (B) and (C) now exit 64, each like its precedent. (D) exits 70 and prints
its traceback beside a line saying what it is not. Both halves are held here,
because 70 is born wrong if a `PermissionError` still reaches it.
"""

from __future__ import annotations

import dataclasses
import importlib
import os
import subprocess
import sys
from pathlib import Path
from typing import cast

import pytest
from tests._helpers import cli, git, run_key, write_suite

from digline.cli import EXIT_INTERNAL, EXIT_OK, EXIT_USAGE, EXIT_WORSE
from digline.core import AssertionShapeError, RunAssertion, expand_by_group
from digline.host import REFUSALS, UsageError, load_suite

#: The module, not the function: `digline.cli` exports `main` under the
#: module's own name, so `import digline.cli.main` finds the function.
cli_main = importlib.import_module("digline.cli.main")

SUITE = ("--suite", "suite_qa.py")

#: One gate and one reading at least, each broken inside the host function it
#: calls, so the path to `main()` is the real one.
BROKEN = [
    pytest.param("compare", "compare", ("--run", "latest"), id="compare-gate"),
    pytest.param("explain", "explained", ("--run", "latest"), id="explain-gate"),
    pytest.param("log", "history", (), id="log-reading"),
    pytest.param("list", "suite_runs", (), id="list-reading"),
]


@pytest.fixture
def compared(repo: Path) -> Path:
    """A baseline, and a run to compare with it."""
    key = run_key(repo)
    done = cli(repo, "promote", *SUITE, "--run", key, "--replacing", "none")
    assert done.returncode == EXIT_OK, done.stderr
    run_key(repo)
    return repo


def broken(*args: object, **kwargs: object) -> object:
    raise KeyError("provider")


@pytest.mark.parametrize(("command", "inside", "extra"), BROKEN)
def test_a_failure_nobody_anticipated_exits_70_on_a_gate_and_a_reading(
    compared: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    command: str,
    inside: str,
    extra: tuple[str, ...],
) -> None:
    """#402's shape: a `KeyError` from inside a command. It exited 1 before.

    A gate must not pass on it, and must not report a regression either: 70
    is neither 0 nor 1. A reading must not exit 0 on it, because "it exits 0
    whenever it could read the store" presupposes the reading came out."""
    monkeypatch.chdir(compared)
    monkeypatch.setattr(cli_main, inside, broken)

    code = cli_main.main([command, *SUITE, *extra])

    assert code == EXIT_INTERNAL
    assert code not in (EXIT_OK, EXIT_WORSE)
    err = capsys.readouterr().err
    assert "Traceback (most recent call last):" in err
    assert "KeyError: 'provider'" in err
    assert err.rstrip().endswith("It is not a verdict on the suite (exit 70)."), err[
        -300:
    ]


def test_the_traceback_reaches_the_terminal_through_the_sanitiser(
    compared: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """An exception's message can quote a document, and a document can carry a
    model's text. Nothing in it may rewrite the terminal."""

    def quoting(*args: object, **kwargs: object) -> object:
        raise RuntimeError("the reply said \x1b[2J\x1b[31mall clear\x9b")

    monkeypatch.chdir(compared)
    monkeypatch.setattr(cli_main, "history", quoting)

    assert cli_main.main(["log", *SUITE]) == EXIT_INTERNAL
    err = capsys.readouterr().err
    assert "\x1b" not in err
    assert "\x9b" not in err
    assert "all clear" in err


def test_an_interrupt_is_not_turned_into_a_70(
    compared: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ctrl-C keeps the convention, and is not a failure of anything."""

    def interrupted(*args: object, **kwargs: object) -> object:
        raise KeyboardInterrupt

    monkeypatch.chdir(compared)
    monkeypatch.setattr(cli_main, "history", interrupted)
    with pytest.raises(KeyboardInterrupt):
        cli_main.main(["log", *SUITE])


# --------------------------------------------------------------------------- #
# (A) A deliberate refusal raised as a `TypeError`
# --------------------------------------------------------------------------- #

NOT_A_DATACLASS = """

from digline.core import AssertionBase, Score


class Plain(AssertionBase):
    name = "plain"

    def evaluate(self, inputs):
        return Score(name="plain", score=1.0)


suite.assertions.append(Plain())
"""


def suite_repo(root: Path, *, extra: str = "", preamble: str = "") -> Path:
    git(root, "init", "-q")
    git(root, "config", "user.email", "test@example.invalid")
    git(root, "config", "user.name", "Test")
    path = write_suite(root, preamble=preamble)
    if extra:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(extra)
    git(root, "add", "-A")
    git(root, "commit", "-qm", "initial")
    return root


def test_a_check_that_is_not_a_dataclass_is_refused_not_a_failure(
    tmp_path: Path,
) -> None:
    done = cli(suite_repo(tmp_path, extra=NOT_A_DATACLASS), "run", *SUITE)
    assert done.returncode == EXIT_USAGE, done.stderr
    assert "AssertionShapeError: Plain is not a dataclass" in done.stderr
    assert "Traceback" not in done.stderr


class NoDataclass:
    """Opts into `by_group` without being a dataclass."""

    name = "accuracy"
    by_group = True


@dataclasses.dataclass(frozen=True)
class NoGroupField:
    """A dataclass that opts into `by_group` and has no `group` field."""

    name: str = "accuracy"
    by_group: bool = True


@pytest.mark.parametrize(
    ("declared", "says"),
    [
        pytest.param(NoDataclass(), "is not a dataclass", id="not-a-dataclass"),
        pytest.param(NoGroupField(), "declares no `group` field", id="no-group"),
    ],
)
def test_a_by_group_that_cannot_be_expanded_is_the_same_refusal(
    declared: object, says: str
) -> None:
    """The two other deliberate `TypeError`s, which no test reached before."""
    with pytest.raises(AssertionShapeError, match=says):
        expand_by_group([cast(RunAssertion, declared)], ["fr"])


def test_the_refusal_is_still_a_type_error_and_is_classified() -> None:
    """A library caller that caught `TypeError` still catches it."""
    assert issubclass(AssertionShapeError, TypeError)
    assert AssertionShapeError in REFUSALS


# --------------------------------------------------------------------------- #
# (B) The environment: a file that cannot be read
# --------------------------------------------------------------------------- #


def a_baseline(root: Path) -> Path:
    (path,) = (root / ".digline").glob("*/baselines/qa.json")
    return path


@pytest.mark.skipif(
    sys.platform == "win32" or os.geteuid() == 0,
    reason="mode 000 does not stop root, and Windows has no such mode",
)
@pytest.mark.parametrize("command", ["compare", "log"])
def test_an_unreadable_baseline_is_refused_not_a_failure(
    compared: Path, command: str
) -> None:
    """The same thing on a directory was already 64 (`DirectoryUnreadableError`).
    On a file it was a `PermissionError` traceback and exit 1."""
    baseline = a_baseline(compared)
    baseline.chmod(0)
    try:
        extra = ("--run", "latest") if command == "compare" else ()
        done = cli(compared, command, *SUITE, *extra)
    finally:
        baseline.chmod(0o644)
    assert done.returncode == EXIT_USAGE, done.stderr
    assert "PermissionError" in done.stderr
    assert "Traceback" not in done.stderr


def test_a_baseline_that_is_a_directory_is_refused_not_a_failure(
    compared: Path,
) -> None:
    baseline = a_baseline(compared)
    baseline.unlink()
    baseline.mkdir()
    done = cli(compared, "compare", *SUITE, "--run", "latest")
    assert done.returncode == EXIT_USAGE, done.stderr
    assert "IsADirectoryError" in done.stderr
    assert "Traceback" not in done.stderr


# --------------------------------------------------------------------------- #
# (C) The user's suite raising while it loads
# --------------------------------------------------------------------------- #


BOOM = "raise RuntimeError('boom at import')"


def line_of(path: Path, text: str) -> int:
    """The 1-based line of `path` that holds `text`, so a location is asserted
    exactly rather than as any number."""
    lines = path.read_text(encoding="utf-8").splitlines()
    return next(i for i, line in enumerate(lines, 1) if text in line)


@pytest.mark.parametrize("command", ["run", "compare"])
def test_a_suite_that_raises_while_it_loads_is_refused_with_its_location(
    tmp_path: Path, command: str
) -> None:
    """`SyntaxError` and `ImportError` were already 64. A `RuntimeError` was a
    traceback and exit 1, from a suite that never got as far as running.

    27bc37e kept it unexpected because a sentence would hide where the suite
    failed. So the sentence carries the type, the message and the location,
    which is what that commit protected, and this asserts each of them."""
    root = suite_repo(tmp_path, preamble=BOOM)
    suite = root / "suite_qa.py"
    extra = ("--run", "latest") if command == "compare" else ()
    done = cli(root, command, *SUITE, *extra)
    assert done.returncode == EXIT_USAGE, done.stderr
    assert "raised RuntimeError: boom at import" in done.stderr
    assert f"at {suite.resolve()}:{line_of(suite, BOOM)}," in done.stderr
    assert "For the full traceback, run: cd " in done.stderr
    assert "Traceback" not in done.stderr


def test_the_command_in_the_sentence_reproduces_the_traceback(
    tmp_path: Path,
) -> None:
    """The traceback the sentence leaves out is one command away, and the
    command is checked by running it, not by reading it."""
    root = suite_repo(tmp_path, preamble=BOOM)
    done = cli(root, "run", *SUITE)
    command = done.stderr.split("For the full traceback, run: ", 1)[1].strip()
    command = command.replace(" python -c ", f" {sys.executable} -c ", 1)
    shown = subprocess.run(
        command, shell=True, capture_output=True, text=True, check=False
    )
    assert "Traceback (most recent call last):" in shown.stderr
    assert "RuntimeError: boom at import" in shown.stderr


def test_the_location_names_the_frame_that_raised_and_the_suite_line(
    tmp_path: Path,
) -> None:
    """Raised in a module the suite imports: the innermost frame is that
    module's, and the suite's own line is named beside it."""
    (tmp_path / "app.py").write_text(
        "def start():\n    raise RuntimeError('the app would not start')\n",
        encoding="utf-8",
    )
    root = suite_repo(tmp_path, preamble="import app\napp.start()")
    suite = root / "suite_qa.py"
    done = cli(root, "run", *SUITE)
    assert done.returncode == EXIT_USAGE, done.stderr
    assert f"at {(root / 'app.py').resolve()}:2" in done.stderr
    assert f"reached from {suite.resolve()}:{line_of(suite, 'app.start()')}" in (
        done.stderr
    )


def test_a_message_from_the_suite_cannot_rewrite_the_terminal(
    tmp_path: Path,
) -> None:
    root = suite_repo(
        tmp_path, preamble="raise RuntimeError('\\x1b[2J\\x1b[31mall clear\\x9b')"
    )
    done = cli(root, "run", *SUITE)
    assert done.returncode == EXIT_USAGE, done.stderr
    assert "\x1b" not in done.stderr
    assert "\x9b" not in done.stderr
    assert "all clear" in done.stderr


def test_the_dotted_form_is_refused_the_same_way(tmp_path: Path) -> None:
    root = suite_repo(tmp_path, preamble=BOOM)
    done = cli(root, "run", "--suite", "suite_qa:suite")
    assert done.returncode == EXIT_USAGE, done.stderr
    assert "raised RuntimeError: boom at import" in done.stderr
    assert "For the full traceback, run: python -c 'import suite_qa'" in done.stderr


def test_what_digline_raised_while_the_suite_loaded_is_not_the_suites(
    tmp_path: Path,
) -> None:
    """Rule 2 of ADR 0041 §4. The innermost frame is digline's, and the type is
    one digline wrote no sentence for: the missing sentence is digline's
    defect, so it exits 70 with its traceback rather than blaming the suite."""
    root = suite_repo(
        tmp_path, preamble="from digline.report import phrase\nphrase('en', 'no.such')"
    )
    done = cli(root, "run", *SUITE)
    assert done.returncode == EXIT_INTERNAL, done.stderr
    assert "Traceback (most recent call last):" in done.stderr
    assert "KeyError" in done.stderr
    assert "while it was being loaded" not in done.stderr


def test_a_value_error_the_suite_raises_while_it_loads_is_refused_with_its_location(
    tmp_path: Path,
) -> None:
    """Reversed by ADR 0041 §4.2. Until then a bare `ValueError` passed through
    unwrapped, because every `ValueError` was taken for a refusal. It is the
    suite's own code, so it is refused like any other exception the suite
    raises, with the location. **The exit stays 64: the sentence changes, not
    the verdict.**"""
    root = suite_repo(tmp_path, preamble="raise ValueError('a sentence of its own')")
    done = cli(root, "run", *SUITE)
    assert done.returncode == EXIT_USAGE, done.stderr
    assert "raised ValueError: a sentence of its own" in done.stderr
    assert "suite_qa.py:4" in done.stderr
    assert "while it was being loaded" in done.stderr
    assert "Traceback" not in done.stderr


def test_a_refusal_digline_writes_while_the_suite_loads_is_its_sentence(
    tmp_path: Path,
) -> None:
    """The other half of the same line. `Contains(needle="")` is refused inside
    digline, so by its frame it would be rule 2 and exit 70. Its type is what
    says it is on purpose. (ADR 0041 §4.2)"""
    root = suite_repo(tmp_path, preamble="Contains(needle='')")
    done = cli(root, "run", *SUITE)
    assert done.returncode == EXIT_USAGE, done.stderr
    assert "RefusedError: Contains.needle must not be empty" in done.stderr
    assert "Traceback" not in done.stderr


def test_a_calibration_band_declared_out_of_range_is_still_a_refusal(
    tmp_path: Path,
) -> None:
    """`CalibrationBand.bounds` belongs to the `Run` family's class, whose
    `raise`s stay bare. But `Calibration` calls it at declaration, so its error
    reaches a front end along the user's road. Left bare, this was 64 and would
    have become 70. (ADR 0041 §4.2)"""
    root = suite_repo(
        tmp_path,
        preamble=(
            "from digline.run import Calibration\n"
            "Calibration(output='Rome', check='answers?', low=0.0, high=0.5)"
        ),
    )
    done = cli(root, "run", *SUITE)
    assert done.returncode == EXIT_USAGE, done.stderr
    assert "RefusedError:" in done.stderr
    assert "strictly between 0" in done.stderr


def test_a_bare_value_error_from_inside_digline_exits_70(
    compared: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """#415. The defect ADR 0041 kept on purpose in its rule 1, and §4.2
    repaired. A `ValueError` digline raises by mistake told the user their
    request was wrong. The type is the only thing that can say *on purpose*, so
    a bare one is a failure nobody anticipated, on a gate as on a reading."""

    def mistaken(*args: object, **kwargs: object) -> object:
        return int("not a number")

    monkeypatch.chdir(compared)
    monkeypatch.setattr(cli_main, "compare", mistaken)

    code = cli_main.main(["compare", *SUITE, "--run", "latest"])

    assert code == EXIT_INTERNAL
    err = capsys.readouterr().err
    assert "Traceback (most recent call last):" in err
    assert "ValueError: invalid literal for int()" in err


def test_a_suite_that_exits_while_it_loads_still_passes_its_code_through(
    tmp_path: Path,
) -> None:
    """Recorded, not repaired: #414. Pinned so that a change to it is a
    decision somebody sees, not a side effect."""
    root = suite_repo(tmp_path, preamble="raise SystemExit(3)")
    done = cli(root, "run", *SUITE)
    assert done.returncode == 3


def test_the_refusal_is_neutralised_before_any_front_end_sees_it(
    tmp_path: Path,
) -> None:
    """Both front ends sanitise at their sink. The loader does it as well, so a
    third caller of `load_suite` cannot print the suite's message raw."""
    root = suite_repo(tmp_path, preamble="raise RuntimeError('\\x1b[2Jgone\\x9b')")
    with pytest.raises(UsageError) as refused:
        load_suite(str(root / "suite_qa.py"))
    assert "\x1b" not in str(refused.value)
    assert "\x9b" not in str(refused.value)
    assert "gone" in str(refused.value)
