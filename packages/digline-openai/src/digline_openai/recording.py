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
and token parameters, `tools`, `tool_choice`, `response_format`, `extra_body`.
Neither is how the request travels (`extra_headers`, `extra_query`,
`timeout`), streaming (`stream`, `stream_options`), or who the request is for
(`user`, `metadata`, `safety_identifier`, `prompt_cache_key`), nor `store`.

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
from typing import Any, cast

from digline.targets import Completion, Pricing
from digline_openai.client import completion_of

__all__ = [
    "INSTRUCTION_ROLES",
    "MAP",
    "NOT_SETUP",
    "STREAM_MAP",
    "WIRE",
    "OpenAIRecording",
    "OpenAIWire",
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

#: The roles of the leading messages that are the setup's `system`.
INSTRUCTION_ROLES: frozenset[str] = frozenset({"system", "developer"})

_NO_PRICES = Pricing(per_model={})


def _role(message: object) -> object:
    if isinstance(message, Mapping):
        return cast(Mapping[str, object], message).get("role")
    return getattr(message, "role", None)


class OpenAIRecording:
    """The map digline's recorder loads for `openai.OpenAI`."""

    def split(
        self, request: Mapping[str, Any]
    ) -> tuple[dict[str, object], dict[str, object]]:
        messages = request.get("messages")
        listed: list[object] = (
            list(cast(Sequence[object], messages))
            if isinstance(messages, Sequence) and not isinstance(messages, str)
            else [messages]
        )
        lead = 0
        while lead < len(listed) and _role(listed[lead]) in INSTRUCTION_ROLES:
            lead += 1
        setup = {key: value for key, value in request.items() if key not in NOT_SETUP}
        if lead:
            setup["system"] = listed[:lead]
        return {"messages": listed[lead:]}, setup

    def completion(self, reply: Any, request: Mapping[str, Any]) -> Completion:
        return completion_of(reply, str(request.get("model", "")), _NO_PRICES)

    def reading(self, request: Mapping[str, Any]) -> Any:
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

    def reading(self, request: Mapping[str, Any]) -> Any:
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


WIRE = OpenAIWire()
