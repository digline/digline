"""The two judges, on the same client and in the same region as the target.

`BedrockJudge` satisfies `digline.core.Judge` and `BedrockClaimJudge` satisfies
`ClaimJudge` (ADR 0004 §1). Everything that is not the provider is in
`digline.targets.JudgeBase`: the system prompt, the timing, the pricing, the
lenient parsing and the validated reply.

**No structured-output mode.** Converse has no `response_format`: the reply
shape is asked for in the system prompt and read back by `loads_lenient`, which
is the same parser that already carries an Ollama refusing JSON mode. If a
model on your account needs the instruction phrased differently, `system` is a
plain `ClassVar` — subclass and override it, rather than teaching the base a
provider's dialect.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from digline.targets import ClaimCountJudge, JudgeBase, Pricing, ScoreJudge, Usage
from digline_bedrock.client import BedrockChat
from digline_bedrock.pricing import bedrock_pricing

__all__ = ["BedrockClaimJudge", "BedrockJudge"]

#: Enough for the object we ask for, with room for the sentence in it. Raise it
#: for a model that reasons before answering — the budget is spent on thinking
#: first, and a judge that runs out mid-thought returns empty text, which is an
#: `error` and not a judgement.
DEFAULT_MAX_TOKENS = 400


class _BedrockJudge(JudgeBase):
    """The client half of both judges.

    A mixin over `JudgeBase` rather than a second copy of this constructor:
    `BedrockJudge` and `BedrockClaimJudge` differ only in the question they ask
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
        region: str | None = None,
        client: Any = None,
        additional_request_fields: Mapping[str, Any] | None = None,
        pricing: Pricing | None = None,
    ) -> None:
        # Before `super().__init__`, for the same reason as in the target: the
        # price list is chosen by the region, and the region comes from the
        # client. A judge with no region fails here, not mid-run.
        self.chat = BedrockChat(region=region, client=client)
        super().__init__(
            model,
            max_tokens=max_tokens,
            pricing=(
                pricing if pricing is not None else bedrock_pricing(self.chat.region)
            ),
            temperature=temperature,
        )
        #: Same contract as on the target: **not part of `config_hash`**, so a
        #: change here is not reported as a configuration change (ADR 0003 §3,
        #: and ADR 0005 for the open question).
        self.additional_request_fields = additional_request_fields

    @property
    def region(self) -> str:
        """Resolved at construction. What was priced is what was called."""
        return self.chat.region

    def __repr__(self) -> str:
        """Model, region and what it has spent. Never a session or a credential."""
        return (
            f"{type(self).__name__}(model={self.model!r}, region={self.region!r}, "
            f"calls={self.calls}, spent_usd={self.spent_usd:.6f})"
        )

    def _complete(self, system: str, prompt: str) -> tuple[str, Usage]:
        return self.chat.complete(
            model=self.model,
            prompt=prompt,
            system=system,
            max_tokens=self.max_tokens,
            pricing=self.pricing,
            temperature=self.temperature,
            additional_request_fields=self.additional_request_fields,
        )


class BedrockJudge(_BedrockJudge, ScoreJudge):
    """`(prompt) -> JudgeReply`. Satisfies `digline.core.Judge`.

        judge = BedrockJudge(model="eu.anthropic.claude-haiku-4-5-20251001-v1:0")
        LlmRubric(rubric="...", judge=judge, threshold=0.8, tolerance=0.05)

    `judge.calls`, `judge.spent_usd` and `judge.latency_ms` say what judging has
    cost since the object was built. They are never reset (ADR 0004 §3).
    """


class BedrockClaimJudge(_BedrockJudge, ClaimCountJudge):
    """`(prompt) -> ClaimReply`. Satisfies `digline.core.ClaimJudge`.

        Faithfulness(judge=BedrockClaimJudge(model="eu.anthropic.claude-haiku-4-5-20251001-v1:0"),
                     threshold=0.9, tolerance=0.05)

    Two counts, not a fraction: the core does the division, so the arithmetic
    is in the one place that can be tested.
    """
