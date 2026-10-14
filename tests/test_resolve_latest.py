"""`latest` when the newest run is gone (#286).

A scan sees what is there, not what was. So the note can name a missing run
only where a committed artifact remembers one newer than the pick — the
baseline, or a register line — and must stay empty otherwise. The first two
tests are the controls that were red before the note existed. The third keeps
the note from being said on every resolution, which would pass the first two
and tell nobody anything. The fourth pins the case no store can see, so that
widening the note is a decision somebody takes, not a drift.
"""

from __future__ import annotations

from dataclasses import fields, replace
from pathlib import Path

from tests.test_store import run

from digline.core import Contains, RegisterEntry, Run, key_of
from digline.core.register import RecordedOutcome
from digline.host import resolve_key
from digline.run import Case, Suite
from digline.store import FileResultStore, RunRef

SUITE = Suite(
    tenant="acme",
    environment="test",
    name="test-suite",
    assertions=[Contains(needle="x")],
    cases=[Case(id="case-1")],
)
T1 = "2026-01-01T12:00:00.000001+00:00"
T2 = "2026-01-02T12:00:00.000001+00:00"


def two_runs(root: Path) -> tuple[FileResultStore, Run, Run]:
    store = FileResultStore(root)
    older, newer = replace(run(), created_at=T1), replace(run(), created_at=T2)
    store.write_run(older)
    store.write_run(newer)
    return store, older, newer


def key(document: Run) -> str:
    return key_of(document.created_at, document.config_hash)


def remove(store: FileResultStore, document: Run) -> None:
    ref = RunRef(tenant="acme", suite="test-suite", key=key(document))
    store.run_path(ref).unlink()


def entry_naming(document: Run) -> RegisterEntry:
    counts = {
        f.name: (False if f.type == "bool" else 0) for f in fields(RecordedOutcome)
    }
    return RegisterEntry(
        recorded_at="2026-01-03T09:00:00+00:00",
        digline_version="test",
        disposition="accepted",
        run_key=key(document),
        run_created_at=document.created_at,
        run_config_hash=document.config_hash,
        run_environment=document.environment,
        run_digline_version="test",
        run_rejudged=False,
        baseline_key="none",
        baseline_config_hash="",
        baseline_promoted_at="",
        outcome=RecordedOutcome(**counts),  # pyright: ignore[reportArgumentType]
        exit_code=0,
    )


def test_the_baseline_names_a_newer_run_that_is_gone(tmp_path: Path) -> None:
    store, older, newer = two_runs(tmp_path)
    store.promote_baseline(
        RunRef(tenant="acme", suite="test-suite", key=key(newer)),
        newer.config_hash,
        expected_baseline=None,
        promoted_at="2026-01-03T09:00:00+00:00",
        declared=None,
    )
    remove(store, newer)

    resolved = resolve_key(store, SUITE, "latest")

    assert resolved.key == key(older)
    assert "baseline" in resolved.note
    assert key(newer) in resolved.note
    assert "not read here" in resolved.note


def test_the_register_names_a_newer_run_that_is_gone(tmp_path: Path) -> None:
    store, older, newer = two_runs(tmp_path)
    store.append_register("acme", "test-suite", entry_naming(newer))
    remove(store, newer)

    resolved = resolve_key(store, SUITE, "latest")

    assert resolved.key == key(older)
    assert "register" in resolved.note
    assert key(newer) in resolved.note


def test_the_note_is_empty_when_nothing_on_record_is_newer(tmp_path: Path) -> None:
    """Both artifacts present and both naming a run — the newest one, which is
    there. A note here would be a note on every resolution."""
    store, _older, newer = two_runs(tmp_path)
    store.promote_baseline(
        RunRef(tenant="acme", suite="test-suite", key=key(newer)),
        newer.config_hash,
        expected_baseline=None,
        promoted_at="2026-01-03T09:00:00+00:00",
        declared=None,
    )
    store.append_register("acme", "test-suite", entry_naming(newer))

    resolved = resolve_key(store, SUITE, "latest")

    assert resolved.key == key(newer)
    assert resolved.note == ""


def test_a_newer_run_nothing_recorded_is_not_seen(tmp_path: Path) -> None:
    """The limit, pinned. No baseline, no register: the store holds no trace
    that the newer run existed, so `latest` falls back to the older one and the
    note cannot say otherwise. `resolve_key`'s docstring says why."""
    store, older, newer = two_runs(tmp_path)
    remove(store, newer)

    resolved = resolve_key(store, SUITE, "latest")

    assert resolved.key == key(older)
    assert resolved.note == ""


def test_an_unreadable_baseline_is_named_and_latest_still_resolves(
    tmp_path: Path,
) -> None:
    store, _older, newer = two_runs(tmp_path)
    path = store.baseline_path("acme", "test-suite")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{ not json", encoding="utf-8")

    resolved = resolve_key(store, SUITE, "latest")

    assert resolved.key == key(newer)
    assert "the baseline could not be read" in resolved.note
