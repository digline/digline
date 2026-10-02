"""A tolerance that holds every movement a score can make. Said, never refused.

`compare()` reads for a flip before it reads the tolerance, so a tolerance only
judges a score that stayed on one side of its threshold. A tolerance at least as
wide as the wider side switches the check off, and at threshold 0.5 that is a
tolerance of 0.5, not the 1.0 #386 first wrote down. The rule is
`tolerance_is_blind`; what it cannot see is listed in its docstring.

The test that matters most here is `test_the_predicate_is_what_compare_does`.
It holds the predicate against `compare()` itself rather than against a copy
of its arithmetic, so a change to the order of `compare()`'s rules, or to its
precision, reddens this file instead of leaving a warning that describes a
comparison digline no longer makes.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from tests._helpers import cli

from digline.core import (
    STORAGE_STEP,
    Accuracy,
    CaseResult,
    Contains,
    JudgeReply,
    LlmRubric,
    Repeated,
    Run,
    Score,
    Verdict,
    at_precision,
    compare,
    tolerance_is_blind,
)
from digline.run import BlindTolerance, Case, Suite, blind_tolerances

CREATED = "2026-10-02T09:00:00+00:00"


def verdict(score: float, threshold: float, tolerance: float) -> Verdict:
    return Verdict(
        score=Score(name="check", score=score),
        threshold=threshold,
        tolerance=tolerance,
        status="pass" if at_precision(score) >= at_precision(threshold) else "fail",
        reason="test reason",
        assertion_id="check",
    )


def run_of(v: Verdict) -> Run:
    return Run(
        tenant="acme",
        environment="test",
        suite="test-suite",
        config_hash="hash-a",
        created_at=CREATED,
        results=(CaseResult(case_id="case-1", verdicts=(v,)),),
    )


def outcome(threshold: float, tolerance: float, before: float, now: float) -> str:
    current = run_of(verdict(now, threshold, tolerance))
    baseline = run_of(verdict(before, threshold, tolerance))
    (delta,) = compare(current, baseline).deltas
    return delta.outcome


def extremes(threshold: float) -> list[tuple[float, float]]:
    """The widest move on each side of `threshold`, both ways."""
    moves = [(1.0, threshold), (threshold, 1.0)]
    if threshold > 0:
        low = at_precision(threshold - STORAGE_STEP)
        moves += [(low, 0.0), (0.0, low)]
    return moves


# --------------------------------------------------------------------------- #
# The rule, at its edges
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("threshold", "tolerance", "blind"),
    [
        # #386's own numbers: threshold 0.5, and the check is blind at 0.5.
        (0.5, 0.5, True),
        (0.5, 0.499999, False),
        # The failing side is the wider one, and its bound is strict.
        (0.8, 0.799999, True),
        (0.8, 0.799998, False),
        # The passing side is the wider one.
        (0.2, 0.8, True),
        (0.2, 0.799999, False),
        # A threshold of 0 has no failing side; one of 1 has a passing side of
        # one point.
        (0.0, 1.0, True),
        (0.0, 0.999999, False),
        (1.0, 0.999999, True),
        (1.0, 0.999998, False),
        # The ordinary declarations stay silent.
        (0.7, 0.05, False),
        (0.9, 0.1, False),
        (1.0, 0.0, False),
    ],
)
def test_the_rule_at_its_edges(threshold: float, tolerance: float, blind: bool) -> None:
    assert tolerance_is_blind(threshold, tolerance) is blind


def test_blindness_starts_at_one_half_and_never_lower() -> None:
    """The widest side is never narrower than half the scale, so a tolerance
    below 0.5 is never called blind, whatever the threshold."""
    thresholds = [i / 100 for i in range(101)]
    assert not any(tolerance_is_blind(t, 0.499998) for t in thresholds)
    assert tolerance_is_blind(0.5, 0.5)


# --------------------------------------------------------------------------- #
# The rule is compare()'s, not a copy of it
# --------------------------------------------------------------------------- #


THRESHOLDS = [0.0, 0.1, 0.25, 0.5, 0.7, 0.8, 0.9, 1.0]


def _tolerances(threshold: float) -> list[float]:
    """Around both sides' widest move, and a few ordinary values."""
    edges = [1.0 - threshold]
    if threshold > 0:
        edges.append(threshold - STORAGE_STEP)
    near = [
        at_precision(edge + step)
        for edge in edges
        for step in (-STORAGE_STEP, 0.0, STORAGE_STEP)
    ]
    return sorted({t for t in [0.0, 0.05, 0.3, 0.5, 1.0, *near] if t >= 0})


@pytest.mark.parametrize("threshold", THRESHOLDS)
def test_the_predicate_is_what_compare_does(threshold: float) -> None:
    """Blind exactly when every widest move on either side compares
    `unchanged`, measured through `compare()` and not re-derived."""
    for tolerance in _tolerances(threshold):
        silent = all(
            outcome(threshold, tolerance, before, now) == "unchanged"
            for before, now in extremes(threshold)
        )
        assert tolerance_is_blind(threshold, tolerance) is silent, (
            f"threshold {threshold}, tolerance {tolerance}: the predicate says "
            f"{tolerance_is_blind(threshold, tolerance)}, compare() says "
            f"{'every move is unchanged' if silent else 'a move is reported'}"
        )


def test_a_flip_is_still_reported_by_a_blind_tolerance() -> None:
    """What blind does not mean: the flip is read before the tolerance."""
    assert tolerance_is_blind(0.5, 1.0)
    assert outcome(0.5, 1.0, 1.0, 0.0) == "regressed"


# --------------------------------------------------------------------------- #
# Read off the suite
# --------------------------------------------------------------------------- #


def judge(prompt: str) -> JudgeReply:
    return JudgeReply(score=1.0, reason="looked")


def suite_of(*checks: object, run_checks: tuple[object, ...] = ()) -> Suite:
    return Suite(
        tenant="acme",
        environment="test",
        name="blind",
        assertions=checks,  # type: ignore[arg-type]
        run_assertions=run_checks,  # type: ignore[arg-type]
        cases=[Case(id="one", label="positive")],
    )


def test_the_suite_names_each_blind_check_and_only_those() -> None:
    blind = LlmRubric(
        rubric="ok?", judge=judge, threshold=0.5, tolerance=0.5, name="loose"
    )
    fine = LlmRubric(rubric="ok?", judge=judge, threshold=0.7, tolerance=0.05)
    found = blind_tolerances(suite_of(Contains(needle="x"), blind, fine))
    assert found == (BlindTolerance("loose", 0.5, 0.5),)


def test_a_wrapped_check_is_read_through_its_wrapper() -> None:
    inner = LlmRubric(rubric="ok?", judge=judge, threshold=0.8, tolerance=0.8)
    found = blind_tolerances(
        suite_of(Repeated(inner=inner, samples=3, min_agreement="2/3"))
    )
    assert [b.name for b in found] == [inner.name]


def test_a_check_over_the_run_is_read_too() -> None:
    accuracy = Accuracy(over="contains", threshold="1/2", tolerance="1/2")
    found = blind_tolerances(suite_of(Contains(needle="x"), run_checks=(accuracy,)))
    assert found == (BlindTolerance("accuracy", 0.5, 0.5),)


def test_an_ordinary_suite_says_nothing() -> None:
    fine = LlmRubric(rubric="ok?", judge=judge, threshold=0.7, tolerance=0.05)
    assert blind_tolerances(suite_of(Contains(needle="x"), fine)) == ()


def test_the_sentence_names_the_check_its_numbers_and_what_still_speaks() -> None:
    sentence = BlindTolerance("loose", 0.5, 0.5).sentence()
    assert sentence == (
        "tolerance 0.5 on 'loose' (threshold 0.5) covers every movement its "
        "score can make without crossing the threshold: compare will report "
        "this check only when it flips between pass and fail"
    )


# --------------------------------------------------------------------------- #
# End to end — where the author reads it
# --------------------------------------------------------------------------- #


SUITE_PY = """
from digline.core import Contains, LlmRubric, JudgeReply
from digline.run import Case, Response, Suite


def judge(prompt):
    return JudgeReply(score=1.0, reason="looked")


suite = Suite(
    tenant="acme-bank",
    environment="staging",
    name="blind",
    assertions=[
        Contains(needle="Rome"),
        LlmRubric(rubric="ok?", judge=judge, threshold=0.5, tolerance=0.5,
                  name="loose"),
    ],
    cases=[Case(id="one")],
)


def target(case):
    return Response(output="Rome", input="capital?")
"""


def test_digline_run_says_so_on_stderr_and_exits_as_before(repo: Path) -> None:
    (repo / "suite_blind.py").write_text(SUITE_PY, encoding="utf-8")
    done = cli(repo, "run", "--suite", "suite_blind.py")
    assert done.returncode == 0, done.stderr
    assert (
        "digline: tolerance 0.5 on 'loose' (threshold 0.5) covers every movement"
        in done.stderr
    )
    assert "covers every movement" not in done.stdout

    quiet = cli(repo, "run", "--suite", "suite_qa.py")
    assert quiet.returncode == 0, quiet.stderr
    assert "covers every movement" not in quiet.stderr
