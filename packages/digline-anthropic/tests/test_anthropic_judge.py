"""`AnthropicJudge` and `AnthropicClaimJudge`, with the SDK replaced by a stand-in.

The shared half — the parser, the counters, the validation — is tested once in
the core's `tests/test_judge.py`. What is checked here is the half that is
Anthropic's: the request these judges build, and the prefill that has to be
prepended before anything can be parsed at all.
"""

from __future__ import annotations

import importlib.util
import os
from dataclasses import dataclass, field
from typing import Any

import pytest

from digline.core import ClaimJudge, EvaluatorInputs, Faithfulness, Judge, LlmRubric
from digline.targets import CLAIM_SYSTEM, SCORE_SYSTEM
from digline_anthropic import AnthropicClaimJudge, AnthropicJudge


@dataclass
class FakeBlock:
    text: str
    type: str = "text"


@dataclass
class FakeUsage:
    input_tokens: int = 1_000_000
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0


@dataclass
class FakeReply:
    content: list[FakeBlock]
    usage: FakeUsage = field(default_factory=FakeUsage)


class FakeMessages:
    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []
        self.reply = FakeReply(content=[FakeBlock('"score": 1, "reason": "fine"}')])
        self.raises: Exception | None = None

    def create(self, **kwargs: Any) -> FakeReply:
        self.requests.append(kwargs)
        if self.raises is not None:
            raise self.raises
        return self.reply


class FakeClient:
    def __init__(self) -> None:
        self.messages = FakeMessages()


@pytest.fixture
def client() -> FakeClient:
    return FakeClient()


def replying(client: FakeClient, text: str) -> None:
    client.messages.reply = FakeReply(content=[FakeBlock(text)])


def a_judge(client: FakeClient, **kwargs: Any) -> AnthropicJudge:
    return AnthropicJudge(model="claude-haiku-4-5", client=client, **kwargs)


def test_each_judge_is_the_protocol_the_core_declares(client: FakeClient) -> None:
    assert isinstance(a_judge(client), Judge)
    assert isinstance(
        AnthropicClaimJudge(model="claude-haiku-4-5", client=client), ClaimJudge
    )


def test_the_two_judges_ask_two_different_questions(client: FakeClient) -> None:
    a_judge(client)("Output to judge:\nRome.")
    assert client.messages.requests[0]["system"] == SCORE_SYSTEM

    other = FakeClient()
    replying(other, '"supported": 1, "total": 2, "reason": "half"}')
    AnthropicClaimJudge(model="claude-haiku-4-5", client=other)("Output to judge:\nx")
    assert other.messages.requests[0]["system"] == CLAIM_SYSTEM


def test_the_prefill_is_sent_and_prepended_before_parsing(client: FakeClient) -> None:
    """The reply *is* the prefill plus the completion: a parser handed only the
    tail sees invalid JSON (friction 27). Here the model returns
    `"score": 1, …}` and only the `{` we put in its mouth completes it."""
    reply = a_judge(client)("p")

    messages = client.messages.requests[0]["messages"]
    assert messages[-1] == {"role": "assistant", "content": "{"}
    assert reply.score == 1.0 and reply.reason == "fine"


def test_without_a_prefill_the_reply_stands_on_its_own(client: FakeClient) -> None:
    """Some replies arrive as a whole object anyway, and the parser is lenient
    enough that turning the prefill off is a supported choice rather than a
    broken one."""
    replying(client, 'Sure!\n```json\n{"score": 0.5, "reason": "partly"}\n```')
    reply = a_judge(client, prefill=None)("p")

    roles = [m["role"] for m in client.messages.requests[0]["messages"]]
    assert roles == ["user"]
    assert reply.score == 0.5


def test_an_unset_temperature_is_not_sent(client: FakeClient) -> None:
    a_judge(client)("p")
    assert "temperature" not in client.messages.requests[0]


def test_the_counters_accumulate(client: FakeClient) -> None:
    judge = a_judge(client)
    judge("p")
    judge("p")
    assert judge.calls == 2
    # claude-haiku-4-5 at 1.0 per million input tokens, twice.
    assert judge.spent_usd == pytest.approx(2.0)
    assert judge.latency_ms > 0


def test_a_call_that_raises_is_not_counted(client: FakeClient) -> None:
    client.messages.raises = RuntimeError("the provider is down")
    judge = a_judge(client)
    with pytest.raises(RuntimeError):
        judge("p")
    assert judge.calls == 0 and judge.spent_usd == 0.0


def test_a_cache_write_is_priced_on_a_judging_call_too(client: FakeClient) -> None:
    """The same friction-25 arithmetic as the target: cached writes are not in
    `input_tokens`, and a judge called five times per case writes a lot of
    cache."""
    client.messages.reply = FakeReply(
        content=[FakeBlock('"score": 1, "reason": "fine"}')],
        usage=FakeUsage(
            input_tokens=10, output_tokens=4, cache_creation_input_tokens=9202
        ),
    )
    judge = a_judge(client)
    judge("p")
    # 10 in + 4 out + 9202 written at 1.25/Mtok.
    assert judge.spent_usd == pytest.approx(0.011532, abs=1e-6)


def test_an_unpriced_judge_model_is_refused(client: FakeClient) -> None:
    judge = AnthropicJudge(model="claude-from-the-future", client=client)
    with pytest.raises(ValueError, match="has no price"):
        judge.preflight()


def test_a_tool_use_block_is_not_part_of_the_reply(client: FakeClient) -> None:
    client.messages.reply = FakeReply(
        content=[
            FakeBlock('"score": 1, "reason": "fine"}', "text"),
            FakeBlock("ignored", "tool_use"),
        ]
    )
    assert a_judge(client)("p").reason == "fine"


def test_llm_rubric_with_this_judge_produces_a_verdict(client: FakeClient) -> None:
    replying(client, '"score": 0.9, "reason": "one sentence"}')
    rubric = LlmRubric(
        rubric="One sentence.", judge=a_judge(client), threshold=0.8, tolerance=0.05
    )
    verdict = rubric(EvaluatorInputs(output="Rome."))
    assert verdict.status == "pass" and verdict.score.score == pytest.approx(0.9)


def test_faithfulness_with_the_claim_judge_produces_a_verdict(
    client: FakeClient,
) -> None:
    replying(client, '"supported": 1, "total": 2, "reason": "one is new"}')
    faithful = Faithfulness(
        judge=AnthropicClaimJudge(model="claude-haiku-4-5", client=client),
        threshold=0.9,
        tolerance=0.05,
    )
    verdict = faithful(
        EvaluatorInputs(
            output="It opens at 9 and has a rooftop bar.",
            context=("It opens at 9.",),
        )
    )
    assert verdict.status == "fail" and verdict.score.score == pytest.approx(0.5)


def test_the_sdk_is_imported_only_when_a_call_is_made(client: FakeClient) -> None:
    import sys

    assert "anthropic" not in sys.modules
    AnthropicJudge(model="claude-haiku-4-5", client=client).preflight()
    assert "anthropic" not in sys.modules


def sdk_installed() -> bool:
    return importlib.util.find_spec("anthropic") is not None


LIVE = (
    bool(os.environ.get("ANTHROPIC_API_KEY")) and os.environ.get("DIGLINE_LIVE") == "1"
)


@pytest.mark.live
@pytest.mark.skipif(
    not LIVE or not sdk_installed(),
    reason="needs ANTHROPIC_API_KEY, DIGLINE_LIVE=1 and the anthropic SDK",
)
def test_a_real_judge_scores_and_is_priced() -> None:
    """The one judging test that spends money: it proves the system prompt gets
    a parseable reply out of a real model, which is the half no fake can."""
    judge = AnthropicJudge(model="claude-haiku-4-5-20251001")
    reply = judge(
        "Rubric:\nThe answer names a city.\n\nOutput to judge:\nRome, in Italy."
    )
    assert 0.0 <= reply.score <= 1.0 and reply.reason
    assert judge.calls == 1 and judge.spent_usd > 0
