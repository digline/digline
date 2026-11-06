"""A reviewed answer, run: the judge against a person. (ADR 0059 §1)

What is held here:

- the target is never called, and only the check the answer names runs on it,
  on the recorded answer and its input; the case records what the person said
  beside the verdict, bound by identity;
- a judge that agrees with the person passes the gate, and one that
  contradicts the person fails it, exit `1`, in either direction, from the run
  alone and against a reference; an errored verdict is unjudged, `2`, and
  never a contradiction;
- the case is out of every aggregate, counted as `reviewed_excluded`, needs no
  label, and is no subject case;
- the run document writes `reviewed` on that case alone and reads it back,
  refusing what no writer writes, and a run refuses one that binds no verdict;
- a projection mints the check as `calibration_check`, and the wire carries
  the check and the person's yes or no;
- a comparison keeps the case's delta and counts it nowhere; the headline
  counts the two directions, says them in a sentence, and the report shows a
  section beside the calibration one; `explain` tallies them, and `shape` and
  `log` read the case as a case of its own kind;
- a replay re-judges it from the declaration, and the plan announces its
  judge calls;
- `digline run` judges it without calling the target and exits by it.
"""

from __future__ import annotations

import dataclasses
import json
import secrets
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest
from tests._helpers import cli

from digline.core import (
    Accuracy,
    CaseOutcome,
    CaseResult,
    Contains,
    JudgeReply,
    LlmRubric,
    Reviewed,
    Run,
    Score,
    Verdict,
    compare,
    contradicted,
    nothing_judged,
    run_from_json,
    run_to_json,
)
from digline.core.aggregate import per_sample_outcomes
from digline.core.projection import project_served
from digline.core.run import run_from_dict
from digline.core.tokens import TokenKind
from digline.report.explain import TallyFact, explain_text, facts
from digline.report.log import _population  # pyright: ignore[reportPrivateUsage]
from digline.report.render import headline, render_run_html, reviewed_section
from digline.report.shape import shape
from digline.run import Case, Response, ReviewedAnswer, Suite, execute
from digline.run.replay import Replay
from digline.run.suite import planned_calls
from digline.store import ContradictedRunError, refusals_for
from digline.wire import (
    EXIT_OK,
    EXIT_UNJUDGED,
    EXIT_USAGE,
    EXIT_WORSE,
    exit_code,
    explain_json,
    run_exit_code,
)
from digline.wire.compare import compare_json
from digline.wire.run import run_document

CREATED = "2026-01-01T00:00:00+00:00"
QUESTION = "How long does a refund take?"
#: What the judge scores: an answer with the word in it passes, any other fails.
GOOD = "Refunds take 14 days. (judged right)"
BAD = "Refunds take a year."


def judge(prompt: str) -> JudgeReply:
    return JudgeReply(score=1.0 if "judged right" in prompt else 0.0, reason="r")


def broken(prompt: str) -> JudgeReply:
    raise RuntimeError("the judge is down")


def rubric(scorer: Any = judge) -> LlmRubric:
    return LlmRubric(rubric="is it right?", judge=scorer, threshold=0.7, tolerance=0.05)


def reviewed(case_id: str, output: str, *, good: bool) -> Case:
    return Case(
        id=case_id,
        reviewed_answer=ReviewedAnswer(
            output=output, check="llm_rubric", good=good, input=QUESTION
        ),
    )


def suite(*cases: Case, scorer: Any = judge, **changes: Any) -> Suite:
    fields: dict[str, Any] = {
        "tenant": "acme",
        "environment": "dev",
        "name": "support",
        "assertions": [rubric(scorer), Contains(needle="days")],
        "cases": [Case(id="by-hand"), *cases],
        "samples": 2,
        "min_agreement": "2/2",
    }
    fields.update(changes)
    return Suite(**fields)


def target(case: Case) -> Response:
    if case.reviewed_answer is not None:
        raise AssertionError("the target was called for a reviewed answer")
    return Response(output=GOOD, input=QUESTION)


def run(*cases: Case, **changes: Any) -> Run:
    return execute(suite(*cases, **changes), target, created_at=CREATED)


def result(found: Run, case_id: str) -> CaseResult:
    return next(r for r in found.results if r.case_id == case_id)


AGREES = (
    reviewed("yes-good", GOOD, good=True),
    reviewed("no-bad", BAD, good=False),
)


# -- the case ------------------------------------------------------------------- #


def test_only_the_named_check_runs_and_the_target_is_never_called() -> None:
    found = run(*AGREES)
    checked = suite(*AGREES)
    identity = checked.assertions[0].identity
    for case_id, good in (("yes-good", True), ("no-bad", False)):
        case = result(found, case_id)
        assert [v.assertion_id for v in case.verdicts] == [identity]
        assert case.reviewed == Reviewed(
            check="llm_rubric", assertion_id=identity, good=good
        )
        assert case.responses == ()
    assert result(found, "by-hand").reviewed is None


def test_the_judge_reads_the_recorded_answer_and_its_question() -> None:
    seen: list[str] = []

    def reading(prompt: str) -> JudgeReply:
        seen.append(prompt)
        return judge(prompt)

    execute(
        suite(reviewed("yes-good", GOOD, good=True), scorer=reading),
        target,
        created_at=CREATED,
    )
    asked = [prompt for prompt in seen if GOOD in prompt]
    assert asked and all(QUESTION in prompt for prompt in asked)


# -- the gate ---------------------------------------------------------------- #


def test_a_judge_that_agrees_with_every_person_passes_the_gate() -> None:
    found = run(*AGREES)
    assert contradicted(found) == ()
    assert run_exit_code(found, declared=suite(*AGREES).declared()) == EXIT_OK


@pytest.mark.parametrize(
    ("case", "direction"),
    [
        (reviewed("no-good", GOOD, good=False), "passed_no"),
        (reviewed("yes-bad", BAD, good=True), "failed_yes"),
    ],
    ids=["passed-a-no", "failed-a-yes"],
)
def test_a_judge_that_contradicts_a_person_fails_the_run(
    case: Case, direction: str
) -> None:
    found = run(case)
    [against] = contradicted(found)
    assert (against.case_id, against.direction) == (case.id, direction)
    assert run_exit_code(found, declared=suite(case).declared()) == EXIT_WORSE


@pytest.mark.parametrize(
    ("case", "counted"),
    [
        (reviewed("no-good", GOOD, good=False), (1, 0)),
        (reviewed("yes-bad", BAD, good=True), (0, 1)),
    ],
    ids=["passed-a-no", "failed-a-yes"],
)
def test_a_contradiction_fails_against_a_reference_too(
    case: Case, counted: tuple[int, int]
) -> None:
    """Each direction on its own moves the code: the headline counts it, and
    `exit_code` reads that count with nothing worse beside it."""
    found = run(case)
    head = headline(
        compare(found, found),
        found,
        found,
        locale="en",
        declared=suite(case).declared(),
    )
    assert (head.reviewed_passed_no, head.reviewed_failed_yes) == counted
    assert not head.worse and not head.canary_moved
    assert exit_code(head) == EXIT_WORSE


def test_an_errored_verdict_is_unjudged_and_never_a_contradiction() -> None:
    case = reviewed("yes-good", GOOD, good=True)
    found = run(case, scorer=broken)
    assert result(found, "yes-good").verdicts[0].status == "error"
    assert contradicted(found) == ()
    assert run_exit_code(found, declared=suite(case).declared()) == EXIT_UNJUDGED


# -- out of every aggregate ----------------------------------------------------- #


def test_it_is_out_of_the_aggregate_and_counted_as_excluded() -> None:
    found = run(
        *AGREES,
        cases=[Case(id="by-hand", label="positive"), *AGREES],
        run_assertions=[Accuracy(over="llm_rubric", threshold="1/2", tolerance=0.0)],
    )
    [accuracy] = found.aggregate
    assert accuracy.score.metadata["considered"] == 1
    assert accuracy.score.metadata["reviewed_excluded"] == 2
    assert "2 reviewed" in accuracy.reason


def test_an_aggregate_with_no_reviewed_answer_writes_no_key() -> None:
    found = run(
        cases=[Case(id="by-hand", label="positive")],
        run_assertions=[Accuracy(over="llm_rubric", threshold="1/2", tolerance=0.0)],
    )
    assert "reviewed_excluded" not in found.aggregate[0].score.metadata


def _sampled(case_id: str, samples: tuple[float, ...], **flags: bool) -> CaseOutcome:
    return CaseOutcome(
        case_id=case_id,
        label="positive" if not flags else None,
        verdict=Verdict(
            score=Score(
                name="llm_rubric",
                score=sum(samples) / len(samples),
                samples=samples,
                sample_min=min(samples),
                sample_max=max(samples),
            ),
            threshold=0.7,
            status="pass",
            reason="judged",
            assertion_id="llm_rubric",
        ),
        **flags,
    )


def test_its_samples_do_not_silence_the_aggregates_interval() -> None:
    """It samples the judge alone, and nothing obliges its count to match the
    other cases': counted, it would delete the noise interval of every
    aggregate in the run, for the calibration case's reason. (ADR 0024 §4.4)"""
    subject = _sampled("one", (0.7, 0.9))
    odd = _sampled("cap-1", (0.7, 0.8, 0.9), reviewed=True)
    assert per_sample_outcomes([subject, odd]) != ()


def test_it_is_a_case_that_watches_and_not_a_subject() -> None:
    declared = suite(*AGREES).declared()
    assert declared.subject == frozenset({"by-hand"})
    assert declared.watching == frozenset({"yes-good", "no-bad"})


def test_read_off_the_run_a_judged_reviewed_answer_does_not_judge_the_suite() -> None:
    """With no declaration to read, the subject cases are read off the run,
    and a reviewed answer is not one: a run whose only subject case was set
    aside judged nothing, however its reviewed answers went. (ADR 0049 §3)"""
    found = run(AGREES[0], cases=[Case(id="by-hand", suspended="parked"), AGREES[0]])
    assert nothing_judged(found, None)
    assert run_exit_code(found, declared=None) == EXIT_UNJUDGED


def test_a_reviewed_answer_and_a_calibration_band_are_two_kinds() -> None:
    from digline.core import CalibrationBand

    with pytest.raises(ValueError, match="a kind of its own"):
        CaseResult(
            case_id="x",
            calibration=CalibrationBand(check="c", low=0.3, high=0.7, assertion_id="a"),
            reviewed=Reviewed(check="c", assertion_id="a", good=True),
        )


# -- the run document --------------------------------------------------------- #


def test_the_document_writes_it_on_that_case_alone_and_reads_it_back() -> None:
    found = run(*AGREES)
    written = json.loads(run_to_json(found))
    by_id = {case["case_id"]: case for case in written["results"]}
    assert by_id["yes-good"]["reviewed"] == {
        "check": "llm_rubric",
        "assertion_id": suite().assertions[0].identity,
        "good": True,
    }
    assert by_id["no-bad"]["reviewed"]["good"] is False
    assert "reviewed" not in by_id["by-hand"]
    assert run_from_json(run_to_json(found)) == found


@pytest.mark.parametrize(
    ("value", "said"),
    [
        (None, "'reviewed' is not an object"),
        ({"check": "llm_rubric", "assertion_id": "x", "good": 1}, "not true or false"),
        (
            {"check": "llm_rubric", "good": True},
            "needs a 'check' and an 'assertion_id'",
        ),
        (
            {"check": "c", "assertion_id": "x", "good": True, "output": "o"},
            "carries output",
        ),
    ],
    ids=["null", "good-1", "no-identity", "the-answer"],
)
def test_a_document_refuses_what_no_writer_writes(value: object, said: str) -> None:
    written = json.loads(run_to_json(run(*AGREES)))
    written["results"][1]["reviewed"] = value
    with pytest.raises(ValueError, match=said):
        run_from_dict(written)


def test_a_run_refuses_a_reviewed_answer_that_binds_no_verdict() -> None:
    found = run(*AGREES)
    case = result(found, "yes-good")
    assert case.reviewed is not None
    unbound = dataclasses.replace(
        case, reviewed=dataclasses.replace(case.reviewed, assertion_id="0" * 16)
    )
    with pytest.raises(ValueError, match="binds no verdict checks nothing"):
        dataclasses.replace(found, results=(unbound,))


def test_a_case_is_not_both_a_reviewed_answer_and_a_canary() -> None:
    with pytest.raises(ValueError, match="a kind of its own"):
        CaseResult(
            case_id="x",
            canary=True,
            reviewed=Reviewed(check="c", assertion_id="a", good=True),
        )


class Tokens:
    """Look-up-or-mint on (kind, text), as the owning process does."""

    def __init__(self) -> None:
        self.rows: dict[tuple[TokenKind, str], str] = {}

    def __call__(self, kind: TokenKind, text: str) -> str:
        return self.rows.setdefault((kind, text), secrets.token_urlsafe(16))


def test_a_projection_mints_the_check_as_a_calibration_check() -> None:
    tokens = Tokens()
    projected = project_served(run(*AGREES), tokens)
    case = next(r for r in projected.results if r.reviewed is not None)
    assert case.reviewed is not None
    assert case.reviewed.check == tokens.rows[("calibration_check", "llm_rubric")]
    assert case.reviewed.good is True


def test_the_wire_carries_the_check_and_the_yes_or_no() -> None:
    from digline.core import NOTHING_EXTRA

    # Through JSON, as a consumer reads it.
    document: dict[str, Any] = json.loads(
        json.dumps(run_document(run(*AGREES), NOTHING_EXTRA))
    )
    cases = {case["case_id"]: case for case in document["results"]}
    assert cases["no-bad"]["reviewed"] == {"check": "llm_rubric", "good": False}
    assert cases["by-hand"]["reviewed"] is None


# -- comparison, headline, report ------------------------------------------------ #


def test_its_delta_is_kept_and_counted_nowhere() -> None:
    before = run(reviewed("case", GOOD, good=True))
    after = run(reviewed("case", BAD, good=True))
    comparison = compare(after, before)
    [delta] = comparison.reviewed_deltas
    assert delta.outcome == "regressed" and delta.instrument
    assert comparison.counts.get("regressed", 0) == 0
    assert comparison.of("regressed") == ()
    head = headline(comparison, after, before, locale="en", declared=None)
    assert not head.worse
    document = compare_json(comparison, head, baseline=before, full=True)
    rows = document["deltas"]
    assert isinstance(rows, list)
    flagged = [row["case_id"] for row in rows if row["reviewed"]]  # pyright: ignore[reportUnknownVariableType, reportIndexIssue]
    assert flagged == ["case"]


@pytest.mark.parametrize(
    ("cases", "said"),
    [
        (
            (reviewed("no-good", GOOD, good=False),),
            "The judge contradicted a person on 1 reviewed answer, and the case "
            "fails: no-good for llm_rubric, passed where the person said no.",
        ),
        (
            (reviewed("yes-bad", BAD, good=True),),
            "The judge contradicted a person on 1 reviewed answer, and the case "
            "fails: yes-bad for llm_rubric, failed where the person said yes.",
        ),
        (
            (
                reviewed("no-good", GOOD, good=False),
                reviewed("yes-bad", BAD, good=True),
                reviewed("yes-bad-2", BAD, good=True),
            ),
            "The judge contradicted a person on 3 reviewed answers, and each of "
            "those cases fails: no-good for llm_rubric, passed where the person "
            "said no; yes-bad for llm_rubric, failed where the person said yes; "
            "yes-bad-2 for llm_rubric, failed where the person said yes.",
        ),
    ],
    ids=["passed-a-no", "failed-a-yes", "both"],
)
def test_the_headline_says_each_direction(cases: Sequence[Case], said: str) -> None:
    found = run(*cases)
    head = headline(
        compare(found, found),
        found,
        found,
        locale="en",
        declared=suite(*cases).declared(),
    )
    assert said in head.sentence


def test_an_agreeing_judge_adds_nothing_to_the_sentence() -> None:
    found = run(*AGREES)
    head = headline(compare(found, found), found, found, locale="en", declared=None)
    assert "reviewed" not in head.sentence
    assert (head.reviewed_passed_no, head.reviewed_failed_yes) == (0, 0)


def test_the_italian_sentence_says_it_too() -> None:
    found = run(reviewed("no-good", GOOD, good=False))
    head = headline(compare(found, found), found, found, locale="it", declared=None)
    assert "promossa dove la persona ha detto no" in head.sentence


def test_the_report_shows_a_section_open_where_the_judge_contradicted() -> None:
    agreeing = reviewed_section(run(*AGREES), "en", reasons=False)
    assert agreeing.startswith("<details><summary>What the judge said of the")
    assert agreeing.count("<tr>") == 1 + 2  # the header row, and one per case
    against = reviewed_section(
        run(reviewed("no-good", GOOD, good=False)), "en", reasons=False
    )
    assert against.startswith("<details open>")
    assert "contradicts the person" in against
    assert reviewed_section(run(), "en", reasons=False) == ""
    page = render_run_html(run(reviewed("no-good", GOOD, good=False)), locale="en")
    assert "What the judge said of the reviewed answers" in page
    assert "no-good for llm_rubric, passed where the person said no" in page


def test_explain_tallies_the_contradictions() -> None:
    found = run(reviewed("no-good", GOOD, good=False))
    lines = explain_text(facts(found), locale="en")
    assert any(
        line.startswith("The judge contradicted a person on 1 reviewed answer")
        for line in lines
    )
    assert not any(
        "reviewed answer" in line
        for line in explain_text(facts(run(*AGREES)), locale="en")
    )


def test_explain_names_each_contradiction_and_its_direction() -> None:
    """The report's section, in the reading: which answer, which check, and
    which way the judge went, in the text and beside the count in --json."""
    found = run(
        reviewed("no-good", GOOD, good=False),
        reviewed("yes-bad", BAD, good=True),
        *AGREES,
    )
    [line] = [
        line
        for line in explain_text(facts(found), locale="en")
        if "reviewed answer" in line
    ]
    assert "no-good for llm_rubric, passed where the person said no" in line
    assert "yes-bad for llm_rubric, failed where the person said yes" in line
    assert "yes-good" not in line and "no-bad" not in line
    document = json.loads(
        json.dumps(explain_json(facts(found), reading="run", exit_code=1, run=found))
    )
    [fact] = [f for f in document["facts"] if f.get("kind") == "reviewed"]
    assert fact["count"] == 2
    assert fact["contradictions"] == [
        {"case_id": "no-good", "check": "llm_rubric", "direction": "passed_no"},
        {"case_id": "yes-bad", "check": "llm_rubric", "direction": "failed_yes"},
    ]
    [compared] = [
        f
        for f in facts(found, compare(found, found))
        if isinstance(f, TallyFact) and f.kind == "reviewed"
    ]
    assert [c.case_id for c in compared.contradictions] == ["no-good", "yes-bad"]
    [said] = [
        line
        for line in explain_text(facts(found), locale="it")
        if "risposte riviste" in line
    ]
    assert "no-good per llm_rubric, promossa dove la persona ha detto no" in said


@pytest.mark.parametrize(
    ("case", "said"),
    [
        (
            reviewed("no-good", GOOD, good=False),
            "no-good · llm_rubric passed at 1.000000, and a person said no to the "
            "answer: the judge contradicts the person, and the case fails.",
        ),
        (
            reviewed("yes-bad", BAD, good=True),
            "yes-bad · llm_rubric failed at 0.000000, and a person said yes to the "
            "answer: the judge contradicts the person, and the case fails.",
        ),
    ],
    ids=["passed-a-no", "failed-a-yes"],
)
def test_a_contradiction_is_what_the_run_found(case: Case, said: str) -> None:
    """When it is the only finding, `What it found` says it, and never
    *Nothing in this group*; alone and against a reference alike."""
    found = run(case)
    for reading, heading in (
        (facts(found), "What it found"),
        (facts(found, compare(found, found)), "What moved"),
    ):
        lines = explain_text(reading, locale="en")
        # The last group is the checks: its heading, then the contradiction,
        # where *Nothing in this group.* used to stand.
        assert lines[-2:] == (heading, said)


def test_explain_json_says_what_the_person_said_on_a_contradiction() -> None:
    found = run(reviewed("no-good", GOOD, good=False), *AGREES)
    document = json.loads(
        json.dumps(explain_json(facts(found), reading="run", exit_code=1, run=found))
    )
    [check] = [f for f in document["facts"] if f.get("kind") == "contradicted"]
    assert (check["case_id"], check["good"], check["after"]) == ("no-good", False, 1.0)
    assert all(
        "good" not in f for f in document["facts"] if f.get("kind") != "contradicted"
    )


def test_shape_leaves_it_out() -> None:
    """A yes or a no asks for an extreme, so counted it would inflate the
    share at 0 or 1 of the check it names. Only `by-hand`'s two samples are
    read."""
    found = run(*AGREES)
    [item] = [i for i in shape(compare(found, found)) if i.check == "llm_rubric"]
    assert item.run.scores == 2


def test_the_log_reads_it_as_part_of_the_population() -> None:
    with_one = run(*AGREES)
    without = run(AGREES[0])
    assert _population(with_one)[-1] == frozenset({"yes-good", "no-bad"})
    assert _population(with_one) != _population(without)


# -- replay and the plan ---------------------------------------------------------- #


def test_a_replay_rejudges_it_from_the_declaration() -> None:
    declared = suite(reviewed("no-good", GOOD, good=False), record_responses=True)
    stored = execute(declared, target, created_at=CREATED)
    replayed = Replay(declared, stored)
    again = execute(declared, replayed, created_at=CREATED)
    assert [c.direction for c in contradicted(again)] == ["passed_no"]


def test_the_plan_announces_its_judge_calls_and_no_target_call() -> None:
    plan = planned_calls(suite(*AGREES))
    assert plan.cases == 1
    assert (plan.reviewed, plan.reviewed_calls, plan.calibration) == (2, 4, 0)
    assert "2 reviewed answers judged 4 times, with no call to the target" in (
        plan.sentence()
    )


# -- digline run ------------------------------------------------------------------- #

SUITE_PY = """\
from digline.core import JudgeReply, LlmRubric
from digline.run import Case, Response, ReviewedAnswer, Suite


def judge(prompt):
    return JudgeReply(score=1.0 if "judged right" in prompt else 0.0, reason="r")


suite = Suite(
    tenant="acme",
    environment="dev",
    name="support",
    assertions=[
        LlmRubric(rubric="is it right?", judge=judge, threshold=0.7, tolerance=0.05)
    ],
    cases=[
        Case(id="by-hand"),
        Case(
            id="cap-1",
            reviewed_answer=ReviewedAnswer(
                output="Fourteen days. (judged right)",
                check="llm_rubric",
                good=GOOD,
                input="How long?",
            ),
        ),
    ],
    samples=2,
    min_agreement="2/2",
)


def target(case):
    if case.reviewed_answer is not None:
        raise AssertionError("the target was called")
    return Response(output="(judged right)", input="How long?")
"""


@pytest.mark.parametrize(("good", "code"), [(True, EXIT_OK), (False, EXIT_WORSE)])
def test_digline_run_judges_it_and_report_exits_by_it(
    tmp_path: Path, good: bool, code: int
) -> None:
    """`digline run` exits `2` for a run that judged nothing and `0` for every
    other, a lost scale included (ADR 0049 §3, amended; #654): the gate is
    `report`, `explain` and `compare`, and `report` exits `1` here."""
    (tmp_path / "suite.py").write_text(
        SUITE_PY.replace("good=GOOD", f"good={good}"), encoding="utf-8"
    )
    done = cli(tmp_path, "run", "--suite", "suite.py")
    assert done.returncode == EXIT_OK, done.stderr
    assert "the target was called" not in done.stderr
    reported = cli(
        tmp_path, "report", "--suite", "suite.py", "--run", "latest", "--locale", "en"
    )
    assert reported.returncode == code, reported.stderr
    [written] = (tmp_path / ".digline" / "acme" / "runs").rglob("*.json")
    document = json.loads(written.read_text(encoding="utf-8"))
    by_id = {case["case_id"]: case for case in document["results"]}
    assert by_id["cap-1"]["reviewed"]["good"] is good
    # What the person who ran it reads, beside the bill: the contradiction,
    # and a next step that is never promote, which refuses it. (ADR 0059 §1)
    said = "the judge contradicted a person on 1 reviewed answer."
    [following] = [line for line in done.stderr.splitlines() if "next:" in line]
    if good:
        assert said not in done.stderr
        assert "digline promote" in following
    else:
        assert f"digline: {said}" in done.stderr.splitlines()
        assert "digline explain" in following
        assert "digline promote" not in following
        refused = cli(
            tmp_path,
            "promote",
            "--suite",
            "suite.py",
            "--run",
            "latest",
            "--replacing",
            "none",
        )
        assert refused.returncode == EXIT_USAGE, refused.stderr
        assert "cap-1 (failed a yes)" not in refused.stderr
        assert "contradicted a person about (cap-1 (passed a no))" in refused.stderr
        assert not list((tmp_path / ".digline" / "acme").rglob("baselines/*.json"))


def test_promotion_refuses_a_run_the_judge_contradicted_a_person_in() -> None:
    """Condition 12, after the lost scale: named by case and direction, and a
    run whose judge agreed with every person is not refused for it."""
    against = run(
        reviewed("no-good", GOOD, good=False), reviewed("yes-bad", BAD, good=True)
    )
    refusals = refusals_for(against, against.config_hash, declared=None)
    [refusal] = [r for r in refusals if isinstance(r, ContradictedRunError)]
    assert "no-good (passed a no), yes-bad (failed a yes)" in str(refusal)
    assert "a baseline where the judge contradicts the person is not a baseline" in (
        str(refusal)
    )
    agreeing = run(*AGREES)
    assert not [
        r
        for r in refusals_for(agreeing, agreeing.config_hash, declared=None)
        if isinstance(r, ContradictedRunError)
    ]
