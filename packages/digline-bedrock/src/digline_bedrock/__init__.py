"""Amazon Bedrock target and judges for digline, on the Converse API.

Installed beside digline, never inside it: `pip install digline` must not pull
somebody's HTTP client along with it.

A plugin is a target **and** a judge (ADR 0004), so a suite generates and judges
inside one AWS account, in one region, under one IAM role — which for Bedrock is
usually the whole reason the model is there.

No credential ever reaches this package: the chain is boto3's job.
"""

from digline_bedrock.client import BedrockCallFailed, BedrockChat, scrub
from digline_bedrock.judge import BedrockClaimJudge, BedrockJudge
from digline_bedrock.pricing import (
    BASE_PRICES,
    PRICES_READ_ON,
    SEEDED_REGIONS,
    bedrock_pricing,
    free,
)
from digline_bedrock.target import BedrockTarget

__all__ = [
    "BASE_PRICES",
    "PRICES_READ_ON",
    "SEEDED_REGIONS",
    "BedrockCallFailed",
    "BedrockChat",
    "BedrockClaimJudge",
    "BedrockJudge",
    "BedrockTarget",
    "bedrock_pricing",
    "free",
    "scrub",
]
