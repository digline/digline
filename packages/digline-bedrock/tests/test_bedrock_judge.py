"""`BedrockJudge` and `BedrockClaimJudge`, with Converse replaced by a stand-in.

The shared half — the parser, the counters, the validation — is tested once in
the core's `tests/test_judge.py`. What is here is the half that is Bedrock's:
the request these judges build, the region they inherit, and the fact that
without any structured-output mode the lenient parser is the whole strategy.

At the bottom, the one test that answers a question no fake can: whether
Converse counts cached input tokens inside `inputTokens` or beside them.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any, cast

import pytest
from _bedrock_fakes import FakeClient, converse_reply

from digline.core import ClaimJudge, EvaluatorInputs, Faithfulness, Judge, LlmRubric
from digline.targets import CLAIM_SYSTEM, SCORE_SYSTEM
from digline_bedrock import BedrockCallFailed, BedrockClaimJudge, BedrockJudge, free

HAIKU = "eu.anthropic.claude-haiku-4-5-20251001-v1:0"


def replying(client: FakeClient, text: str, **kwargs: Any) -> FakeClient:
    client.reply = converse_reply(text, **kwargs)
    return client


def a_judge(client: FakeClient, **kwargs: Any) -> BedrockJudge:
    return BedrockJudge(model=HAIKU, client=client, **kwargs)


def test_the_judge_declares_the_instrument_it_is(client: FakeClient) -> None:
    """Including the region: what was priced is what was called, for a judge
    exactly as for a target (ADR 0005 §4)."""
    assert dict(a_judge(client).config) == {
        "provider": "bedrock",
        "model": HAIKU,
        "max_tokens": 400,
        "region": "eu-west-1",
    }


# -- the protocols ------------------------------------------------------ #


def test_each_judge_is_the_protocol_the_core_declares(client: FakeClient) -> None:
    assert isinstance(a_judge(client), Judge)
    assert isinstance(BedrockClaimJudge(model=HAIKU, client=client), ClaimJudge)


def test_the_two_judges_ask_two_different_questions(client: FakeClient) -> None:
    replying(client, '{"score": 1, "reason": "fine"}')
    a_judge(client)("Output to judge:\nRome.")
    assert client.requests[0]["system"] == [{"text": SCORE_SYSTEM}]

    other = FakeClient()
    replying(other, '{"supported": 1, "total": 2, "reason": "half"}')
    BedrockClaimJudge(model=HAIKU, client=other)("Output to judge:\nRome.")
    assert other.requests[0]["system"] == [{"text": CLAIM_SYSTEM}]


def test_the_prompt_is_passed_through_untouched(client: FakeClient) -> None:
    replying(client, '{"score": 0.5, "reason": "partly"}')
    prompt = "Rubric:\nbe brief\n\nOutput to judge:\nRome, the capital of Italy."
    a_judge(client)(prompt)
    assert client.requests[0]["messages"] == [
        {"role": "user", "content": [{"text": prompt}]}
    ]


# -- reading a reply, with no JSON mode to lean on ---------------------- #


@pytest.mark.parametrize(
    "text",
    [
        '{"score": 0.75, "reason": "cites the passage"}',
        '```json\n{"score": 0.75, "reason": "cites the passage"}\n```',
        'Sure! Here is my judgement:\n{"score": 0.75, "reason": "cites the passage"}',
        '  {"score": "0.75", "reason": "cites the passage"}  ',
        '{"score": 0.75, "reason": "cites the passage"}\nHope that helps!',
    ],
)
def test_a_dirty_reply_is_still_read(client: FakeClient, text: str) -> None:
    """Converse has no `response_format`: the shape is asked for in the system
    prompt and read back leniently. That makes this the ordinary case here, not
    the pathological one."""
    replying(client, text)
    reply = a_judge(client)("Output to judge:\nRome.")
    assert reply.score == pytest.approx(0.75)
    assert reply.reason == "cites the passage"


def test_no_structured_output_parameter_is_ever_sent(client: FakeClient) -> None:
    """Converse would reject one, and inventing a dialect for it in the plugin
    would be a second author for a shape the base owns."""
    replying(client, '{"score": 1, "reason": "fine"}')
    a_judge(client)("p")
    request = client.requests[0]
    assert "response_format" not in request
    assert "responseFormat" not in request


def test_a_reply_with_no_object_raises(client: FakeClient) -> None:
    replying(client, "I would rather not.")
    with pytest.raises(ValueError, match="no JSON object"):
        a_judge(client)("p")


def test_a_missing_reason_raises(client: FakeClient) -> None:
    replying(client, '{"score": 1}')
    with pytest.raises(ValueError, match="no reason"):
        a_judge(client)("p")


def test_the_system_prompt_can_be_recalibrated_by_subclassing(
    client: FakeClient,
) -> None:
    """`system` is a plain `ClassVar`: a model that needs the instruction
    phrased differently is a subclass, not a constructor argument the parser
    cannot promise to read."""

    class Terse(BedrockJudge):
        system = 'Reply with JSON only: {"score": <0..1>, "reason": "..."}'

    replying(client, '{"score": 1, "reason": "fine"}')
    Terse(model=HAIKU, client=client)("p")
    assert client.requests[0]["system"] == [{"text": Terse.system}]


# -- region, price and counters ---------------------------------------- #


def test_the_judge_inherits_the_region_and_its_price_list(client: FakeClient) -> None:
    judge = a_judge(client)
    assert judge.region == "eu-west-1"
    assert judge.pricing.knows(HAIKU)
    assert not judge.pricing.knows(HAIKU.replace("eu.", "us."))


def test_a_judge_with_no_region_fails_at_construction() -> None:
    with pytest.raises(ValueError, match="no region"):
        BedrockJudge(model=HAIKU, client=FakeClient(region=None))


def test_the_counters_accumulate_and_are_never_reset(client: FakeClient) -> None:
    replying(
        client,
        '{"score": 1, "reason": "fine"}',
        input_tokens=1_000_000,
        output_tokens=0,
    )
    judge = a_judge(client)

    judge("p")
    judge("p")
    assert judge.calls == 2
    # claude-haiku-4-5 at 1.0 per million input tokens, twice.
    assert judge.spent_usd == pytest.approx(2.0)
    assert judge.latency_ms > 0

    before = judge.spent_usd
    judge("p")
    assert judge.spent_usd - before == pytest.approx(1.0)


def test_a_call_that_raises_is_not_counted(client: FakeClient) -> None:
    client.raises = RuntimeError("ThrottlingException: slow down")
    judge = a_judge(client)
    with pytest.raises(BedrockCallFailed):
        judge("p")
    assert judge.calls == 0 and judge.spent_usd == 0.0


def test_an_arn_does_not_escape_a_judging_call_either(client: FakeClient) -> None:
    """The judge runs the same scrub as the target: a judging failure lands in
    the same `reason`, in the same committed file."""
    client.raises = RuntimeError(
        "User: arn:aws:sts::123456789012:assumed-role/ci/x is not authorized"
    )
    with pytest.raises(BedrockCallFailed) as caught:
        a_judge(client)("p")
    assert "arn:aws" not in str(caught.value)
    assert "123456789012" not in str(caught.value)


def test_an_unpriced_judge_model_is_refused_before_it_is_used(
    client: FakeClient,
) -> None:
    judge = BedrockJudge(model="anthropic.claude-from-the-future", client=client)
    with pytest.raises(ValueError, match="has no price"):
        judge.preflight()


def test_a_provisioned_judge_has_no_token_price(client: FakeClient) -> None:
    replying(client, '{"score": 1, "reason": "fine"}')
    judge = BedrockJudge(
        model="my-provisioned-arn", client=client, pricing=free("my-provisioned-arn")
    )
    judge.preflight()
    judge("p")
    assert judge.spent_usd == 0.0


def test_the_repr_shows_model_region_and_spend_and_no_credential(
    client: FakeClient,
) -> None:
    judge = a_judge(client)
    printed = repr(judge) + str(judge)
    assert HAIKU in printed and "eu-west-1" in printed and "spent_usd" in printed
    assert "FakeClient" not in printed


# -- through an assertion ----------------------------------------------- #


def test_llm_rubric_with_this_judge_produces_a_verdict(client: FakeClient) -> None:
    replying(client, '{"score": 0.9, "reason": "one sentence, cites the passage"}')
    rubric = LlmRubric(
        rubric="One sentence, and it cites the passage.",
        judge=a_judge(client),
        threshold=0.8,
        tolerance=0.05,
    )
    verdict = rubric(EvaluatorInputs(output="Rome, per the passage."))

    assert verdict.status == "pass"
    assert verdict.score.score == pytest.approx(0.9)
    sent = client.requests[0]["messages"][0]["content"][0]["text"]
    assert sent.rstrip().endswith("Rome, per the passage.")


def test_a_judge_that_blows_up_is_an_error_not_a_failure(client: FakeClient) -> None:
    replying(client, "no JSON here")
    rubric = LlmRubric(
        rubric="One sentence.", judge=a_judge(client), threshold=0.8, tolerance=0.05
    )
    verdict = rubric(EvaluatorInputs(output="Rome."))
    assert verdict.status == "error" and "ValueError" in verdict.reason


def test_faithfulness_with_the_claim_judge_produces_a_verdict(
    client: FakeClient,
) -> None:
    replying(client, '{"supported": 1, "total": 2, "reason": "one is not in the text"}')
    faithful = Faithfulness(
        judge=BedrockClaimJudge(model=HAIKU, client=client),
        threshold=0.9,
        tolerance=0.05,
    )
    verdict = faithful(
        EvaluatorInputs(
            output="The library opens at 9 and has a rooftop bar.",
            context=("The library opens at 9.",),
        )
    )
    assert verdict.status == "fail" and verdict.score.score == pytest.approx(0.5)


# -- the ones that spend money ------------------------------------------ #


LIVE_MODEL = os.environ.get(
    "DIGLINE_BEDROCK_MODEL", "eu.anthropic.claude-haiku-4-5-20251001-v1:0"
)

LIVE = os.environ.get("DIGLINE_LIVE") == "1" and bool(
    os.environ.get("AWS_PROFILE")
    or os.environ.get("AWS_ACCESS_KEY_ID")
    or os.environ.get("AWS_ROLE_ARN")
)


@pytest.mark.live
@pytest.mark.skipif(not LIVE, reason="needs AWS credentials and DIGLINE_LIVE=1")
def test_a_real_judge_scores_and_is_priced() -> None:
    """Proves the system prompt gets a parseable reply out of a real model,
    which is the half no fake can."""
    judge = BedrockJudge(model=LIVE_MODEL)
    reply = judge(
        "Rubric:\nThe answer names a city.\n\nOutput to judge:\nRome, in Italy."
    )
    assert 0.0 <= reply.score <= 1.0 and reply.reason
    assert judge.calls == 1 and judge.spent_usd > 0


@pytest.mark.live
@pytest.mark.skipif(not LIVE, reason="needs AWS credentials and DIGLINE_LIVE=1")
def test_cache_tokens_say_which_convention_converse_follows() -> None:
    """**The measurement.** Run with `-s`: it prints the five numbers.

        AWS_PROFILE=<profile> AWS_REGION=eu-west-1 DIGLINE_LIVE=1 \\
          uv run pytest -m live packages/digline-bedrock -k cache_tokens -s

    Two calls with the same long system prompt and an explicit `cachePoint`: the
    first writes the cache, the second reads it. What is being asked is whether
    the cached tokens are counted **inside** `inputTokens` (the OpenAI
    convention — they must be subtracted before pricing) or **beside** it (the
    Anthropic convention — they must be added).

    The signal is `totalTokens`, which is arithmetic rather than opinion:

    - `total == input + output`                  → cached reads are **inside**;
    - `total == input + output + cacheRead`      → they are **beside**.

    **Run on 2026-08-28, eu-south-1:** `inputTokens=10`, `outputTokens=4`,
    `totalTokens=12016`, `cacheReadInputTokens=12002` — the sum of the three,
    so **beside**, and `CACHE_READS_ARE_INSIDE_INPUT_TOKENS = False` is now the
    measured answer rather than the assumed one.

    Two things that run cost, and that the multiplier below encodes:

    1. **A `cachePoint` under the model's minimum cacheable length is ignored in
       silence** — no error, no cache, `cacheReadInputTokens=0`, and a test that
       looks like it disproved the question when it never asked it. Hence
       `* 2000`: comfortably above the minimum, which is model-specific and in
       the low thousands of tokens. Do not trim it to make the run cheaper.
    2. **`cacheWriteInputTokens=0` on both calls is not a bug.** A cache written
       by an earlier attempt is still warm — the TTL is minutes — so a rerun
       reads without writing. What the assertion needs is a non-zero *read*,
       which is the half that answers the question.

    It asserts against the constant, so a provider that changes its mind fails
    here rather than in a bill.
    """
    import boto3  # pyright: ignore[reportMissingTypeStubs]

    from digline_bedrock.client import CACHE_READS_ARE_INSIDE_INPUT_TOKENS

    client = cast(
        "Any",
        boto3.client("bedrock-runtime"),  # pyright: ignore[reportUnknownMemberType]
    )

    def ask() -> Mapping[str, Any]:
        """The same call twice: the first writes the cache, the second reads it.

        Long enough to be cacheable — the minimum is model-specific and in the
        low thousands of tokens — with an explicit `cachePoint` after it.
        """
        reply: Mapping[str, Any] = client.converse(
            modelId=LIVE_MODEL,
            system=[
                # Note 1 in the docstring: below the minimum cacheable length
                # the cachePoint is dropped without a word. Keep the multiplier.
                {"text": "You are a careful assistant. " * 2000},
                {"cachePoint": {"type": "default"}},
            ],
            messages=[{"role": "user", "content": [{"text": "Say only: ok"}]}],
            inferenceConfig={"maxTokens": 16},
        )
        return reply

    ask()  # writes the cache
    usage: Mapping[str, Any] = ask()["usage"]

    reported_input = int(usage.get("inputTokens", 0))
    output = int(usage.get("outputTokens", 0))
    total = int(usage.get("totalTokens", 0))
    cache_read = int(usage.get("cacheReadInputTokens", 0) or 0)
    cache_write = int(usage.get("cacheWriteInputTokens", 0) or 0)
    print(
        f"\nConverse usage on the second, cached call:\n"
        f"  inputTokens           = {reported_input}\n"
        f"  outputTokens          = {output}\n"
        f"  totalTokens           = {total}\n"
        f"  cacheReadInputTokens  = {cache_read}\n"
        f"  cacheWriteInputTokens = {cache_write}\n"
        f"  input + output             = {reported_input + output}\n"
        f"  input + output + cacheRead = {reported_input + output + cache_read}\n"
    )

    assert cache_read > 0, (
        "nothing was read from cache, so the question was not asked: a "
        "cachePoint below the model's minimum cacheable length is ignored in "
        "silence, so raise the multiplier — or use a model that supports "
        "prompt caching. A cacheWriteInputTokens of 0 is *not* the problem: a "
        "cache warmed by an earlier attempt is read without being rewritten."
    )
    inside = total == reported_input + output
    beside = total == reported_input + output + cache_read
    assert inside != beside, (
        "totalTokens matches neither arrangement, so it cannot settle it — "
        "read the printed numbers and decide by hand"
    )
    assert inside == CACHE_READS_ARE_INSIDE_INPUT_TOKENS, (
        "CACHE_READS_ARE_INSIDE_INPUT_TOKENS is "
        f"{CACHE_READS_ARE_INSIDE_INPUT_TOKENS}, the API says {inside}. Flip "
        "the constant in digline_bedrock.client and write the date of this "
        "measurement in its comment."
    )
