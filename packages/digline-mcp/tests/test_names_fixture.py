"""The names gate's fixture copies what git tracks of the example, and nothing
git ignores beside it.

A checkout that has run the example holds runs and journals under
`.digline/*/runs/`, which git ignores. A copy of the whole directory carried
them into the fixture, and a measurement read them as the fixture's own: the
journal strings of the first name pass came from there, and were reported as
measured. So the fixture built beside such leftovers must be the fixture built
without them.
"""

from __future__ import annotations

import io
import subprocess
import tarfile
from pathlib import Path

from test_names_gate import EXAMPLE, ROOT, build_repository
from tests._helpers import git

_LEFTOVERS = (
    ".digline/bookshop/runs/replies/2026-01-01T00-00-00-000000-00-00-0000000000000000.json",
    ".digline/bookshop/runs/replies/.pending/2026-01-01T00-00-00-000000-00-00-0000000000000000.1.jsonl",
)


def _tracked_example(tmp: Path) -> Path:
    """The example as this commit tracks it, in a repository of its own."""
    archive = subprocess.run(
        ["git", "-C", str(ROOT), "archive", "HEAD", str(EXAMPLE.relative_to(ROOT))],
        check=True,
        capture_output=True,
    ).stdout
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        tar.extractall(tmp, filter="data")
    source = tmp / EXAMPLE.relative_to(ROOT)
    git(source, "init", "-q")
    git(source, "add", "-A")
    git(source, "-c", "user.email=t@e.i", "-c", "user.name=T", "commit", "-qm", "i")
    return source


def _outside_runs(repo: Path) -> set[str]:
    """Every file of the built fixture outside `.git` and outside the runs,
    whose names carry the instant each was made."""
    return {
        path.relative_to(repo).as_posix()
        for path in repo.rglob("*")
        if path.is_file()
        and path.relative_to(repo).parts[0] != ".git"
        and "runs" not in path.relative_to(repo).parts
    }


def _runs(repo: Path) -> list[str]:
    return sorted(
        path.relative_to(repo).as_posix()
        for path in (repo / ".digline").rglob("*")
        if path.is_file() and "runs" in path.relative_to(repo).parts
    )


def test_what_git_ignores_beside_the_example_is_not_copied(tmp_path: Path) -> None:
    source = _tracked_example(tmp_path / "source")
    clean, _, _ = build_repository(tmp_path / "clean", example=source)
    for leftover in _LEFTOVERS:
        path = source / leftover
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{"schema_version": 1}\n', encoding="utf-8")
        # The control: each leftover is one git ignores, as a run's are.
        # `check-ignore` exits 1 on a path it does not ignore, and `git` raises.
        git(source, "check-ignore", "-q", leftover)
    dirty, _, _ = build_repository(tmp_path / "dirty", example=source)

    assert len(_runs(clean)) == len(_runs(dirty)) == 2, (_runs(clean), _runs(dirty))
    for leftover in _LEFTOVERS:
        assert not (dirty / leftover).exists(), leftover
    assert _outside_runs(clean) == _outside_runs(dirty)
