"""The payload boundary: the verdict travels, the payload stays where it was born.

These tests are the enforcement of ADR 0002. They are written from the point of
view of the mistake being prevented — a fragment of an end customer's data
arriving in a software house's repository — rather than of the function being
exercised.
"""

from __future__ import annotations

import pytest

from digline.core import (
    REDACTED,
    CaseResult,
    Contains,
    CostBudget,
    Disclosure,
    EvaluatorInputs,
    JudgeReply,
    LlmRubric,
    Run,
    compare,
    config_hash,
    redact,
    run_from_json,
    run_to_json,
    travels,
)

CREATED = "2026-01-01T00:00:00+00:00"

# A judgement that quotes the output it judged — which is what a real judge does,
# and the reason `reason` is payload rather than a label.
CONFIDENTIAL = (
    "The reply discloses that Mario Rossi's account IBAN IT60X0542811101 was "
    "overdrawn by 1499 euro, which the rubric forbids"
)


def judged_run(*, tenant: str = "acme") -> Run:
    def judge(prompt: str) -> JudgeReply:
        return JudgeReply(score=0.2, reason=CONFIDENTIAL)

    rubric = LlmRubric(
        rubric="Does it leak account data?", judge=judge, threshold=0.7, tolerance=0.05
    )
    budget = CostBudget(max_usd=0.10, tolerance=0.02)
    probe = EvaluatorInputs(output="…", cost_usd=0.01)
    return Run(
        tenant=tenant,
        environment="test",
        suite="privacy",
        config_hash=config_hash([rubric, budget]),
        created_at=CREATED,
        results=(CaseResult("case-1", (rubric(probe), budget(probe))),),
        metadata={"model": "claude-opus-5", "customer_balance": 1499.0},
    )


# --------------------------------------------------------------------------- #
# What a redacted document must not contain
# --------------------------------------------------------------------------- #


def test_a_redacted_document_carries_no_word_of_the_judgement() -> None:
    """The requirement, stated as the customer would state it.

    Structural vocabulary is excluded from the check on purpose: `rubric` is a
    substring of the assertion name `llm_rubric`, so a naive scan over every
    word flags a legitimate label. What must not survive is the content —
    identity, account number, amount — and the sentence as a whole.
    """
    document = run_to_json(judged_run(), redacted=True)
    assert CONFIDENTIAL not in document
    for secret in (
        "Mario",
        "Rossi",
        "IT60X0542811101",
        "1499",
        "overdrawn",
        "discloses",
    ):
        assert secret not in document, f"{secret!r} survived redaction"


def test_the_payload_field_is_absent_not_emptied() -> None:
    """Omitted, so not even the length of the original survives."""
    document = run_to_json(judged_run(), redacted=True)
    assert '"reason"' not in document
    assert REDACTED not in document


def test_a_redacted_document_says_so() -> None:
    """A reader must never mistake it for a complete one where the judge was
    simply terse."""
    assert '"redacted": true' in run_to_json(judged_run(), redacted=True)
    assert '"redacted": false' in run_to_json(judged_run())


def test_the_complete_document_still_holds_everything() -> None:
    """Redaction is a boundary crossing, not the default: inside the perimeter
    the reason is exactly what makes a failure actionable."""
    assert CONFIDENTIAL in run_to_json(judged_run())


# --------------------------------------------------------------------------- #
# What survives, and why it must
# --------------------------------------------------------------------------- #


def test_the_verdict_travels_intact() -> None:
    redacted = redact(judged_run())
    verdict = redacted.results[0].verdicts[0]
    assert verdict.score.name == "llm_rubric"
    assert verdict.score.score == 0.2
    assert verdict.status == "fail"
    assert verdict.threshold == 0.7
    assert verdict.tolerance == 0.05
    assert verdict.assertion_id  # pairing survives, so comparison survives


def test_measurements_written_by_an_assertion_survive() -> None:
    """`cost_usd` and `ratio` are produced by `CostBudget` from what it measured,
    so cost drift stays visible to the software house on the redacted form. It
    was the reason budgets got a graded score in the first place."""
    budget_verdict = redact(judged_run()).results[0].verdicts[1]
    assert budget_verdict.score.metadata["cost_usd"] == 0.01
    assert budget_verdict.score.metadata["ratio"] == pytest.approx(0.1)


def test_a_redacted_run_still_compares_against_a_complete_baseline() -> None:
    """Everything `compare()` reads survives redaction, which is what makes the
    end customer able to send a verdict without sending their data."""
    complete = judged_run()
    result = compare(redact(complete), complete)
    assert result.counts == {"unchanged": 2}


def test_a_redacted_run_survives_the_round_trip_as_redacted() -> None:
    restored = run_from_json(run_to_json(judged_run(), redacted=True))
    assert restored.redacted is True
    assert restored.results[0].verdicts[0].reason == REDACTED


# --------------------------------------------------------------------------- #
# The two halves of Disclosure, and why they differ
# --------------------------------------------------------------------------- #


def test_numbers_travel_from_score_metadata_but_not_from_run_metadata() -> None:
    """The asymmetry: `0.01` written by `CostBudget` is a measurement,
    `1499.0` copied out of a customer's request is their data wearing the same
    clothes. Both are floats; only the first has a provenance we trust."""
    redacted = redact(judged_run())
    assert redacted.results[0].verdicts[1].score.metadata["cost_usd"] == 0.01
    assert "customer_balance" not in redacted.metadata


def test_run_metadata_travels_only_by_explicit_disclosure() -> None:
    allowed = Disclosure(run_metadata=frozenset({"model"}))
    redacted = redact(judged_run(), allowed)
    assert redacted.metadata == {"model": "claude-opus-5"}
    # Still not the balance: an allowlist names keys, it does not widen a type.
    assert "customer_balance" not in redacted.metadata


def test_string_score_metadata_needs_a_disclosure_too() -> None:
    assert travels(0.5) and travels(True)
    assert not travels("anything")


def test_the_default_disclosure_discloses_nothing_extra() -> None:
    """So code that redacts without knowing the suite's policy discloses less,
    never more."""
    assert redact(judged_run()).metadata == {}


def test_redaction_never_widens() -> None:
    wide = Disclosure(run_metadata=frozenset({"model", "customer_balance"}))
    once = redact(judged_run(), wide)
    assert "customer_balance" in once.metadata
    # Applying it again with a narrower policy narrows; it cannot restore.
    twice = redact(once, Disclosure())
    assert twice.metadata == {}
    assert redact(twice, wide).metadata == {}


def test_redaction_is_idempotent_under_one_policy() -> None:
    allowed = Disclosure(run_metadata=frozenset({"model"}))
    once = redact(judged_run(), allowed)
    assert run_to_json(redact(once, allowed)) == run_to_json(once)


# --------------------------------------------------------------------------- #
# The mapper has no route into Score.metadata
# --------------------------------------------------------------------------- #


def test_the_redacted_flag_is_verified_not_believed() -> None:
    """A flag that announced a guarantee nothing provides would be worse than no
    flag: the serializer would omit the reasons on its word, and a reader would
    trust a document built by hand."""
    complete = judged_run()
    with pytest.raises(ValueError, match="still\n?\\s*carries a reason"):
        Run(
            tenant=complete.tenant,
            environment=complete.environment,
            suite=complete.suite,
            config_hash=complete.config_hash,
            created_at=complete.created_at,
            results=complete.results,
            redacted=True,
        )


def test_a_properly_redacted_run_is_accepted() -> None:
    """The other direction: what `redact()` produces satisfies the check by
    construction."""
    assert redact(judged_run()).redacted is True


def test_a_complete_run_needs_no_redacted_flag() -> None:
    assert judged_run().redacted is False


# --------------------------------------------------------------------------- #
# Environment: reported, never constrained
# --------------------------------------------------------------------------- #


def test_staging_compares_against_a_production_baseline() -> None:
    """The pre-release check the product exists for. Same tenant, different
    environment: legal, and the comparison says which was which."""
    production = judged_run()
    staging = Run(
        tenant=production.tenant,
        environment="staging",
        suite=production.suite,
        config_hash=production.config_hash,
        created_at="2026-01-02T00:00:00+00:00",
        results=production.results,
    )
    result = compare(staging, production)
    assert result.environment == "staging"
    assert result.baseline_environment == "test"
    assert result.counts == {"unchanged": 2}


def test_a_mapper_cannot_reach_score_metadata() -> None:
    """Structural, not a convention: an assertion writes `Score.metadata` from
    what it measured, and what a mapper carries in through
    `EvaluatorInputs.metadata` has no route there. Whatever an integration wants
    to annotate belongs in `Run.metadata`, where nothing travels by default."""
    smuggled = EvaluatorInputs(
        output="The capital is Rome.",
        cost_usd=0.01,
        metadata={"iban": "IT60X0542811101", "balance": 1499.0},
    )
    verdicts = [
        Contains(needle="Rome")(smuggled),
        CostBudget(max_usd=0.10, tolerance=0.02)(smuggled),
        LlmRubric(
            rubric="polite?",
            judge=lambda prompt: JudgeReply(score=1.0, reason="fine"),
            threshold=0.7,
            tolerance=0.05,
        )(smuggled),
    ]
    for verdict in verdicts:
        assert "iban" not in verdict.score.metadata
        assert "balance" not in verdict.score.metadata
