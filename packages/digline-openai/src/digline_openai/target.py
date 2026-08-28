"""`OpenAITarget`: a prompt file and a model, priced — at any compatible endpoint.

Everything that is not provider-specific is in `digline.targets.ProviderTarget`
— composing the prompt, timing the call, pricing the tokens, building the
`Response`. What is left here is one method and one argument that earns its
keep: `base_url`.

**Why `base_url` is on the target and not in a second package.** The wire
protocol is the same at api.openai.com, at an Azure deployment, at OpenRouter,
at Groq, at a vLLM in a VPC and at an Ollama on a laptop. A separate plugin per
endpoint would be five copies of this file differing in a string, and — the
part that matters — it would leave a customer running their own model with no
way to evaluate it in their own perimeter. One target, one argument, and the
payload never leaves the network it was generated on.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from digline.targets import Pricing, ProviderTarget, Usage
from digline_openai.client import OpenAIChat, TokenParam
from digline_openai.pricing import OPENAI_PRICING

__all__ = ["OpenAITarget"]


class OpenAITarget(ProviderTarget):
    """One prompt file, one model, one call per case.

        target = OpenAITarget(
            prompt_file=Path(__file__).parent / "prompts/answer.md",
            system_file=Path(__file__).parent / "prompts/system.md",
            model="gpt-5",
            max_tokens=1024,
        )

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
        base_url: str | None = None,
        api_key: str | None = None,
        response_format: Mapping[str, Any] | None = None,
        token_param: TokenParam = "auto",
        extra_body: Mapping[str, Any] | None = None,
        pricing: Pricing = OPENAI_PRICING,
        client: Any = None,
    ) -> None:
        super().__init__(
            prompt_file,
            model,
            pricing=pricing,
            system=system,
            system_file=system_file,
        )
        if max_tokens < 1:
            raise ValueError("OpenAITarget.max_tokens must be at least 1")
        self.max_tokens = max_tokens
        self.temperature = temperature
        #: `{"type": "json_object"}` is how you get JSON out of this API — there
        #: is no assistant prefill here, and asking for one would work on the
        #: official endpoint and behave differently on three others. Sent when
        #: given, dropped and remembered if the provider refuses it, and the
        #: reply is parsed leniently either way (ADR 0004 §4).
        self.response_format = response_format
        self.token_param: TokenParam = token_param
        #: Arguments the SDK never heard of — a routing preference on
        #: OpenRouter, `num_ctx` on Ollama.
        #:
        #: **Not part of `config_hash`**, exactly like `temperature`, `model`
        #: and `max_tokens`: the fingerprint covers the rules that judge a run,
        #: not the system being judged (ADR 0003 §3). Two runs that differ only
        #: here will read as "same configuration as the reference". Keep the
        #: values in a file declared in `Suite.artifacts` if you need the
        #: difference to show; ADR 0005 is the open question.
        self.extra_body = extra_body
        self.chat = OpenAIChat(base_url=base_url, api_key=api_key, client=client)

    def __repr__(self) -> str:
        """Model and endpoint. Never the key — a `repr` ends up in tracebacks."""
        return (
            f"{type(self).__name__}(model={self.model!r}, "
            f"base_url={self.chat.base_url!r})"
        )

    def _complete(self, prompt: str, system: str | None) -> tuple[str, Usage]:
        messages: list[dict[str, Any]] = []
        if system is not None:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return self.chat.complete(
            model=self.model,
            messages=messages,
            max_tokens=self.max_tokens,
            pricing=self.pricing,
            temperature=self.temperature,
            response_format=self.response_format,
            token_param=self.token_param,
            extra_body=self.extra_body,
        )
