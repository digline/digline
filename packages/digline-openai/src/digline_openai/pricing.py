"""OpenAI list prices, in USD per million tokens.

    Read from openai.com/api/pricing on 2026-08-28.

That date is the first line of this file on purpose. A price list is a fact
about a day, and the only honest thing a copy of one can carry is when it was
copied. When it is stale, `Pricing.override` in your suite fixes it in one
argument — digline does not cut a release because a price moved, and you should
not wait for one.

**Cached input, and the arithmetic that goes with it.** OpenAI bills a cached
prompt token at a discount and — unlike Anthropic — counts it *inside*
`prompt_tokens`. `digline_openai.client` subtracts it before building the
`Usage`, so the two token counts here are disjoint and nothing is billed twice.
There is no charge for *writing* a cache, which is why every entry leaves
`cache_write_per_mtok` at `None`: `None` means "this provider has no such tier"
and makes a non-zero count raise, where a `0.0` would price it at nothing.

**This list is the official endpoint's.** Point `base_url` at Azure, OpenRouter,
Groq or vLLM and the prices are somebody else's: pass your own `pricing=`, or
`free(...)` for what you host yourself.
"""

from __future__ import annotations

from digline.targets import ModelPrice, Pricing

__all__ = ["OPENAI_PRICING", "PRICES_READ_ON", "free"]

#: When the figures below were copied. Kept as data so a test can read it.
PRICES_READ_ON = "2026-08-28"

OPENAI_PRICING = Pricing(
    per_model={
        # GPT-5
        "gpt-5": ModelPrice(
            input_per_mtok=1.25,
            output_per_mtok=10.0,
            cache_read_per_mtok=0.125,
        ),
        "gpt-5-mini": ModelPrice(
            input_per_mtok=0.25,
            output_per_mtok=2.0,
            cache_read_per_mtok=0.025,
        ),
        "gpt-5-nano": ModelPrice(
            input_per_mtok=0.05,
            output_per_mtok=0.40,
            cache_read_per_mtok=0.005,
        ),
        # GPT-4.1
        "gpt-4.1": ModelPrice(
            input_per_mtok=2.0,
            output_per_mtok=8.0,
            cache_read_per_mtok=0.50,
        ),
        "gpt-4.1-mini": ModelPrice(
            input_per_mtok=0.40,
            output_per_mtok=1.60,
            cache_read_per_mtok=0.10,
        ),
        "gpt-4.1-nano": ModelPrice(
            input_per_mtok=0.10,
            output_per_mtok=0.40,
            cache_read_per_mtok=0.025,
        ),
        # GPT-4o. Both forms, alias and dated id: a suite is written with
        # whichever one its author had in front of them, and an alias missing
        # from the list fails `preflight` for a reason that has nothing to do
        # with the suite. (friction 28)
        "gpt-4o": ModelPrice(
            input_per_mtok=2.50,
            output_per_mtok=10.0,
            cache_read_per_mtok=1.25,
        ),
        "gpt-4o-2024-08-06": ModelPrice(
            input_per_mtok=2.50,
            output_per_mtok=10.0,
            cache_read_per_mtok=1.25,
        ),
        "gpt-4o-mini": ModelPrice(
            input_per_mtok=0.15,
            output_per_mtok=0.60,
            cache_read_per_mtok=0.075,
        ),
        "gpt-4o-mini-2024-07-18": ModelPrice(
            input_per_mtok=0.15,
            output_per_mtok=0.60,
            cache_read_per_mtok=0.075,
        ),
        # Reasoning models
        "o3": ModelPrice(
            input_per_mtok=2.0,
            output_per_mtok=8.0,
            cache_read_per_mtok=0.50,
        ),
        "o4-mini": ModelPrice(
            input_per_mtok=1.10,
            output_per_mtok=4.40,
            cache_read_per_mtok=0.275,
        ),
        # GPT-5.6 — short-context prices; the long-context meter (input roughly
        # doubles) is not modeled here, see the note at the top.
        "gpt-5.6-sol": ModelPrice(  # promotional until at least 2026-11-21
            input_per_mtok=4.0,
            output_per_mtok=20.0,
            cache_read_per_mtok=0.40,
            cache_write_per_mtok=5.0,
        ),
        "gpt-5.6-terra": ModelPrice(
            input_per_mtok=2.0,
            output_per_mtok=12.0,
            cache_read_per_mtok=0.20,
            cache_write_per_mtok=2.5,
        ),
        "gpt-5.6-luna": ModelPrice(
            input_per_mtok=0.20,
            output_per_mtok=1.20,
            cache_read_per_mtok=0.02,
            cache_write_per_mtok=0.25,
        ),
    }
)


def free(*models: str) -> Pricing:
    """A price list where the named models cost nothing.

    For a model **you host** — Ollama on your laptop, a vLLM in your own VPC.
    Zero is not a shortcut there, it is the honest per-token price: the GPU was
    paid for by the hour and no meter runs per token, so a `CostBudget` over a
    self-hosted run is measuring something that does not exist.

    It is deliberately not a default. An unpriced model raises (fixed decision
    3) precisely so that nobody discovers a zero-cost run by omission, and this
    function is how you say out loud that this one really is free:

        OpenAITarget(..., base_url=OLLAMA, pricing=free("llama3.2"))

    A `LatencyBudget` still measures something real, and on your own hardware it
    is usually the budget you actually care about.
    """
    if not models:
        raise ValueError(
            "free() needs at least one model name: an empty price list knows "
            "nothing and every model would fail preflight"
        )
    return Pricing(
        per_model={
            model: ModelPrice(
                input_per_mtok=0.0,
                output_per_mtok=0.0,
                cache_read_per_mtok=0.0,
                cache_write_per_mtok=0.0,
            )
            for model in models
        }
    )
