"""What a call cost, from a price list declared in code.

Prices change on the provider's schedule, not on ours, so a list lives in the
plugin that knows the provider and can be replaced by the user in one argument.
digline does not cut a release because a price moved.

Nothing here reads the network or a file: a price list is a value, and a value
that had to be fetched would make the cost of a run depend on the day it was
computed rather than on the day it was run.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace

__all__ = ["ModelPrice", "Pricing", "Usage", "UnknownModelError", "free"]


class UnknownModelError(KeyError):
    """Raised when a model has no price.

    An exception and never `0.0`. A model that costs nothing passes every
    `CostBudget` there is, which is fixed decision 3 — a check that cannot fail
    is a bug — and it would fail silently, in the direction of "everything is
    fine", for as long as nobody read the numbers.
    """


@dataclass(frozen=True, slots=True)
class Usage:
    """What one call consumed. Counts, never money: the arithmetic is here."""

    input_tokens: int
    output_tokens: int
    cache_read_tokens: int = 0
    #: Tokens written *into* a cache. A separate count because it is billed at
    #: a separate rate and because — measured against the real API on
    #: 2026-08-27 — a provider does **not** include them in `input_tokens`:
    #: a cached call reported `input_tokens=10` beside `cache_write=9202`.
    #: Folding them in would have reported that call as a thousandth of its
    #: cost, in the direction of good news. (friction 25)
    cache_write_tokens: int = 0

    def __post_init__(self) -> None:
        for name in (
            "input_tokens",
            "output_tokens",
            "cache_read_tokens",
            "cache_write_tokens",
        ):
            if getattr(self, name) < 0:
                raise ValueError(f"Usage.{name} must not be negative")


@dataclass(frozen=True, slots=True)
class ModelPrice:
    """USD per million tokens, the unit every provider publishes."""

    input_per_mtok: float
    output_per_mtok: float
    #: `None` when the provider has no cached tier, which is different from
    #: zero: zero would silently price a cached token at nothing.
    cache_read_per_mtok: float | None = None
    cache_write_per_mtok: float | None = None

    def rates(self) -> dict[str, float | None]:
        """The four rates by the names a data suite declares them under."""
        return {
            "input_per_mtok": self.input_per_mtok,
            "output_per_mtok": self.output_per_mtok,
            "cache_read_per_mtok": self.cache_read_per_mtok,
            "cache_write_per_mtok": self.cache_write_per_mtok,
        }


@dataclass(frozen=True, slots=True)
class Pricing:
    """A price list, and the one piece of arithmetic that uses it."""

    per_model: Mapping[str, ModelPrice]
    #: The models whose price the **suite declared**, rather than inherited from
    #: a plugin's shipped list. A declared price enters `config_hash` — it is the
    #: ruler a `CostBudget` reads cost on — and a shipped one does not, because a
    #: plugin release must not unpromote every baseline that uses it. Filled by
    #: `override()` and `free()`; a `Pricing` built directly declares nothing,
    #: which is how a Python suite prices without declaring. (ADR 0022 §2, §6)
    declared: frozenset[str] = frozenset()

    def declared_price(self, model: str) -> ModelPrice | None:
        """The price the suite declared for `model`, or `None`."""
        return self.per_model.get(model) if model in self.declared else None

    def knows(self, model: str) -> bool:
        return model in self.per_model

    def cost(self, model: str, usage: Usage) -> float:
        """USD for one call.

        Raises on a model it does not know, and on cached reads it cannot
        price: undercounting a cost is the failure that reads as good news.
        """
        price = self.per_model.get(model)
        if price is None:
            known = ", ".join(sorted(self.per_model)) or "none"
            raise UnknownModelError(
                f"no price for model {model!r}: a run cannot report what it "
                f"cost, and a cost of zero passes every budget. Known: {known}. "
                "Pass `pricing=` to the target to add it."
            )
        for count, rate, kind in (
            (usage.cache_read_tokens, price.cache_read_per_mtok, "cached-read"),
            (usage.cache_write_tokens, price.cache_write_per_mtok, "cache-write"),
        ):
            if count and rate is None:
                raise UnknownModelError(
                    f"model {model!r} used {count} {kind} tokens and its price "
                    f"list declares no {kind} rate: pricing them at zero would "
                    "report a run as cheaper than it was"
                )
        total = (
            usage.input_tokens * price.input_per_mtok
            + usage.output_tokens * price.output_per_mtok
            + usage.cache_read_tokens * (price.cache_read_per_mtok or 0.0)
            + usage.cache_write_tokens * (price.cache_write_per_mtok or 0.0)
        )
        return total / 1_000_000

    def override(self, model: str, price: ModelPrice) -> Pricing:
        """A new list with one entry replaced or added.

        A price the user corrects is one argument in the suite, which is code
        and goes through a review — the same route as every other thing digline
        will not decide on its own. It is therefore a **declaration**, and the
        model joins `declared`. (ADR 0022 §2)
        """
        return replace(
            self,
            per_model={**self.per_model, model: price},
            declared=self.declared | {model},
        )


def free(*models: str) -> Pricing:
    """A declared price of zero, for models you host. (ADR 0022 §2)

    Zero is the honest per-token price on hardware paid for by the hour, and it
    is still a decision: an unpriced model raises (fixed decision 3), so a zero
    has to be written down. Declared, so it enters `config_hash` like any other
    declared price. The plugins' own `free()` delegate here from their next
    releases; until then theirs build an undeclared list.
    """
    if not models:
        raise ValueError(
            "free() needs at least one model name: an empty price list knows "
            "nothing and every model would fail preflight"
        )
    zero = ModelPrice(
        input_per_mtok=0.0,
        output_per_mtok=0.0,
        cache_read_per_mtok=0.0,
        cache_write_per_mtok=0.0,
    )
    return Pricing(per_model=dict.fromkeys(models, zero), declared=frozenset(models))
