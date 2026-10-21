"""For a binary check, no same-side movement is excused: the tolerance decides.

ADR 0050's fourth point, held against `compare()` itself. Its figures are the
evidence that justified the decision: the range floor excused, for a binary
check below unanimity, every same-side movement the configuration permits —
`0.5` at `min_agreement` 2/5 and below, `0.4` at 3/5, `0.2` at 4/5, nothing at
5/5 (ADR 0050, *Context*, the fourth consequence). They are held here as what
they still are, the widest same-side movement the folds permit. What has
changed is what `compare()` does with them: a binary check's samples are 0 or
1, ADR 0050's third item gives such a check to its tolerance, and so none of
those movements is excused any more, with or without a declared width.

At K=5 and threshold 0.5, every baseline and every current run is enumerated as
a count of passes, fails and samples that could not be judged, and folded by
`combine_samples` at each `min_agreement` five samples can produce; a fold that
errors can be neither a baseline nor a run that is compared, and is dropped.
Every pair on one side of the threshold then goes through `compare()` at
tolerance 0, so a pair reported `unchanged` with a nonzero delta would have
been excused by a floor and by nothing else. The file was
`test_noise_floor_concedes_every_same_side_move.py`, which held the coincidence
through the range floor.
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
#: The fourth point's figures, as ADR 0050's *Context* prints them.
FIGURES = {"1/5": 0.5, "2/5": 0.5, "3/5": 0.4, "4/5": 0.2, "1": 0.0}


def sample(score: float | None, width: float | None) -> Verdict:
    if score is None:
        return Verdict(
            score=Score(name="vote", score=None),
            threshold=THRESHOLD,
            tolerance=0.0,
            status="error",
            reason="could not be judged",
            assertion_id="vote",
            floor_standard_errors=width,
        )
    return Verdict(
        score=Score(name="vote", score=score),
        threshold=THRESHOLD,
        tolerance=0.0,
        status="pass" if score >= THRESHOLD else "fail",
        reason="a vote",
        assertion_id="vote",
        floor_standard_errors=width,
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


def folds(agreement: Fraction, width: float | None) -> list[Verdict]:
    """Every fold of K binary samples that `agreement` lets stand."""
    floor = as_agreement(agreement, samples=K, field="min_agreement")
    out: list[Verdict] = []
    for passes in range(K + 1):
        for fails in range(K + 1 - passes):
            errored = K - passes - fails
            verdicts = [sample(1.0, width)] * passes + [sample(0.0, width)] * fails
            verdicts += [sample(None, width)] * errored
            folded = combine_samples(verdicts, min_agreement=floor)
            if folded.status != "error":
                out.append(folded)
    return out


def widest(agreement: Fraction, width: float | None) -> tuple[float, float]:
    """The widest same-side movement the folds permit, and the widest excused."""
    stood = folds(agreement, width)
    permitted = excused = 0.0
    for before in stood:
        for now in stood:
            if before.status != now.status:
                continue
            delta = compare(run_of(now), run_of(before)).deltas[0]
            moved = abs(delta.delta or 0.0)
            permitted = max(permitted, moved)
            if delta.outcome == "unchanged" and moved > 0:
                excused = max(excused, moved)
    return permitted, excused


@pytest.mark.parametrize("width", [None, 2.0], ids=["no width", "width 2"])
@pytest.mark.parametrize("agreement", reachable_agreements(K), ids=str)
def test_no_same_side_movement_is_excused(
    agreement: Fraction, width: float | None
) -> None:
    permitted, excused = widest(agreement, width)
    assert excused == 0.0, (
        f"at min_agreement {agreement}, width {width}, compare() excused a "
        f"same-side movement of {excused} out of {permitted} permitted: a binary "
        "check is the tolerance's business (ADR 0050, the third item)"
    )


@pytest.mark.parametrize("width", [None, 2.0], ids=["no width", "width 2"])
def test_the_figures_adr_0050_prints_are_what_the_folds_permit(
    width: float | None,
) -> None:
    """`0.5` at 2/5 and below, `0.4` at 3/5, `0.2` at 4/5, nothing at 5/5: the
    movement the range floor excused in full, and the evidence for the change."""
    measured = {str(a): widest(a, width)[0] for a in reachable_agreements(K)}
    assert measured == FIGURES, (
        f"{measured}: the figures in ADR 0050's fourth point must be rewritten"
    )


def test_at_unanimity_no_baseline_is_split() -> None:
    stood = folds(Fraction(1), None)
    assert all(
        verdict.score.sample_min == verdict.score.sample_max for verdict in stood
    ), [(v.score.sample_min, v.score.sample_max) for v in stood]
    assert widest(Fraction(1), None) == (0.0, 0.0)
