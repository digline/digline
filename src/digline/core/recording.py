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

**An episode is a recording too** (ADR 0058 §5), with the same compartments
and three keys a single call never carries: `steps`, its trajectory as a list
of `RecordedStep`; `interrupted`, where the application raised inside it; and
`unrecorded_children`, how many calls made inside it were not recorded. A
recording carries `steps` if and only if it is an episode. They are optional
keys added to a format that has not shipped, so `RECORDING_VERSION` stays 1.

**Two keys added for the import, on the same terms** (ADR 0058 §4, §5, §10):
`id`, an episode's own id, the one its children carry in `episode`, so that
the files alone can join them back; and `recorded_at`, the system time the
recording was written at, so that a case elected from it can carry the
watermark ADR 0023 §9 reads.

**The response's `input` is the question, as JSON text** (`input_of`): a single
call's is its case's `messages`, an episode's is its whole case. The import
copies it into a reviewed answer, beside the answer, for the judge to read,
and refuses an answer recorded without one. The field was always in a
recorded response, so `RECORDING_VERSION` stays 1.

**A public contract** (ADR 0062 §2): a writer in another language writes these
documents too, so what is fixed is held here, on write and on read alike.
Three things were ruled for it, with the format unreleased, so
`RECORDING_VERSION` stays 1:

- a float enters `setup_digest` as text in one form two languages can both
  write (`setup_digest_of`);
- `recorded_at` has one form, UTC written with `+00:00`, refused by name in
  any other, and is compared as an instant, never as text (`instant_of`);
- the `label` compartment is gone. ADR 0059 ruled that the import no longer
  reads it, and a field no reader reads is not one a writer should be asked
  to fill. A document written with one is still read, and the key ignored, as
  the reader ignores any key it does not know.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, cast

from digline.core.refused import RefusedError, Written
from digline.core.run import (
    Actor,
    RecordedResponse,
    RecordedStep,
    RecordedToolCall,
    recorded_response_from_dict,
    recorded_response_to_dict,
    recorded_step_to_dict,
    recorded_tool_call_from_dict,
)

__all__ = [
    "RECORDING_VERSION",
    "Recording",
    "RecordingRefusedError",
    "float_text",
    "input_of",
    "instant_of",
    "recording_from_dict",
    "recording_to_dict",
    "setup_digest_of",
]

#: The recording's format version. Independent of `SCHEMA_VERSION` and of
#: `JOURNAL_VERSION`: a recording is a document of its own, and a reader that
#: meets another version refuses it rather than guessing. (ADR 0058 §11)
RECORDING_VERSION = 1

#: `recorded_at`'s one form: a date, a time to the second with up to six
#: digits after it, and the UTC offset written `+00:00`. What Python's
#: `datetime.isoformat()` writes for an instant in UTC, which leaves the
#: fraction out when it is zero. (ADR 0062 §2)
_RECORDED_AT = re.compile(
    r"\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])"
    r"T([01]\d|2[0-3]):[0-5]\d:[0-5]\d(\.\d{1,6})?\+00:00"
)


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
    SHA-256 of its JSON, keys sorted, each float written as text in the form
    `float_text` gives. An episode's digest is made otherwise (ADR 0058 §8)
    and is passed in, not computed here.

    **A float is text in the digest, and only there** (ADR 0062 §2). A writer
    in another language computes this digest too, and two languages write one
    float as different text: Java writes `1.0E-5` and `1.0E16` where Python
    writes `1e-05` and `1e+16`, so the same setup would hash two ways. Strings
    and integers were measured written alike. The setup itself keeps the
    float as a number; what changes is only the text the digest is taken of.
    The cost: a float and the string of its text hash alike, `0.7` and
    `"0.7"`. Accepted, because a model's parameter is sent as a number or as
    a string, and the same setup does not send it both ways.
    """
    payload = json.dumps(
        _floats_as_text(_json_value(dict(setup), "setup")),
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def float_text(value: float) -> str:
    """A float as the digest writes it: the shortest digits that read back as
    the same float, in positional notation, without trailing zeros or a
    trailing point. `0.7` is `"0.7"`, `1e-05` is `"0.00001"`, `100.0` is
    `"100"`, and both zeros are `"0"`.

    Chosen because Java writes the same text from the same double, with
    `new BigDecimal(Double.toString(d)).stripTrailingZeros().toPlainString()`
    and `"0"` for a zero: from JDK 19, `Double.toString` gives the shortest
    digits that read back, as `repr` does here. Measured equal on ten values
    with JDK 21 against Python 3.13, and different on one: the smallest
    subnormal, which Java writes `4.9E-324` and Python `5e-324`. A setup is a
    model's parameters, where that value does not occur.
    """
    if value == 0:
        # `-0.0` is `"0"`: Java's `BigDecimal` has no negative zero.
        return "0"
    return format(Decimal(repr(value)).normalize(), "f")


def _floats_as_text(value: object) -> object:
    """`value`, already JSON, with each float replaced by `float_text`. A
    `bool` is not a float here, nor an `int`."""
    if isinstance(value, float):
        return float_text(value)
    if isinstance(value, dict):
        return {
            key: _floats_as_text(item)
            for key, item in cast(dict[str, object], value).items()
        }
    if isinstance(value, list):
        return [_floats_as_text(item) for item in cast(list[object], value)]
    return value


def instant_of(recorded_at: str) -> str:
    """`recorded_at` as a key that sorts as the instants do, which is how a
    reader compares two. In the one form the texts nearly sort as the
    instants, and not quite: one instant has more than one text, since the
    fraction may have from one to six digits and is left out when it is
    zero, so `08:00:00.100+00:00`, as a writer that keeps milliseconds
    writes it, sorts before `08:00:00.100000+00:00`, as Python writes it.
    The key pads the fraction to six digits, and every value has the one
    offset, so equal instants have equal keys and the order of the keys is
    the order of the instants.

    Text and not a `datetime`, because the core reads no clock and imports
    none of its module (`tests/test_layering.py`). The form is the one
    `Recording` holds a value to, so this reads only what it accepts. A day
    the month does not have, `2026-02-30`, is not refused here."""
    if not _RECORDED_AT.fullmatch(recorded_at):
        raise RecordingRefusedError(
            f"recorded_at {recorded_at[:40]!r} is not in the recording's form: "
            "UTC, written with its offset as +00:00, for example "
            "2026-11-04T08:00:00.123456+00:00"
        )
    seconds, _, fraction = recorded_at[: -len("+00:00")].partition(".")
    return f"{seconds}.{fraction.ljust(6, '0')}"


def input_of(question: object) -> str:
    """The question a recorded answer replies to, as a recorded response's
    `input` holds it: JSON text, keys sorted, compact, non-ASCII kept as it was
    written, the form `record_output` gives a structured answer.

    `question` is a single call's case's `messages`, or an episode's whole case
    (`episode(case=...)`). Not the messages the provider received: the leading
    instructions an OpenAI map moves into the setup are the setup's, and the
    case is what the import groups answers by, so every recording of one
    answer carries one input. Strict as the compartments are, and for the same
    reason: a value JSON cannot carry is refused, not rewritten.
    """
    return json.dumps(
        _json_value(question, "input"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


@dataclass(frozen=True, slots=True)
class Recording:
    """One recorded call, or one episode. (ADR 0058 §3, §4, §7)

    `source_tenant` is the tenant the call was made for, and the directory the
    recording is filed under. `app` is a field and not a directory (§1).
    `suite` is the name the call site gave, or `_unassigned` (§2). `episode` is
    the id of the episode the call belongs to, `None` for a single call made
    outside one (§5), and for an episode the id of the episode it is nested
    in.

    `steps` is `None` on a single call and a tuple on an episode, empty where
    nothing inside it was recorded: its presence is what makes a recording an
    episode. `interrupted` says the application raised inside the episode and
    the recording holds what was seen until then. `unrecorded_children` counts
    the calls made inside the episode that were not recorded, so a trajectory
    with a hole says it has one.

    `orphan` marks a single call recorded in no episode while an episode was
    open in the process that made it: a child whose thread was not attached,
    or a call that belongs to none. It is written when the call is, where that
    is known, because the files alone cannot tell it from a call made while
    nothing was open, and the import says how many it found (§5). A call that
    ended after its episode had closed in the same process — a stream read to
    its end too late, or a call made in a task attached to the episode that
    ran on — is an orphan too, and carries that episode's id: it was the
    episode's, and arrived too late to be one of its steps.
    """

    source_tenant: str
    app: str
    suite: str
    case: Mapping[str, object]
    setup: Mapping[str, object]
    setup_digest: str
    response: RecordedResponse
    episode: str | None = None
    #: `module:function` of the call that named no suite, so a person can
    #: assign it (ADR 0058 §2). `None` where the call named its suite.
    call_site: str | None = None
    steps: tuple[RecordedStep, ...] | None = None
    interrupted: bool = False
    unrecorded_children: int = 0
    orphan: bool = False
    #: An episode's own id: what its children carry in `episode`. `None` on a
    #: single call, and on an episode written before the key existed.
    id: str | None = None
    #: When the recording was written, in UTC with its offset written
    #: `+00:00`, read from the system clock by the host. `None` where nothing
    #: recorded it. Any other form is refused (ADR 0062 §2).
    recorded_at: str | None = None

    def __post_init__(self) -> None:
        for name in ("source_tenant", "app", "suite", "setup_digest"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value:
                raise RecordingRefusedError(
                    f"Recording.{name} must be a non-empty string"
                )
        if self.call_site == "":
            raise RecordingRefusedError(
                "Recording.call_site must be a non-empty string, or None"
            )
        if self.episode == "":
            raise RecordingRefusedError(
                "Recording.episode must be a non-empty string, or None for a "
                "call made outside an episode"
            )
        if self.steps is None:
            if self.interrupted or self.unrecorded_children:
                raise RecordingRefusedError(
                    "only an episode is interrupted or has unrecorded children, "
                    "and a recording without steps is a single call"
                )
        else:
            steps = tuple(self.steps)
            if not all(isinstance(step, RecordedStep) for step in steps):  # pyright: ignore[reportUnnecessaryIsInstance]
                raise RecordingRefusedError(
                    "Recording.steps holds something that is not a RecordedStep"
                )
            if [step.index for step in steps] != list(range(len(steps))):
                raise RecordingRefusedError(
                    "Recording.steps must be indexed 0, 1, 2, ... in order"
                )
            object.__setattr__(self, "steps", steps)
        for name in ("id", "recorded_at"):
            if getattr(self, name) == "":
                raise RecordingRefusedError(
                    f"Recording.{name} must be a non-empty string, or None"
                )
        if self.recorded_at is not None:
            instant_of(self.recorded_at)
        if self.id is not None and self.steps is None:
            raise RecordingRefusedError(
                "only an episode carries an id of its own; a single call "
                "carries the id of its episode in `episode`"
            )
        if type(self.orphan) is not bool:
            raise RecordingRefusedError("Recording.orphan must be a boolean")
        if self.orphan and self.steps is not None:
            raise RecordingRefusedError(
                "only a single call is an orphan, never an episode"
            )
        if type(self.interrupted) is not bool:
            raise RecordingRefusedError("Recording.interrupted must be a boolean")
        if type(self.unrecorded_children) is not int or self.unrecorded_children < 0:
            raise RecordingRefusedError(
                "Recording.unrecorded_children must be an integer from 0"
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
    run document: no `episode` outside an episode."""
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
    if recording.call_site is not None:
        payload["call_site"] = recording.call_site
    if recording.steps is not None:
        payload["steps"] = [recorded_step_to_dict(step) for step in recording.steps]
    if recording.interrupted:
        payload["interrupted"] = True
    if recording.unrecorded_children:
        payload["unrecorded_children"] = recording.unrecorded_children
    if recording.orphan:
        payload["orphan"] = True
    if recording.id is not None:
        payload["id"] = recording.id
    if recording.recorded_at is not None:
        payload["recorded_at"] = recording.recorded_at
    return payload


def _step_from_dict(raw: object, at: int) -> RecordedStep:
    if not isinstance(raw, Mapping):
        raise RecordingRefusedError(f"a recording's step {at} is not an object")
    entry = dict(cast(Mapping[str, Any], raw))
    index = entry.pop("index", None)
    actor = entry.pop("actor", None)
    finish = entry.pop("finish", None)
    if finish is not None and not isinstance(finish, str):
        raise RecordingRefusedError(
            f"a recording's step {at} has a finish that is not text"
        )
    if actor == "tool":
        try:
            call = recorded_tool_call_from_dict(entry)
        except ValueError as exc:
            raise RecordingRefusedError(
                Written.of(exc, f"a recording's step {at}: ", named=False)
            ) from exc
        return _step(at, cast(int, index), "tool", finish, call)
    if entry:
        raise RecordingRefusedError(
            f"a recording's step {at} is a model step and carries a tool call's keys"
        )
    return _step(at, cast(int, index), cast(Actor, actor), finish, None)


def _step(
    at: int,
    index: int,
    actor: Actor,
    finish: str | None,
    call: RecordedToolCall | None,
) -> RecordedStep:
    """A step read from a recording, refused as a recording is: the step's
    own rules are the run document's, since it moved there (ADR 0060 §5)."""
    try:
        return RecordedStep(index=index, actor=actor, finish=finish, call=call)
    except RefusedError as exc:
        raise RecordingRefusedError(
            Written.of(exc, f"a recording's step {at}: ", named=False)
        ) from exc


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
            call_site=_optional_text(document, "call_site"),
            steps=_steps(document),
            interrupted=_flag(document, "interrupted"),
            unrecorded_children=_count(document, "unrecorded_children"),
            orphan=_flag(document, "orphan"),
            id=_optional_text(document, "id"),
            recorded_at=_optional_text(document, "recorded_at"),
        )
    except RecordingRefusedError:
        raise
    except ValueError as exc:
        # The response compartment's own reader wrote this sentence; it is
        # handed over as written, after where it was found. (ADR 0043 §2)
        raise RecordingRefusedError(
            Written.of(exc, f"{where}, response: ", named=False)
        ) from exc


def _steps(document: Mapping[str, Any]) -> tuple[RecordedStep, ...] | None:
    if "steps" not in document:
        return None
    raw = document["steps"]
    if not isinstance(raw, list):
        raise RecordingRefusedError("a recording's 'steps' is not a list")
    return tuple(
        _step_from_dict(entry, at) for at, entry in enumerate(cast(list[object], raw))
    )


def _flag(document: Mapping[str, Any], key: str) -> bool:
    """Absent is `False`, and only `true` is written: a document that says
    `false` or `null` is refused, because no writer writes either."""
    if key not in document:
        return False
    if document[key] is not True:
        raise RecordingRefusedError(
            f"a recording's {key!r} is written as true or not at all"
        )
    return True


def _count(document: Mapping[str, Any], key: str) -> int:
    if key not in document:
        return 0
    value = document[key]
    if type(value) is not int or value < 1:
        raise RecordingRefusedError(
            f"a recording's {key!r} is written as a positive integer or not at all"
        )
    return value


def _text(document: Mapping[str, Any], key: str) -> str:
    value = document.get(key)
    if not isinstance(value, str):
        raise RecordingRefusedError(f"a recording's {key!r} is not a string")
    return value


def _optional_text(document: Mapping[str, Any], key: str) -> str | None:
    if key not in document:
        return None
    return _text(document, key)
