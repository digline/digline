"""Verdicts about the run: the figure that gates a release.

The centrepiece is `test_the_aggregate_is_steady_where_the_cases_are_not`, which
reproduces the measurement that put this feature at the top of the list: four
runs of one unchanged prompt agreed with the human mark on 14, 14, 15, 15 of 21
cases while individual cases moved by three votes.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from digline.core import (
    F1,
    Accuracy,
    CaseOutcome,
    Contains,
    Precision,
    Recall,
    Run,
    Score,
    Verdict,
    compare,
    redact,
    run_from_json,
    run_to_json,
)
from digline.report import headline, render_html, summary_lines
from digline.run import Case, Response, Suite, execute

BASE_AT = "2026-01-01T00:00:00+00:00"
LATER_AT = "2026-01-02T00:00:00+00:00"

CASES = [f"case-{i:02d}" for i in range(21)]
#: Eight marked worth reading, thirteen not — the shape the brief had.
LABELS = {c: ("positive" if i < 8 else "negative") for i, c in enumerate(CASES)}

AGREES = "agrees_with_mark"


def outcome(case_id: str, label: str, *, agreed: bool | None) -> CaseOutcome:
    if agreed is None:
        return CaseOutcome(case_id, label, None)  # type: ignore[arg-type]
    return CaseOutcome(
        case_id,
        label,  # type: ignore[arg-type]
        Verdict(
            score=Score(name=AGREES, score=1.0 if agreed else 0.0),
            threshold=1.0,
            status="pass" if agreed else "fail",
            reason="judged",
            assertion_id=f"id-{AGREES}",
        ),
    )


def errored(case_id: str, label: str) -> CaseOutcome:
    return CaseOutcome(
        case_id,
        label,  # type: ignore[arg-type]
        Verdict(
            score=Score(name=AGREES, score=None),
            threshold=1.0,
            status="error",
            reason="could not judge",
            assertion_id=f"id-{AGREES}",
        ),
    )


# --------------------------------------------------------------------------- #
# The confusion matrix
# --------------------------------------------------------------------------- #


def test_the_four_corners_of_the_matrix() -> None:
    """A `pass` on the named check means the system agreed with the mark, so a
    marked-positive case that passes was correctly kept and a marked-negative
    one that passes was correctly rejected."""
    outcomes = [
        outcome("tp", "positive", agreed=True),
        outcome("fn", "positive", agreed=False),
        outcome("tn", "negative", agreed=True),
        outcome("fp", "negative", agreed=False),
    ]
    m = Accuracy(over=AGREES, threshold=0.1, tolerance=0.0)(outcomes).score.metadata
    assert m["true_positive"] == 1
    assert m["false_negative"] == 1
    assert m["true_negative"] == 1
    assert m["false_positive"] == 1
    assert m["considered"] == 4


def test_the_three_formulas() -> None:
    outcomes = [
        *[outcome(f"tp{i}", "positive", agreed=True) for i in range(6)],
        *[outcome(f"fn{i}", "positive", agreed=False) for i in range(2)],
        *[outcome(f"tn{i}", "negative", agreed=True) for i in range(9)],
        *[outcome(f"fp{i}", "negative", agreed=False) for i in range(3)],
    ]
    assert Precision(over=AGREES, threshold=0.1, tolerance=0.0)(
        outcomes
    ).score.score == pytest.approx(6 / 9)
    assert Recall(over=AGREES, threshold=0.1, tolerance=0.0)(
        outcomes
    ).score.score == pytest.approx(6 / 8)
    assert Accuracy(over=AGREES, threshold=0.1, tolerance=0.0)(
        outcomes
    ).score.score == pytest.approx(15 / 20)


def test_an_empty_denominator_is_an_error_not_a_perfect_score() -> None:
    """The system kept nothing, so precision is undefined. `1.0` would be the
    most dangerous possible answer."""
    outcomes = [outcome("a", "negative", agreed=True)]
    v = Precision(over=AGREES, threshold=0.65, tolerance=0.05)(outcomes)
    assert v.status == "error"
    assert v.score.score is None
    assert "empty denominator" in v.reason


def test_the_two_exclusions_are_counted_and_named_beside_the_number() -> None:
    """`suspended_excluded` is the one figure in this product that improves by
    doing less work, so it never appears on its own."""
    outcomes = [
        outcome("kept", "positive", agreed=True),
        outcome("parked", "positive", agreed=None),
        errored("broken", "negative"),
    ]
    v = Accuracy(over=AGREES, threshold=0.5, tolerance=0.0)(outcomes)
    assert v.score.metadata["suspended_excluded"] == 1
    assert v.score.metadata["errored_excluded"] == 1
    assert v.score.metadata["considered"] == 1
    assert "1 suspended" in v.reason and "1 could not be judged" in v.reason


def test_the_counts_are_integers_so_they_cross_a_boundary() -> None:
    outcomes = [outcome("a", "positive", agreed=True)]
    metadata = Precision(over=AGREES, threshold=0.5, tolerance=0.0)(
        outcomes
    ).score.metadata
    assert all(isinstance(v, int) for v in metadata.values())


# --------------------------------------------------------------------------- #
# The measurement that made this the top of the list
# --------------------------------------------------------------------------- #


def a_suite(*, threshold: float = 0.65, tolerance: float = 0.05) -> Suite:
    return Suite(
        tenant="brief",
        environment="dev",
        name="daily",
        assertions=[Contains(needle="MATCH", name=AGREES)],
        run_assertions=[
            Accuracy(over=AGREES, threshold=threshold, tolerance=tolerance)
        ],
        cases=[
            Case(id=cid, label=LABELS[cid])  # type: ignore[arg-type]
            for cid in CASES
        ],
    )


def run_agreeing(agreeing: set[str], when: str, suite: Suite | None = None) -> Run:
    suite = suite or a_suite()

    def target(case: Case) -> Response:
        return Response(
            output="MATCH" if case.id in agreeing else "MISS", cost_usd=0.001
        )

    return execute(suite, target, created_at=when)


def test_the_aggregate_is_steady_where_the_cases_are_not() -> None:
    """The measured motivation, reproduced.

    Four runs of one unchanged prompt: 14, 14, 15, 15 of 21 agreeing, with a
    *different* set of cases each time. Per-case, that is a stream of
    regressions. On the aggregate, 14/21 to 15/21 is 0.0476 — inside a tolerance
    of one case — so the gate never turns red on noise.
    """
    baseline = run_agreeing(set(CASES[:14]), BASE_AT)

    # Same count, two cases swapped: the wobble the brief measured.
    swapped = run_agreeing(set(CASES[2:16]), LATER_AT)
    # One more agreeing, and again a different subset.
    fifteen = run_agreeing(set(CASES[1:16]), LATER_AT)
    fifteen_other = run_agreeing(set(CASES[:13]) | {CASES[17], CASES[18]}, LATER_AT)

    for later in (swapped, fifteen, fifteen_other):
        result = compare(later, baseline)
        aggregates = [d for d in result.deltas if d.scope == "run"]
        assert len(aggregates) == 1
        assert aggregates[0].outcome == "unchanged", aggregates[0].reason

        # And the per-case view *would* have gone red, which is the point.
        per_case = [d for d in result.deltas if d.scope == "case"]
        assert any(d.outcome == "regressed" for d in per_case)


def test_the_gate_stays_green_across_the_measured_range() -> None:
    """14/21 = 0.667 and 15/21 = 0.714, both above a threshold of 0.65."""
    for agreeing in (14, 15):
        run = run_agreeing(set(CASES[:agreeing]), BASE_AT)
        assert run.aggregate[0].status == "pass"
        assert run.aggregate[0].score.score == pytest.approx(agreeing / 21)


def test_a_real_drop_still_registers() -> None:
    """The tolerance covers one case, not four: the gate has to still work."""
    baseline = run_agreeing(set(CASES[:15]), BASE_AT)
    worse = run_agreeing(set(CASES[:11]), LATER_AT)
    result = compare(worse, baseline)
    aggregate = next(d for d in result.deltas if d.scope == "run")
    assert aggregate.outcome == "regressed"
    assert worse.aggregate[0].status == "fail"  # 11/21 = 0.524, under 0.65


# --------------------------------------------------------------------------- #
# What the suite refuses to declare
# --------------------------------------------------------------------------- #


def test_an_aggregate_over_a_name_nobody_declared_is_refused() -> None:
    with pytest.raises(ValueError, match="which no assertion"):
        Suite(
            tenant="acme",
            environment="dev",
            name="qa",
            assertions=[Contains(needle="x", name="agrees")],
            run_assertions=[Precision(over="agree", threshold=0.6, tolerance=0.05)],
            cases=[Case(id="one", label="positive")],
        )


def test_an_aggregate_over_an_ambiguous_name_is_refused() -> None:
    """Two `contains` in one suite is the ordinary case — it is why `compare()`
    pairs on identity rather than on names — so an aggregate that cannot choose
    between them must say so instead of taking the first."""
    with pytest.raises(ValueError, match="2 assertions .* share"):
        Suite(
            tenant="acme",
            environment="dev",
            name="qa",
            assertions=[Contains(needle="a"), Contains(needle="b")],
            run_assertions=[Precision(over="contains", threshold=0.6, tolerance=0.05)],
            cases=[Case(id="one", label="positive")],
        )


def test_a_confusion_matrix_demands_a_label_on_every_case() -> None:
    with pytest.raises(ValueError, match="needs a label. Missing on: two"):
        Suite(
            tenant="acme",
            environment="dev",
            name="qa",
            assertions=[Contains(needle="x", name=AGREES)],
            run_assertions=[Precision(over=AGREES, threshold=0.6, tolerance=0.05)],
            cases=[Case(id="one", label="positive"), Case(id="two")],
        )


def test_labels_are_not_demanded_without_an_aggregate_that_counts_them() -> None:
    suite = Suite(
        tenant="acme",
        environment="dev",
        name="qa",
        assertions=[Contains(needle="x")],
        cases=[Case(id="one")],
    )
    assert suite.run_assertions == ()


def test_the_aggregates_are_part_of_the_configuration() -> None:
    """Changing the bar is comparable but not promotable, as everywhere else."""
    lenient = a_suite(threshold=0.60).config_hash()
    strict = a_suite(threshold=0.80).config_hash()
    assert lenient != strict


def test_precision_and_recall_are_different_suites() -> None:
    """Three dataclasses, three identities: swapping the metric is not a
    threshold change, it is another question."""
    identities = {
        Precision(over=AGREES, threshold=0.6, tolerance=0.05).identity,
        Recall(over=AGREES, threshold=0.6, tolerance=0.05).identity,
        Accuracy(over=AGREES, threshold=0.6, tolerance=0.05).identity,
    }
    assert len(identities) == 3


# --------------------------------------------------------------------------- #
# Through the run: storage, comparison, redaction, report
# --------------------------------------------------------------------------- #


def test_the_aggregate_survives_the_round_trip() -> None:
    run = run_agreeing(set(CASES[:14]), BASE_AT)
    restored = run_from_json(run_to_json(run))
    assert len(restored.aggregate) == 1
    assert restored.aggregate[0].score.score == pytest.approx(14 / 21)
    assert restored.aggregate[0].score.metadata["considered"] == 21


def test_the_number_travels_and_the_sentence_does_not() -> None:
    """World 3 to world 2: the software house sees precision fall without
    seeing a case."""
    run = run_agreeing(set(CASES[:14]), BASE_AT)
    hidden = redact(run)
    aggregate = hidden.aggregate[0]

    assert aggregate.score.score == pytest.approx(14 / 21)
    assert aggregate.score.metadata["true_positive"] == 8
    document = run_to_json(run, redacted=True)
    assert "accuracy 0.666667" not in document  # the reason is gone
    assert '"true_positive": 8' in document  # the counts are not


def test_a_redacted_run_may_not_keep_an_aggregate_reason() -> None:
    """Verified, not believed — the same treatment as every other reason."""
    run = run_agreeing(set(CASES[:14]), BASE_AT)
    with pytest.raises(ValueError, match="aggregate verdict"):
        Run(
            tenant=run.tenant,
            environment=run.environment,
            suite=run.suite,
            config_hash=run.config_hash,
            created_at=run.created_at,
            aggregate=run.aggregate,
            redacted=True,
        )


def test_the_report_puts_the_aggregate_above_the_cases() -> None:
    baseline = run_agreeing(set(CASES[:14]), BASE_AT)
    later = run_agreeing(set(CASES[:11]), LATER_AT)
    document = render_html(compare(later, baseline), later, baseline, locale="en")

    assert document.index("Overall") < document.index("What got worse")
    assert "accuracy" in document
    # The exclusions travel with the ratio, never under it.
    assert "21 counted · 0 suspended · 0 not judged" in document


def test_an_aggregate_regression_is_named_in_the_summary() -> None:
    baseline = run_agreeing(set(CASES[:15]), BASE_AT)
    later = run_agreeing(set(CASES[:11]), LATER_AT)
    comparison = compare(later, baseline)

    lines = summary_lines(comparison, later, baseline, locale="en")
    aggregate_line = next(line for line in lines if "accuracy" in line)
    # A run-level verdict belongs to no case, so it says so.
    assert aggregate_line.startswith("whole run · accuracy · ")

    assert headline(comparison, later, baseline, locale="en").worse is True


def test_a_suspended_case_leaves_the_denominator_and_says_so(tmp_path: Path) -> None:
    """The gaming risk, made visible rather than forbidden."""
    suite = Suite(
        tenant="brief",
        environment="dev",
        name="daily",
        assertions=[Contains(needle="MATCH", name=AGREES)],
        run_assertions=[Accuracy(over=AGREES, threshold=0.5, tolerance=0.05)],
        cases=[
            Case(id="kept", label="positive"),
            Case(id="parked", label="negative", suspended="ticket 412"),
        ],
    )
    run = run_agreeing({"kept"}, BASE_AT, suite)
    aggregate = run.aggregate[0]

    assert aggregate.score.score == pytest.approx(1.0)  # 1 of 1 counted
    assert aggregate.score.metadata["suspended_excluded"] == 1
    assert "1 counted" in aggregate.reason and "1 suspended" in aggregate.reason


# --------------------------------------------------------------------------- #
# "k out of n" (friction 11)
# --------------------------------------------------------------------------- #


def test_a_tolerance_can_say_how_many_cases_it_means() -> None:
    """`"1/21"` says "one case out of twenty-one"; `0.047619` says nothing."""
    written = Accuracy(over=AGREES, threshold=0.65, tolerance="1/21")
    assert written.tolerance == pytest.approx(1 / 21)
    assert (
        written.identity
        == Accuracy(over=AGREES, threshold=0.65, tolerance=1 / 21).identity
    )


def test_one_case_of_tolerance_covers_the_measured_wobble() -> None:
    """14/21 to 15/21 is 0.0476, so "one case" is exactly the right width — and
    saying it that way is why the next reader will know it was chosen."""
    suite = Suite(
        tenant="brief",
        environment="dev",
        name="daily",
        assertions=[Contains(needle="MATCH", name=AGREES)],
        run_assertions=[Accuracy(over=AGREES, threshold=0.65, tolerance="1/21")],
        cases=[Case(id=cid, label=LABELS[cid]) for cid in CASES],  # type: ignore[arg-type]
    )
    baseline = run_agreeing(set(CASES[:14]), BASE_AT, suite)
    later = run_agreeing(set(CASES[1:16]), LATER_AT, suite)
    aggregate = next(d for d in compare(later, baseline).deltas if d.scope == "run")
    assert aggregate.outcome == "unchanged"


# --------------------------------------------------------------------------- #
# F1
# --------------------------------------------------------------------------- #


def outcomes_with(*, tp: int, fp: int, tn: int, fn: int) -> list[CaseOutcome]:
    """A matrix built to order, so a metric can be checked against arithmetic
    rather than against another metric."""
    made: list[CaseOutcome] = []
    for kind, count in (("tp", tp), ("fp", fp), ("tn", tn), ("fn", fn)):
        for i in range(count):
            label = "positive" if kind in ("tp", "fn") else "negative"
            made.append(outcome(f"{kind}-{i}", label, agreed=kind in ("tp", "tn")))
    return made


def test_f1_is_the_harmonic_mean_of_precision_and_recall() -> None:
    # P = 6/8 = 0.75, R = 6/9 = 0.666…, so F1 = 2PR/(P+R) = 0.705882…
    cases = outcomes_with(tp=6, fp=2, tn=5, fn=3)
    metric = F1(over=AGREES, threshold=0.6, tolerance=0.05)
    verdict = metric(cases)
    assert verdict.status == "pass"
    assert verdict.score.score == pytest.approx(12 / 17)

    p = Precision(over=AGREES, threshold=0.6, tolerance=0.05)(cases).score.score
    r = Recall(over=AGREES, threshold=0.6, tolerance=0.05)(cases).score.score
    assert p is not None and r is not None
    assert verdict.score.score == pytest.approx(2 * p * r / (p + r))


def test_f1_fails_below_its_threshold() -> None:
    verdict = F1(over=AGREES, threshold=0.9, tolerance=0.05)(
        outcomes_with(tp=6, fp=2, tn=5, fn=3)
    )
    assert verdict.status == "fail"
    assert "12/17" in verdict.reason


def test_f1_goes_down_when_the_trade_was_a_bad_one() -> None:
    """Why it sits next to the other three: a stricter prompt that keeps fewer
    items raises precision and lowers recall, and each of those numbers alone
    reports half the story."""
    before = outcomes_with(tp=6, fp=2, tn=5, fn=3)
    stricter = outcomes_with(tp=2, fp=0, tn=7, fn=7)

    metric = F1(over=AGREES, threshold=0.6, tolerance=0.05)
    precision = Precision(over=AGREES, threshold=0.6, tolerance=0.05)
    p_before = precision(before).score.score
    p_after = precision(stricter).score.score
    f_before = metric(before).score.score
    f_after = metric(stricter).score.score

    assert p_before is not None and p_after is not None
    assert f_before is not None and f_after is not None
    assert p_after > p_before  # precision alone calls this an improvement
    assert f_after < f_before  # F1 does not


def test_f1_errors_on_an_empty_denominator() -> None:
    """No true positives and no mistakes of either kind: nothing was kept and
    nothing should have been. A perfect score there would be a lie."""
    verdict = F1(over=AGREES, threshold=0.6, tolerance=0.05)(
        outcomes_with(tp=0, fp=0, tn=5, fn=0)
    )
    assert verdict.status == "error"
    assert verdict.score.score is None
    assert "empty denominator" in verdict.reason


def test_f1_is_its_own_question_not_a_threshold_on_precision() -> None:
    identities = {
        F1(over=AGREES, threshold=0.6, tolerance=0.05).identity,
        Precision(over=AGREES, threshold=0.6, tolerance=0.05).identity,
    }
    assert len(identities) == 2


def test_f1_counts_the_exclusions_like_the_others() -> None:
    cases = [*outcomes_with(tp=3, fp=1, tn=2, fn=1), errored("boom", "positive")]
    verdict = F1(over=AGREES, threshold=0.6, tolerance="1/7")(cases)
    assert verdict.score.metadata["errored_excluded"] == 1
    assert verdict.score.metadata["considered"] == 7
    assert "1 could not be judged" in verdict.reason
