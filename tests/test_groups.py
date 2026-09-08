"""Per-group aggregates where they leave the suite: compare, diff, the report.

ADR 0010 §9 claims that **nothing downstream is special-cased** — an expanded
aggregate is an ordinary run-scoped verdict, and a group appearing or vanishing
between two runs is the existing `new`/`missing` rule meeting a key it has not
met before. A claim of that shape is worth exactly what its tests are worth:
the whole point is that no code was written for it, so nothing would fail if it
were false.

Writing them found the one place the claim does not hold, and it is recorded in
the ADR rather than smoothed over here: `diff()` refuses a pair whose group sets
differ, because a changed group set is a changed `config_hash`, and ADR 0008 §3
refuses that before it reads a single verdict.

The grid ordering (§9) and the sentence the document owes a reader (§10) are
here too, because both are about what a group does once it is on a page.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import pytest

from digline.core import (
    Accuracy,
    AssertionBase,
    Comparison,
    Contains,
    DifferentSuitesError,
    EvaluatorInputs,
    Precision,
    Run,
    Verdict,
    compare,
    diff,
    grouped_name,
    split_grouped_name,
)
from digline.report import headline, render_html, runs_page
from digline.report.text import LOCALES
from digline.run import Case, Response, Suite, execute

BASE_AT = "2026-01-01T00:00:00+00:00"
LATER_AT = "2026-01-02T00:00:00+00:00"

AGREES = "agrees"

#: `(id, label, group)`.
Marked = tuple[str, str, str | None]

ORDERS: list[Marked] = [("o1", "positive", "orders"), ("o2", "negative", "orders")]
RETURNS: list[Marked] = [("r1", "positive", "returns"), ("r2", "negative", "returns")]
REFUNDS: list[Marked] = [("f1", "positive", "refunds"), ("f2", "negative", "refunds")]


def build(cases: Sequence[Marked], *, threshold: str = "1/2") -> Suite:
    return Suite(
        tenant="acme",
        environment="staging",
        name="triage",
        assertions=[Contains(needle="YES", name=AGREES)],
        run_assertions=[
            Precision(over=AGREES, threshold=threshold, tolerance=0.0, by_group=True),
        ],
        cases=[
            Case(id=case, label=label, group=group)  # type: ignore[arg-type]
            for case, label, group in cases
        ],
    )


def ran(
    cases: Sequence[Marked],
    *,
    at: str = BASE_AT,
    wrong: frozenset[str] = frozenset(),
    threshold: str = "1/2",
) -> Run:
    """One run, where every case named in `wrong` disagrees with its mark.

    The per-case check answers "did the system agree with the human", so it
    passes on agreement whatever the mark was: a case in `wrong` fails, and the
    matrix turns that into a false negative on a positive case and a false
    positive on a negative one. That is `AgreesWithMark` in miniature.
    """

    def target(case: Case) -> Response:
        return Response(output="NO" if case.id in wrong else "YES")

    return execute(build(cases, threshold=threshold), target, created_at=at)


def run_scoped(result: Comparison) -> dict[str, str]:
    """Only the aggregates. The per-case deltas are a separate story and would
    otherwise drown these assertions — removing a group removes its cases too,
    and each of those is a `missing` of its own."""
    return {d.assertion: d.outcome for d in result.deltas if d.scope == "run"}


# --------------------------------------------------------------------------- #
# The grammar, read back
# --------------------------------------------------------------------------- #


def test_the_name_a_group_takes_reads_back_to_the_group() -> None:
    assert grouped_name("precision", "travel") == "precision[group=travel]"
    assert split_grouped_name("precision[group=travel]") == ("precision", "travel")
    assert split_grouped_name("precision") == ("precision", None)


def test_a_group_whose_name_ends_in_a_bracket_survives_the_round_trip() -> None:
    """The tail is taken to the *last* bracket. A cosmetic property — the parse
    orders columns and never decides identity — but a name that read back as a
    different group would put a column under the wrong heading."""
    assert split_grouped_name(grouped_name("precision", "odd]")) == (
        "precision",
        "odd]",
    )


def test_a_declared_aggregate_may_not_forge_the_expanded_form() -> None:
    """Two checks under one name is what identity exists to prevent, and the
    run grid would merge them into one column without a word (ADR 0010 §3)."""
    with pytest.raises(ValueError, match="which is the form an expanded"):
        Suite(
            tenant="acme",
            environment="staging",
            name="triage",
            assertions=[Contains(needle="YES", name=AGREES)],
            run_assertions=[
                Precision(
                    over=AGREES,
                    threshold="1/2",
                    tolerance=0.0,
                    name="precision[group=orders]",
                )
            ],
            cases=[Case(id="a", label="positive")],
        )


# --------------------------------------------------------------------------- #
# §2, §4, §6: the expansion is stable, and it moves no identity that existed
# --------------------------------------------------------------------------- #


SHAPES: list[tuple[str, list[Marked]]] = [
    ("declared in one order", [*ORDERS, *RETURNS, *REFUNDS]),
    ("declared in another", [*REFUNDS, *ORDERS, *RETURNS]),
    (
        "interleaved",
        [ORDERS[0], REFUNDS[0], RETURNS[0], ORDERS[1], REFUNDS[1], RETURNS[1]],
    ),
    (
        "some cases in no group",
        [*ORDERS, ("u1", "positive", None), ("u2", "negative", None)],
    ),
    ("one group only", list(ORDERS)),
]


@pytest.mark.parametrize("shape", [name for name, _ in SHAPES])
def test_the_expansion_is_the_same_every_time_it_is_built(shape: str) -> None:
    """Built twice from the same declaration, a suite must expand identically:
    same order, same names, same identities, same `config_hash`.

    A property rather than an example, over several shapes, because the
    expansion reads a *set* of groups off the cases — and a set has no order of
    its own. `Suite.groups()` sorts precisely so that nothing downstream is at
    the mercy of the order somebody happened to write their cases in: the
    fingerprint would churn between runs of one unchanged suite, and a
    committed baseline would stop matching itself.
    """
    cases = dict(SHAPES)[shape]
    first, second = build(cases), build(cases)
    assert [a.name for a in first.run_assertions] == [
        a.name for a in second.run_assertions
    ]
    assert [a.identity for a in first.run_assertions] == [
        a.identity for a in second.run_assertions
    ]
    assert first.config_hash() == second.config_hash()


def test_the_declaration_order_of_the_cases_does_not_reach_the_fingerprint() -> None:
    """The same cases in a different order are the same suite."""
    one, other = build(SHAPES[0][1]), build(SHAPES[1][1])
    assert one.groups() == other.groups()
    assert one.config_hash() == other.config_hash()


def test_the_expansion_names_the_whole_run_first_then_the_groups_sorted() -> None:
    """Asserted literally, because §3 makes these a public format: they land in
    `Run.aggregate[].assertion` in every run file this suite writes, and a
    change to the grammar is a diff of every artifact anyone kept."""
    suite = build([*REFUNDS, *ORDERS, *RETURNS])
    assert [a.name for a in suite.run_assertions] == [
        "precision",
        "precision[group=orders]",
        "precision[group=refunds]",
        "precision[group=returns]",
    ]


def test_two_aggregates_over_one_check_each_expand_into_their_own_family() -> None:
    """The expansion is per declared aggregate, so the families do not
    interleave and each keeps its whole-run instance at its head."""
    suite = Suite(
        tenant="acme",
        environment="staging",
        name="triage",
        assertions=[Contains(needle="YES", name=AGREES)],
        run_assertions=[
            Precision(over=AGREES, threshold="1/2", tolerance=0.0, by_group=True),
            Accuracy(over=AGREES, threshold="1/2", tolerance=0.0, by_group=True),
        ],
        cases=[
            Case(id=case, label=label, group=group)  # type: ignore[arg-type]
            for case, label, group in [*ORDERS, *REFUNDS]
        ],
    )
    assert [a.name for a in suite.run_assertions] == [
        "precision",
        "precision[group=orders]",
        "precision[group=refunds]",
        "accuracy",
        "accuracy[group=orders]",
        "accuracy[group=refunds]",
    ]


def test_the_whole_run_identity_is_the_one_it_had_before_groups_existed() -> None:
    """The pair that has to hold together, and the one this feature could most
    easily have broken silently.

    An aggregate's `identity` is what `compare()` pairs on, so a fingerprint
    that shifted here would unpair **every stored aggregate in the world** — a
    baseline promoted last month reporting `missing` with a `new` beside it,
    on a suite nobody touched. `by_group` and `group` are both excluded from
    the identity for that reason, and the literal below is the classifier's
    precision as it was before ADR 0010 was written.

    `config_hash` moving is the other half and is asserted with it, so neither
    can be satisfied by weakening the other: the suite *is* different once it
    declares ten more gates, and a baseline promoted before them is comparable
    but not promotable. (ADR 0010 §4, §11)
    """
    plain = Precision(over="agrees_with_mark", threshold="3/5", tolerance="3/20")
    flagged = Precision(
        over="agrees_with_mark", threshold="3/5", tolerance="3/20", by_group=True
    )
    assert plain.identity == "31e12a0068b3f1db"
    assert flagged.identity == "31e12a0068b3f1db"

    cases = [*ORDERS, *REFUNDS]
    without = Suite(
        tenant="acme",
        environment="staging",
        name="triage",
        assertions=[Contains(needle="YES", name=AGREES)],
        run_assertions=[Precision(over=AGREES, threshold="1/2", tolerance=0.0)],
        cases=[
            Case(id=case, label=label, group=group)  # type: ignore[arg-type]
            for case, label, group in cases
        ],
    )
    with_groups = build(cases)
    # Same check, still paired: the expansion added, it did not replace.
    assert without.run_assertions[0].identity == with_groups.run_assertions[0].identity
    # Different suite, so not promotable across: it now declares more gates.
    assert without.config_hash() != with_groups.config_hash()


def test_a_group_on_a_case_does_nothing_until_an_aggregate_asks() -> None:
    """§1's descriptive claim, as a fingerprint. A suite that never sets the
    flag is the suite it was, groups written on its cases or not."""
    labelled = Suite(
        tenant="acme",
        environment="staging",
        name="triage",
        assertions=[Contains(needle="YES", name=AGREES)],
        run_assertions=[Precision(over=AGREES, threshold="1/2", tolerance=0.0)],
        cases=[
            Case(id=case, label=label, group=group)  # type: ignore[arg-type]
            for case, label, group in ORDERS
        ],
    )
    bare = Suite(
        tenant="acme",
        environment="staging",
        name="triage",
        assertions=[Contains(needle="YES", name=AGREES)],
        run_assertions=[Precision(over=AGREES, threshold="1/2", tolerance=0.0)],
        cases=[
            Case(id=case, label=label)  # type: ignore[arg-type]
            for case, label, _group in ORDERS
        ],
    )
    assert labelled.config_hash() == bare.config_hash()
    assert [a.name for a in labelled.run_assertions] == ["precision"]


# --------------------------------------------------------------------------- #
# §9: a group arriving and leaving is the rule that was already there
# --------------------------------------------------------------------------- #


def test_a_group_that_appears_is_new_and_nothing_else() -> None:
    """A case carrying a group nobody had used adds gates. They are absent from
    the baseline, which is what `new` says — and no existing figure is
    disturbed by their arrival."""
    baseline = ran([*ORDERS, *RETURNS])
    run = ran([*ORDERS, *RETURNS, *REFUNDS], at=LATER_AT)

    result = compare(run, baseline)
    assert run_scoped(result) == {
        "precision": "unchanged",
        "precision[group=orders]": "unchanged",
        "precision[group=returns]": "unchanged",
        "precision[group=refunds]": "new",
    }
    assert not result.has_regressions


def test_a_group_that_vanishes_is_missing_and_leaves_the_rest_alone() -> None:
    """Remove the last case carrying a group and its aggregates stop being
    produced. Nothing is invented for the group that went, and the figures that
    remain are untouched."""
    baseline = ran([*ORDERS, *RETURNS, *REFUNDS])
    run = ran([*ORDERS, *RETURNS], at=LATER_AT)

    result = compare(run, baseline)
    gone = [d for d in result.deltas if d.outcome == "missing" and d.scope == "run"]
    assert [d.assertion for d in gone] == ["precision[group=refunds]"]
    # An aggregate belongs to no case, so it carries the empty `case_id` the
    # run scope has always carried — a group does not make it a case.
    assert gone[0].case_id == ""
    assert set(run_scoped(result).values()) == {"unchanged", "missing"}


def test_a_renamed_group_is_exactly_one_new_and_one_missing() -> None:
    """Nothing knows that `refunds` became `credits`, and guessing would be
    worse than reporting. It is the sentence a renamed case already gets."""
    baseline = ran([*ORDERS, *REFUNDS])
    renamed: list[Marked] = [
        (case, label, "credits" if group == "refunds" else group)
        for case, label, group in [*ORDERS, *REFUNDS]
    ]
    run = ran(renamed, at=LATER_AT)

    result = compare(run, baseline)
    moved = {
        outcome: assertion
        for assertion, outcome in run_scoped(result).items()
        if outcome in ("new", "missing")
    }
    assert moved == {
        "new": "precision[group=credits]",
        "missing": "precision[group=refunds]",
    }


def test_a_group_regresses_on_its_own_like_any_other_check() -> None:
    """The point of watching a class. `f2` is marked negative and is now kept,
    so the refunds matrix gains a false positive and its precision halves while
    the other two classes do not move at all."""
    cases = [*ORDERS, *RETURNS, *REFUNDS]
    result = compare(ran(cases, at=LATER_AT, wrong=frozenset({"f2"})), ran(cases))
    scoped = run_scoped(result)
    assert scoped["precision[group=refunds]"] == "regressed"
    assert scoped["precision[group=orders]"] == "unchanged"
    assert scoped["precision[group=returns]"] == "unchanged"


def test_diff_reads_groups_through_the_same_index_and_stays_symmetric() -> None:
    """`diff()` shares `index_verdicts` with `compare()` — ADR 0008 §5 — so it
    inherits the group keys whole, and ADR 0008 §2's symmetry promise has to
    hold over them like any other."""
    cases = [*ORDERS, *REFUNDS]
    left, right = ran(cases), ran(cases, at=LATER_AT, wrong=frozenset({"f2"}))

    forward, backward = diff(left, right), diff(right, left)
    differing = {c.assertion for c in forward.checks if c.differs}
    assert "precision[group=refunds]" in differing
    assert "precision[group=orders]" not in differing

    assert differing == {c.assertion for c in backward.checks if c.differs}
    assert forward.total == backward.total
    assert forward.favours_left == backward.favours_right
    assert forward.favours_right == backward.favours_left


def test_diff_refuses_two_runs_whose_group_sets_differ() -> None:
    """The one place §9's "nothing special-cased" does not reach, and it is
    correct rather than an oversight.

    A group set comes from the cases and the expansion turns it into gates, so
    changing it changes `config_hash` (ADR 0010 §4) — and ADR 0008 §3 refuses a
    diff across configurations before it reads a verdict, because the two runs
    were measured against different rulers. `compare()` is the instrument for
    that pair, and it reports `new` and `missing` as the tests above show.
    """
    with pytest.raises(DifferentSuitesError, match="different suites"):
        diff(ran([*ORDERS, *REFUNDS]), ran([*ORDERS, *RETURNS], at=LATER_AT))


# --------------------------------------------------------------------------- #
# §7: where the filter sits, and the test that fails if it moves
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class Agrees(AssertionBase):
    """`agrees_with_mark` in miniature, with one addition: an empty answer is
    `error` rather than a judgement, which is how a single sample of a single
    case comes to be unjudgeable while the others are fine."""

    name: str = AGREES
    threshold: float = 0.5
    tolerance: float = 0.0

    def __call__(self, inputs: EvaluatorInputs) -> Verdict:
        if inputs.output == "":
            return self._error("the target returned nothing to judge")
        return self._binary(inputs.output == "YES", f"said {inputs.output!r}")


def test_a_group_keeps_its_interval_when_a_case_outside_it_cannot_be_judged() -> None:
    """The test ADR 0010 §7 chose its filter placement for.

    `per_sample_outcomes` gives up unless every judged case in the list it is
    given carries the same number of samples — reading across lists of
    different lengths would align sample 2 of one case with sample 3 of another
    and call the result a measurement. So *which list it is given* decides what
    that condition is about.

    Here one sample of `out1` could not be judged, so `out1` carries two scores
    where every other case carries three. The whole-run aggregate therefore has
    no interval, correctly: it is not the same run three times. The **group**
    still does, because inside `alpha` nothing is ragged.

    Move the filter from `driver._outcomes` into the aggregate's `__call__` and
    this test fails: `with_noise_interval` would be handed all three cases,
    `per_sample_outcomes` would see two different counts, and one odd case
    outside the group would silence every group's interval at once.
    """
    calls: dict[str, int] = {}

    def target(case: Case) -> Response:
        seen = calls.get(case.id, 0)
        calls[case.id] = seen + 1
        if case.id == "out1" and seen == 0:
            return Response(output="")
        if case.id == "a2" and seen == 1:
            return Response(output="NO")
        return Response(output="YES")

    suite = Suite(
        tenant="acme",
        environment="staging",
        name="triage",
        assertions=[Agrees()],
        run_assertions=[
            Precision(over=AGREES, threshold="1/4", tolerance=0.0, by_group=True)
        ],
        cases=[
            Case(id="a1", label="positive", group="alpha"),
            Case(id="a2", label="negative", group="alpha"),
            Case(id="out1", label="positive"),
        ],
        samples=3,
        min_agreement="1/3",
    )
    run = execute(suite, target, created_at=BASE_AT)

    counted = {r.case_id: len(r.verdicts[0].score.samples) for r in run.results}
    assert counted == {"a1": 3, "a2": 3, "out1": 2}, counted

    by_name = {v.score.name: v for v in run.aggregate}
    # Ragged across the run: no interval, and that is the right answer.
    assert by_name["precision"].score.samples == ()
    # Not ragged inside the group: an interval, sized by the group's own wobble.
    scoped = by_name["precision[group=alpha]"].score
    assert len(scoped.samples) == 3
    assert (scoped.sample_min, scoped.sample_max) == (0.5, 1.0)


def test_a_group_aggregate_counts_only_its_own_cases() -> None:
    """The denominators, stated plainly: the matrix a group reports is built
    from that group's cases and no others."""
    run = ran([*ORDERS, *RETURNS, *REFUNDS])
    counted = {
        v.score.name: v.score.metadata["considered"]
        for v in run.aggregate
        if v.score.name.startswith("precision")
    }
    assert counted == {
        "precision": 6,
        "precision[group=orders]": 2,
        "precision[group=refunds]": 2,
        "precision[group=returns]": 2,
    }


# --------------------------------------------------------------------------- #
# §9: the grid
# --------------------------------------------------------------------------- #


def columns(html: str) -> list[str]:
    """The measure headings, in the order the table puts them."""
    head = html.split("<thead>")[1].split("</thead>")[0]
    cells = [c.split("</th>")[0] for c in head.split('<th class="num">')[1:]]
    return [c for c in cells if "precision" in c]


EXPECTED_COLUMNS = [
    "precision",
    "precision[group=orders]",
    "precision[group=refunds]",
    "precision[group=returns]",
]


def test_the_grid_puts_the_whole_run_figure_first_and_sorts_the_groups() -> None:
    """The figure that gates the release stays leftmost, where it was before
    groups existed; the classes follow it in an order a reader can rely on."""
    run = ran([*RETURNS, *ORDERS, *REFUNDS])
    html = runs_page(
        [("k1", run)],
        baseline_key=None,
        config_hash=run.config_hash,
        locale="en",
        suite="triage",
    )
    assert columns(html) == EXPECTED_COLUMNS


def test_a_group_only_an_older_run_carries_keeps_its_place() -> None:
    """The defect arrival order had, and the only one a reader cannot see: the
    columns rearranging themselves as runs come and go."""
    older = ran([*ORDERS, *REFUNDS])
    newer = ran([*ORDERS, *RETURNS], at=LATER_AT)
    html = runs_page(
        [("k1", older), ("k2", newer)],
        baseline_key=None,
        config_hash=newer.config_hash,
        locale="en",
        suite="triage",
    )
    # `refunds` is in neither the newest run nor last alphabetically, so under
    # arrival order it would have landed after `returns`.
    assert columns(html) == EXPECTED_COLUMNS
    # And the run that has no refunds says so with the absent marker rather
    # than borrowing the other run's figure.
    assert '<td class="num absent">—</td>' in html


# --------------------------------------------------------------------------- #
# §10: the combination the document has to explain
# --------------------------------------------------------------------------- #


def aggregates_section(document: str) -> str:
    return document.split('<section class="aggregates">')[1].split("</section>")[0]


def test_a_failing_group_beside_an_answer_of_no_is_explained() -> None:
    """The combination ADR 0010 §10 ships on purpose: a red row under a
    document that says nothing got worse. Both are true — the threshold says
    the system does not meet the bar, the comparison says it has not moved —
    and a reader who is not told reads the report as broken.

    Both locales, because the document has a recipient who did not choose
    English and the sentence is the whole point of the section.
    """
    cases = [*ORDERS, *REFUNDS]
    # Under a bar of 9/10, refunds sits at 0.5 in both runs. Nothing moved.
    baseline = ran(cases, wrong=frozenset({"f2"}), threshold="9/10")
    run = ran(cases, at=LATER_AT, wrong=frozenset({"f2"}), threshold="9/10")

    comparison = compare(run, baseline)
    scoped = next(v for v in run.aggregate if v.score.name.endswith("[group=refunds]"))
    assert scoped.status == "fail"

    for locale in LOCALES:
        head = headline(comparison, run, baseline, locale=locale)
        assert not head.worse
        section = aggregates_section(
            render_html(comparison, run, baseline, locale=locale)
        )
        assert '<p class="note">' in section, locale


def test_the_explanation_is_absent_when_something_really_did_get_worse() -> None:
    """It explains an answer of "no". With a regression the answer is "yes",
    the exit code is 1, and there is nothing left that wants explaining."""
    cases = [*ORDERS, *REFUNDS]
    baseline = ran(cases, threshold="9/10")
    run = ran(cases, at=LATER_AT, wrong=frozenset({"f2"}), threshold="9/10")

    comparison = compare(run, baseline)
    assert headline(comparison, run, baseline, locale="en").worse
    assert '<p class="note">' not in aggregates_section(
        render_html(comparison, run, baseline, locale="en")
    )
