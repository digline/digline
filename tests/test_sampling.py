"""Sampling: judge noise, system noise, and the promise that neither costs
anything to a suite that does not ask for them.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from digline.core import (
    CaseResult,
    Contains,
    CostBudget,
    EvaluatorInputs,
    JudgeReply,
    LlmRubric,
    Repeated,
    Run,
    Score,
    Verdict,
    combine_samples,
    config_hash,
    run_to_json,
)
from digline.run import Case, Response, Suite, default_mapper, execute

CREATED = "2026-01-01T00:00:00+00:00"


def verdict(score: float | None, *, threshold: float = 0.7, name: str = "rubric"):
    if score is None:
        return Verdict(
            score=Score(name=name, score=None),
            threshold=threshold,
            status="error",
            reason="could not judge",
            assertion_id=f"id-{name}",
        )
    return Verdict(
        score=Score(name=name, score=score),
        threshold=threshold,
        status="pass" if score >= threshold else "fail",
        reason="judged",
        assertion_id=f"id-{name}",
    )


def wobbling_judge(*scores: float):
    """A judge that answers differently each time it is asked, like a real one."""
    calls = iter(scores * 100)

    def judge(prompt: str) -> JudgeReply:
        return JudgeReply(score=next(calls), reason="wobble")

    return judge


def steady_target(case: Case) -> Response:
    return Response(output="Rome", input="capital?", cost_usd=0.01, latency_ms=100.0)


# --------------------------------------------------------------------------- #
# One sample changes nothing
# --------------------------------------------------------------------------- #


def test_combining_one_verdict_returns_that_verdict_untouched() -> None:
    only = verdict(0.9)
    assert combine_samples([only], min_agreement=1.0) is only


def test_a_suite_at_one_sample_produces_the_bytes_it_produced_before() -> None:
    """The guarantee sampling had to buy its way in with.

    `expected` is built the way the driver worked before sampling existed —
    call the assertion once on the mapped response, no folding — so if the fold
    ever leaks into the single-sample path the JSON stops matching."""
    assertions = [Contains(needle="Rome"), CostBudget(max_usd=0.02, tolerance=0.05)]
    suite = Suite(
        tenant="acme",
        environment="dev",
        name="qa",
        assertions=assertions,
        cases=[Case(id="one"), Case(id="two")],
    )
    run = execute(suite, steady_target, created_at=CREATED)

    expected = Run(
        tenant="acme",
        environment="dev",
        suite="qa",
        config_hash=suite.config_hash(),
        created_at=CREATED,
        results=tuple(
            CaseResult(
                case.id,
                tuple(a(default_mapper(steady_target(case), case)) for a in assertions),
            )
            for case in suite.cases
        ),
    )
    assert run_to_json(run) == run_to_json(expected)


def test_one_sample_adds_no_sampling_metadata() -> None:
    suite = Suite(
        tenant="acme",
        environment="dev",
        name="qa",
        assertions=[Contains(needle="Rome")],
        cases=[Case(id="one")],
    )
    run = execute(suite, steady_target, created_at=CREATED)
    assert run.results[0].verdicts[0].score.metadata == {}


# --------------------------------------------------------------------------- #
# Budgets judge one call, not the bill
# --------------------------------------------------------------------------- #


def test_a_budget_still_judges_a_single_call() -> None:
    """Raising `samples` must never trip `CostBudget` on its own: what the user
    pays per answer has not changed."""
    budget = CostBudget(max_usd=0.02, tolerance=0.05)
    suite = Suite(
        tenant="acme",
        environment="dev",
        name="qa",
        assertions=[budget],
        cases=[Case(id="one")],
        samples=3,
        min_agreement=1.0,
    )
    run = execute(suite, steady_target, created_at=CREATED)
    combined = run.results[0].verdicts[0]

    single = budget(EvaluatorInputs(output="Rome", cost_usd=0.01))
    assert combined.status == "pass"
    assert combined.score.score == single.score.score  # the mean of three equals


def test_the_total_spent_is_recorded_and_travels() -> None:
    """Cost is money and sampling multiplies the bill, so the total is reported
    even though no assertion judges it. It is a number, so it survives
    redaction."""
    suite = Suite(
        tenant="acme",
        environment="dev",
        name="qa",
        assertions=[CostBudget(max_usd=0.02, tolerance=0.05)],
        cases=[Case(id="one")],
        samples=3,
        min_agreement=1.0,
    )
    run = execute(suite, steady_target, created_at=CREATED)
    metadata = run.results[0].verdicts[0].score.metadata
    assert metadata["total_cost_usd"] == pytest.approx(0.03)
    # And what the samples measured survives the fold: without it, sampling
    # would cost the reader the raw values the graded score exists to expose.
    assert metadata["cost_usd"] == pytest.approx(0.01)  # mean per call
    assert metadata["max_usd"] == pytest.approx(0.02)  # a constant, untouched
    assert metadata["ratio"] == pytest.approx(0.5)

    from digline.core import redact

    assert redact(run).results[0].verdicts[0].score.metadata["total_cost_usd"] == (
        pytest.approx(0.03)
    )


# --------------------------------------------------------------------------- #
# agreement, spread, and what gets recorded
# --------------------------------------------------------------------------- #


def test_agreement_is_the_fraction_sharing_the_majority_verdict() -> None:
    """Two pass, one fail: agreement is two thirds, not a variance."""
    combined = combine_samples(
        [verdict(0.90), verdict(0.80), verdict(0.60)], min_agreement=0.6
    )
    assert combined.score.metadata["agreement"] == pytest.approx(2 / 3)


def test_a_wide_but_unanimous_spread_still_agrees() -> None:
    """0.80 to 0.99 is noisy and harmless; agreement says so and the spread
    reports the width for whoever wants the other view."""
    combined = combine_samples([verdict(0.80), verdict(0.99)], min_agreement=1.0)
    assert combined.status == "pass"
    assert combined.score.metadata["agreement"] == 1.0
    assert combined.score.metadata["spread"] == pytest.approx(0.19)


def test_a_narrow_spread_across_the_threshold_does_not_agree() -> None:
    """0.69 to 0.71 across a bar of 0.70 is the dangerous case, and only
    agreement tells it apart from the harmless one."""
    combined = combine_samples([verdict(0.71), verdict(0.69)], min_agreement=0.9)
    assert combined.status == "error"
    assert "did not agree" in combined.reason


def test_the_recorded_metadata_is_all_numbers() -> None:
    combined = combine_samples(
        [verdict(0.90), verdict(0.80), verdict(0.85)], min_agreement=0.6
    )
    metadata = combined.score.metadata
    assert set(metadata) == {
        "samples",
        "agreement",
        "spread",
        "errored_samples",
        "scores",
    }
    assert metadata["samples"] == 3
    assert metadata["scores"] == [0.90, 0.80, 0.85]


def test_measurements_that_disagree_are_dropped_rather_than_guessed() -> None:
    """There is no honest way to average two different strings, so a key the
    samples do not agree on does not survive."""

    def with_meta(score: float, **extra: object) -> Verdict:
        base = verdict(score)
        return Verdict(
            score=Score(name=base.score.name, score=score, metadata=extra),
            threshold=base.threshold,
            status=base.status,
            reason=base.reason,
            assertion_id=base.assertion_id,
        )

    combined = combine_samples(
        [
            with_meta(0.9, model="a", tokens=10),
            with_meta(0.8, model="b", tokens=20),
        ],
        min_agreement=1.0,
    )
    assert "model" not in combined.score.metadata  # disagreed
    assert combined.score.metadata["tokens"] == pytest.approx(15.0)  # averaged


def test_a_measurement_every_sample_agrees_on_is_kept_as_is() -> None:
    def with_meta(score: float, **extra: object) -> Verdict:
        base = verdict(score)
        return Verdict(
            score=Score(name=base.score.name, score=score, metadata=extra),
            threshold=base.threshold,
            status=base.status,
            reason=base.reason,
            assertion_id=base.assertion_id,
        )

    combined = combine_samples(
        [with_meta(0.9, model="claude"), with_meta(0.8, model="claude")],
        min_agreement=1.0,
    )
    assert combined.score.metadata["model"] == "claude"


def test_the_combined_score_is_the_mean() -> None:
    combined = combine_samples(
        [verdict(0.90), verdict(0.80), verdict(0.70)], min_agreement=0.6
    )
    assert combined.score.score == pytest.approx(0.8)
    assert "mean of 3 samples" in combined.reason


# --------------------------------------------------------------------------- #
# Disagreement is `error`, not `fail`
# --------------------------------------------------------------------------- #


def test_below_the_floor_the_outcome_is_error_and_lists_the_scores() -> None:
    """A judgement that does not repeat is not a failure, it is a judgement that
    could not be given."""
    combined = combine_samples(
        [verdict(0.95), verdict(0.20), verdict(0.90)], min_agreement=0.9
    )
    assert combined.status == "error"
    assert combined.passed is False
    assert combined.score.score is None
    assert "0.950000" in combined.reason and "0.200000" in combined.reason


def test_a_suite_too_noisy_to_trust_cannot_be_promoted(tmp_path: Path) -> None:
    """The consequence that matters: an unstable check keeps the suite from ever
    becoming a reference."""
    from digline.store import ErroredRunError, FileResultStore

    suite = Suite(
        tenant="acme",
        environment="dev",
        name="qa",
        assertions=[
            LlmRubric(
                rubric="ok?",
                judge=wobbling_judge(0.95, 0.20, 0.90),
                threshold=0.7,
                tolerance=0.05,
            )
        ],
        cases=[Case(id="one")],
        samples=3,
        # With three samples the reachable floors are 1/3, 2/3 and 3/3. "Too
        # noisy to trust" means unanimity here — there is no 0.9 to reach for,
        # which is the whole point of refusing one.
        min_agreement="3/3",
    )
    run = execute(suite, steady_target, created_at=CREATED)
    assert run.results[0].verdicts[0].status == "error"

    store = FileResultStore(tmp_path)
    with pytest.raises(ErroredRunError, match="one"):
        store.promote_baseline(store.write_run(run), suite.config_hash())


def test_when_every_sample_errors_the_result_says_so() -> None:
    combined = combine_samples([verdict(None), verdict(None)], min_agreement=0.5)
    assert combined.status == "error"
    assert "no sample could be judged" in combined.reason


# --------------------------------------------------------------------------- #
# Repeated: the judge, not the system
# --------------------------------------------------------------------------- #


def test_repeated_asks_the_inner_assertion_several_times() -> None:
    inner = LlmRubric(
        rubric="ok?",
        judge=wobbling_judge(0.90, 0.80, 0.85),
        threshold=0.7,
        tolerance=0.05,
    )
    combined = Repeated(inner=inner, samples=3, min_agreement="2/3")(
        EvaluatorInputs(output="Rome")
    )
    assert combined.score.metadata["samples"] == 3
    assert combined.score.score == pytest.approx(0.85)


def test_repeated_borrows_the_inner_threshold_and_tolerance() -> None:
    inner = LlmRubric(
        rubric="ok?", judge=wobbling_judge(0.9), threshold=0.75, tolerance=0.04
    )
    wrapper = Repeated(inner=inner, samples=2, min_agreement=1.0)
    assert (wrapper.threshold, wrapper.tolerance) == (0.75, 0.04)
    assert wrapper.accepts == inner.accepts
    assert wrapper.name == inner.name


def test_repeated_carries_its_own_identity() -> None:
    """Wrapping is a configuration change loud enough to show as new + missing:
    the right way for "this check is now judged three times" to reach a
    reviewer."""
    inner = LlmRubric(
        rubric="ok?", judge=wobbling_judge(0.9), threshold=0.7, tolerance=0.05
    )
    wrapper = Repeated(inner=inner, samples=3, min_agreement="2/3")
    assert wrapper.identity != inner.identity

    verdict_out = wrapper(EvaluatorInputs(output="Rome"))
    assert verdict_out.assertion_id == wrapper.identity


def test_repeated_refuses_a_pointless_repetition() -> None:
    inner = Contains(needle="Rome")
    with pytest.raises(ValueError, match="at least 2"):
        Repeated(inner=inner, samples=1, min_agreement=1.0)
    with pytest.raises(ValueError, match=r"outside \(0, 1\]"):
        Repeated(inner=inner, samples=3, min_agreement=0.0)


# --------------------------------------------------------------------------- #
# The suite has to declare what it accepts
# --------------------------------------------------------------------------- #


def test_sampling_without_a_declared_floor_is_refused() -> None:
    """Same reason `LlmRubric.tolerance` is mandatory: a floor on a noisy value
    that nobody chose is a green light nobody gave."""
    with pytest.raises(ValueError, match="without\n?\\s*declaring min_agreement"):
        Suite(
            tenant="acme",
            environment="dev",
            name="qa",
            assertions=[Contains(needle="Rome")],
            cases=[Case(id="one")],
            samples=3,
        )


def test_zero_samples_are_refused() -> None:
    with pytest.raises(ValueError, match="at least"):
        Suite(
            tenant="acme",
            environment="dev",
            name="qa",
            assertions=[Contains(needle="Rome")],
            cases=[Case(id="one")],
            samples=0,
        )


def test_samples_and_the_floor_change_the_config_hash() -> None:
    """Comparable but not promotable: a baseline taken at one sample is not a
    reference for a suite that now takes three."""
    checks = [Contains(needle="Rome")]
    once = config_hash(checks)
    thrice = config_hash(checks, samples=3, min_agreement=0.9)
    stricter = config_hash(checks, samples=3, min_agreement=1.0)
    assert len({once, thrice, stricter}) == 3


def test_the_default_config_hash_is_unchanged_by_the_new_arguments() -> None:
    """A suite that never mentions sampling must hash exactly as it did."""
    checks = [Contains(needle="Rome")]
    assert config_hash(checks) == config_hash(checks, samples=1, min_agreement=None)


# --------------------------------------------------------------------------- #
# The driver samples the target
# --------------------------------------------------------------------------- #


def test_the_target_is_called_once_per_sample_per_case() -> None:
    seen: list[str] = []

    def counting(case: Case) -> Response:
        seen.append(case.id)
        return Response(output="Rome", cost_usd=0.01)

    suite = Suite(
        tenant="acme",
        environment="dev",
        name="qa",
        assertions=[Contains(needle="Rome")],
        cases=[Case(id="one"), Case(id="two")],
        samples=3,
        min_agreement=1.0,
    )
    execute(suite, counting, created_at=CREATED)
    assert seen == ["one", "one", "one", "two", "two", "two"]


def test_a_target_that_fails_once_errors_the_whole_case() -> None:
    """A target that cannot answer has not answered, and a partly-sampled case
    would be a weaker measurement claiming to be the declared one."""
    attempts = {"n": 0}

    def flaky(case: Case) -> Response:
        attempts["n"] += 1
        if attempts["n"] == 2:
            raise TimeoutError("second call timed out")
        return Response(output="Rome", cost_usd=0.01)

    suite = Suite(
        tenant="acme",
        environment="dev",
        name="qa",
        assertions=[Contains(needle="Rome")],
        cases=[Case(id="one")],
        samples=3,
        min_agreement=1.0,
    )
    run = execute(suite, flaky, created_at=CREATED)
    verdicts = run.results[0].verdicts
    assert all(v.status == "error" for v in verdicts)
    assert "TimeoutError" in verdicts[0].reason


def test_a_suspended_case_is_not_sampled_at_all() -> None:
    seen: list[str] = []

    def counting(case: Case) -> Response:
        seen.append(case.id)
        return Response(output="Rome", cost_usd=0.01)

    suite = Suite(
        tenant="acme",
        environment="dev",
        name="qa",
        assertions=[Contains(needle="Rome")],
        cases=[Case(id="live"), Case(id="parked", suspended="ticket 412")],
        samples=3,
        min_agreement=1.0,
    )
    execute(suite, counting, created_at=CREATED)
    assert seen == ["live", "live", "live"]


# --------------------------------------------------------------------------- #
# "k out of n" (friction 11)
# --------------------------------------------------------------------------- #


def test_a_decimal_that_no_count_can_produce_is_refused() -> None:
    """It happened twice inside one hour of writing a real suite: `0.67` for two
    out of three, which is *above* 2/3, so every two-vote case errored for the
    opposite of the intended reason."""
    inner = Contains(needle="Rome")
    with pytest.raises(ValueError, match="3 samples cannot produce"):
        Repeated(inner=inner, samples=3, min_agreement=0.67)
    with pytest.raises(ValueError, match="1/3 = 0.333333, 2/3 = 0.666667"):
        Repeated(inner=inner, samples=3, min_agreement=0.67)


def test_the_fraction_may_be_written_as_one() -> None:
    from fractions import Fraction

    inner = Contains(needle="Rome")
    written = Repeated(inner=inner, samples=3, min_agreement="2/3")
    typed = Repeated(inner=inner, samples=3, min_agreement=Fraction(2, 3))
    assert written.min_agreement == pytest.approx(2 / 3)
    assert written.identity == typed.identity


def test_an_unreachable_fraction_is_refused_too() -> None:
    """The value is refused, not the notation: `"2/4"` is as impossible with
    three samples as `0.67` is."""
    with pytest.raises(ValueError, match="3 samples cannot produce"):
        Repeated(inner=Contains(needle="Rome"), samples=3, min_agreement="2/4")


def test_a_suite_refuses_the_same_decimal() -> None:
    with pytest.raises(ValueError, match="5 samples cannot produce"):
        Suite(
            tenant="acme",
            environment="dev",
            name="qa",
            assertions=[Contains(needle="Rome")],
            cases=[Case(id="one")],
            samples=5,
            min_agreement=0.5,
        )


def test_the_exact_decimal_is_accepted_because_it_is_the_value() -> None:
    """`2/5` is exact in decimal, so `0.4` is right — it was right by luck
    before, and now it is right by check."""
    suite = Suite(
        tenant="acme",
        environment="dev",
        name="qa",
        assertions=[Contains(needle="Rome")],
        cases=[Case(id="one")],
        samples=5,
        min_agreement=0.4,
    )
    assert suite.min_agreement == pytest.approx(2 / 5)


def test_a_check_that_passes_alone_still_passes_folded() -> None:
    """Found writing the `prompt-first` example, not writing the engine.

    Three samples of exactly `0.7` against a threshold of `0.7` average to
    `0.6999999999999998`. The fold judged the unrounded mean and said `fail`;
    `Verdict` rounds the score to `0.7` and refuses a `fail` that its own score
    contradicts — so a rubric that passes on its own turned into `error` the
    moment it was wrapped in `Repeated`. Thresholds are round numbers and rubric
    scores land on them, so this is the ordinary case, not the exotic one.
    """
    on_the_nose = LlmRubric(
        rubric="r",
        judge=lambda prompt: JudgeReply(score=0.4 + 0.3 * 0 + 0.3 * 1, reason="x"),
        threshold=0.7,
        tolerance=0.1,
    )
    alone = on_the_nose(EvaluatorInputs(output="hello"))
    assert alone.status == "pass"

    folded = Repeated(inner=on_the_nose, samples=3, min_agreement="2/3")(
        EvaluatorInputs(output="hello")
    )
    assert folded.status == "pass", "wrapping a passing check must not fail it"
    assert folded.score.score == 0.7


def test_the_folded_score_is_the_one_the_verdict_carries() -> None:
    """The general rule behind it: whatever decides the status has to be the
    number the reader sees, or the two can disagree."""
    scores = iter([0.1, 0.2, 0.30000000000000004])
    drifting = LlmRubric(
        rubric="r",
        judge=lambda prompt: JudgeReply(score=next(scores), reason="x"),
        threshold=0.2,
        tolerance=0.5,
    )
    folded = Repeated(inner=drifting, samples=3, min_agreement="1/3")(
        EvaluatorInputs(output="hello")
    )
    assert folded.score.score is not None
    expected = "pass" if folded.score.score >= folded.threshold else "fail"
    assert folded.status == expected
