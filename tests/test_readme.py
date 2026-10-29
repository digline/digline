"""The README, executed.

The front page is the one artifact a reader trusts without checking, so nothing
on it is allowed to be typed by hand:

- each suite in a ```python block is written to a file and run;
- every line of terminal output in a ```console block has to come back out of a
  real execution of the suite that block belongs to;
- the assertion table has to name every assertion the package exports;
- the command table has to name exactly the subcommands `--help` announces;
- every relative link has to resolve.

**A page can hold more than one suite, and a console block says whose it is.**
Its fence reads ```console suite=<name>, the `name=` of a suite on the page.
Ownership is declared, not inferred from where the block stands: a block may
come before its suite or after it. A console block with no label, or a label
naming no suite on the page, is red. The ```bash blocks are install lines, not
transcripts, and are never replayed.

**The number of suites is fixed here**, in `SECTIONS`, with the replay of each.
A suite added to the page without a replay in this file does not pass.

The run keys are the one thing that legitimately differs between two executions,
so they are normalised away — and only they.
"""

from __future__ import annotations

import ast
import re
import subprocess
import sys
import tomllib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pytest
from tests._helpers import baseline_in

from digline.cli import EXIT_OK, EXIT_WORSE

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
TEXT = README.read_text(encoding="utf-8")

#: `2026-08-26T15-44-09-282929-00-00-e7421ec503ccefe8` — the slugged instant and
#: the config hash. It changes on every run and means nothing to the reader.
KEY_RE = re.compile(r"\d{4}-\d{2}-\d{2}T[\d-]+-[0-9a-f]{16}")

#: The sign-off the quickstart drops to produce the regression the README shows.
SIGN_OFF = " — Northwind Support"

#: A fenced block: the info string after the backticks, and its body.
FENCE = re.compile(r"^```([^\n]*)\n(.*?)^```", re.M | re.S)

#: The label that gives a console block to a suite.
LABEL = re.compile(r"console suite=([\w.-]+)")


def fences() -> list[tuple[str, str, int]]:
    """Every fenced block on the page: its info string, its body, and where it
    starts in `TEXT`."""
    return [(m.group(1).strip(), m.group(2), m.start()) for m in FENCE.finditer(TEXT)]


def suite_name(source: str) -> str | None:
    """The `name=` of the one `Suite(...)` call in a block, read from the code."""
    names = [
        keyword.value.value
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "Suite"
        for keyword in node.keywords
        if keyword.arg == "name"
        and isinstance(keyword.value, ast.Constant)
        and isinstance(keyword.value.value, str)
    ]
    return names[0] if len(names) == 1 else None


def suites() -> dict[str, str]:
    """Each ```python block on the page, by the name of the suite it declares."""
    found: dict[str, str] = {}
    for info, body, _at in fences():
        if info == "python":
            name = suite_name(body)
            assert name is not None, "a ```python block declares no one Suite(name=)"
            assert name not in found, f"two suites on the page are named {name!r}"
            found[name] = body
    return found


def console_blocks() -> list[tuple[str | None, str]]:
    """Each ```console block: the suite its label names, or `None` without a
    label, and its body."""
    labelled: list[tuple[str | None, str]] = []
    for info, body, _at in fences():
        if info == "console" or info.startswith("console "):
            match = LABEL.fullmatch(info)
            labelled.append((match.group(1) if match else None, body))
    return labelled


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


def entries(suite: str | None = None) -> list[tuple[str, list[str]]]:
    """Every `$ command` in the console blocks of `suite`, or of the whole page,
    with the lines printed under it."""
    found: list[tuple[str, list[str]]] = []
    for owner, body in console_blocks():
        if suite is not None and owner != suite:
            continue
        for line in body.splitlines():
            if line.startswith("$ "):
                found.append((line[2:].strip(), []))
            elif line.strip() and found:
                found[-1][1].append(normalise(line))
    return found


# --------------------------------------------------------------------------- #
# Each suite on the page, and how it is replayed
# --------------------------------------------------------------------------- #


def replay_support(workdir: Path) -> tuple[set[str], int]:
    """The quickstart, exactly as the page tells it, and what it printed on
    either stream, as a terminal shows both.

    Between the promotion and the second run the sign-off is dropped from the
    *second* answer — that is the "make it worse" the README asks for, and it
    is what produces the two regressed checks the page shows, on the case the
    page names.
    """
    printed: list[str] = []

    first = cli(workdir, "run", "--suite", "suite.py")
    assert first.returncode == EXIT_OK, first.stderr
    printed.extend((first.stdout, first.stderr))

    promoted = cli(
        workdir,
        "promote",
        "--replacing",
        baseline_in(workdir),
        "--suite",
        "suite.py",
        "--run",
        "latest",
    )
    assert promoted.returncode == EXIT_OK, promoted.stderr
    printed.extend((promoted.stdout, promoted.stderr))

    suite = workdir / "suite.py"
    source = suite.read_text(encoding="utf-8")
    # Exactly two, so "the last one" is `how-do-i-return` and stays so.
    assert source.count(SIGN_OFF) == 2
    head, _sep, tail = source.rpartition(SIGN_OFF)
    suite.write_text(head + tail, encoding="utf-8")

    second = cli(workdir, "run", "--suite", "suite.py")
    assert second.returncode == EXIT_OK, second.stderr
    printed.extend((second.stdout, second.stderr))

    compared = cli(workdir, "compare", "--suite", "suite.py", "--run", "latest")
    printed.extend((compared.stdout, compared.stderr))

    lines = {normalise(line) for chunk in printed for line in chunk.splitlines()}
    return lines - {""}, compared.returncode


@dataclass(frozen=True)
class Section:
    """A suite on the page: how it is replayed, the exit its arc ends on, and
    whether the page must show that exit."""

    replay: Callable[[Path], tuple[set[str], int]]
    exits: int
    shows_exit: bool


#: Every suite the page holds, and nothing else. Fixed: a suite added to the
#: page without its replay here is refused by the count below.
SECTIONS: dict[str, Section] = {
    # The quickstart: a judge, two answers signed, and the second made worse.
    "support": Section(replay=replay_support, exits=EXIT_WORSE, shows_exit=True),
}
SUITES_ON_THE_PAGE = 1


@pytest.fixture(params=sorted(SECTIONS))
def section(request: pytest.FixtureRequest, tmp_path: Path) -> tuple[str, Path]:
    """One suite of the page, on disk, ready to run."""
    name: str = request.param
    workdir = tmp_path / name
    workdir.mkdir()
    (workdir / "suite.py").write_text(suites()[name], encoding="utf-8")
    return name, workdir


@pytest.fixture
def quickstart(tmp_path: Path) -> Path:
    """The Northwind quickstart, on disk, ready to run."""
    workdir = tmp_path / "quickstart"
    workdir.mkdir()
    (workdir / "suite.py").write_text(suites()["support"], encoding="utf-8")
    return workdir


# --------------------------------------------------------------------------- #
# Which block belongs to which suite
# --------------------------------------------------------------------------- #


def test_the_page_shows_exactly_the_suites_this_file_replays() -> None:
    """A fixed count and the same names: a suite added to the page without a
    replay here, or one removed from the page, is red."""
    shown = suites()
    assert len(shown) == SUITES_ON_THE_PAGE == len(SECTIONS), sorted(shown)
    assert set(shown) == set(SECTIONS)


def test_every_console_block_names_its_suite() -> None:
    unlabelled = [body.splitlines()[0] for owner, body in console_blocks() if not owner]
    assert not unlabelled, (
        "a ```console block with no `suite=` label belongs to no suite and is "
        f"replayed by nothing: {unlabelled}"
    )


def test_every_label_names_a_suite_on_the_page() -> None:
    named = {owner for owner, _body in console_blocks() if owner}
    assert named <= set(suites()), f"labels naming no suite: {named - set(suites())}"


def test_every_suite_owns_a_console_block() -> None:
    """The control: a suite whose blocks all went missing would pass every
    replay test vacuously."""
    owners = {owner for owner, _body in console_blocks()}
    for name in suites():
        assert name in owners, f"no ```console block is labelled suite={name}"


# --------------------------------------------------------------------------- #
# The suites on the front page are suites that run
# --------------------------------------------------------------------------- #


def test_every_suite_is_self_contained(section: tuple[str, Path]) -> None:
    """No import from a project the reader does not have, and the target in the
    block, which is what makes it copyable."""
    _name, workdir = section
    source = (workdir / "suite.py").read_text(encoding="utf-8")
    imports = re.findall(r"^(?:from|import)\s+([\w.]+)", source, re.MULTILINE)
    assert set(imports) == {"digline.core", "digline.run"}
    assert "def target(" in source


def test_the_quickstart_carries_its_judge(quickstart: Path) -> None:
    """The quickstart's regression is a judge's score falling: the judge has to
    be in the block, or the page shows a regression it cannot produce."""
    assert "def judge(" in (quickstart / "suite.py").read_text(encoding="utf-8")


def test_the_readme_hands_the_tenant_over_right_after_the_suite() -> None:
    """The copy source of friction 64: a suite copied between customers with
    its `tenant=` line unchanged files one customer's runs under another's.
    The value is ours, so the paragraph under the quickstart's block has to say
    so, and say what a tenant is for, about the tenant the block declares."""
    source = suites()["support"]
    tenant = re.search(r'tenant="([^"]+)"', source)
    assert tenant is not None
    (at,) = [at for info, body, at in fences() if info == "python" and body == source]
    after = TEXT[at:].split("```python\n", 1)[1].split("```\n", 1)[1]
    paragraph = after.strip().split("\n\n", 1)[0]
    assert paragraph.startswith(f'`tenant="{tenant.group(1)}"` is ours')
    assert "one customer" in paragraph
    assert "`.digline/<tenant>/`" in paragraph


def test_every_suite_runs(section: tuple[str, Path]) -> None:
    _name, workdir = section
    done = cli(workdir, "run", "--suite", "suite.py")
    assert done.returncode == EXIT_OK, done.stderr
    assert KEY_RE.fullmatch(done.stdout.strip())


# --------------------------------------------------------------------------- #
# Every printed line came out of an execution of its own suite
# --------------------------------------------------------------------------- #


def test_every_command_on_the_page_is_a_digline_command() -> None:
    shown = {command.split()[0] for command, _output in entries()}
    assert shown <= {"digline", "echo"}


def test_every_printed_line_comes_back_out_of_a_real_run(
    section: tuple[str, Path],
) -> None:
    """The anti-fabrication rule. A README that quotes output nobody produced is
    a README that will quote output nobody can produce. Each block is held to
    the run of its own suite."""
    name, workdir = section
    actual, _returncode = SECTIONS[name].replay(workdir)
    for command, output in entries(name):
        if command.startswith("echo"):
            continue
        for line in output:
            assert line in actual, f"`{command}` ({name}) never printed: {line!r}"


def test_the_replay_hears_standard_error_too(section: tuple[str, Path]) -> None:
    """A terminal shows both streams, so a console block may show both.

    `digline run` puts only the key on standard output and says everything
    else on standard error: the plan before the first call, the bill after the
    last. A replay that read standard output alone could not hold a block that
    quoted any of it, right or wrong, and the anti-fabrication rule above would
    have had nothing to say about half of what the command prints.
    """
    name, workdir = section
    actual, _returncode = SECTIONS[name].replay(workdir)
    plans = [line for line in actual if line.startswith("digline: tenant ")]
    assert plans, f"the replay of {name} heard none of what `digline run` says"


def test_the_exit_code_on_the_page_is_the_exit_code(section: tuple[str, Path]) -> None:
    name, workdir = section
    _actual, returncode = SECTIONS[name].replay(workdir)
    assert returncode == SECTIONS[name].exits
    shown = [output for command, output in entries(name) if command.startswith("echo")]
    if SECTIONS[name].shows_exit:
        assert shown, f"the page no longer shows the exit code of {name}"
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
