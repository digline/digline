"""The two judges, on the same client as the target.

`OpenAIJudge` satisfies `digline.core.Judge` and `OpenAIClaimJudge` satisfies
`ClaimJudge`. Both protocols, because they answer different questions and
`Faithfulness` — the assertion with the strongest reason to run inside the
perimeter, since it is handed the retrieved context too — needs the second one
(ADR 0004 §1).

Everything that is not the provider is in `digline.targets.JudgeBase`: the
system prompt, the timing, the pricing, the lenient parsing and the validated
reply. What is here is `_complete` and a constructor, twice over one shared
half.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from digline.targets import ClaimCountJudge, JudgeBase, Pricing, ScoreJudge, Usage
from digline_openai.client import OpenAIChat, TokenParam
from digline_openai.pricing import OPENAI_PRICING

__all__ = ["OpenAIClaimJudge", "OpenAIJudge"]

#: Enough for the object we ask for, with room for the sentence in it. Raise it
#: for a **reasoning** model — gpt-5 and the o-series spend this budget on
#: thinking before they write anything, and a judge that runs out mid-thought
#: returns empty text, which is an `error` and not a judgement. A small
#: non-reasoning model is usually the better judge anyway: it is the one you can
#: afford to call five times per case.
DEFAULT_MAX_TOKENS = 400

#: What we ask for when the provider supports it. Never required: a provider
#: that refuses it is retried once without it and the reply is read leniently
#: (ADR 0004 §4).
JSON_OBJECT: Mapping[str, Any] = {"type": "json_object"}


class _OpenAIJudge(JudgeBase):
    """The client half of both judges.

    A mixin over `JudgeBase` rather than a second copy of this constructor:
    `OpenAIJudge` and `OpenAIClaimJudge` differ only in the question they ask
    and the shape they return, both of which already live in the two base
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
        base_url: str | None = None,
        api_key: str | None = None,
        json_mode: bool = True,
        token_param: TokenParam = "auto",
        extra_body: Mapping[str, Any] | None = None,
        pricing: Pricing = OPENAI_PRICING,
        client: Any = None,
    ) -> None:
        super().__init__(
            model,
            max_tokens=max_tokens,
            pricing=pricing,
            temperature=temperature,
        )
        self.json_mode = json_mode
        self.token_param: TokenParam = token_param
        self.extra_body = extra_body
        self.chat = OpenAIChat(base_url=base_url, api_key=api_key, client=client)

    def __repr__(self) -> str:
        """Model, endpoint and what it has spent. Never the key."""
        return (
            f"{type(self).__name__}(model={self.model!r}, "
            f"base_url={self.chat.base_url!r}, calls={self.calls}, "
            f"spent_usd={self.spent_usd:.6f})"
        )

    def _complete(self, system: str, prompt: str) -> tuple[str, Usage]:
        return self.chat.complete(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            max_tokens=self.max_tokens,
            pricing=self.pricing,
            temperature=self.temperature,
            response_format=JSON_OBJECT if self.json_mode else None,
            token_param=self.token_param,
            extra_body=self.extra_body,
        )


class OpenAIJudge(_OpenAIJudge, ScoreJudge):
    """`(prompt) -> JudgeReply`. Satisfies `digline.core.Judge`.

        judge = OpenAIJudge(model="gpt-5-mini")
        LlmRubric(rubric="...", judge=judge, threshold=0.8, tolerance=0.05)

    `judge.calls`, `judge.spent_usd` and `judge.latency_ms` say what judging has
    cost since the object was built. They are never reset (ADR 0004 §3).
    """


class OpenAIClaimJudge(_OpenAIJudge, ClaimCountJudge):
    """`(prompt) -> ClaimReply`. Satisfies `digline.core.ClaimJudge`.

        Faithfulness(judge=OpenAIClaimJudge(model="gpt-5-mini"),
                     threshold=0.9, tolerance=0.05)

    Two counts, not a fraction: the core does the division, so the arithmetic
    is in the one place that can be tested.
    """
