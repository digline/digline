"""ADR 0050, phase 2 of #496: the floor compares means with means.

Where a check declares `floor_standard_errors`, the floor is the standard error
of the mean of the baseline's judged samples, `s / sqrt(K)`, times that width,
either side of the baseline's score. `Noise.covers` is the same test as before,
on a different interval.

There is no floor, and the tolerance alone decides, in five cases, each tested
on its own below: the check declares no width (the second decision); the
baseline's samples are binary (the third item, read off the samples as the
*Context* reads them, not off the check's declared kind); they are all equal,
so their dispersion is zero (the first decision, as amended); the verdict was
not sampled; or fewer than two of its samples were judged, where a standard
deviation is not defined. That last case is named by no ADR.

**This is the break.** A movement inside the range of the baseline's samples
was `unchanged`; where the check declares no floor it is now reported, and its
reason says the two facts that explain it — the movement is inside that range,
and the check declares no floor — without a date.

Aggregates keep the range: they are outside ADR 0050, and
`test_an_aggregate_whose_slices_tie_away_from_its_score_keeps_its_floor`
in `tests/test_noise_floor.py` holds that.
"""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from pathlib import Path
from statistics import fmean, stdev

import pytest

from digline.core import (
    CaseResult,
    Comparison,
    Run,
    Score,
    Verdict,
    compare,
)
from digline.core.compare import AssertionDelta
from digline.core.types import at_precision
from digline.report import render_html
from digline.report.explain import explain_text, facts
from digline.wire.compare import delta_json
from digline.wire.explain import fact_json

ROOT = Path(__file__).resolve().parents[1]
CREATED = "2026-01-01T00:00:00+00:00"
SPREAD = (0.7, 0.8, 0.9, 0.8, 0.8)


def make_run(verdicts: Sequence[Verdict]) -> Run:
    return Run(
        tenant="acme",
        environment="staging",
        suite="s",
        config_hash="h",
        created_at=CREATED,
        results=(CaseResult(case_id="c1", verdicts=tuple(verdicts)),),
    )


def sampled(
    values: Sequence[float],
    *,
    width: float | None = None,
    threshold: float = 0.0,
    means: bool = False,
) -> Verdict:
    """A folded verdict whose judged samples are `values`."""
    mean = at_precision(fmean(values))
    return Verdict(
        score=Score(
            name="check",
            score=mean,
            samples=tuple(values),
            sample_min=min(values),
            sample_max=max(values),
            sample_means=means,
        ),
        threshold=threshold,
        status="pass" if mean >= threshold else "fail",
        reason="folded",
        assertion_id="id-check",
        floor_standard_errors=width,
    )


def once(
    score: float, *, width: float | None = None, threshold: float = 0.0
) -> Verdict:
    return Verdict(
        score=Score(name="check", score=score),
        threshold=threshold,
        status="pass" if score >= threshold else "fail",
        reason="once",
        assertion_id="id-check",
        floor_standard_errors=width,
    )


def compared(now: Verdict, before: Verdict) -> AssertionDelta:
    (delta,) = compare(make_run([now]), make_run([before])).deltas
    return delta


def comparison(now: Verdict, before: Verdict) -> Comparison:
    return compare(make_run([now]), make_run([before]))


# --------------------------------------------------------------------------- #
# The floor: the dispersion of the mean, centred on the baseline's score
# --------------------------------------------------------------------------- #


def test_a_declared_width_gives_a_floor_from_the_standard_error_of_the_mean() -> None:
    se = stdev(SPREAD) / math.sqrt(len(SPREAD))
    delta = compared(sampled([0.75] * 5, width=2), sampled(SPREAD, width=2))
    assert delta.outcome == "unchanged"
    assert delta.within_noise
    assert delta.noise_min == pytest.approx(0.8 - 2 * se, abs=1e-6)
    assert delta.noise_max == pytest.approx(0.8 + 2 * se, abs=1e-6)
    assert delta.noise_samples == 5
    assert delta.noise_width == 2.0
    assert delta.noise_sd == pytest.approx(stdev(SPREAD), abs=1e-6)
    assert delta.noise_judged == SPREAD


def test_a_movement_inside_the_range_but_outside_the_mean_floor_is_reported() -> None:
    """0.72 is inside 0.7–0.9, the range today's floor excused, and outside
    0.8 ± 2 standard errors of the mean, which is 0.737–0.863."""
    delta = compared(sampled([0.72] * 5, width=2), sampled(SPREAD, width=2))
    assert delta.outcome == "regressed"
    assert not delta.within_noise


def test_the_floor_narrows_as_k_grows() -> None:
    """The point of ADR 0050: more samples, a steadier mean, a narrower floor.
    The range of the same values does not narrow at all."""
    few = (0.7, 0.9, 0.7, 0.9)
    many = few * 4
    narrow = compared(sampled([0.74] * 4, width=2), sampled(many, width=2))
    wide = compared(sampled([0.74] * 4, width=2), sampled(few, width=2))
    assert narrow.noise_min is not None and narrow.noise_max is not None
    assert wide.noise_min is not None and wide.noise_max is not None
    assert narrow.noise_max - narrow.noise_min < wide.noise_max - wide.noise_min
    assert wide.outcome == "unchanged" and wide.within_noise
    assert narrow.outcome == "regressed"


def test_the_floor_is_centred_on_the_baselines_score() -> None:
    delta = compared(sampled([0.75] * 5, width=1), sampled(SPREAD, width=1))
    assert delta.noise_width == 1.0
    assert delta.noise_min is not None and delta.noise_max is not None
    assert (delta.noise_min + delta.noise_max) / 2 == pytest.approx(0.8, abs=1e-6)


def test_the_width_in_force_is_the_judged_runs() -> None:
    """The dispersion is the baseline's (ADR 0006 §5), the width is the rule
    this run is held to: a width withdrawn takes the floor away with it."""
    withdrawn = compared(sampled([0.75] * 5), sampled(SPREAD, width=2))
    assert withdrawn.outcome == "regressed"
    added = compared(sampled([0.75] * 5, width=2), sampled(SPREAD))
    assert added.outcome == "unchanged" and added.within_noise


# --------------------------------------------------------------------------- #
# The five cases with no floor
# --------------------------------------------------------------------------- #


def test_no_floor_where_the_check_declares_no_width() -> None:
    delta = compared(sampled([0.75] * 5), sampled(SPREAD))
    assert delta.outcome == "regressed"
    assert (delta.noise_min, delta.noise_max, delta.noise_width) == (None, None, None)


def test_no_floor_where_the_baselines_samples_are_binary() -> None:
    """Read off the samples, as ADR 0050's *Context* reads them."""
    delta = compared(
        sampled([0.6] * 5, width=2, threshold=0.5),
        sampled((1.0, 1.0, 1.0, 1.0, 0.0), width=2, threshold=0.5),
    )
    assert delta.outcome == "regressed"
    assert delta.noise_min is None
    assert "the baseline's samples are all 0 or 1" in delta.reason


def test_samples_that_are_means_of_zeros_and_ones_are_not_binary() -> None:
    """`sample_means` is the exception the *Context* names: each sample is
    already a mean, so 0 and 1 there are not a binary check's verdicts."""
    delta = compared(
        sampled([0.6] * 5, width=2, means=True),
        sampled((1.0, 1.0, 1.0, 1.0, 0.0), width=2, means=True),
    )
    assert delta.noise_width == 2.0


def test_no_floor_where_the_baselines_samples_are_all_equal() -> None:
    delta = compared(sampled([0.75] * 5, width=2), sampled([0.8] * 5, width=2))
    assert delta.outcome == "regressed"
    assert delta.noise_min is None
    assert "the baseline's samples are all equal" in delta.reason


def test_no_floor_where_the_verdict_was_not_sampled() -> None:
    delta = compared(once(0.75, width=2), once(0.8, width=2))
    assert delta.outcome == "regressed"
    assert (delta.noise_min, delta.noise_width, delta.noise_sd) == (None, None, None)


def test_no_floor_where_fewer_than_two_samples_were_judged() -> None:
    delta = compared(sampled([0.75], width=2), sampled([0.8], width=2))
    assert delta.outcome == "regressed"
    assert delta.noise_min is None
    assert "fewer than two of the baseline's samples were judged" in delta.reason


# --------------------------------------------------------------------------- #
# The break explains itself
# --------------------------------------------------------------------------- #


def test_the_break_a_movement_the_range_excused_is_now_reported() -> None:
    """Today `unchanged`, within noise; from this change, a regression."""
    delta = compared(sampled([0.75] * 5), sampled(SPREAD))
    assert delta.outcome == "regressed"
    assert not delta.within_noise


def test_the_break_says_both_of_its_facts_and_no_date() -> None:
    delta = compared(sampled([0.75] * 5), sampled(SPREAD))
    assert "inside the range of the baseline's individual samples" in delta.reason
    assert "0.700000-0.900000 across 5 samples" in delta.reason
    assert "this check declares no noise floor" in delta.reason
    assert not re.search(r"\b0\.\d+\.\d+\b|\bbefore\b|\buntil\b", delta.reason)


def test_outside_the_range_with_no_floor_says_nothing_about_a_floor() -> None:
    delta = compared(sampled([0.6] * 5), sampled(SPREAD))
    assert delta.outcome == "regressed"
    assert "noise floor" not in delta.reason
    assert "range" not in delta.reason


# --------------------------------------------------------------------------- #
# What prints the floor prints what it was computed from (the fourth item)
# --------------------------------------------------------------------------- #

INPUTS = ("0.7, 0.8, 0.9, 0.8, 0.8", "0.070711", "5", "2")


def test_the_reason_prints_the_inputs() -> None:
    covered = compared(sampled([0.75] * 5, width=2), sampled(SPREAD, width=2))
    beyond = compared(sampled([0.72] * 5, width=2), sampled(SPREAD, width=2))
    for delta in (covered, beyond):
        assert "0.7, 0.8, 0.9, 0.8, 0.8" in delta.reason
        assert "standard deviation 0.070711" in delta.reason
        assert "5 judged samples" in delta.reason
        assert "2 standard errors of the mean" in delta.reason
    assert "inside the baseline's noise floor" in covered.reason
    assert "outside the baseline's noise floor" in beyond.reason


@pytest.mark.parametrize(
    ("locale", "words"),
    [
        ("en", ("standard errors of the mean", "judged samples")),
        ("it", ("errori standard della media", "campioni giudicati")),
    ],
)
def test_the_report_prints_the_inputs(locale: str, words: tuple[str, str]) -> None:
    for now in (0.75, 0.72):
        before = make_run([sampled(SPREAD, width=2)])
        current = make_run([sampled([now] * 5, width=2)])
        page = render_html(
            compare(current, before), current, before, locale=locale, declared=None
        )  # type: ignore[arg-type]
        for needle in (*words, "0.7, 0.8, 0.9, 0.8, 0.8", "0.070711"):
            assert needle in page, (locale, now, needle)


@pytest.mark.parametrize(
    ("locale", "words"),
    [
        ("en", ("standard errors of the mean", "judged samples")),
        ("it", ("errori standard della media", "campioni giudicati")),
    ],
)
def test_explain_prints_the_inputs(locale: str, words: tuple[str, str]) -> None:
    for now in (0.75, 0.72):
        before = make_run([sampled(SPREAD, width=2)])
        current = make_run([sampled([now] * 5, width=2)])
        reading = facts(current, compare(current, before))
        text = " ".join(explain_text(reading, locale=locale))  # type: ignore[arg-type]
        for needle in (*words, "0.7, 0.8, 0.9, 0.8, 0.8", "0.070711"):
            assert needle in text, (locale, now, needle)


def test_compare_json_carries_the_inputs() -> None:
    row = delta_json(compared(sampled([0.75] * 5, width=2), sampled(SPREAD, width=2)))
    assert row["noise_width"] == 2.0
    assert row["noise_sd"] == pytest.approx(stdev(SPREAD), abs=1e-6)
    assert row["noise_judged"] == list(SPREAD)
    assert row["noise_samples"] == 5


def test_compare_json_says_none_where_there_is_no_floor() -> None:
    row = delta_json(compared(sampled([0.75] * 5), sampled(SPREAD)))
    assert (row["noise_width"], row["noise_sd"], row["noise_judged"]) == (
        None,
        None,
        [],
    )


def test_explain_json_carries_the_inputs_and_whose_interval_it_is() -> None:
    before = make_run([sampled(SPREAD, width=2)])
    current = make_run([sampled([0.75] * 5, width=2)])
    (row,) = [
        fact_json(f)
        for f in facts(current, compare(current, before))
        if fact_json(f)["about"] == "check"
    ]
    assert row["noise_width"] == 2.0
    assert row["noise_judged"] == list(SPREAD)
    assert row["noise_source"] == "reference"


def test_a_runs_own_interval_cannot_be_read_as_a_floor() -> None:
    """Read alone, a failing check carries the interval *its own* samples
    spanned. It is not a floor, and the reading says whose it is."""
    alone = make_run([sampled((0.1, 0.2, 0.3), threshold=0.5)])
    (row,) = [fact_json(f) for f in facts(alone) if fact_json(f)["about"] == "check"]
    assert row["noise_source"] == "run"
    assert row["noise_width"] is None


# --------------------------------------------------------------------------- #
# docs/guide.md: the sentence the third item asks for
# --------------------------------------------------------------------------- #


def guide_section() -> str:
    text = (ROOT / "docs" / "guide.md").read_text(encoding="utf-8")
    start = text.index("### The second control: what the check measured about itself")
    end = text.index("\n## ", start)
    return " ".join(text[start:end].split())


def test_the_guide_says_a_binary_check_is_served_by_its_tolerance() -> None:
    """ADR 0050, the third item: the change that implements it lands with this
    sentence, and a test that fails when the page stops saying it."""
    assert "a binary check is served by its declared tolerance" in guide_section()


def test_the_guide_no_longer_says_nobody_chose_the_floor() -> None:
    section = guide_section()
    assert "Nobody chose it and nobody can widen it by hand" not in section
    assert "because the measured floor is now doing the other job" not in section
