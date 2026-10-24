"""A sample that never voted is said where a person looks. (#656, from #598)

A sampled verdict records how many samples the suite asked for
(`metadata["samples"]`) and how many were never judged
(`metadata["errored_samples"]`), and its floor is built from the judged ones
alone. Two places now say so when the two counts differ:

- **`promote`**, where a person signs: one line per check, after the line that
  names the baseline, on the model of `--accepting-pin`'s. It does not refuse:
  `min_agreement` is the suite author's declaration of how many samples are
  enough (#656, *Decided*);
- **the floor's sentence**, in `compare`'s reason and in the report and
  `explain` in both locales: the judged count beside the count asked for. When
  the two are equal the sentence is today's, word for word.

Nothing of it reaches the wire.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any, cast

from digline.core import (
    AssertionDelta,
    CaseResult,
    Run,
    Score,
    Verdict,
    combine_samples,
    compare,
)
from digline.core.compare import Noise
from digline.host import promotion_notes
from digline.report import headline, render_html
from digline.report.explain import explain_text, facts
from digline.wire import compare_json
from digline.wire.explain import explain_json

ROOT = Path(__file__).resolve().parents[1]
CREATED = "2026-01-01T00:00:00+00:00"
KEY = "promote.unjudged_samples"


def _sample(score: float | None, *, name: str = "rubric") -> Verdict:
    """One sample as an assertion returns it, before the fold: `None` is a
    sample that could not be judged. The check declares a floor of two."""
    if score is None:
        return Verdict(
            score=Score(name=name, score=None),
            threshold=0.5,
            status="error",
            reason="could not judge",
            assertion_id=f"id-{name}",
            floor_standard_errors=2,
        )
    return Verdict(
        score=Score(name=name, score=score),
        threshold=0.5,
        status="pass" if score >= 0.5 else "fail",
        reason="judged",
        assertion_id=f"id-{name}",
        floor_standard_errors=2,
    )


def _folded(*scores: float | None, name: str = "rubric") -> Verdict:
    return combine_samples(
        [_sample(score, name=name) for score in scores], min_agreement=0.0
    )


def _run(*verdicts: Verdict, case_id: str = "is-it-waterproof") -> Run:
    return Run(
        tenant="acme",
        environment="staging",
        suite="s",
        config_hash="h",
        created_at=CREATED,
        results=(CaseResult(case_id=case_id, verdicts=tuple(verdicts)),),
    )


#: Five asked for, one never voted: the floor rests on four.
ONE_MISSING = (0.7, 0.9, None, 0.8, 0.8)
ALL_JUDGED = (0.7, 0.9, 0.8, 0.8, 0.8)


def _delta(before: Sequence[float | None]) -> tuple[AssertionDelta, Run, Run]:
    # 0.6 against a reference near 0.8: outside the floor, and not a flip.
    now, reference = _run(_folded(0.6, 0.6, 0.6)), _run(_folded(*before))
    (delta,) = compare(now, reference).deltas
    return delta, now, reference


# --- the floor's sentence ---------------------------------------------------


def test_the_floor_names_the_count_asked_for_when_a_sample_never_voted() -> None:
    delta, _, _ = _delta(ONE_MISSING)
    assert delta.noise_samples == 4
    assert delta.noise_asked == 5
    assert "over 4 judged samples of the 5 asked for (" in delta.reason


def test_the_floor_reads_as_today_when_every_sample_voted() -> None:
    """The long form only where the counts differ: a sentence that always
    named the count asked for would say nothing on the ordinary case."""
    delta, _, _ = _delta(ALL_JUDGED)
    assert delta.noise_asked == 5
    assert "over 5 judged samples (" in delta.reason
    assert "asked for" not in delta.reason


def test_the_count_asked_for_is_the_record_s_not_the_judged_one() -> None:
    """Read from `metadata["samples"]`, which counts every sample the suite
    asked for. Counting the judged values instead gives four, the long form
    never appears, and the sentence is back to hiding the missing sample."""
    _, _, reference = _delta(ONE_MISSING)
    (verdict,) = reference.results[0].verdicts
    assert verdict.score.metadata["samples"] == 5
    assert len(verdict.score.samples) == 4


def test_noise_has_two_forms() -> None:
    def rendered(asked: int | None) -> str:
        return Noise(
            0.7, 0.9, 4, width=2, sd=0.08, judged=(0.7, 0.9, 0.8, 0.8), asked=asked
        ).rendered()

    assert "over 4 judged samples of the 5 asked for (" in rendered(5)
    assert "over 4 judged samples (" in rendered(4)
    assert "over 4 judged samples (" in rendered(None)


def test_the_report_names_both_counts_in_each_locale() -> None:
    delta, now, reference = _delta(ONE_MISSING)
    comparison = compare(now, reference)
    english = render_html(comparison, now, reference, locale="en", declared=None)
    italian = render_html(comparison, now, reference, locale="it", declared=None)
    assert delta.noise_min is not None
    assert "over 4 judged samples of the 5 asked for (" in english
    assert "su 4 campioni giudicati dei 5 chiesti (" in italian


def test_the_report_reads_as_today_when_every_sample_voted() -> None:
    _, now, reference = _delta(ALL_JUDGED)
    comparison = compare(now, reference)
    english = render_html(comparison, now, reference, locale="en", declared=None)
    italian = render_html(comparison, now, reference, locale="it", declared=None)
    assert "asked for" not in english and "over 5 judged samples (" in english
    assert "chiesti" not in italian and "su 5 campioni giudicati (" in italian


def test_explain_names_both_counts() -> None:
    _, now, reference = _delta(ONE_MISSING)
    reading = facts(now, compare(now, reference))
    said = "\n".join(explain_text(reading, locale="en"))
    assert "over 4 judged samples of the 5 asked for (" in said


def test_nothing_reaches_the_wire() -> None:
    _, now, reference = _delta(ONE_MISSING)
    comparison = compare(now, reference)
    head = headline(comparison, now, reference, locale="en", declared=None)
    full = compare_json(comparison, head, baseline=reference, full=True, run=now)
    (row,) = cast(list[dict[str, Any]], full["deltas"])
    assert not any("asked" in key for key in row)
    reading = explain_json(
        facts(now, comparison),
        scope="comparison",
        exit_code=0,
        run=now,
        baseline=reference,
    )
    for fact in cast(list[dict[str, Any]], reading["facts"]):
        assert not any("asked" in key for key in fact)


# --- promote ----------------------------------------------------------------


def test_promote_says_which_check_rests_on_fewer_samples() -> None:
    run = _run(_folded(*ONE_MISSING), _folded(*ALL_JUDGED, name="tone"))
    (line,) = promotion_notes(run)
    assert "is-it-waterproof" in line
    assert "rubric" in line
    assert "4 of 5 samples" in line


def test_promote_says_nothing_when_every_sample_voted() -> None:
    assert promotion_notes(_run(_folded(*ALL_JUDGED))) == ()


def test_promote_says_nothing_of_an_unsampled_check() -> None:
    once = Verdict(
        score=Score(name="rubric", score=0.8),
        threshold=0.5,
        status="pass",
        reason="judged",
        assertion_id="id-rubric",
    )
    assert promotion_notes(_run(once)) == ()


def test_the_promote_sentence_is_composed_in_host_and_never_in_store() -> None:
    """Where the sentence is made: the key of `report/text.py` is named in
    `host/promotion.py`, and nothing under `store/` names it. The store refuses
    and does not narrate; what a person reads at `promote` is the host's."""
    assert KEY in (ROOT / "src/digline/host/promotion.py").read_text(encoding="utf-8")
    under_store = [
        path.relative_to(ROOT).as_posix()
        for path in sorted((ROOT / "src/digline/store").rglob("*.py"))
        if KEY in path.read_text(encoding="utf-8")
    ]
    assert under_store == []
