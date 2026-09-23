"""The files a suite declares as the thing under test, read as they are now.

Here and not in the driver for the same reason the clock and git are here: this
is the layer allowed to touch the world, and a driver that opened files would
need one to be tested. (ADR 0003, and ADR 0011 §7 for why "here" is `host` and
no longer `cli`.)
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Mapping
from pathlib import Path

from digline.core import Artifact
from digline.host.errors import UsageError
from digline.run import HasArtifacts, Suite

__all__ = ["read_artifacts", "read_pinned"]


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
        key = _key(path, root or base)
        found[key] = Artifact(
            sha=hashlib.sha256(data).hexdigest(),
            text=data.decode("utf-8"),
        )
    return found


def read_pinned(
    suite: Suite,
    base: Path,
    *,
    root: Path | None = None,
    artifacts: Mapping[str, Artifact],
) -> tuple[str, ...]:
    """The paths that must not drift, as the keys the run files them under.

    Resolved exactly as `read_artifacts` resolves an artifact — same helper, so
    a pin and the file it pins cannot come to be keyed differently — and then
    checked against what was actually recorded.

    **A pin naming nothing recorded is refused here**, which is the whole reason
    this is a separate step rather than a field `Suite` could validate. A path in
    neither run produces no `ArtifactDelta` at all, so a typo would be a control
    that never runs and never says so; and `Suite` cannot catch it, because the
    artifact set is the union of the suite's own and whatever the target answered
    through `HasArtifacts`, which no suite has at construction. (ADR 0029 §4)

    Deduplicated after resolution: `tools.json` and `./tools.json` are two
    spellings that `Suite` cannot tell apart and one key here. Order follows the
    resolved key, so the run document does not record the order somebody typed.
    """
    keys: dict[str, Path] = {}
    for entry in suite.pinned:
        path = entry if entry.is_absolute() else base / entry
        keys.setdefault(_key(path, root or base), entry)
    unknown = sorted(key for key in keys if key not in artifacts)
    if unknown:
        named = ", ".join(f"{keys[key]} (as {key})" for key in unknown)
        raise UsageError(
            f"suite {suite.name!r} pins {named}, which this run records no "
            "artifact for. A pinned path that names nothing recorded produces "
            "no comparison at all — not even an unknown one — so it would be a "
            "control that never runs and never says so. Declare it in "
            "`artifacts` as well, or correct the path"
        )
    return tuple(sorted(keys))


def _key(path: Path, root: Path) -> str:
    """`os.path.relpath` and not `Path.relative_to`: the latter raises when the
    path is outside the root, and raising is what produced the fallback this
    replaces. `relpath` walks up instead, which is the honest answer."""
    try:
        return os.path.relpath(path.resolve(), root.resolve())
    except ValueError:  # pragma: no cover - Windows, across drives
        return str(path.resolve())
