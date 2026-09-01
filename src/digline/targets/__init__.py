"""Targets that call a provider: the shared half, with no SDK in it.

`digline.targets` sits above `digline.run` — a target produces a `Response` for
a `Case` — and below the CLI. It imports no provider SDK and never will: a real
provider is a separate package under `packages/`, so installing digline does
not install someone's HTTP client.

The same shape covers judging: `JudgeBase` is `ProviderTarget`'s twin, and a
plugin ships both — a target and a judge (ADR 0004).
"""

from digline.targets.config import CONTRACT_FIELDS, declared_config, endpoint_host, sent
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
)
from digline.targets.provider import ProviderTarget
from digline.targets.template import PromptTemplate, render_value

__all__ = [
    "CLAIM_SYSTEM",
    "CONTRACT_FIELDS",
    "SCORE_SYSTEM",
    "ClaimCountJudge",
    "HttpTarget",
    "JudgeBase",
    "ModelPrice",
    "PromptTemplate",
    "ProviderTarget",
    "Pricing",
    "ScoreJudge",
    "UnknownModelError",
    "declared_config",
    "Usage",
    "endpoint_host",
    "loads_lenient",
    "render_value",
    "sent",
]
