"""A recording: one call an application made to a model, as the recorder keeps
it. (ADR 0058)

The document and its two pure functions, nothing else. Where a recording is
filed and how it reaches the disk is the store's (`digline.store.file_store`),
because the core does no I/O.

**Three compartments, kept apart from the first day** (ADR 0058 §3): `case`,
what becomes `Case.vars`; `setup`, what decided how the system answered; and
`response`, a `RecordedResponse`. The response compartment is written by the
function that writes a recorded response into a run document, and read back by
its inverse (`recorded_response_to_dict`, `recorded_response_from_dict`): a
second serializer of one fact is how a trajectory came to have three forms
(ADR 0057, ADR 0058 §11).

**A format of its own, with a version of its own.** `RECORDING_VERSION` moves
on its own schedule, apart from `SCHEMA_VERSION` and `JOURNAL_VERSION`. A
recording at any other version is refused by name, saying which version was
read and which this digline reads, and is never read as the version it is not.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, cast

from digline.core.aggregate import Label
from digline.core.refused import RefusedError, Written
from digline.core.run import (
    RecordedResponse,
    recorded_response_from_dict,
    recorded_response_to_dict,
)

__all__ = [
    "RECORDING_VERSION",
    "Recording",
    "RecordingRefusedError",
    "recording_from_dict",
    "recording_to_dict",
    "setup_digest_of",
]

#: The recording's format version. Independent of `SCHEMA_VERSION` and of
#: `JOURNAL_VERSION`: a recording is a document of its own, and a reader that
#: meets another version refuses it rather than guessing. (ADR 0058 §11)
RECORDING_VERSION = 1

_LABELS: frozenset[str] = frozenset({"positive", "negative"})


class RecordingRefusedError(RefusedError):
    """Raised when a recording cannot be built, or a document cannot be read as
    one. A `RefusedError`, so a `ValueError`: a caller that already catches
    `ValueError` around a read keeps working.
    """


def _json_value(value: object, where: str) -> object:
    """`value` as JSON would carry it, or a refusal naming `where`.

    Strict, and on purpose: `canonical` would turn an unknown value into
    `"<TypeName>"`, which is a value nobody sent. A compartment that cannot be
    written as it was given is refused, not rewritten.
    """
    try:
        return json.loads(json.dumps(value, allow_nan=False))
    except (TypeError, ValueError):
        raise RecordingRefusedError(
            f"a recording's {where} holds a value JSON cannot carry as it is: "
            "pass strings, numbers, booleans, null, lists and objects with "
            "string keys"
        ) from None


def setup_digest_of(setup: Mapping[str, object]) -> str:
    """The digest of a single call's setup: the first 16 hex characters of the
    SHA-256 of its JSON, keys sorted. An episode's digest is made otherwise
    (ADR 0058 §8) and is passed in, not computed here."""
    payload = json.dumps(
        _json_value(dict(setup), "setup"),
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True, slots=True)
class Recording:
    """One recorded call, or one episode. (ADR 0058 §3, §4, §7)

    `source_tenant` is the tenant the call was made for, and the directory the
    recording is filed under. `app` is a field and not a directory (§1).
    `suite` is the name the call site gave, or `_unassigned` (§2). `episode` is
    the id of the episode the call belongs to, `None` for a single call made
    outside one (§5). `label` is `Case.label` before the case exists, empty
    until a person gives one (§7).
    """

    source_tenant: str
    app: str
    suite: str
    case: Mapping[str, object]
    setup: Mapping[str, object]
    setup_digest: str
    response: RecordedResponse
    episode: str | None = None
    label: Label | None = None

    def __post_init__(self) -> None:
        for name in ("source_tenant", "app", "suite", "setup_digest"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value:
                raise RecordingRefusedError(
                    f"Recording.{name} must be a non-empty string"
                )
        if self.episode == "":
            raise RecordingRefusedError(
                "Recording.episode must be a non-empty string, or None for a "
                "call made outside an episode"
            )
        if self.label is not None and self.label not in _LABELS:
            raise RecordingRefusedError(
                f"Recording.label must be 'positive', 'negative' or None, got "
                f"{self.label!r}"
            )
        # Replaced by the checked copy, so that what is written is what was
        # checked, and a caller who mutates its own dict later changes nothing
        # here. `object.__setattr__` is how a frozen dataclass sets a field in
        # its own `__post_init__`.
        object.__setattr__(self, "case", _compartment(self.case, "case"))
        object.__setattr__(self, "setup", _compartment(self.setup, "setup"))


def _compartment(value: object, name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise RecordingRefusedError(
            f"a recording's {name} must be a mapping, not a {type(value).__name__}"
        )
    items = cast(Mapping[object, object], value)
    if not all(isinstance(key, str) for key in items):
        raise RecordingRefusedError(
            f"a recording's {name} has a key that is not a string"
        )
    return cast(Mapping[str, object], _json_value(dict(items), name))


def recording_to_dict(recording: Recording) -> dict[str, object]:
    """The document. Absent rather than emptied, like every payload field of a
    run document: no `episode` outside an episode, no `label` until one is
    given."""
    payload: dict[str, object] = {
        "recording_version": RECORDING_VERSION,
        "source_tenant": recording.source_tenant,
        "app": recording.app,
        "suite": recording.suite,
        "case": dict(recording.case),
        "setup": dict(recording.setup),
        "setup_digest": recording.setup_digest,
        "response": recorded_response_to_dict(recording.response),
    }
    if recording.episode is not None:
        payload["episode"] = recording.episode
    if recording.label is not None:
        payload["label"] = recording.label
    return payload


def recording_from_dict(raw: object, *, where: str = "this recording") -> Recording:
    """A document read back, or a refusal by name. `where` opens every
    sentence: the store passes the file's path.

    The version is read first and alone: a document at another version is not
    read field by field, because a newer format may give an old key a new
    meaning. Exactly the integer, as the register reads its own: `True == 1` in
    Python, and a document claiming version `true` is not at version 1.
    """
    if not isinstance(raw, Mapping):
        raise RecordingRefusedError(
            f"{where} is not a JSON object, so it is not a recording"
        )
    document = cast(Mapping[str, Any], raw)
    version = document.get("recording_version")
    if version is None:
        raise RecordingRefusedError(
            f"{where} carries no recording_version, so it is not a recording "
            f"this digline can read (it reads version {RECORDING_VERSION})"
        )
    if type(version) is not int or version != RECORDING_VERSION:
        raise RecordingRefusedError(
            f"{where} is at version {repr(version)[:40]} and this digline "
            f"reads version {RECORDING_VERSION}: a recording at another version "
            "is never read as this one. Upgrade digline to read it"
        )
    response = document.get("response")
    if not isinstance(response, Mapping):
        raise RecordingRefusedError(f"{where} carries no response object")
    try:
        return Recording(
            source_tenant=_text(document, "source_tenant"),
            app=_text(document, "app"),
            suite=_text(document, "suite"),
            case=cast(Mapping[str, object], document.get("case")),
            setup=cast(Mapping[str, object], document.get("setup")),
            setup_digest=_text(document, "setup_digest"),
            response=recorded_response_from_dict(cast(Mapping[str, Any], response)),
            episode=_optional_text(document, "episode"),
            label=cast(Label | None, _optional_text(document, "label")),
        )
    except RecordingRefusedError:
        raise
    except ValueError as exc:
        # The response compartment's own reader wrote this sentence; it is
        # handed over as written, after where it was found. (ADR 0043 §2)
        raise RecordingRefusedError(
            Written.of(exc, f"{where}, response: ", named=False)
        ) from exc


def _text(document: Mapping[str, Any], key: str) -> str:
    value = document.get(key)
    if not isinstance(value, str):
        raise RecordingRefusedError(f"a recording's {key!r} is not a string")
    return value


def _optional_text(document: Mapping[str, Any], key: str) -> str | None:
    if key not in document:
        return None
    return _text(document, key)
