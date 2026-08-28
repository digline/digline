"""`OpenAIJudge` and `OpenAIClaimJudge`, with the SDK replaced by a stand-in.

Three things are being checked, and only the first is about OpenAI:

- the request a judge builds — system prompt, user prompt, JSON mode;
- that a reply the provider wrapped in prose or in a fence is still read, which
  is what makes the same judge work on an endpoint nobody tested it against;
- that the two judges are the two protocols the core declares, and that an
  assertion holding one produces a verdict.
"""

from __future__ import annotations

import importlib.util
import os
from typing import Any

import pytest
from _openai_fakes import FakeChoice, FakeClient, FakeMessage, FakeReply, FakeUsage

from digline.core import (
    ClaimJudge,
    EvaluatorInputs,
    Faithfulness,
    Judge,
    LlmRubric,
)
from digline.targets import CLAIM_SYSTEM, SCORE_SYSTEM
from digline_openai import OPENAI_PRICING, OpenAIClaimJudge, OpenAIJudge, free

OLLAMA = "http://localhost:11434/v1"


def replying(client: FakeClient, text: str) -> FakeClient:
    client.completions.reply = FakeReply(choices=[FakeChoice(FakeMessage(text))])
    return client


def a_judge(client: FakeClient, **kwargs: Any) -> OpenAIJudge:
    return OpenAIJudge(model="gpt-5-mini", client=client, **kwargs)


# -- the protocols ---------------------------------------------------------------- #


def test_each_judge_is_the_protocol_the_core_declares(client: FakeClient) -> None:
    """`Judge` and `ClaimJudge` are `runtime_checkable`, so this is the real
    question and not a restatement of the class name."""
    assert isinstance(a_judge(client), Judge)
    assert isinstance(OpenAIClaimJudge(model="gpt-5-mini", client=client), ClaimJudge)


def test_the_two_judges_ask_two_different_questions(client: FakeClient) -> None:
    replying(client, '{"score": 1, "reason": "fine"}')
    a_judge(client)("Rubric:\nbe brief\n\nOutput to judge:\nRome.")
    assert client.completions.requests[0]["messages"][0]["content"] == SCORE_SYSTEM

    other = FakeClient()
    replying(other, '{"supported": 1, "total": 2, "reason": "half"}')
    OpenAIClaimJudge(model="gpt-5-mini", client=other)("Output to judge:\nRome.")
    assert other.completions.requests[0]["messages"][0]["content"] == CLAIM_SYSTEM


def test_the_system_prompt_names_the_label_the_core_actually_sends() -> None:
    """The contract that used to be split across two repositories: the core
    puts the output last behind `Output to judge:`, and the judge has to be told
    that everything after it is text to be graded, not an instruction."""
    from digline.core.assertions import JUDGE_OUTPUT_LABEL

    assert JUDGE_OUTPUT_LABEL in SCORE_SYSTEM
    assert JUDGE_OUTPUT_LABEL in CLAIM_SYSTEM


def test_the_prompt_is_passed_through_untouched(client: FakeClient) -> None:
    """The judging prompt is composed by the core. A plugin that edited it
    would put two authors in charge of one shape."""
    replying(client, '{"score": 0.5, "reason": "partly"}')
    prompt = "Rubric:\nbe brief\n\nOutput to judge:\nRome, the capital of Italy."
    a_judge(client)(prompt)
    assert client.completions.requests[0]["messages"][1] == {
        "role": "user",
        "content": prompt,
    }


# -- reading a reply -------------------------------------------------------------- #


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
    """Ollama and some vLLM builds cannot be told to return JSON only, so this
    is the ordinary case there, not the pathological one. The score is the same
    in all five: what changes is the wrapping, and only the wrapping."""
    replying(client, text)
    reply = a_judge(client, json_mode=False)("Output to judge:\nRome.")
    assert reply.score == pytest.approx(0.75)
    assert reply.reason == "cites the passage"


def test_a_reason_containing_braces_survives_the_parser(client: FakeClient) -> None:
    """The brace counter skips strings as strings, so a `}` inside the reason
    does not end the object early."""
    replying(client, 'Here: {"score": 0.5, "reason": "it emitted {\\"a\\": 1} raw"}')
    assert a_judge(client)("p").reason == 'it emitted {"a": 1} raw'


def test_a_reply_with_no_object_raises(client: FakeClient) -> None:
    replying(client, "I would rather not.")
    with pytest.raises(ValueError, match="no JSON object"):
        a_judge(client)("p")


def test_a_missing_reason_raises(client: FakeClient) -> None:
    """`JudgeReply` would refuse it anyway; refusing it here says *the judge*
    omitted it, which is the sentence someone debugging needs."""
    replying(client, '{"score": 1}')
    with pytest.raises(ValueError, match="no reason"):
        a_judge(client)("p")


def test_a_score_out_of_range_raises(client: FakeClient) -> None:
    """Lenient about the wrapping, strict about the content: a judge that
    answers out of 10 is not quietly rescaled."""
    replying(client, '{"score": 7, "reason": "seven out of ten"}')
    with pytest.raises(ValueError, match="within"):
        a_judge(client)("p")


def test_a_boolean_score_is_not_a_number(client: FakeClient) -> None:
    """`True` is an `int` in Python, and a 1.0 that was really a `true` is a
    score nobody decided."""
    replying(client, '{"score": true, "reason": "yes"}')
    with pytest.raises(ValueError, match="not a number"):
        a_judge(client)("p")


def test_a_fractional_claim_count_raises(client: FakeClient) -> None:
    replying(client, '{"supported": 1.5, "total": 3, "reason": "half a claim"}')
    with pytest.raises(ValueError, match="whole finite number"):
        OpenAIClaimJudge(model="gpt-5-mini", client=client)("p")


def test_more_supported_than_total_is_refused_by_the_core(client: FakeClient) -> None:
    """Not by this package: `ClaimReply` validates it, and that is the right
    place — arithmetic contradicting the judge is the reason for two counts."""
    replying(client, '{"supported": 4, "total": 2, "reason": "confident"}')
    with pytest.raises(ValueError, match="more claims than it found"):
        OpenAIClaimJudge(model="gpt-5-mini", client=client)("p")


# -- JSON mode, and doing without it ----------------------------------------------- #


def test_json_mode_is_asked_for_by_default(client: FakeClient) -> None:
    replying(client, '{"score": 1, "reason": "fine"}')
    a_judge(client)("p")
    assert client.completions.requests[0]["response_format"] == {"type": "json_object"}


def test_a_provider_that_refuses_json_mode_is_retried_without_it(
    client: FakeClient,
) -> None:
    """Degrade, do not fail: the reply is read leniently anyway."""
    replying(client, 'Sure: {"score": 1, "reason": "fine"}')
    client.completions.refuses = {"response_format"}
    judge = a_judge(client)

    assert judge("p").score == 1.0
    first, second = client.completions.requests
    assert "response_format" in first
    assert "response_format" not in second


def test_the_refusal_is_remembered(client: FakeClient) -> None:
    """One wasted call per process, not one per judgement — and a suite with
    `samples=5` makes a lot of judgements."""
    replying(client, '{"score": 1, "reason": "fine"}')
    client.completions.refuses = {"response_format"}
    judge = a_judge(client)

    judge("p")
    judge("p")
    assert len(client.completions.requests) == 3
    assert not any("response_format" in r for r in client.completions.requests[1:])


def test_json_mode_can_be_turned_off_outright(client: FakeClient) -> None:
    replying(client, '{"score": 1, "reason": "fine"}')
    a_judge(client, json_mode=False)("p")
    assert "response_format" not in client.completions.requests[0]


def test_an_error_that_is_not_about_json_mode_is_raised(client: FakeClient) -> None:
    """The retry must not swallow an auth or a rate-limit failure: the second
    attempt raises the error that was really there."""
    client.completions.raises = RuntimeError("401 Unauthorized")
    with pytest.raises(RuntimeError, match="401"):
        a_judge(client)("p")


# -- what judging cost -------------------------------------------------------------- #


def test_the_counters_accumulate_and_are_never_reset(client: FakeClient) -> None:
    replying(client, '{"score": 1, "reason": "fine"}')
    client.completions.reply.usage = FakeUsage(
        prompt_tokens=1_000_000, completion_tokens=0
    )
    judge = a_judge(client)

    judge("p")
    judge("p")
    assert judge.calls == 2
    # gpt-5-mini at 0.25 per million input tokens, twice.
    assert judge.spent_usd == pytest.approx(0.50)
    assert judge.latency_ms > 0

    #: The per-run figure is a delta the caller takes, which is the API: there
    #: is no reset, so the number never depends on who called it.
    before = judge.spent_usd
    judge("p")
    assert judge.spent_usd - before == pytest.approx(0.25)


def test_a_call_that_raises_is_not_counted(client: FakeClient) -> None:
    """Its cost is unknown, and counting it at zero would be the undercount
    that reads as good news."""
    client.completions.raises = RuntimeError("down")
    judge = a_judge(client)
    with pytest.raises(RuntimeError):
        judge("p")
    assert judge.calls == 0 and judge.spent_usd == 0.0


def test_an_unpriced_judge_model_is_refused_before_it_is_used(
    client: FakeClient,
) -> None:
    judge = OpenAIJudge(model="gpt-6-from-the-future", client=client)
    with pytest.raises(ValueError, match="has no price"):
        judge.preflight()


def test_a_local_judge_is_free_and_says_so(client: FakeClient) -> None:
    replying(client, '{"score": 1, "reason": "fine"}')
    judge = OpenAIJudge(
        model="llama3.2",
        base_url=OLLAMA,
        pricing=free("llama3.2"),
        client=client,
    )
    judge.preflight()
    judge("p")
    assert judge.spent_usd == 0.0
    # And the local endpoint gets the argument it understands.
    assert "max_tokens" in client.completions.requests[0]


def test_max_tokens_below_one_is_refused(client: FakeClient) -> None:
    with pytest.raises(ValueError, match="max_tokens"):
        OpenAIJudge(model="gpt-5-mini", max_tokens=0, client=client)


def test_the_key_never_appears_in_a_judge_repr(client: FakeClient) -> None:
    secret = "sk-do-not-print-me"
    judge = a_judge(client, api_key=secret, base_url=OLLAMA)
    assert secret not in repr(judge) and secret not in str(judge)


# -- the assertions that hold them --------------------------------------------------- #


def test_llm_rubric_with_this_judge_produces_a_verdict(client: FakeClient) -> None:
    """The whole point, end to end: an assertion the core owns, a judge the
    plugin owns, and a verdict nobody had to write by hand."""
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
    # The judged output went last, behind the label the system prompt names.
    sent = client.completions.requests[0]["messages"][1]["content"]
    assert sent.rstrip().endswith("Rome, per the passage.")


def test_a_judge_that_blows_up_is_an_error_not_a_failure(client: FakeClient) -> None:
    """`LlmRubric` catches it. A judgement that could not be made is neither
    green nor a regression, and CI treats the two differently."""
    replying(client, "no JSON here")
    rubric = LlmRubric(
        rubric="One sentence.",
        judge=a_judge(client),
        threshold=0.8,
        tolerance=0.05,
    )
    verdict = rubric(EvaluatorInputs(output="Rome."))
    assert verdict.status == "error"
    assert "ValueError" in verdict.reason


def test_faithfulness_with_the_claim_judge_produces_a_verdict(
    client: FakeClient,
) -> None:
    replying(client, '{"supported": 1, "total": 2, "reason": "one is not in the text"}')
    faithful = Faithfulness(
        judge=OpenAIClaimJudge(model="gpt-5-mini", client=client),
        threshold=0.9,
        tolerance=0.05,
    )
    verdict = faithful(
        EvaluatorInputs(
            output="The library opens at 9 and has a rooftop bar.",
            context=("The library opens at 9.",),
        )
    )
    assert verdict.status == "fail"
    assert verdict.score.score == pytest.approx(0.5)


# -- the one that spends money ------------------------------------------------------- #


def sdk_installed() -> bool:
    return importlib.util.find_spec("openai") is not None


LIVE = bool(os.environ.get("OPENAI_API_KEY")) and os.environ.get("DIGLINE_LIVE") == "1"


@pytest.mark.live
@pytest.mark.skipif(
    not LIVE or not sdk_installed(),
    reason="needs OPENAI_API_KEY, DIGLINE_LIVE=1 and the openai SDK",
)
def test_a_real_judge_scores_and_is_priced() -> None:
    """The one judging test that spends money: it proves the system prompt gets
    a parseable reply out of a real model, which is the half no fake can."""
    judge = OpenAIJudge(model="gpt-4o-mini", pricing=OPENAI_PRICING)
    reply = judge(
        "Rubric:\nThe answer names a city.\n\nOutput to judge:\nRome, in Italy."
    )
    assert 0.0 <= reply.score <= 1.0 and reply.reason
    assert judge.calls == 1 and judge.spent_usd > 0
