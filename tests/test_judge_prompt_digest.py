"""The judge's instruction is part of the instrument. (P-1686)

A judge asked under new words grades on another scale, as one given another
model does, so the digest of its `system` is recorded in `judge_config` as
`prompt_digest` and a comparison says the judge changed when it moves. Two
runs under one instruction say nothing. A reference recorded before the key
existed reads it as `new`, which is a change: the first comparison after the
upgrade says the judge changed, once, and the next one does not.
(ADR 0005 §4, amended 2026-11-14)
"""

from __future__ import annotations

import hashlib
from dataclasses import replace

from tests.test_judge import FakeClaimJudge, FakeScoreJudge

from digline.core import LlmRubric, Run, SystemConfig, compare
from digline.run import Case, Response, Suite, execute
from digline.targets import CLAIM_SYSTEM, SCORE_SYSTEM
from digline.targets.judge import prompt_digest

REPLY = '{"score": 1, "reason": "it names the capital"}'


class Graded(FakeScoreJudge):
    """A judge that names its instrument, as every plugin's does."""

    provider = "fake"


class Reworded(Graded):
    """The same model and cap, asked under one sentence more."""

    system = SCORE_SYSTEM + "\n\nPrefer the shorter answer."


def a_run(judge: Graded) -> Run:
    suite = Suite(
        tenant="acme-bank",
        environment="staging",
        name="qa",
        assertions=[
            LlmRubric(rubric="right?", judge=judge, threshold=0.5, tolerance=0.05)
        ],
        cases=[Case(id="capital-it")],
    )
    return execute(
        suite,
        lambda case: Response(output="Rome."),
        created_at="2026-11-14T00:00:00Z",
    )


def outcome(now: Run, before: Run) -> str:
    deltas = compare(now, before).judge_config_deltas
    return next(d.outcome for d in deltas if d.field == "prompt_digest")


def test_the_digest_is_sixteen_hex_characters_of_the_instruction() -> None:
    expected = hashlib.sha256(SCORE_SYSTEM.encode("utf-8")).hexdigest()[:16]
    assert prompt_digest(SCORE_SYSTEM) == expected
    assert Graded(REPLY).config["prompt_digest"] == expected
    assert Reworded(REPLY).config["prompt_digest"] != expected


def test_each_judge_records_the_instruction_it_asks_under() -> None:
    class Counted(FakeClaimJudge):
        provider = "fake"

    assert Counted("").config["prompt_digest"] == prompt_digest(CLAIM_SYSTEM)


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
            values={k: v for k, v in recorded.values.items() if k != "prompt_digest"},
            identities=recorded.identities,
            named=recorded.named - {"prompt_digest"},
        ),
    )
    assert outcome(first, older) == "new"
    assert compare(first, older).judge_config_changed
    assert not compare(a_run(Graded(REPLY)), first).judge_config_changed


def test_the_key_is_digline_s_word_and_crosses_a_projection_in_clear() -> None:
    """Named by the driver, so a projected comparison names the field."""
    assert "prompt_digest" in (a_run(Graded(REPLY)).judge_config.named or ())


def test_a_score_and_a_claim_judge_on_one_model_record_no_digest() -> None:
    """The limit ADR 0005 §4's merge rule sets, written where it bites: the two
    are asked under two instructions, so the set-up keeps neither."""
    from digline.core import Faithfulness
    from digline.run import judge_config

    class Counted(FakeClaimJudge):
        provider = "fake"

    suite = Suite(
        tenant="acme-bank",
        environment="staging",
        name="qa",
        assertions=[
            LlmRubric(
                rubric="right?", judge=Graded(REPLY), threshold=0.5, tolerance=0.05
            ),
            Faithfulness(judge=Counted(""), threshold=0.9, tolerance=0.05),
        ],
        cases=[Case(id="capital-it")],
    )
    config = judge_config(suite)
    assert config.identities == ("fake/fake-1",)
    assert "max_tokens" in config.values
    assert "prompt_digest" not in config.values
