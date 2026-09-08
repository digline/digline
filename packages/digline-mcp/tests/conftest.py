"""A repository with runs in it, and a server pointed at it.

Built on `tests/_helpers.py` from the root suite rather than on a second copy of
the same fixture: the suite these tools read is the suite every other test reads,
so a change to it reaches here too.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from tests._helpers import cli, git, run_key, write_suite


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    if shutil.which("git") is None:  # pragma: no cover - CI always has git
        pytest.skip("git is not installed")
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "user.email", "test@example.invalid")
    git(tmp_path, "config", "user.name", "Test")
    write_suite(tmp_path)
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-qm", "initial")
    return tmp_path


@pytest.fixture
def promoted(repo: Path) -> Path:
    """A repository whose suite has a baseline, promoted through the CLI.

    Through the CLI deliberately: this package cannot promote, and a fixture
    that reached into the store to write a baseline would be quietly proving
    that it can.
    """
    cli(repo, "promote", "--suite", "suite_qa.py", "--run", run_key(repo))
    return repo
