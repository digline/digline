"""The whole cycle, on a real filesystem.

This was a throwaway demo until it found something the 210 unit tests around it
could not: a case that is both new and unjudgeable is classified `new` by
`compare()`, so counting the tally let the report announce that every case had
been judged while three had not. Nothing in the parts was wrong; the composition
was. That is why it is a test now.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from digline.core import (
    Contains,
    CostBudget,
    JudgeReply,
    LlmRubric,
    compare,
    redact,
)
from digline.report import headline, render_html
from digline.run import Case, Response, Suite, execute
from digline.store import ErroredRunError, FileResultStore

BASELINE_AT = "2026-08-25T10:00:00+00:00"
RUN_AT = "2026-08-25T11:00:00+00:00"
JUDGED = "The answer names the correct city and stays in the required register"

QUALITY: dict[str, float] = {}


def judge(prompt: str) -> JudgeReply:
    return JudgeReply(score=QUALITY["score"], reason=JUDGED)


def assertions() -> list[object]:
    return [
        Contains(needle="Rome"),
        CostBudget(max_usd=0.10, tolerance=0.02),
        LlmRubric(rubric="does it answer?", judge=judge, threshold=0.7, tolerance=0.05),
    ]


def suite_of(*cases: Case, environment: str = "staging") -> Suite:
    return Suite(
        tenant="acme-bank",
        environment=environment,
        name="qa",
        assertions=assertions(),  # type: ignore[arg-type]
        cases=cases,
    )


def target_scoring(scores: dict[str, float]):  # type: ignore[no-untyped-def]
    def target(case: Case) -> Response:
        if case.id == "flaky":
            raise TimeoutError("provider did not answer in 30s")
        QUALITY["score"] = scores[case.id]
        return Response(
            output="The capital is Rome.",
            input="What is the capital of Italy?",
            cost_usd=0.01,
            latency_ms=120.0,
        )

    return target


GOOD = {"capital-it": 0.95, "capital-fr": 0.92}
WORSE = {"capital-it": 0.95, "capital-fr": 0.55}


def test_the_full_cycle(tmp_path: Path) -> None:
    store = FileResultStore(tmp_path)

    # 1. A reference is produced from a suite that can be judged end to end.
    reference_suite = suite_of(
        Case(id="capital-it"), Case(id="capital-fr"), environment="production"
    )
    reference = execute(reference_suite, target_scoring(GOOD), created_at=BASELINE_AT)
    store.promote_baseline(store.write_run(reference), reference_suite.config_hash())
    baseline = store.read_baseline("acme-bank", "qa")
    assert baseline is not None

    # 2. A later run: one answer got worse, and a new case cannot run at all.
    later_suite = suite_of(
        Case(id="capital-it"), Case(id="capital-fr"), Case(id="flaky")
    )
    later = execute(later_suite, target_scoring(WORSE), created_at=RUN_AT)
    store.write_run(later)

    comparison = compare(later, baseline)
    head = headline(comparison, later, baseline, locale="it")

    # 3. The headline answers the question the end company asks.
    assert head.worse is True
    # The regression the developer cares about, and nothing else counted as one.
    assert head.counts["regressed"] == 1
    # The bug this test exists for: `flaky` is classified `new`, not `errored`,
    # yet its three checks could not run and the reader must be told.
    assert comparison.counts.get("errored", 0) == 0
    assert head.unjudged == 1
    assert head.suspended == 0
    assert head.config_changed is False

    # 4. The document says the same thing, in the reader's language.
    document = render_html(comparison, later, baseline, locale="it")
    assert head.sentence in document
    assert "È peggiorato? Sì" in document
    assert "production" in document and "staging" in document
    assert JUDGED in document


def test_the_cycle_leaves_only_what_belongs_in_the_repository(
    tmp_path: Path,
) -> None:
    store = FileResultStore(tmp_path)
    suite = suite_of(Case(id="capital-it"), Case(id="capital-fr"))
    run = execute(suite, target_scoring(GOOD), created_at=BASELINE_AT)
    store.promote_baseline(store.write_run(run), suite.config_hash())

    written = {
        p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*") if p.is_file()
    }
    assert ".digline/acme-bank/baselines/qa.json" in written
    assert any(p.startswith(".digline/acme-bank/runs/qa/") for p in written)
    ignored = (tmp_path / ".digline" / ".gitignore").read_text(encoding="utf-8")
    assert "*/runs/" in ignored


def test_a_run_that_could_not_judge_is_not_promotable(tmp_path: Path) -> None:
    """The other half of the same story: the flaky case cannot become the
    reference, which is why suspension exists as the declared alternative."""
    store = FileResultStore(tmp_path)
    suite = suite_of(Case(id="capital-it"), Case(id="flaky"))
    run = execute(suite, target_scoring(GOOD), created_at=RUN_AT)
    with pytest.raises(ErroredRunError, match="flaky"):
        store.promote_baseline(store.write_run(run), suite.config_hash())


def test_suspending_the_flaky_case_makes_the_suite_promotable(
    tmp_path: Path,
) -> None:
    store = FileResultStore(tmp_path)
    suite = suite_of(
        Case(id="capital-it"),
        Case(id="flaky", suspended="provider times out, ticket 412"),
    )
    run = execute(suite, target_scoring(GOOD), created_at=RUN_AT)
    store.promote_baseline(store.write_run(run), suite.config_hash())

    baseline = store.read_baseline("acme-bank", "qa")
    assert baseline is not None
    head = headline(compare(run, baseline), run, baseline, locale="en")
    assert head.suspended == 1
    assert head.unjudged == 0


def test_the_customer_can_send_the_verdict_without_the_data(
    tmp_path: Path,
) -> None:
    """World 3 to world 2: the software house sees the regression, the end
    company keeps the words."""
    store = FileResultStore(tmp_path)
    reference_suite = suite_of(Case(id="capital-it"), Case(id="capital-fr"))
    reference = execute(reference_suite, target_scoring(GOOD), created_at=BASELINE_AT)
    store.promote_baseline(store.write_run(reference), reference_suite.config_hash())
    baseline = store.read_baseline("acme-bank", "qa")
    assert baseline is not None

    later = execute(reference_suite, target_scoring(WORSE), created_at=RUN_AT)
    hidden = redact(later)

    # The regression survives the boundary.
    assert compare(hidden, baseline).counts["regressed"] == 1
    # The judgement does not.
    document = render_html(compare(hidden, baseline), hidden, baseline, locale="it")
    assert JUDGED not in document
    assert "dati redatti" in document
