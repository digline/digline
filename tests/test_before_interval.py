"""`before_interval`: the range the reference's own samples spanned. (#1)

On `compare --json` each delta carries it, and so does each check of
`explain --json`, under the same name and in the shape `diff` already writes an
interval in: `{"min", "max", "samples"}`, or `null` where the reference has no
samples for the check.

It is the scale of the movement, and it is **not** the noise floor. A flip
still carries no `noise_*` (ADR 0006 §6, amended for #1): the floor does not
reach a flip, nothing was judged against an interval, and the report prints
none. `before_interval` is computed on the wire from the reference's verdict,
so `AssertionDelta` and the report never see it, and it changes no verdict.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from typing import Any, cast

from digline.core import CaseResult, Run, Score, Verdict, combine_samples, compare
from digline.report import headline, render_html
from digline.report.explain import facts
from digline.wire import compare_json
from digline.wire.contract import _ADDED  # pyright: ignore[reportPrivateUsage]
from digline.wire.explain import explain_json

CREATED = "2026-01-01T00:00:00+00:00"


def _sample(score: float, *, assertion_id: str = "id-check") -> Verdict:
    return Verdict(
        score=Score(name="check", score=score),
        threshold=0.5,
        status="pass" if score >= 0.5 else "fail",
        reason=f"sample scored {score}",
        assertion_id=assertion_id,
    )


def _folded(*scores: float, assertion_id: str = "id-check") -> Verdict:
    return combine_samples(
        [_sample(value, assertion_id=assertion_id) for value in scores],
        min_agreement=0.0,
    )


def _run(*verdicts: Verdict, created: str = CREATED) -> Run:
    return Run(
        tenant="acme",
        environment="staging",
        suite="s",
        config_hash="h",
        created_at=created,
        results=(CaseResult(case_id="c1", verdicts=tuple(verdicts)),),
    )


def _deltas(now: Run, before: Run) -> list[dict[str, Any]]:
    comparison = compare(now, before)
    head = headline(comparison, now, before, locale="en", declared=None)
    document = compare_json(comparison, head, baseline=before, full=True, run=now)
    return cast(list[dict[str, Any]], document["deltas"])


def _checks(now: Run, before: Run | None) -> list[dict[str, Any]]:
    comparison = None if before is None else compare(now, before)
    document = explain_json(
        facts(now, comparison),
        scope="run" if before is None else "comparison",
        exit_code=0,
        run=now,
        baseline=before,
    )
    return [
        fact
        for fact in cast(Sequence[dict[str, Any]], document["facts"])
        if fact["about"] == "check"
    ]


#: A flip: the reference's mean is 0.8 over five samples that ran 0.0 to 1.0,
#: and this run's mean is 0.2. ADR 0006 §6's own example of a score that lands
#: *inside* the reference's samples while the outcome flips.
FLIP_BEFORE = (1.0, 0.0, 1.0, 1.0, 1.0)
FLIP_NOW = (0.0, 0.0, 1.0, 0.0, 0.0)


# --- compare --json ---------------------------------------------------------


def test_a_flip_carries_the_range_the_reference_samples_spanned() -> None:
    (row,) = _deltas(_run(_folded(*FLIP_NOW)), _run(_folded(*FLIP_BEFORE)))
    assert row["outcome"] == "regressed"
    assert row["before_interval"] == {"min": 0.0, "max": 1.0, "samples": 5}


def test_a_flip_still_carries_no_floor() -> None:
    """The scale beside the flip, and still no excuse: `noise_*` is what the
    movement was judged against, and a flip was judged against nothing."""
    (row,) = _deltas(_run(_folded(*FLIP_NOW)), _run(_folded(*FLIP_BEFORE)))
    assert row["within_noise"] is False
    assert (row["noise_min"], row["noise_max"], row["noise_samples"]) == (None, None, 0)


def test_a_movement_that_did_not_flip_carries_it_too() -> None:
    (row,) = _deltas(_run(_folded(0.6, 0.7, 0.6)), _run(_folded(0.8, 1.0, 0.9)))
    assert row["outcome"] == "regressed"
    assert row["before_interval"] == {"min": 0.8, "max": 1.0, "samples": 3}


def test_a_reference_that_took_one_sample_carries_null() -> None:
    """`null`, not a zero-width interval: one sample spans nothing, and
    `{"min": 0.9, "max": 0.9, "samples": 1}` would be a measurement nobody took."""
    (row,) = _deltas(_run(_sample(0.3)), _run(_sample(0.9)))
    assert row["outcome"] == "regressed"
    assert row["before_interval"] is None


def test_a_check_the_reference_does_not_hold_carries_null() -> None:
    other = _folded(0.9, 0.8, 1.0, assertion_id="id-other")
    rows = _deltas(_run(_folded(*FLIP_NOW), other), _run(other))
    (new,) = [r for r in rows if r["outcome"] == "new"]
    assert new["before_interval"] is None


# --- explain --json ---------------------------------------------------------


def test_explain_carries_the_interval_compare_carries() -> None:
    now, before = _run(_folded(*FLIP_NOW)), _run(_folded(*FLIP_BEFORE))
    (row,) = _deltas(now, before)
    (check,) = _checks(now, before)
    assert check["before_interval"] == row["before_interval"]
    assert check["before_interval"] == {"min": 0.0, "max": 1.0, "samples": 5}


def test_explain_of_an_unsampled_reference_carries_null() -> None:
    (check,) = _checks(_run(_sample(0.3)), _run(_sample(0.9)))
    assert check["before_interval"] is None


def test_explain_of_a_run_with_no_reference_carries_null() -> None:
    (check,) = _checks(_run(_folded(*FLIP_NOW)), None)
    assert check["before_interval"] is None


def test_twins_whose_reference_samples_differ_carry_null() -> None:
    """The same check twice on one case pairs by order in `compare()`, and a
    fact carries no order. Where the two reference verdicts spanned different
    ranges the reading cannot say which is which, so it says neither."""
    now = _run(_folded(*FLIP_NOW), _folded(*FLIP_NOW))
    before = _run(_folded(*FLIP_BEFORE), _folded(0.9, 1.0, 0.8, 1.0, 0.9))
    checks = _checks(now, before)
    assert len(checks) == 2
    assert [c["before_interval"] for c in checks] == [None, None]


def test_twins_whose_reference_samples_agree_carry_the_range() -> None:
    now = _run(_folded(*FLIP_NOW), _folded(*FLIP_NOW))
    before = _run(_folded(*FLIP_BEFORE), _folded(*FLIP_BEFORE))
    checks = _checks(now, before)
    assert [c["before_interval"] for c in checks] == [
        {"min": 0.0, "max": 1.0, "samples": 5}
    ] * 2


# --- the report -------------------------------------------------------------


def test_the_report_prints_no_interval_on_a_flip() -> None:
    """ADR 0006 §6 holds for the document: the interval the wire now carries
    beside a flip never reaches the page, because the report reads
    `AssertionDelta` and the delta of a flip has none."""
    now, before = _run(_folded(*FLIP_NOW)), _run(_folded(*FLIP_BEFORE))
    comparison = compare(now, before)
    (delta,) = comparison.deltas
    assert (delta.noise_min, delta.noise_max, delta.noise_samples) == (None, None, 0)
    for locale in ("en", "it"):
        page = render_html(comparison, now, before, locale=locale, declared=None)
        assert "across 5 samples" not in page
        assert "su 5 campioni" not in page


def test_the_report_prints_no_interval_on_a_flip_even_if_a_delta_carried_one() -> None:
    """The second guard, on its own. `render.py` words a flip before it reads
    any interval, so a flipped delta that did carry one, built here by hand
    because `compare()` never builds it, still reaches the page without it.
    With the test above, each of the two guards is pinned alone."""
    now, before = _run(_folded(*FLIP_NOW)), _run(_folded(*FLIP_BEFORE))
    comparison = compare(now, before)
    (delta,) = comparison.deltas
    carried = replace(delta, noise_min=0.0, noise_max=1.0, noise_samples=5)
    forged = replace(comparison, deltas=(carried,))
    for locale in ("en", "it"):
        page = render_html(forged, now, before, locale=locale, declared=None)
        assert "across 5 samples" not in page
        assert "su 5 campioni" not in page


# --- the contract -----------------------------------------------------------


def test_both_keys_are_added_keys_with_one_shape() -> None:
    added = {(entry.shape, entry.key): entry for entry in _ADDED}
    on_delta = added[("delta", "before_interval")]
    on_check = added[("fact.check", "before_interval")]
    assert on_delta.value == on_check.value
