"""Anthropic target and judges for digline.

Installed beside digline, never inside it: `pip install digline` must not pull
somebody's HTTP client along with it.

A plugin is a target **and** a judge (ADR 0004), so a suite generates and judges
with one provider, one key and one price list.
"""

from digline_anthropic.judge import AnthropicClaimJudge, AnthropicJudge
from digline_anthropic.pricing import ANTHROPIC_PRICING, PRICES_READ_ON
from digline_anthropic.target import AnthropicTarget

__all__ = [
    "ANTHROPIC_PRICING",
    "PRICES_READ_ON",
    "AnthropicClaimJudge",
    "AnthropicJudge",
    "AnthropicTarget",
]
