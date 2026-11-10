"""How the recorder reads a call made through `anthropic.Anthropic`.
(ADR 0058 §3, §6)

Declared under `digline.recording_maps` as `anthropic.Anthropic:messages.create`
and loaded only when a call is recorded.

**The case is the messages.** The setup is everything else the call decides
with: `model`, `system`, `max_tokens`, the sampling parameters, `tools` and
`tool_choice`, `thinking`, and the keys of `extra_body`, merged at the top
level as the SDK sends them (`as_sent`). Neither is a credential the body
carries, an MCP server's `authorization_token`, which is left out of its
server's entry; how the request travels
(`extra_headers`, `extra_query`, `timeout`), `stream`, or `metadata`, which
names who the request is for: a per-request identifier in the setup would give
every user a setup of their own, and the digest would read people as changes.

**The reply is read by `completion_of`**, the function the target already uses,
so a recorded reply and a measured one are read the same way.

**A streamed reply is read from its events** (ADR 0058 §13), into the message
the whole reply would have been, and then by `completion_of` like any other:
- `messages.create(stream=True)` gives the raw events, accumulated with the
  SDK's own `accumulate_event`, the function its `MessageStream` uses. It is
  imported from `anthropic.lib.streaming._messages`, a module the SDK does not
  export by name: if it moves, the reading fails and the call counts `map`,
  and the application's stream is not touched;
- `messages.stream()` is another method, declared under its own entry point,
  `anthropic.Anthropic:messages.stream`. It returns a manager, and the stream
  its `with` gives accumulates itself: its final message is read when it ends.

**The SDK's own objects in a request are recorded as the SDK sends them.**
An agent that hands a reply back as it came, `reply.content` in the next
call's messages, passes pydantic models where a recording holds data. The SDK
sends each as `openapi_model_dump` does: `model_dump(exclude_unset=True,
mode="json", by_alias=True)`, less the fields it names in `__api_exclude__`;
the map writes the same, so the case is the call off the wire, and the
model's step is recorded. A value that is still not data after that is
declined by `refusal`, with its type and the key it sits at, not counted as
*not JSON*.

**Off the wire** (ADR 0062 §3), `WIRE` is what `digline record proxy` reads a
Messages call with, declared under `digline.recording_wire` as `anthropic`.
The reply's JSON, and each streamed event's, become the SDK's own types the
way the SDK builds them from a response, `construct_type`, and `MAP` reads
them as it reads a call made through the client.
"""

from __future__ import annotations

import importlib
import inspect
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any, cast

from digline.targets import Completion, ToolCall
from digline_anthropic.client import completion_of

if TYPE_CHECKING:
    from digline.recorder import StreamReading

__all__ = [
    "MAP",
    "NOT_SETUP",
    "STREAM_MAP",
    "WIRE",
    "AnthropicRecording",
    "AnthropicWire",
    "as_sent",
]

#: The keywords of `messages.create` that are neither the case nor the setup,
#: beside the messages themselves.
NOT_SETUP: frozenset[str] = frozenset(
    {"messages", "stream", "extra_headers", "extra_query", "timeout", "metadata"}
)

#: The keys of a Messages request body that carry a credential, by where they
#: sit: an MCP server's `authorization_token`, the bearer token Anthropic
#: forwards to that server. A credential is the one payload no `Disclosure`
#: releases (ADR 0004 §5), and in a setup it would also enter the digest, so
#: each rotation of the token would read as a new setup.
_CREDENTIAL_KEYS: frozenset[str] = frozenset({"authorization_token"})


def _without_credentials(servers: object) -> object:
    """`mcp_servers` with each server's credential left out, and everything
    else as it was sent: which servers, at which address, with which tools.
    A value that is not a list of mappings is left as it is."""
    if not isinstance(servers, list):
        return servers
    kept: list[object] = []
    for server in cast(list[object], servers):
        if isinstance(server, Mapping):
            entry = cast(Mapping[str, object], server)
            kept.append(
                {
                    key: value
                    for key, value in entry.items()
                    if key not in _CREDENTIAL_KEYS
                }
            )
        else:
            kept.append(server)
    return kept


def as_sent(request: Mapping[str, Any]) -> dict[str, Any]:
    """The request as it travels: `extra_body`'s keys merged into the body at
    its top level, as the SDK merges them, and `extra_body` itself gone. So a
    call recorded in process and the same call read off the wire, by `digline
    record proxy` or by a recorder in another language, have one setup and one
    digest (ADR 0062 §2)."""
    extra = request.get("extra_body")
    sent = {key: value for key, value in request.items() if key != "extra_body"}
    if isinstance(extra, Mapping):
        sent.update(cast(Mapping[str, Any], extra))
    return sent


def as_data(value: Any) -> Any:
    """`value` with every pydantic model in it dumped as the SDK dumps one in
    a request body (its `openapi_model_dump`), mappings and lists walked, and
    anything else left as it is, for `refusal` to name. A model is the SDK's
    own reply handed back; a date or a set is the application's value, and a
    recording does not rewrite it (`tests/test_recorder.py`)."""
    import pydantic

    if isinstance(value, pydantic.BaseModel):
        try:
            dumped = value.model_dump(
                exclude_unset=True,
                mode="json",
                by_alias=True,
                exclude=getattr(value, "__api_exclude__", None),
            )
        except Exception as exc:  # noqa: BLE001 — named where it sits, by `refusal`
            return _Undumped(
                f"{type(value).__name__} whose dump raised {type(exc).__name__}"
            )
        return as_data(dumped)
    if isinstance(value, Mapping):
        return {
            key: as_data(item) for key, item in cast(Mapping[Any, Any], value).items()
        }
    if isinstance(value, (list, tuple)):
        return [as_data(item) for item in cast(Sequence[Any], value)]
    return value


class _Undumped:
    """A model whose dump raised, left where it was for `refusal` to name."""

    def __init__(self, kind: str) -> None:
        self.kind = kind


#: What a recording holds as data, beside mappings with text keys and lists.
_DATA = (str, int, float, bool, type(None))


def _not_data(value: Any, where: str) -> tuple[str, str] | None:
    """The first place in `value` that is not data, and the type found
    there, or `None`."""
    if isinstance(value, Mapping):
        for key, item in cast(Mapping[Any, Any], value).items():
            if not isinstance(key, str):
                return where, f"key of type {type(key).__name__}"
            found = _not_data(item, f"{where}.{key}" if where else key)
            if found is not None:
                return found
        return None
    if isinstance(value, list):
        for index, item in enumerate(cast(list[Any], value)):
            found = _not_data(item, f"{where}[{index}]")
            if found is not None:
                return found
        return None
    if isinstance(value, _DATA):
        return None
    if isinstance(value, _Undumped):
        return where, value.kind
    return where, type(value).__name__


class AnthropicRecording:
    """The map digline's recorder loads for `anthropic.Anthropic`."""

    def split(
        self, request: Mapping[str, Any]
    ) -> tuple[dict[str, object], dict[str, object]]:
        request = as_sent(request)
        case: dict[str, object] = {"messages": as_data(request.get("messages"))}
        setup = {
            key: as_data(value)
            for key, value in request.items()
            if key not in NOT_SETUP
        }
        if "mcp_servers" in setup:
            setup["mcp_servers"] = _without_credentials(setup["mcp_servers"])
        return case, setup

    def refusal(self, request: Mapping[str, Any]) -> Any:
        """A call whose recorded part holds something that is not data once
        the SDK's models are dumped: declined, and said by the key it sits at
        and the type found there. `None` for a call that is all data."""
        from digline.recorder import Refusal

        case, setup = self.split(request)
        found = _not_data({**case, **setup}, "")
        if found is None:
            return None
        where, kind = found
        return Refusal(
            reason=f"{where} holds a {kind}",
            family=f"anthropic {where} {kind}",
            said=(
                f"messages.create: {where} holds a {kind}, which a recording "
                "cannot hold as data; the call was made, and not recorded"
            ),
        )

    def completion(self, reply: Any, request: Mapping[str, Any]) -> Completion:
        return completion_of(reply)

    def reading(self, request: Mapping[str, Any]) -> StreamReading:
        """A reading of `messages.create(stream=True)`'s raw events."""
        return _Events()


class _Events:
    """The raw events of one stream, folded into the message they make."""

    def __init__(self) -> None:
        from anthropic.lib.streaming._messages import accumulate_event

        self._accumulate = accumulate_event
        self._snapshot: Any = None
        self._json: dict[int, bytes] = {}

    def add(self, event: Any) -> None:
        self._snapshot = self._accumulate(
            event=event, current_snapshot=self._snapshot, json_bufs=self._json
        )

    def completion(self, stream: Any) -> Completion:
        if self._snapshot is None:
            raise ValueError("the stream ended with no message")
        return completion_of(self._snapshot)


class AnthropicStreamRecording(AnthropicRecording):
    """The map for `messages.stream()`: the same request, a manager for a
    reply, and a stream that keeps its own message."""

    #: The stream is what the manager's `with` gives.
    entered = True

    def streams(self, request: Mapping[str, Any]) -> bool:
        return True

    def reading(self, request: Mapping[str, Any]) -> StreamReading:
        return _Final()


class _Final:
    """Reads the message a `MessageStream` accumulated itself. On an
    `AsyncMessageStream`, `get_final_message()` is a coroutine, and so is
    what this returns: the recorder awaits it."""

    def add(self, event: Any) -> None:
        return None

    def completion(self, stream: Any) -> Any:
        final = stream.get_final_message()
        if inspect.isawaitable(final):
            return _later(final)
        return completion_of(final)


async def _later(final: Any) -> Completion:
    return completion_of(await final)


MAP = AnthropicRecording()
STREAM_MAP = AnthropicStreamRecording()


class AnthropicWire:
    """Messages off the wire, for `digline record proxy`."""

    map = MAP
    #: `ANTHROPIC_BASE_URL` is the host: the SDK adds `/v1/messages` itself.
    base = ""
    upstream = "https://api.anthropic.com"

    def matches(self, path: str) -> bool:
        return path.partition("?")[0].rstrip("/").endswith("/v1/messages")

    def claims(self, headers: Mapping[str, str]) -> bool:
        """`anthropic-version`, which the SDK sends on every call, or
        `x-api-key`. Not the key's header alone: the SDK sends its key as
        `Authorization: Bearer`, as OpenAI's does (read in the SDK's
        `_client.py`, and measured through the proxy)."""
        return "anthropic-version" in headers or "x-api-key" in headers

    def reply(self, raw: object) -> Any:
        from anthropic._models import construct_type
        from anthropic.types import Message

        return construct_type(type_=Message, value=raw)

    def event(self, raw: object) -> Any:
        from anthropic._models import construct_type
        from anthropic.types import RawMessageStreamEvent

        return construct_type(type_=RawMessageStreamEvent, value=raw)

    def load(self) -> None:
        # The streaming module first: two threads importing it for the first
        # time at once were measured to fail on a circular import.
        for name in ("anthropic.lib.streaming._messages", "anthropic._models"):
            importlib.import_module(name)

    def results(self, request: Mapping[str, Any]) -> Sequence[ToolCall] | None:
        """The `tool_result` blocks after the last assistant message that
        asked for tools, in the order it asked. `is_error` is the status where
        the application set it, `not_reported` where it did not."""
        messages = _mappings(request.get("messages"))
        asked: list[Mapping[str, Any]] = []
        at = -1
        for index, message in enumerate(messages):
            if message.get("role") == "assistant":
                uses = [
                    block
                    for block in _mappings(message.get("content"))
                    if block.get("type") == "tool_use"
                ]
                if uses:
                    asked, at = uses, index
        if at < 0:
            return None
        given: dict[str, Mapping[str, Any]] = {
            str(block.get("tool_use_id")): block
            for message in messages[at + 1 :]
            for block in _mappings(message.get("content"))
            if block.get("type") == "tool_result"
        }
        if not given:
            return None
        return tuple(_result(use, given.get(str(use.get("id")))) for use in asked)


def _mappings(value: object) -> list[Mapping[str, Any]]:
    """The objects in a JSON list, in order; nothing where it is not one."""
    if not isinstance(value, list):
        return []
    items = cast(list[object], value)
    return [
        cast(Mapping[str, Any], item) for item in items if isinstance(item, Mapping)
    ]


def _result(use: Mapping[str, Any], result: Mapping[str, Any] | None) -> ToolCall:
    name = use.get("name") or None
    arguments = cast(Mapping[str, object] | None, use.get("input"))
    if result is None:
        return ToolCall(
            tool=name,
            arguments=arguments,
            status="not_reported",
            result_absence="not_reported",
        )
    said = result.get("is_error")
    status = "error" if said is True else "success" if said is False else "not_reported"
    content = result.get("content")
    if content is None or isinstance(content, str):
        return ToolCall(
            tool=name, arguments=arguments, status=status, result=content or ""
        )
    parts: list[str] = []
    for block in _mappings(content):
        if block.get("type") != "text" or not isinstance(block.get("text"), str):
            # An image or a document: bulk, never copied into a step.
            return ToolCall(
                tool=name,
                arguments=arguments,
                status=status,
                result_absence="not_recorded",
            )
        parts.append(block["text"])
    return ToolCall(
        tool=name, arguments=arguments, status=status, result="".join(parts)
    )


WIRE = AnthropicWire()
