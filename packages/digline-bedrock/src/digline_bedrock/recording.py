"""How the recorder reads a call made through a `bedrock-runtime` client.
(ADR 0058 §3, §6)

Declared under `digline.recording_maps` as `botocore.BedrockRuntime:converse`:
boto3 builds the client's class at run time, in `botocore.client`, under the
service's name. Loaded only when a call is recorded.

**`converse_stream` is another method**, declared under its own entry point,
`botocore.BedrockRuntime:converse_stream` (ADR 0058 §13). Its reply is a dict
whose `stream` is botocore's `EventStream`; the events are folded into the
Converse reply the whole answer would have been — `output.message` from
`messageStart` and the `contentBlock*` events, `stopReason` from
`messageStop`, `usage` from `metadata` — and read by `completion_of` like any
other. The SDK offers no accumulator of its own for these events, so this one
is the plugin's.

**The case is the messages.** The setup is everything else the call decides
with: `modelId`, `system`, `inferenceConfig`, `toolConfig`, `guardrailConfig`,
`additionalModelRequestFields`, `promptVariables`, `performanceConfig`. Not
`requestMetadata`, which names who or what the request is for.

**The reply is read by `completion_of`**, the function the target already uses.
A recording does not price: the price list passed is empty, so a reply without
a usage block is recorded as *not recorded*, never as zero.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, cast

from digline.targets import Completion, Pricing
from digline_bedrock.client import completion_of

__all__ = ["MAP", "NOT_SETUP", "STREAM_MAP", "BedrockRecording"]

#: The keywords of `converse` that are neither the case nor the setup, beside
#: the messages themselves.
NOT_SETUP: frozenset[str] = frozenset({"messages", "requestMetadata"})

_NO_PRICES = Pricing(per_model={})


class BedrockRecording:
    """The map digline's recorder loads for a `bedrock-runtime` client."""

    def split(
        self, request: Mapping[str, Any]
    ) -> tuple[dict[str, object], dict[str, object]]:
        case: dict[str, object] = {"messages": request.get("messages")}
        setup = {key: value for key, value in request.items() if key not in NOT_SETUP}
        return case, setup

    def completion(self, reply: Any, request: Mapping[str, Any]) -> Completion:
        return completion_of(reply, str(request.get("modelId", "")), _NO_PRICES)


class BedrockStreamRecording(BedrockRecording):
    """The map for `converse_stream`: the same request, and a reply whose
    `stream` carries the events."""

    def streams(self, request: Mapping[str, Any]) -> bool:
        return True

    def stream_of(self, reply: Any) -> Any:
        return reply["stream"]

    def reading(self, request: Mapping[str, Any]) -> Any:
        return _Events(str(request.get("modelId", "")))


class _Events:
    """The events of one `converse_stream`, folded into a Converse reply."""

    def __init__(self, model: str) -> None:
        self._model = model
        self._role = "assistant"
        #: Per content block index: its kind, and what has arrived of it.
        self._blocks: dict[int, dict[str, Any]] = {}
        self._stop: str | None = None
        self._usage: Mapping[str, Any] | None = None

    def add(self, event: Any) -> None:
        if not isinstance(event, Mapping):
            return
        found = cast("Mapping[str, Any]", event)
        if "messageStart" in found:
            self._role = str(found["messageStart"].get("role", "assistant"))
        elif "contentBlockStart" in found:
            start = found["contentBlockStart"]
            tool = start.get("start", {}).get("toolUse")
            if tool is not None:
                self._blocks[int(start["contentBlockIndex"])] = {
                    "toolUse": {**tool, "input": ""}
                }
        elif "contentBlockDelta" in found:
            delta = found["contentBlockDelta"]
            index = int(delta["contentBlockIndex"])
            change = delta.get("delta", {})
            block = self._blocks.setdefault(index, {})
            if "text" in change:
                block["text"] = block.get("text", "") + str(change["text"])
            elif "toolUse" in change:
                use = block.setdefault("toolUse", {"input": ""})
                use["input"] = use.get("input", "") + str(
                    change["toolUse"].get("input", "")
                )
        elif "messageStop" in found:
            self._stop = found["messageStop"].get("stopReason")
        elif "metadata" in found:
            self._usage = found["metadata"].get("usage")

    def completion(self, stream: Any) -> Completion:
        content: list[dict[str, Any]] = []
        for index in sorted(self._blocks):
            block = self._blocks[index]
            if "toolUse" in block:
                use = dict(block["toolUse"])
                raw = use.get("input") or "{}"
                use["input"] = json.loads(raw) if isinstance(raw, str) else raw
                content.append({"toolUse": use})
            elif "text" in block:
                content.append({"text": block["text"]})
        reply: dict[str, Any] = {
            "output": {"message": {"role": self._role, "content": content}},
            "stopReason": self._stop,
        }
        if self._usage is not None:
            reply["usage"] = self._usage
        return completion_of(reply, self._model, _NO_PRICES)


MAP = BedrockRecording()
STREAM_MAP = BedrockStreamRecording()
