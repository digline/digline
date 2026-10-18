"""ADR 0050: a noise floor is declared, and a mean is compared with a band
around a mean.

The defect, from #496: `within_noise` compared the current run's **mean** with
the baseline's range of **individual samples**. A binary check whose baseline
voted 0 and 1 had the band `[0, 1]`, so *every* same-side movement of a mean
was inside it — the floor excused everything the folds could produce, and
sampling the same check more often could neither widen nor narrow it.

What this file holds, in the ADR's own order:

1. the band is the baseline's mean ± the width the check declares, in
   standard errors of that mean — and it shrinks as the suite samples more;
2. the band is printed with its width in standard errors;
3. a check that declares no floor **has** no floor, decided by its `tolerance`
   alone whatever its baseline happened to record;
4. the reference's samples stay exactly as recorded, and everything that read
   a baseline before still reads it.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from digline.core import (
    Accuracy,
    AssertionDelta,
    CaseOutcome,
    CaseResult,
    Contains,
    Repeated,
    Run,
    Score,
    Verdict,
    combine_samples,
    compare,
    meets,
    with_noise_interval,
)
from digline.core.run import run_from_json, run_to_json
from digline.report import render_html
from digline.report.text import Locale

CREATED = "2026-10-16T09:00:00+00:00"
THRESHOLD = 0.5

#: #496's own shapes: a baseline that voted 4/5, and a run that voted 3/5 —
#: both passing at a threshold of 0.5, so nothing here is a flip.
WAS = (1.0, 1.0, 1.0, 0.0, 1.0)
NOW = (1.0, 1.0, 0.0, 1.0, 0.0)

#: The declared width in `WAS`'s own terms: its sum of squared deviations from
#: its own mean of 0.8 is 0.8, so one standard error of that mean is
#: sqrt(0.8 / 5^2) = 0.178885.
SE_ONE = 0.178885

#: What one standard error of `WAS`'s mean bounds: [0.8 - 0.178885,
#: 0.8 + 0.178885].
BAND_ONE = (0.621115, 0.978885)


def vote(
    score: float, *, threshold: float = THRESHOLD, noise_se: float | None = None
) -> Verdict:
    return Verdict(
        score=Score(name="vote", score=score),
        threshold=threshold,
        noise_se=noise_se,
        status="pass" if meets(score, threshold) else "fail",
        reason=f"voted {score}",
        assertion_id="id-vote",
    )


def folded(scores: tuple[float, ...], *, noise_se: float | None = None) -> Verdict:
    """The samples folded the way `Suite.samples` folds them, carrying the
    declaration the assertion made."""
    return combine_samples(
        [vote(value, noise_se=noise_se) for value in scores], min_agreement=0.0
    )


def run_of(verdict: Verdict) -> Run:
    return Run(
        tenant="acme",
        environment="staging",
        suite="s",
        config_hash="h",
        created_at=CREATED,
        results=(CaseResult(case_id="c1", verdicts=(verdict,)),),
    )


def compare_pair(now: Verdict, before: Verdict) -> AssertionDelta:
    deltas = compare(run_of(now), run_of(before)).deltas
    assert len(deltas) == 1
    return deltas[0]


# -- #496, reproduced ------------------------------------------------------- #


def test_the_same_side_move_496_reported_as_noise_is_a_regression() -> None:
    """The issue, held against `compare()` itself.

    4/5 → 3/5 at threshold 0.5 and tolerance 0: both runs pass, so this is not
    a flip and nothing but a floor could quiet it. The floor that used to
    answer was the baseline's `[0.0, 1.0]` — every value a binary sample can
    take — which excused the drop with `within_noise: true` and exit 0.
    """
    delta = compare_pair(folded(NOW), folded(WAS))
    assert delta.outcome == "regressed"
    assert not delta.within_noise
    assert delta.noise_min is None and delta.noise_max is None
    assert "individual samples" not in delta.reason
    assert "noise" not in delta.reason


def test_the_same_side_move_against_a_declared_floor_is_still_a_regression() -> None:
    """And the same movement, once the suite says how much noise it accepts:
    one standard error of a 4/5 baseline's mean is 0.178885, so its band is
    [0.621115, 0.978885] and a mean of 0.6 is outside it."""
    delta = compare_pair(folded(NOW, noise_se=1.0), folded(WAS, noise_se=1.0))
    assert delta.outcome == "regressed"
    assert not delta.within_noise
    assert delta.delta == -0.2
    assert round(delta.noise_min or 0.0, 6) == BAND_ONE[0]
    assert round(delta.noise_max or 0.0, 6) == BAND_ONE[1]
    assert "outside the declared noise floor" in delta.reason


# -- 1. the band, and how it is sized --------------------------------------- #


def test_the_band_is_the_baselines_mean_plus_or_minus_the_declared_width() -> None:
    delta = compare_pair(folded(NOW, noise_se=1.0), folded(WAS, noise_se=1.0))
    mean, count = 0.8, len(WAS)
    # The width the ADR prescribes, written out: the population spread of the
    # reference's own samples over the square root of how many there were.
    variance = sum((value - mean) ** 2 for value in WAS) / count
    expected = (variance / count) ** 0.5
    assert expected == pytest.approx(SE_ONE, abs=1e-6)
    assert (delta.noise_se, delta.noise_samples) == (1.0, 5)
    assert delta.noise_min == pytest.approx(mean - expected, abs=1e-6)
    assert delta.noise_max == pytest.approx(mean + expected, abs=1e-6)


def test_the_band_narrows_as_the_suite_samples_more() -> None:
    """The whole point of measuring in standard errors rather than in samples:
    the same wobble, observed twenty times, excuses less than observed five."""
    five = compare_pair(folded(NOW, noise_se=1.0), folded(WAS, noise_se=1.0))
    twenty = compare_pair(folded(NOW * 4, noise_se=1.0), folded(WAS * 4, noise_se=1.0))

    def band_width(delta: AssertionDelta) -> float:
        assert delta.noise_min is not None and delta.noise_max is not None
        return delta.noise_max - delta.noise_min

    assert band_width(twenty) < band_width(five)
    # The mean is the same measurement at both sample counts.
    assert (five.delta, twenty.delta) == (-0.2, -0.2)


def test_an_unanimous_baseline_declares_a_band_of_no_width() -> None:
    """Zero spread is a measurement too: a check that voted 5/5 shows no
    variability, so one standard error of its mean is nothing, and every later
    change of mind is still a finding."""
    unanimous = (1.0,) * 5
    delta = compare_pair(
        folded((1.0, 1.0, 1.0, 0.0, 1.0), noise_se=1.0), folded(unanimous, noise_se=1.0)
    )
    assert delta.outcome == "regressed"
    assert not delta.within_noise
    assert (delta.noise_min, delta.noise_max) == (1.0, 1.0)


def test_two_standard_errors_excuse_more_than_one() -> None:
    """The declaration is a number the suite argues for, not a constant: at two
    standard errors the same 0.6 mean is inside the band, and the reason says
    which width spoke."""
    delta = compare_pair(folded(NOW, noise_se=2.0), folded(WAS, noise_se=2.0))
    assert delta.outcome == "unchanged"
    assert delta.within_noise
    assert delta.noise_se == 2.0
    assert "2 standard errors of the mean" in delta.reason


def test_a_negative_width_is_refused() -> None:
    with pytest.raises(ValueError, match="negative"):
        vote(1.0, noise_se=-1.0)


# -- 2. the band is printed with its width ---------------------------------- #


def test_the_reason_prints_the_band_with_its_width_in_standard_errors() -> None:
    delta = compare_pair(folded(NOW, noise_se=1.0), folded(WAS, noise_se=1.0))
    assert (
        "0.621115-0.978885 across 5 samples (1 standard error of the mean)"
        in delta.reason
    )


@pytest.mark.parametrize(
    ("locale", "rendered"),
    [
        ("en", "0.621115–0.978885 across 5 samples, 1 standard error of the mean"),
        ("it", "0.621115–0.978885 su 5 campioni, 1 errore standard della media"),
    ],
)
def test_the_report_prints_the_width_beside_the_band(
    locale: Locale, rendered: str
) -> None:
    run = run_of(folded(NOW, noise_se=1.0))
    document = render_html(
        compare(run_of(folded(NOW, noise_se=1.0)), run_of(folded(WAS, noise_se=1.0))),
        run,
        run,
        locale=locale,
        declared=None,
    )
    assert rendered in document


# -- 3. no declaration, no floor -------------------------------------------- #


def test_the_declaration_is_the_only_thing_that_gives_a_check_a_floor() -> None:
    delta = compare_pair(folded(NOW), folded(WAS))
    assert delta.outcome == "regressed"
    assert not delta.within_noise
    assert delta.noise_se is None


def test_a_wider_declaration_does_not_leak_from_one_check_to_another() -> None:
    """Each check carries its own. Two checks in one case, one of them
    declared: only the declared one gets a band."""
    declared = replace(folded((1.0, 0.0, 1.0), noise_se=3.0), assertion_id="id-a")
    quiet = replace(folded((1.0, 0.0, 1.0)), assertion_id="id-b")
    run = Run(
        tenant="acme",
        environment="staging",
        suite="s",
        config_hash="h",
        created_at=CREATED,
        results=(CaseResult(case_id="c1", verdicts=(declared, quiet)),),
    )
    by_check = {
        d.baseline.assertion_id: d
        for d in compare(run, run).deltas
        if d.baseline is not None
    }
    assert by_check["id-a"].noise_se == 3.0
    assert by_check["id-a"].noise_min is not None
    assert by_check["id-b"].noise_se is None
    assert by_check["id-b"].noise_min is None


# -- 4. the samples stay as recorded ---------------------------------------- #


def test_the_declaration_round_trips_through_the_document() -> None:
    declared = folded(WAS, noise_se=1.0)
    back = run_from_json(run_to_json(run_of(declared))).results[0].verdicts[0]
    assert back.noise_se == 1.0
    assert back.score.samples == WAS


def test_a_suite_that_declares_no_floor_writes_no_noise_se_key() -> None:
    """Absent, never `null`: a run of an undeclared suite is the byte-identical
    file it was before this ADR."""
    document = run_to_json(run_of(folded(WAS)))
    assert "noise_se" not in document


def test_an_aggregate_keeps_the_band_it_had() -> None:
    """Run-level aggregates are out of ADR 0050's scope: their per-sample values
    are already means of a whole run, so the range band stays."""

    def aggregate_only(wobble: tuple[float, ...]) -> Run:
        """One aggregate over three cases, where case 1's own samples disagree
        — so the aggregate records per-sample values the way ADR 0006 §7 says
        it does, rather than three copies of one number."""
        verdicts = (folded((1.0, 1.0, 1.0)), folded(wobble), folded((1.0, 1.0, 1.0)))
        return Run(
            tenant="acme",
            environment="staging",
            suite="s",
            config_hash="h",
            created_at=CREATED,
            aggregate=(
                with_noise_interval(
                    Accuracy(over="vote", threshold="1/2", tolerance=0.0),
                    tuple(
                        CaseOutcome(case_id=f"c{n}", label="positive", verdict=verdict)
                        for n, verdict in enumerate(verdicts)
                    ),
                ),
            ),
        )

    # The baseline passes 3/3 with per-sample values (1, 0.666667, 1) — a range
    # band of [0.666667, 1.0] — and this run fails the wobbling case outright:
    # accuracy falls to 0.666667, inside that band.
    delta = compare(
        aggregate_only((0.0, 0.0, 0.0)),
        aggregate_only((1.0, 0.0, 1.0)),
    ).deltas[0]
    assert delta.scope == "run"
    assert delta.noise_se is None
    assert delta.noise_min == pytest.approx(0.666667, abs=1e-6)
    assert delta.noise_max == pytest.approx(1.0, abs=1e-6)
    assert delta.outcome == "unchanged"
    assert delta.within_noise
    assert "range of the baseline's individual samples" in delta.reason


def test_repeated_carries_the_declaration_of_what_it_wraps() -> None:
    """The declaration travels the way the threshold does: a wrapper has no
    opinion of its own, so it copies what it wraps."""
    inner = Contains(needle="x", noise_se=2.0)
    repeated = Repeated(inner=inner, samples=3, min_agreement="2/3")
    assert repeated.noise_se == 2.0
    assert repeated.threshold == inner.threshold
    # Wrapping changes identity — that is what makes the first comparison after
    # wrapping loud — but the floor it declares is the same floor.
    assert repeated.identity != inner.identity
    quiet = Repeated(inner=Contains(needle="x"), samples=3, min_agreement="2/3")
    assert quiet.noise_se is None


def test_the_declaration_is_outside_identity() -> None:
    """A widened floor is a moved rule, not a different check: the verdicts
    still pair, so `compare()` can report the movement instead of a `new` and
    a `missing`."""
    assert Contains(needle="x", noise_se=1.0).identity == Contains(needle="x").identity
    assert "noise_se" not in Contains(needle="x", noise_se=1.0).identity
