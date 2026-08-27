"""Targets that call a provider: the shared half, with no SDK in it.

`digline.targets` sits above `digline.run` — a target produces a `Response` for
a `Case` — and below the CLI. It imports no provider SDK and never will: a real
provider is a separate package under `packages/`, so installing digline does
not install someone's HTTP client.
"""

from digline.targets.http import HttpTarget
from digline.targets.pricing import (
    ModelPrice,
    Pricing,
    UnknownModelError,
    Usage,
)
from digline.targets.provider import ProviderTarget
from digline.targets.template import PromptTemplate, render_value

__all__ = [
    "HttpTarget",
    "ModelPrice",
    "PromptTemplate",
    "ProviderTarget",
    "Pricing",
    "UnknownModelError",
    "Usage",
    "render_value",
]
