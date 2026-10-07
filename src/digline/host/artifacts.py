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
    perimeter = (root or base).resolve()
    # Each declared path is normalized once, here, and that one result is what
    # the boundary checks, what is read and what the key is computed from. A
    # name made from the path before normalization would answer for a file the
    # check did not see. (ADR 0045 §5) Each entry: who declared it, the field
    # that names it, the path as declared, and that one normalized path.
    declared: list[tuple[str, str, Path, Path]] = [
        (
            f"suite {suite.name!r} declares the artifact {entry}",
            "`artifacts`",
            entry,
            _normalized(entry, base),
        )
        for entry in suite.artifacts
    ]
    if isinstance(target, HasArtifacts):
        for entry in target.artifacts():
            who = (
                f"the target {_target_name(target)} of suite {suite.name!r} "
                f"answers the artifact {entry}"
            )
            if not entry.is_absolute():
                raise UsageError(
                    f"{who}, a relative path. A target reports the file it "
                    "read, already resolved: a relative answer would be "
                    "resolved a second time, against a directory the target "
                    "did not read from. Answer it absolute (ADR 0045 §5)"
                )
            declared.append((who, "`HasArtifacts`", entry, entry.resolve()))

    found: dict[str, Artifact] = {}
    for who, field, entry, path in declared:
        if not path.is_relative_to(perimeter):
            # The resolved path only where it says something the declared one
            # does not: an absolute answer is usually its own resolution.
            where = "" if path == entry else f", which resolves to {path}"
            raise UsageError(
                f"{who}{where}, outside {perimeter}: "
                f"{field} names a file outside the perimeter, and a file from "
                "outside is never read into a run, whatever the suite format. "
                "Move it into the project (ADR 0042 §2)"
            )
        if not path.is_file():
            raise UsageError(
                f"{who}, which is not a file at {path}: the thing under test "
                "cannot be recorded, so the run would not say what produced it"
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
        key = _key(path, perimeter)
        # The file under test is the user's, so a file that is not UTF-8 is
        # refused at the read, where it happens. (ADR 0041 §4.2)
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise UsageError(
                f"{who}, which is not UTF-8 at byte {exc.start}: an artifact is "
                "recorded as its text, so these bytes cannot be"
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
    perimeter = (root or base).resolve()
    keys: dict[str, Path] = {}
    for entry in suite.pinned:
        keys.setdefault(_key(_normalized(entry, base), perimeter), entry)
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


def _normalized(entry: Path, base: Path) -> Path:
    """A path the suite declares, anchored to the suite's directory and
    normalized. Only for `Suite.artifacts` and `Suite.pinned`, which a front end
    reads from a suite file it loaded; a target's answer is never anchored
    here. (ADR 0045 §4)"""
    return (entry if entry.is_absolute() else base / entry).resolve()


def _target_name(target: object) -> str:
    """The target as a sentence can name it."""
    # The class's name and never `repr(target)`: a `repr` is the suite's code,
    # and calling it inside a refusal would run that code, which can raise or
    # print anything, at the moment digline is explaining why it stopped.
    return type(target).__qualname__


def _key(path: Path, perimeter: Path) -> str:
    """`os.path.relpath` and not `Path.relative_to`: the latter raises when the
    path is outside the root, and raising is what produced the fallback this
    replaces. `relpath` walks up instead, which is the honest answer.

    Both arguments arrive normalized, and nothing here normalizes again: the
    name is computed from the path the boundary checked. (ADR 0045 §5)"""
    try:
        return os.path.relpath(path, perimeter)
    except ValueError:  # pragma: no cover - Windows, across drives
        return str(path)
