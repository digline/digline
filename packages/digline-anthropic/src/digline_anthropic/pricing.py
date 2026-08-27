"""Anthropic list prices, in USD per million tokens.

    Read from anthropic.com/pricing on 2026-08-27.

Cache **writes** are billed at 1.25x the input rate and are counted separately:
the API does not fold them into `input_tokens` (friction 25).

That date is the first line of this file on purpose. A price list is a fact
about a day, and the only honest thing a copy of one can carry is when it was
copied. When it is stale, `Pricing.override` in your suite fixes it in one
argument — digline does not cut a release because a price moved, and you should
not wait for one.
"""

from __future__ import annotations

from digline.targets import ModelPrice, Pricing

__all__ = ["ANTHROPIC_PRICING", "PRICES_READ_ON"]

#: When the figures below were copied. Kept as data so a test can read it.
PRICES_READ_ON = "2026-08-27"

ANTHROPIC_PRICING = Pricing(
    per_model={
        # Opus 5
        "claude-opus-5": ModelPrice(
            input_per_mtok=15.0,
            output_per_mtok=75.0,
            cache_read_per_mtok=1.50,
            cache_write_per_mtok=18.75,
        ),
        # Sonnet 5
        "claude-sonnet-5": ModelPrice(
            input_per_mtok=3.0,
            output_per_mtok=15.0,
            cache_read_per_mtok=0.30,
            cache_write_per_mtok=3.75,
        ),
        # Fable 5
        "claude-fable-5": ModelPrice(
            input_per_mtok=3.0,
            output_per_mtok=15.0,
            cache_read_per_mtok=0.30,
            cache_write_per_mtok=3.75,
        ),
        # Haiku 4.5. Both forms: a suite is written with whichever id its author
        # had in front of them, and an alias that is not in the list fails
        # `preflight` for a reason that has nothing to do with the suite.
        # (friction 28)
        "claude-haiku-4-5": ModelPrice(
            input_per_mtok=1.0,
            output_per_mtok=5.0,
            cache_read_per_mtok=0.10,
            cache_write_per_mtok=1.25,
        ),
        "claude-haiku-4-5-20251001": ModelPrice(
            input_per_mtok=1.0,
            output_per_mtok=5.0,
            cache_read_per_mtok=0.10,
            cache_write_per_mtok=1.25,
        ),
    }
)
