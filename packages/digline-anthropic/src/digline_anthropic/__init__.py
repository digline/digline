"""Anthropic target for digline.

Installed beside digline, never inside it: `pip install digline` must not pull
somebody's HTTP client along with it.
"""

from digline_anthropic.pricing import ANTHROPIC_PRICING, PRICES_READ_ON
from digline_anthropic.target import AnthropicTarget

__all__ = ["ANTHROPIC_PRICING", "PRICES_READ_ON", "AnthropicTarget"]
