"""A new round on the reviewed answers alone, and the two rubrics compared.
(ADR 0067 §1 (d), §10 item 3, and the rulings of 2026-11-22, P-1715)

What is held here, each with the mutation that turns it red, listed in the
session's report:

- **no target is called**: the round is the run's reviewed answers and nothing
  else, and a target that records its calls stays at zero, through the driver
  and through `digline rejudge --reviewed`;
- **a rubric edit is paired and named**: the verdicts of one check name are
  paired across the run and its re-judge although the rubric moved the
  identity, the check is said to have changed, and each reviewed answer whose
  verdict changed is named with its check and its direction;
- **a change of type is not paired**, and says so;
- **a run written before schema 25 is not paired**, and says that the source's
  type is not recorded;
- around them: the type each verdict records, the held-out answers counted
  and never named, the readings in en and it, `--json`, the report, and the
  re-judge refused at promotion, which is ADR 0015 §7 as written.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any

import pytest
from tests._helpers import cli

from digline.core import (
    CHECK_TYPES,
    TYPE_OF_CLASS,
    CaseResult,
    Contains,
    FromAutoevals,
    JudgeReply,
    LlmRubric,
    Repeated,
    Reviewed,
    RubricComparison,
    Run,
    Score,
    Verdict,
    check_type,
    rubric_comparison,
    run_from_json,
    run_to_json,
)
from digline.host.toml_suite import AGGREGATES, ASSERTIONS
from digline.report.explain import explain_text, facts
from digline.report.render import render_run_html, rubric_lines
from digline.run import (
    Case,
    ReplayError,
    Response,
    ReviewedAnswer,
    Suite,
    execute,
    rejudge_reviewed,
    reviewed_round,
)
from digline.wire import EXIT_OK, EXIT_USAGE, explain_json

CREATED = "2026-11-22T09:00:00+00:00"
AGAIN = "2026-11-22T10:00:00+00:00"
SOURCE = "2026-11-22T09-00-00-000000-00-00-0123456789abcdef"
QUESTION = "How long does a refund take?"
GOOD = "Refunds take 14 days. (judged right)"
BAD = "Refunds take a year."


def judge(prompt: str) -> JudgeReply:
    """A lenient rubric passes every answer; a strict one only the right."""
    if "strict" in prompt:
        return JudgeReply(score=1.0 if "judged right" in prompt else 0.0, reason="r")
    return JudgeReply(score=1.0, reason="r")


def rubric(text: str) -> LlmRubric:
    return LlmRubric(rubric=text, judge=judge, threshold=0.7, tolerance=0.05)


def reviewed(case_id: str, output: str, *, good: bool, held_out: bool = False) -> Case:
    return Case(
        id=case_id,
        reviewed_answer=ReviewedAnswer(
            output=output,
            check="llm_rubric",
            good=good,
            input=QUESTION,
            held_out=held_out,
        ),
    )


REVIEWED = (
    reviewed("yes-good", GOOD, good=True),
    reviewed("no-bad", BAD, good=False),
    reviewed("aside-bad", BAD, good=False, held_out=True),
)


def suite(text: str, *, assertions: Any = None) -> Suite:
    return Suite(
        tenant="acme",
        environment="dev",
        name="support",
        assertions=assertions or [rubric(text), Contains(needle="days")],
        cases=[Case(id="by-hand"), *REVIEWED],
        samples=2,
        min_agreement="2/2",
    )


class Recording:
    """A target that records every call, so a round can be held to zero."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def __call__(self, case: Case) -> Response:
        self.calls.append(case.id)
        return Response(output=GOOD, input=QUESTION)


def first_run() -> Run:
    return execute(suite("lenient"), Recording(), created_at=CREATED)


def round_of(declared: Suite, source: Run) -> Run:
    return rejudge_reviewed(declared, source, key=SOURCE, created_at=AGAIN)


# -- the type a verdict records ------------------------------------------------ #


def test_each_verdict_records_its_checks_type_in_the_word_a_suite_toml_writes() -> None:
    """Mutation: `check_type=None` in the driver's `_stamped` turns it red."""
    found = first_run()
    by_hand = next(case for case in found.results if case.case_id == "by-hand")
    assert [v.check_type for v in by_hand.verdicts] == ["llm_rubric", "contains"]


def test_a_repeated_check_is_the_type_it_wraps_and_a_suites_own_class_has_none() -> (
    None
):
    assert (
        check_type(Repeated(inner=rubric("x"), samples=3, min_agreement="2/3"))
        == "llm_rubric"
    )

    @dataclasses.dataclass(frozen=True)
    class Mine(Contains):
        pass

    assert check_type(Mine(needle="days")) is None


def test_the_words_are_the_tokens_a_suite_toml_builds_each_class_from() -> None:
    """One vocabulary, two places: the run's word for a type is the token a
    `suite.toml` writes, `repeated` excepted, which is read through, and
    `from_autoevals`, which no data file builds and is still digline's."""
    tokens = {**ASSERTIONS, **AGGREGATES}
    expected = {cls: token for token, cls in tokens.items() if token != "repeated"}
    expected[FromAutoevals] = "from_autoevals"
    assert dict(TYPE_OF_CLASS) == expected
    assert set(TYPE_OF_CLASS.values()) == CHECK_TYPES


def test_the_document_writes_the_type_and_reads_it_back_and_refuses_another_word() -> (
    None
):
    found = first_run()
    text = run_to_json(found)
    assert '"check_type": "llm_rubric"' in text
    assert run_from_json(text) == found
    with pytest.raises(ValueError, match="not one of digline's words"):
        run_from_json(text.replace('"check_type": "contains"', '"check_type": "x"'))


# -- no target is called --------------------------------------------------------- #


def test_the_round_is_the_runs_reviewed_answers_and_no_target_is_called() -> None:
    """Mutation: `reviewed_round` returning `suite` unnarrowed turns it red,
    the recording target asked for `by-hand`."""
    source = first_run()
    recording = Recording()
    again = execute(
        reviewed_round(suite("strict"), source), recording, created_at=AGAIN
    )
    assert recording.calls == []
    assert [case.case_id for case in again.results] == [
        "yes-good",
        "no-bad",
        "aside-bad",
    ]


def test_the_round_declares_its_source_and_carries_the_runs_target() -> None:
    source = first_run()
    again = round_of(suite("strict"), source)
    assert again.rejudged_from == SOURCE
    assert again.target_config == source.target_config


def test_a_run_with_no_reviewed_answer_is_refused() -> None:
    plain = execute(
        dataclasses.replace(suite("lenient"), cases=[Case(id="by-hand")]),
        Recording(),
        created_at=CREATED,
    )
    with pytest.raises(ReplayError, match="holds no reviewed answer"):
        reviewed_round(suite("strict"), plain)


def test_a_reviewed_answer_the_suite_no_longer_declares_is_refused_by_name() -> None:
    source = first_run()
    narrower = dataclasses.replace(
        suite("strict"), cases=[Case(id="by-hand"), *REVIEWED[:2]]
    )
    with pytest.raises(ReplayError, match="'aside-bad' is a reviewed answer"):
        reviewed_round(narrower, source)


# -- a rubric edit is paired and named ------------------------------------------ #


def test_a_rubric_edit_is_paired_by_name_and_each_changed_answer_is_named() -> None:
    """Mutations: `_named` matching on `assertion_id` instead of the name turns
    it red, nothing paired; `PairedCheck.changed` returning `False` turns it
    red, the check said unchanged."""
    source = first_run()
    again = round_of(suite("strict"), source)
    compared = rubric_comparison(source, again)
    assert compared is not None
    [paired] = compared.paired
    assert (paired.check, paired.check_type, paired.changed) == (
        "llm_rubric",
        "llm_rubric",
        True,
    )
    assert paired.before_id != paired.after_id
    assert [
        (c.case_id, c.check, c.before, c.after, c.toward) for c in compared.changes
    ] == [("no-bad", "llm_rubric", "pass", "fail", True)]
    assert compared.answers == 3
    assert compared.unpaired == ()


def test_the_same_rubric_is_paired_and_said_unchanged() -> None:
    source = first_run()
    compared = rubric_comparison(source, round_of(suite("lenient"), source))
    assert compared is not None
    assert [c.changed for c in compared.paired] == [False]
    assert compared.changes == ()
    assert "No reviewed answer changed verdict on a paired check." in rubric_lines(
        compared, "en"
    )


def test_a_change_away_from_the_person_is_said_so() -> None:
    """Mutation: `_toward` returning `not` its value turns it red."""
    strict = execute(suite("strict"), Recording(), created_at=CREATED)
    compared = rubric_comparison(strict, round_of(suite("lenient"), strict))
    assert compared is not None
    assert [(c.case_id, c.toward) for c in compared.changes] == [("no-bad", False)]


# -- held out: counted, never named -------------------------------------------- #


def test_a_held_out_answer_that_changed_is_counted_and_never_named() -> None:
    """Mutation: dropping the `held_out` branch turns it red, `aside-bad`
    named among the changes."""
    source = first_run()
    compared = rubric_comparison(source, round_of(suite("strict"), source))
    assert compared is not None
    assert compared.held_out_changes == 1
    assert "aside-bad" not in {c.case_id for c in compared.changes}
    lines = rubric_lines(compared, "en")
    assert not any("aside-bad" in line for line in lines)
    assert (
        "1 held-out answer changed verdict on a paired check, counted and not named."
        in lines
    )


# -- a change of type, and a run before schema 25 -------------------------------- #


def _verdict(name: str, status: str, kind: Any, identity: str) -> Verdict:
    return Verdict(
        score=Score(name=name, score=1.0 if status == "pass" else 0.0),
        threshold=0.7,
        status=status,  # pyright: ignore[reportArgumentType]
        reason="r",
        assertion_id=identity,
        judged=True,
        check_type=kind,
    )


def _pair(before: Any, after: Any) -> tuple[Run, Run]:
    """A run and its re-judge, one reviewed answer whose verdict on `tone`
    changed from fail to pass, the person having said yes."""
    base = first_run()
    reviewed = Reviewed(check="tone", assertion_id="b" * 16, good=True)

    def one(status: str, kind: Any, identity: str) -> tuple[CaseResult, ...]:
        return (
            CaseResult(
                "c1",
                (_verdict("tone", status, kind, identity),),
                reviewed=dataclasses.replace(reviewed, assertion_id=identity),
            ),
        )

    source = dataclasses.replace(base, results=one("fail", before, "a" * 16))
    again = dataclasses.replace(
        base, results=one("pass", after, "b" * 16), rejudged_from=SOURCE
    )
    return source, again


def test_a_check_whose_type_changed_is_not_paired_and_says_so() -> None:
    """Mutation: dropping the `old_types != new_types` test turns it red, the
    two kinds paired and the change listed."""
    source, again = _pair("llm_rubric", "faithfulness")
    compared = rubric_comparison(source, again)
    assert compared is not None
    assert compared.paired == ()
    assert compared.changes == ()
    [unpaired] = compared.unpaired
    assert (unpaired.why, unpaired.before, unpaired.after) == (
        "type_changed",
        "llm_rubric",
        "faithfulness",
    )
    assert "tone is not paired: its type changed, llm_rubric → faithfulness." in (
        rubric_lines(compared, "en")
    )


def test_an_unnamed_check_in_a_typed_checks_place_changed_type() -> None:
    source, again = _pair("llm_rubric", None)
    compared = rubric_comparison(source, again)
    assert compared is not None
    assert [u.why for u in compared.unpaired] == ["type_changed"]
    assert (
        "tone is not paired: its type changed, llm_rubric → a type digline has no "
        "word for." in rubric_lines(compared, "en")
    )


def test_a_source_written_before_schema_25_is_not_paired_and_says_so() -> None:
    """Read from a document with the key taken out, which is what a verdict
    before 25 is. Mutation: dropping the `None in old_types` branch turns it
    red, the verdicts paired with a type nobody recorded."""
    source, again = _pair("llm_rubric", "llm_rubric")
    older = run_from_json(json.dumps(_without_type(json.loads(run_to_json(source)))))
    assert all(v.check_type is None for c in older.results for v in c.verdicts)
    compared = rubric_comparison(older, again)
    assert compared is not None
    assert compared.paired == ()
    assert compared.changes == ()
    assert [u.why for u in compared.unpaired] == ["type_not_recorded"]
    assert rubric_lines(compared, "en")[1] == (
        "tone is not paired: the type of the run it was re-judged from is not recorded."
    )
    assert rubric_lines(compared, "it")[1] == (
        "tone non è accoppiato: il tipo del run di partenza non è registrato."
    )


def _without_type(document: Any) -> Any:
    for case in document["results"]:
        for verdict in case["verdicts"]:
            verdict.pop("check_type", None)
    return document


def test_a_name_two_checks_share_on_one_answer_is_not_paired() -> None:
    source, again = _pair("llm_rubric", "llm_rubric")
    [case] = again.results
    doubled = dataclasses.replace(
        again,
        results=(
            dataclasses.replace(
                case,
                verdicts=(
                    *case.verdicts,
                    _verdict("tone", "fail", "contains", "c" * 16),
                ),
            ),
        ),
    )
    compared = rubric_comparison(source, doubled)
    assert compared is not None
    assert [u.why for u in compared.unpaired] == ["name_shared"]


def test_two_tenants_are_refused() -> None:
    source, again = _pair("llm_rubric", "llm_rubric")
    with pytest.raises(ValueError, match="across tenants"):
        rubric_comparison(dataclasses.replace(source, tenant="other"), again)


def test_a_run_that_is_no_re_judge_has_no_comparison() -> None:
    source, again = _pair("llm_rubric", "llm_rubric")
    assert (
        rubric_comparison(source, dataclasses.replace(again, rejudged_from=None))
        is None
    )


# -- the readings ---------------------------------------------------------------- #


def _compared() -> tuple[Run, RubricComparison]:
    source = first_run()
    again = round_of(suite("strict"), source)
    compared = rubric_comparison(source, again)
    assert compared is not None
    return again, compared


def test_explain_prints_the_comparison_under_its_heading_in_en_and_it() -> None:
    again, compared = _compared()
    en = "\n".join(explain_text(facts(again, rubrics=compared), locale="en"))
    assert (
        "What the re-judge changed, against the run it was made from\n"
        f"Read against {SOURCE}, the run this was re-judged from, on 3 reviewed "
        "answers in both.\n"
        "llm_rubric changed since that run, its rubric or another of its settings; "
        "verdicts paired by name.\n"
        "no-bad · llm_rubric: passed → failed, toward the person.\n"
        "1 held-out answer changed verdict on a paired check, counted and not named."
    ) in en, en
    it = "\n".join(explain_text(facts(again, rubrics=compared), locale="it"))
    assert "no-bad · llm_rubric: passato → fallito, verso la persona." in it


def test_explain_json_carries_it_as_a_tally_with_no_held_out_name() -> None:
    again, compared = _compared()
    payload: Any = json.loads(
        json.dumps(
            explain_json(
                facts(again, rubrics=compared), reading="run", exit_code=0, run=again
            )
        )
    )
    facts_by_kind = {
        fact["kind"]: fact for fact in payload["facts"] if fact["about"] == "run"
    }
    rubrics = facts_by_kind["rubrics"]["rubrics"]
    assert facts_by_kind["rubrics"]["count"] == 3
    assert rubrics["source"] == SOURCE
    assert rubrics["paired"][0]["changed"] is True
    assert rubrics["changes"] == [
        {
            "case_id": "no-bad",
            "check": "llm_rubric",
            "before": "pass",
            "after": "fail",
            "toward": True,
        }
    ]
    assert rubrics["held_out_changes"] == 1
    assert "aside-bad" not in json.dumps(rubrics)


def test_the_report_has_a_section_of_its_own_open_where_a_verdict_changed() -> None:
    again, compared = _compared()
    html = render_run_html(again, locale="it", rubrics=compared)
    assert (
        "<details open><summary>Che cosa ha cambiato il nuovo giudizio, rispetto al "
        "run da cui è stato fatto</summary>"
    ) in html
    assert "verso la persona" in html
    assert "What the re-judge changed" not in render_run_html(again, locale="en")


def test_a_source_the_store_no_longer_holds_is_said() -> None:
    assert rubric_lines(RubricComparison.unread(SOURCE), "en") == (
        f"{SOURCE}, the run this was re-judged from, could not be read: its "
        "verdicts are not compared.",
    )


# -- digline rejudge --reviewed ---------------------------------------------------- #

SUITE_PY = """\
from pathlib import Path

from digline.core import JudgeReply, LlmRubric
from digline.run import Case, Response, ReviewedAnswer, Suite

CALLS = Path(__file__).with_name("calls.txt")


def judge(prompt):
    if "strict" in prompt:
        return JudgeReply(score=1.0 if "judged right" in prompt else 0.0, reason="r")
    return JudgeReply(score=1.0, reason="r")


def answer(case_id, output, good, held_out=False):
    return Case(
        id=case_id,
        reviewed_answer=ReviewedAnswer(
            output=output,
            check="llm_rubric",
            good=good,
            input="How long?",
            held_out=held_out,
        ),
    )


suite = Suite(
    tenant="acme",
    environment="dev",
    name="support",
    assertions=[
        LlmRubric(rubric="RUBRIC", judge=judge, threshold=0.7, tolerance=0.05)
    ],
    cases=[
        Case(id="by-hand"),
        answer("yes-good", "Fourteen days. (judged right)", True),
        answer("no-bad", "A year.", False),
    ],
    samples=2,
    min_agreement="2/2",
)


def target(case):
    with CALLS.open("a", encoding="utf-8") as calls:
        calls.write(case.id + "\\n")
    return Response(output="(judged right)", input="How long?")
"""


def _write(root: Path, text: str) -> None:
    (root / "suite.py").write_text(SUITE_PY.replace("RUBRIC", text), encoding="utf-8")


def test_digline_rejudge_reviewed_calls_no_target_and_says_what_changed(
    tmp_path: Path,
) -> None:
    """End to end: the run asks the target twice, `by-hand`'s two samples; the round on
    the reviewed answers, with the rubric corrected, asks it nothing, writes a
    run that declares its source, says what changed at the end, and is
    refused at promotion (ADR 0015 §7)."""
    _write(tmp_path, "lenient")
    done = cli(tmp_path, "run", "--suite", "suite.py")
    assert done.returncode == EXIT_OK, done.stderr
    calls = tmp_path / "calls.txt"
    assert calls.read_text(encoding="utf-8").splitlines() == ["by-hand", "by-hand"]

    _write(tmp_path, "strict")
    again = cli(
        tmp_path, "rejudge", "--suite", "suite.py", "--run", "latest", "--reviewed"
    )
    assert again.returncode == EXIT_OK, again.stderr
    assert calls.read_text(encoding="utf-8").splitlines() == ["by-hand", "by-hand"]
    lines = again.stderr.splitlines()
    assert (
        "digline: llm_rubric changed since that run, its rubric or another of its "
        "settings; verdicts paired by name." in lines
    ), again.stderr
    assert "digline: no-bad · llm_rubric: passed → failed, toward the person." in lines
    key = again.stdout.strip()

    written = next((tmp_path / ".digline" / "acme" / "runs").rglob(f"{key}.json"))
    document = json.loads(written.read_text(encoding="utf-8"))
    assert document["rejudged_from"]
    assert [case["case_id"] for case in document["results"]] == ["yes-good", "no-bad"]

    explained = cli(tmp_path, "explain", "--suite", "suite.py", "--run", key)
    assert "no-bad · llm_rubric: passed → failed, toward the person." in (
        explained.stdout
    ), explained.stdout + explained.stderr

    refused = cli(
        tmp_path, "promote", "--suite", "suite.py", "--run", key, "--replacing", "none"
    )
    assert refused.returncode == EXIT_USAGE, refused.stderr
    assert "not from the target" in refused.stderr


def test_digline_rejudge_reviewed_refuses_a_run_with_no_reviewed_answer(
    tmp_path: Path,
) -> None:
    (tmp_path / "suite.py").write_text(
        SUITE_PY.replace("RUBRIC", "lenient").replace(
            """        answer("yes-good", "Fourteen days. (judged right)", True),
        answer("no-bad", "A year.", False),
""",
            "",
        ),
        encoding="utf-8",
    )
    done = cli(tmp_path, "run", "--suite", "suite.py")
    assert done.returncode == EXIT_OK, done.stderr
    again = cli(
        tmp_path, "rejudge", "--suite", "suite.py", "--run", "latest", "--reviewed"
    )
    assert again.returncode == EXIT_USAGE
    assert "holds no reviewed answer" in again.stderr


def test_explain_and_the_report_read_the_source_and_say_when_it_is_gone(
    tmp_path: Path,
) -> None:
    """The host reads the run `rejudged_from` names: the report has the
    section in it, `explain --json` the tally, and once the source is deleted
    `explain` says it could not be read rather than leaving the block out."""
    _write(tmp_path, "lenient")
    assert cli(tmp_path, "run", "--suite", "suite.py").returncode == EXIT_OK
    source_key = next((tmp_path / ".digline" / "acme" / "runs").rglob("*.json")).stem
    _write(tmp_path, "strict")
    again = cli(
        tmp_path, "rejudge", "--suite", "suite.py", "--run", "latest", "--reviewed"
    )
    key = again.stdout.strip()

    reported = cli(
        tmp_path, "report", "--suite", "suite.py", "--run", key, "--locale", "it"
    )
    assert "no-bad · llm_rubric: passato → fallito, verso la persona." in (
        reported.stdout
    ), reported.stderr

    as_json = cli(tmp_path, "explain", "--suite", "suite.py", "--run", key, "--json")
    payload = json.loads(as_json.stdout)
    [tally] = [f for f in payload["facts"] if f["kind"] == "rubrics"]
    assert tally["rubrics"]["source"] == source_key

    # Taken out of the store by hand: what is held is the reading of a store
    # that no longer has the run, however it went.
    next((tmp_path / ".digline" / "acme" / "runs").rglob(f"{source_key}.json")).unlink()
    gone = cli(tmp_path, "explain", "--suite", "suite.py", "--run", key)
    assert (
        f"{source_key}, the run this was re-judged from, could not be read: its "
        "verdicts are not compared." in gone.stdout
    ), gone.stdout + gone.stderr
