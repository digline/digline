"""Producing a run, and promoting one, for the fixtures.

A plain module rather than a name in `conftest.py`, which is the rule
`tests/_helpers.py` sets in this repository: everything shared is a module, and
no test module imports another. `digline-openai` and `digline-bedrock` share
their fakes the same way.

It goes through `digline.host` and `digline.run` rather than through the CLI, so
what it writes is what `digline run` would have written — but it is a fixture,
not a test of the CLI, and driving a subprocess per run would triple the time
these tests take to say the same thing.
"""

from __future__ import annotations

from pathlib import Path

from digline.core import key_of
from digline.host import (
    load_suite,
    load_target,
    read_artifacts,
    read_pinned,
    utc_now_iso,
)
from digline.run import execute
from digline.store import FileResultStore

__all__ = ["cycle"]


def cycle(path: Path, root: Path, *, promote: bool) -> str:
    spec = str(path)
    suite, loaded = load_suite(spec, root=root)
    target = load_target(None, loaded, spec)
    artifacts = read_artifacts(suite, target, path.parent, root=root)
    run = execute(
        suite,
        target,
        created_at=utc_now_iso(),
        git_commit=None,
        artifacts=artifacts,
        # As `digline run` and `--digline-run` resolve them: a suite that pins
        # a file is refused by `execute` without its resolved pin set.
        pinned=read_pinned(suite, path.parent, root=root, artifacts=artifacts),
    )
    store = FileResultStore(str(root))
    ref = store.write_run(run)
    if promote:
        # Whatever is there now: a cycle that promotes is standing in for a
        # person who has just compared against it.
        current = store.read_baseline(suite.tenant, suite.name)
        store.promote_baseline(
            ref,
            suite.config_hash(),
            expected_baseline=(
                None
                if current is None
                else key_of(current.created_at, current.config_hash)
            ),
            promoted_at="2026-01-02T09:00:00+00:00",
            declared=None,
        )
    return ref.key
