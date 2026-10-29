"""The readers take `ResultStore`, and this file is what holds them to it.

Retyping a signature from `FileResultStore` to `ResultStore` binds almost
nothing on its own: every construction site passes a `FileResultStore`, which
satisfies both. The retyped sites hold one another only where one calls
another — `_resolve` holds `resolve_key`, `explained` holds `read_run`, `serve`
holds `ViewHandler` — and only for as long as the caller stays retyped. Measured
before this file existed, reverting one site at a time: those three went red,
and the other six stayed green. What makes each one hold is a caller passing
something that is **not** a `FileResultStore` — `MemoryStore`, which implements
the five and nothing else — so that pyright's strict run over `tests/` goes red
on the argument the moment a parameter narrows again. Each of the nine was
reverted in turn with this file present, and each went red here.

**It holds exactly the sites called below, and each is named with how:**

| Site | Held by |
|---|---|
| `host.resolve_key`, `read_run`, `need_baseline` | a call that runs |
| `host.explained` | a call that runs |
| `cli.main._resolve` | a call that runs |
| `cli.main._resume` (`SupportsJournal`) | a call that runs, with `_NoJournals` |
| `cli.view.ViewHandler` | a server that runs and serves a page from the fake |
| `cli.view.serve` | **a call pyright checks and nothing runs** |
| `pytest_digline.plugin._measure` | **a call pyright checks and nothing runs** |

The last two are called in `held_by_pyright_alone`, which nothing calls: `serve`
blocks until interrupted, and `_measure` needs a target to call. pyright reads
the calls and the interpreter never does, so the signature is held and the
body is not exercised through the fake. The body is held by the annotation
itself — inside a function whose parameter says `ResultStore`, a call to a
method the protocol lacks is already a type error — and that half needs no
test.

A new signature typed `ResultStore` is held by none of this until a test here
calls it with the fake. That is the whole reach of the file.
"""

from __future__ import annotations

import threading
import urllib.request
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from tests._protocol_store import MemoryStore

from digline.cli.main import _resolve, _resume  # pyright: ignore[reportPrivateUsage]
from digline.cli.view import ViewHandler, self_netlocs
from digline.core import (
    CaseResult,
    Contains,
    Run,
    Score,
    Verdict,
    key_of,
)
from digline.host import (
    Loaded,
    UsageError,
    explained,
    need_baseline,
    read_run,
    resolve_key,
)
from digline.run import Case, Suite
from digline.store import (
    FileResultStore,
    Journal,
    JournalHeader,
    Pending,
    ResultStore,
    SupportsJournal,
)

if TYPE_CHECKING:
    from digline.cli.view import serve
    from pytest_digline.plugin import (
        _measure,  # pyright: ignore[reportPrivateUsage]
    )

TENANT = "acme"
SUITE = "memory"

SUITE_OBJ = Suite(
    tenant=TENANT,
    environment="test",
    name=SUITE,
    assertions=[Contains(needle="x")],
    cases=[Case(id="case-1")],
)


def a_run(created_at: str, *, score: float = 1.0) -> Run:
    return Run(
        tenant=TENANT,
        environment="test",
        suite=SUITE,
        config_hash="hash-a",
        created_at=created_at,
        results=(
            CaseResult(
                "case-1",
                (
                    Verdict(
                        score=Score(name="contains", score=score),
                        threshold=1.0,
                        tolerance=0.0,
                        status="pass" if score >= 1.0 else "fail",
                        reason="found" if score >= 1.0 else "missing",
                        assertion_id="contains",
                    ),
                ),
            ),
        ),
    )


OLDER = a_run("2026-01-01T10:00:00+00:00")
NEWER = a_run("2026-01-02T10:00:00+00:00", score=0.0)


def a_store(*, baseline: Run | None = None) -> MemoryStore:
    store = MemoryStore()
    store.write_run(OLDER)
    store.write_run(NEWER)
    if baseline is not None:
        store.baselines[(TENANT, SUITE)] = baseline
    return store


class _NoJournals:
    """`SupportsJournal` with nothing pending — what `_resume` asks and nothing
    more. It is not a `ResultStore`, which is the point: `_resume` takes the
    journal protocol alone."""

    def open_journal(self, header: JournalHeader) -> Journal:
        raise NotImplementedError("nothing here opens a journal")

    def pending(self, tenant: str, suite: str) -> tuple[Pending, ...]:
        return ()

    def drop_pending(self, tenant: str, suite: str, key: str) -> None:
        raise AssertionError("nothing is pending, so nothing is dropped")


# --------------------------------------------------------------------------- #
# The fake is a ResultStore, and the file store is still one
# --------------------------------------------------------------------------- #


def test_the_fake_is_a_result_store_and_only_that() -> None:
    """Checked by pyright on the assignments, and at run time on what the fake
    lacks: were it to grow the file store's other members, it would stop being
    evidence that the five are what these sites need."""
    fake: ResultStore = MemoryStore()
    journal: SupportsJournal = _NoJournals()
    assert fake is not None and journal is not None
    for concrete in ("key_for", "stored_paths", "register_path", "ensure_layout"):
        assert not hasattr(MemoryStore, concrete), concrete
    for optional in ("read_register", "pending", "open_journal"):
        assert not hasattr(MemoryStore, optional), optional


def test_the_fake_keeps_the_key_invariant() -> None:
    ref = MemoryStore().write_run(OLDER)
    assert ref.key == key_of(OLDER.created_at, OLDER.config_hash)


def test_the_fake_does_not_promote() -> None:
    store = a_store()
    ref = next(iter(store.runs))
    with pytest.raises(NotImplementedError, match="condition 8"):
        store.promote_baseline(
            ref,
            "hash-a",
            expected_baseline=None,
            promoted_at="2026-01-03",
            declared=None,
        )


# --------------------------------------------------------------------------- #
# host/
# --------------------------------------------------------------------------- #


def test_resolve_key_finds_the_newest_run_in_the_fake() -> None:
    resolved = resolve_key(a_store(), SUITE_OBJ, "latest")
    assert resolved.key == key_of(NEWER.created_at, NEWER.config_hash)
    assert resolved.note == ""


def test_resolve_key_on_an_empty_fake_asks_for_a_run() -> None:
    """The empty-store sentence, not the migrate one: the fake can never report
    a skipped document, so the other branch is out of its reach (see
    `tests/_protocol_store.py`)."""
    with pytest.raises(UsageError, match="Run it first"):
        resolve_key(MemoryStore(), SUITE_OBJ, "latest")


def test_read_run_and_need_baseline_read_the_fake() -> None:
    store = a_store(baseline=OLDER)
    key = key_of(NEWER.created_at, NEWER.config_hash)
    assert read_run(store, SUITE_OBJ, key) is NEWER
    assert need_baseline(store, SUITE_OBJ) is OLDER


def test_need_baseline_refuses_on_a_fake_without_one() -> None:
    with pytest.raises(UsageError, match="has no baseline"):
        need_baseline(a_store(), SUITE_OBJ)


def test_explained_compares_against_the_fakes_baseline() -> None:
    key = key_of(NEWER.created_at, NEWER.config_hash)
    against = explained(a_store(baseline=OLDER), SUITE_OBJ, key)
    assert against.reading == "comparison"
    assert against.baseline is OLDER
    alone = explained(a_store(), SUITE_OBJ, key)
    assert alone.reading == "run"
    assert alone.baseline is None


# --------------------------------------------------------------------------- #
# cli/
# --------------------------------------------------------------------------- #


def test_the_cli_resolves_latest_through_the_fake() -> None:
    assert _resolve(a_store(), SUITE_OBJ, "latest") == key_of(
        NEWER.created_at, NEWER.config_hash
    )


def test_resume_asks_only_the_journal_protocol() -> None:
    assert _resume(_NoJournals(), SUITE_OBJ, None) is None


def test_the_view_serves_the_runs_screen_from_the_fake() -> None:
    """A real server, constructed the way `serve()` constructs it, over the
    fake. The page must name the newest run's key: a 200 alone would also be
    what the *"list unavailable"* page answers with."""
    known: set[str] = set()
    handler = partial(ViewHandler, suite=SUITE_OBJ, store=a_store(), known=known)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)  # pyright: ignore[reportArgumentType]
    port = int(httpd.server_address[1])
    known.update(self_netlocs("127.0.0.1", port))
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=10) as r:
            status, page = r.status, r.read().decode("utf-8")
    finally:
        httpd.shutdown()
        httpd.server_close()
    assert status == 200
    assert key_of(NEWER.created_at, NEWER.config_hash) in page


def held_by_pyright_alone(root: Path) -> None:
    """Never called. pyright checks these two calls; nothing runs them, so the
    signatures are held and the bodies are not exercised through the fake."""
    serve(SUITE_OBJ, MemoryStore())
    _measure(SUITE_OBJ, Loaded(SUITE_OBJ), "suite.py", root, MemoryStore(), root=root)


def test_the_file_store_still_satisfies_every_retyped_site() -> None:
    """The other direction, which the whole tree already exercises; stated so
    the file names both sides of the claim."""
    fake: ResultStore = FileResultStore("unused")
    journal: SupportsJournal = FileResultStore("unused")
    assert fake is not None and journal is not None
