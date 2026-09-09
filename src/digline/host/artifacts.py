"""The files a suite declares as the thing under test, read as they are now.

Here and not in the driver for the same reason the clock and git are here: this
is the layer allowed to touch the world, and a driver that opened files would
need one to be tested. (ADR 0003, and ADR 0011 §7 for why "here" is `host` and
no longer `cli`.)
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from digline.core import Artifact
from digline.host.errors import UsageError
from digline.run import HasArtifacts, Suite

__all__ = ["read_artifacts"]


def read_artifacts(suite: Suite, target: object, base: Path) -> dict[str, Artifact]:
    """The declared files, as they are right now.

    Relative paths resolve against the suite's own directory, which is where a
    prompt sits next to the suite that names it.

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
        # Keyed by where it sits relative to the suite, so a run file stays
        # readable on another machine: an absolute path is this laptop's fact.
        try:
            key = str(path.resolve().relative_to(base.resolve()))
        except ValueError:
            key = path.name
        found[key] = Artifact(
            sha=hashlib.sha256(data).hexdigest(),
            text=data.decode("utf-8"),
        )
    return found
