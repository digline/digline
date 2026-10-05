"""A file whose name is not its run's key (ADR 0040, #332, #429).

The store answers to one key per run, `key_of(created_at, config_hash)`. The
scan leaves out a file named otherwise, before it looks at the schema, and says
what is wrong with it. The read refuses the same file when it is addressed by
its name. Written from the mistakes each test prevents:

- one badly named file stopping `--run latest` for the whole suite (#429);
- a note that says a left-out run was *newer*, on a `created_at` nobody
  validated (§5.2);
- *rename it* said where the name is taken, or where two files hold one run
  (§5.3, ruled 2026-10-05);
- a name proposed where the key is not a safe name (§5.4);
- an old-schema file with the wrong name counted under its schema (§5.1);
- a document with no key to compute pulled into a check that has nothing to
  check it with (left as it was, by ruling).
"""

from __future__ import annotations

import json
import shutil
from dataclasses import replace
from pathlib import Path

import pytest
from tests._helpers import cli
from tests.test_refused_runs import promoted
from tests.test_store import run

from digline.core import Contains, Run, key_of, run_to_json
from digline.core.run import SCHEMA_VERSION, DocumentRefusedError
from digline.host import REFUSALS, resolve_key
from digline.run import Case, Suite
from digline.store import (
    FileResultStore,
    MisfiledRunError,
    PathRefusedError,
    RunRef,
)
from digline.wire import EXIT_OK, runs_json

SUITE = Suite(
    tenant="acme",
    environment="test",
    name="test-suite",
    assertions=[Contains(needle="x")],
    cases=[Case(id="case-1")],
)
T1 = "2026-01-01T12:00:00.000001+00:00"
T2 = "2026-01-02T12:00:00.000001+00:00"


def key(r: Run) -> str:
    return key_of(r.created_at, r.config_hash)


def two_runs(root: Path) -> tuple[FileResultStore, Run, Run]:
    store = FileResultStore(root)
    older, newer = replace(run(), created_at=T1), replace(run(), created_at=T2)
    store.write_run(older)
    store.write_run(newer)
    return store, older, newer


def directory(store: FileResultStore) -> Path:
    return store.runs_dir(SUITE.tenant) / SUITE.name


def rename(store: FileResultStore, r: Run, name: str) -> None:
    (directory(store) / f"{key(r)}.json").rename(directory(store) / f"{name}.json")


def copy(store: FileResultStore, source: str, name: str) -> None:
    shutil.copyfile(
        directory(store) / f"{source}.json", directory(store) / f"{name}.json"
    )


# --------------------------------------------------------------------------- #
# A copy and a rename (§5.1, §5.2)
# --------------------------------------------------------------------------- #


def test_a_finder_copy_no_longer_stops_latest(tmp_path: Path) -> None:
    """#429: `<key> copy.json` failed `latest` for the whole suite with
    `PathRefusedError`. A copy holds the same run as the file it copies, so
    `latest` picks right and nothing is lost."""
    store, _older, newer = two_runs(tmp_path)
    copy(store, key(newer), f"{key(newer)} copy")

    resolved = resolve_key(store, SUITE, "latest")

    assert resolved.key == key(newer)
    assert f"already filed as {key(newer)}.json" in resolved.note
    assert "rename" not in resolved.note
    assert "newer" not in resolved.note


def test_a_rename_is_said_and_latest_never_calls_it_newer(tmp_path: Path) -> None:
    """The one case where `latest` falls back. It says the left-out key is not
    among the listed runs, and not that it was newer: that would rest on a
    `created_at` read from a document nobody validated."""
    store, older, newer = two_runs(tmp_path)
    rename(store, newer, "rossi-mario")

    resolved = resolve_key(store, SUITE, "latest")

    assert resolved.key == key(older)
    assert (
        f"'rossi-mario' holds a run not among the listed runs: rename it to "
        f"{key(newer)}.json"
    ) in resolved.note
    # The key once, in the name to give the file: a second copy of it is 49
    # characters to compare by eye and nothing to learn. (#440)
    assert resolved.note.count(key(newer)) == 1
    assert "newer" not in resolved.note


def test_renaming_it_back_puts_it_back(tmp_path: Path) -> None:
    """The refusal's instruction is true: following it restores the run."""
    store, _older, newer = two_runs(tmp_path)
    rename(store, newer, "rossi-mario")
    (directory(store) / "rossi-mario.json").rename(
        directory(store) / f"{key(newer)}.json"
    )

    resolved = resolve_key(store, SUITE, "latest")

    assert resolved.key == key(newer)
    assert resolved.note == ""


# --------------------------------------------------------------------------- #
# The name before the schema (§5.1)
# --------------------------------------------------------------------------- #


def at_schema(store: FileResultStore, name: str, r: Run, version: int) -> None:
    document = json.loads(run_to_json(r))
    document["schema_version"] = version
    (directory(store) / f"{name}.json").write_text(
        json.dumps(document), encoding="utf-8"
    )


def test_an_old_schema_file_with_the_wrong_name_is_left_out_for_its_name(
    tmp_path: Path,
) -> None:
    """Counted under its schema, `migrate` would rewrite it under that name."""
    store, _older, newer = two_runs(tmp_path)
    at_schema(
        store,
        "rossi-mario",
        replace(newer, created_at=T1.replace("01T", "03T")),
        SCHEMA_VERSION - 1,
    )

    listing = store.scan_runs(SUITE.tenant, SUITE.name)

    assert dict(listing.skipped) == {}
    assert [m.stem for m in listing.misfiled] == ["rossi-mario"]


def test_a_copy_of_an_old_schema_run_is_not_told_to_take_a_taken_name(
    tmp_path: Path,
) -> None:
    """The case §5.1 made: the copy is left out for its name while the
    original stays in `skipped`, so its key is not among the listed runs. Two
    facts, for two readers. *Taken* decides the instruction, so there is none.
    *Not listed* is what `latest` is told."""
    store = FileResultStore(tmp_path)
    store.write_run(replace(run(), created_at=T1))
    old = replace(run(), created_at=T2)
    at_schema(store, key(old), old, SCHEMA_VERSION - 1)
    copy(store, key(old), f"{key(old)} copy")

    listing = store.scan_runs(SUITE.tenant, SUITE.name)
    [misfiled] = listing.misfiled

    assert misfiled.taken
    assert dict(listing.skipped) == {SCHEMA_VERSION - 1: 1}
    [sentence] = listing.misfiled_sentences()
    assert sentence == (
        f"'{key(old)} copy' holds a run already filed as {key(old)}.json, "
        "which is not among the listed runs"
    )
    # Twice, and both are facts: the copy's own name, and the name the run is
    # already filed under. "holds run <key>" was a third, and said neither. (#440)
    assert sentence.count(key(old)) == 2


# --------------------------------------------------------------------------- #
# Two files and one run; a key that is not a safe name (§5.3, §5.4)
# --------------------------------------------------------------------------- #


def test_two_files_holding_one_run_are_told_nothing_to_do(tmp_path: Path) -> None:
    """Which of the two is the original is open (ADR 0040), so neither is told
    to take the name: the second rename would collide."""
    store, _older, newer = two_runs(tmp_path)
    rename(store, newer, "rossi-mario")
    copy(store, "rossi-mario", "rossi-mario copy")

    sentences = store.scan_runs(SUITE.tenant, SUITE.name).misfiled_sentences()

    assert len(sentences) == 2
    for sentence in sentences:
        assert (
            f"2 files hold the same run, and none is named {key(newer)}.json"
        ) in sentence
        assert sentence.count(key(newer)) == 1
        assert "rename" not in sentence


def test_a_key_that_is_not_a_safe_name_proposes_no_name(tmp_path: Path) -> None:
    """No document digline writes reaches it: a `config_hash` with a space."""
    store, _older, newer = two_runs(tmp_path)
    at_schema(store, "hand-made", replace(newer, config_hash="a b"), SCHEMA_VERSION)

    [sentence] = store.scan_runs(SUITE.tenant, SUITE.name).misfiled_sentences()

    assert sentence == (
        "'hand-made' is not named by its key, and its key is not a safe file name"
    )


def test_an_unsafe_key_equal_to_its_stem_is_the_residue(tmp_path: Path) -> None:
    """Pinned, not repaired: the name matches the key, so the check passes,
    and the name rule refuses it at the read. Only a hand-made document reaches
    it (ADR 0040 §5.4)."""
    store, _older, newer = two_runs(tmp_path)
    hand = replace(newer, config_hash="a b", created_at=T2.replace("02T", "05T"))
    at_schema(store, key(hand), hand, SCHEMA_VERSION)

    with pytest.raises(PathRefusedError):
        resolve_key(store, SUITE, "latest")


# --------------------------------------------------------------------------- #
# A document with no key to compute: left as it was (ruled 2026-10-05)
# --------------------------------------------------------------------------- #


def test_a_document_without_its_key_fields_is_not_checked_by_the_scan(
    tmp_path: Path,
) -> None:
    """It passes the scan at the current schema and is refused by the read,
    as before: the check has nothing to check it with."""
    store, _older, _newer = two_runs(tmp_path)
    (directory(store) / "rossi-mario.json").write_text(
        json.dumps({"schema_version": SCHEMA_VERSION}), encoding="utf-8"
    )

    listing = store.scan_runs(SUITE.tenant, SUITE.name)

    assert listing.misfiled == ()
    assert "rossi-mario" in [ref.key for ref in listing.runs]
    with pytest.raises(DocumentRefusedError) as refused:
        store.read_run(RunRef(SUITE.tenant, SUITE.name, "rossi-mario"))
    assert not isinstance(refused.value, MisfiledRunError)


# --------------------------------------------------------------------------- #
# The read
# --------------------------------------------------------------------------- #


def test_reading_a_run_by_a_name_that_is_not_its_key_is_refused(
    tmp_path: Path,
) -> None:
    """With the scan's own sentence, so the two say one thing."""
    store, _older, newer = two_runs(tmp_path)
    rename(store, newer, "rossi-mario")

    with pytest.raises(MisfiledRunError) as refused:
        store.read_run(RunRef(SUITE.tenant, SUITE.name, "rossi-mario"))

    assert f"rename it to {key(newer)}.json" in str(refused.value)


def test_the_refusal_is_a_refusal() -> None:
    """A front end exits 64 on it, as on every refused document."""
    assert issubclass(MisfiledRunError, DocumentRefusedError)
    assert any(issubclass(MisfiledRunError, kind) for kind in REFUSALS)


def test_a_store_holding_only_misfiled_runs_says_so_not_migrate(
    tmp_path: Path,
) -> None:
    store, older, newer = two_runs(tmp_path)
    rename(store, older, "one")
    rename(store, newer, "two")

    with pytest.raises(Exception, match="no runs stored under their key") as refused:
        resolve_key(store, SUITE, "latest")

    assert "migrate" not in str(refused.value)


# --------------------------------------------------------------------------- #
# The wire, and the CLI
# --------------------------------------------------------------------------- #


def test_list_runs_counts_the_misfiled(tmp_path: Path) -> None:
    store, older, newer = two_runs(tmp_path)
    rename(store, newer, "rossi-mario")
    listing = store.scan_runs(SUITE.tenant, SUITE.name)

    answered = runs_json(
        [(key(older), older)],
        tenant=SUITE.tenant,
        suite=SUITE.name,
        baseline_key=None,
        listing=listing,
    )

    assert answered["misfiled"] == 1


def test_compare_latest_beside_a_finder_copy_exits_ok(repo: Path) -> None:
    """#429's measurement, through the command line: it exited 64."""
    key_ = promoted(repo)
    runs = FileResultStore(repo).runs_dir("acme-bank") / "qa"
    shutil.copyfile(runs / f"{key_}.json", runs / f"{key_} copy.json")

    done = cli(repo, "compare", "--suite", "suite_qa.py", "--run", "latest")

    assert done.returncode == EXIT_OK, done.stderr
    assert f"already filed as {key_}.json" in done.stderr
