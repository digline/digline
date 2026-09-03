"""OpenAI target and judges for digline, at any OpenAI-compatible endpoint.

Installed beside digline, never inside it: `pip install digline` must not pull
somebody's HTTP client along with it.

A plugin is a target **and** a judge (ADR 0004), so a suite can generate and
judge in one perimeter, with one key and one price list — including when that
perimeter is an Azure deployment, a vLLM in a VPC or an Ollama on a laptop.
"""

from digline.targets import Provider
from digline_openai.client import NO_KEY, OpenAIChat
from digline_openai.judge import OpenAIClaimJudge, OpenAIJudge
from digline_openai.pricing import OPENAI_PRICING, PRICES_READ_ON, free
from digline_openai.target import OpenAITarget

#: What the coordinate `"openai/<model>"` resolves through — a judge named in a
#: TOML suite, or a `[target]` naming this provider (ADR 0007 §3). Registered in
#: pyproject.toml under the `digline.providers` entry point group, which is how
#: digline finds it **by name**: nothing shipped with digline imports this
#: package, and the layering gate holds it to that.
PROVIDER = Provider(
    name="openai",
    target=OpenAITarget,
    judge=OpenAIJudge,
    claim_judge=OpenAIClaimJudge,
)
__all__ = [
    "PROVIDER",
    "NO_KEY",
    "OPENAI_PRICING",
    "PRICES_READ_ON",
    "OpenAIChat",
    "OpenAIClaimJudge",
    "OpenAIJudge",
    "OpenAITarget",
    "free",
]
