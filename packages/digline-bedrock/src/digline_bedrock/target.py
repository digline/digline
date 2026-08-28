"""`BedrockTarget`: a prompt file and a model, priced in the region it was called.

Everything that is not provider-specific is in `digline.targets.ProviderTarget`
— composing the prompt, timing the call, pricing the tokens, building the
`Response`. What is left here is one method and the region.

**The region is resolved at construction.** Not at the first call: the client is
built (or handed in) in `__init__`, its region is read from
`client.meta.region_name`, and the price list follows from that. A missing
region fails there, before the first paid call, which is what `preflight` exists
to guarantee. The price is the price of the region you actually called — that is
why it is read from the client and not from a default.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from digline.targets import Pricing, ProviderTarget, Usage
from digline_bedrock.client import BedrockChat
from digline_bedrock.pricing import bedrock_pricing

__all__ = ["BedrockTarget"]


class BedrockTarget(ProviderTarget):
    """One prompt file, one model, one Converse call per case.

        target = BedrockTarget(
            prompt_file=Path(__file__).parent / "prompts/answer.md",
            system_file=Path(__file__).parent / "prompts/system.md",
            model="eu.anthropic.claude-sonnet-4-20250514-v1:0",
            max_tokens=1024,
        )

    `model` accepts a model id or an inference profile id — the argument is
    called `model` and not `modelId` because a suite that swaps one provider for
    another should not have to rename its arguments.

    Both files are recorded in every run, so a baseline carries the prompt that
    produced it (ADR 0003).
    """

    def __init__(
        self,
        prompt_file: str | Path,
        model: str,
        max_tokens: int,
        *,
        system: str | None = None,
        system_file: str | Path | None = None,
        temperature: float | None = None,
        region: str | None = None,
        client: Any = None,
        additional_request_fields: Mapping[str, Any] | None = None,
        pricing: Pricing | None = None,
    ) -> None:
        # Before `super().__init__`, because the price list is chosen by the
        # region and the region is only known once the client exists.
        self.chat = BedrockChat(region=region, client=client)
        super().__init__(
            prompt_file,
            model,
            pricing=(
                pricing if pricing is not None else bedrock_pricing(self.chat.region)
            ),
            system=system,
            system_file=system_file,
        )
        if max_tokens < 1:
            raise ValueError("BedrockTarget.max_tokens must be at least 1")
        self.max_tokens = max_tokens
        self.temperature = temperature
        #: Converse's `additionalModelRequestFields` — reasoning budgets, a
        #: `top_k`, anything the model takes and the common API does not name.
        #:
        #: **Not part of `config_hash` today**, exactly like `temperature`,
        #: `model` and `max_tokens`: the fingerprint covers the rules that judge
        #: a run, not the system being judged (ADR 0003 §3). A change here will
        #: **not** be reported as a configuration change, and two runs that
        #: differ only in these fields will read as "same configuration as the
        #: reference". If you need the difference to show, keep the fields in a
        #: file and declare it in `Suite.artifacts` — then the report carries
        #: the diff. ADR 0005 is the open question of recording the system's own
        #: configuration; until it is decided, this sentence is the contract.
        self.additional_request_fields = additional_request_fields

    @property
    def region(self) -> str:
        """The region this target calls, resolved at construction. Read-only:
        what was priced is what was called, and a region that could be
        reassigned after the price list was chosen would break that quietly."""
        return self.chat.region

    def __repr__(self) -> str:
        """Model and region. Never a session, never a credential — a `repr`
        ends up in a traceback, a pytest failure and a log line."""
        return f"{type(self).__name__}(model={self.model!r}, region={self.region!r})"

    def _complete(self, prompt: str, system: str | None) -> tuple[str, Usage]:
        return self.chat.complete(
            model=self.model,
            prompt=prompt,
            system=system,
            max_tokens=self.max_tokens,
            pricing=self.pricing,
            temperature=self.temperature,
            additional_request_fields=self.additional_request_fields,
        )
