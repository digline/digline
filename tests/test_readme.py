"""The README, executed.

The front page is the one artifact a reader trusts without checking, so nothing
on it is allowed to be typed by hand:

- the suite in the ```python block is written to a file and run;
- every line of terminal output in a ```console block has to come back out of a
  real execution of that same suite;
- the assertion table has to name every assertion the package exports;
- the command table has to name exactly the subcommands `--help` announces;
- every relative link has to resolve.

The run keys are the one thing that legitimately differs between two executions,
so they are normalised away — and only they.
"""

from __future__ import annotations

import re
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

from digline.cli import EXIT_OK, EXIT_WORSE

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
TEXT = README.read_text(encoding="utf-8")

#: `2026-08-26T15-44-09-282929-00-00-e7421ec503ccefe8` — the slugged instant and
#: the config hash. It changes on every run and means nothing to the reader.
KEY_RE = re.compile(r"\d{4}-\d{2}-\d{2}T[\d-]+-[0-9a-f]{16}")

#: The sign-off the quickstart drops to produce the regression the README shows.
SIGN_OFF = " — Northwind Support"


def blocks(language: str) -> list[str]:
    return re.findall(rf"```{language}\n(.*?)```", TEXT, re.DOTALL)


def normalise(line: str) -> str:
    return KEY_RE.sub("<KEY>", line).rstrip()


def cli(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "digline.cli", *args],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )


# --------------------------------------------------------------------------- #
# The suite on the front page is a suite that runs
# --------------------------------------------------------------------------- #


def test_the_readme_shows_exactly_one_suite() -> None:
    """More than one and "the quickstart" stops having a referent."""
    assert len(blocks("python")) == 1


@pytest.fixture
def quickstart(tmp_path: Path) -> Path:
    """The README's own code block, on disk, ready to run."""
    workdir = tmp_path / "quickstart"
    workdir.mkdir()
    (workdir / "suite.py").write_text(blocks("python")[0], encoding="utf-8")
    return workdir


def test_the_readme_suite_is_self_contained(quickstart: Path) -> None:
    """No import from a project the reader does not have. The judge and the
    target are in the block, which is what makes it copyable."""
    source = (quickstart / "suite.py").read_text(encoding="utf-8")
    imports = re.findall(r"^(?:from|import)\s+([\w.]+)", source, re.MULTILINE)
    assert set(imports) == {"digline.core", "digline.run"}
    assert "def judge(" in source and "def target(" in source


def test_the_readme_suite_runs(quickstart: Path) -> None:
    done = cli(quickstart, "run", "--suite", "suite.py")
    assert done.returncode == EXIT_OK, done.stderr
    assert KEY_RE.fullmatch(done.stdout.strip())


# --------------------------------------------------------------------------- #
# Every printed line came out of an execution
# --------------------------------------------------------------------------- #


def replay(workdir: Path) -> tuple[set[str], int]:
    """The quickstart, exactly as the page tells it, and what it printed.

    Between the promotion and the second run the sign-off is dropped from the
    *second* answer — that is the "make it worse" the README asks for, and it
    is what produces the two regressed checks the page shows, on the case the
    page names.
    """
    printed: list[str] = []

    first = cli(workdir, "run", "--suite", "suite.py")
    assert first.returncode == EXIT_OK, first.stderr
    printed.append(first.stdout)

    promoted = cli(workdir, "promote", "--suite", "suite.py", "--run", "latest")
    assert promoted.returncode == EXIT_OK, promoted.stderr
    printed.append(promoted.stdout)

    suite = workdir / "suite.py"
    source = suite.read_text(encoding="utf-8")
    # Exactly two, so "the last one" is `how-do-i-return` and stays so.
    assert source.count(SIGN_OFF) == 2
    head, _sep, tail = source.rpartition(SIGN_OFF)
    suite.write_text(head + tail, encoding="utf-8")

    second = cli(workdir, "run", "--suite", "suite.py")
    assert second.returncode == EXIT_OK, second.stderr
    printed.append(second.stdout)

    compared = cli(workdir, "compare", "--suite", "suite.py", "--run", "latest")
    printed.append(compared.stdout)

    lines = {normalise(line) for chunk in printed for line in chunk.splitlines()}
    return lines - {""}, compared.returncode


def console_entries() -> list[tuple[str, list[str]]]:
    """Every `$ command` in the README with the lines printed under it."""
    entries: list[tuple[str, list[str]]] = []
    for block in blocks("console"):
        for line in block.splitlines():
            if line.startswith("$ "):
                entries.append((line[2:].strip(), []))
            elif line.strip() and entries:
                entries[-1][1].append(normalise(line))
    return entries


def test_every_command_on_the_page_is_a_digline_command() -> None:
    shown = {command.split()[0] for command, _output in console_entries()}
    assert shown <= {"digline", "echo"}


def test_every_printed_line_comes_back_out_of_a_real_run(quickstart: Path) -> None:
    """The anti-fabrication rule. A README that quotes output nobody produced is
    a README that will quote output nobody can produce."""
    actual, _returncode = replay(quickstart)
    for command, output in console_entries():
        if command.startswith("echo"):
            continue
        for line in output:
            assert line in actual, f"`{command}` never printed: {line!r}"


def test_the_exit_code_on_the_page_is_the_exit_code(quickstart: Path) -> None:
    _actual, returncode = replay(quickstart)
    assert returncode == EXIT_WORSE
    shown = [
        output for command, output in console_entries() if command.startswith("echo")
    ]
    assert shown, "the page no longer shows an exit code"
    for output in shown:
        assert [int(line) for line in output] == [returncode]


# --------------------------------------------------------------------------- #
# The tables cannot fall behind the code
# --------------------------------------------------------------------------- #


def test_the_tables_name_every_assertion_the_package_exports() -> None:
    """Derived from `__all__`, never from a list kept here: a hand-kept list has
    to be remembered, and forgetting it makes the test *pass*."""
    import digline.core as core

    bases = (core.AssertionBase, core.RunAssertionBase)
    exported = [
        name
        for name in core.__all__
        if isinstance(obj := getattr(core, name), type) and issubclass(obj, bases)
    ]
    # A guard on the guard: an empty derivation would prove nothing below.
    assert len(exported) >= 12, exported
    for name in exported:
        assert f"`{name}`" in TEXT, f"{name} is exported but not on the front page"


def test_the_command_table_is_the_one_help_announces() -> None:
    """Compared with `--help` itself, so a subcommand cannot be added, renamed
    or dropped without the page saying so."""
    helped = subprocess.run(
        [sys.executable, "-m", "digline.cli", "--help"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    match = re.search(r"\{([a-z,]+)\}", helped)
    assert match is not None, helped
    announced = set(match.group(1).split(","))

    table = TEXT.split("## Commands", 1)[1].split("\n## ", 1)[0]
    documented = set(re.findall(r"\|\s*`digline (\w+)`", table))
    assert documented == announced


def test_every_relative_link_resolves() -> None:
    targets = re.findall(r"\]\(([^)]+)\)", TEXT)
    relative = [t for t in targets if not t.startswith(("http://", "https://", "#"))]
    assert len(relative) >= 6, relative
    for target in relative:
        assert (ROOT / target.split("#", 1)[0]).exists(), f"broken link: {target}"


def test_the_pypi_badge_and_the_install_line_stand_or_fall_together() -> None:
    """Published or not, the page must not be caught half-way.

    What this refuses is the state in between: a badge above an install line the
    reader cannot follow, or the reverse.

    The badge is the dynamic shield, which renders whatever PyPI currently says.
    That is why there is no version to compare with `pyproject.toml` here: a
    static badge carries a version a release can leave behind — and did, since
    the page said `0.1.0` in its Status section while `0.3.0` was on PyPI — and
    the shield cannot fall behind because it holds no copy of the number.
    """
    badge = "img.shields.io/pypi/v/digline" in TEXT
    installable = "pip install digline" in TEXT or "uv add digline" in TEXT
    assert badge == installable, (
        "the PyPI badge and the install line must appear together: "
        f"badge={badge}, install line={installable}"
    )


def test_the_status_version_is_the_version_in_pyproject() -> None:
    """The prose beside the badge is gated too, because it drifted twice.

    The badge holds no copy of the number, so it cannot fall behind. The
    sentence under **Status** does hold one, and that is the whole difference:
    the test above explains why the *badge* is dynamic, citing the release that
    left `0.1.0` on the page while `0.3.0` was on PyPI — and then 0.4.0 shipped
    and the same line said `0.3.0` again, under a badge already rendering
    `0.4.0`. Twice is not an accident, it is an ungated fact recorded in two
    places.

    So this reads the number the release actually bumps. `tomllib` is stdlib
    from 3.11 and this repository is 3.12+, so the check costs no dependency —
    the same reasoning that picked TOML for the suite format on the roadmap.
    """
    with (ROOT / "pyproject.toml").open("rb") as handle:
        expected = tomllib.load(handle)["project"]["version"]

    status = re.search(r"^## Status\s*\n+`([^`]+)`", TEXT, re.M)
    assert status is not None, (
        "the README has no `## Status` section opening with a version in "
        "backticks. If the section moved, move this check with it rather than "
        "deleting it: the version in that sentence is the one that drifts."
    )
    assert status.group(1) == expected, (
        f"README's Status section says `{status.group(1)}` and "
        f"pyproject.toml says {expected}. The release bumps pyproject; this "
        "sentence is written by hand and has fallen behind twice. Update the "
        "Status line."
    )
