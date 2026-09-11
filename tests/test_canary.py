"""The canary case: excluded from the metrics, loud when it moves.

The table in ADR 0016 §2 is eleven counting sites and the shape of it is the
decision — a canary is out of every **metric** and in everything that reports
what happened. So most of this file is that table, one assertion at a time.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from tests._helpers import cli

from digline.core import (
    Accuracy,
    CaseOutcome,
    CaseResult,
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
from digline.core.aggregate import build_matrix, per_sample_outcomes
from digline.report import facts, headline, run_tally
from digline.run import Case, Response, Suite, execute, planned_calls
from digline.wire import EXIT_UNJUDGED, EXIT_WORSE, compare_json, exit_code

CREATED = "2026-01-01T00:00:00+00:00"
LATER = "2026-01-02T00:00:00+00:00"


def verdict(score: float, *, name: str = "contains", threshold: float = 0.7) -> Verdict:
    return Verdict(
        score=Score(name=name, score=score),
        threshold=threshold,
        status="pass" if score >= threshold else "fail",
        reason="judged",
        assertion_id=f"id-{name}",
    )


def outcome(
    case_id: str, score: float, *, label: str = "positive", canary: bool = False
):
    return CaseOutcome(
        case_id=case_id,
        label=label,  # type: ignore[arg-type]
        verdict=verdict(score),
        canary=canary,
    )


# --------------------------------------------------------------------------- #
# §1 — the declaration, and what it refuses
# --------------------------------------------------------------------------- #


def test_a_canary_declares_no_group() -> None:
    with pytest.raises(ValueError, match="counted in no aggregate"):
        Case(id="probe", canary=True, group="travel")


def test_a_canary_needs_no_label_while_the_others_do() -> None:
    """Exempt because it is not in the population being measured — and the
    exemption is narrow: an ordinary unlabelled case still refuses."""
    Suite(
        tenant="acme",
        environment="dev",
        name="qa",
        assertions=[Contains(needle="Rome")],
        cases=[
            Case(id="one", label="positive"),
            Case(id="probe", canary=True),
        ],
        samples=2,
        min_agreement="2/2",
        run_assertions=[Precision(over="contains", threshold="1/2", tolerance=0.0)],
    )
    with pytest.raises(ValueError, match="every case needs a label"):
        Suite(
            tenant="acme",
            environment="dev",
            name="qa",
            assertions=[Contains(needle="Rome")],
            cases=[Case(id="one"), Case(id="probe", canary=True)],
            samples=2,
            min_agreement="2/2",
            run_assertions=[Precision(over="contains", threshold="1/2", tolerance=0.0)],
        )


def test_a_canary_case_does_not_create_a_group() -> None:
    suite = Suite(
        tenant="acme",
        environment="dev",
        name="qa",
        assertions=[Contains(needle="Rome")],
        cases=[Case(id="one", group="travel"), Case(id="probe", canary=True)],
        samples=2,
        min_agreement="2/2",
    )
    assert suite.groups() == ("travel",)


def test_the_flag_round_trips_and_is_absent_when_false() -> None:
    run = Run(
        tenant="acme",
        environment="dev",
        suite="qa",
        config_hash="h",
        created_at=CREATED,
        results=(CaseResult("probe", canary=True), CaseResult("one")),
    )
    document = json.loads(run_to_json(run))
    assert document["results"][0]["canary"] is True
    assert "canary" not in document["results"][1]
    assert run_from_json(run_to_json(run)) == run


def test_redaction_keeps_which_case_watched_the_model() -> None:
    """Not payload: a redacted document that lost it would report an exit code
    its own contents could not account for."""
    run = Run(
        tenant="acme",
        environment="dev",
        suite="qa",
        config_hash="h",
        created_at=CREATED,
        results=(CaseResult("probe", (verdict(0.9),), canary=True),),
    )
    assert redact(run).results[0].canary


# --------------------------------------------------------------------------- #
# §2, §3 — every denominator, and the count that keeps them checkable
# --------------------------------------------------------------------------- #


def test_the_matrix_excludes_it_and_says_so() -> None:
    matrix = build_matrix(
        [
            outcome("one", 0.9),
            outcome("two", 0.9),
            outcome("probe", 0.2, canary=True),
        ]
    )
    assert matrix.considered == 2
    assert matrix.canary_excluded == 1
    assert matrix.unlabelled_excluded == 0
    assert matrix.as_metadata()["canary_excluded"] == 1


@pytest.mark.parametrize(
    "aggregate", [Precision, Recall, Accuracy], ids=["precision", "recall", "accuracy"]
)
def test_no_aggregate_counts_it(aggregate: type) -> None:
    counted = [outcome("one", 0.9), outcome("two", 0.9)]
    with_canary = [*counted, outcome("probe", 0.1, canary=True)]
    metric = aggregate(over="contains", threshold="1/2", tolerance=0.0)
    assert metric(counted).score.score == metric(with_canary).score.score


def test_the_clause_is_silent_when_there_is_no_canary() -> None:
    """Rendered always, it would rewrite the recorded reason of every aggregate
    verdict in every committed baseline of every suite that has none."""
    metric = Accuracy(over="contains", threshold="1/2", tolerance=0.0)
    assert "canary" not in metric([outcome("one", 0.9)]).reason
    assert (
        "1 canary"
        in metric([outcome("one", 0.9), outcome("p", 0.1, canary=True)]).reason
    )


def test_a_canary_does_not_delete_the_runs_noise_interval() -> None:
    """The §4 trap: a canary sampled differently would otherwise silently remove
    the interval of every aggregate in the run, and the loss would look exactly
    like a suite that had not been sampled."""
    sampled = CaseOutcome(
        case_id="one",
        label="positive",
        verdict=Verdict(
            score=Score(
                name="contains",
                score=0.8,
                samples=(0.7, 0.9),
                sample_min=0.7,
                sample_max=0.9,
            ),
            threshold=0.7,
            status="pass",
            reason="judged",
        ),
    )
    odd = CaseOutcome(
        case_id="probe",
        label=None,
        verdict=Verdict(
            score=Score(
                name="contains",
                score=0.8,
                samples=(0.7, 0.8, 0.9),
                sample_min=0.7,
                sample_max=0.9,
            ),
            threshold=0.7,
            status="pass",
            reason="judged",
        ),
        canary=True,
    )
    assert per_sample_outcomes([sampled]) != ()
    assert per_sample_outcomes([sampled, odd]) != ()


def test_it_is_counted_everywhere_that_reports_what_happened() -> None:
    """Out of the metrics, in the tally and in the planned calls: it ran, it was
    called, and a reader must not have to discover it by subtraction."""
    suite = Suite(
        tenant="acme",
        environment="dev",
        name="qa",
        assertions=[Contains(needle="Rome")],
        cases=[Case(id="one"), Case(id="probe", canary=True)],
        samples=2,
        min_agreement="2/2",
    )
    run = execute(
        suite, lambda case: Response(output="Rome", input="q"), created_at=CREATED
    )
    assert planned_calls(suite).cases == 2
    assert run_tally(run).cases == 2
    assert run.results[1].canary


# --------------------------------------------------------------------------- #
# §5, §6 — what counts as moved, and what it costs
# --------------------------------------------------------------------------- #


def moved_run(before: float, after: float) -> tuple[Run, Run]:
    def side(score: float, created: str) -> Run:
        return Run(
            tenant="acme",
            environment="dev",
            suite="qa",
            config_hash="h",
            created_at=created,
            results=(
                CaseResult("one", (verdict(0.9),)),
                CaseResult("probe", (verdict(score),), canary=True),
            ),
        )

    return side(after, LATER), side(before, CREATED)


@pytest.mark.parametrize(
    ("before", "after"), [(0.9, 0.3), (0.3, 0.9)], ids=["dropped", "rose"]
)
def test_a_canary_that_moved_exits_one_in_either_direction(
    before: float, after: float
) -> None:
    run, baseline = moved_run(before, after)
    comparison = compare(run, baseline)
    head = headline(comparison, run, baseline, locale="en")
    assert comparison.canary_moved
    assert head.canary_moved
    assert exit_code(head) == EXIT_WORSE


def test_a_canary_that_improved_is_not_called_worse() -> None:
    """The reason it is not folded into `worse`: the headline would say one
    check got worse about a check that got better."""
    run, baseline = moved_run(0.3, 0.9)
    head = headline(compare(run, baseline), run, baseline, locale="en")
    assert not head.worse
    assert "likely changed" in head.sentence
    assert exit_code(head) == EXIT_WORSE


def test_a_canary_that_stayed_put_says_nothing() -> None:
    run, baseline = moved_run(0.9, 0.9)
    head = headline(compare(run, baseline), run, baseline, locale="en")
    assert not head.canary_moved
    assert "likely changed" not in head.sentence
    assert exit_code(head) == 0


def test_a_canary_that_errored_is_unjudged_and_not_moved() -> None:
    broken = Run(
        tenant="acme",
        environment="dev",
        suite="qa",
        config_hash="h",
        created_at=LATER,
        results=(
            CaseResult(
                "probe",
                (
                    Verdict(
                        score=Score(name="contains", score=None),
                        threshold=0.7,
                        status="error",
                        reason="the target raised",
                        assertion_id="id-contains",
                    ),
                ),
                canary=True,
            ),
        ),
    )
    baseline = Run(
        tenant="acme",
        environment="dev",
        suite="qa",
        config_hash="h",
        created_at=CREATED,
        results=(CaseResult("probe", (verdict(0.9),), canary=True),),
    )
    head = headline(compare(broken, baseline), broken, baseline, locale="en")
    assert not head.canary_moved
    assert exit_code(head) == EXIT_UNJUDGED


def test_a_canary_added_or_removed_is_not_a_moved_model() -> None:
    run, baseline = moved_run(0.9, 0.9)
    without = Run(
        tenant="acme",
        environment="dev",
        suite="qa",
        config_hash="h",
        created_at=CREATED,
        results=(CaseResult("one", (verdict(0.9),)),),
    )
    assert not compare(run, without).canary_moved
    assert not compare(without, baseline).canary_moved


def test_a_movement_inside_the_baselines_interval_is_not_a_moved_model() -> None:
    """The floor doing its job. Without it every wobble would stop a release,
    which is the canary nobody trusts."""
    sampled = Verdict(
        score=Score(
            name="contains",
            score=0.8,
            samples=(0.7, 0.9),
            sample_min=0.7,
            sample_max=0.9,
        ),
        threshold=0.5,
        status="pass",
        reason="judged",
        assertion_id="id-contains",
    )
    now = Verdict(
        score=Score(
            name="contains",
            score=0.75,
            samples=(0.7, 0.8),
            sample_min=0.7,
            sample_max=0.8,
        ),
        threshold=0.5,
        status="pass",
        reason="judged",
        assertion_id="id-contains",
    )
    run = Run(
        tenant="acme",
        environment="dev",
        suite="qa",
        config_hash="h",
        created_at=LATER,
        results=(CaseResult("probe", (now,), canary=True),),
    )
    baseline = Run(
        tenant="acme",
        environment="dev",
        suite="qa",
        config_hash="h",
        created_at=CREATED,
        results=(CaseResult("probe", (sampled,), canary=True),),
    )
    assert not compare(run, baseline).canary_moved


def test_a_suite_with_a_canary_has_to_sample() -> None:
    with pytest.raises(ValueError, match="no noise to measure"):
        Suite(
            tenant="acme",
            environment="dev",
            name="qa",
            assertions=[Contains(needle="Rome")],
            cases=[Case(id="probe", canary=True)],
        )
    # And the refusal is scoped: a suite with no canary still runs at one.
    Suite(
        tenant="acme",
        environment="dev",
        name="qa",
        assertions=[Contains(needle="Rome")],
        cases=[Case(id="one")],
    )


# --------------------------------------------------------------------------- #
# §7, §8 — the sentence, the reading, and the wire
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("locale", ["en", "it"])
def test_the_clause_exists_in_both_locales(locale: str) -> None:
    run, baseline = moved_run(0.9, 0.3)
    head = headline(compare(run, baseline), run, baseline, locale=locale)  # type: ignore[arg-type]
    assert "probe" in head.sentence
    assert "0.900000" in head.sentence


def test_the_reading_accounts_for_the_exit_code() -> None:
    run, baseline = moved_run(0.9, 0.3)
    kinds = [getattr(fact, "kind", None) for fact in facts(run, compare(run, baseline))]
    assert "canary" in kinds


def test_the_wire_carries_the_fact_and_the_row() -> None:
    run, baseline = moved_run(0.9, 0.3)
    comparison = compare(run, baseline)
    head = headline(comparison, run, baseline, locale="en")
    payload = compare_json(comparison, head, full=True)
    assert payload["canary_moved"] is True
    assert payload["exit_code"] == EXIT_WORSE
    rows = payload["deltas"]
    assert isinstance(rows, list)
    assert [row["canary"] for row in rows] == [False, True]  # type: ignore[index]


def test_the_cli_stops_on_a_canary_that_moved(repo: Path) -> None:
    """End to end, because the exit code is the contract: a suite whose canary
    answers differently exits 1 with no regression anywhere in it."""
    suite = repo / "suite_canary.py"
    suite.write_text(
        """
from pathlib import Path

from digline.core import Contains
from digline.run import Case, Response, Suite

suite = Suite(
    tenant="acme-bank",
    environment="staging",
    name="canary",
    assertions=[Contains(needle="Rome")],
    cases=[Case(id="one"), Case(id="probe", canary=True)],
    samples=2,
    min_agreement="2/2",
)


def target(case):
    answer = Path("answer.txt").read_text().strip() if case.id == "probe" else "Rome"
    return Response(output=answer, input="capital?")
""",
        encoding="utf-8",
    )
    (repo / "answer.txt").write_text("Rome\n", encoding="utf-8")

    first = cli(repo, "run", "--suite", "suite_canary.py")
    assert first.returncode == 0, first.stderr
    key = first.stdout.strip()
    promoted = cli(repo, "promote", "--suite", "suite_canary.py", "--run", key)
    assert promoted.returncode == 0, promoted.stderr

    (repo / "answer.txt").write_text("Paris\n", encoding="utf-8")
    second = cli(repo, "run", "--suite", "suite_canary.py")
    moved = second.stdout.strip()
    compared = cli(
        repo, "compare", "--suite", "suite_canary.py", "--run", moved, "--json"
    )
    payload = json.loads(compared.stdout)
    assert payload["canary_moved"] is True
    assert compared.returncode == EXIT_WORSE
