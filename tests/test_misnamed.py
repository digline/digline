"""A verdict carries its assertion's name, or it is refused. (ADR 0027 §6,
amended 2026-09-28)

`Score.name` crosses verbatim into a redacted document, so a name an assertion
built from the answer carries the answer out past the redaction of the reason
beside it (ADR 0034 §7, route 4). The driver compares every raw verdict's name
with the name the assertion declared before the first case, and refuses the
mismatch: one errored verdict, marked `misnamed`, and not the whole case.

**Every test that says "refused" asserts the marker, not the status.** An
errored status is what an assertion that raised produces too, and telling the
two apart in a redacted document — where the reason is gone — is the whole
reason the marker exists. A test that asserted `status == "error"` would pass
on a verdict that errored for any other reason.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import ClassVar

import pytest

from digline.core import (
    DRIVER_MARKERS,
    MISNAMED,
    UNRECONCILED,
    AssertionBase,
    CaseResult,
    CheckKind,
    Contains,
    EvaluatorInputs,
    Run,
    Score,
    Verdict,
    compare,
    error_verdict,
    misnamed,
    misnamings,
    redact,
    run_from_json,
    run_to_json,
    unmarked,
    unreconciled,
)
from digline.host import REFUSALS
from digline.report import explain_text, facts, headline, render_run_html
from digline.run import Case, Response, Suite, execute, rejudge
from digline.store import FileResultStore
from digline.wire import EXIT_UNJUDGED, compare_json, exit_code, explain_json

CREATED = "2026-09-28T10:00:00+00:00"
#: The word the answer carries, and the one a misnamed verdict would carry out.
SECRET = "Rossi"


def answering(case: Case) -> Response:
    return Response(output=f"refund approved for {SECRET}")


@dataclass(frozen=True, slots=True)
class NamedByAnswer(AssertionBase):
    """What the protocol permits and the contract forbids: a verdict named from
    the answer. `redaction-probe`'s leg of the same name, as a fixture."""

    name: str = "named_by_answer"
    threshold: float = 0.5
    tolerance: float = 0.0

    def __call__(self, inputs: EvaluatorInputs) -> Verdict:
        word = str(inputs.output).split()[-1]
        return Verdict(
            score=Score(name=f"named_{word}", score=1.0, metadata={"word": word}),
            threshold=self.threshold,
            status="pass",
            reason=f"saw {word}",
            tolerance=self.tolerance,
            assertion_id=self.identity,
        )


@dataclass(frozen=True, slots=True)
class Raises(AssertionBase):
    """The error a refused name must not be mistaken for."""

    name: str = "raises"
    threshold: float = 0.5
    tolerance: float = 0.0

    def __call__(self, inputs: EvaluatorInputs) -> Verdict:
        raise RuntimeError("the instrument broke")


def run_of(*assertions: object, samples: int = 1, **suite_args: object) -> Run:
    suite = Suite(
        tenant="acme",
        environment="test",
        name="triage",
        samples=samples,
        assertions=list(assertions),  # type: ignore[arg-type]
        cases=[Case(id="c1")],
        **suite_args,  # type: ignore[arg-type]
    )
    return execute(suite, answering, created_at=CREATED)


def by_name(run: Run) -> dict[str, Verdict]:
    (case,) = run.results
    return {v.score.name: v for v in case.verdicts}


# --------------------------------------------------------------------------- #
# The comparison, pure
# --------------------------------------------------------------------------- #


def verdict_named(name: str) -> Verdict:
    return Verdict(
        score=Score(name=name, score=1.0),
        threshold=0.5,
        status="pass",
        reason="r",
        assertion_id="id",
    )


def test_a_verdict_named_after_its_assertion_is_not_a_misnaming() -> None:
    assert misnamings("agrees", [verdict_named("agrees")] * 3) == ()


def test_each_wrong_name_is_named_once_in_the_order_it_came() -> None:
    verdicts = [verdict_named(n) for n in ("agrees", "b", "a", "b", "agrees")]
    assert misnamings("agrees", verdicts) == ("b", "a")


# --------------------------------------------------------------------------- #
# The driver: one errored, marked verdict, and the case's others stand
# --------------------------------------------------------------------------- #


def test_the_refused_verdict_carries_the_declared_name_and_nothing_it_refused() -> None:
    run = run_of(NamedByAnswer(), Contains(needle="refund"))
    verdicts = by_name(run)
    assert set(verdicts) == {"named_by_answer", "contains"}
    refused = verdicts["named_by_answer"]
    assert refused.score.metadata == {MISNAMED: True}
    assert refused.score.score is None
    assert refused.assertion_id == NamedByAnswer().identity
    # The reason says what was refused; it is payload, and withheld below.
    assert f"named_{SECRET}" in refused.reason
    # One verdict, not the case.
    assert verdicts["contains"].status == "pass"
    assert misnamed(run) == (("c1", "named_by_answer"),)


def test_redacted_a_refused_name_is_told_apart_from_an_assertion_that_raised() -> None:
    """**The test the amendment exists for, and it fails on `main`.**

    Read off the redacted *document* — the JSON a boundary carries — rather
    than off `misnamed()`, so the failure on `main` is the defect itself and not
    a missing import: there, the answer's word crosses in the verdict's name,
    and nothing tells the two errors apart.
    """
    run = run_of(NamedByAnswer(), Raises())
    document = json.loads(run_to_json(redact(run), redacted=True))
    (case,) = document["results"]
    verdicts = {v["assertion"]: v for v in case["verdicts"]}

    assert SECRET not in json.dumps(document)
    assert set(verdicts) == {"named_by_answer", "raises"}
    # Both errored, which is exactly why the status cannot be what is asserted.
    assert verdicts["named_by_answer"]["status"] == "error"
    assert verdicts["raises"]["status"] == "error"
    assert verdicts["named_by_answer"]["metadata"] == {MISNAMED: True}
    assert verdicts["raises"]["metadata"] == {}


def test_the_marker_survives_redaction_and_the_round_trip() -> None:
    run = run_of(NamedByAnswer(), Raises())
    for reading in (
        redact(run),
        run_from_json(run_to_json(redact(run), redacted=True)),
        run_from_json(run_to_json(run)),
    ):
        assert misnamed(reading) == (("c1", "named_by_answer"),)


def test_a_misnamed_second_sample_is_not_out_voted_by_the_fold() -> None:
    """`combine_samples` takes the first verdict's name and drops the others',
    and under a `min_agreement` below 1 it carries a case past one bad sample.
    The check runs before the fold, so the second sample is seen."""

    @dataclass(frozen=True, slots=True)
    class SecondSample(AssertionBase):
        # A class-level counter, not a field: a field enters the identity.
        calls: ClassVar[list[int]] = []
        name: str = "second"
        threshold: float = 0.5
        tolerance: float = 0.0

        def __call__(self, inputs: EvaluatorInputs) -> Verdict:
            self.calls.append(1)
            name = self.name if len(self.calls) == 1 else f"second_{SECRET}"
            return Verdict(
                score=Score(name=name, score=1.0),
                threshold=self.threshold,
                status="pass",
                reason="r",
                tolerance=self.tolerance,
                assertion_id=self.identity,
            )

    run = run_of(SecondSample(), samples=2, min_agreement=0.5)
    assert misnamed(run) == (("c1", "second"),)
    assert SECRET not in json.dumps(json.loads(run_to_json(redact(run), redacted=True)))


def test_a_misnamed_second_judgement_is_not_absorbed_by_the_judge_fold() -> None:
    """`fold_judgements` counts an errored judgement without escalating it, so
    a refusal made per judgement would be out-voted. Refused before it."""

    @dataclass(frozen=True, slots=True)
    class SecondJudgement(AssertionBase):
        KIND: ClassVar[CheckKind] = "judged"
        calls: ClassVar[list[int]] = []
        name: str = "judged"
        threshold: float = 0.5
        tolerance: float = 0.0

        def __call__(self, inputs: EvaluatorInputs) -> Verdict:
            self.calls.append(1)
            name = self.name if len(self.calls) == 1 else f"judged_{SECRET}"
            return Verdict(
                score=Score(name=name, score=0.9),
                threshold=self.threshold,
                status="pass",
                reason="r",
                tolerance=self.tolerance,
                assertion_id=self.identity,
            )

    suite = Suite(
        tenant="acme",
        environment="test",
        name="triage",
        record_responses=True,
        assertions=[SecondJudgement()],
        cases=[Case(id="c1")],
    )
    source = execute(suite, answering, created_at=CREATED)
    assert misnamed(source) == ()
    # Judged twice on the replay, and only the second judgement is misnamed.
    SecondJudgement.calls.clear()
    replay = rejudge(suite, source, key="k", created_at=CREATED, judge_samples=2)
    assert len(SecondJudgement.calls) == 2
    assert misnamed(replay) == (("c1", "judged"),)


def test_an_assertion_that_renames_itself_is_held_to_the_name_it_declared() -> None:
    """A live read of `assertion.name` would agree with an assertion that set
    its name from the answer; the name captured before the first case does not.

    **Two cases, and the second is the one that matters.** A live read taken
    before the call still sees the old name on the first case, so with one
    case this passed with the capture removed — measured, 2026-09-28.
    """

    class Renaming:
        threshold = 0.5
        tolerance = 0.0
        identity = "renaming01"
        accepts = frozenset({"text"})

        def __init__(self) -> None:
            self.name = "renaming"

        def __call__(self, inputs: EvaluatorInputs) -> Verdict:
            self.name = f"renaming_{str(inputs.output).split()[-1]}"
            return Verdict(
                score=Score(name=self.name, score=1.0),
                threshold=self.threshold,
                status="pass",
                reason="r",
                assertion_id=self.identity,
            )

    suite = Suite(
        tenant="acme",
        environment="test",
        name="triage",
        assertions=[Renaming()],  # type: ignore[list-item]
        cases=[Case(id="c1"), Case(id="c2")],
    )
    run = execute(suite, answering, created_at=CREATED)
    assert misnamed(run) == (("c1", "renaming"), ("c2", "renaming"))


def test_a_suite_of_shipped_assertions_refuses_nothing() -> None:
    run = run_of(Contains(needle="refund"))
    assert misnamed(run) == ()
    assert all(v.status == "pass" for v in by_name(run).values())


def test_the_marker_counts_only_on_an_errored_verdict_and_only_as_true() -> None:
    def with_marker(status: str, value: object) -> Run:
        run = run_of(Contains(needle="refund"))
        (case,) = run.results
        (v,) = case.verdicts
        forged = Verdict(
            score=Score(
                name=v.score.name,
                score=None if status == "error" else 1.0,
                metadata={MISNAMED: value},
            ),
            threshold=v.threshold,
            status=status,  # type: ignore[arg-type]
            reason="r",
            assertion_id=v.assertion_id,
        )
        return replace(run, results=(CaseResult("c1", (forged,)),))

    assert misnamed(with_marker("pass", True)) == ()
    assert misnamed(with_marker("error", 1)) == ()
    assert misnamed(with_marker("error", True)) == (("c1", "contains"),)


# --------------------------------------------------------------------------- #
# The reading: §7's cost a second time
# --------------------------------------------------------------------------- #


def test_the_headline_says_why_directly_before_the_unjudged_clause() -> None:
    run = redact(run_of(NamedByAnswer(), Contains(needle="refund")))
    head = headline(compare(run, run), run, run, locale="en", declared=None)
    clause = (
        "1 check returned a verdict under a name that is not its assertion's, "
        "and it was refused: c1 · named_by_answer. The assertion is at fault, "
        "not the system under test."
    )
    assert clause in head.sentence
    assert head.sentence.index(clause) < head.sentence.index("could not be judged")
    assert head.misnamed == 1
    assert exit_code(head) == EXIT_UNJUDGED
    payload = compare_json(compare(run, run), head, baseline=run, full=False)
    assert payload["misnamed"] == 1


def test_the_italian_clause() -> None:
    run = run_of(NamedByAnswer())
    head = headline(compare(run, run), run, run, locale="it", declared=None)
    assert (
        "1 controllo ha restituito un verdetto con un nome che non è quello della "
        "sua asserzione, ed è stato rifiutato: c1 · named_by_answer."
    ) in head.sentence


def test_a_run_that_refused_nothing_reads_as_it_always_did() -> None:
    run = run_of(Raises())
    head = headline(compare(run, run), run, run, locale="en", declared=None)
    assert head.misnamed == 0
    assert "under a name" not in head.sentence
    assert all(fact.kind != "misnamed" for fact in facts(run) if hasattr(fact, "kind"))


def test_the_reading_and_the_single_run_document_say_it_too() -> None:
    run = redact(run_of(NamedByAnswer(), Raises()))
    for reading in (facts(run), facts(run, compare(run, run))):
        kinds = [getattr(fact, "kind", None) for fact in reading]
        assert kinds.index("misnamed") == kinds.index("unjudged") - 1
        assert any(
            line.startswith("1 check returned a verdict under a name")
            for line in explain_text(reading, locale="en")
        )
    wire = explain_json(facts(run), scope="run", exit_code=2)
    assert {
        "about": "run",
        "kind": "misnamed",
        "count": 1,
        "state": None,
    } in wire["facts"]  # type: ignore[operator]
    assert "under a name that is not its assertion" in render_run_html(run, locale="en")


def test_it_can_never_be_promoted(tmp_path: Path) -> None:
    suite = Suite(
        tenant="acme",
        environment="test",
        name="triage",
        assertions=[NamedByAnswer()],
        cases=[Case(id="c1")],
    )
    run = execute(suite, answering, created_at=CREATED)
    store = FileResultStore(tmp_path)
    ref = store.write_run(run)
    # Refused, and by name. Which refusal is not this test's argument: its one
    # case errored, so the run also judged nothing, and that comes first.
    # (ADR 0049 §5)
    with pytest.raises(REFUSALS, match="c1"):
        store.promote_baseline(
            ref,
            suite.config_hash(),
            expected_baseline=None,
            promoted_at="2026-09-28T11:00:00+00:00",
            declared=None,
        )


# --------------------------------------------------------------------------- #
# The markers are the driver's to write: D-1 of the delta-pass over 0.22.0
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class ClaimsAMarker(AssertionBase):
    """Declines to score under its own name, and writes one of the driver's
    markers beside a key of its own. Nothing was misnamed and nothing went
    unanswered: the marker is a claim about what the driver did, made by the
    assertion the driver is checking."""

    marker: str = MISNAMED
    name: str = "claims_a_marker"
    threshold: float = 0.5
    tolerance: float = 0.0

    def __call__(self, inputs: EvaluatorInputs) -> Verdict:
        forged = error_verdict(self, "an ordinary failure")
        return replace(
            forged,
            score=replace(forged.score, metadata={self.marker: True, "measured": 3}),
        )


def test_an_assertion_cannot_claim_it_was_refused_for_its_name() -> None:
    """On 0.22.0 the headline said this check "returned a verdict under a name
    that is not its assertion's" and blamed the assertion for a misnaming that
    never happened."""
    run = run_of(ClaimsAMarker(marker=MISNAMED))
    (verdict,) = by_name(run).values()
    assert misnamed(run) == ()
    assert MISNAMED not in verdict.score.metadata
    assert verdict.score.metadata["measured"] == 3
    assert verdict.status == "error"
    head = headline(compare(run, run), run, run, locale="en", declared=None)
    assert head.misnamed == 0
    assert "under a name that is not" not in head.sentence


def test_an_assertion_cannot_claim_a_gap() -> None:
    """The same repair for `unreconciled`, joined on reading its code: a forged
    gap sends a reader looking for a defect in the driver's bookkeeping."""
    run = run_of(ClaimsAMarker(marker=UNRECONCILED))
    (verdict,) = by_name(run).values()
    assert unreconciled(run) == ()
    assert UNRECONCILED not in verdict.score.metadata
    assert verdict.score.metadata["measured"] == 3


def test_the_driver_still_writes_its_own_marker() -> None:
    """The removal happens before the driver builds its verdict, never after:
    a genuine misnaming is still marked."""
    run = run_of(NamedByAnswer())
    assert misnamed(run) == (("c1", "named_by_answer"),)


def test_unmarked_leaves_a_verdict_without_markers_as_it_was() -> None:
    plain = verdict_named("contains")
    assert unmarked(plain) is plain
    marked = replace(
        plain, score=replace(plain.score, metadata={MISNAMED: True, "n": 1})
    )
    assert unmarked(marked).score.metadata == {"n": 1}
    assert frozenset({MISNAMED, UNRECONCILED}) == DRIVER_MARKERS
