"""The run delete, against a store that really writes (ADR 0044).

Numbered by ADR 0044's test plan, which is the contract: a test here names the
item it holds. Items 11 to 14 belong to the command and to the walk, and live
beside them.

Every test reads the store back through its own readers — `read_run`,
`scan_runs`, `list_runs`, `pending` — because that is what §1's contract is
about: a removed run is absent from every reader, not merely from a directory.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Callable, Generator
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path

import pytest
from tests.test_store import run

from digline.core import RecordedOutcome, RegisterEntry, Run, key_of, run_to_json
from digline.core.run import SCHEMA_VERSION, DocumentRefusedError
from digline.store import (
    DirectoryUnreadableError,
    FileJournal,
    FileResultStore,
    JournalHeader,
    KeylessRunError,
    MisfiledRunError,
    PromotedRunError,
    Removal,
    RunNotFoundError,
    RunRef,
    refusal_for_a_promoted_run,
)

TENANT = "acme"
T1 = "2026-01-01T12:00:00.000001+00:00"
T2 = "2026-01-02T12:00:00.000001+00:00"
T3 = "2026-01-03T12:00:00.000001+00:00"
T4 = "2026-01-04T12:00:00.000001+00:00"
PROMOTED = "2026-02-01T09:00:00+00:00"


def a_run(at: str, suite: str = "s", *, rejudged_from: str | None = None) -> Run:
    return replace(
        run(suite=suite, tenant=TENANT), created_at=at, rejudged_from=rejudged_from
    )


def key(r: Run) -> str:
    return key_of(r.created_at, r.config_hash)


def ref(r: Run, suite: str | None = None) -> RunRef:
    return RunRef(tenant=TENANT, suite=suite or r.suite, key=key(r))


def file_of(store: FileResultStore, r: Run, suite: str | None = None) -> Path:
    return store.run_path(ref(r, suite))


def filed_by_hand(store: FileResultStore, r: Run, suite: str, name: str) -> Path:
    """`r` written where `write_run` would never put it: another suite's
    directory, or a name that is not its key."""
    path = store.runs_dir(TENANT) / suite / f"{name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(run_to_json(r), encoding="utf-8")
    return path


#: Journals kept open for the length of a test, as a live or killed process
#: leaves them: the leg is on disk from its first line.
_OPEN: list[FileJournal] = []


def legs(store: FileResultStore, r: Run, count: int) -> list[Path]:
    """`count` legs of `r`'s journal, each with its header written."""
    header = JournalHeader(
        tenant=r.tenant,
        environment=r.environment,
        suite=r.suite,
        config_hash=r.config_hash,
        cases_digest="d",
        created_at=r.created_at,
        started_at=r.created_at,
        digline_version="0",
        record_responses=False,
    )
    opened = [store.open_journal(header) for _ in range(count)]
    _OPEN.extend(opened)
    return [journal.path for journal in opened]


def promote(store: FileResultStore, r: Run, replacing: str | None = None) -> None:
    store.promote_baseline(
        ref(r), r.config_hash, expected_baseline=replacing, promoted_at=PROMOTED
    )


def tree(store: FileResultStore) -> dict[str, bytes]:
    """Every file under `.digline/`, by relative path, with its bytes."""
    return {
        str(path.relative_to(store.root)): path.read_bytes()
        for path in sorted(store.root.rglob("*"))
        if path.is_file()
    }


def assert_absent(store: FileResultStore, *keys: str) -> None:
    """§1's contract: none of `keys` is returned by any reader, in any suite
    of the tenant."""
    for directory in sorted(store.runs_dir(TENANT).iterdir()):
        suite = directory.name
        listed = {r.key for r in store.scan_runs(TENANT, suite).runs}
        named = {r.key for r in store.list_runs(TENANT, suite)}
        waiting = {p.key for p in store.pending(TENANT, suite)}
        for k in keys:
            assert k not in listed, (suite, k)
            assert k not in named, (suite, k)
            assert k not in waiting, (suite, k)
            with pytest.raises(RunNotFoundError):
                store.read_run(RunRef(tenant=TENANT, suite=suite, key=k))


def entry(run_key: str, baseline_key: str) -> RegisterEntry:
    return RegisterEntry(
        recorded_at=T4,
        digline_version="0",
        disposition="accepted",
        run_key=run_key,
        run_created_at=T1,
        run_config_hash="hash-a",
        run_environment="test",
        run_digline_version="0",
        run_rejudged=False,
        baseline_key=baseline_key,
        baseline_config_hash="hash-a",
        baseline_promoted_at=PROMOTED,
        outcome=RecordedOutcome(
            regressed=0,
            improved=0,
            unchanged=1,
            new=0,
            missing=0,
            errored=0,
            unjudged=0,
            suspended=0,
            within_noise=0,
            on_the_line=0,
            worse=False,
            canary_moved=False,
            config_changed=False,
            artifacts_changed=False,
            target_config_changed=False,
            judge_config_changed=False,
            rejudged=False,
        ),
        exit_code=0,
    )


@contextmanager
def removals_recorded(monkeypatch: pytest.MonkeyPatch) -> Generator[list[str]]:
    """Every `Path.unlink` in the block, in order, by file name."""
    seen: list[str] = []
    unlink = Path.unlink

    def recording(self: Path, missing_ok: bool = False) -> None:
        seen.append(self.name)
        unlink(self, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", recording)
    yield seen


# --------------------------------------------------------------------------- #
# 1. The refusal before the first step
# --------------------------------------------------------------------------- #


def test_1_a_promoted_run_is_refused_and_nothing_is_removed(tmp_path: Path) -> None:
    """A promoted run with legs and a replay. Either removed before the
    refusal would be something removed and then refused. (ADR 0044 §3)"""
    store = FileResultStore(tmp_path)
    k = a_run(T1)
    store.write_run(k)
    promote(store, k)
    legs(store, k, 1)
    store.write_run(a_run(T2, rejudged_from=key(k)))
    before = tree(store)

    with pytest.raises(PromotedRunError) as refused:
        store.delete_run(ref(k))

    assert tree(store) == before
    said = str(refused.value)
    assert key(k) in said
    assert "current baseline" in said
    assert f"promoted at {PROMOTED}" in said
    assert "promote another run first" in said
    assert f"--replacing {key(k)}" in said


# --------------------------------------------------------------------------- #
# 2. The orphaned baseline
# --------------------------------------------------------------------------- #


def test_2_a_baseline_over_a_run_that_is_gone_refuses_the_same_way(
    tmp_path: Path,
) -> None:
    """A refusal about the key, not about the run (ADR 0044 §3.2)."""
    store = FileResultStore(tmp_path)
    k = a_run(T1)
    store.write_run(k)
    promote(store, k)
    file_of(store, k).unlink()
    baseline = store.read_baseline(TENANT, "s")
    owed = refusal_for_a_promoted_run(ref(k), baseline)
    assert owed is not None
    before = tree(store)

    with pytest.raises(PromotedRunError) as refused:
        store.delete_run(ref(k))

    assert str(refused.value) == str(owed)
    assert tree(store) == before


# --------------------------------------------------------------------------- #
# 3. A replaced baseline
# --------------------------------------------------------------------------- #


def test_3_after_another_promotion_the_run_goes_and_the_register_stays(
    tmp_path: Path,
) -> None:
    store = FileResultStore(tmp_path)
    k, other = a_run(T1), a_run(T2)
    store.write_run(k)
    store.write_run(other)
    promote(store, k)
    store.append_register(TENANT, "s", entry(key(k), key(k)))
    promote(store, other, replacing=key(k))
    store.append_register(TENANT, "s", entry(key(other), key(k)))
    register = store.register_path(TENANT, "s").read_bytes()

    removal = store.delete_run(ref(k))

    assert removal.run.document
    assert_absent(store, key(k))
    assert store.register_path(TENANT, "s").read_bytes() == register
    assert store.read_run(ref(other)) == other


# --------------------------------------------------------------------------- #
# 4. The legs-only run
# --------------------------------------------------------------------------- #


def test_4_a_run_made_only_of_legs_is_removed_and_its_birth_read(
    tmp_path: Path,
) -> None:
    store = FileResultStore(tmp_path)
    k = a_run(T1)
    paths = legs(store, k, 2)
    assert [p.key for p in store.pending(TENANT, "s")] == [key(k)]

    removal = store.delete_run(ref(k))

    assert not any(path.exists() for path in paths)
    assert removal.run.legs == 2
    assert removal.run.document is False
    assert removal.run.created_at == T1
    assert not removal.nothing
    assert_absent(store, key(k))


# --------------------------------------------------------------------------- #
# 5. The chain across the tenant
# --------------------------------------------------------------------------- #


def test_5_the_chain_is_followed_across_suites_leaves_first(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """K in `s`, R1 of K in `t`, R2 of R1 in `s`. The library's `rejudge`
    files a replay under another suite of the tenant, so the walk crosses
    suites, and a repeat finds R2 only while R1 is there. (ADR 0044 §4)"""
    store = FileResultStore(tmp_path)
    k = a_run(T1)
    r1 = a_run(T2, "t", rejudged_from=key(k))
    r2 = a_run(T3, rejudged_from=key(r1))
    for each in (k, r1, r2):
        store.write_run(each)

    with removals_recorded(monkeypatch) as seen:
        removal = store.delete_run(ref(k))

    assert seen == [f"{key(r2)}.json", f"{key(r1)}.json", f"{key(k)}.json"]
    assert [r.ref for r in removal.replays] == [ref(r2), ref(r1)]
    assert all(r.found_in is None for r in removal.replays)
    assert [r.created_at for r in removal.replays] == [T3, T2]
    assert removal.unread == 0
    assert_absent(store, key(k), key(r1), key(r2))


def test_5_a_replay_s_legs_go_before_its_document(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = FileResultStore(tmp_path)
    k = a_run(T1)
    r1 = a_run(T2, rejudged_from=key(k))
    store.write_run(k)
    store.write_run(r1)
    leg = legs(store, r1, 1)[0]
    mine = legs(store, k, 1)[0]

    with removals_recorded(monkeypatch) as seen:
        removal = store.delete_run(ref(k))

    assert seen == [leg.name, f"{key(r1)}.json", mine.name, f"{key(k)}.json"]
    assert removal.replays[0].legs == 1
    assert not (store.journal_dir(TENANT, "s")).exists()


# --------------------------------------------------------------------------- #
# 6. Repeatability: every row of §4's table, left by hand
# --------------------------------------------------------------------------- #


def _chain(store: FileResultStore) -> tuple[Run, Run, Run]:
    k = a_run(T1)
    r1 = a_run(T2, "t", rejudged_from=key(k))
    r2 = a_run(T3, rejudged_from=key(r1))
    for each in (k, r1, r2):
        store.write_run(each)
    return k, r1, r2


def _in_the_plan(store: FileResultStore) -> list[str]:
    k, r1, r2 = _chain(store)
    legs(store, k, 2)
    return [key(k), key(r1), key(r2)]


def _between_two_replays(store: FileResultStore) -> list[str]:
    k, r1, r2 = _chain(store)
    file_of(store, r2).unlink()
    return [key(k), key(r1), key(r2)]


def _among_the_legs_with_the_document(store: FileResultStore) -> list[str]:
    k = a_run(T1)
    store.write_run(k)
    legs(store, k, 2)[0].unlink()
    assert [p.finished for p in store.pending(TENANT, "s")] == [True]
    return [key(k)]


def _among_the_legs_without_a_document(store: FileResultStore) -> list[str]:
    k = a_run(T1)
    legs(store, k, 3)[0].unlink()
    assert [p.finished for p in store.pending(TENANT, "s")] == [False]
    return [key(k)]


def _between_the_legs_and_the_document(store: FileResultStore) -> list[str]:
    k = a_run(T1)
    store.write_run(k)
    return [key(k)]


def _after_the_document(store: FileResultStore) -> list[str]:
    store.ensure_layout(TENANT)
    (store.runs_dir(TENANT) / "s").mkdir()
    return [key(a_run(T1))]


@pytest.mark.parametrize(
    "interrupted",
    [
        _in_the_plan,
        _between_two_replays,
        _among_the_legs_with_the_document,
        _among_the_legs_without_a_document,
        _between_the_legs_and_the_document,
        _after_the_document,
    ],
    ids=lambda f: f.__name__.lstrip("_"),
)
def test_6_every_interrupted_state_is_finished_by_the_same_call(
    tmp_path: Path, interrupted: Callable[[FileResultStore], list[str]]
) -> None:
    store = FileResultStore(tmp_path)
    keys = interrupted(store)

    first = store.delete_run(RunRef(tenant=TENANT, suite="s", key=keys[0]))
    assert_absent(store, *keys)

    again = store.delete_run(RunRef(tenant=TENANT, suite="s", key=keys[0]))
    assert again.nothing
    assert_absent(store, *keys)
    if interrupted is _after_the_document:
        assert first.nothing


# --------------------------------------------------------------------------- #
# 7. A file under K that cannot be shown to be K
# --------------------------------------------------------------------------- #


def test_7_a_file_under_k_that_is_not_json_is_refused_and_stays(
    tmp_path: Path,
) -> None:
    store = FileResultStore(tmp_path)
    k = a_run(T1)
    store.write_run(k)
    file_of(store, k).write_text("{ not json", encoding="utf-8")
    before = tree(store)

    with pytest.raises(DocumentRefusedError) as refused:
        store.delete_run(ref(k))

    assert not isinstance(refused.value, KeylessRunError | MisfiledRunError)
    assert "nothing was removed" in str(refused.value)
    assert tree(store) == before


def test_7_a_misfiled_file_under_k_is_refused_and_stays(tmp_path: Path) -> None:
    store = FileResultStore(tmp_path)
    other = a_run(T2)
    filed_by_hand(store, other, "s", key(a_run(T1)))
    before = tree(store)

    with pytest.raises(MisfiledRunError):
        store.delete_run(ref(a_run(T1)))

    assert tree(store) == before


# --------------------------------------------------------------------------- #
# 8. A misfiled replay of K
# --------------------------------------------------------------------------- #


def test_8_a_misfiled_replay_is_removed_and_named_by_its_own_key(
    tmp_path: Path,
) -> None:
    store = FileResultStore(tmp_path)
    k = a_run(T1)
    store.write_run(k)
    r1 = a_run(T2, rejudged_from=key(k))
    path = filed_by_hand(store, r1, "s", "renamed-by-hand")
    r2 = a_run(T3, "t", rejudged_from=key(r1))
    store.write_run(r2)

    removal = store.delete_run(ref(k))

    assert not path.exists()
    assert [r.ref for r in removal.replays] == [ref(r2), ref(r1)]
    assert removal.replays[1].found_in == RunRef(
        tenant=TENANT, suite="s", key="renamed-by-hand"
    )
    assert removal.replays[0].found_in is None
    assert_absent(store, key(k), key(r1), key(r2))


def _two_under_one_key(store: FileResultStore, *, both: bool) -> tuple[Run, Path, Path]:
    """A replay filed properly as Y, and a second document holding the same
    key Y under another name. With `both`, the two are on K's chain; without,
    only the misfiled one is, and the proper Y is a run of its own."""
    k = a_run(T1)
    store.write_run(k)
    proper = a_run(T2, rejudged_from=key(k) if both else None)
    store.write_run(proper)
    misfiled = filed_by_hand(
        store, replace(proper, rejudged_from=key(k)), "s", "copied-by-hand"
    )
    return k, file_of(store, proper), misfiled


def test_8_two_documents_under_one_key_on_the_chain_both_go(tmp_path: Path) -> None:
    store = FileResultStore(tmp_path)
    k, proper, misfiled = _two_under_one_key(store, both=True)
    y = proper.stem

    removal = store.delete_run(ref(k))

    assert not proper.exists() and not misfiled.exists()
    assert [r.ref.key for r in removal.replays] == [y, y]
    assert sorted(str(r.found_in) for r in removal.replays) == sorted(
        [str(None), str(RunRef(tenant=TENANT, suite="s", key="copied-by-hand"))]
    )


def test_8_only_the_misfiled_one_on_the_chain_leaves_the_other(
    tmp_path: Path,
) -> None:
    """`Removal.replays` names a key `read_run` still answers to, and
    `found_in` is what lets the command say so beside it. (ADR 0044 §5)"""
    store = FileResultStore(tmp_path)
    k, proper, misfiled = _two_under_one_key(store, both=False)
    y = proper.stem
    survivor = proper.read_bytes()

    removal = store.delete_run(ref(k))

    assert not misfiled.exists()
    assert proper.read_bytes() == survivor
    [only] = removal.replays
    assert only.ref.key == y
    assert only.found_in == RunRef(tenant=TENANT, suite="s", key="copied-by-hand")
    assert store.read_run(RunRef(tenant=TENANT, suite="s", key=y)).rejudged_from is None


# --------------------------------------------------------------------------- #
# 9. An older schema under K
# --------------------------------------------------------------------------- #


def _at_an_older_schema(path: Path) -> None:
    document = json.loads(path.read_text(encoding="utf-8"))
    document["schema_version"] = SCHEMA_VERSION - 1
    path.write_text(json.dumps(document), encoding="utf-8")


def test_9_an_older_schema_under_k_is_removed_with_its_birth_read(
    tmp_path: Path,
) -> None:
    store = FileResultStore(tmp_path)
    k = a_run(T1)
    store.write_run(k)
    _at_an_older_schema(file_of(store, k))
    with pytest.raises(DocumentRefusedError):
        store.read_run(ref(k))

    removal = store.delete_run(ref(k))

    assert removal.run.document
    assert removal.run.created_at == T1
    assert not file_of(store, k).exists()


def test_9_a_replay_at_an_older_schema_is_reached(tmp_path: Path) -> None:
    """The raw reading of §3.4, for a replay: the scan would skip it, the
    delete does not."""
    store = FileResultStore(tmp_path)
    k = a_run(T1)
    r1 = a_run(T2, "t", rejudged_from=key(k))
    store.write_run(k)
    store.write_run(r1)
    _at_an_older_schema(file_of(store, r1))

    removal = store.delete_run(ref(k))

    assert [r.ref for r in removal.replays] == [ref(r1)]
    assert not file_of(store, r1).exists()


# --------------------------------------------------------------------------- #
# 10. What the scan cannot read
# --------------------------------------------------------------------------- #


@contextmanager
def unreadable(directory: Path) -> Generator[None]:
    directory.chmod(0o000)
    try:
        yield
    finally:
        directory.chmod(0o755)


@pytest.mark.skipif(
    sys.platform == "win32" or os.geteuid() == 0,
    reason="mode 000 denies nothing to root, and Windows has no such mode",
)
def test_10_an_unreadable_directory_refuses_before_any_removal(
    tmp_path: Path,
) -> None:
    store = FileResultStore(tmp_path)
    k = a_run(T1)
    store.write_run(k)
    legs(store, k, 1)
    store.write_run(a_run(T2, "t"))
    before = tree(store)

    with (
        unreadable(store.runs_dir(TENANT) / "t"),
        pytest.raises(DirectoryUnreadableError),
    ):
        store.delete_run(ref(k))

    assert tree(store) == before


def test_10_an_unreadable_document_is_skipped_and_counted(tmp_path: Path) -> None:
    store = FileResultStore(tmp_path)
    k = a_run(T1)
    store.write_run(k)
    junk = store.runs_dir(TENANT) / "t" / "junk.json"
    junk.parent.mkdir()
    junk.write_text("[1, 2", encoding="utf-8")
    listed = store.runs_dir(TENANT) / "t" / "a-list.json"
    listed.write_text("[1, 2]", encoding="utf-8")

    removal = store.delete_run(ref(k))

    assert removal.unread == 2
    assert junk.exists() and listed.exists()
    assert_absent(store, key(k))


def test_10_a_link_out_of_the_store_is_counted_and_never_opened(
    tmp_path: Path,
) -> None:
    store = FileResultStore(tmp_path / "repo")
    k = a_run(T1)
    store.write_run(k)
    outside = tmp_path / "outside.json"
    outside.write_text(run_to_json(a_run(T2, rejudged_from=key(k))), encoding="utf-8")
    (store.runs_dir(TENANT) / "s" / "planted.json").symlink_to(outside)

    removal = store.delete_run(ref(k))

    assert removal.unread == 1
    assert removal.replays == ()
    assert outside.exists()


# --------------------------------------------------------------------------- #
# 15. A replay that declares another tenant or another suite
# --------------------------------------------------------------------------- #


def test_15_a_replay_declaring_another_address_is_removed_and_says_where(
    tmp_path: Path,
) -> None:
    """The declaration is a defect and not an address: the document was read,
    its `rejudged_from` says what it is. (ADR 0044 §3.4, ruled 2026-10-07)"""
    store = FileResultStore(tmp_path)
    k = a_run(T1)
    store.write_run(k)
    elsewhere = replace(
        run(suite="s", tenant="other"), created_at=T2, rejudged_from=key(k)
    )
    tenant_path = filed_by_hand(store, elsewhere, "s", key(elsewhere))
    misplaced = a_run(T3, "other-suite", rejudged_from=key(k))
    suite_path = filed_by_hand(store, misplaced, "t", key(misplaced))

    removal: Removal = store.delete_run(ref(k))

    assert not tenant_path.exists() and not suite_path.exists()
    by_key = {r.ref.key: r for r in removal.replays}
    assert by_key[key(elsewhere)].ref == RunRef(
        tenant="other", suite="s", key=key(elsewhere)
    )
    assert by_key[key(elsewhere)].found_in == RunRef(
        tenant=TENANT, suite="s", key=key(elsewhere)
    )
    assert by_key[key(misplaced)].ref == RunRef(
        tenant=TENANT, suite="other-suite", key=key(misplaced)
    )
    assert by_key[key(misplaced)].found_in == RunRef(
        tenant=TENANT, suite="t", key=key(misplaced)
    )
    assert_absent(store, key(k), key(elsewhere), key(misplaced))


# --------------------------------------------------------------------------- #
# 16. A document on the chain with no key of its own
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("missing", ["created_at", "config_hash"])
def test_16_a_keyless_document_on_the_chain_refuses_and_nothing_goes(
    tmp_path: Path, missing: str
) -> None:
    store = FileResultStore(tmp_path)
    k = a_run(T1)
    store.write_run(k)
    legs(store, k, 1)
    r1 = a_run(T2, "t", rejudged_from=key(k))
    store.write_run(r1)
    document = json.loads(run_to_json(a_run(T3, rejudged_from=key(r1))))
    del document[missing]
    keyless = store.runs_dir(TENANT) / "s" / "keyless.json"
    keyless.write_text(json.dumps(document), encoding="utf-8")
    before = tree(store)

    with pytest.raises(KeylessRunError) as refused:
        store.delete_run(ref(k))

    said = str(refused.value)
    assert str(keyless) in said
    assert f"it lacks {missing}" in said
    assert "nothing was removed" in said
    assert tree(store) == before


def test_16_a_keyless_file_under_k_is_refused_with_the_same_type(
    tmp_path: Path,
) -> None:
    """§3.3's case, the key asked for: the same reason, so the same type."""
    store = FileResultStore(tmp_path)
    k = a_run(T1)
    store.write_run(k)
    path = file_of(store, k)
    document = json.loads(path.read_text(encoding="utf-8"))
    document["config_hash"] = ""
    path.write_text(json.dumps(document), encoding="utf-8")
    before = tree(store)

    with pytest.raises(KeylessRunError, match="its config_hash is empty"):
        store.delete_run(ref(k))

    assert tree(store) == before


# --------------------------------------------------------------------------- #
# Beyond the plan: two suites that share a key (ADR 0044 §5)
# --------------------------------------------------------------------------- #


def test_a_shared_key_reaches_the_other_suites_replays_and_not_its_run(
    tmp_path: Path,
) -> None:
    """Same configuration and same `created_at` in two suites give one key.
    The cascade matches `rejudged_from` by key, so it reaches the other
    suite's replays too; the other suite's run itself is not asked for, and
    stays. A limit §5 states, measured here rather than left read."""
    store = FileResultStore(tmp_path)
    k = a_run(T1)
    twin = a_run(T1, "t")
    assert key(k) == key(twin)
    store.write_run(k)
    store.write_run(twin)
    of_twin = a_run(T2, "t", rejudged_from=key(twin))
    store.write_run(of_twin)

    removal = store.delete_run(ref(k))

    assert [r.ref for r in removal.replays] == [ref(of_twin)]
    assert store.read_run(ref(twin)) == twin
