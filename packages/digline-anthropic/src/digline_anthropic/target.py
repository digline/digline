"""`AnthropicTarget`: a prompt file and a model, priced.

Everything that is not Anthropic-specific is in `digline.targets.ProviderTarget`
— composing the prompt, timing the call, pricing the tokens, building the
`Response`. What is left here is one method.

**No key in the code.** The SDK reads `ANTHROPIC_API_KEY` from the environment,
and this file never names it: a key that a suite could set is a key that ends up
in a repository. The client is built on first use and can be injected, which is
what lets the tests run with no SDK installed and no network at all.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from digline.targets import Pricing, ProviderTarget, Usage
from digline_anthropic.client import build_client, text_of, usage_of
from digline_anthropic.pricing import ANTHROPIC_PRICING

__all__ = ["AnthropicTarget"]


class AnthropicTarget(ProviderTarget):
    """One prompt file, one model, one call per case.

        target = AnthropicTarget(
            prompt_file=Path(__file__).parent / "prompts/answer.md",
            system_file=Path(__file__).parent / "prompts/system.md",
            model="claude-sonnet-5",
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
        prefill: str | None = None,
        pricing: Pricing = ANTHROPIC_PRICING,
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
            raise ValueError("AnthropicTarget.max_tokens must be at least 1")
        self.max_tokens = max_tokens
        self.temperature = temperature
        #: Text put in the assistant's mouth before it answers — `"{"` is the
        #: usual one, and it is how you get JSON out of a model without asking
        #: it nicely. Prepended to what comes back, because the reply *is* the
        #: prefill plus the completion, and a parser handed only the tail sees
        #: invalid JSON. (friction 27)
        self.prefill = prefill
        self._injected = client

    def _client(self) -> Any:
        """Built on first use. See `digline_anthropic.client.build_client`."""
        if self._injected is None:
            self._injected = build_client()
        return self._injected

    def _complete(self, prompt: str, system: str | None) -> tuple[str, Usage]:
        messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]
        if self.prefill is not None:
            messages.append({"role": "assistant", "content": self.prefill})
        request: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": messages,
        }
        if system is not None:
            request["system"] = system
        if self.temperature is not None:
            request["temperature"] = self.temperature

        reply = self._client().messages.create(**request)
        text = text_of(reply)
        if self.prefill is not None:
            text = self.prefill + text
        return text, usage_of(reply)
