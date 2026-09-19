"""A judge that says it cannot answer, and the ways it must not be able to.

ADR 0004 §7's test plan. The first test is the one that must never be weakened:
if an abstention were ever reachable by omitting a key, every malformed reply in
the world would become a judge declining — and that reading cannot be told from
the truth.

The rest exist to keep the feature from overselling itself: it changes a
sentence and closes one previously unattributable case. It attributes no side,
moves no exit code and touches no denominator.
"""

from __future__ import annotations

import json
from html import escape

import pytest

from digline.core import (
    CaseResult,
    ClaimReply,
    EvaluatorInputs,
    Faithfulness,
    JudgeAbstained,
    JudgeReply,
    LlmRubric,
    Run,
    Score,
    Verdict,
    combine_samples,
    redact,
)
from digline.core.run import run_to_json
from digline.report import facts, render_run_html
from digline.targets.judge import ABSTAIN_KEY, JudgeBase, ScoreJudge
from digline.targets.pricing import ModelPrice, Pricing, Usage

PRICING = Pricing(
    per_model={"j-1": ModelPrice(input_per_mtok=1.0, output_per_mtok=2.0)}
)


def inputs(**extra: object) -> EvaluatorInputs:
    return EvaluatorInputs(output="an answer", **extra)  # pyright: ignore[reportArgumentType]


def rubric(judge: object) -> LlmRubric:
    return LlmRubric(
        rubric="Is it polite?",
        judge=judge,  # pyright: ignore[reportArgumentType]
        threshold=0.7,
        tolerance=0.05,
    )


def faithfulness(judge: object) -> Faithfulness:
    return Faithfulness(
        judge=judge,  # pyright: ignore[reportArgumentType]
        threshold=0.8,
        tolerance=0.1,
    )


class Replying(JudgeBase):
    """A judge whose provider returns exactly the text a test hands it.

    Subclasses `JudgeBase` rather than faking the parse, because what is under
    test **is** the parse: a double that returned a `JudgeReply` would skip the
    three refusals of ADR 0004 §7.3 entirely.
    """

    provider = "fake"
    system = "unused"

    def __init__(self, payload: object) -> None:
        super().__init__(model="j-1", max_tokens=16, pricing=PRICING)
        self.payload = payload

    def _complete(self, system: str, prompt: str) -> tuple[str, Usage]:
        payload = self.payload
        text = payload if isinstance(payload, str) else json.dumps(payload)
        return text, Usage(input_tokens=10, output_tokens=5)


class Scoring(Replying, ScoreJudge):
    """`ScoreJudge`'s parsing, over a reply the test wrote."""


# --------------------------------------------------------------------------- #
# The line that must never weaken
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("payload", "what"),
    [
        ({"reason": "no idea"}, "a missing score"),
        ({"score": None, "reason": "no idea"}, "a null score"),
        ({"abstain": False, "score": None, "reason": "no idea"}, "abstain false"),
    ],
)
def test_an_abstention_is_unreachable_by_malformation(
    payload: dict[str, object], what: str
) -> None:
    """A judge that never abstains behaves exactly as today, and this is why.

    Each of these is a reply a confused model produces. If any of them became a
    declining, every judge in the world would start declining the first time a
    model dropped a key.
    """
    judge = Scoring(payload)
    with pytest.raises(ValueError) as caught:  # noqa: PT011 — the message is the assertion
        judge("anything")
    assert not isinstance(caught.value, JudgeAbstained), (
        f"{what} became an abstention: a broken reply must stay broken"
    )


def test_a_key_that_is_not_true_or_false_is_a_broken_reply() -> None:
    """A key that accepts anything declares nothing — `_number`'s rule for a
    score that is not a number, applied to a declaration."""
    judge = Scoring({"abstain": "yes", "score": 0.9, "reason": "sure"})
    with pytest.raises(ValueError, match="not true or false") as caught:
        judge("anything")
    assert not isinstance(caught.value, JudgeAbstained)


def test_declining_without_a_reason_is_broken_rather_than_a_declining() -> None:
    """The one place declining is stricter than scoring: a score can be
    contradicted by arithmetic, a declining can only be read."""
    judge = Scoring({"abstain": True, "reason": "   "})
    with pytest.raises(ValueError, match="gave no reason") as caught:
        judge("anything")
    assert not isinstance(caught.value, JudgeAbstained)


# --------------------------------------------------------------------------- #
# A declared abstention is one
# --------------------------------------------------------------------------- #


def test_a_declared_abstention_carries_the_judges_own_sentence() -> None:
    judge = Scoring({"abstain": True, "reason": "the answer is a refusal to help"})
    with pytest.raises(JudgeAbstained, match="refusal to help"):
        judge("anything")


def test_a_reply_that_declines_and_scores_declines() -> None:
    """A judge that declined and then supplied a number has not scored, it has
    decorated — and reading the number would read a value nobody stood behind."""
    judge = Scoring({"abstain": True, "score": 0.9, "reason": "cannot be scored"})
    with pytest.raises(JudgeAbstained):
        judge("anything")


def test_the_key_is_exported_under_its_own_name() -> None:
    """A plugin writing its own parser imports the key rather than guessing it,
    the way `JUDGE_OUTPUT_LABEL` is imported rather than retyped."""
    assert ABSTAIN_KEY == "abstain"


# --------------------------------------------------------------------------- #
# What the assertions do with it
# --------------------------------------------------------------------------- #


def declining(sentence: str) -> object:
    def judge(prompt: str) -> JudgeReply:
        raise JudgeAbstained(sentence)

    return judge


def test_llm_rubric_records_the_declining_and_does_not_say_raised() -> None:
    v = rubric(declining("the output is empty, so there is nothing to score"))(inputs())
    assert v.status == "error"
    assert v.reason == (
        "the judge declined to score: the output is empty, so there is nothing to score"
    )
    assert "raised" not in v.reason, "a declining is not a failure"


def test_a_judge_that_really_raises_is_still_reported_as_raising() -> None:
    """The other half: catching the declining first must not swallow a failure."""

    def broken(prompt: str) -> JudgeReply:
        raise RuntimeError("timeout")

    v = rubric(broken)(inputs())
    assert v.status == "error"
    assert "the judge raised RuntimeError" in v.reason
    assert "declined" not in v.reason


def test_an_abstention_is_not_a_fourth_status() -> None:
    """ADR 0001 fixed three, and `error` is already a judgement that could not
    be given."""
    v = rubric(declining("cannot be scored"))(inputs())
    assert v.status == "error"
    assert v.score.score is None


# --------------------------------------------------------------------------- #
# Faithfulness: the zero that used to mean two things
# --------------------------------------------------------------------------- #


def counting(supported: int, total: int) -> object:
    def judge(prompt: str) -> ClaimReply:
        return ClaimReply(supported=supported, total=total, reason="counted")

    return judge


def test_faithfulness_tells_the_two_zeros_apart() -> None:
    """The point of the whole amendment: one sentence for the judge that could
    not tell what the output asserts, another for the judge that counted and
    found nothing."""
    declined = faithfulness(declining("the output is in a script I cannot read"))(
        inputs(context=["a source"])
    )
    none_found = faithfulness(counting(0, 0))(inputs(context=["a source"]))

    assert declined.status == none_found.status == "error"
    assert declined.reason == (
        "the judge declined to count the claims: the output is in a script I "
        "cannot read"
    )
    assert none_found.reason.startswith("the judge counted the claims")
    assert declined.reason != none_found.reason


def test_the_zero_may_now_claim_the_judge_counted() -> None:
    """The rewritten sentence, and it may only be said because the line above it
    exists: before an abstention was possible, "counted and found none" was a
    claim the data did not support."""
    v = faithfulness(counting(0, 0))(inputs(context=["a source"]))
    assert "counted the claims in this output and found none" in v.reason


# --------------------------------------------------------------------------- #
# What it does not do
# --------------------------------------------------------------------------- #


def test_a_declining_attributes_no_side_and_moves_no_number() -> None:
    """It changes a sentence. There is no field on the verdict, and the check is
    excluded from an aggregate exactly where an errored check always was."""
    v = rubric(declining("cannot be scored"))(inputs())
    assert not hasattr(v, "side")
    assert v.threshold == 0.7
    assert v.tolerance == 0.05
    assert v.score.metadata == {}


def test_a_fold_keeps_both_causes_with_their_counts() -> None:
    """A `Repeated` check that declined twice and failed once reads as both, so
    folding does not cost the reader the diagnosis it folded."""
    declined = rubric(declining("the output is empty"))(inputs())

    def broken(prompt: str) -> JudgeReply:
        raise RuntimeError("timeout")

    failed = rubric(broken)(inputs())
    folded = combine_samples([declined, declined, failed], min_agreement=0.5)

    assert folded.status == "error"
    assert "2 of 3: the judge declined to score: the output is empty" in folded.reason
    assert "1 of 3: the judge raised RuntimeError" in folded.reason


# --------------------------------------------------------------------------- #
# The bill
# --------------------------------------------------------------------------- #


def test_a_declining_is_a_paid_call() -> None:
    """The model was asked and answered, so the call is counted — unlike one
    that raises, whose cost is unknown. (ADR 0025 §4)"""
    judge = Scoring({"abstain": True, "reason": "cannot be scored"})
    with pytest.raises(JudgeAbstained):
        judge("anything")

    assert judge.calls == 1
    assert judge.spent_usd > 0
    assert judge.tokens.input_tokens == 10


# --------------------------------------------------------------------------- #
# What the reader sees, and the one surface that will not show it
# --------------------------------------------------------------------------- #


DECLINED = "the judge declined to score: the output is a refusal to help"


def a_declined_run() -> Run:
    """A run holding one check the judge declined, and nothing else."""
    return Run(
        tenant="acme",
        environment="staging",
        suite="qa",
        config_hash="h",
        created_at="2026-01-01T00:00:00+00:00",
        results=[
            CaseResult(
                case_id="one",
                verdicts=(
                    Verdict(
                        score=Score(name="llm_rubric", score=None),
                        threshold=0.7,
                        status="error",
                        reason=DECLINED,
                        assertion_id="a1",
                    ),
                ),
            )
        ],
    )


def test_the_report_prints_the_judges_own_sentence() -> None:
    """`reasons_available` is `not redacted`, so an ordinary reader sees it."""
    document = render_run_html(a_declined_run(), locale="en")
    assert escape(DECLINED) in document


def test_a_redacted_document_withholds_it_like_any_other_reason() -> None:
    """Unchanged and correct: the reason is payload, and a judge quoting an
    output is quoting the output."""
    document = render_run_html(redact(a_declined_run()), locale="en")
    assert escape(DECLINED) not in document


def test_explain_does_not_carry_it_and_that_is_deliberate() -> None:
    """`CheckFact` has no `reason`, by ADR 0012 §4 — *absent rather than
    emptied, because a field that exists is a field a later edit fills*.

    Asserted so the deliberate absence cannot be closed by accident later. It is
    the one surface that will not show the judge's sentence, and the amendment
    says so rather than quietly adding a field for it.
    """
    reading = facts(a_declined_run())
    assert reading, "an empty reading would make this gate prove nothing"
    assert not any(DECLINED in str(fact) for fact in reading)
    assert any(getattr(fact, "kind", "") == "errored" for fact in reading), (
        "the check is still reported as unjudged — only its sentence is absent"
    )


def test_a_scoring_judge_leaves_no_trace_of_the_feature_in_the_document() -> None:
    """The compatibility line, asserted on the document.

    It cannot prove byte-identity against a release that is not installed, and
    it does not claim to: what it proves is that this amendment added no key and
    no word to any stored document, so a run whose judge scored normally is the
    run it always was.
    """
    judge = Scoring({"score": 0.9, "reason": "polite enough"})
    reply = judge("anything")
    assert (reply.score, reply.reason) == (0.9, "polite enough")

    written = run_to_json(
        Run(
            tenant="acme",
            environment="staging",
            suite="qa",
            config_hash="h",
            created_at="2026-01-01T00:00:00+00:00",
            results=[
                CaseResult(
                    case_id="one",
                    verdicts=(
                        Verdict(
                            score=Score(name="llm_rubric", score=0.9),
                            threshold=0.7,
                            status="pass",
                            reason=reply.reason,
                            assertion_id="a1",
                        ),
                    ),
                )
            ],
        )
    )
    assert ABSTAIN_KEY not in written
    assert "declined" not in written
