"""How the recorder reads a call made through a `bedrock-runtime` client.
(ADR 0058 §3, §6)

Declared under `digline.recording_maps` as `botocore.BedrockRuntime:converse`:
boto3 builds the client's class at run time, in `botocore.client`, under the
service's name. Loaded only when a call is recorded. `converse_stream` is not
intercepted: streaming is a later piece.

**The case is the messages.** The setup is everything else the call decides
with: `modelId`, `system`, `inferenceConfig`, `toolConfig`, `guardrailConfig`,
`additionalModelRequestFields`, `promptVariables`, `performanceConfig`. Not
`requestMetadata`, which names who or what the request is for.

**The reply is read by `completion_of`**, the function the target already uses.
A recording does not price: the price list passed is empty, so a reply without
a usage block is recorded as *not recorded*, never as zero.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from digline.targets import Completion, Pricing
from digline_bedrock.client import completion_of

__all__ = ["MAP", "NOT_SETUP", "BedrockRecording"]

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


MAP = BedrockRecording()
