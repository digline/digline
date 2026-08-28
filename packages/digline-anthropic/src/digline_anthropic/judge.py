"""The two judges, on the same SDK as the target.

`AnthropicJudge` satisfies `digline.core.Judge` and `AnthropicClaimJudge`
satisfies `ClaimJudge`. Both protocols, because they answer different questions
and `Faithfulness` needs the second one (ADR 0004 §1).

Everything that is not the provider is in `digline.targets.JudgeBase`: the
system prompt, the timing, the pricing, the lenient parsing and the validated
reply. What is here is `_complete` and a constructor.
"""

from __future__ import annotations

from typing import Any

from digline.targets import ClaimCountJudge, JudgeBase, Pricing, ScoreJudge, Usage
from digline_anthropic.client import build_client, text_of, usage_of
from digline_anthropic.pricing import ANTHROPIC_PRICING

__all__ = ["AnthropicClaimJudge", "AnthropicJudge"]

#: Enough for the object we ask for, with room for the sentence in it. A small
#: model is usually the better judge anyway: it is the one you can afford to
#: call five times per case.
DEFAULT_MAX_TOKENS = 400

#: `"{"` in the assistant's mouth is how you get JSON out of this API — the
#: same trick `AnthropicTarget` exposes as `prefill`, applied here to the one
#: reply shape we control ourselves. The reply *is* the prefill plus the
#: completion, so it is prepended before parsing (friction 27).
JSON_PREFILL = "{"


class _AnthropicJudge(JudgeBase):
    """The client half of both judges.

    A mixin over `JudgeBase` rather than a second copy of this constructor:
    `AnthropicJudge` and `AnthropicClaimJudge` differ only in the question they
    ask and the shape they return, both of which already live in the two base
    classes. `super().__init__` here reaches `ScoreJudge`/`ClaimCountJudge` and
    through them `JudgeBase` — cooperative inheritance, which is the Python
    idiom that lets one `__init__` serve two hierarchies without either one
    knowing about the other.
    """

    def __init__(
        self,
        model: str,
        *,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        temperature: float | None = None,
        prefill: str | None = JSON_PREFILL,
        pricing: Pricing = ANTHROPIC_PRICING,
        client: Any = None,
    ) -> None:
        super().__init__(
            model,
            max_tokens=max_tokens,
            pricing=pricing,
            temperature=temperature,
        )
        self.prefill = prefill
        self._injected = client

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}(model={self.model!r}, calls={self.calls}, "
            f"spent_usd={self.spent_usd:.6f})"
        )

    def _client(self) -> Any:
        if self._injected is None:
            self._injected = build_client()
        return self._injected

    def _complete(self, system: str, prompt: str) -> tuple[str, Usage]:
        messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]
        if self.prefill is not None:
            messages.append({"role": "assistant", "content": self.prefill})
        request: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "system": system,
            "messages": messages,
        }
        if self.temperature is not None:
            request["temperature"] = self.temperature

        reply = self._client().messages.create(**request)
        text = text_of(reply)
        if self.prefill is not None:
            text = self.prefill + text
        return text, usage_of(reply)


class AnthropicJudge(_AnthropicJudge, ScoreJudge):
    """`(prompt) -> JudgeReply`. Satisfies `digline.core.Judge`.

        judge = AnthropicJudge(model="claude-haiku-4-5")
        LlmRubric(rubric="...", judge=judge, threshold=0.8, tolerance=0.05)

    `judge.calls`, `judge.spent_usd` and `judge.latency_ms` say what judging has
    cost since the object was built. They are never reset (ADR 0004 §3).
    """


class AnthropicClaimJudge(_AnthropicJudge, ClaimCountJudge):
    """`(prompt) -> ClaimReply`. Satisfies `digline.core.ClaimJudge`.

        Faithfulness(judge=AnthropicClaimJudge(model="claude-haiku-4-5"),
                     threshold=0.9, tolerance=0.05)

    Two counts, not a fraction: the core does the division, so the arithmetic
    is in the one place that can be tested.
    """
