"""A run that judged nothing does not pass, and is never promotable. (ADR 0049)

Written from the record's test plan, item by item, and from the mistake each
item prevents: a run of suspensions exiting `0`, a judged canary turning a
subject suite green, a front end that reads the run where the suite's
declaration decides, and a promotion that makes a reference out of nothing.

Every exit code here is asked of both paths a front end has: `run_exit_code`
for a first round, and `exit_code` of a headline against a good reference for
a later one. A rule that held on one path only is the defect *Requires* names.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from digline.core import (
    CalibrationBand,
    CaseResult,
    Contains,
    Declared,
    Run,
    Score,
    Verdict,
    compare,
    key_of,
)
from digline.host import REFUSALS, entry_for, explained, promote_priced
from digline.report import headline
from digline.report.text import LOCALES, Locale, phrase
from digline.run import Case, Suite
from digline.store import (
    FileResultStore,
    NothingJudgedError,
    refusals_for,
)
from digline.wire import (
    EXIT_OK,
    EXIT_UNJUDGED,
    compare_json,
    exit_code,
    run_exit_code,
)
from digline.wire.contract import _ADDED  # pyright: ignore[reportPrivateUsage]

CFG = "hash-a"
EARLIER = "2026-01-01T10:00:00+00:00"
CREATED = "2026-01-02T10:00:00+00:00"
RECORDED = "2026-01-03T10:00:00+00:00"

#: A suite that measures a subject, beside a canary and a calibration case.
SUBJECT = Declared(
    subject=frozenset({"s1", "s2"}), watching=frozenset({"probe", "cal"})
)
#: A suite of canaries only: what it measures is whether the model is that model.
CANARIES_ONLY = Declared(subject=frozenset(), watching=frozenset({"probe"}))


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


def verdict(
    status: str = "pass",
    *,
    name: str = "contains",
    score: float | None = 1.0,
    assertion_id: str = "contains-1",
    threshold: float = 1.0,
) -> Verdict:
    return Verdict(
        score=Score(name=name, score=score if status != "error" else None),
        threshold=threshold,
        tolerance=0.0,
        status=status,  # type: ignore[arg-type]
        reason="judged",
        assertion_id=assertion_id,
    )


def subject(case_id: str, status: str = "pass") -> CaseResult:
    return CaseResult(case_id, (verdict(status),))


def suspended(case_id: str, *, canary: bool = False) -> CaseResult:
    return CaseResult(case_id, suspended="parked", canary=canary)


def canary(case_id: str = "probe") -> CaseResult:
    return CaseResult(case_id, (verdict(),), canary=True)


def calibration(case_id: str = "cal") -> CaseResult:
    """A calibration case inside its band: judged, and its scale held."""
    return CaseResult(
        case_id,
        (verdict(name="score", score=0.5, assertion_id="score-1", threshold=0.0),),
        calibration=CalibrationBand(
            assertion_id="score-1", check="score", low=0.3, high=0.7
        ),
    )


def errored_aggregate() -> Verdict:
    """An aggregate over an empty denominator: `error`, never `1.0`."""
    return verdict("error", name="accuracy", assertion_id="accuracy-1")


def run(
    *results: CaseResult,
    aggregate: tuple[Verdict, ...] = (),
    created_at: str = CREATED,
    config_hash: str = CFG,
) -> Run:
    return Run(
        tenant="acme",
        environment="test",
        suite="qa",
        config_hash=config_hash,
        created_at=created_at,
        results=results,
        aggregate=aggregate,
    )


#: A good reference: both subject cases judged, nothing errored.
GOOD = run(subject("s1"), subject("s2"), created_at=EARLIER)


def first_round(document: Run, declared: Declared | None) -> int:
    return run_exit_code(document, declared=declared)


def later_round(document: Run, declared: Declared | None) -> int:
    head = headline(
        compare(document, GOOD), document, GOOD, locale="en", declared=declared
    )
    return exit_code(head)


ROUNDS = {"first round": first_round, "later round": later_round}


# --------------------------------------------------------------------------- #
# 1. Every case suspended exits 2 (§3)
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("declared", [SUBJECT, None], ids=["declared", "no suite"])
@pytest.mark.parametrize("round_", list(ROUNDS))
def test_every_case_suspended_stops(round_: str, declared: Declared | None) -> None:
    document = run(suspended("s1"), suspended("s2"))
    assert ROUNDS[round_](document, declared) == EXIT_UNJUDGED


@pytest.mark.parametrize("round_", list(ROUNDS))
def test_one_judged_subject_case_beside_suspensions_proceeds(round_: str) -> None:
    """The control, and §6's first level: one suspension among judged cases
    moves nothing."""
    document = run(subject("s1"), suspended("s2"))
    assert ROUNDS[round_](document, SUBJECT) == EXIT_OK


# --------------------------------------------------------------------------- #
# 2. A document with no cases exits 2 (§3)
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("declared", [SUBJECT, None], ids=["declared", "no suite"])
@pytest.mark.parametrize("round_", list(ROUNDS))
def test_a_document_with_no_cases_stops(round_: str, declared: Declared | None) -> None:
    assert ROUNDS[round_](run(), declared) == EXIT_UNJUDGED


# --------------------------------------------------------------------------- #
# 3. Canary and calibration do not count beside subject cases (§3)
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "watcher", [canary(), calibration()], ids=["canary", "calibration in band"]
)
@pytest.mark.parametrize("declared", [SUBJECT, None], ids=["declared", "no suite"])
@pytest.mark.parametrize("round_", list(ROUNDS))
def test_a_judged_watcher_beside_suspended_subject_cases_stops(
    round_: str, declared: Declared | None, watcher: CaseResult
) -> None:
    """With no suite the run itself carries subject cases, so the third clause
    reaches the same answer as the first."""
    document = run(suspended("s1"), suspended("s2"), watcher)
    assert ROUNDS[round_](document, declared) == EXIT_UNJUDGED


# --------------------------------------------------------------------------- #
# 4. A suite of canaries only (§3)
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "declared", [CANARIES_ONLY, None], ids=["declared", "no suite"]
)
@pytest.mark.parametrize("round_", list(ROUNDS))
def test_a_suite_of_canaries_only_is_judged_by_them(
    round_: str, declared: Declared | None
) -> None:
    assert ROUNDS[round_](run(canary()), declared) == EXIT_OK


@pytest.mark.parametrize(
    "declared", [CANARIES_ONLY, None], ids=["declared", "no suite"]
)
@pytest.mark.parametrize("round_", list(ROUNDS))
def test_a_suite_of_canaries_only_with_its_canary_suspended_stops(
    round_: str, declared: Declared | None
) -> None:
    assert ROUNDS[round_](run(suspended("probe", canary=True)), declared) == (
        EXIT_UNJUDGED
    )


# --------------------------------------------------------------------------- #
# 5 and 6. The declaration decides, not the run, on both paths (§3, Requires)
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("round_", list(ROUNDS))
def test_a_judged_canary_does_not_turn_a_subject_suite_green(round_: str) -> None:
    """The suite declares subject cases and the run carries none of them: it
    still counts them, and judged none. Item 5 is the later round, item 6 the
    first."""
    assert ROUNDS[round_](run(canary()), SUBJECT) == EXIT_UNJUDGED


@pytest.mark.parametrize("round_", list(ROUNDS))
def test_with_no_suite_the_same_run_is_judged_by_its_canary(round_: str) -> None:
    """The counterpart: without a declaration the third clause reads the
    document, whose only case is a judged canary. So the `2` above is the
    declaration's doing, and a path that dropped it would answer this."""
    assert ROUNDS[round_](run(canary()), None) == EXIT_OK


# --------------------------------------------------------------------------- #
# Drift: a result the suite no longer declares (maintainer, 2026-10-14)
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("round_", list(ROUNDS))
def test_a_result_in_neither_declared_set_does_not_count(round_: str) -> None:
    """A case removed from the suite, still in an old run. Under the first
    clause only the declared subject cases count, and `old` is not one."""
    document = run(subject("old"), suspended("s1"))
    assert ROUNDS[round_](document, SUBJECT) == EXIT_UNJUDGED


@pytest.mark.parametrize("round_", list(ROUNDS))
def test_with_no_suite_the_undeclared_result_counts(round_: str) -> None:
    """The counterpart: with no declaration, `old` is a subject case of the
    document, and it was judged."""
    document = run(subject("old"), suspended("s1"))
    assert ROUNDS[round_](document, None) == EXIT_OK


# --------------------------------------------------------------------------- #
# 7. An aggregate does not count (§3)
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "aggregate", [(errored_aggregate(),), ()], ids=["aggregate", "no aggregate"]
)
@pytest.mark.parametrize("round_", list(ROUNDS))
def test_every_case_suspended_stops_with_or_without_an_aggregate(
    round_: str, aggregate: tuple[Verdict, ...]
) -> None:
    document = run(suspended("s1"), suspended("s2"), aggregate=aggregate)
    assert ROUNDS[round_](document, SUBJECT) == EXIT_UNJUDGED


# --------------------------------------------------------------------------- #
# 8. Something judged and an aggregate in error exits 0 (§2)
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("round_", list(ROUNDS))
def test_something_judged_beside_an_errored_aggregate_proceeds(round_: str) -> None:
    """ADR 0010 §8, where it holds."""
    document = run(subject("s1"), suspended("s2"), aggregate=(errored_aggregate(),))
    assert ROUNDS[round_](document, SUBJECT) == EXIT_OK


@pytest.mark.parametrize("round_", list(ROUNDS))
def test_an_errored_case_still_stops(round_: str) -> None:
    """§2 does not make an errored case pass."""
    document = run(subject("s1"), subject("s2", "error"))
    assert ROUNDS[round_](document, SUBJECT) == EXIT_UNJUDGED


# --------------------------------------------------------------------------- #
# 9. The tenth condition (§5)
# --------------------------------------------------------------------------- #


def refused_types(document: Run, declared: Declared | None) -> list[type[Exception]]:
    return [type(r) for r in refusals_for(document, CFG, declared=declared)]


@pytest.mark.parametrize(
    "aggregate", [(errored_aggregate(),), ()], ids=["aggregate", "no aggregate"]
)
def test_a_run_that_judged_nothing_is_refused(aggregate: tuple[Verdict, ...]) -> None:
    """With an aggregate or without one: #375's asymmetry is gone."""
    document = run(suspended("s1"), suspended("s2"), aggregate=aggregate)
    assert NothingJudgedError in refused_types(document, SUBJECT)


def test_the_cause_is_refused_before_the_symptom(tmp_path: Path) -> None:
    """Every case suspended, and an aggregate in error because of it: the
    person promoting reads that nothing was judged, not that a figure could
    not be computed, and the refusal names the cases. Cause before symptom is
    the class of defect ADR 0049 closes. (Maintainer, 2026-10-14)"""
    document = run(suspended("s1"), suspended("s2"), aggregate=(errored_aggregate(),))
    first, *_ = refusals_for(document, CFG, declared=SUBJECT)
    assert isinstance(first, NothingJudgedError)
    assert "s1" in str(first) and "s2" in str(first)

    store = FileResultStore(tmp_path)
    ref = store.write_run(document)
    with pytest.raises(NothingJudgedError, match="s1"):
        store.promote_baseline(
            ref, CFG, expected_baseline=None, declared=SUBJECT, promoted_at=RECORDED
        )


def test_the_refusal_names_a_declared_case_the_run_does_not_carry() -> None:
    """Absent is one of the three ways a case went unjudged, and a name the
    person can look for is what the refusal owes them."""
    (refusal,) = refusals_for(run(canary()), CFG, declared=SUBJECT)
    assert "s1" in str(refusal) and "s2" in str(refusal)


def test_the_refusal_says_which_state_each_case_is_in() -> None:
    """Suspended, could not be judged, absent: each case named with its state,
    and the errored one with condition 3's remedy. A run whose every case
    errored is refused here first, so this message has to send its reader to
    the case, not to a general fact about the run. (Maintainer, 2026-10-14)"""
    declared = Declared(subject=frozenset({"s1", "s2", "s3"}), watching=frozenset())
    document = run(suspended("s1"), subject("s2", "error"))
    first, *_ = refusals_for(document, CFG, declared=declared)
    assert isinstance(first, NothingJudgedError)
    text = str(first)
    assert "s1 (suspended)" in text
    assert "s2 (could not be judged)" in text
    assert "s3 (absent)" in text
    assert "fix the case or remove it from the suite" in text.lower()


def test_a_run_with_one_judged_subject_case_is_not_refused() -> None:
    assert (
        refusals_for(run(subject("s1"), suspended("s2")), CFG, declared=SUBJECT) == ()
    )


def test_the_refusal_is_a_refusal() -> None:
    assert NothingJudgedError in REFUSALS


def test_the_declaration_reaches_the_promotion() -> None:
    """A suite that declares subject cases, a run that carries only a judged
    canary: refused."""
    assert NothingJudgedError in refused_types(run(canary()), SUBJECT)


def test_without_the_declaration_the_promotion_reads_the_document() -> None:
    """The counterpart: the third clause, a judged canary, nothing refused."""
    assert refusals_for(run(canary()), CFG, declared=None) == ()


def test_the_store_refuses_it_and_writes_nothing(tmp_path: Path) -> None:
    store = FileResultStore(tmp_path)
    ref = store.write_run(run(suspended("s1"), suspended("s2")))
    with pytest.raises(NothingJudgedError):
        store.promote_baseline(
            ref, CFG, expected_baseline=None, declared=SUBJECT, promoted_at=RECORDED
        )
    assert store.read_baseline("acme", "qa") is None


# --------------------------------------------------------------------------- #
# The front ends hand over the suite's declaration (Requires)
# --------------------------------------------------------------------------- #


def a_suite() -> Suite:
    """Declares one subject case and one canary."""
    return Suite(
        tenant="acme",
        environment="test",
        name="qa",
        assertions=[Contains(needle="Rome")],
        cases=[Case(id="s1"), Case(id="probe", canary=True)],
        samples=2,
        min_agreement="2/2",
    )


def test_a_suite_declares_its_cases_by_kind() -> None:
    assert a_suite().declared() == Declared(
        subject=frozenset({"s1"}), watching=frozenset({"probe"})
    )


def test_explain_on_a_first_round_hands_over_the_declaration(tmp_path: Path) -> None:
    store = FileResultStore(tmp_path)
    document = run(canary())
    store.write_run(document)
    key = key_of(document.created_at, document.config_hash)
    assert explained(store, a_suite(), key).exit_code == EXIT_UNJUDGED


def test_explain_against_a_reference_hands_over_the_declaration(
    tmp_path: Path,
) -> None:
    suite = a_suite()
    store = FileResultStore(tmp_path)
    reference = run(subject("s1"), canary(), created_at=EARLIER)
    store.promote_baseline(
        store.write_run(reference),
        CFG,
        expected_baseline=None,
        declared=suite.declared(),
        promoted_at=RECORDED,
    )
    document = run(canary())
    store.write_run(document)
    key = key_of(document.created_at, document.config_hash)
    assert explained(store, suite, key).exit_code == EXIT_UNJUDGED


def test_promote_hands_over_the_declaration(tmp_path: Path) -> None:
    suite = a_suite()
    store = FileResultStore(tmp_path)
    document = run(canary(), config_hash=suite.config_hash(pricing=""))
    store.write_run(document)
    with pytest.raises(NothingJudgedError):
        promote_priced(
            store,
            suite,
            "",
            key_of(document.created_at, document.config_hash),
            replacing="none",
            promoted_at=RECORDED,
        )


# --------------------------------------------------------------------------- #
# 10. The headline and the wire (§4)
# --------------------------------------------------------------------------- #


NOTHING = run(suspended("s1"), suspended("s2"))
SOMETHING = run(subject("s1"), suspended("s2"))


@pytest.mark.parametrize(
    ("document", "expected"),
    [(NOTHING, True), (SOMETHING, False)],
    ids=["true", "false"],
)
def test_the_headline_and_the_wire_carry_the_fact(
    document: Run, expected: bool
) -> None:
    comparison = compare(document, GOOD)
    head = headline(comparison, document, GOOD, locale="en", declared=SUBJECT)
    assert head.nothing_judged is expected
    wire = compare_json(comparison, head, baseline=GOOD, full=False, run=document)
    assert wire["nothing_judged"] is expected


def test_the_key_is_recorded_as_added() -> None:
    assert {(a.shape, a.key) for a in _ADDED} >= {
        ("compare", "nothing_judged"),
        ("compare.full", "nothing_judged"),
    }


@pytest.mark.parametrize("locale", LOCALES)
def test_the_headline_says_it_in_every_locale(locale: Locale) -> None:
    head = headline(
        compare(NOTHING, GOOD), NOTHING, GOOD, locale=locale, declared=SUBJECT
    )
    assert phrase(locale, "fact.nothing_judged") in head.sentence


# --------------------------------------------------------------------------- #
# 11. The register (§4)
# --------------------------------------------------------------------------- #


def registered(tmp_path: Path) -> FileResultStore:
    store = FileResultStore(tmp_path)
    entry = entry_for(
        NOTHING,
        key_of(NOTHING.created_at, NOTHING.config_hash),
        GOOD,
        key_of(GOOD.created_at, GOOD.config_hash),
        disposition="accepted",
        recorded_at=RECORDED,
        digline_version="0.0.0",
        declared=SUBJECT,
    )
    store.append_register("acme", "qa", entry)
    return store


def test_a_written_line_carries_the_fact(tmp_path: Path) -> None:
    store = registered(tmp_path)
    (line,) = store.register_path("acme", "qa").read_text().splitlines()
    assert json.loads(line)["outcome"]["nothing_judged"] is True
    (entry,) = store.read_register("acme", "qa").entries
    assert entry.outcome.nothing_judged is True


def test_a_line_without_the_key_reads_as_not_declared(tmp_path: Path) -> None:
    """Absent is not `false`: a line written before ADR 0049 does not say that
    something was judged."""
    store = registered(tmp_path)
    path = store.register_path("acme", "qa")
    (line,) = path.read_text().splitlines()
    document = json.loads(line)
    document["outcome"].pop("nothing_judged", None)
    path.write_text(json.dumps(document) + "\n")
    (entry,) = store.read_register("acme", "qa").entries
    assert entry.outcome.nothing_judged is None


# --------------------------------------------------------------------------- #
# 12. The invariant: both paths, the same declaration, the same code
# --------------------------------------------------------------------------- #


FIXTURES: dict[str, tuple[Run, Declared | None]] = {
    "every case suspended": (NOTHING, SUBJECT),
    "every case suspended, no suite": (NOTHING, None),
    "no cases": (run(), SUBJECT),
    "no cases, no suite": (run(), None),
    "suspended beside a canary": (run(suspended("s1"), canary()), SUBJECT),
    "suspended beside calibration": (run(suspended("s1"), calibration()), SUBJECT),
    "canaries only": (run(canary()), CANARIES_ONLY),
    "canary suspended": (run(suspended("probe", canary=True)), CANARIES_ONLY),
    "only a canary, subject declared": (run(canary()), SUBJECT),
    "only a canary, no suite": (run(canary()), None),
    "drifted result": (run(subject("old"), suspended("s1")), SUBJECT),
    "errored aggregate, all suspended": (
        run(suspended("s1"), aggregate=(errored_aggregate(),)),
        SUBJECT,
    ),
    "errored aggregate, one judged": (
        run(subject("s1"), aggregate=(errored_aggregate(),)),
        SUBJECT,
    ),
    "errored case": (run(subject("s1"), subject("s2", "error")), SUBJECT),
    "one judged": (SOMETHING, SUBJECT),
}


@pytest.mark.parametrize("name", list(FIXTURES))
def test_both_paths_agree_given_the_same_declaration(name: str) -> None:
    document, declared = FIXTURES[name]
    head = headline(
        compare(document, document), document, document, locale="en", declared=declared
    )
    assert run_exit_code(document, declared=declared) == exit_code(head)


def test_the_fixtures_are_not_all_one_answer() -> None:
    """The invariant above holds vacuously if every fixture exits the same, so
    the table must reach both codes."""
    codes = {
        run_exit_code(document, declared=declared)
        for document, declared in FIXTURES.values()
    }
    assert codes == {EXIT_OK, EXIT_UNJUDGED}
