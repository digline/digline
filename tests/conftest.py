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
from tests._providers import REGISTERED


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


@pytest.fixture
def fake_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    """Register `tests._providers.REGISTERED` as the provider `fake`.

    A TOML suite names a judge by coordinate and the loader resolves it through
    an installed plugin, so anything testing the format needs one — and a test
    that reached for `anthropic` would need a key, a network and a bill to
    check a parser.

    The entry point points at `tests._providers` by import path, which is why
    the fakes live in a module and not in a test file: see that file's
    docstring.
    """
    from importlib.metadata import EntryPoint

    from digline.targets.registry import GROUP

    point = EntryPoint(
        name=REGISTERED.name, value="tests._providers:REGISTERED", group=GROUP
    )
    monkeypatch.setattr(
        "digline.targets.registry._entry_points", lambda: {REGISTERED.name: point}
    )
