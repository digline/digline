"""`migrate` replaces a document, it never overwrites it in place. (#668)

`migrate_file` wrote with `Path.write_text`, which opens in mode `w` and so
truncates the file before the first byte of the new content is written. A
write interrupted between the two — a full disk, a killed process — left a
run with neither its old content nor its new one, and a run has no other copy:
the generated `.gitignore` excludes `*/runs/`. `docs/migrate.md` promised a
temporary file and `os.replace` from the commit that added it.

The interruption is injected at the one place both writes go through: `io.open`,
which `Path.open` and `os.fdopen` both call. Every file opened for writing
receives half of what it is given and then fails as a full disk does, so the
test does not name the mechanism it expects to see.
"""

from __future__ import annotations

import errno
import io
import json
from pathlib import Path
from types import TracebackType
from typing import Any, Self

import pytest

from digline.core import CaseResult, Contains, Score, Verdict
from digline.core.run import SCHEMA_VERSION, Run
from digline.store import FileResultStore
from digline.store.migrate import migrate_file

_REAL_OPEN = io.open


class _HalfWritten:
    """A writable file that takes half of the first write and then fails."""

    def __init__(self, handle: Any) -> None:
        self._handle = handle

    def write(self, data: str) -> int:
        self._handle.write(data[: len(data) // 2])
        self._handle.flush()
        raise OSError(errno.ENOSPC, "No space left on device")

    def __getattr__(self, name: str) -> Any:
        return getattr(self._handle, name)

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._handle.close()


def _interrupted_open(file: Any, mode: str = "r", *args: Any, **kwargs: Any) -> Any:
    handle = _REAL_OPEN(file, mode, *args, **kwargs)
    if any(flag in mode for flag in "wax+"):
        return _HalfWritten(handle)
    return handle


def _old_run(tmp_path: Path) -> Path:
    """A stored run rewritten as schema 9, which `migrate` has to upgrade."""
    store = FileResultStore(tmp_path)
    ref = store.write_run(
        Run(
            tenant="acme",
            environment="staging",
            suite="qa",
            config_hash="0123456789abcdef",
            created_at="2026-01-01T00:00:00+00:00",
            results=(
                CaseResult(
                    "one",
                    (
                        Verdict(
                            score=Score(name="contains", score=0.9),
                            threshold=0.7,
                            status="pass",
                            reason="found it",
                            assertion_id=Contains(needle="Rome").identity,
                        ),
                    ),
                ),
            ),
        )
    )
    path = store.run_path(ref)
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["schema_version"] = 9
    raw.pop("digline_version", None)
    path.write_text(json.dumps(raw), encoding="utf-8")
    return path


def test_an_interrupted_migration_leaves_the_original_document_whole(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _old_run(tmp_path)
    before = path.read_bytes()
    siblings = sorted(p.name for p in path.parent.iterdir())

    monkeypatch.setattr(io, "open", _interrupted_open)
    with pytest.raises(OSError, match="No space left on device"):
        migrate_file(path)
    monkeypatch.undo()

    assert path.read_bytes() == before
    # Nothing left behind beside it either: a stray temporary file in `runs/`
    # is a file the next listing has to explain.
    assert sorted(p.name for p in path.parent.iterdir()) == siblings


def test_an_uninterrupted_migration_puts_the_new_document_in_its_place(
    tmp_path: Path,
) -> None:
    """The other half: a write that cannot be interrupted because it never
    lands would pass the test above."""
    path = _old_run(tmp_path)
    siblings = sorted(p.name for p in path.parent.iterdir())

    assert migrate_file(path) == 9

    migrated = json.loads(path.read_text(encoding="utf-8"))
    assert migrated["schema_version"] == SCHEMA_VERSION
    assert sorted(p.name for p in path.parent.iterdir()) == siblings
