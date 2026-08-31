"""Bringing stored documents up to the current schema.

A software house keeps years of history for a dozen customers. If a release
that adds a field costs them their baselines, the release does not happen — so
the schema bump has to come with the way through it.

**Only additive bumps migrate.** A version that added a field with an obvious
empty value — `aggregate` became `[]`, `suspended` became `false` — can be
upgraded without inventing anything. A version that added a field with no
answer in the old document cannot: there is no `tenant` to derive for a file
written before perimeters existed, and no `environment` for one written before
staging and production were told apart. Guessing there would place a run in a
perimeter it may not belong to, which is the one mistake this project exists to
prevent. Those refuse, and the message names the missing field.

**Rewriting happens last.** Each document is upgraded in memory, then parsed
with the *current* reader, and only a document that parses is written back. A
migration that wrote first and validated afterwards would turn one unreadable
file into one corrupted file.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from digline.core.run import SCHEMA_VERSION, run_from_dict, run_to_json

__all__ = [
    "MigrationReport",
    "NonAdditiveError",
    "document_version",
    "migrate_file",
    "upgrade_document",
]


class NonAdditiveError(Exception):
    """Raised when a document cannot be upgraded without inventing a value."""


def _add_suspended(raw: dict[str, Any]) -> dict[str, Any]:
    """4 -> 5. Every case predates the idea of being set aside, so none was."""
    results = cast(list[dict[str, Any]], raw.get("results") or [])
    for case in results:
        case.setdefault("suspended", False)
    raw["results"] = results
    return raw


def _add_aggregate(raw: dict[str, Any]) -> dict[str, Any]:
    """5 -> 6. A run written before aggregates existed declared none."""
    raw.setdefault("aggregate", [])
    return raw


def _add_artifacts(raw: dict[str, Any]) -> dict[str, Any]:
    """6 -> 7. A run written before artifacts existed declared none.

    `{}` is not a guess: a suite that never named a file under examination had
    none, which is exactly what an empty map says. Nothing is reconstructed —
    the prompt of a run from last month is not recoverable and must not be
    invented.
    """
    raw.setdefault("artifacts", {})
    return raw


def _add_configs(raw: dict[str, Any]) -> dict[str, Any]:
    """7 -> 8. A run written before ADR 0005 recorded no configuration.

    `{}` is not a guess: nobody asked the target what it was configured to do,
    so nothing is known — and `compare()` reads that as `unknown` for every
    field rather than as a change. Which is what keeps a baseline promoted last
    month from needing to be promoted again.

    The model that answered is **not** reconstructed from anywhere. It is not in
    the document, and putting a plausible one there would be the invention this
    module exists to refuse.
    """
    raw.setdefault("target_config", {})
    raw.setdefault("judge_config", {})
    return raw


#: from-version -> how to reach the next one. A version absent from this table
#: is one whose bump was not additive, and the absence is the whole statement.
_STEPS: Mapping[int, Callable[[dict[str, Any]], dict[str, Any]]] = {
    4: _add_suspended,
    5: _add_aggregate,
    6: _add_artifacts,
    7: _add_configs,
}

#: What each non-additive bump introduced, for the refusal message. Kept beside
#: the steps so the two are read together and neither is updated alone.
_NON_ADDITIVE: Mapping[int, str] = {
    1: "'assertion_id' on every verdict, which pairs a verdict with its "
    "counterpart — deriving it would pair verdicts that were never the same "
    "check",
    2: "'tenant' and 'redacted' on the run — a tenant is a perimeter and "
    "cannot be guessed, and a document whose redaction is unknown must not be "
    "declared complete",
    3: "'environment' on the run — a comparison that cannot say whether it "
    "read staging or production is one nobody should act on",
}


def document_version(raw: Mapping[str, Any]) -> int:
    """The schema a document declares. `0` when it declares none."""
    return int(raw.get("schema_version", 0))


def upgrade_document(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Apply every additive step up to `SCHEMA_VERSION`.

    Raises `NonAdditiveError` at the first version that has no step, naming
    what that version introduced. The input is not modified.
    """
    document = cast(dict[str, Any], json.loads(json.dumps(raw)))
    version = document_version(document)
    if version > SCHEMA_VERSION:
        raise NonAdditiveError(
            f"the document declares schema {version}, which is newer than this "
            f"version understands ({SCHEMA_VERSION}). Upgrade digline "
            "instead: a newer file cannot be rewritten backwards without "
            "discarding whatever the newer schema added."
        )
    while version < SCHEMA_VERSION:
        step = _STEPS.get(version)
        if step is None:
            introduced = _NON_ADDITIVE.get(
                version, "a field with no answer in the older document"
            )
            raise NonAdditiveError(
                f"schema {version} cannot be migrated to {version + 1}: that "
                f"version introduced {introduced}. Nothing here can supply it, "
                "and supplying it wrongly is worse than not reading the file."
            )
        document = step(document)
        version += 1
        document["schema_version"] = version
    return document


def migrate_file(path: Path, *, dry_run: bool = False) -> int | None:
    """Upgrade one stored document in place.

    Returns the version it came from, or `None` if it was already current.
    Raises `NonAdditiveError` when it cannot be upgraded, and `ValueError` when
    the upgraded document does not parse — which is the check that makes
    rewriting safe.
    """
    raw = cast(Mapping[str, Any], json.loads(path.read_text(encoding="utf-8")))
    version = document_version(raw)
    if version == SCHEMA_VERSION:
        return None

    upgraded = upgrade_document(raw)
    # Parsed with the current reader *before* anything is written. If the
    # upgrade produced something this version cannot read, the file on disk is
    # still the old one — recoverable — rather than a new one that is not.
    run = run_from_dict(upgraded)
    if not dry_run:
        path.write_text(run_to_json(run), encoding="utf-8")
    return version


@dataclass(frozen=True, slots=True)
class MigrationReport:
    """What a migration did, in the terms a reader needs to check it."""

    #: path -> the version it came from.
    migrated: tuple[tuple[str, int], ...] = ()
    already_current: int = 0
    #: path -> why it was refused. Never a silent skip.
    refused: tuple[tuple[str, str], ...] = ()

    @property
    def ok(self) -> bool:
        return not self.refused


def migrate_paths(paths: tuple[Path, ...], *, dry_run: bool = False) -> MigrationReport:
    """Migrate every path, collecting refusals instead of stopping at the first.

    One unmigratable file out of two hundred must not leave the other hundred
    and ninety-nine unmigrated: the report names what was refused, and the
    caller decides.
    """
    migrated: list[tuple[str, int]] = []
    refused: list[tuple[str, str]] = []
    current = 0
    for path in paths:
        try:
            came_from = migrate_file(path, dry_run=dry_run)
        except (NonAdditiveError, ValueError) as exc:
            refused.append((str(path), str(exc)))
            continue
        if came_from is None:
            current += 1
        else:
            migrated.append((str(path), came_from))
    return MigrationReport(
        migrated=tuple(migrated),
        already_current=current,
        refused=tuple(refused),
    )
