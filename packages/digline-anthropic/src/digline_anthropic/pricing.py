"""Anthropic list prices, in USD per million tokens.

    Read from platform.claude.com/docs/en/about-claude/pricing on 2026-10-02.

Cache **writes** are billed at 1.25x the input rate and are counted separately:
the API does not fold them into `input_tokens` (friction 25). That is the
5-minute rate. A 1-hour write costs 2x, and this list has no rate for it: a
reply that reports one is refused by `usage_of` rather than priced at 1.25x,
which under-counted those tokens by 37.5% before #368.

That date is the first line of this file on purpose. A price list is a fact
about a day, and the only honest thing a copy of one can carry is when it was
copied. When it is stale, `Pricing.override` in your suite fixes it in one
argument, and you should not wait for a release.

**Whether a stale price earns a release depends on its direction.** A list
that prices a call **below** what it cost lets a `CostBudget` pass on spend
that exceeded it. That is a silent pass, and it is repaired with a release. A
list that prices **above** fails a budget on spend that never happened. That
is loud, and it can wait for the package's next release. (#293)
"""

from __future__ import annotations

from digline.targets import ModelPrice, Pricing

__all__ = ["ANTHROPIC_PRICING", "PRICES_READ_ON"]

#: When the figures below were copied. Kept as data so a test can read it.
PRICES_READ_ON = "2026-10-02"

ANTHROPIC_PRICING = Pricing(
    per_model={
        # Fable 5.1. Cache hits are 0.025x the input rate, not the usual 0.1x.
        "claude-fable-5-1": ModelPrice(
            input_per_mtok=10.0,
            output_per_mtok=50.0,
            cache_read_per_mtok=0.25,
            cache_write_per_mtok=12.50,
        ),
        # Opus 5.5. Cache hits are 0.05x the input rate, not the usual 0.1x.
        "claude-opus-5-5": ModelPrice(
            input_per_mtok=4.0,
            output_per_mtok=20.0,
            cache_read_per_mtok=0.20,
            cache_write_per_mtok=5.0,
        ),
        # Sonnet 5.5
        "claude-sonnet-5-5": ModelPrice(
            input_per_mtok=2.0,
            output_per_mtok=10.0,
            cache_read_per_mtok=0.20,
            cache_write_per_mtok=2.50,
        ),
        # Fable 5
        "claude-fable-5": ModelPrice(
            input_per_mtok=10.0,
            output_per_mtok=50.0,
            cache_read_per_mtok=1.0,
            cache_write_per_mtok=12.50,
        ),
        # Opus 5
        "claude-opus-5": ModelPrice(
            input_per_mtok=5.0,
            output_per_mtok=25.0,
            cache_read_per_mtok=0.50,
            cache_write_per_mtok=6.25,
        ),
        # Sonnet 5. $2/$10 began as introductory pricing; the page now calls it
        # the standard price, and the increase to $3/$15 will not occur.
        "claude-sonnet-5": ModelPrice(
            input_per_mtok=2.0,
            output_per_mtok=10.0,
            cache_read_per_mtok=0.20,
            cache_write_per_mtok=2.50,
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
