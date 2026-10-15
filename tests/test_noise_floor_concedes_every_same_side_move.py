"""For a binary check, below unanimity the noise floor excuses every same-side
movement there is.

ADR 0050's fourth point, held against `compare()` itself, and for a binary
check only: unanimity is a property of the outcomes, and only a check whose
samples are 0 and 1 has the interval `[0, 1]` once its baseline is divided on
them. For a check that is not binary this file says nothing.

At K=5 and threshold 0.5, every baseline and every current run is enumerated as a
count of passes, fails and samples that could not be judged, and folded by
`combine_samples` at each `min_agreement` five samples can produce; a fold that
errors can be neither a baseline nor a run that is compared, and is dropped.
Every pair on one side of the threshold then goes through `compare()` at
tolerance 0, so a pair reported `unchanged` with a nonzero delta was excused by
the floor and by nothing else.

What is held is the coincidence: at every `min_agreement`, the widest
same-side movement the folds permit and the widest the floor excuses are the
same number. At unanimity there is no pair at all for the floor to excuse,
which is what makes the ADR's "and nothing else" true. The figures the ADR
prints are held second, so that a number in a public text regenerates from an
artifact that runs in CI.
"""

from __future__ import annotations

from fractions import Fraction

import pytest

from digline.core import (
    CaseResult,
    Run,
    Score,
    Verdict,
    combine_samples,
    compare,
    reachable_agreements,
)
from digline.core.ratio import as_agreement

K = 5
THRESHOLD = 0.5
CREATED = "2026-10-15T09:00:00+00:00"


def sample(score: float | None) -> Verdict:
    if score is None:
        return Verdict(
            score=Score(name="vote", score=None),
            threshold=THRESHOLD,
            tolerance=0.0,
            status="error",
            reason="could not be judged",
            assertion_id="vote",
        )
    return Verdict(
        score=Score(name="vote", score=score),
        threshold=THRESHOLD,
        tolerance=0.0,
        status="pass" if score >= THRESHOLD else "fail",
        reason="a vote",
        assertion_id="vote",
    )


def run_of(verdict: Verdict) -> Run:
    return Run(
        tenant="acme",
        environment="test",
        suite="votes",
        config_hash="hash-a",
        created_at=CREATED,
        results=(CaseResult(case_id="case-1", verdicts=(verdict,)),),
    )


def folds(agreement: Fraction) -> list[Verdict]:
    """Every fold of K binary samples that `agreement` lets stand."""
    floor = as_agreement(agreement, samples=K, field="min_agreement")
    out: list[Verdict] = []
    for passes in range(K + 1):
        for fails in range(K + 1 - passes):
            errored = K - passes - fails
            verdicts = [sample(1.0)] * passes + [sample(0.0)] * fails
            verdicts += [sample(None)] * errored
            folded = combine_samples(verdicts, min_agreement=floor)
            if folded.status != "error":
                out.append(folded)
    return out


def widest(agreement: Fraction) -> tuple[float, float]:
    """The widest same-side movement, and the widest the floor excused."""
    stood = folds(agreement)
    permitted = excused = 0.0
    for before in stood:
        for now in stood:
            if before.status != now.status:
                continue
            delta = compare(run_of(now), run_of(before)).deltas[0]
            moved = abs(delta.delta or 0.0)
            permitted = max(permitted, moved)
            if delta.outcome == "unchanged" and delta.within_noise:
                excused = max(excused, moved)
    return permitted, excused


@pytest.mark.parametrize("agreement", reachable_agreements(K), ids=str)
def test_the_floor_excuses_the_widest_same_side_movement(agreement: Fraction) -> None:
    permitted, excused = widest(agreement)
    assert excused == permitted, (
        f"at min_agreement {agreement} the folds permit a same-side movement of "
        f"{permitted} and the floor excuses {excused}: ADR 0050's fourth point "
        "says these are the same number below unanimity, and must be rewritten"
    )


def test_at_unanimity_no_baseline_is_split_and_nothing_is_excused() -> None:
    stood = folds(Fraction(1))
    assert all(
        verdict.score.sample_min == verdict.score.sample_max for verdict in stood
    ), [(v.score.sample_min, v.score.sample_max) for v in stood]
    assert widest(Fraction(1)) == (0.0, 0.0)


def test_the_figures_adr_0050_prints() -> None:
    """`0.5` at 2/5 and below, `0.4` at 3/5, `0.2` at 4/5, nothing at 5/5."""
    measured = {str(a): widest(a)[1] for a in reachable_agreements(K)}
    assert measured == {"1/5": 0.5, "2/5": 0.5, "3/5": 0.4, "4/5": 0.2, "1": 0.0}, (
        f"{measured}: the figures in ADR 0050's fourth point must be rewritten"
    )
