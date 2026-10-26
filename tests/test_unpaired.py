"""A check the comparison could not pair is a cause of exit 2. (#642)

`compare()` pairs a verdict with its reference on the assertion's identity, and
a `Repeated` check's identity holds its `inner`'s threshold and tolerance. So a
moved bar inside a `Repeated` turns one check into a `new` and a `missing`, and
neither is counted. Measured before this existed: the reference 0.75 passing,
the run 0.65 passing under a bar lowered from 0.7 to 0.6, and `compare` said
*Nothing got worse* and exited `0`. The same edit on a check outside a
`Repeated` pairs, reports the fall and exits `1`.

The identity is not changed to fix it: the project has declined that move three
times, for the reason `4fa33335` wrote down — every stored baseline holding the
check would stop pairing and need re-promoting. What is added is what two
documents can say without a suite: a `new` and a `missing` on the same case, in
the same scope and under the same name, were not compared. That is a cause of
`2`, and the headline says which checks, what each side scored and passed, and
whether the bar moved between them.

Every run here is measured by the driver, so every `assertion_id` is the one the
assertion computes rather than one written by hand: the defect lives in that
computation, and a test that wrote the ids would test nothing.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from digline.core import (
    Assertion,
    JudgeReply,
    LlmRubric,
    Repeated,
    Run,
    causes_of_two,
    compare,
    key_of,
)
from digline.host import entry_for, promote_priced
from digline.report import Headline, headline
from digline.report.text import LOCALES, Locale, phrase
from digline.run import Case, Response, Suite, execute
from digline.store import FileResultStore
from digline.wire import EXIT_OK, EXIT_UNJUDGED, compare_json, exit_code

REFERENCE_AT = "2026-10-26T10:00:00+00:00"
RUN_AT = "2026-10-26T11:00:00+00:00"
PROMOTED_AT = "2026-10-26T10:30:00+00:00"
RECORDED_AT = "2026-10-26T12:00:00+00:00"

#: `exit_code`'s `1`. `digline.wire` names `0` and `2`; this one is spelled out
#: where it is read.
WORSE = 1


def target(case: Case) -> Response:
    return Response(output="Rome")


def rubric(
    threshold: float,
    score: float,
    *,
    tolerance: float = 0.05,
    name: str = "llm_rubric",
    text: str = "Is it right?",
) -> LlmRubric:
    """A rubric whose judge always answers `score`: the behaviour, held still
    or moved by the test."""

    def judge(prompt: str) -> JudgeReply:
        return JudgeReply(score=score, reason="judged")

    return LlmRubric(
        rubric=text, judge=judge, threshold=threshold, tolerance=tolerance, name=name
    )


def wrapped(threshold: float, score: float, **kwargs: object) -> Repeated:
    return Repeated(
        inner=rubric(threshold, score, **kwargs),  # type: ignore[arg-type]
        samples=3,
        min_agreement="2/3",
    )


def suite(assertion: Assertion) -> Suite:
    return Suite(
        tenant="acme",
        environment="dev",
        name="qa",
        assertions=[assertion],
        cases=[Case(id="one")],
    )


def measured(assertion: Assertion, created_at: str) -> Run:
    return execute(suite(assertion), target, created_at=created_at)


def compared(
    before: Assertion, after: Assertion, *, locale: Locale = "en"
) -> tuple[Run, Run, Headline]:
    reference = measured(before, REFERENCE_AT)
    run = measured(after, RUN_AT)
    head = headline(
        compare(run, reference),
        run,
        reference,
        locale=locale,
        declared=suite(after).declared(),
    )
    return reference, run, head


# --------------------------------------------------------------------------- #
# The exit code
# --------------------------------------------------------------------------- #


def test_a_bar_lowered_inside_repeated_over_a_fall_exits_2() -> None:
    """c2, the case that made this: the bar went from 0.7 to 0.6 while the
    judge fell from 0.75 to 0.65. Both sides pass, nothing was compared, and
    until now the exit was `0`."""
    _reference, _run, head = compared(wrapped(0.7, 0.75), wrapped(0.6, 0.65))

    assert head.counts["regressed"] == 0
    assert head.unjudged_causes == ("unpaired",)
    assert head.unpaired == 1
    assert exit_code(head) == EXIT_UNJUDGED


def test_a_bar_raised_inside_repeated_over_a_fall_exits_2() -> None:
    """c1: the bar went from 0.7 to 0.8 and the judge from 0.75 to 0.5, a pass
    turned into a fail that nothing counted."""
    _reference, _run, head = compared(wrapped(0.7, 0.75), wrapped(0.8, 0.5))

    assert head.unjudged_causes == ("unpaired",)
    assert exit_code(head) == EXIT_UNJUDGED


def test_a_real_regression_inside_repeated_still_exits_1() -> None:
    """c0: the bar held, the judge fell. The check pairs, the fall is a
    regression, and the new cause must not take its place."""
    _reference, _run, head = compared(wrapped(0.7, 0.75), wrapped(0.7, 0.5))

    assert head.counts["regressed"] == 1
    assert "unpaired" not in head.unjudged_causes
    assert head.unpaired == 0
    assert exit_code(head) == WORSE


def test_a_bar_moved_outside_repeated_pairs_and_exits_1() -> None:
    """The control: a check outside a `Repeated` keeps its identity when its bar
    moves, so the fall is compared and reported."""
    _reference, _run, head = compared(rubric(0.7, 0.75), rubric(0.6, 0.65))

    assert head.counts["regressed"] == 1
    assert "unpaired" not in head.unjudged_causes
    assert exit_code(head) == WORSE


def test_a_new_and_a_missing_under_different_names_are_not_the_cause() -> None:
    """A check removed and another added under its own name is what `new` and
    `missing` have always said, and it stays that: no pair to name."""
    _reference, _run, head = compared(
        rubric(0.7, 0.75, name="tone"), rubric(0.7, 0.75, name="accuracy")
    )

    assert head.counts["new"] == 1
    assert head.counts["missing"] == 1
    assert head.unjudged_causes == ()
    assert exit_code(head) == EXIT_OK


def test_a_regression_beside_the_cause_still_exits_1() -> None:
    """The precedence `exit_code` has always had: a check that got worse
    outranks every cause of `2`, and the cause is still listed."""
    reference = execute(
        Suite(
            tenant="acme",
            environment="dev",
            name="qa",
            assertions=[wrapped(0.7, 0.75, name="wrapped"), rubric(0.7, 0.75)],
            cases=[Case(id="one")],
        ),
        target,
        created_at=REFERENCE_AT,
    )
    now = Suite(
        tenant="acme",
        environment="dev",
        name="qa",
        assertions=[wrapped(0.6, 0.65, name="wrapped"), rubric(0.7, 0.5)],
        cases=[Case(id="one")],
    )
    run = execute(now, target, created_at=RUN_AT)
    head = headline(
        compare(run, reference), run, reference, locale="en", declared=now.declared()
    )

    assert head.unjudged_causes == ("unpaired",)
    assert exit_code(head) == WORSE


def test_the_cause_needs_a_reference() -> None:
    """A first round has nothing to pair against, so the cause cannot hold."""
    run = measured(wrapped(0.7, 0.75), RUN_AT)

    assert "unpaired" not in causes_of_two(run, None, declared=None)


# --------------------------------------------------------------------------- #
# The clause
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("locale", LOCALES)
def test_the_clause_says_each_pair_was_not_compared(locale: Locale) -> None:
    """The sentence keeps *Nothing got worse* and qualifies it straight after,
    as `fact.denominator_moved` does: the count was not taken over every check.
    """
    _reference, _run, head = compared(
        wrapped(0.7, 0.75), wrapped(0.6, 0.65), locale=locale
    )
    worse = phrase(locale, "fact.worse.none")
    opening = phrase(locale, "fact.unpaired.one", pairs="{pairs}").split("{pairs}")[0]

    assert opening.strip()
    assert worse in head.sentence
    assert opening in head.sentence
    # Straight after: nothing between the count and what qualifies it.
    assert head.sentence.index(worse) + len(worse) + 1 == head.sentence.index(opening)
    assert "one · llm_rubric" in head.sentence


@pytest.mark.parametrize("locale", LOCALES)
def test_the_clause_shows_each_side_with_its_score_and_its_outcome(
    locale: Locale,
) -> None:
    """The only place the fall is visible: 0.75 passing in the reference, 0.65
    passing here. Without these numbers the clause says that something was not
    compared and hides what it was."""
    _reference, _run, head = compared(
        wrapped(0.7, 0.75), wrapped(0.6, 0.65), locale=locale
    )

    before = phrase(locale, "fact.unpaired.state.pass", score="0.750000")
    after = phrase(locale, "fact.unpaired.state.pass", score="0.650000")
    assert before in head.sentence
    assert after in head.sentence
    assert head.sentence.index(before) < head.sentence.index(after)


@pytest.mark.parametrize("locale", LOCALES)
def test_the_clause_shows_a_failure_as_a_failure(locale: Locale) -> None:
    _reference, _run, head = compared(
        wrapped(0.7, 0.75), wrapped(0.8, 0.5), locale=locale
    )

    assert phrase(locale, "fact.unpaired.state.pass", score="0.750000") in head.sentence
    assert phrase(locale, "fact.unpaired.state.fail", score="0.500000") in head.sentence


@pytest.mark.parametrize("locale", LOCALES)
def test_the_clause_names_a_moved_threshold(locale: Locale) -> None:
    _reference, _run, head = compared(
        wrapped(0.7, 0.75), wrapped(0.6, 0.65), locale=locale
    )

    assert (
        phrase(
            locale,
            "fact.unpaired.moved",
            field=phrase(locale, "fact.unpaired.field.threshold"),
            before="0.700000",
            after="0.600000",
        )
        in head.sentence
    )
    assert phrase(locale, "fact.unpaired.field.tolerance") not in head.sentence


@pytest.mark.parametrize("locale", LOCALES)
def test_the_clause_names_a_moved_tolerance(locale: Locale) -> None:
    _reference, _run, head = compared(
        wrapped(0.7, 0.75, tolerance=0.05),
        wrapped(0.7, 0.75, tolerance=0.1),
        locale=locale,
    )

    assert head.unpaired == 1
    assert (
        phrase(
            locale,
            "fact.unpaired.moved",
            field=phrase(locale, "fact.unpaired.field.tolerance"),
            before="0.050000",
            after="0.100000",
        )
        in head.sentence
    )
    assert phrase(locale, "fact.unpaired.field.threshold") not in head.sentence


@pytest.mark.parametrize("locale", LOCALES)
def test_the_clause_names_no_bar_where_none_moved(locale: Locale) -> None:
    """The rubric's text changed and the bar did not: the two verdicts carry
    the same threshold and tolerance, and the clause says nothing of either."""
    _reference, _run, head = compared(
        wrapped(0.7, 0.75), wrapped(0.7, 0.75, text="Is it kind?"), locale=locale
    )

    assert head.unpaired == 1
    assert phrase(locale, "fact.unpaired.field.threshold") not in head.sentence
    assert phrase(locale, "fact.unpaired.field.tolerance") not in head.sentence


@pytest.mark.parametrize("locale", LOCALES)
def test_the_clause_says_what_the_documents_cannot(locale: Locale) -> None:
    """A rubric whose text was edited and a rubric removed beside another added
    under the same default name leave the same two documents. The clause says
    that it cannot tell them apart, rather than guessing which."""
    _reference, _run, head = compared(
        wrapped(0.7, 0.75), wrapped(0.6, 0.65), locale=locale
    )
    tail = phrase(locale, "fact.unpaired.one", pairs="{pairs}").split("{pairs}")[1]

    assert tail.strip(". ")
    assert tail in head.sentence


@pytest.mark.parametrize("locale", LOCALES)
def test_the_clause_counts_several_pairs(locale: Locale) -> None:
    reference = execute(
        Suite(
            tenant="acme",
            environment="dev",
            name="qa",
            assertions=[wrapped(0.7, 0.75)],
            cases=[Case(id="one"), Case(id="two")],
        ),
        target,
        created_at=REFERENCE_AT,
    )
    now = Suite(
        tenant="acme",
        environment="dev",
        name="qa",
        assertions=[wrapped(0.6, 0.65)],
        cases=[Case(id="one"), Case(id="two")],
    )
    run = execute(now, target, created_at=RUN_AT)
    head = headline(
        compare(run, reference), run, reference, locale=locale, declared=now.declared()
    )

    assert head.unpaired == 2
    assert "one · llm_rubric" in head.sentence
    assert "two · llm_rubric" in head.sentence
    opening = phrase(locale, "fact.unpaired.many", count=2, pairs="{pairs}")
    assert opening.split("{pairs}")[0] in head.sentence


def test_the_clause_is_silent_where_nothing_is_unpaired() -> None:
    _reference, _run, head = compared(wrapped(0.7, 0.75), wrapped(0.7, 0.5))

    assert "fact.unpaired" not in head.sentence
    assert phrase("en", "fact.unpaired.field.threshold") not in head.sentence


# --------------------------------------------------------------------------- #
# The wire and the register
# --------------------------------------------------------------------------- #


def test_the_wire_carries_the_count_and_the_cause() -> None:
    reference, run, head = compared(wrapped(0.7, 0.75), wrapped(0.6, 0.65))

    for full in (False, True):
        payload = compare_json(
            compare(run, reference), head, baseline=reference, full=full, run=run
        )
        assert payload["unpaired"] == 1
        assert payload["unjudged_causes"] == ["unpaired"]
        assert payload["exit_code"] == EXIT_UNJUDGED


def test_the_register_records_the_count(tmp_path: Path) -> None:
    reference, run, _head = compared(wrapped(0.7, 0.75), wrapped(0.6, 0.65))
    entry = entry_for(
        run,
        key_of(run.created_at, run.config_hash),
        reference,
        key_of(reference.created_at, reference.config_hash),
        disposition="accepted",
        recorded_at=RECORDED_AT,
        digline_version="0.0.0",
        declared=suite(wrapped(0.6, 0.65)).declared(),
    )

    assert entry.outcome.unpaired == 1
    assert entry.exit_code == EXIT_UNJUDGED


# --------------------------------------------------------------------------- #
# Promotion
# --------------------------------------------------------------------------- #


def test_the_rebaseline_after_a_moved_bar_is_not_refused(tmp_path: Path) -> None:
    """**Promotion does not refuse on this cause, and this is the test that
    holds it.** The comparison a promotion reads is the run it promotes against
    the reference it replaces, and after a bar moved inside a `Repeated` that
    is exactly the pair that carries the cause: the re-baseline a person makes
    on purpose. Refusing it would refuse the one way out of the state the cause
    reports."""
    store = FileResultStore(tmp_path)
    before = suite(wrapped(0.7, 0.75))
    reference = execute(before, target, created_at=REFERENCE_AT)
    store.write_run(reference)
    reference_key = key_of(reference.created_at, reference.config_hash)
    promote_priced(
        store,
        before,
        "",
        reference_key,
        replacing="none",
        promoted_at=PROMOTED_AT,
    )

    after = suite(wrapped(0.6, 0.65))
    run = execute(after, target, created_at=RUN_AT)
    store.write_run(run)
    run_key = key_of(run.created_at, run.config_hash)
    current = store.read_baseline("acme", "qa")
    assert current is not None
    assert "unpaired" in causes_of_two(run, compare(run, current), declared=None)

    promoted = promote_priced(
        store,
        after,
        "",
        run_key,
        replacing=reference_key,
        promoted_at=RECORDED_AT,
    )

    assert key_of(promoted.created_at, promoted.config_hash) == run_key
