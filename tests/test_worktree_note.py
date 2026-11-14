"""`digline run` and `digline record on` say when the store sits in a linked git
worktree. (P-1685)

Asked for from a first use outside the project: a store in a worktree is
removed with the worktree, and nothing said where it lived. The check reads
the repository and changes nothing, and git is not called where it is not
installed.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
from tests._helpers import cli

from digline.host import environment
from digline.host.environment import WORKTREE_NOTE, in_a_worktree

SUITE_PY = """\
from digline.core import Contains
from digline.run import Case, Response, Suite

def target(case):
    return Response(output="yes", cost_usd=0.0)

suite = Suite(
    tenant="acme", environment="dev", name="support",
    assertions=[Contains(needle="yes")],
    cases=[Case(id="one")],
)
"""


def git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(cwd), *args],
        check=True,
        capture_output=True,
        env={
            **os.environ,
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@example.invalid",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@example.invalid",
        },
    )


@pytest.fixture
def repos(tmp_path: Path) -> tuple[Path, Path]:
    """A repository holding the suite, and a linked worktree of it."""
    main = tmp_path / "main"
    main.mkdir()
    git(main, "init", "-q")
    (main / "suite.py").write_text(SUITE_PY, encoding="utf-8")
    git(main, "add", "-A")
    git(main, "commit", "-q", "-m", "suite")
    linked = tmp_path / "linked"
    git(main, "worktree", "add", "-q", str(linked))
    return main, linked


def test_a_linked_worktree_is_told_from_the_main_one(
    repos: tuple[Path, Path], tmp_path: Path
) -> None:
    main, linked = repos
    assert in_a_worktree(linked)
    assert not in_a_worktree(main)
    outside = tmp_path / "outside"
    outside.mkdir()
    assert not in_a_worktree(outside)


def test_git_is_not_called_where_it_is_not_installed(
    monkeypatch: pytest.MonkeyPatch, repos: tuple[Path, Path]
) -> None:
    _, linked = repos

    def never(*args: object, **kwargs: object) -> object:
        raise AssertionError("git was called on a machine without it")

    def absent(name: str) -> None:
        return None

    monkeypatch.setattr(environment.shutil, "which", absent)
    monkeypatch.setattr(environment.subprocess, "run", never)
    assert not in_a_worktree(linked)


def test_run_says_it_in_a_worktree_and_not_outside(repos: tuple[Path, Path]) -> None:
    main, linked = repos
    there = cli(linked, "run", "--suite", "suite.py")
    assert there.returncode == 0, there.stderr
    assert f"digline: {WORKTREE_NOTE}" in there.stderr
    assert WORKTREE_NOTE not in there.stdout
    here = cli(main, "run", "--suite", "suite.py")
    assert here.returncode == 0, here.stderr
    assert WORKTREE_NOTE not in here.stderr


def test_record_on_says_it_in_a_worktree_and_not_outside(
    repos: tuple[Path, Path],
) -> None:
    main, linked = repos
    there = cli(linked, "record", "on", "--tenant", "acme")
    assert there.returncode == 0, there.stderr
    assert f"digline: {WORKTREE_NOTE}" in there.stderr
    here = cli(main, "record", "on", "--tenant", "acme")
    assert here.returncode == 0, here.stderr
    assert WORKTREE_NOTE not in here.stderr
