"""`digline run` says where the run went and what to type next. (B0, P-1072)

Two lines on standard error, after the key, which stays alone on standard
output:

    digline: recorded <the path of the document this run wrote>
    digline: next: <command>  # <what it does>

The `# …` is a shell comment on purpose: the line without its prefix can be
pasted whole and it runs.

Five states, and a fixed count of each line in each:

| state                                  | recorded | next    |
|----------------------------------------|----------|---------|
| 1. no reference                        | 1        | promote |
| 2. a reference present                 | 1        | compare |
| 3. written, nothing judged             | 1        | none    |
| 4. refused on the reference's schema   | 0        | none    |
| 5. failed before writing               | 0        | none    |

- `recorded` comes out if and only if a document was written, and it names a
  path that exists.
- `next` names a command that uses what this run produced. State 3 produced
  nothing to use, so it says none, with a reference present too.
- States 4 and 5 carry their instruction in the refusal.
- `run` says nothing about whether the reference is any good: a file there is
  enough to name `compare`, and `compare` judges it.
"""

from __future__ import annotations

import json
import shlex
import subprocess
import sys
from pathlib import Path

from tests._helpers import cli

from digline.cli import EXIT_OK, EXIT_UNJUDGED, EXIT_USAGE
from digline.core.run import SCHEMA_VERSION

RECORDED = "digline: recorded "
NEXT = "digline: next: "
PROMOTE_SAYS = "  # keeps this run as the reference"
COMPARE_SAYS = "  # says whether anything got worse"

SUITE = """
from digline.core import Contains
from digline.run import Case, Response, Suite

suite = Suite(
    tenant="acme",
    environment="dev",
    name="hello",
    assertions=[Contains(needle="hello")],
    cases=[Case(id="greet")],
)


def target(case):
    return Response(output="hello world")
"""

DOWN = SUITE.replace(
    'return Response(output="hello world")', 'raise TimeoutError("the app is down")'
)


def lines(stderr: str, prefix: str) -> list[str]:
    return [line for line in stderr.splitlines() if line.startswith(prefix)]


def repo(root: Path, source: str = SUITE, name: str = "suite.py") -> Path:
    (root / name).write_text(source, encoding="utf-8")
    return root


def promote(root: Path, suite: str = "suite.py") -> None:
    done = cli(
        root, "promote", "--suite", suite, "--run", "latest", "--replacing", "none"
    )
    assert done.returncode == EXIT_OK, done.stderr


def recorded_path(root: Path, line: str) -> Path:
    return root / line.removeprefix(RECORDED)


# --------------------------------------------------------------------------- #
# The five rows
# --------------------------------------------------------------------------- #


def test_no_reference_says_recorded_and_next_promote(tmp_path: Path) -> None:
    ran = cli(repo(tmp_path), "run", "--suite", "suite.py")
    assert ran.returncode == EXIT_OK, ran.stderr
    (recorded,) = lines(ran.stderr, RECORDED)
    assert recorded_path(tmp_path, recorded).is_file()
    assert lines(ran.stderr, NEXT) == [
        "digline: next: digline promote --suite suite.py --run latest "
        f"--replacing none{PROMOTE_SAYS}"
    ]


def test_a_reference_present_says_recorded_and_next_compare(tmp_path: Path) -> None:
    root = repo(tmp_path)
    assert cli(root, "run", "--suite", "suite.py").returncode == EXIT_OK
    promote(root)
    ran = cli(root, "run", "--suite", "suite.py")
    assert ran.returncode == EXIT_OK, ran.stderr
    (recorded,) = lines(ran.stderr, RECORDED)
    assert recorded_path(root, recorded).is_file()
    assert lines(ran.stderr, NEXT) == [
        f"digline: next: digline compare --suite suite.py --run latest{COMPARE_SAYS}"
    ]


def test_nothing_judged_says_recorded_and_no_next(tmp_path: Path) -> None:
    ran = cli(repo(tmp_path, DOWN), "run", "--suite", "suite.py")
    assert ran.returncode == EXIT_UNJUDGED, ran.stderr
    (recorded,) = lines(ran.stderr, RECORDED)
    assert recorded_path(tmp_path, recorded).is_file()
    assert lines(ran.stderr, NEXT) == []


def test_nothing_judged_says_no_next_with_a_reference_present(tmp_path: Path) -> None:
    root = repo(tmp_path)
    assert cli(root, "run", "--suite", "suite.py").returncode == EXIT_OK
    promote(root)
    repo(root, DOWN)
    ran = cli(root, "run", "--suite", "suite.py")
    assert ran.returncode == EXIT_UNJUDGED, ran.stderr
    assert len(lines(ran.stderr, RECORDED)) == 1
    assert lines(ran.stderr, NEXT) == []


def test_a_refusal_on_the_schema_says_neither(tmp_path: Path) -> None:
    root = repo(tmp_path)
    assert cli(root, "run", "--suite", "suite.py").returncode == EXIT_OK
    promote(root)
    (baseline,) = (root / ".digline").glob("*/baselines/hello.json")
    document = json.loads(baseline.read_text(encoding="utf-8"))
    document["schema_version"] = SCHEMA_VERSION - 1
    baseline.write_text(json.dumps(document), encoding="utf-8")
    runs_before = sorted((root / ".digline").glob("*/runs/*/*.json"))
    ran = cli(root, "run", "--suite", "suite.py")
    assert ran.returncode == EXIT_USAGE, ran.stderr
    assert "could not be compared" in ran.stderr
    assert lines(ran.stderr, RECORDED) == []
    assert lines(ran.stderr, NEXT) == []
    assert sorted((root / ".digline").glob("*/runs/*/*.json")) == runs_before


def test_a_failure_before_writing_says_neither(tmp_path: Path) -> None:
    source = SUITE.replace("def target(case):", "def not_the_target(case):")
    ran = cli(repo(tmp_path, source), "run", "--suite", "suite.py")
    assert ran.returncode == EXIT_USAGE, ran.stderr
    assert "has no attribute 'target'" in ran.stderr
    assert lines(ran.stderr, RECORDED) == []
    assert lines(ran.stderr, NEXT) == []
    assert not list(tmp_path.glob(".digline/*/runs/*/*.json"))


# --------------------------------------------------------------------------- #
# The rules the table holds
# --------------------------------------------------------------------------- #


def test_the_key_stays_alone_on_standard_output(tmp_path: Path) -> None:
    """The action reads standard output as the run key."""
    ran = cli(repo(tmp_path), "run", "--suite", "suite.py")
    assert ran.returncode == EXIT_OK, ran.stderr
    (key,) = ran.stdout.splitlines()
    assert RECORDED not in ran.stdout and NEXT not in ran.stdout
    assert lines(ran.stderr, RECORDED) == [
        f"digline: recorded .digline/acme/runs/hello/{key}.json"
    ]


def test_the_recorded_path_is_read_from_where_the_command_ran(tmp_path: Path) -> None:
    """Relative to `--root`, which is where `.digline/` is: the path a person
    reads from the folder they typed the command in."""
    store = tmp_path / "store"
    store.mkdir()
    repo(tmp_path)
    ran = cli(tmp_path, "run", "--suite", "suite.py", "--root", "store")
    assert ran.returncode == EXIT_OK, ran.stderr
    (recorded,) = lines(ran.stderr, RECORDED)
    path = recorded.removeprefix(RECORDED)
    assert path.startswith("store/.digline/")
    assert (tmp_path / path).is_file()


def test_next_repeats_the_options_that_move_where_it_looks(tmp_path: Path) -> None:
    """`--root`, `--tenant` and `--env` on both commands, `--target` on
    `promote` alone: `compare` takes no target."""
    store = tmp_path / "store"
    store.mkdir()
    repo(tmp_path)
    given = ("--root", "store", "--tenant", "acme", "--env", "dev")
    ran = cli(
        tmp_path, "run", "--suite", "suite.py", *given, "--target", "suite.py:target"
    )
    assert ran.returncode == EXIT_OK, ran.stderr
    assert lines(ran.stderr, NEXT) == [
        "digline: next: digline promote --suite suite.py --run latest "
        "--replacing none --root store --tenant acme --env dev "
        f"--target suite.py:target{PROMOTE_SAYS}"
    ]
    promote_line = lines(ran.stderr, NEXT)[0]
    pasted(tmp_path, promote_line)
    again = cli(tmp_path, "run", "--suite", "suite.py", *given)
    assert lines(again.stderr, NEXT) == [
        "digline: next: digline compare --suite suite.py --run latest "
        f"--root store --tenant acme --env dev{COMPARE_SAYS}"
    ]


def pasted(root: Path, line: str) -> subprocess.CompletedProcess[str]:
    """The line without its prefix, run as a shell would: the comment dropped,
    the words split as the shell splits them, `digline` as this interpreter's."""
    words = shlex.split(line.removeprefix("digline: next: "), comments=True)
    assert words[0] == "digline"
    done = subprocess.run(
        [sys.executable, "-m", "digline.cli", *words[1:]],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == EXIT_OK, done.stderr
    return done


def test_each_next_line_pasted_whole_runs(tmp_path: Path) -> None:
    root = repo(tmp_path)
    first = cli(root, "run", "--suite", "suite.py")
    (promote_line,) = lines(first.stderr, NEXT)
    pasted(root, promote_line)
    second = cli(root, "run", "--suite", "suite.py")
    (compare_line,) = lines(second.stderr, NEXT)
    compared = pasted(root, compare_line)
    assert "Nothing got worse" in compared.stdout


def test_a_suite_path_with_a_space_is_quoted_so_it_pastes(tmp_path: Path) -> None:
    root = repo(tmp_path, name="my suite.py")
    ran = cli(root, "run", "--suite", "my suite.py")
    assert ran.returncode == EXIT_OK, ran.stderr
    (line,) = lines(ran.stderr, NEXT)
    assert "--suite 'my suite.py'" in line
    pasted(root, line)


def test_a_reference_compare_would_refuse_still_names_compare(tmp_path: Path) -> None:
    """A file there is enough: whether it is a usable reference is `compare`'s
    to say, and `run` judges nothing about it."""
    root = repo(tmp_path)
    assert cli(root, "run", "--suite", "suite.py").returncode == EXIT_OK
    promote(root)
    (baseline,) = (root / ".digline").glob("*/baselines/hello.json")
    baseline.write_text("not json", encoding="utf-8")
    ran = cli(root, "run", "--suite", "suite.py")
    assert ran.returncode == EXIT_OK, ran.stderr
    assert lines(ran.stderr, NEXT) == [
        f"digline: next: digline compare --suite suite.py --run latest{COMPARE_SAYS}"
    ]
