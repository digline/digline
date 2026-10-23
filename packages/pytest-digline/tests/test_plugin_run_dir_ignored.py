"""`--digline-run` says what `digline run` says about a run directory git would
commit. (#523)

The plugin writes the run itself, through the store, and never passes through
the command line: without this, a suite run only from pytest would commit its
run files, written unredacted, with nothing in the session saying so.
"""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git is needed")

ANSWERS = {"alpha": "Acme SATISFIED", "beta": "Acme SATISFIED"}


def repository(path: Path) -> None:
    subprocess.run(["git", "-C", str(path), "init", "-q"], check=True)


def test_the_session_says_it_on_stderr(
    pytester: pytest.Pytester, repo: Callable[[dict[str, str]], Path]
) -> None:
    path = repo(ANSWERS)
    repository(pytester.path)
    (pytester.path / ".digline").mkdir()
    (pytester.path / ".digline" / ".gitignore").write_text(
        "my-own-entry\n", encoding="utf-8"
    )

    result = pytester.runpytest_subprocess(
        "--digline-suite", str(path), "--digline-run"
    )

    result.stderr.fnmatch_lines(
        [
            "digline: git does not ignore .digline/acme/runs/*",
            "digline: git does not ignore .digline/acme/name-table/*",
        ],
        consecutive=True,
    )


def test_the_first_run_of_a_fresh_repository_says_nothing(
    pytester: pytest.Pytester, repo: Callable[[dict[str, str]], Path]
) -> None:
    """The control: the run writes the generated rules, and is asked after."""
    path = repo(ANSWERS)
    repository(pytester.path)

    result = pytester.runpytest_subprocess(
        "--digline-suite", str(path), "--digline-run"
    )

    assert "git does not ignore" not in result.stderr.str()
