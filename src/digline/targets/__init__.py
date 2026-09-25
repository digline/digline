"""Targets that call a provider: the shared half, with no SDK in it.

`digline.targets` sits above `digline.run` — a target produces a `Response` for
a `Case` — and below the CLI. It imports no provider SDK and never will: a real
provider is a separate package under `packages/`, so installing digline does
not install someone's HTTP client.

The same shape covers judging: `JudgeBase` is `ProviderTarget`'s twin, and a
plugin ships both — a target and a judge (ADR 0004).
"""

from digline.targets.completion import (
    Completion,
    CompletionResult,
    HasObserved,
    ObservedIdentity,
    ToolCall,
    as_completion,
    finish_of,
)
from digline.targets.config import (
    CONTRACT_FIELDS,
    declared_config,
    endpoint_host,
    expected_config,
    refuse_config_mismatch,
    sent,
)
from digline.targets.http import HttpTarget
from digline.targets.judge import (
    CLAIM_SYSTEM,
    SCORE_SYSTEM,
    ClaimCountJudge,
    JudgeBase,
    ScoreJudge,
    loads_lenient,
)
from digline.targets.pricing import (
    ModelPrice,
    Pricing,
    UnknownModelError,
    Usage,
    free,
)
from digline.targets.provider import ProviderTarget
from digline.targets.registry import (
    GROUP,
    Provider,
    ProviderNotFound,
    installed,
    resolve,
    split_coordinate,
)
from digline.targets.template import PromptTemplate, render_value

__all__ = [
    "CLAIM_SYSTEM",
    "CONTRACT_FIELDS",
    "GROUP",
    "SCORE_SYSTEM",
    "ClaimCountJudge",
    "Completion",
    "CompletionResult",
    "HttpTarget",
    "JudgeBase",
    "ModelPrice",
    "HasObserved",
    "ObservedIdentity",
    "PromptTemplate",
    "Provider",
    "ProviderNotFound",
    "ProviderTarget",
    "Pricing",
    "ScoreJudge",
    "ToolCall",
    "UnknownModelError",
    "Usage",
    "as_completion",
    "declared_config",
    "endpoint_host",
    "expected_config",
    "finish_of",
    "free",
    "installed",
    "loads_lenient",
    "render_value",
    "resolve",
    "refuse_config_mismatch",
    "sent",
    "split_coordinate",
]
