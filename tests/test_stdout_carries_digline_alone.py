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

import ast
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


#: Each front end, and where in it standard output may be touched: a whole
#: module (`None`) or the named functions in one. Everywhere else a new window
#: is covered because nothing there can write to standard output directly.
#: pytest-digline is not here: under pytest standard output is pytest's, and its
#: one reader is the terminal (ADR 0043 §8, amended 2026-10-18).
OUTPUT_FUNCTIONS: dict[str, dict[str, frozenset[str] | None]] = {
    "digline.cli": {"output.py": None},
    "digline_mcp": {"server.py": frozenset({"_flushed"})},
}


def _touches_stdout(node: ast.AST) -> str:
    """What `node` does to standard output, or `""` when it does nothing."""
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        return "print(...)" if node.func.id == "print" else ""
    if isinstance(node, ast.Attribute) and ast.unparse(node) in {
        "sys.stdout",
        "sys.__stdout__",
    }:
        return ast.unparse(node)
    if (
        isinstance(node, ast.Call)
        and ast.unparse(node.func) == "os.write"
        and node.args
        and ast.unparse(node.args[0]) == "1"
    ):
        return "os.write(1, ...)"
    return ""


def _offenders(
    node: ast.AST, allowed: frozenset[str], inside: frozenset[str], where: str
) -> list[str]:
    """Every touch of standard output under `node` outside the `allowed`
    functions, as `where:line what`."""
    if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
        inside = inside | {node.name}
    found: list[str] = []
    touched = _touches_stdout(node)
    if touched and not (inside & allowed):
        found.append(f"{where}:{getattr(node, 'lineno', '?')} {touched}")
    for child in ast.iter_child_nodes(node):
        found += _offenders(child, allowed, inside, where)
    return found


@pytest.mark.parametrize("module", sorted(OUTPUT_FUNCTIONS))
def test_no_front_end_touches_standard_output_outside_its_output_function(
    module: str,
) -> None:
    """The structural half, in the style of `test_layering.py`: a `print`, a
    `sys.stdout` or `sys.__stdout__`, or an `os.write` to descriptor 1 in a front
    end is refused outside the place that owns standard output. The tests above
    hold the windows that exist; this one is why the next one is born covered."""
    import importlib

    package = importlib.import_module(module)
    roots = [Path(entry) for entry in package.__path__]
    allowed = OUTPUT_FUNCTIONS[module]
    offenders: list[str] = []
    for source in sorted({s for root in roots for s in root.glob("*.py")}):
        if source.name in allowed and allowed[source.name] is None:
            continue
        tree = ast.parse(source.read_text(encoding="utf-8"))
        offenders += _offenders(
            tree,
            allowed.get(source.name) or frozenset(),
            frozenset(),
            f"{module}/{source.name}",
        )
    assert offenders == [], (
        "these touch standard output outside the place that owns it, so what "
        "they write would share it with the user's code (ADR 0043 §8): "
        + ", ".join(offenders)
    )
