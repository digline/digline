"""Bedrock list prices, in USD per million tokens, **per region**.

    Read from aws.amazon.com/bedrock/pricing on 2026-08-28.

That date is the first line of this file on purpose. A price list is a fact
about a day, and the only honest thing a copy of one can carry is when it was
copied. When it is stale, `Pricing.override` in your suite fixes it in one
argument — digline does not cut a release because a price moved, and you should
not wait for one.

**The seeding is deliberately narrow.** Bedrock prices by model *and* by region,
and a figure invented for a region nobody checked is worse than no figure at
all: it would price a run confidently and wrongly. So only the models and
regions below are seeded; everything else raises `UnknownModelError` at
`preflight`, which is loud, happens before the first paid call, and is fixed by
one `pricing=` argument. That is the intended behaviour, not a gap.

**Inference profile ids.** A cross-region profile is billed at the price of the
region you call, so the factory generates the prefixed key — `eu.` for an EU
region, `us.` for a US one, `apac.` for an Asia-Pacific one — beside the bare
model id, from one base table. An **application** inference profile is an ARN,
is opaque, and is never in the list: it fails `preflight` and is served with an
explicit `pricing=`.
"""

from __future__ import annotations

from digline.targets import ModelPrice, Pricing

__all__ = [
    "BASE_PRICES",
    "PRICES_READ_ON",
    "SEEDED_REGIONS",
    "bedrock_pricing",
    "free",
]

#: When the figures below were copied. Kept as data so a test can read it.
PRICES_READ_ON = "2026-08-28"

#: The regions these figures were read for. Anything else is unpriced by
#: design — see the module docstring.
SEEDED_REGIONS = frozenset(
    {"us-east-1", "us-west-2", "eu-west-1", "eu-central-1", "eu-west-3"}
)

#: Base model ids, without the inference-profile prefix the factory adds.
#: Anthropic models only: they are the ones whose Bedrock figures were checked
#: against the page. Nova, Llama, Mistral and the rest are not seeded — pass
#: `pricing=` for them rather than trusting a number nobody read.
BASE_PRICES = {
    "anthropic.claude-opus-4-1-20250805-v1:0": ModelPrice(
        input_per_mtok=15.0,
        output_per_mtok=75.0,
        cache_read_per_mtok=1.50,
        cache_write_per_mtok=18.75,
    ),
    "anthropic.claude-sonnet-4-20250514-v1:0": ModelPrice(
        input_per_mtok=3.0,
        output_per_mtok=15.0,
        cache_read_per_mtok=0.30,
        cache_write_per_mtok=3.75,
    ),
    "anthropic.claude-haiku-4-5-20251001-v1:0": ModelPrice(
        input_per_mtok=1.0,
        output_per_mtok=5.0,
        cache_read_per_mtok=0.10,
        cache_write_per_mtok=1.25,
    ),
    "anthropic.claude-3-5-sonnet-20241022-v2:0": ModelPrice(
        input_per_mtok=3.0,
        output_per_mtok=15.0,
        cache_read_per_mtok=0.30,
        cache_write_per_mtok=3.75,
    ),
    "anthropic.claude-3-5-haiku-20241022-v1:0": ModelPrice(
        input_per_mtok=0.80,
        output_per_mtok=4.0,
        cache_read_per_mtok=0.08,
        cache_write_per_mtok=1.0,
    ),
}

#: Which inference-profile prefix a region belongs to. Read from the region's
#: first segment, which is how AWS names them.
_PREFIXES = {"us": "us.", "ca": "us.", "eu": "eu.", "ap": "apac."}


def profile_prefix(region: str) -> str | None:
    """`"eu."` for `eu-west-1`. `None` for a region with no known geography."""
    return _PREFIXES.get(region.split("-", 1)[0])


def bedrock_pricing(region: str) -> Pricing:
    """The price list for one region, bare ids and profile ids together.

    Seeded for **us-east-1, us-west-2, eu-west-1, eu-central-1 and eu-west-3**,
    with the Anthropic models in `BASE_PRICES`. Any other region — and any other
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
    prefix = profile_prefix(region)
    per_model: dict[str, ModelPrice] = {}
    for model, price in BASE_PRICES.items():
        per_model[model] = price
        if prefix is not None:
            per_model[f"{prefix}{model}"] = price
    return Pricing(per_model=per_model)


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
