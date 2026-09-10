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

from digline.host import load_suite, load_target, read_artifacts, utc_now_iso
from digline.run import execute
from digline.store import FileResultStore

__all__ = ["cycle"]


def cycle(path: Path, root: Path, *, promote: bool) -> str:
    spec = str(path)
    suite, loaded = load_suite(spec, root=root)
    target = load_target(None, loaded, spec)
    run = execute(
        suite,
        target,
        created_at=utc_now_iso(),
        git_commit=None,
        artifacts=read_artifacts(suite, target, path.parent, root=root),
    )
    store = FileResultStore(str(root))
    ref = store.write_run(run)
    if promote:
        store.promote_baseline(ref, suite.config_hash())
    return ref.key
