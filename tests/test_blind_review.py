"""The reviewed answer's new shape and the blind review: the first pull request
of ADR 0067 §10, with the rulings of 2026-11-19 (P-1710).

What §10 asks this pull request to measure, each held here with a control,
and each with a mutation that makes it fail (in the pull request's report):

1. **An answer awaiting a verdict is in no gate, and is never shown beside
   the judge's verdict.** Its judge's contradiction moves no exit code, its
   judge's error is no cause of 2 and is said, a run of awaiting answers alone
   judged nothing, and the report's section of reviewed answers has no row for
   it;
2. **a press and the command leave identical stores**: the first press on an
   awaiting answer about the whole answer, with its failing check, and the
   second press, the revision;
3. **today's files load unchanged**: a cases file in today's form, the
   record a run writes of it, and a schema-24 document read back;
4. **"good on everything but X" expects what it says, check by check.**
"""

from __future__ import annotations

import json
import shlex
import sys
from pathlib import Path
from typing import Any

import pytest
from tests.test_review import CAPTURED, LONG_ID, cases_in, press
from tests.test_view_recorder import (
    WRITES,
    Served,
    by_command,
    copy_of,
    opened,
    serving,
    tree,
)
from tests.test_view_recorder import (
    root as root,  # noqa: F401 — the fixture, by its name
)

from digline.core import (
    Contains,
    JudgeReply,
    LlmRubric,
    Reviewed,
    Run,
    all_awaiting,
    awaiting_cases,
    awaiting_unjudged,
    compare,
    contradicted,
    nothing_judged,
    unjudged_cases,
)
from digline.core.run import reviewed_to_dict, run_from_dict, run_to_dict
from digline.host import read_cases
from digline.report.render import headline, nothing_judged_text, reviewed_section
from digline.run import Case, Response, ReviewedAnswer, Suite, execute
from digline.store.migrate import upgrade_document
from digline.wire import EXIT_OK, EXIT_UNJUDGED, EXIT_WORSE, run_exit_code

CREATED = "2026-01-01T00:00:00+00:00"
QUESTION = "How long does a refund take?"
RIGHT = "Refunds take 14 days. (judged right)"
WRONG = "Refunds take a year."
DOWN = "the judge cannot read this one"


def judge(prompt: str) -> JudgeReply:
    if DOWN in prompt:
        raise RuntimeError("the judge is down")
    return JudgeReply(score=1.0 if "judged right" in prompt else 0.0, reason="r")


def rubric(name: str = "llm_rubric") -> LlmRubric:
    return LlmRubric(
        rubric="is it right?", judge=judge, threshold=0.7, tolerance=0.05, name=name
    )


def answer(output: str, *, good: bool | None, **changes: Any) -> ReviewedAnswer:
    fields: dict[str, Any] = {
        "output": output,
        "check": "llm_rubric",
        "good": good,
        "input": QUESTION,
    }
    fields.update(changes)
    return ReviewedAnswer(**fields)


def suite(*cases: Case, by_hand: bool = True, **changes: Any) -> Suite:
    fields: dict[str, Any] = {
        "tenant": "acme",
        "environment": "dev",
        "name": "support",
        "assertions": [rubric(), Contains(needle="days")],
        "cases": [*([Case(id="by-hand")] if by_hand else []), *cases],
        "samples": 2,
        "min_agreement": "2/2",
    }
    fields.update(changes)
    return Suite(**fields)


def target(case: Case) -> Response:
    if case.reviewed_answer is not None:
        raise AssertionError("the target was called for a reviewed answer")
    return Response(output=RIGHT, input=QUESTION)


def run(*cases: Case, by_hand: bool = True, **changes: Any) -> tuple[Suite, Run]:
    checked = suite(*cases, by_hand=by_hand, **changes)
    return checked, execute(checked, target, created_at=CREATED)


# -- 1. awaiting: in no gate, never beside the judge's verdict --------------- #


def test_a_contradiction_on_an_answer_awaiting_a_verdict_moves_no_exit() -> None:
    """The judge fails WRONG. Awaiting, nobody has said anything it could
    contradict; given a yes, the same verdict is a contradiction, exit 1."""
    checked, found = run(Case(id="chosen", reviewed_answer=answer(WRONG, good=None)))
    assert awaiting_cases(found) == {"chosen"}
    assert contradicted(found) == ()
    assert run_exit_code(found, declared=checked.declared()) == EXIT_OK
    # The control: the same answer with a yes.
    checked, said = run(Case(id="chosen", reviewed_answer=answer(WRONG, good=True)))
    assert len(contradicted(said)) == 1
    assert run_exit_code(said, declared=checked.declared()) == EXIT_WORSE


def test_a_judge_error_on_an_awaiting_answer_is_said_and_no_cause_of_two() -> None:
    """Ruled 2026-11-19 (P-1710): it is in no gate, so its error is said,
    *1 awaiting answer was not judged*, and the exit stays the gate's."""
    checked, found = run(Case(id="chosen", reviewed_answer=answer(DOWN, good=None)))
    assert unjudged_cases(found) == 0
    assert awaiting_unjudged(found) == 1
    assert run_exit_code(found, declared=checked.declared()) == EXIT_OK
    said = headline(
        compare(found, found), found, found, locale="en", declared=checked.declared()
    )
    assert said.awaiting == 1 and said.awaiting_unjudged == 1
    assert "1 awaiting answer was not judged." in said.sentence
    # The control: the same error on an answer with a verdict is unjudged.
    checked, decided = run(Case(id="chosen", reviewed_answer=answer(DOWN, good=True)))
    assert unjudged_cases(decided) == 1
    assert run_exit_code(decided, declared=checked.declared()) == EXIT_UNJUDGED


def test_a_run_whose_only_cases_await_a_verdict_judged_nothing() -> None:
    """Fixed decision 3, as ruled (P-1710): exit 2, with its own sentence."""
    checked, found = run(
        Case(id="chosen", reviewed_answer=answer(RIGHT, good=None)), by_hand=False
    )
    declared = checked.declared()
    assert nothing_judged(found, declared) and all_awaiting(found, declared)
    assert run_exit_code(found, declared=declared) == EXIT_UNJUDGED
    assert "is an answer awaiting a person's verdict" in nothing_judged_text(
        found, declared, "en"
    )
    # The control: one answer with a verdict beside it is judged.
    checked, decided = run(
        Case(id="chosen", reviewed_answer=answer(RIGHT, good=None)),
        Case(id="said", reviewed_answer=answer(RIGHT, good=True)),
        by_hand=False,
    )
    assert not nothing_judged(decided, checked.declared())
    assert run_exit_code(decided, declared=checked.declared()) == EXIT_OK


def test_the_report_never_sets_an_awaiting_answer_beside_the_judge() -> None:
    """The report's section shows what the judge said beside what the person
    said. An answer awaiting a verdict has no row there: the judge's verdict
    alone, beside nothing, is what the blind review must not be shown."""
    _, found = run(
        Case(id="chosen-zz", reviewed_answer=answer(RIGHT, good=None)),
        Case(id="said-yy", reviewed_answer=answer(RIGHT, good=True)),
    )
    section = reviewed_section(found, "en", reasons=True)
    assert "said-yy" in section
    assert "chosen-zz" not in section


# -- 4. good on everything but X, check by check ----------------------------- #


def keyed(prompt: str) -> JudgeReply:
    """Passes a check whose rubric's word appears in the answer."""
    rubric_line = next(line for line in prompt.splitlines() if "criterion:" in line)
    word = rubric_line.split("criterion:")[1].strip().rstrip("?")
    return JudgeReply(
        score=1.0 if word in prompt.split("Output")[-1] else 0.0, reason="r"
    )


def criteria() -> list[LlmRubric]:
    return [
        LlmRubric(
            rubric=f"criterion: {word}?",
            judge=keyed,
            threshold=0.7,
            tolerance=0.05,
            name=word,
        )
        for word in ("accurate", "polite", "brief")
    ]


def whole(output: str, *, good: bool, failing: list[str] | None) -> tuple[Run, Suite]:
    checked = suite(
        Case(
            id="whole",
            reviewed_answer=answer(output, good=good, check=None, failing=failing),
        ),
        by_hand=False,
        assertions=criteria(),
    )
    return execute(checked, target, created_at=CREATED), checked


def against(found: Run) -> set[tuple[str, str]]:
    return {(c.check, c.direction) for c in contradicted(found)}


def test_good_on_everything_but_one_check_expects_that_check_alone_to_fail() -> None:
    """`good = false, failing = ["polite"]`: polite expected to fail, accurate
    and brief to pass. Each check is held to what was said of it."""
    # Agrees on all three: polite failed, the other two passed.
    found, checked = whole("accurate brief", good=False, failing=["polite"])
    assert against(found) == set()
    reviewed = found.results[0].reviewed
    assert reviewed is not None and reviewed.check is None
    assert len(reviewed.judged) == 3 and len(reviewed.failing) == 1
    # The judge passed polite, which the person said failed.
    found, _ = whole("accurate polite brief", good=False, failing=["polite"])
    assert against(found) == {("polite", "passed_no")}
    # The judge failed brief, which the person expected to pass.
    found, _ = whole("accurate", good=False, failing=["polite"])
    assert against(found) == {("brief", "failed_yes")}
    # A yes about the whole answer expects all three to pass.
    found, _ = whole("accurate polite", good=True, failing=None)
    assert against(found) == {("brief", "failed_yes")}
    assert run_exit_code(found, declared=checked.declared()) == EXIT_WORSE


def test_a_no_about_the_whole_answer_names_what_failed() -> None:
    with pytest.raises(ValueError, match="names no check that failed"):
        answer(RIGHT, good=False, check=None)
    with pytest.raises(ValueError, match="is not a judged check|no assertion"):
        whole("x", good=False, failing=["nowhere"])


# -- 3. today's files, unchanged --------------------------------------------- #


TODAY = {
    "id": "today",
    "reviewed_answer": {
        "output": RIGHT,
        "check": "llm_rubric",
        "good": True,
        "input": QUESTION,
    },
}


def test_a_cases_file_written_today_loads_as_it_did(tmp_path: Path) -> None:
    path = tmp_path / "cases.json"
    path.write_text(json.dumps([TODAY]), encoding="utf-8")
    [case] = read_cases(path)
    assert case.reviewed_answer == ReviewedAnswer(
        output=RIGHT, check="llm_rubric", good=True, input=QUESTION
    )
    loaded = case.reviewed_answer
    assert loaded is not None
    assert (loaded.failing, loaded.revised, loaded.held_out) == (None, None, False)
    assert loaded.held == (True, ())


def test_the_record_of_today_s_form_is_written_as_schema_24_wrote_it() -> None:
    """The run document's `reviewed` for an answer about one check, with a
    blind verdict, held in: the three keys and nothing else, so a document
    reads the same to a reader of either schema."""
    _, found = run(Case(id="today", reviewed_answer=answer(RIGHT, good=True)))
    reviewed = next(r for r in found.results if r.case_id == "today").reviewed
    assert reviewed is not None
    assert set(reviewed_to_dict(reviewed)) == {"check", "assertion_id", "good"}


def test_a_schema_24_document_reads_as_a_blind_verdict_held_in() -> None:
    _, found = run(Case(id="today", reviewed_answer=answer(RIGHT, good=False)))
    document = run_to_dict(found)
    document["schema_version"] = 24
    back = run_from_dict(upgrade_document(document))
    reviewed = next(r for r in back.results if r.case_id == "today").reviewed
    assert reviewed is not None
    assert (reviewed.good, reviewed.revised, reviewed.held_out) == (False, False, False)
    assert reviewed.blind == (False, ())
    assert reviewed == Reviewed(
        check="llm_rubric", assertion_id=reviewed.assertion_id, good=False
    )


# -- 2. a press and the command leave identical stores ----------------------- #


@pytest.fixture
def writing(root: Path):  # noqa: F811 — the fixture `root`, by its name
    with serving(root, allow_record=True) as (server, launch):
        assert launch is not None
        yield opened(server, launch)


AT = "2026-11-19T12:00:00+00:00"


def test_the_presses_on_a_chosen_answer_write_what_the_commands_write(
    writing: Served,
    tmp_path_factory: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Chosen about the whole answer, then a no naming its failing check, then
    a revision to a yes: by the page on one copy of the store and by the
    commands under its buttons on the other. The clock the revision reads is
    held, so the two `at` are one. (ADR 0061 §6, ADR 0067 §1 (b), §2)"""
    for module in ("digline.cli.view", "digline.cli.main"):
        monkeypatch.setattr(sys.modules[module], "utc_now_iso", lambda: AT)
    chosen = shlex.join(
        ["digline", "record", "import", *WRITES, "--choose", LONG_ID, "--whole"]
    )
    by_command(writing.root, chosen, monkeypatch)
    other = copy_of(writing.root, tmp_path_factory)
    [awaiting] = [c for c in cases_in(writing.root) if c["id"] == LONG_ID]
    assert "good" not in awaiting["reviewed_answer"]  # pyright: ignore[reportOperatorIssue]

    status, _, body = press(
        writing, LONG_ID, "bad", "Ada Lovelace", failing="llm_rubric"
    )
    assert status == 303, body
    by_command(
        other,
        shlex.join(
            [
                "digline",
                "record",
                "import",
                *WRITES,
                "--bad",
                LONG_ID,
                "--failing",
                "llm_rubric",
                "--by",
                "Ada Lovelace",
            ]
        ),
        monkeypatch,
    )
    assert tree(writing.root) == tree(other)

    revised = writing.ask(
        "POST",
        f"/review/acme/triage/{LONG_ID}",
        "locale=en&revise=good&by=Ada+Lovelace",
    )
    assert revised.status == 303, revised.body
    by_command(
        other,
        shlex.join(
            [
                "digline",
                "record",
                "revise",
                *WRITES,
                "--case",
                LONG_ID,
                "--good",
                "--by",
                "Ada Lovelace",
            ]
        ),
        monkeypatch,
    )
    assert tree(writing.root) == tree(other)
    [written] = [c for c in cases_in(writing.root) if c["id"] == LONG_ID]
    held = written["reviewed_answer"]
    assert isinstance(held, dict)
    assert held["good"] is False and held["failing"] == ["llm_rubric"]
    assert held["revised"] == {"good": True, "by": "Ada Lovelace", "at": AT}


def test_filling_a_verdict_leaves_every_other_case_s_bytes(
    writing: Served, monkeypatch: pytest.MonkeyPatch
) -> None:
    by_command(
        writing.root,
        shlex.join(["digline", "record", "import", *WRITES, "--choose", LONG_ID]),
        monkeypatch,
    )
    path = writing.root / CAPTURED
    before = path.read_text(encoding="utf-8").replace("\n", "\n")
    hand = '  {"id": "typed by hand",   "vars": {"q": "?"}}'
    path.write_text(before.replace("[\n", "[\n" + hand + ",\n", 1), encoding="utf-8")
    status, _, body = press(writing, LONG_ID, "good", "Ada")
    assert status == 303, body
    assert hand in path.read_text(encoding="utf-8")
