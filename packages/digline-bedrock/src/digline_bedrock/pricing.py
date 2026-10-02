"""Bedrock list prices, in USD per million tokens, **per region**.

    Read on 2026-10-02 from AWS's Price List API, offer
    `AmazonBedrockFoundationModels`, publication 2026-09-30T00:19:12Z; and,
    for Claude 3.5 Sonnet v2 only, from aws.amazon.com/bedrock/pricing.

That date is the first line of this file on purpose. A price list is a fact
about a day, and the only honest thing a copy of one can carry is when it was
copied. When it is stale, `Pricing.override` in your suite fixes it in one
argument, and you should not wait for a release.

**Whether a stale price earns a release depends on its direction**, the rule
`digline-anthropic` states: a list that prices a call **below** what it cost
lets a `CostBudget` pass on spend that exceeded it, and is repaired with a
release; one that prices **above** fails a budget loudly and can wait. (#293)

**The seeding is deliberately narrow.** Bedrock prices by model, by region and
by endpoint, and a figure invented for a region nobody checked is worse than no
figure at all: it would price a run confidently and wrongly. So a model is
seeded only in the regions where the source lists it, and only under the ids
that route there; everything else raises `UnknownModelError` at `preflight`,
which is loud, happens before the first paid call, and is fixed by one
`pricing=` argument. *Before #369 this file priced Claude Opus 4.1 and Claude
3.5 Haiku in eu-west-1, eu-central-1 and eu-west-3, where AWS does not sell
them, which is the thing this paragraph says it does not do.* (#369)

**Two prices for one model, by endpoint.** From Claude Haiku 4.5 on, AWS bills
a **global** inference profile (`global.`) about 10% below everything else: a
geographic profile (`us.`, `eu.`) and an in-region call pay the *Standard*
price. AWS's own words: geographic cross-region inference is *"Standard
pricing"*, global is *"Approximately 10% savings"*, and *"The price is
calculated based on the Region from which you call an inference profile."*
Before #369 this list priced Haiku 4.5's geographic profiles at the global
price, 10% under on every token. (#369)

**Claude 3.5 Sonnet v2: the two sources disagree, and this list takes the
higher.** The Price List API still lists $3 / $15. The pricing page lists
*"Claude 3.5 Sonnet v2 (Public Extended Access, Effective 1 Dec 2025)"* at
$6 / $30, with cache writes at $7.50 and reads at $0.60, in US East and US West
only. A list that is wrong on the high side fails a budget loudly; one wrong
on the low side passes it silently. So $6 / $30 it is, until the two agree.

**A 1-hour cache write is refused, not priced** — see `usage_of`. Bedrock bills
it at 1.6x the 5-minute write, and `Usage` has one write rate. (#368)

**Inference profile ids.** A cross-region profile is billed at the price of the
region you call, so a geographic profile is keyed by the prefix of the region's
geography — `eu.` for an EU region, `us.` for a US one — and `global.` beside
it where the source lists a global price. An **application** inference profile
is an ARN, is opaque, and is never in the list: it fails `preflight` and is
served with an explicit `pricing=`.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

from digline.targets import ModelPrice, Pricing
from digline.targets import free as declared_free

__all__ = [
    "PRICES_READ_ON",
    "SEEDED_PRICES",
    "SEEDED_REGIONS",
    "bedrock_pricing",
    "free",
]

#: When the figures below were copied. Kept as data so a test can read it.
PRICES_READ_ON = "2026-10-02"

_US = ("us-east-1", "us-west-2")
_EU = ("eu-west-1", "eu-central-1", "eu-west-3")

#: The regions these figures were read for. Anything else is unpriced by
#: design — see the module docstring.
SEEDED_REGIONS = frozenset(_US + _EU)

_OPUS_4_1 = "anthropic.claude-opus-4-1-20250805-v1:0"
_SONNET_4 = "anthropic.claude-sonnet-4-20250514-v1:0"
_HAIKU_4_5 = "anthropic.claude-haiku-4-5-20251001-v1:0"
_SONNET_3_5_V2 = "anthropic.claude-3-5-sonnet-20241022-v2:0"
_HAIKU_3_5 = "anthropic.claude-3-5-haiku-20241022-v1:0"
_FABLE_5_1 = "anthropic.claude-fable-5-1"
_OPUS_5_5 = "anthropic.claude-opus-5-5"
_SONNET_5_5 = "anthropic.claude-sonnet-5-5"


def _price(input_: float, output: float, read: float, write: float) -> ModelPrice:
    return ModelPrice(
        input_per_mtok=input_,
        output_per_mtok=output,
        cache_read_per_mtok=read,
        cache_write_per_mtok=write,
    )


#: One row per fact read: (regions, how the model is reached there, price).
#: `bare` is the model id itself, `geo` the region's geographic profile, and
#: `global` the `global.` profile. A model reached only through profiles has
#: no `bare` row: AWS does not take its bare id on `bedrock-runtime`.
_ROWS: tuple[tuple[tuple[str, ...], str, tuple[str, ...], ModelPrice], ...] = (
    # Claude Opus 4.1. One price; sold in US East and US West only.
    (_US, _OPUS_4_1, ("bare", "geo"), _price(15.0, 75.0, 1.50, 18.75)),
    # Claude Sonnet 4. One price, global or not; the global rows are listed in
    # three of the five regions.
    (_US + _EU, _SONNET_4, ("bare", "geo"), _price(3.0, 15.0, 0.30, 3.75)),
    (_US + ("eu-west-1",), _SONNET_4, ("global",), _price(3.0, 15.0, 0.30, 3.75)),
    # Claude Haiku 4.5. "Regional" and "Global" rows, 10% apart.
    (_US + _EU, _HAIKU_4_5, ("bare", "geo"), _price(1.10, 5.50, 0.11, 1.375)),
    (_US + _EU, _HAIKU_4_5, ("global",), _price(1.0, 5.0, 0.10, 1.25)),
    # Claude 3.5 Sonnet v2, at the pricing page's Extended Access figure.
    (_US, _SONNET_3_5_V2, ("bare", "geo"), _price(6.0, 30.0, 0.60, 7.50)),
    # Claude 3.5 Haiku. Sold in US East and US West only.
    (_US, _HAIKU_3_5, ("bare", "geo"), _price(0.80, 4.0, 0.08, 1.0)),
    # Claude Fable 5.1. A `us.` profile in the US; in the EU, `global.` only.
    (_US, _FABLE_5_1, ("geo",), _price(11.0, 55.0, 0.275, 13.75)),
    (_US + _EU, _FABLE_5_1, ("global",), _price(10.0, 50.0, 0.25, 12.50)),
    # Claude Opus 5.5. Cache hits are 0.05x the input rate.
    (_US + _EU, _OPUS_5_5, ("geo",), _price(4.40, 22.0, 0.22, 5.50)),
    (_US + _EU, _OPUS_5_5, ("global",), _price(4.0, 20.0, 0.20, 5.0)),
    # Claude Sonnet 5.5
    (_US + _EU, _SONNET_5_5, ("geo",), _price(2.20, 11.0, 0.22, 2.75)),
    (_US + _EU, _SONNET_5_5, ("global",), _price(2.0, 10.0, 0.20, 2.50)),
)


#: Which inference-profile prefix a region belongs to. Read from the region's
#: first segment, which is how AWS names them.
_PREFIXES = {"us": "us.", "ca": "us.", "eu": "eu.", "ap": "apac."}


def profile_prefix(region: str) -> str | None:
    """`"eu."` for `eu-west-1`. `None` for a region with no known geography."""
    return _PREFIXES.get(region.split("-", 1)[0])


def _seed(region: str) -> dict[str, ModelPrice]:
    prefix = profile_prefix(region)
    seeded: dict[str, ModelPrice] = {}
    for regions, model, routes, price in _ROWS:
        if region not in regions:
            continue
        for route in routes:
            if route == "bare":
                seeded[model] = price
            elif route == "geo" and prefix is not None:
                seeded[f"{prefix}{model}"] = price
            elif route == "global":
                seeded[f"global.{model}"] = price
    return seeded


#: Every seeded region's list, by model id, exactly as `bedrock_pricing` returns
#: it. Read-only: a correction belongs in a suite's `Pricing.override`.
SEEDED_PRICES: Mapping[str, Mapping[str, ModelPrice]] = MappingProxyType(
    {region: MappingProxyType(_seed(region)) for region in sorted(SEEDED_REGIONS)}
)


def bedrock_pricing(region: str) -> Pricing:
    """The price list for one region: bare ids and profile ids together.

    Seeded for **us-east-1, us-west-2, eu-west-1, eu-central-1 and eu-west-3**,
    with the Anthropic models AWS lists there. Any other region — and any other
    model family — is served with an explicit `pricing=` in the suite, or with
    `bedrock_pricing(...).override(...)` when only one entry is missing:

        BedrockTarget(..., pricing=bedrock_pricing("us-east-1").override(
            "amazon.nova-pro-v1:0", ModelPrice(0.80, 3.20)
        ))

    An unseeded region raises here rather than returning an empty list: an empty
    list would fail `preflight` with a message about a model, when the thing
    that is actually missing is a region.
    """
    if region not in SEEDED_REGIONS:
        seeded = ", ".join(sorted(SEEDED_REGIONS))
        raise ValueError(
            f"no seeded price list for region {region!r} (seeded: {seeded}). "
            "Bedrock prices by region, and a figure copied from another one "
            "would be wrong in the direction nobody notices: pass an explicit "
            "`pricing=` for this region"
        )
    return Pricing(per_model=dict(SEEDED_PRICES[region]))


def free(*models: str) -> Pricing:
    """A price list where the named models cost nothing **per token**.

    On Bedrock this is not a convenience, it is the accurate description of two
    real billing modes: a model brought in through **Custom Model Import** and
    one behind **Provisioned Throughput** are billed by model-copy-hour and by
    model-unit-hour. There is no per-token meter to report, so a per-token price
    of anything other than zero would be an invention, and a `CostBudget` over
    such a run measures something that does not exist.

    It is deliberately not a default. An unpriced model raises (fixed decision
    3) precisely so that nobody discovers a zero-cost run by omission, and this
    function is how you say out loud that this one really has no per-token bill:

        BedrockTarget(..., model="my-imported-model", pricing=free("my-imported-model"))

    A `LatencyBudget` still measures something real, and on provisioned capacity
    it is usually the budget you actually care about.

    **A declaration**, and that moves a hash. This delegates to
    `digline.targets.free`, so the zero enters `config_hash` like any declared
    price and a Python suite hashes as its data-suite twin with four declared
    zeros does. A suite that already called this gets a new hash on upgrade: its
    baseline stays comparable and is no longer promotable. (ADR 0022 §2)
    """
    return declared_free(*models)
