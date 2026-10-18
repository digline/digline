"""What excuses a same-side movement, now that a floor has to be declared.

ADR 0050's fourth point, held against `compare()` itself — in two halves, and
the first half is #496 fixed. The file keeps the name it had when it pinned the
*defect*: what a silent floor concedes, which is now nothing.

For a binary check only: unanimity is a property of the outcomes, and only a
check whose samples are 0 and 1 can show the reference divided on them.

At K=5 and threshold 0.5, every baseline and every current run is enumerated as a
count of passes, fails and samples that could not be judged, and folded by
`combine_samples` at each `min_agreement` five samples can produce; a fold that
errors can be neither a baseline nor a run that is compared, and is dropped.
Every pair on one side of the threshold then goes through `compare()` at
tolerance 0, so a pair reported `unchanged` with a nonzero delta was excused by
the floor and by nothing else.

1. **Nothing is excused where nothing is declared.** The enumeration below used
   to excuse *everything* the folds permit: the band was the baseline's range of
   individual samples, which for divided binary votes is `[0, 1]`, and ADR
   0050's Context records exactly those figures (0.5, 0.5, 0.4, 0.2) as the
   defect they were. A check that declares no floor now has none, so the widest
   movement it excuses is zero at every `min_agreement`.
2. **A declared floor excuses a measured part of it.** With `noise_se = 1.0`
   the band is the baseline's mean plus or minus one standard error of that
   mean, and the widest movement inside it is measured here — so a figure the
   ADR prints regenerates from an artifact that runs in CI instead of being
   typed in by hand. At `2.0` the same bands excuse everything the folds permit:
   the width is a declaration a suite argues for, not a constant, and this is
   what arguing about it buys.
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

#: `min_agreement` -> (widest same-side movement the folds permit, widest the
#: floor excuses). Identical keys for all three tables: what the folds permit
#: does not depend on the floor, only on how they are folded.
UNDECLARED = {
    "1/5": (0.5, 0.0),
    "2/5": (0.5, 0.0),
    "3/5": (0.4, 0.0),
    "4/5": (0.2, 0.0),
    "1": (0.0, 0.0),
}
ONE_STANDARD_ERROR = {
    "1/5": (0.5, 0.3),
    "2/5": (0.5, 0.25),
    "3/5": (0.4, 0.2),
    "4/5": (0.2, 0.0),
    "1": (0.0, 0.0),
}
TWO_STANDARD_ERRORS = {
    "1/5": (0.5, 0.5),
    "2/5": (0.5, 0.5),
    "3/5": (0.4, 0.4),
    "4/5": (0.2, 0.2),
    "1": (0.0, 0.0),
}


def sample(score: float | None, noise_se: float | None = None) -> Verdict:
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
        noise_se=noise_se,
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


def folds(agreement: Fraction, noise_se: float | None = None) -> list[Verdict]:
    """Every fold of K binary samples that `agreement` lets stand."""
    floor = as_agreement(agreement, samples=K, field="min_agreement")
    out: list[Verdict] = []
    for passes in range(K + 1):
        for fails in range(K + 1 - passes):
            errored = K - passes - fails
            verdicts = [sample(1.0, noise_se)] * passes
            verdicts += [sample(0.0, noise_se)] * fails
            verdicts += [sample(None)] * errored
            folded = combine_samples(verdicts, min_agreement=floor)
            if folded.status != "error":
                out.append(folded)
    return out


def widest(agreement: Fraction, noise_se: float | None = None) -> tuple[float, float]:
    """The widest same-side movement, and the widest the floor excused."""
    stood = folds(agreement, noise_se)
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
def test_without_a_declaration_nothing_is_excused(agreement: Fraction) -> None:
    """#496's fix, held over every fold there is.

    The same enumeration that used to excuse every same-side movement — the
    ADR's Context prints 0.5 at 2/5 and below, 0.4 at 3/5, 0.2 at 4/5 — now
    excuses nothing, because a check that declares no floor has no floor and
    nothing but its tolerance can quiet a movement. (ADR 0050 decision 2)
    """
    permitted, excused = widest(agreement)
    assert (permitted, excused) == UNDECLARED[str(agreement)]
    assert excused == 0.0, (
        f"at min_agreement {agreement} an undeclared check still excused "
        f"{excused}: it declares no floor, so only tolerance can speak"
    )


@pytest.mark.parametrize("agreement", reachable_agreements(K), ids=str)
def test_one_standard_error_excuses_only_part_of_the_movement(
    agreement: Fraction,
) -> None:
    """The declared band, measured rather than asserted. Below unanimity every
    figure is *less* than what the folds permit: one standard error of the
    reference's mean bounds some of the movement and leaves the rest to be
    reported."""
    permitted, excused = widest(agreement, noise_se=1.0)
    assert (permitted, excused) == ONE_STANDARD_ERROR[str(agreement)]
    if permitted:
        assert excused < permitted, (
            f"at min_agreement {agreement} a one-standard-error band excused "
            f"{excused} of a permitted {permitted}: it should not concede all"
        )


@pytest.mark.parametrize("agreement", reachable_agreements(K), ids=str)
def test_two_standard_errors_excuse_everything_the_folds_permit(
    agreement: Fraction,
) -> None:
    """The same bands, twice as wide, and the floor concedes the lot — which is
    the argument for making the width a declaration. A suite that wants the old
    behaviour says so in its own file, where a reviewer can read it."""
    assert widest(agreement, noise_se=2.0) == TWO_STANDARD_ERRORS[str(agreement)]
    permitted, excused = widest(agreement, noise_se=2.0)
    assert excused == permitted


def test_at_unanimity_no_baseline_is_split_and_nothing_is_excused() -> None:
    stood = folds(Fraction(1))
    assert all(
        verdict.score.sample_min == verdict.score.sample_max for verdict in stood
    ), [(v.score.sample_min, v.score.sample_max) for v in stood]
    assert widest(Fraction(1)) == (0.0, 0.0)
    assert widest(Fraction(1), noise_se=1.0) == (0.0, 0.0)


def test_the_figures_adr_0050_prints() -> None:
    """Every number the ADR's fourth point may print, regenerated.

    The *undeclared* table is the defect its Context section describes — each
    figure there was the widest movement the silent floor excused. The other
    two are what this change puts in its place, so whichever the ADR keeps,
    this is where the arithmetic lives.
    """
    measured = {str(a): widest(a) for a in reachable_agreements(K)}
    one = {str(a): widest(a, noise_se=1.0) for a in reachable_agreements(K)}
    two = {str(a): widest(a, noise_se=2.0) for a in reachable_agreements(K)}
    assert measured == UNDECLARED, f"{measured}: {UNDECLARED} must be rewritten"
    assert one == ONE_STANDARD_ERROR, f"{one}: {ONE_STANDARD_ERROR} must be rewritten"
    assert two == TWO_STANDARD_ERRORS, f"{two}: {TWO_STANDARD_ERRORS} must be rewritten"
