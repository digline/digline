"""`digline delete`, the front end of ADR 0044.

Items 11, 12 and 13 of the test plan, and the command's half of 8, 10 and 15:
the store's half is `tests/test_delete_run.py`. Run as a person runs it, in a
subprocess, so the exit code and the words are the ones a terminal gets.
"""

from __future__ import annotations

import json
from pathlib import Path

from tests._helpers import cli, run_key, write_suite

from digline.core import key_of
from digline.store import FileResultStore, RunRef
from digline.wire import EXIT_OK, EXIT_USAGE

TENANT = "acme-bank"
SUITE = "qa"


def a_repo(root: Path) -> tuple[FileResultStore, str]:
    write_suite(root)
    return FileResultStore(root), run_key(root)


def delete(root: Path, key: str) -> tuple[int, str, str]:
    done = cli(root, "delete", "--suite", "suite_qa.py", "--run", key)
    return done.returncode, done.stdout, done.stderr


def suite_dir(store: FileResultStore, suite: str = SUITE) -> Path:
    path = store.runs_dir(TENANT) / suite
    path.mkdir(parents=True, exist_ok=True)
    return path


def a_replay(
    store: FileResultStore, of: str, at: str, **changed: object
) -> dict[str, object]:
    """A replay of `of`, made from the stored run's own document: another
    `created_at`, `rejudged_from` set, and whatever `changed` says."""
    source = store.run_path(RunRef(tenant=TENANT, suite=SUITE, key=of))
    document = json.loads(source.read_text(encoding="utf-8"))
    document.update({"created_at": at, "rejudged_from": of, **changed})
    return document


def key(document: dict[str, object]) -> str:
    return key_of(str(document["created_at"]), str(document["config_hash"]))


def put(directory: Path, name: str, document: dict[str, object]) -> Path:
    path = directory / f"{name}.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


# --------------------------------------------------------------------------- #
# 11. Nothing to remove
# --------------------------------------------------------------------------- #


def test_11_nothing_to_remove_exits_0_and_never_says_removed(tmp_path: Path) -> None:
    write_suite(tmp_path)
    missing = "2026-01-01T00-00-00-00-00-0123456789abcdef"

    code, out, _ = delete(tmp_path, missing)

    assert code == EXIT_OK
    assert out == (
        f"nothing is filed under {missing} in suite {SUITE}, tenant {TENANT}: "
        "no document, no legs, no replay. Nothing was removed.\n"
    )


def test_11_a_repeated_delete_says_nothing_the_second_time(tmp_path: Path) -> None:
    store, k = a_repo(tmp_path)

    first = delete(tmp_path, k)
    second = delete(tmp_path, k)

    assert first[0] == EXIT_OK
    assert first[1].startswith(f"removed run {k} in suite {SUITE}, tenant {TENANT}")
    assert second[0] == EXIT_OK
    assert second[1].startswith(f"nothing is filed under {k}")
    assert not store.list_runs(TENANT, SUITE)


# --------------------------------------------------------------------------- #
# 12. --run latest
# --------------------------------------------------------------------------- #


def test_12_latest_is_refused_and_nothing_moves(tmp_path: Path) -> None:
    store, k = a_repo(tmp_path)

    code, out, err = delete(tmp_path, "latest")

    assert code == EXIT_USAGE
    assert out == ""
    assert "not 'latest'" in err
    assert [r.key for r in store.list_runs(TENANT, SUITE)] == [k]


# --------------------------------------------------------------------------- #
# 13. The name table
# --------------------------------------------------------------------------- #


def test_13_the_name_table_survives_a_delete_of_every_run(tmp_path: Path) -> None:
    """The listing walks `runs/`, and the name table is outside it, so it is
    never met (ADR 0044 §3)."""
    store, first = a_repo(tmp_path)
    second = run_key(tmp_path)
    table = store.name_table_dir(TENANT) / "table.sqlite"
    table.parent.mkdir()
    table.write_bytes(b"owned by another process")

    for k in (first, second):
        assert delete(tmp_path, k)[0] == EXIT_OK

    assert not store.list_runs(TENANT, SUITE)
    assert table.read_bytes() == b"owned by another process"


# --------------------------------------------------------------------------- #
# The refusal, through the command
# --------------------------------------------------------------------------- #


def test_the_run_under_the_baseline_is_refused_with_its_sentence(
    tmp_path: Path,
) -> None:
    store, k = a_repo(tmp_path)
    assert (
        cli(
            tmp_path,
            "promote",
            "--suite",
            "suite_qa.py",
            "--run",
            k,
            "--replacing",
            "none",
        ).returncode
        == EXIT_OK
    )

    code, out, err = delete(tmp_path, k)

    assert code == EXIT_USAGE
    assert out == ""
    assert "promote another run first" in err
    assert [r.key for r in store.list_runs(TENANT, SUITE)] == [k]


# --------------------------------------------------------------------------- #
# 8. A misfiled replay whose key another document still holds
# --------------------------------------------------------------------------- #


def test_8_the_command_says_the_key_still_names_a_document(tmp_path: Path) -> None:
    store, k = a_repo(tmp_path)
    proper = a_replay(store, k, "2026-01-02T00:00:00+00:00", rejudged_from=None)
    y = key(proper)
    put(suite_dir(store), y, proper)
    put(suite_dir(store), "copied-by-hand", {**proper, "rejudged_from": k})

    code, out, _ = delete(tmp_path, k)

    assert code == EXIT_OK
    assert f"removed replay {y} of suite {SUITE}, tenant {TENANT}" in out
    assert (
        f"it was filed as copied-by-hand.json in suite {SUITE}, tenant {TENANT}, "
        f"and its name is not its key {y}"
    ) in out
    assert (
        f"{y} still names a document in suite {SUITE}: only the copy filed as "
        f"copied-by-hand.json was removed, and that document and any journal "
        f"legs under {y}, which are its, were left."
    ) in out


# --------------------------------------------------------------------------- #
# 10. A document the scan cannot read
# --------------------------------------------------------------------------- #


def test_10_the_command_says_section_5s_sentence(tmp_path: Path) -> None:
    store, k = a_repo(tmp_path)
    (suite_dir(store, "other") / "junk.json").write_text("{", encoding="utf-8")

    code, out, _ = delete(tmp_path, k)

    assert code == EXIT_OK
    assert (
        f"1 documents in tenant {TENANT} could not be read. Whether any of them "
        f"was a replay of {k} is not known, and none of them was removed.\n"
    ) in out


# --------------------------------------------------------------------------- #
# 15. A replay that declares another address
# --------------------------------------------------------------------------- #


def test_15_the_command_names_the_file_and_what_it_declared(tmp_path: Path) -> None:
    store, k = a_repo(tmp_path)
    other_tenant = a_replay(store, k, "2026-01-02T00:00:00+00:00", tenant="elsewhere")
    other_suite = a_replay(store, k, "2026-01-03T00:00:00+00:00", suite="not-qa")
    put(suite_dir(store), key(other_tenant), other_tenant)
    put(suite_dir(store, "t"), key(other_suite), other_suite)

    code, out, _ = delete(tmp_path, k)

    assert code == EXIT_OK
    assert (
        f"removed replay {key(other_tenant)} of suite {SUITE}, tenant elsewhere"
    ) in out
    assert (
        f"it was filed as {key(other_tenant)}.json in suite {SUITE}, tenant "
        f"{TENANT}, and it declares tenant elsewhere: the store held a document "
        "filed otherwise than it says."
    ) in out
    assert (
        f"it was filed as {key(other_suite)}.json in suite t, tenant {TENANT}, "
        "and it declares suite not-qa: the store held a document filed otherwise "
        "than it says."
    ) in out


def test_15_a_declaration_that_is_missing_is_said_as_such(tmp_path: Path) -> None:
    store, k = a_repo(tmp_path)
    document = a_replay(store, k, "2026-01-02T00:00:00+00:00")
    del document["suite"]
    put(suite_dir(store), key(document), document)

    _, out, _ = delete(tmp_path, k)

    assert "it declares no tenant or no suite that is a string" in out


def test_a_control_character_in_a_declaration_reaches_no_terminal(
    tmp_path: Path,
) -> None:
    """A declared tenant is text a stranger wrote, and the sentence carries it:
    it goes through `visible()` like every sentence. (`cli/output.py`)"""
    store, k = a_repo(tmp_path)
    document = a_replay(store, k, "2026-01-02T00:00:00+00:00", tenant="x\x1b[2Ky")
    put(suite_dir(store), key(document), document)

    _, out, _ = delete(tmp_path, k)

    assert "\x1b" not in out
    assert "it declares tenant x" in out
