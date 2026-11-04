"""How the recorder reads a call made through `anthropic.Anthropic`.
(ADR 0058 §3, §6)

Declared under `digline.recording_maps` as `anthropic.Anthropic:messages.create`
and loaded only when a call is recorded.

**The case is the messages.** The setup is everything else the call decides
with: `model`, `system`, `max_tokens`, the sampling parameters, `tools` and
`tool_choice`, `thinking`, `extra_body`. Neither is how the request travels
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
"""

from __future__ import annotations

import inspect
from collections.abc import Mapping
from typing import Any

from digline.targets import Completion
from digline_anthropic.client import completion_of

__all__ = ["MAP", "NOT_SETUP", "STREAM_MAP", "AnthropicRecording"]

#: The keywords of `messages.create` that are neither the case nor the setup,
#: beside the messages themselves.
NOT_SETUP: frozenset[str] = frozenset(
    {"messages", "stream", "extra_headers", "extra_query", "timeout", "metadata"}
)


class AnthropicRecording:
    """The map digline's recorder loads for `anthropic.Anthropic`."""

    def split(
        self, request: Mapping[str, Any]
    ) -> tuple[dict[str, object], dict[str, object]]:
        case: dict[str, object] = {"messages": request.get("messages")}
        setup = {key: value for key, value in request.items() if key not in NOT_SETUP}
        return case, setup

    def completion(self, reply: Any, request: Mapping[str, Any]) -> Completion:
        return completion_of(reply)

    def reading(self, request: Mapping[str, Any]) -> Any:
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

    def reading(self, request: Mapping[str, Any]) -> Any:
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
