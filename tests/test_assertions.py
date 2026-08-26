"""Every assertion has at least one failing case and at least one error case.

The error case is not a bonus: it is the ADR 0001 constraint — an assertion that
cannot judge must not turn green.
"""

from __future__ import annotations

import pytest

from digline.core import (
    ITALIAN_PII,
    TEXT_ONLY,
    Affix,
    AssertionBase,
    ClaimJudge,
    ClaimReply,
    Contains,
    CostBudget,
    Equals,
    EvaluatorInputs,
    Faithfulness,
    IsJson,
    JsonSchema,
    Judge,
    JudgeReply,
    LatencyBudget,
    Length,
    Levenshtein,
    LlmRubric,
    Message,
    NotContains,
    PiiAbsent,
    PiiPattern,
    Regex,
    budget_score,
    levenshtein_distance,
)


def inputs(**kwargs: object) -> EvaluatorInputs:
    kwargs.setdefault("output", "")
    return EvaluatorInputs(**kwargs)  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# Equals
# --------------------------------------------------------------------------- #


def test_equals_passes_on_identical_text() -> None:
    v = Equals()(inputs(output="Rome", expected="Rome"))
    assert v.status == "pass" and v.passed


def test_equals_fails_on_different_text() -> None:
    v = Equals()(inputs(output="Milan", expected="Rome"))
    assert v.status == "fail"
    assert v.score.score == 0.0


def test_equals_compares_conversations_ignoring_the_container() -> None:
    # list against tuple: without normalization this would fail because of the
    # container type rather than the content.
    turns = [Message("user", "hello"), Message("assistant", "hi")]
    v = Equals()(inputs(output=turns, expected=tuple(turns)))
    assert v.status == "pass"


def test_equals_errors_without_expected() -> None:
    v = Equals()(inputs(output="Rome"))
    assert v.status == "error"
    assert v.score.score is None
    assert "expected is missing" in v.reason


def test_equals_errors_across_output_branches() -> None:
    v = Equals()(inputs(output="Rome", expected={"city": "Rome"}))
    assert v.status == "error"
    assert "not comparable" in v.reason


# --------------------------------------------------------------------------- #
# Contains
# --------------------------------------------------------------------------- #


def test_contains_passes() -> None:
    assert (
        Contains(needle="Rome")(inputs(output="The capital is Rome.")).status == "pass"
    )


def test_contains_fails() -> None:
    v = Contains(needle="Rome")(inputs(output="The capital is Milan."))
    assert v.status == "fail"
    assert "not found" in v.reason


def test_contains_honours_case_sensitivity() -> None:
    assert Contains(needle="rome")(inputs(output="Rome")).status == "fail"
    assert (
        Contains(needle="rome", case_sensitive=False)(inputs(output="Rome")).status
        == "pass"
    )


def test_contains_errors_on_a_mapping_instead_of_converting() -> None:
    """The explicit ADR 0001 case: no silent stringification."""
    v = Contains(needle="Rome")(inputs(output={"city": "Rome"}))
    assert v.status == "error"
    assert "does not accept 'structured' output" in v.reason


def test_contains_errors_on_a_conversation() -> None:
    v = Contains(needle="hello")(inputs(output=[Message("user", "hello")]))
    assert v.status == "error"


def test_contains_rejects_an_empty_needle() -> None:
    with pytest.raises(ValueError, match="always passes"):
        Contains(needle="")


# --------------------------------------------------------------------------- #
# Regex
# --------------------------------------------------------------------------- #


def test_regex_passes() -> None:
    assert Regex(pattern=r"\d{4}")(inputs(output="year 2026")).status == "pass"


def test_regex_fails() -> None:
    v = Regex(pattern=r"\d{4}")(inputs(output="no year here"))
    assert v.status == "fail"


def test_regex_errors_on_structured_output() -> None:
    assert Regex(pattern=r"\d")(inputs(output={"n": 1})).status == "error"


def test_regex_rejects_an_invalid_pattern_at_load_time() -> None:
    # A broken pattern is a configuration error: it must be loud immediately,
    # not silently `error` on every case.
    with pytest.raises(ValueError, match="does not compile"):
        Regex(pattern="[")


# --------------------------------------------------------------------------- #
# JsonSchema
# --------------------------------------------------------------------------- #

SCHEMA = {
    "type": "object",
    "properties": {"name": {"type": "string"}, "age": {"type": "integer"}},
    "required": ["name", "age"],
}


def test_json_schema_passes_on_structured_output() -> None:
    v = JsonSchema(schema=SCHEMA)(inputs(output={"name": "Ada", "age": 36}))
    assert v.status == "pass"


def test_json_schema_passes_on_json_text() -> None:
    v = JsonSchema(schema=SCHEMA)(inputs(output='{"name": "Ada", "age": 36}'))
    assert v.status == "pass"


def test_json_schema_fails_on_a_violation() -> None:
    v = JsonSchema(schema=SCHEMA)(inputs(output={"name": "Ada", "age": "thirty-six"}))
    assert v.status == "fail"
    assert "age" in v.reason


def test_json_schema_errors_on_undecodable_json() -> None:
    """An undecodable output is a different problem from a schema violation:
    conflating them would make the diff unreadable."""
    v = JsonSchema(schema=SCHEMA)(inputs(output="this is not JSON"))
    assert v.status == "error"
    assert "not decodable" in v.reason


def test_json_schema_rejects_an_invalid_schema() -> None:
    with pytest.raises(ValueError, match="not a valid schema"):
        JsonSchema(schema={"type": "nonexistent"})


# --------------------------------------------------------------------------- #
# LlmRubric
# --------------------------------------------------------------------------- #


def fixed_judge(score: float, reason: str = "because") -> Judge:
    def _judge(prompt: str) -> JudgeReply:
        assert prompt  # the prompt is composed by the core, not by the judge
        return JudgeReply(score=score, reason=reason)

    return _judge


def test_llm_rubric_passes() -> None:
    a = LlmRubric(
        rubric="Is it polite?", judge=fixed_judge(0.9), threshold=0.7, tolerance=0.05
    )
    v = a(inputs(output="Good morning, how may I help you?"))
    assert v.status == "pass"
    assert v.tolerance == 0.05


def test_llm_rubric_fails_below_threshold() -> None:
    a = LlmRubric(
        rubric="Is it polite?", judge=fixed_judge(0.4), threshold=0.7, tolerance=0.05
    )
    assert a(inputs(output="What do you want.")).status == "fail"


def test_llm_rubric_errors_when_the_judge_blows_up() -> None:
    def broken_judge(prompt: str) -> JudgeReply:
        raise RuntimeError("timeout")

    a = LlmRubric(
        rubric="Is it polite?", judge=broken_judge, threshold=0.7, tolerance=0.05
    )
    v = a(inputs(output="anything"))
    assert v.status == "error"
    assert "RuntimeError" in v.reason


def test_llm_rubric_errors_on_an_out_of_range_score() -> None:
    a = LlmRubric(
        rubric="Is it polite?", judge=fixed_judge(7.0), threshold=0.7, tolerance=0.05
    )
    assert a(inputs(output="anything")).status == "error"


def test_llm_rubric_errors_on_an_unjustified_judgement() -> None:
    a = LlmRubric(
        rubric="Is it polite?",
        judge=fixed_judge(0.9, ""),
        threshold=0.7,
        tolerance=0.05,
    )
    assert a(inputs(output="anything")).status == "error"


def test_llm_rubric_demands_an_explicit_tolerance() -> None:
    # No default: an LLM judge is not reproducible, and an implicit tolerance
    # over a noisy value is another way of being vacuously green.
    with pytest.raises(TypeError):
        LlmRubric(rubric="Is it polite?", judge=fixed_judge(0.9), threshold=0.7)  # type: ignore[call-arg]


# --------------------------------------------------------------------------- #
# Budgets
# --------------------------------------------------------------------------- #


def test_cost_budget_passes_exactly_at_budget() -> None:
    v = CostBudget(max_usd=0.10, tolerance=0.02)(inputs(output="x", cost_usd=0.10))
    assert v.status == "pass"
    assert v.score.score == pytest.approx(0.5)


def test_cost_budget_fails_over_budget() -> None:
    v = CostBudget(max_usd=0.10, tolerance=0.02)(inputs(output="x", cost_usd=0.15))
    assert v.status == "fail"
    assert "over budget" in v.reason


def test_cost_budget_is_graded_so_drift_stays_visible() -> None:
    """The score must move below the threshold, otherwise `compare()` could not
    catch a cost that grows while staying under the cap."""
    cheap = CostBudget(max_usd=0.10, tolerance=0.02)(inputs(output="x", cost_usd=0.01))
    pricey = CostBudget(max_usd=0.10, tolerance=0.02)(inputs(output="x", cost_usd=0.09))
    assert cheap.status == pricey.status == "pass"
    assert cheap.score.score is not None and pricey.score.score is not None
    assert cheap.score.score > pricey.score.score


def test_cost_budget_errors_without_data() -> None:
    v = CostBudget(max_usd=0.10, tolerance=0.02)(inputs(output="x"))
    assert v.status == "error"
    assert "unverifiable budget" in v.reason


def test_latency_budget_fails_over_budget() -> None:
    v = LatencyBudget(max_ms=1000, tolerance=0.02)(inputs(output="x", latency_ms=2500))
    assert v.status == "fail"


def test_latency_budget_errors_without_data() -> None:
    assert (
        LatencyBudget(max_ms=1000, tolerance=0.02)(inputs(output="x")).status == "error"
    )


def test_budgets_reject_a_non_positive_cap() -> None:
    with pytest.raises(ValueError):
        CostBudget(max_usd=0, tolerance=0.02)
    with pytest.raises(ValueError):
        LatencyBudget(max_ms=-1, tolerance=0.02)


# --------------------------------------------------------------------------- #
# Budget scale: the behaviour past the cap
# --------------------------------------------------------------------------- #


def test_budget_score_is_exactly_half_at_the_cap() -> None:
    """This is what lets a threshold of 0.5 mean "within budget" without
    encoding the same fact twice."""
    assert budget_score(0.10, 0.10) == pytest.approx(0.5)
    assert budget_score(0.0, 0.10) == pytest.approx(1.0)


def test_cost_budget_at_two_and_a_half_times_the_cap() -> None:
    """The boundary case. A clamped linear scale would return 0.0 here and lose
    every distinction past 2x; this returns 1 / 3.5."""
    v = CostBudget(max_usd=0.10, tolerance=0.02)(inputs(output="x", cost_usd=0.25))
    assert v.status == "fail"
    assert v.score.score == pytest.approx(1 / 3.5)
    assert v.score.metadata["ratio"] == pytest.approx(2.5)


def test_latency_budget_at_two_and_a_half_times_the_cap() -> None:
    v = LatencyBudget(max_ms=1000, tolerance=0.02)(inputs(output="x", latency_ms=2500))
    assert v.status == "fail"
    assert v.score.score == pytest.approx(1 / 3.5)
    assert v.score.metadata["ratio"] == pytest.approx(2.5)


def test_the_budget_score_never_saturates() -> None:
    """3x and 10x over the cap must stay distinguishable, otherwise a regression
    past the boundary would be invisible to `compare()`."""
    three = CostBudget(max_usd=0.10, tolerance=0.02)(inputs(output="x", cost_usd=0.30))
    ten = CostBudget(max_usd=0.10, tolerance=0.02)(inputs(output="x", cost_usd=1.00))
    assert three.score.score is not None and ten.score.score is not None
    assert three.score.score > ten.score.score > 0.0


def test_the_budget_score_is_strictly_decreasing_and_always_in_range() -> None:
    scores = [
        budget_score(multiplier * 0.10, 0.10)
        for multiplier in (0, 0.5, 1, 2, 2.5, 3, 10, 100, 10_000)
    ]
    assert all(0.0 < s <= 1.0 for s in scores)
    assert scores == sorted(scores, reverse=True)
    assert len(set(scores)) == len(scores)  # no two multipliers collide


def test_budgets_demand_an_explicit_tolerance() -> None:
    """Same argument as `LlmRubric`: cost varies with sampling and retries,
    latency with the network, so a silent tolerance of zero would turn ordinary
    noise into a regression on every run."""
    with pytest.raises(TypeError):
        CostBudget(max_usd=0.10)  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        LatencyBudget(max_ms=1000)  # type: ignore[call-arg]


def test_a_cost_wobble_within_tolerance_is_not_a_regression() -> None:
    """0.010 -> 0.012 under a 0.10 cap moves the score by ~0.016. With an
    explicit tolerance of 0.02 that is noise; with the old default of 0.0 it
    would have been reported as a regression."""
    from digline.core import CaseResult, Run, compare

    def run_at(cost: float, tolerance: float) -> Run:
        budget = CostBudget(max_usd=0.10, tolerance=tolerance)
        return Run(
            tenant="acme",
            environment="test",
            suite="s",
            config_hash="h",
            created_at="2026-01-01T00:00:00+00:00",
            results=(CaseResult("c", (budget(inputs(output="x", cost_usd=cost)),)),),
        )

    tolerant = compare(run_at(0.012, 0.02), run_at(0.010, 0.02))
    assert tolerant.counts == {"unchanged": 1}

    # The same wobble, judged with no tolerance at all.
    strict = compare(run_at(0.012, 0.0), run_at(0.010, 0.0))
    assert strict.counts == {"regressed": 1}


def test_budget_metadata_always_carries_the_raw_values() -> None:
    """The score is a comparable quantity; the metadata is the raw truth, and it
    survives into the committed baseline."""
    cost = CostBudget(max_usd=0.10, tolerance=0.02)(inputs(output="x", cost_usd=0.25))
    assert cost.score.metadata == {
        "cost_usd": pytest.approx(0.25),
        "max_usd": pytest.approx(0.10),
        "ratio": pytest.approx(2.5),
    }
    latency = LatencyBudget(max_ms=1000, tolerance=0.02)(
        inputs(output="x", latency_ms=250)
    )
    assert latency.score.metadata == {
        "latency_ms": pytest.approx(250.0),
        "max_ms": pytest.approx(1000.0),
        "ratio": pytest.approx(0.25),
    }


def test_the_raw_values_survive_a_baseline_round_trip() -> None:
    """Metadata is only useful if it reaches the reviewer reading the diff."""
    from digline.core import CaseResult, Run, run_from_json, run_to_json

    v = CostBudget(max_usd=0.10, tolerance=0.02)(inputs(output="x", cost_usd=0.25))
    r = Run(
        tenant="acme",
        environment="test",
        suite="s",
        config_hash="h",
        created_at="2026-01-01T00:00:00+00:00",
        results=(CaseResult("c", (v,)),),
    )
    restored = run_from_json(run_to_json(r))
    assert restored.results[0].verdicts[0].score.metadata["ratio"] == pytest.approx(2.5)


# --------------------------------------------------------------------------- #
# Cross-cutting invariant
# --------------------------------------------------------------------------- #


def test_an_assertion_that_is_not_a_dataclass_says_so() -> None:
    """`AssertionBase` derives `identity` from the declared fields, so the
    contract is explicit and the failure names it — rather than surfacing as a
    `TypeError` from `dataclasses.fields()` about an unrelated object."""

    class HandRolled(AssertionBase):
        name = "hand_rolled"
        threshold = 1.0
        tolerance = 0.0
        accepts = TEXT_ONLY

    with pytest.raises(TypeError, match="is not a .*dataclass"):
        _ = HandRolled().identity


def test_no_errored_verdict_is_ever_green() -> None:
    """The ADR 0001 constraint, checked across every error path at once."""
    errors = [
        Equals()(inputs(output="x")),
        Contains(needle="x")(inputs(output={"a": 1})),
        Regex(pattern="x")(inputs(output={"a": 1})),
        JsonSchema(schema=SCHEMA)(inputs(output="not json")),
        CostBudget(max_usd=1.0, tolerance=0.02)(inputs(output="x")),
        LatencyBudget(max_ms=1.0, tolerance=0.02)(inputs(output="x")),
    ]
    for v in errors:
        assert v.status == "error"
        assert v.passed is False
        assert v.score.score is None
        assert v.reason


# --------------------------------------------------------------------------- #
# NotContains
# --------------------------------------------------------------------------- #


def test_not_contains_passes_when_the_needle_is_absent() -> None:
    v = NotContains(needle="sorry")(inputs(output="Here is the answer."))
    assert v.status == "pass"


def test_not_contains_fails_when_the_needle_is_there() -> None:
    v = NotContains(needle="sorry")(inputs(output="I'm sorry, I can't."))
    assert v.status == "fail"
    assert "present in" in v.reason


def test_not_contains_folds_case_when_asked() -> None:
    v = NotContains(needle="SORRY", case_sensitive=False)(inputs(output="sorry"))
    assert v.status == "fail"


def test_an_empty_needle_would_always_fail_so_it_is_refused() -> None:
    """The mirror of `Contains`: there `''` is vacuously green, here vacuously
    red. Neither says anything about the output."""
    with pytest.raises(ValueError, match="always fail"):
        NotContains(needle="")


def test_not_contains_errors_on_structured_output() -> None:
    v = NotContains(needle="sorry")(inputs(output={"a": "sorry"}))
    assert v.status == "error"


# --------------------------------------------------------------------------- #
# Affix
# --------------------------------------------------------------------------- #


def test_affix_checks_the_start_by_default() -> None:
    v = Affix(affix="Dear")(inputs(output="Dear Sir,"))
    assert v.status == "pass" and v.score.name == "starts_with"


def test_affix_fails_at_the_wrong_end() -> None:
    """The same string is a suffix and not a prefix: the parameter is doing the
    work, not the search."""
    assert Affix(affix="Sir,", at="end")(inputs(output="Dear Sir,")).status == "pass"
    assert Affix(affix="Sir,", at="start")(inputs(output="Dear Sir,")).status == "fail"


def test_the_two_ends_have_different_names_so_a_report_can_tell_them_apart() -> None:
    starts, ends = Affix(affix="x"), Affix(affix="x", at="end")
    assert (starts.name, ends.name) == ("starts_with", "ends_with")
    assert starts.identity != ends.identity


def test_an_explicit_name_is_kept() -> None:
    assert Affix(affix="x", name="greeting").name == "greeting"


def test_an_empty_affix_is_refused() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        Affix(affix="")


def test_an_unknown_end_is_refused_at_construction() -> None:
    with pytest.raises(ValueError, match="'start' or 'end'"):
        Affix(affix="x", at="middle")  # type: ignore[arg-type]


def test_affix_errors_on_a_conversation() -> None:
    v = Affix(affix="Dear")(inputs(output=[Message("user", "Dear Sir")]))
    assert v.status == "error"


# --------------------------------------------------------------------------- #
# IsJson
# --------------------------------------------------------------------------- #


def test_is_json_passes_on_decodable_text() -> None:
    v = IsJson()(inputs(output='{"a": 1}'))
    assert v.status == "pass"
    assert v.score.metadata["json_kind"] == "object"


def test_undecodable_text_fails_rather_than_errors() -> None:
    """The opposite of `JsonSchema`, and deliberately: there the question was
    about a shape and could not be answered, so `error`. Here being decodable is
    the question, so a negative answer is a `fail`."""
    v = IsJson()(inputs(output="{not json"))
    assert v.status == "fail"
    assert v.score.metadata["json_kind"] == "invalid"


def test_the_failing_reason_carries_a_position_not_the_text() -> None:
    v = IsJson()(inputs(output='{"secret": "hunter2",,}'))
    assert v.status == "fail"
    assert "hunter2" not in v.reason


def test_a_scalar_fails_when_an_object_was_required() -> None:
    assert IsJson()(inputs(output="4")).status == "pass"
    v = IsJson(top_level="object")(inputs(output="4"))
    assert v.status == "fail"
    assert v.score.metadata["json_kind"] == "scalar"


def test_is_json_refuses_structured_output_instead_of_passing_it() -> None:
    """A `structured` output has already been decoded, so this check could only
    ever pass on one — the vacuously green assertion decision 3 forbids."""
    v = IsJson()(inputs(output={"a": 1}))
    assert v.status == "error"


def test_an_unknown_top_level_is_refused() -> None:
    with pytest.raises(ValueError, match="'any', 'object' or 'array'"):
        IsJson(top_level="dict")  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# Length
# --------------------------------------------------------------------------- #


def test_length_passes_within_bounds() -> None:
    v = Length(minimum=3, maximum=10)(inputs(output="hello"))
    assert v.status == "pass"
    assert v.score.metadata["length"] == 5


def test_length_fails_below_the_minimum() -> None:
    v = Length(minimum=10)(inputs(output="hi"))
    assert v.status == "fail"
    assert "below the minimum" in v.reason


def test_length_fails_above_the_maximum() -> None:
    v = Length(maximum=3)(inputs(output="hello"))
    assert v.status == "fail"
    assert "above the maximum" in v.reason


def test_words_are_whitespace_runs_not_tokens() -> None:
    v = Length(maximum=3, unit="words")(inputs(output="  one   two  three  "))
    assert v.status == "pass"
    assert v.score.metadata["length"] == 3


def test_the_measurement_travels_even_on_a_pass() -> None:
    """ "How long are the answers getting" is a question the metadata answers and
    a pass/fail cannot."""
    v = Length(maximum=100)(inputs(output="x" * 42))
    assert v.status == "pass" and v.score.metadata["length"] == 42


def test_length_without_bounds_is_refused() -> None:
    with pytest.raises(ValueError, match="every output passes"):
        Length()


def test_an_impossible_pair_of_bounds_is_refused() -> None:
    with pytest.raises(ValueError, match="no output can satisfy both"):
        Length(minimum=10, maximum=3)


def test_a_negative_minimum_is_refused() -> None:
    with pytest.raises(ValueError, match="must not be negative"):
        Length(minimum=-1)


def test_an_unknown_unit_is_refused() -> None:
    with pytest.raises(ValueError, match="'characters' or 'words'"):
        Length(maximum=3, unit="tokens")  # type: ignore[arg-type]


def test_length_errors_on_structured_output() -> None:
    assert Length(maximum=3)(inputs(output={"a": 1})).status == "error"


# --------------------------------------------------------------------------- #
# Levenshtein
# --------------------------------------------------------------------------- #


def test_the_distance_is_the_textbook_one() -> None:
    assert levenshtein_distance("kitten", "sitting") == 3
    assert levenshtein_distance("", "abc") == 3
    assert levenshtein_distance("abc", "abc") == 0
    assert levenshtein_distance("flaw", "lawn") == 2


def test_the_distance_is_symmetric() -> None:
    assert levenshtein_distance("kitten", "sitting") == levenshtein_distance(
        "sitting", "kitten"
    )


def test_levenshtein_passes_on_a_near_match() -> None:
    v = Levenshtein(threshold=0.7)(inputs(output="Roma", expected="Rome"))
    assert v.status == "pass"
    assert v.score.metadata["distance"] == 1
    assert v.score.score == 0.75  # one edit over four characters


def test_the_threshold_is_read_against_the_measured_similarity() -> None:
    """The same output, one threshold apart: 0.75 is below 0.8 and above 0.7."""
    over = Levenshtein(threshold=0.8)(inputs(output="Roma", expected="Rome"))
    assert over.status == "fail" and over.score.score == 0.75


def test_levenshtein_fails_when_it_is_not_near_enough() -> None:
    v = Levenshtein(threshold=0.9)(inputs(output="Milan", expected="Rome"))
    assert v.status == "fail"


def test_a_near_miss_and_gibberish_are_told_apart() -> None:
    """This is the whole reason to have it next to `Equals`, which calls both
    of these `0.0`."""
    near = Levenshtein()(inputs(output="Rome.", expected="Rome"))
    far = Levenshtein()(inputs(output="qzxvb", expected="Rome"))
    assert near.score.score is not None and far.score.score is not None
    assert near.score.score > 0.7 > far.score.score


def test_two_empty_strings_are_identical_not_a_division_by_zero() -> None:
    v = Levenshtein()(inputs(output="", expected=""))
    assert v.status == "pass" and v.score.score == 1.0


def test_levenshtein_errors_without_expected() -> None:
    assert Levenshtein()(inputs(output="Rome")).status == "error"


def test_levenshtein_errors_when_expected_is_not_text() -> None:
    v = Levenshtein()(inputs(output="Rome", expected={"city": "Rome"}))
    assert v.status == "error"


def test_the_reason_does_not_quote_either_string() -> None:
    v = Levenshtein()(inputs(output="the patient is Mario Rossi", expected="redacted"))
    assert "Mario Rossi" not in v.reason


def test_a_threshold_outside_the_range_is_refused() -> None:
    with pytest.raises(ValueError, match=r"within \[0, 1\]"):
        Levenshtein(threshold=1.5)


# --------------------------------------------------------------------------- #
# PiiAbsent
# --------------------------------------------------------------------------- #

#: A structurally valid IBAN. The same number appears below broken by the spaces
#: a person types, and once more with one digit changed so the checksum fails.
IBAN = "IT60X0542811101000000123456"
IBAN_SPACED = "IT60 X054 2811 1010 0000 0123 456"
IBAN_BAD_CHECKSUM = "IT61X0542811101000000123456"

#: Published examples, kept because they are the only strings here whose check
#: character was not computed by the code under test.
CF = "MRTMTT25D09F205Z"
PARTITA_IVA = "00743110157"


def test_a_clean_output_passes_and_says_what_was_checked() -> None:
    v = PiiAbsent()(inputs(output="The order has shipped."))
    assert v.status == "pass"
    assert v.score.metadata["pii_total"] == 0
    assert "iban" in v.reason  # what was looked for, not what was found


def test_a_real_iban_is_found() -> None:
    v = PiiAbsent()(inputs(output=f"Send it to {IBAN} please."))
    assert v.status == "fail"
    assert v.score.metadata["pii_iban"] == 1


def test_the_same_iban_broken_by_spaces_is_the_same_iban() -> None:
    """The way a person actually types it. A pattern that only matched the
    compact form would pass on the commonest way of leaking one."""
    v = PiiAbsent()(inputs(output=f"Send it to {IBAN_SPACED} please."))
    assert v.status == "fail"
    assert v.score.metadata["pii_iban"] == 1


def test_the_right_shape_with_the_wrong_checksum_is_not_reported() -> None:
    """One digit changed. Without the mod-97 check this would be reported, and
    an assertion that cries wolf is one that gets switched off."""
    v = PiiAbsent()(inputs(output=f"Reference {IBAN_BAD_CHECKSUM} is internal."))
    assert v.score.metadata["pii_iban"] == 0


def test_the_checksum_carries_the_codice_fiscale_and_the_vat_number_too() -> None:
    found = PiiAbsent()(inputs(output=f"{CF} and {PARTITA_IVA}"))
    assert found.score.metadata["pii_codice_fiscale"] == 1
    assert found.score.metadata["pii_partita_iva"] == 1

    # Same shapes, last character changed: eleven digits are not a VAT number
    # and sixteen alphanumerics are not a codice fiscale.
    clean = PiiAbsent(patterns=ITALIAN_PII[:3])(
        inputs(output=f"{CF[:15]}A and {PARTITA_IVA[:10]}8")
    )
    assert clean.score.metadata["pii_total"] == 0


def test_an_email_is_found_without_a_checksum_to_verify() -> None:
    v = PiiAbsent()(inputs(output="write to mario.rossi@example.com"))
    assert v.status == "fail"
    assert v.score.metadata["pii_email"] == 1


def test_neither_the_reason_nor_the_metadata_carries_what_was_found() -> None:
    """The whole point of the assertion: it reports that an identifier is there
    without becoming the second place it is written down."""
    v = PiiAbsent()(inputs(output=f"{IBAN} and mario.rossi@example.com"))
    assert IBAN not in v.reason
    assert "mario.rossi" not in v.reason
    rendered = str(sorted(v.score.metadata.items()))
    assert IBAN not in rendered and "mario.rossi" not in rendered


def test_every_pattern_is_reported_including_the_ones_that_found_nothing() -> None:
    """`pii_iban: 0` also says "we looked", and stable keys are what let a
    sampled run fold its metadata."""
    v = PiiAbsent()(inputs(output="nothing here"))
    for pattern in ITALIAN_PII:
        assert f"pii_{pattern.name}" in v.score.metadata


def test_the_pattern_list_is_extensible_by_construction() -> None:
    badge = PiiPattern("badge", r"\bEMP-\d{5}\b")
    v = PiiAbsent(patterns=(*ITALIAN_PII, badge))(inputs(output="ticket EMP-01234"))
    assert v.status == "fail"
    assert v.score.metadata["pii_badge"] == 1


def test_two_patterns_under_one_name_are_refused() -> None:
    with pytest.raises(ValueError, match="indistinguishable"):
        PiiAbsent(patterns=(PiiPattern("x", "a"), PiiPattern("x", "b")))


def test_no_patterns_at_all_is_refused() -> None:
    with pytest.raises(ValueError, match="every output passes"):
        PiiAbsent(patterns=())


def test_a_pattern_that_does_not_compile_is_refused_at_construction() -> None:
    with pytest.raises(ValueError, match="does not compile"):
        PiiPattern("broken", "(unclosed")


def test_pii_absent_errors_on_structured_output() -> None:
    """Which field of a dict holds prose is a decision, and it must not be taken
    in silence."""
    assert PiiAbsent()(inputs(output={"iban": IBAN})).status == "error"


# --------------------------------------------------------------------------- #
# Faithfulness
# --------------------------------------------------------------------------- #


def claim_judge(supported: int, total: int, reason: str = "counted") -> ClaimJudge:
    """A deterministic stand-in for the model. Tests about arithmetic must not
    depend on a judge that is free to disagree with itself."""

    def judge(prompt: str) -> ClaimReply:
        return ClaimReply(supported=supported, total=total, reason=reason)

    return judge


def faithfulness(judge: ClaimJudge, threshold: float = 0.8) -> Faithfulness:
    return Faithfulness(judge=judge, threshold=threshold, tolerance=0.1)


def test_the_score_is_the_supported_fraction() -> None:
    v = faithfulness(claim_judge(3, 4))(
        inputs(output="three of these are in the source", context=["source"])
    )
    assert v.score.score == 0.75
    assert v.score.metadata["claims_total"] == 4
    assert v.score.metadata["claims_supported"] == 3


def test_faithfulness_fails_below_its_threshold() -> None:
    v = faithfulness(claim_judge(1, 4))(inputs(output="mostly invented", context=["s"]))
    assert v.status == "fail"


def test_the_core_does_the_division_not_the_model() -> None:
    """The judge reports two counts it can be held to; a judge asked for a ratio
    returns a number nothing can contradict."""
    v = faithfulness(claim_judge(2, 3))(inputs(output="x", context=["s"]))
    assert v.score.score == pytest.approx(2 / 3)


def test_more_supported_than_found_is_refused_at_the_boundary() -> None:
    with pytest.raises(ValueError, match="more claims than it found"):
        ClaimReply(supported=5, total=3, reason="r")


def test_negative_counts_are_refused() -> None:
    with pytest.raises(ValueError, match="must not be negative"):
        ClaimReply(supported=-1, total=3, reason="r")


def test_an_unexplained_count_is_refused() -> None:
    with pytest.raises(ValueError, match="reason is mandatory"):
        ClaimReply(supported=1, total=3, reason="")


def test_an_empty_context_errors_rather_than_passing() -> None:
    """Faithfulness to nothing would be the vacuously green assertion."""
    v = faithfulness(claim_judge(0, 0))(inputs(output="anything"))
    assert v.status == "error"
    assert "faithful to" in v.reason


def test_an_output_with_no_claims_errors_rather_than_scoring_one() -> None:
    """A perfect score there would reward saying nothing."""
    v = faithfulness(claim_judge(0, 0))(inputs(output="Hello.", context=["source"]))
    assert v.status == "error"
    assert v.score.score is None


def test_a_judge_that_raises_is_an_error_not_a_failure() -> None:
    def broken(prompt: str) -> ClaimReply:
        raise RuntimeError("no model")

    v = faithfulness(broken)(inputs(output="x", context=["s"]))
    assert v.status == "error"
    assert "RuntimeError" in v.reason


def test_the_prompt_carries_the_context_and_the_output() -> None:
    seen: list[str] = []

    def recording(prompt: str) -> ClaimReply:
        seen.append(prompt)
        return ClaimReply(supported=1, total=1, reason="r")

    faithfulness(recording)(
        inputs(output="Rome is the capital.", context=["Rome is the capital of Italy."])
    )
    assert "Rome is the capital of Italy." in seen[0]
    assert "Rome is the capital." in seen[0]


def test_faithfulness_errors_on_a_conversation() -> None:
    """Which turn holds the claims is a decision, and it is not taken here."""
    v = faithfulness(claim_judge(1, 1))(
        inputs(output=[Message("assistant", "x")], context=["s"])
    )
    assert v.status == "error"


def test_faithfulness_needs_a_threshold_and_a_tolerance() -> None:
    with pytest.raises(TypeError):
        Faithfulness(judge=claim_judge(1, 1))  # type: ignore[call-arg]
