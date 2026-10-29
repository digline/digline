"""A command digline prints either runs as it is or declares its placeholder.

(P-1086, P-1087) Three commands carried a placeholder a shell takes for
something else. `<key>` is a redirection from a file named `key`, and `…` is
passed to digline as a suite, which then cannot be imported. Pasted, they failed
in the shell or in digline, and nothing said which word was the reader's to
fill in.

The rule each test holds:
- a placeholder digline cannot fill is spelled so a shell passes it through,
  and the sentence around the command says it is one;
- one digline can fill is filled, and the command runs as printed.

Each test provokes the message, takes the command as it is printed, and pastes
it into `bash`, as a person would.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

from tests._helpers import cli

from digline.cli import EXIT_OK

SUITE = """
from digline.core import Contains
from digline.run import Case, Response, Suite

suite = Suite(
    tenant="acme",
    environment="dev",
    name="hello",
    assertions=[Contains(needle="hello")],
    cases=[Case(id="greet"), Case(id="part"), Case(id="wave")],
)


def target(case):
    return Response(output="hello world")
"""

#: The same suite, whose code ends digline's process on its second case: the
#: run is journalled and never written.
INTERRUPTED = SUITE.replace(
    'def target(case):\n    return Response(output="hello world")',
    'def target(case):\n    if case.id == "part":\n        raise SystemExit(3)\n'
    '    return Response(output="hello world")',
)


def repo(root: Path, source: str = SUITE) -> Path:
    (root / "suite.py").write_text(source, encoding="utf-8")
    return root


def in_bash(root: Path, command: str) -> subprocess.CompletedProcess[str]:
    """`command` pasted into bash in `root`, with this interpreter's `digline`
    first on the path."""
    bin_dir = str(Path(sys.executable).parent)
    env = {**os.environ, "PATH": bin_dir + os.pathsep + os.environ.get("PATH", "")}
    return subprocess.run(
        ["bash", "-c", command],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def key_of(document: Path) -> str:
    return document.name.removesuffix(".json")


def test_compare_without_a_reference_declares_the_key_it_cannot_know(
    tmp_path: Path,
) -> None:
    """R3: `compare` with no reference names the promote to make, and the run's
    key is the reader's to fill in."""
    root = repo(tmp_path)
    assert cli(root, "run", "--suite", "suite.py").returncode == EXIT_OK
    refused = cli(root, "compare", "--suite", "suite.py", "--run", "latest")
    (command,) = re.findall(r"'(digline promote [^']*)'", refused.stderr)
    assert "<" not in command and ">" not in command, command
    assert "KEY" in command.split()
    assert "with KEY the key of the run" in refused.stderr, refused.stderr
    pasted = in_bash(root, command)
    assert "No such file or directory" not in pasted.stderr, pasted.stderr
    assert pasted.stderr.startswith("digline") or "digline" in pasted.stderr


def test_delete_of_the_reference_declares_suite_and_key(tmp_path: Path) -> None:
    """R7: deleting the run under the reference names the promote that frees
    it. The suite and the other run are the reader's to fill in, and filled
    in, the command runs."""
    root = repo(tmp_path)
    assert cli(root, "run", "--suite", "suite.py").returncode == EXIT_OK
    assert cli(root, "run", "--suite", "suite.py").returncode == EXIT_OK
    first, second = sorted((root / ".digline").glob("*/runs/hello/*.json"))
    promoted = cli(
        root, "promote", "--suite", "suite.py", "--run", key_of(first),
        "--replacing", "none",
    )  # fmt: skip
    assert promoted.returncode == EXIT_OK, promoted.stderr
    refused = cli(root, "delete", "--suite", "suite.py", "--run", key_of(first))
    (command,) = re.findall(r"`(digline promote [^`]*)`", refused.stderr)
    assert "…" not in command and "<" not in command, command
    assert {"SUITE", "KEY"} <= set(command.split()), command
    assert "where SUITE is the suite and KEY another run's key" in refused.stderr
    filled = command.replace("SUITE", "suite.py").replace("KEY", key_of(second))
    pasted = in_bash(root, filled)
    assert pasted.returncode == EXIT_OK, pasted.stderr
    # "and delete this one after": the run is no longer under the reference.
    deleted = cli(root, "delete", "--suite", "suite.py", "--run", key_of(first))
    assert deleted.returncode == EXIT_OK, deleted.stderr


def test_the_note_on_an_unfinished_run_pastes_and_finishes_it(tmp_path: Path) -> None:
    """R9: a journalled run that was never written is named with the command
    that finishes it, with the suite and the options as given, so it runs as
    printed."""
    store = tmp_path / "store"
    store.mkdir()
    root = repo(tmp_path, INTERRUPTED)
    given = ("--root", "store", "--tenant", "acme", "--env", "dev")
    stopped = cli(root, "run", "--suite", "suite.py", *given)
    assert stopped.returncode != EXIT_OK
    repo(root)
    noted = cli(root, "run", "--suite", "suite.py", *given)
    (command,) = re.findall(r"Finish it with `([^`]*)`", noted.stderr)
    assert "…" not in command, command
    assert command.startswith("digline run --suite suite.py --resume ")
    assert "--root store --tenant acme --env dev" in command, command
    pasted = in_bash(root, command)
    assert pasted.returncode == EXIT_OK, pasted.stderr
