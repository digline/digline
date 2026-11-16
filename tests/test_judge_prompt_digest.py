"""The judge's instruction is part of the instrument. (P-1686; ADR 0068 §3)

A judge asked under new words grades on another scale, as one given another
model does, so the digest of its `system` is recorded in `judge_config` and a
comparison says the judge changed when it moves. One key per kind of judge:
a `ScoreJudge` writes `score_prompt_digest` and a `ClaimCountJudge`
`claim_prompt_digest`, each merged over the judges that write it, so two kinds
on one model keep both. Two runs under one instruction say nothing. A
reference recorded before the key existed reads it as `new`, which is a
change: the first comparison after the upgrade says the judge changed, once,
and the next one does not. (ADR 0005 §4, amended 2026-11-14; ADR 0068 §3)
"""

from __future__ import annotations

import hashlib
from dataclasses import replace

from tests.test_judge import FakeClaimJudge, FakeScoreJudge

from digline.core import (
    JUDGE_PROMPT_DIGESTS,
    NAMED_CONFIG_KEYS,
    Assertion,
    Faithfulness,
    LlmRubric,
    Run,
    SystemConfig,
    compare,
)
from digline.run import Case, Response, Suite, execute, judge_config
from digline.targets import CLAIM_SYSTEM, SCORE_SYSTEM
from digline.targets.judge import prompt_digest

REPLY = '{"score": 1, "reason": "it names the capital"}'


class Graded(FakeScoreJudge):
    """A judge that names its instrument, as every plugin's does."""

    provider = "fake"


class Reworded(Graded):
    """The same model and cap, asked under one sentence more."""

    system = SCORE_SYSTEM + "\n\nPrefer the shorter answer."


class Counted(FakeClaimJudge):
    provider = "fake"


def a_suite(*assertions: Assertion) -> Suite:
    return Suite(
        tenant="acme-bank",
        environment="staging",
        name="qa",
        assertions=list(assertions),
        cases=[Case(id="capital-it")],
    )


def rubric(judge: Graded) -> LlmRubric:
    return LlmRubric(rubric="right?", judge=judge, threshold=0.5, tolerance=0.05)


def a_run(judge: Graded) -> Run:
    return execute(
        a_suite(rubric(judge)),
        lambda case: Response(output="Rome."),
        created_at="2026-11-14T00:00:00Z",
    )


def outcome(now: Run, before: Run) -> str:
    deltas = compare(now, before).judge_config_deltas
    return next(d.outcome for d in deltas if d.field == "score_prompt_digest")


def test_the_digest_is_sixteen_hex_characters_of_the_instruction() -> None:
    expected = hashlib.sha256(SCORE_SYSTEM.encode("utf-8")).hexdigest()[:16]
    assert prompt_digest(SCORE_SYSTEM) == expected
    assert Graded(REPLY).config["score_prompt_digest"] == expected
    assert Reworded(REPLY).config["score_prompt_digest"] != expected


def test_each_kind_of_judge_records_its_instruction_under_its_own_key() -> None:
    claim = Counted("").config
    score = Graded(REPLY).config
    assert claim["claim_prompt_digest"] == prompt_digest(CLAIM_SYSTEM)
    assert "score_prompt_digest" not in claim
    assert "claim_prompt_digest" not in score
    assert "prompt_digest" not in claim and "prompt_digest" not in score


def test_a_judge_that_names_no_instrument_still_records_nothing() -> None:
    """The rule of `config` is unchanged: no `provider`, no configuration."""
    assert dict(FakeScoreJudge(REPLY).config) == {}


def test_two_runs_under_different_instructions_say_the_judge_changed() -> None:
    now, before = a_run(Reworded(REPLY)), a_run(Graded(REPLY))
    comparison = compare(now, before)
    assert comparison.judge_config_changed
    assert comparison.comparability_reduced
    assert outcome(now, before) == "changed"


def test_two_runs_under_one_instruction_say_nothing() -> None:
    """The control: the same words, and no change of instrument."""
    now, before = a_run(Graded(REPLY)), a_run(Graded(REPLY))
    comparison = compare(now, before)
    assert not comparison.judge_config_changed
    assert not comparison.comparability_reduced
    assert outcome(now, before) == "same"


def test_a_reference_recorded_before_the_key_says_it_once() -> None:
    """What the CHANGELOG promises: the first run under 1.3, against a
    reference judged under 1.2, says the judge changed; promoted, the next
    comparison is quiet."""
    first = a_run(Graded(REPLY))
    recorded = first.judge_config
    assert recorded.named is not None
    older = replace(
        first,
        judge_config=SystemConfig(
            values={
                k: v for k, v in recorded.values.items() if k != "score_prompt_digest"
            },
            identities=recorded.identities,
            named=recorded.named - {"score_prompt_digest"},
        ),
    )
    assert outcome(first, older) == "new"
    assert compare(first, older).judge_config_changed
    assert not compare(a_run(Graded(REPLY)), first).judge_config_changed


def test_the_keys_are_digline_s_words_and_cross_a_projection_in_clear() -> None:
    """Named by the driver, so a projected comparison names the field."""
    assert {"score_prompt_digest", "claim_prompt_digest"} == JUDGE_PROMPT_DIGESTS
    assert JUDGE_PROMPT_DIGESTS <= NAMED_CONFIG_KEYS
    assert "prompt_digest" not in NAMED_CONFIG_KEYS
    assert "score_prompt_digest" in (a_run(Graded(REPLY)).judge_config.named or ())


def test_a_score_and_a_claim_judge_on_one_model_keep_both_digests() -> None:
    """ADR 0068 §3: each key is merged over the judges that write it, so the
    judge of the other kind, which never writes it, does not drop it."""
    config = judge_config(
        a_suite(
            rubric(Graded(REPLY)),
            Faithfulness(judge=Counted(""), threshold=0.9, tolerance=0.05),
        )
    )
    assert config.identities == ("fake/fake-1",)
    assert "max_tokens" in config.values
    assert config.values["score_prompt_digest"] == prompt_digest(SCORE_SYSTEM)
    assert config.values["claim_prompt_digest"] == prompt_digest(CLAIM_SYSTEM)


def test_two_score_judges_under_two_instructions_record_no_score_digest() -> None:
    """The limit ADR 0068 §3 keeps: two judges of one kind that disagree on
    their instruction are two set-ups, and the key is dropped, as any scalar
    two judges disagree on is. The claim judge's key is untouched."""
    config = judge_config(
        a_suite(
            rubric(Graded(REPLY)),
            rubric(Reworded(REPLY)),
            Faithfulness(judge=Counted(""), threshold=0.9, tolerance=0.05),
        )
    )
    assert "score_prompt_digest" not in config.values
    assert config.values["claim_prompt_digest"] == prompt_digest(CLAIM_SYSTEM)
