"""Fixtures shared across test modules.

`repo` is *defined* here rather than imported from `test_cli`: a fixture pulled
in by name is shadowed by the parameter that uses it, which reads to a type
checker as an unused import and to a reader as a mystery. pytest collects
fixtures from `conftest.py` without any import at all.

The plain helpers it is built from live in `tests/_helpers.py`, which is not a
test module — `conftest.py` is imported before pytest collects anything, so
reaching into a test module from here would make collection order load-bearing.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from tests._helpers import git, write_suite


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A git repository with the standard suite committed in it."""
    if shutil.which("git") is None:  # pragma: no cover - CI always has git
        pytest.skip("git is not installed")
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "user.email", "test@example.invalid")
    git(tmp_path, "config", "user.name", "Test")
    write_suite(tmp_path)
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-qm", "initial")
    return tmp_path
