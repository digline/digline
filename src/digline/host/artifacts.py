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

    **A declared file outside the perimeter is refused before it is read**, for
    every suite format and for what a target answers through `HasArtifacts`:
    ADR 0007 §6's read boundary, which reached the TOML form only. Resolved
    first, so a symlink pointing outward is outside. A `.py` suite can open any
    file itself; recording it in a run, which crosses on digline's channel, is
    digline's act, and it does not perform it. (ADR 0042 §2)
    """
    declared: list[Path] = list(suite.artifacts)
    if isinstance(target, HasArtifacts):
        declared.extend(target.artifacts())

    perimeter = (root or base).resolve()
    found: dict[str, Artifact] = {}
    for entry in declared:
        path = entry if entry.is_absolute() else base / entry
        resolved = path.resolve()
        if not resolved.is_relative_to(perimeter):
            raise UsageError(
                f"suite {suite.name!r} declares the artifact {entry}, which "
                f"resolves to {resolved}, outside {perimeter}: `artifacts` "
                "names a file outside the perimeter, and a file from outside "
                "is never read into a run, whatever the suite format. Move it "
                "into the project (ADR 0042 §2)"
            )
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
        # The file under test is the user's, so a file that is not UTF-8 is
        # refused at the read, where it happens. (ADR 0041 §4.2)
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise UsageError(
                f"suite {suite.name!r} declares the artifact {entry}, which is "
                f"not UTF-8 at byte {exc.start}: an artifact is recorded as its "
                "text, so these bytes cannot be"
            ) from None
        found[key] = Artifact(sha=hashlib.sha256(data).hexdigest(), text=text)
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
