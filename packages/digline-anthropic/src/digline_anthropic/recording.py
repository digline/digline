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
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from digline.targets import Completion
from digline_anthropic.client import completion_of

__all__ = ["MAP", "NOT_SETUP", "AnthropicRecording"]

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


MAP = AnthropicRecording()
