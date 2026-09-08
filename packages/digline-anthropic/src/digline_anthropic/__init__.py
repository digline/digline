"""Anthropic target and judges for digline.

Installed beside digline, never inside it: `pip install digline` must not pull
somebody's HTTP client along with it.

A plugin is a target **and** a judge (ADR 0004), so a suite generates and judges
with one provider, one key and one price list.
"""

from digline.targets import Provider
from digline_anthropic.judge import AnthropicClaimJudge, AnthropicJudge
from digline_anthropic.pricing import ANTHROPIC_PRICING, PRICES_READ_ON
from digline_anthropic.target import AnthropicTarget

#: What the coordinate `"anthropic/<model>"` resolves through — a judge named in a
#: TOML suite, or a `[target]` naming this provider (ADR 0007 §3). Registered in
#: pyproject.toml under the `digline.providers` entry point group, which is how
#: digline finds it **by name**: nothing shipped with digline imports this
#: package, and the layering gate holds it to that.
PROVIDER = Provider(
    name="anthropic",
    target=AnthropicTarget,
    judge=AnthropicJudge,
    claim_judge=AnthropicClaimJudge,
)
__all__ = [
    "PROVIDER",
    "ANTHROPIC_PRICING",
    "PRICES_READ_ON",
    "AnthropicClaimJudge",
    "AnthropicJudge",
    "AnthropicTarget",
]
