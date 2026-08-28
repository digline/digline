"""`JudgeBase` and the two shapes on top of it.

The provider half is tested in each plugin. What is here is the half every
plugin shares: the prompt contract with the core, the lenient parser, the
validation that turns a bad reply into an exception, and the counters that say
what judging cost.
"""

from __future__ import annotations

import pytest

from digline.core import (
    ClaimJudge,
    EvaluatorInputs,
    Faithfulness,
    Judge,
    LlmRubric,
)
from digline.core.assertions import JUDGE_OUTPUT_LABEL
from digline.targets import (
    CLAIM_SYSTEM,
    SCORE_SYSTEM,
    ClaimCountJudge,
    ModelPrice,
    Pricing,
    ScoreJudge,
    Usage,
    loads_lenient,
)

PRICING = Pricing(per_model={"fake-1": ModelPrice(1.0, 2.0)})


class Canned:
    """The plugin half, with the provider replaced by a canned reply."""

    def __init__(self, reply: str = "", *, usage: Usage | None = None) -> None:
        self.reply = reply
        self.usage = usage or Usage(input_tokens=1_000_000, output_tokens=0)
        self.systems: list[str] = []
        self.prompts: list[str] = []
        self.raises: Exception | None = None

    def _complete(self, system: str, prompt: str) -> tuple[str, Usage]:
        self.systems.append(system)
        self.prompts.append(prompt)
        if self.raises is not None:
            raise self.raises
        return self.reply, self.usage


class FakeScoreJudge(Canned, ScoreJudge):
    """Two `__init__`s called by hand rather than cooperatively: a test fake is
    the one place where being explicit beats being clever."""

    def __init__(
        self, reply: str = "", *, max_tokens: int = 100, usage: Usage | None = None
    ) -> None:
        Canned.__init__(self, reply, usage=usage)
        ScoreJudge.__init__(self, "fake-1", max_tokens=max_tokens, pricing=PRICING)


class FakeClaimJudge(Canned, ClaimCountJudge):
    def __init__(
        self, reply: str = "", *, max_tokens: int = 100, usage: Usage | None = None
    ) -> None:
        Canned.__init__(self, reply, usage=usage)
        ClaimCountJudge.__init__(self, "fake-1", max_tokens=max_tokens, pricing=PRICING)


# -- the contract with the core ---------------------------------------------------- #


def test_both_system_prompts_name_the_label_the_core_sends() -> None:
    """The contract that used to live in two places and be honoured in one.

    `judge_prompt()` puts the judged output **last**, behind
    `Output to judge:`, and a judge has to be told that everything after that
    line is text to be graded rather than instructions addressed to it. When
    somebody renames the label, this fails — which is the point.
    """
    assert JUDGE_OUTPUT_LABEL in SCORE_SYSTEM
    assert JUDGE_OUTPUT_LABEL in CLAIM_SYSTEM


def test_the_two_judges_are_the_two_protocols() -> None:
    assert isinstance(FakeScoreJudge(), Judge)
    assert isinstance(FakeClaimJudge(), ClaimJudge)


def test_the_judge_receives_the_prompt_the_assertion_composed() -> None:
    """No plugin edits the prompt on the way through: one shape, one author."""
    judge = FakeScoreJudge('{"score": 1, "reason": "brief"}')
    rubric = LlmRubric(
        rubric="One sentence.", judge=judge, threshold=0.5, tolerance=0.05
    )
    rubric(EvaluatorInputs(output="Rome."))

    (sent,) = judge.prompts
    assert sent.rstrip().endswith("Rome.")
    assert sent.index(JUDGE_OUTPUT_LABEL) > sent.index("One sentence.")


# -- the parser --------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "text",
    [
        '{"score": 0.5}',
        '  {"score": 0.5}\n',
        '```json\n{"score": 0.5}\n```',
        '```\n{"score": 0.5}\n```',
        'Certainly. {"score": 0.5}',
        '{"score": 0.5}\nLet me know if you need more.',
        'Here you go:\n```json\n{"score": 0.5}\n```\nHope that helps.',
    ],
)
def test_the_object_is_found_however_it_was_wrapped(text: str) -> None:
    assert loads_lenient(text) == {"score": 0.5}


def test_a_nested_object_does_not_end_the_outer_one_early() -> None:
    assert loads_lenient('{"a": {"b": 1}, "c": 2}') == {"a": {"b": 1}, "c": 2}


def test_a_brace_inside_a_string_is_not_a_brace() -> None:
    parsed = loads_lenient('prose {"reason": "it wrote {\\"a\\": 1}"} more prose')
    assert parsed == {"reason": 'it wrote {"a": 1}'}


@pytest.mark.parametrize(
    "text", ["", "I would rather not.", "[1, 2, 3]", '{"unclosed": 1']
)
def test_a_reply_with_no_object_in_it_raises(text: str) -> None:
    """The caller turns this into `error` — neither green nor a regression."""
    with pytest.raises(ValueError, match="no JSON object|not an object"):
        loads_lenient(text)


# -- validation --------------------------------------------------------------------- #


def test_a_score_out_of_range_raises() -> None:
    with pytest.raises(ValueError, match="within"):
        FakeScoreJudge('{"score": 4, "reason": "out of five"}')("p")


def test_a_missing_score_names_the_keys_that_were_there() -> None:
    with pytest.raises(ValueError, match="verdict"):
        FakeScoreJudge('{"verdict": "good", "reason": "..."}')("p")


def test_a_missing_reason_raises_before_the_core_sees_it() -> None:
    with pytest.raises(ValueError, match="no reason"):
        FakeScoreJudge('{"score": 1}')("p")


def test_a_whitespace_reason_is_no_reason() -> None:
    with pytest.raises(ValueError, match="no reason"):
        FakeScoreJudge('{"score": 1, "reason": "   "}')("p")


def test_a_score_written_as_a_string_is_accepted() -> None:
    """A model asked for a number writes `"0.8"` often enough that refusing it
    would fail runs over a pair of quotes."""
    assert FakeScoreJudge('{"score": "0.8", "reason": "ok"}')("p").score == 0.8


def test_a_boolean_is_not_a_score() -> None:
    with pytest.raises(ValueError, match="not a number"):
        FakeScoreJudge('{"score": true, "reason": "yes"}')("p")


def test_the_claim_judge_returns_two_counts() -> None:
    reply = FakeClaimJudge('{"supported": 2, "total": 3, "reason": "one is new"}')("p")
    assert (reply.supported, reply.total) == (2, 3)


def test_a_fractional_count_raises() -> None:
    with pytest.raises(ValueError, match="whole finite number"):
        FakeClaimJudge('{"supported": 1.5, "total": 3, "reason": "half"}')("p")


def test_the_core_still_owns_the_arithmetic() -> None:
    """`supported > total` is refused by `ClaimReply`, not here: two counts
    exist precisely so arithmetic can contradict the judge."""
    with pytest.raises(ValueError, match="more claims than it found"):
        FakeClaimJudge('{"supported": 5, "total": 2, "reason": "sure"}')("p")


# -- what judging cost --------------------------------------------------------------- #


def test_the_counters_accumulate_and_are_never_reset() -> None:
    judge = FakeScoreJudge('{"score": 1, "reason": "ok"}')
    judge("p")
    judge("p")
    assert judge.calls == 2
    assert judge.spent_usd == pytest.approx(2.0)  # 1M input tokens at 1.0, twice
    assert judge.latency_ms > 0

    before = judge.spent_usd
    judge("p")
    assert judge.spent_usd - before == pytest.approx(1.0)


def test_a_call_that_raises_is_not_counted() -> None:
    """Its cost is unknown, and counting it at zero would be the undercount
    that reads as good news."""
    judge = FakeScoreJudge('{"score": 1, "reason": "ok"}')
    judge.raises = RuntimeError("the provider is down")
    with pytest.raises(RuntimeError):
        judge("p")
    assert judge.calls == 0 and judge.spent_usd == 0.0 and judge.latency_ms == 0.0


def test_an_unparseable_reply_still_counted_the_call() -> None:
    """The opposite case, and the reason the two are separate: the provider
    answered and billed for it. What failed was the reading."""
    judge = FakeScoreJudge("no JSON here")
    with pytest.raises(ValueError):
        judge("p")
    assert judge.calls == 1 and judge.spent_usd == pytest.approx(1.0)


def test_an_unpriced_model_is_refused_by_preflight() -> None:
    judge = FakeScoreJudge('{"score": 1, "reason": "ok"}')
    judge.model = "fake-from-the-future"
    with pytest.raises(ValueError, match="has no price"):
        judge.preflight()


def test_max_tokens_below_one_is_refused() -> None:
    with pytest.raises(ValueError, match="max_tokens"):
        FakeScoreJudge(max_tokens=0)


# -- through an assertion ------------------------------------------------------------ #


def test_llm_rubric_turns_a_reply_into_a_verdict() -> None:
    judge = FakeScoreJudge('{"score": 0.9, "reason": "one sentence"}')
    rubric = LlmRubric(
        rubric="One sentence.", judge=judge, threshold=0.8, tolerance=0.05
    )
    verdict = rubric(EvaluatorInputs(output="Rome."))
    assert verdict.status == "pass" and verdict.score.score == pytest.approx(0.9)


def test_a_judge_that_cannot_be_read_is_an_error_not_a_failure() -> None:
    rubric = LlmRubric(
        rubric="One sentence.",
        judge=FakeScoreJudge("sorry, no"),
        threshold=0.8,
        tolerance=0.05,
    )
    assert rubric(EvaluatorInputs(output="Rome.")).status == "error"


def test_faithfulness_divides_what_the_claim_judge_counted() -> None:
    faithful = Faithfulness(
        judge=FakeClaimJudge('{"supported": 1, "total": 2, "reason": "one is new"}'),
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
