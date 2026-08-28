"""OpenAI target and judges for digline, at any OpenAI-compatible endpoint.

Installed beside digline, never inside it: `pip install digline` must not pull
somebody's HTTP client along with it.

A plugin is a target **and** a judge (ADR 0004), so a suite can generate and
judge in one perimeter, with one key and one price list — including when that
perimeter is an Azure deployment, a vLLM in a VPC or an Ollama on a laptop.
"""

from digline_openai.client import NO_KEY, OpenAIChat
from digline_openai.judge import OpenAIClaimJudge, OpenAIJudge
from digline_openai.pricing import OPENAI_PRICING, PRICES_READ_ON, free
from digline_openai.target import OpenAITarget

__all__ = [
    "NO_KEY",
    "OPENAI_PRICING",
    "PRICES_READ_ON",
    "OpenAIChat",
    "OpenAIClaimJudge",
    "OpenAIJudge",
    "OpenAITarget",
    "free",
]
