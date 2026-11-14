"""How the recorder reads a call made through `openai.OpenAI`.
(ADR 0058 §3, §6)

Declared under `digline.recording_maps` as
`openai.OpenAI:chat.completions.create` and loaded only when a call is
recorded.

**The case is the messages, less the instructions that lead them.** Chat
Completions carries the system prompt inside `messages`, as a leading
`system` or `developer` message. Those leading messages are the setup's
`system`, as Anthropic's `system=` is: they are what the prompt *is*, and a
case that held them would change every time the prompt did. Every message
after the first one of another role is the case.

**The setup** is everything else the call decides with: `model`, the sampling
and token parameters, `tools`, `tool_choice`, `response_format`, and the keys
of `extra_body`, merged at the top level as the SDK sends them (`as_sent`).
Neither is how the request travels (`extra_headers`, `extra_query`,
`timeout`), streaming (`stream`, `stream_options`), or who the request is for
(`user`, `metadata`, `safety_identifier`, `prompt_cache_key`), nor `store`.
Nor is a credential the body carries, by the names digline-anthropic leaves
out (`CREDENTIAL_KEYS`): at the top level, where `extra_body` merges, and in
each entry of an `mcp_servers` list, which an endpoint in OpenAI's shape may
take through `extra_body`. No credential field of Chat Completions' own body
is known; the list is the one GHSA-v7r8-xg2j-wjx4 named for Anthropic.

**The reply is read by `completion_of`**, the function `OpenAIChat.complete`
returns. A recording does not price: the price list passed is empty, so a reply
without usage is recorded as *not recorded*, never as zero.

**A streamed reply is read from its chunks** (ADR 0058 §13), with the SDK's
own `ChatCompletionStreamState`, into the completion the whole reply would
have been:
- `chat.completions.create(stream=True)`. Its usage arrives only where the
  application asked for it, with `stream_options={"include_usage": True}`;
  the recorder never asks in its place, because it does not alter the
  request. Without it the reply is recorded with no counts, and the recorder
  notes `usage not reported`;
- `chat.completions.stream()`, another method, declared under its own entry
  point, `openai.OpenAI:chat.completions.stream`. It returns a manager, and
  the stream its `with` gives keeps its own completion, read when it ends.

**Off the wire** (ADR 0062 §3), `WIRE` is what `digline record proxy` reads a
Chat Completions call with, declared under `digline.recording_wire` as
`openai`. The reply's JSON, and each streamed chunk's, become the SDK's own
types the way the SDK builds them from a response, `construct_type`, and
`MAP` reads them as it reads a call made through the client. So a call reads
the same through either door, and an endpoint that answers in OpenAI's shape
is read the way the SDK would read it.
"""

from __future__ import annotations

import importlib
import inspect
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any, cast

from digline.targets import Completion, Pricing, ToolCall
from digline_openai.client import completion_of

if TYPE_CHECKING:
    from digline.recorder import StreamReading

__all__ = [
    "INSTRUCTION_ROLES",
    "MAP",
    "CREDENTIAL_KEYS",
    "NOT_SETUP",
    "STREAM_MAP",
    "WIRE",
    "OpenAIRecording",
    "OpenAIWire",
    "as_sent",
]

#: The keywords of `chat.completions.create` that are neither the case nor the
#: setup, beside the messages themselves.
NOT_SETUP: frozenset[str] = frozenset(
    {
        "messages",
        "stream",
        "stream_options",
        "extra_headers",
        "extra_query",
        "timeout",
        "user",
        "metadata",
        "safety_identifier",
        "prompt_cache_key",
        "store",
    }
)

#: The keys of a request body that carry a credential, the list
#: digline-anthropic leaves out (GHSA-v7r8-xg2j-wjx4): an MCP server's
#: `authorization_token`. A credential is the one payload no `Disclosure`
#: releases (ADR 0004 §5), and in a setup it would also enter the digest, so
#: each rotation of the token would read as a new setup.
CREDENTIAL_KEYS: frozenset[str] = frozenset({"authorization_token"})


def _without_credentials(servers: object) -> object:
    """`mcp_servers` with each server's credential left out, and everything
    else as it was sent. A value that is not a list of mappings is left as it
    is, as digline-anthropic leaves it."""
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
                    if key not in CREDENTIAL_KEYS
                }
            )
        else:
            kept.append(server)
    return kept


#: The roles of the leading messages that are the setup's `system`.
INSTRUCTION_ROLES: frozenset[str] = frozenset({"system", "developer"})

_NO_PRICES = Pricing(per_model={})


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


def _role(message: object) -> object:
    if isinstance(message, Mapping):
        return cast(Mapping[str, object], message).get("role")
    return getattr(message, "role", None)


class OpenAIRecording:
    """The map digline's recorder loads for `openai.OpenAI`."""

    def split(
        self, request: Mapping[str, Any]
    ) -> tuple[dict[str, object], dict[str, object]]:
        request = as_sent(request)
        messages = request.get("messages")
        listed: list[object] = (
            list(cast(Sequence[object], messages))
            if isinstance(messages, Sequence) and not isinstance(messages, str)
            else [messages]
        )
        lead = 0
        while lead < len(listed) and _role(listed[lead]) in INSTRUCTION_ROLES:
            lead += 1
        setup = {
            key: value
            for key, value in request.items()
            if key not in NOT_SETUP and key not in CREDENTIAL_KEYS
        }
        if "mcp_servers" in setup:
            setup["mcp_servers"] = _without_credentials(setup["mcp_servers"])
        if lead:
            setup["system"] = listed[:lead]
        return {"messages": listed[lead:]}, setup

    def completion(self, reply: Any, request: Mapping[str, Any]) -> Completion:
        return completion_of(reply, str(request.get("model", "")), _NO_PRICES)

    def reading(self, request: Mapping[str, Any]) -> StreamReading:
        """A reading of `chat.completions.create(stream=True)`'s chunks."""
        return _Chunks(request)


class _Chunks:
    """The chunks of one stream, folded into the completion they make."""

    def __init__(self, request: Mapping[str, Any]) -> None:
        from openai.lib.streaming.chat import ChatCompletionStreamState

        tools = request.get("tools")
        self._state: Any = (
            ChatCompletionStreamState(input_tools=tools)
            if tools is not None
            else ChatCompletionStreamState()
        )
        self._model = str(request.get("model", ""))

    def add(self, event: Any) -> None:
        self._state.handle_chunk(event)

    def completion(self, stream: Any) -> Completion:
        return completion_of(
            self._state.get_final_completion(), self._model, _NO_PRICES
        )


class OpenAIStreamRecording(OpenAIRecording):
    """The map for `chat.completions.stream()`: the same request, a manager
    for a reply, and a stream that keeps its own completion."""

    #: The stream is what the manager's `with` gives.
    entered = True

    def streams(self, request: Mapping[str, Any]) -> bool:
        return True

    def reading(self, request: Mapping[str, Any]) -> StreamReading:
        return _Final(str(request.get("model", "")))


class _Final:
    """Reads the completion a `ChatCompletionStream` accumulated itself."""

    def __init__(self, model: str) -> None:
        self._model = model

    def add(self, event: Any) -> None:
        return None

    def completion(self, stream: Any) -> Any:
        """On an `AsyncChatCompletionStream`, `get_final_completion()` is a
        coroutine, and so is what this returns: the recorder awaits it."""
        final = stream.get_final_completion()
        if inspect.isawaitable(final):
            return _later(final, self._model)
        return completion_of(final, self._model, _NO_PRICES)


async def _later(final: Any, model: str) -> Completion:
    return completion_of(await final, model, _NO_PRICES)


MAP = OpenAIRecording()
STREAM_MAP = OpenAIStreamRecording()


class OpenAIWire:
    """Chat Completions off the wire, for `digline record proxy`."""

    map = MAP
    #: `OPENAI_BASE_URL` ends in `/v1`, and so does the default upstream.
    base = "/v1"
    upstream = "https://api.openai.com/v1"

    def matches(self, path: str) -> bool:
        return path.partition("?")[0].rstrip("/").endswith("/chat/completions")

    def claims(self, headers: Mapping[str, str]) -> bool:
        """A bearer key on a call that is not Anthropic's: Anthropic's SDK
        sends its key as a bearer too, beside `anthropic-version`."""
        bearer = headers.get("authorization", "").lower().startswith("bearer ")
        return bearer and "anthropic-version" not in headers

    def reply(self, raw: object) -> Any:
        from openai._models import construct_type
        from openai.types.chat import ChatCompletion

        return construct_type(type_=ChatCompletion, value=raw)

    def event(self, raw: object) -> Any:
        from openai._models import construct_type
        from openai.types.chat import ChatCompletionChunk

        return construct_type(type_=ChatCompletionChunk, value=raw)

    def load(self) -> None:
        for name in ("openai._models", "openai.lib.streaming.chat"):
            importlib.import_module(name)

    def results(self, request: Mapping[str, Any]) -> Sequence[ToolCall] | None:
        """The `tool` messages after the last assistant message that asked
        for tools, in the order it asked. Chat Completions carries no word
        for a tool that failed, so each result's status is `not_reported`."""
        messages = _mappings(request.get("messages"))
        asked: list[Mapping[str, Any]] = []
        at = -1
        for index, message in enumerate(messages):
            if message.get("role") == "assistant":
                calls = _mappings(message.get("tool_calls"))
                if calls:
                    asked, at = calls, index
        if at < 0:
            return None
        given: dict[str, Mapping[str, Any]] = {
            str(message.get("tool_call_id")): message
            for message in messages[at + 1 :]
            if message.get("role") == "tool"
        }
        if not given:
            return None
        return tuple(_result(call, given.get(str(call.get("id")))) for call in asked)


def _mappings(value: object) -> list[Mapping[str, Any]]:
    """The objects in a JSON list, in order; nothing where it is not one."""
    if not isinstance(value, list):
        return []
    items = cast(list[object], value)
    return [
        cast(Mapping[str, Any], item) for item in items if isinstance(item, Mapping)
    ]


def _result(call: Mapping[str, Any], message: Mapping[str, Any] | None) -> ToolCall:
    functions = _mappings([call.get("function")])
    named: Mapping[str, Any] = functions[0] if functions else {}
    name = cast(str | None, named.get("name") or None)
    arguments = cast(str | None, named.get("arguments"))
    if message is None:
        return ToolCall(
            tool=name,
            arguments=arguments,
            status="not_reported",
            result_absence="not_reported",
        )
    content = message.get("content")
    if content is None or isinstance(content, str):
        return ToolCall(
            tool=name, arguments=arguments, status="not_reported", result=content or ""
        )
    parts: list[str] = []
    for part in _mappings(content):
        if part.get("type") != "text":
            # An image or a file: bulk, never copied into a step.
            return ToolCall(
                tool=name,
                arguments=arguments,
                status="not_reported",
                result_absence="not_recorded",
            )
        parts.append(str(part.get("text", "")))
    return ToolCall(
        tool=name, arguments=arguments, status="not_reported", result="".join(parts)
    )


WIRE = OpenAIWire()
