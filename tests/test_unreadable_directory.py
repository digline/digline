"""A store directory that exists and cannot be opened is refused, not empty.

`Path.glob` catches the `OSError` that opening the directory raises and returns
no matches, on 3.12, 3.13 and 3.14 alike. Every lister in the store used it, so
a run directory at mode `000` read as a suite with no runs, and a journal
directory as nothing pending. A file read by name is checked with `exists()`,
which 3.14 answers `False` inside a directory nobody can search: a baseline
there read as no baseline. (#365)

Each test takes the permissions away and gives them back in a `finally`, or
pytest could not remove its own temporary directory afterwards.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

import pytest
from tests._helpers import cli, run_key, write_suite

from digline.core.run import SCHEMA_VERSION
from digline.store import (
    PENDING_DIRNAME,
    DirectoryUnreadableError,
    FileResultStore,
    RunRef,
)
from digline.wire import EXIT_USAGE

pytestmark = pytest.mark.skipif(
    sys.platform == "win32" or os.geteuid() == 0,
    reason="mode 000 denies nothing to root, and Windows has no such mode",
)


@contextmanager
def unreadable(directory: Path) -> Generator[None]:
    """`directory` at mode `000` for the length of the block, then `755`."""
    directory.chmod(0o000)
    try:
        yield
    finally:
        directory.chmod(0o755)


def a_suite_with_one_run(tmp_path: Path) -> tuple[FileResultStore, Path]:
    store = FileResultStore(tmp_path)
    directory = store.runs_dir("acme") / "qa"
    directory.mkdir(parents=True)
    (directory / "one.json").write_text(
        json.dumps({"schema_version": SCHEMA_VERSION}), encoding="utf-8"
    )
    return store, directory


# --------------------------------------------------------------------------- #
# The control: the same directory, readable, is not empty
# --------------------------------------------------------------------------- #


def test_the_directory_holds_a_run_when_it_can_be_read(tmp_path: Path) -> None:
    """Without this, an empty directory would pass every test below for the
    wrong reason: the refusal must stand where a run is."""
    store, _ = a_suite_with_one_run(tmp_path)

    assert store.scan_runs("acme", "qa").runs == (
        RunRef(tenant="acme", suite="qa", key="one"),
    )


def test_an_absent_directory_is_still_an_empty_suite(tmp_path: Path) -> None:
    """Nothing to open is not a failure to open: a suite never run has none."""
    store = FileResultStore(tmp_path)

    assert store.scan_runs("acme", "qa").runs == ()
    assert store.list_runs("acme", "qa") == ()
    assert store.run_paths("acme", "qa") == ()
    assert store.pending("acme", "qa") == ()


# --------------------------------------------------------------------------- #
# The runs directory
# --------------------------------------------------------------------------- #


def test_a_scan_refuses_rather_than_returning_no_runs(tmp_path: Path) -> None:
    store, directory = a_suite_with_one_run(tmp_path)

    with unreadable(directory), pytest.raises(DirectoryUnreadableError) as raised:
        store.scan_runs("acme", "qa")

    message = str(raised.value)
    assert str(directory) in message
    assert "Permission denied" in message
    assert "not an empty directory" in message


def test_list_runs_refuses_too(tmp_path: Path) -> None:
    store, directory = a_suite_with_one_run(tmp_path)

    with unreadable(directory), pytest.raises(DirectoryUnreadableError):
        store.list_runs("acme", "qa")


def test_migration_refuses_rather_than_finding_nothing(tmp_path: Path) -> None:
    """`migrate` lists through `stored_paths`, and reported nothing to do."""
    store, directory = a_suite_with_one_run(tmp_path)

    with unreadable(directory), pytest.raises(DirectoryUnreadableError):
        store.stored_paths("acme", "qa")


# --------------------------------------------------------------------------- #
# The journal directory
# --------------------------------------------------------------------------- #


def a_pending_directory(tmp_path: Path) -> tuple[FileResultStore, Path]:
    store = FileResultStore(tmp_path)
    directory = store.runs_dir("acme") / "qa" / PENDING_DIRNAME
    directory.mkdir(parents=True)
    (directory / "k.1.jsonl").write_text("", encoding="utf-8")
    return store, directory


def test_pending_refuses_rather_than_answering_nothing_is_pending(
    tmp_path: Path,
) -> None:
    store, directory = a_pending_directory(tmp_path)

    with unreadable(directory), pytest.raises(DirectoryUnreadableError) as raised:
        store.pending("acme", "qa")

    assert str(directory) in str(raised.value)


def test_dropping_a_journal_refuses_rather_than_doing_nothing(
    tmp_path: Path,
) -> None:
    """It listed the legs to delete through the same glob, deleted none, and
    returned as though it had."""
    store, directory = a_pending_directory(tmp_path)

    with unreadable(directory), pytest.raises(DirectoryUnreadableError):
        store.drop_pending("acme", "qa", "k")

    assert (directory / "k.1.jsonl").exists()


def test_a_journal_inside_an_unreadable_run_directory_is_not_none_pending(
    tmp_path: Path,
) -> None:
    """The journal directory sits inside the run directory. Its `is_dir()`
    answered `False` on 3.14 when the parent could not be searched, so
    `--resume` said `pending: none`. Measured on 3.14.5 before this fix."""
    store, directory = a_pending_directory(tmp_path)

    with unreadable(directory.parent), pytest.raises(DirectoryUnreadableError):
        store.pending("acme", "qa")


# --------------------------------------------------------------------------- #
# A file read by name inside a directory nobody can search
# --------------------------------------------------------------------------- #


def a_baseline_file(tmp_path: Path) -> tuple[FileResultStore, Path]:
    """Only its existence is in question here, so its content is not a run."""
    store = FileResultStore(tmp_path)
    store.ensure_layout("acme")
    store.baseline_path("acme", "qa").write_text("{}", encoding="utf-8")
    return store, store.baselines_dir("acme")


def test_a_baseline_that_cannot_be_looked_for_is_not_no_baseline(
    tmp_path: Path,
) -> None:
    """3.14 read the unsearchable directory as an absent baseline and returned
    `None`; 3.12 and 3.13 raised a bare `PermissionError`, a traceback at the
    command line."""
    store, directory = a_baseline_file(tmp_path)

    with unreadable(directory), pytest.raises(DirectoryUnreadableError) as raised:
        store.read_baseline("acme", "qa")

    assert str(store.baseline_path("acme", "qa")) in str(raised.value)
    assert "not a missing file" in str(raised.value)


def test_migration_does_not_drop_a_baseline_it_cannot_see(tmp_path: Path) -> None:
    store, directory = a_baseline_file(tmp_path)

    with unreadable(directory), pytest.raises(DirectoryUnreadableError):
        store.stored_paths("acme", "qa")


def test_a_register_that_cannot_be_looked_for_is_not_empty(tmp_path: Path) -> None:
    store = FileResultStore(tmp_path)
    path = store.register_path("acme", "qa")
    path.parent.mkdir(parents=True)
    path.write_text("", encoding="utf-8")

    with unreadable(path.parent), pytest.raises(DirectoryUnreadableError):
        store.read_register("acme", "qa")


def test_a_missing_baseline_and_register_are_still_none_and_empty(
    tmp_path: Path,
) -> None:
    store = FileResultStore(tmp_path)
    store.ensure_layout("acme")

    assert store.read_baseline("acme", "qa") is None
    assert store.read_register("acme", "qa").entries == ()


# --------------------------------------------------------------------------- #
# What a person sees
# --------------------------------------------------------------------------- #


def test_digline_list_names_the_directory_instead_of_listing_nothing(
    tmp_path: Path,
) -> None:
    write_suite(tmp_path)
    run_key(tmp_path)
    (directory,) = (tmp_path / ".digline").glob("*/runs/*")

    with unreadable(directory):
        done = cli(tmp_path, "list", "--suite", "suite_qa.py")

    assert done.returncode == EXIT_USAGE, done.stdout
    assert "DirectoryUnreadableError" in done.stderr
    assert str(directory) in done.stderr
