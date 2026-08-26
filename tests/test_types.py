"""Invariants of the domain values.

These types are the only place where a wrong value can be *prevented* rather
than detected. Every check here exists because the alternative is a plausible
lie travelling all the way into a committed baseline.
"""

from __future__ import annotations

import math

import pytest

from digline.core import (
    JudgeReply,
    Message,
    Score,
    Verdict,
    output_kind,
)
from digline.core.types import canonical, normalize_output


def ok_verdict(**kwargs: object) -> Verdict:
    base: dict[str, object] = {
        "score": Score(name="x", score=1.0),
        "threshold": 0.5,
        "status": "pass",
        "reason": "r",
    }
    base.update(kwargs)
    return Verdict(**base)  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# Verdict cannot contradict itself
# --------------------------------------------------------------------------- #


def test_a_pass_below_the_threshold_is_refused() -> None:
    with pytest.raises(ValueError, match="contradicts score"):
        Verdict(
            score=Score(name="x", score=0.3),
            threshold=0.7,
            status="pass",
            reason="r",
        )


def test_a_fail_at_or_above_the_threshold_is_refused() -> None:
    with pytest.raises(ValueError, match="contradicts score"):
        Verdict(
            score=Score(name="x", score=0.9),
            threshold=0.7,
            status="fail",
            reason="r",
        )


def test_the_boundary_counts_as_a_pass() -> None:
    v = ok_verdict(score=Score(name="x", score=0.7), threshold=0.7, status="pass")
    assert v.passed


def test_a_consistent_fail_is_accepted() -> None:
    v = ok_verdict(score=Score(name="x", score=0.69), threshold=0.7, status="fail")
    assert not v.passed


def test_the_contradiction_check_does_not_apply_to_errors() -> None:
    """An errored verdict has no score to agree or disagree with."""
    v = ok_verdict(score=Score(name="x", score=None), threshold=0.7, status="error")
    assert v.status == "error" and not v.passed


def test_the_threshold_must_be_within_range() -> None:
    for bad in (-0.1, 1.5):
        with pytest.raises(ValueError, match=r"threshold must be within"):
            ok_verdict(threshold=bad, status="fail" if bad > 1 else "pass")


# --------------------------------------------------------------------------- #
# NaN is rejected explicitly, not by accident
# --------------------------------------------------------------------------- #


def test_a_nan_score_is_named_as_such() -> None:
    with pytest.raises(ValueError, match="must not be NaN"):
        Score(name="x", score=math.nan)


def test_a_nan_judge_score_is_named_as_such() -> None:
    with pytest.raises(ValueError, match="must not be NaN"):
        JudgeReply(score=math.nan, reason="r")


# --------------------------------------------------------------------------- #
# JudgeReply validates at the boundary where the LLM enters
# --------------------------------------------------------------------------- #


def test_a_judge_score_outside_the_range_is_refused() -> None:
    with pytest.raises(ValueError, match=r"within \[0, 1\]"):
        JudgeReply(score=7.0, reason="r")


def test_an_unexplained_judgement_is_refused() -> None:
    with pytest.raises(ValueError, match="reason is mandatory"):
        JudgeReply(score=0.9, reason="")


def test_a_well_formed_judgement_is_accepted() -> None:
    assert JudgeReply(score=0.0, reason="nothing matched").score == 0.0


# --------------------------------------------------------------------------- #
# normalize_output goes all the way down
# --------------------------------------------------------------------------- #


def test_nested_sequences_compare_regardless_of_container() -> None:
    """The shallow version left `{"a": ["x"]}` and `{"a": ("x",)}` unequal — the
    same defect one level down, where it is harder to notice."""
    assert normalize_output({"a": ["x"]}) == normalize_output({"a": ("x",)})


def test_deeply_nested_structures_normalize() -> None:
    deep_list = {"a": {"b": [{"c": ["d"]}]}}
    deep_tuple = {"a": {"b": ({"c": ("d",)},)}}
    assert normalize_output(deep_list) == normalize_output(deep_tuple)


def test_normalization_still_distinguishes_different_content() -> None:
    assert normalize_output({"a": ["x"]}) != normalize_output({"a": ["y"]})
    assert normalize_output({"a": ["x", "y"]}) != normalize_output({"a": ["y", "x"]})


def test_strings_are_not_taken_apart_as_sequences() -> None:
    assert normalize_output("abc") == "abc"
    assert normalize_output({"a": "xy"}) == normalize_output({"a": "xy"})
    assert normalize_output({"a": "xy"}) != normalize_output({"a": ["x", "y"]})


def test_conversations_normalize_across_containers() -> None:
    turns = [Message("user", "hi")]
    assert normalize_output(turns) == normalize_output(tuple(turns))


# --------------------------------------------------------------------------- #
# The empty conversation
# --------------------------------------------------------------------------- #


def test_an_empty_sequence_is_an_empty_conversation() -> None:
    """Deliberate, not an accident of `all()` on an empty iterable: a model that
    produced no turns is a real outcome worth judging."""
    assert output_kind([]) == "conversation"
    assert output_kind(()) == "conversation"


def test_a_sequence_of_non_messages_is_not_an_output() -> None:
    assert output_kind([1, 2, 3]) is None
    assert output_kind([Message("user", "hi"), "not a message"]) is None


def test_the_other_branches_are_unaffected() -> None:
    assert output_kind("") == "text"
    assert output_kind({}) == "structured"
    assert output_kind(object()) is None


# --------------------------------------------------------------------------- #
# canonical() is deterministic by construction
# --------------------------------------------------------------------------- #


def test_sets_are_ordered_so_they_can_be_fingerprinted() -> None:
    assert canonical(frozenset({"b", "a"})) == canonical(frozenset({"a", "b"}))
    assert canonical(frozenset({"b", "a"})) == ["a", "b"]


def test_an_unrecognised_object_collapses_to_its_type_name() -> None:
    """Never its `repr`: the default carries a memory address, which would make
    a committed baseline churn on every run."""

    class Opaque:
        pass

    rendered = canonical(Opaque())
    assert rendered == "<Opaque>"
    assert "0x" not in str(rendered)


def test_non_finite_floats_survive_visibly() -> None:
    assert canonical(math.inf) == "inf"
    assert canonical(math.nan) == "nan"


# --------------------------------------------------------------------------- #
# The accepts constants are part of the public surface (friction 12)
# --------------------------------------------------------------------------- #


def test_the_accepts_constants_come_from_the_package() -> None:
    """Writing a custom assertion needed a reach into `digline.core.types`,
    which is not documented and not stable."""
    import digline.core as core

    for name in (
        "TEXT_ONLY",
        "STRUCTURED_ONLY",
        "TEXT_OR_STRUCTURED",
        "TEXT_OR_CONVERSATION",
        "CONVERSATION_ONLY",
        "ALL_KINDS",
    ):
        assert name in core.__all__, name
        assert isinstance(getattr(core, name), frozenset)


def test_structured_only_was_the_one_that_was_missing() -> None:
    from digline.core import ALL_KINDS, STRUCTURED_ONLY

    assert frozenset({"structured"}) == STRUCTURED_ONLY
    assert STRUCTURED_ONLY < ALL_KINDS
