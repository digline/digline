"""The files a suite declares as the thing under test, read as they are now.

Here and not in the driver for the same reason the clock and git are here: this
is the layer allowed to touch the world, and a driver that opened files would
need one to be tested. (ADR 0003, and ADR 0011 §7 for why "here" is `host` and
no longer `cli`.)
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

from digline.core import Artifact
from digline.host.errors import UsageError
from digline.run import HasArtifacts, Suite

__all__ = ["read_artifacts"]


def read_artifacts(
    suite: Suite, target: object, base: Path, *, root: Path | None = None
) -> dict[str, Artifact]:
    """The declared files, as they are right now.

    Relative paths resolve against the suite's own directory, which is where a
    prompt sits next to the suite that names it. They are **keyed** against
    `root`, the perimeter — the repository the run belongs to — so that a file
    from outside it is recorded as the `../` it is rather than as a bare name.
    `root` defaults to `base`, which is the old behaviour and the tightest
    reading of it.

    The **target** is asked too, when it can answer. A `ProviderTarget` builds
    its prompt from a file and already knows which one, so `artifacts=[…]` does
    not have to repeat a path that would then have two places to be wrong.

    A declared file that is missing raises. It is the thing under examination —
    a run that quietly recorded no prompt would be a run whose evidence is
    absent exactly when it matters.
    """
    declared: list[Path] = list(suite.artifacts)
    if isinstance(target, HasArtifacts):
        declared.extend(target.artifacts())

    found: dict[str, Artifact] = {}
    for entry in declared:
        path = entry if entry.is_absolute() else base / entry
        if not path.is_file():
            raise UsageError(
                f"suite {suite.name!r} declares the artifact {entry}, which "
                f"is not a file at {path}: the thing under test cannot be "
                "recorded, so the run would not say what produced it"
            )
        data = path.read_bytes()
        # Keyed by where it sits relative to the **perimeter**, so a run file
        # stays readable on another machine: an absolute path is this laptop's
        # fact. Relative to the repository and not to the suite's own directory
        # because the old rule had a hole: a path outside the suite directory
        # fell through to `path.name`, so `/etc/hosts` was recorded as `hosts`
        # and `../secret.env` as `secret.env` — the escape was invisible in the
        # one document that is supposed to say what was under test. `relpath`
        # has no such fallback: outside the perimeter it yields `../secret.env`,
        # which is the truth and reads as one.
        key = _relative(path, root or base)
        found[key] = Artifact(
            sha=hashlib.sha256(data).hexdigest(),
            text=data.decode("utf-8"),
        )
    return found


def _relative(path: Path, root: Path) -> str:
    """`os.path.relpath` and not `Path.relative_to`: the latter raises when the
    path is outside the root, and raising is what produced the fallback this
    replaces. `relpath` walks up instead, which is the honest answer."""
    try:
        return os.path.relpath(path.resolve(), root.resolve())
    except ValueError:  # pragma: no cover - Windows, across drives
        return str(path.resolve())
