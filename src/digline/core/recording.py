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
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal, cast

from digline.core.aggregate import Label
from digline.core.refused import RefusedError, Written
from digline.core.run import (
    RecordedResponse,
    RecordedToolCall,
    record_trajectory,
    recorded_response_from_dict,
    recorded_response_to_dict,
    recorded_tool_call_from_dict,
    recorded_tool_call_to_dict,
)

__all__ = [
    "RECORDING_VERSION",
    "RecordedStep",
    "Recording",
    "RecordingRefusedError",
    "recording_from_dict",
    "input_of",
    "recording_to_dict",
    "setup_digest_of",
    "steps_as_reported",
    "steps_of",
]

#: The recording's format version. Independent of `SCHEMA_VERSION` and of
#: `JOURNAL_VERSION`: a recording is a document of its own, and a reader that
#: meets another version refuses it rather than guessing. (ADR 0058 §11)
RECORDING_VERSION = 1

_LABELS: frozenset[str] = frozenset({"positive", "negative"})

#: Who acted in a step. `engine`, declared by hand, is a later release's
#: (ADR 0058 §9); 1.1 produces these two.
type Actor = Literal["model", "tool"]
_ACTORS: frozenset[str] = frozenset({"model", "tool"})


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
class RecordedStep:
    """One step of an episode's trajectory. (ADR 0058 §7, §9)

    `index` is the step's place in the episode, from 0, for the order
    assertions planned after 1.1 will read. A `model` step is one call to a
    model and carries the `finish` its reply reported, `None` where the plugin
    reported none; a `tool` step is one tool call the model asked for, carries
    it as `call`, and never a finish, because a tool does not end a reply.

    **Here and not in `digline.core.run`**, beside `RecordedToolCall`, because
    the run document does not hold steps: they enter it when assertions read
    them live (ADR 0058, *Alternatives considered*). A tool step's call is
    written by the run document's own serializer of a tool call, inline in the
    step, so a call has one written form wherever it is kept.

    `finish` is the text the plugin gave, not checked against `Finish`'s
    words: a finish nobody normalised is carried as given (ADR 0058 §12).
    """

    index: int
    actor: Actor
    finish: str | None = None
    call: RecordedToolCall | None = None

    def __post_init__(self) -> None:
        # `bool` is an `int` in Python, and `True` is not a place in a list.
        if type(self.index) is not int or self.index < 0:
            raise RecordingRefusedError("RecordedStep.index must be an integer from 0")
        if self.actor not in _ACTORS:
            raise RecordingRefusedError(
                f"RecordedStep.actor must be 'model' or 'tool', got "
                f"{str(self.actor)[:40]!r}"
            )
        if self.actor == "model" and self.call is not None:
            raise RecordingRefusedError(
                "a model step carries no tool call: the call the model asked "
                "for is the tool step after it"
            )
        if self.actor == "tool":
            if self.call is None:
                raise RecordingRefusedError("a tool step carries its call")
            if self.finish is not None:
                raise RecordingRefusedError(
                    "a tool step carries no finish: a tool does not end a reply "
                    "(ADR 0058 §7)"
                )
        if self.finish == "":
            raise RecordingRefusedError(
                "RecordedStep.finish must be a non-empty string, or None where "
                "none was reported"
            )


def steps_of(
    calls: Iterable[tuple[str | None, Sequence[RecordedToolCall] | None]],
) -> tuple[RecordedStep, ...]:
    """The steps of a trajectory, from its calls to a model, in order.
    (ADR 0060 §1)

    Each call is the `finish` its reply reported and the tool calls it asked
    for. It becomes one `model` step with that finish, then one `tool` step
    per tool call, indexed from 0 across the whole trajectory. A call whose
    tool calls are `None`, nobody said, is its model step alone.

    The one place steps are made: a reply's metadata, a run's collection and
    the close of an episode all come here, so the three cannot order a
    trajectory three ways.
    """
    steps: list[RecordedStep] = []
    for finish, called in calls:
        steps.append(RecordedStep(index=len(steps), actor="model", finish=finish))
        for call in called or ():
            steps.append(RecordedStep(index=len(steps), actor="tool", call=call))
    return tuple(steps)


def steps_as_reported(
    calls: Sequence[tuple[str | None, Sequence[Mapping[str, object]] | None]],
) -> list[dict[str, object]] | None:
    """The steps as `metadata["response"]["steps"]` holds them, or `None`.
    (ADR 0060 §1, §2)

    Each call is its `finish` and its tool calls in the form
    `metadata["response"]["tool_calls"]` already uses. `steps_of` decides the
    order and the indices; each tool step then carries its call in that live
    form, inline beside `index` and `actor`, so a reader finds the same call
    the same way in both keys.

    `None` where any call's tool calls are `None`: steps that left a call's
    tools out would say it called none, so a check that counts tool steps
    would pass on what nobody reported. The calls are read by
    `record_trajectory`, the run document's own reader, and a malformed one is
    refused there rather than skipped.
    """
    recorded: list[tuple[str | None, Sequence[RecordedToolCall]]] = []
    live: list[Mapping[str, object]] = []
    for finish, called in calls:
        if called is None:
            return None
        recorded.append((finish, record_trajectory({"tool_calls": called}) or ()))
        live.extend(called)
    reported: list[dict[str, object]] = []
    at = iter(live)
    for step in steps_of(recorded):
        entry: dict[str, object] = {"index": step.index, "actor": step.actor}
        if step.actor == "tool":
            entry.update(next(at))
        elif step.finish is not None:
            entry["finish"] = step.finish
        reported.append(entry)
    return reported


@dataclass(frozen=True, slots=True)
class Recording:
    """One recorded call, or one episode. (ADR 0058 §3, §4, §7)

    `source_tenant` is the tenant the call was made for, and the directory the
    recording is filed under. `app` is a field and not a directory (§1).
    `suite` is the name the call site gave, or `_unassigned` (§2). `episode` is
    the id of the episode the call belongs to, `None` for a single call made
    outside one (§5), and for an episode the id of the episode it is nested
    in. `label` is `Case.label` before the case exists, empty until a person
    gives one (§7).

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
    label: Label | None = None
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
    #: When the recording was written, ISO 8601 with its offset, read from the
    #: system clock by the host. `None` where nothing recorded it.
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
        if self.label is not None and self.label not in _LABELS:
            raise RecordingRefusedError(
                f"Recording.label must be 'positive', 'negative' or None, got "
                f"{self.label!r}"
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
    if recording.call_site is not None:
        payload["call_site"] = recording.call_site
    if recording.steps is not None:
        payload["steps"] = [_step_to_dict(step) for step in recording.steps]
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


def _step_to_dict(step: RecordedStep) -> dict[str, object]:
    """`index` and `actor`, then a model step's finish where one was reported,
    or a tool step's call as a run document writes one, inline."""
    payload: dict[str, object] = {"index": step.index, "actor": step.actor}
    if step.finish is not None:
        payload["finish"] = step.finish
    if step.call is not None:
        payload.update(recorded_tool_call_to_dict(step.call))
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
        return RecordedStep(
            index=cast(int, index), actor="tool", finish=finish, call=call
        )
    if entry:
        raise RecordingRefusedError(
            f"a recording's step {at} is a model step and carries a tool call's keys"
        )
    return RecordedStep(index=cast(int, index), actor=cast(Actor, actor), finish=finish)


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
