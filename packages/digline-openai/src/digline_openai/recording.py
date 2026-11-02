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
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, cast

from digline.targets import Completion, Pricing
from digline_openai.client import completion_of

__all__ = ["INSTRUCTION_ROLES", "MAP", "NOT_SETUP", "OpenAIRecording"]

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


MAP = OpenAIRecording()
