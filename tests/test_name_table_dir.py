"""The name table's reserved directory: `.digline/<tenant>/name-table/`.

ADR 0036 §2 puts the table in the tenant's directory under a reserved name that
digline keeps and never writes. These tests hold the three things that
reservation means in code: the documented way in (`name_table_dir`), that
nothing digline writes or reads lands under it, and that the generated
`.gitignore` keeps it out of git — the table is the re-identification key and is
never committed (§1). Nothing refuses at run time: no path digline builds can
reach the directory, and these tests are what keep that true.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from digline.core import CaseResult, Run, Score, Verdict
from digline.store import (
    NAME_TABLE_DIRNAME,
    FileResultStore,
    PathRefusedError,
    RunRef,
)

#: What a SQLite table leaves beside it, at one time or another: the database,
#: the rollback journal, and the WAL pair. Named here because the reservation
#: exists to cover every one of them (#234).
SQLITE_FILES = (
    "table.sqlite",
    "table.sqlite-journal",
    "table.sqlite-wal",
    "table.sqlite-shm",
)

#: Names a glob in the store would pick up if it ever looked in here.
LOOKALIKES = ("2026-01-01.json", "test-suite.json", "test-suite.jsonl")


def a_run(suite: str = "test-suite") -> Run:
    return Run(
        tenant="acme",
        environment="test",
        suite=suite,
        config_hash="hash-a",
        created_at="2026-01-01T12:30:45+00:00",
        git_commit="0f1e2d3",
        results=(
            CaseResult(
                "case-1",
                (
                    Verdict(
                        score=Score(name="contains", score=1.0),
                        threshold=1.0,
                        tolerance=0.0,
                        status="pass",
                        reason="found",
                        assertion_id="contains",
                    ),
                ),
            ),
        ),
    )


def plant(directory: Path) -> dict[Path, bytes]:
    directory.mkdir(parents=True)
    planted: dict[Path, bytes] = {}
    for name in SQLITE_FILES + LOOKALIKES:
        path = directory / name
        path.write_bytes(b"owned by the process that owns the table: " + name.encode())
        planted[path] = path.read_bytes()
    return planted


def test_it_is_the_reserved_directory_in_the_tenants_directory(tmp_path: Path) -> None:
    store = FileResultStore(tmp_path)
    assert (
        store.name_table_dir("acme")
        == tmp_path.resolve() / ".digline" / "acme" / "name-table"
    )
    assert NAME_TABLE_DIRNAME == "name-table"


def test_asking_for_it_creates_nothing(tmp_path: Path) -> None:
    FileResultStore(tmp_path).name_table_dir("acme")
    assert not (tmp_path / ".digline").exists()


@pytest.mark.parametrize("tenant", ["..", "../other", "a/b", "", ".hidden"])
def test_a_tenant_that_could_climb_out_is_refused(tmp_path: Path, tenant: str) -> None:
    with pytest.raises(PathRefusedError):
        FileResultStore(tmp_path).name_table_dir(tenant)


@pytest.mark.parametrize("suite", ["test-suite", NAME_TABLE_DIRNAME])
def test_no_path_digline_builds_lands_under_it(tmp_path: Path, suite: str) -> None:
    # A suite named like the reserved directory is the case that would collide
    # if any path put a suite at the tenant's level. None does.
    store = FileResultStore(tmp_path)
    reserved = store.name_table_dir("acme")
    built = (
        store.tenant_dir("acme"),
        store.baselines_dir("acme"),
        store.runs_dir("acme"),
        store.baseline_path("acme", suite),
        store.run_path(RunRef(tenant="acme", suite=suite, key="k")),
        store.register_path("acme", suite),
        store.journal_dir("acme", suite),
    )
    for path in built:
        assert not path.is_relative_to(reserved), path


def test_a_whole_cycle_neither_touches_nor_reads_what_is_there(tmp_path: Path) -> None:
    store = FileResultStore(tmp_path)
    planted = plant(store.name_table_dir("acme"))

    ref = store.write_run(a_run())
    store.promote_baseline(
        ref,
        "hash-a",
        expected_baseline=None,
        promoted_at="2026-01-02T09:00:00+00:00",
        declared=None,
    )

    assert store.list_runs("acme", "test-suite") == (ref,)
    assert store.stored_paths("acme", "test-suite") == (
        store.run_path(ref),
        store.baseline_path("acme", "test-suite"),
    )
    assert store.pending("acme", "test-suite") == ()
    assert store.read_register("acme", "test-suite").entries == ()
    for path, content in planted.items():
        assert path.read_bytes() == content
    assert sorted(p.name for p in store.name_table_dir("acme").iterdir()) == sorted(
        SQLITE_FILES + LOOKALIKES
    )


@pytest.mark.skipif(shutil.which("git") is None, reason="needs git")
def test_the_generated_gitignore_keeps_the_table_and_its_companions_out_of_git(
    tmp_path: Path,
) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    store = FileResultStore(tmp_path)
    store.ensure_layout("acme")
    planted = plant(store.name_table_dir("acme"))
    for path in planted:
        checked = subprocess.run(
            ["git", "-C", str(tmp_path), "check-ignore", "-q", str(path)],
            check=False,
        )
        assert checked.returncode == 0, f"{path.name} is not ignored"
