"""The agreement reading: the second pull request of ADR 0067 §10, with the
rulings of 2026-11-19 (P-1713).

§10 point 2 asks this pull request to measure **each figure against a count
made by hand on a fixture of known verdicts, with a mutation per figure** (in
the pull request's report). The fixture is `FIXTURE` below; every number the
tests assert is counted by hand in the comment beside the answer it comes
from, never computed from the code under test.

The figures: per check and role, blind and after review, each split into
agree, passed a no and failed a yes; the answers revised between the two;
the answers that could not be judged; the answers held in and held out; the
held-out total the readiness line reads; and the composite's disagreements
with its criteria, held in by name and held out by count.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from tests.test_projection import Table

from digline.core import (
    AgreementTally,
    Composite,
    Contains,
    JudgeReply,
    LlmRubric,
    Reviewed,
    Run,
    Score,
    Verdict,
    project_served,
    reviewed_agreement,
)
from digline.core.run import CaseResult
from digline.host.errors import UsageError
from digline.host.toml_suite import load_toml_suite
from digline.report import explain_text, facts, render_run_html, rule_words
from digline.run import Case, Suite
from digline.wire import explain_json
from digline.wire.explain import agreement_json

#: Identities in the shape a projection asks for, a digest, so the fixture
#: can be projected as it is.
IDS = {"accurate": "a" * 16, "polite": "b" * 16, "overall": "c" * 16}
ACC, POL, OV = IDS["accurate"], IDS["polite"], IDS["overall"]
WHOLE = (OV, ACC, POL)
COMPOSITES = (Composite(OV, (ACC, POL)),)


def verdict(name: str, status: str) -> Verdict:
    score = {"pass": 1.0, "fail": 0.0, "error": None}[status]
    return Verdict(
        score=Score(name=name, score=score),
        threshold=0.5,
        status=status,  # pyright: ignore[reportArgumentType]
        reason="the judge could not answer" if score is None else "the judge's words",
        tolerance=0.05,
        judged=True,
        assertion_id=IDS[name],
    )


def one(case_id: str, status: str, **said: Any) -> CaseResult:
    """A reviewed answer about `accurate` alone, judged `status`."""
    return CaseResult(
        case_id,
        (verdict("accurate", status),),
        reviewed=Reviewed(check="accurate", assertion_id=ACC, **said),
    )


def whole(case_id: str, ov: str, acc: str, pol: str, **said: Any) -> CaseResult:
    """A reviewed answer about the whole answer: `overall`, `accurate` and
    `polite` judged on it, `overall` the composite of the other two."""
    return CaseResult(
        case_id,
        (verdict("overall", ov), verdict("accurate", acc), verdict("polite", pol)),
        reviewed=Reviewed(check=None, assertion_id=None, judged=WHOLE, **said),
    )


#: Each answer, and what it adds, counted by hand. B is the blind figure, A
#: the figure after review; agree / passed a no / failed a yes.
FIXTURE = (
    # accurate, held in
    one("a1", "pass", good=True),  # B agree, A agree
    one("a2", "pass", good=False),  # B passed_no, A passed_no
    one("a3", "fail", good=True),  # B failed_yes, A failed_yes
    # Revised to a yes, so the blind verdict was a no: B passed_no, A agree,
    # and one revised.
    one("a4", "pass", good=True, revised=True),
    one("a5", "error", good=True),  # unjudged: in neither figure
    # accurate, held out
    one("a6", "pass", good=True, held_out=True),  # agree, agree
    one("a7", "fail", good=False, held_out=True),  # agree, agree
    one("a8", "fail", good=True, held_out=True),  # failed_yes, failed_yes
    # Awaiting a verdict: in no figure and in no count. (§1 (a))
    one("a9", "pass", good=None),
    # The whole answer, held in: a no expecting `polite` alone to fail.
    # overall agree, accurate agree, polite agree. The composite passed and
    # its criterion `polite` failed: a mismatch, named.
    whole("w1", "pass", "pass", "fail", good=False, failing=(POL,)),
    # The whole answer, held out, a yes: overall failed_yes, accurate agree,
    # polite agree. The composite failed and each criterion passed: a
    # mismatch, held out, so counted and never named.
    whole("w2", "fail", "pass", "pass", good=True, held_out=True),
    # The whole answer, held in, revised to a yes from a blind no that
    # expected `accurate` to fail. After review every check agrees; blind,
    # accurate passed a no, overall and polite agree. One revised, on
    # accurate alone.
    whole(
        "w3",
        "pass",
        "pass",
        "pass",
        good=True,
        revised=True,
        blind_failing=(ACC,),
    ),
)

#: Hand counts, per (check, held out).
EXPECTED = {
    # a1 a2 a3 a4 (a5 unjudged) w1 w3
    ("accurate", False): (
        AgreementTally(agree=2, passed_no=3, failed_yes=1),  # a1 w1 | a2 a4 w3 | a3
        AgreementTally(agree=4, passed_no=1, failed_yes=1),  # a1 a4 w1 w3 | a2 | a3
        2,  # revised: a4, w3
        1,  # unjudged: a5
    ),
    # a6 a7 a8 w2
    ("accurate", True): (
        AgreementTally(agree=3, passed_no=0, failed_yes=1),
        AgreementTally(agree=3, passed_no=0, failed_yes=1),
        0,
        0,
    ),
    # w1 w3
    ("overall", False): (AgreementTally(agree=2), AgreementTally(agree=2), 0, 0),
    # w2
    ("overall", True): (
        AgreementTally(failed_yes=1),
        AgreementTally(failed_yes=1),
        0,
        0,
    ),
    ("polite", False): (AgreementTally(agree=2), AgreementTally(agree=2), 0, 0),
    ("polite", True): (AgreementTally(agree=1), AgreementTally(agree=1), 0, 0),
}


def fixture_run(*results: CaseResult) -> Run:
    return Run(
        tenant="acme",
        environment="dev",
        suite="support",
        config_hash="0" * 16,
        created_at="2026-01-01T00:00:00+00:00",
        results=results or FIXTURE,
    )


def read() -> Any:
    reading = reviewed_agreement(fixture_run(), COMPOSITES)
    assert reading is not None
    return reading


# -- each figure against the hand count -------------------------------------- #


def test_each_check_and_role_counts_what_was_counted_by_hand() -> None:
    reading = read()
    found = {
        (row.check, row.held_out): (row.blind, row.after, row.revised, row.unjudged)
        for row in reading.rows
    }
    assert found == EXPECTED


def test_the_answers_held_in_and_held_out_are_counted_without_the_awaiting() -> None:
    """Held in: a1 to a5, w1, w3, seven. Held out: a6, a7, a8, w2, four. a9
    awaits a verdict and is in neither."""
    reading = read()
    assert (reading.held_in, reading.held_out) == (7, 4)


def test_the_held_out_total_sums_every_check_after_review() -> None:
    """accurate 3 of 4, overall 0 of 1, polite 1 of 1: 4 of 6 held out.
    Held in: 4 of 6 + 2 of 2 + 2 of 2, 8 of 10."""
    reading = read()
    assert reading.total(held_out=True) == AgreementTally(
        agree=4, passed_no=0, failed_yes=2
    )
    assert reading.total(held_out=False) == AgreementTally(
        agree=8, passed_no=1, failed_yes=1
    )


def test_the_composite_is_read_against_the_conjunction_of_its_criteria() -> None:
    """w1: overall passed, polite failed. w2: overall failed, each criterion
    passed. w3: all three passed, no mismatch."""
    reading = read()
    found = [
        (m.case_id, m.composite, m.held_out, m.composite_passed, m.failed)
        for m in reading.mismatches
    ]
    assert found == [
        ("w1", "overall", False, True, ("polite",)),
        ("w2", "overall", True, False, ()),
    ]


def test_no_composite_is_read_where_the_suite_declares_none() -> None:
    reading = reviewed_agreement(fixture_run())
    assert reading is not None and reading.mismatches == ()


def test_a_composite_whose_criterion_errored_is_passed_over() -> None:
    """No conjunction to read: the answer is in no mismatch."""
    reading = reviewed_agreement(
        fixture_run(whole("w4", "pass", "error", "fail", good=False, failing=(POL,))),
        COMPOSITES,
    )
    assert reading is not None and reading.mismatches == ()
    # The control: the same answer with its criterion judged is one.
    reading = reviewed_agreement(
        fixture_run(whole("w4", "pass", "pass", "fail", good=False, failing=(POL,))),
        COMPOSITES,
    )
    assert reading is not None and len(reading.mismatches) == 1


def test_a_run_whose_reviewed_answers_all_await_a_verdict_has_no_reading() -> None:
    assert reviewed_agreement(fixture_run(one("a9", "pass", good=None))) is None
    # The control: one answer with a verdict beside it is read.
    assert reviewed_agreement(
        fixture_run(one("a9", "pass", good=None), one("a1", "pass", good=True))
    )


def test_stability_is_said_not_measured_rather_than_given_a_state() -> None:
    """ADR 0067 §3 waits for its pull request (4): until then no answer is
    set apart as unstable, and the reading says why, as a fact. (P-1713)"""
    assert read().stability_measured is False


# -- the renderings: explain, the report, --json ----------------------------- #


def lines(locale: str = "en") -> list[str]:
    run = fixture_run()
    return list(
        explain_text(
            facts(run, composites=COMPOSITES),
            locale=locale,  # pyright: ignore[reportArgumentType]
            rule=rule_words("a yes means the reply is right", locale=locale),  # pyright: ignore[reportArgumentType]
        )
    )


def test_explain_says_each_row_the_readiness_and_the_stability() -> None:
    said = lines()
    assert (
        "accurate, held in: blind, 2 of 6 agree (3 passed a no, 1 failed a yes); "
        "after review, 4 of 6 agree (1 passed a no, 1 failed a yes). 2 answers "
        "were revised between the two. 1 answer could not be judged on it."
    ) in said
    assert (
        "overall, held out: blind, 0 of 1 agree (0 passed a no, 1 failed a yes); "
        "after review, 0 of 1 agree (0 passed a no, 1 failed a yes)."
    ) in said
    assert (
        "Held out: 4 of 6 verdicts agree after review, check by check; 7 held-in "
        "answers served the tuning and are not counted here."
    ) in said
    assert (
        "No answer is set apart as unstable: this run's stability was not "
        "measured, so every answer is counted."
    ) in said
    assert (
        "What a yes means, in this suite's words: a yes means the reply is right"
        in said
    )


def agreement_block(said: list[str]) -> str:
    """The agreement reading's lines alone: from its heading to the blank line
    that closes it. The gate's own contradiction sentence, above it, names
    every contradicted answer, held out or not (ADR 0059 §1, ADR 0067 §3:
    the gate is what it is today), and is not the reading of §1 (c)."""
    start = said.index("How the judge agrees with the person")
    end = said.index("", start)
    return "\n".join(said[start:end])


def test_a_held_out_composite_mismatch_is_counted_and_never_named() -> None:
    said = agreement_block(lines())
    assert "w1: overall passed, polite failed" in said
    assert "1 held-out answer on which a composite" in said
    assert "w2" not in said


def test_without_a_held_out_answer_the_reading_says_so() -> None:
    run = fixture_run(*(c for c in FIXTURE if not (c.reviewed and c.reviewed.held_out)))
    said = explain_text(facts(run), locale="en")
    assert (
        "No reviewed answer is held out: the agreement above was measured on the "
        "answers the rubric was tuned on."
    ) in said
    assert not any(line.startswith("Held out:") for line in said)


def test_the_italian_reading_says_the_same_figures() -> None:
    said = lines("it")
    assert (
        "accurate, usate per la messa a punto: alla cieca, 2 su 6 d'accordo "
        "(3 promosse dove la persona ha detto no, 1 bocciate dove ha detto sì); "
        "dopo la revisione, 4 su 6 d'accordo (1 promosse dove la persona ha "
        "detto no, 1 bocciate dove ha detto sì). 2 risposte sono state riviste "
        "tra le due. 1 risposta non ha potuto essere giudicata."
    ) in said
    assert any(line.startswith("Tenute da parte: 4 verdetti su 6") for line in said)


def test_the_report_carries_the_same_lines() -> None:
    document = render_run_html(fixture_run(), locale="en", composites=COMPOSITES)
    assert "How the judge agrees with the person" in document
    assert "Held out: 4 of 6 verdicts agree after review" in document
    assert "w1: overall passed, polite failed" in document
    # The review rule is the terminal's, never the document's.
    assert "What a yes means" not in document


def test_the_report_of_a_run_without_reviewed_answers_is_unchanged() -> None:
    run = fixture_run(CaseResult("plain", (verdict("accurate", "pass"),)))
    assert "How the judge agrees" not in render_run_html(run, locale="en")


def test_explain_json_carries_the_figures_and_no_held_out_case() -> None:
    run = fixture_run()
    document = json.loads(
        json.dumps(
            explain_json(
                facts(run, composites=COMPOSITES), reading="run", exit_code=1, run=run
            )
        )
    )
    [fact] = [f for f in document["facts"] if f.get("kind") == "agreement"]
    agreement = fact["agreement"]
    assert fact["count"] == 11
    assert (agreement["held_in"], agreement["held_out"]) == (7, 4)
    assert agreement["stability_measured"] is False
    [accurate] = [
        row
        for row in agreement["checks"]
        if row["check"] == "accurate" and not row["held_out"]
    ]
    assert accurate == {
        "check": "accurate",
        "assertion_id": ACC,
        "held_out": False,
        "blind": {"agree": 2, "passed_no": 3, "failed_yes": 1},
        "after": {"agree": 4, "passed_no": 1, "failed_yes": 1},
        "revised": 2,
        "unjudged": 1,
    }
    assert agreement["composites"] == [
        {
            "case_id": "w1",
            "composite": "overall",
            "composite_passed": True,
            "failed": ["polite"],
        }
    ]
    assert agreement["composites_held_out"] == 1
    assert "w2" not in json.dumps(agreement)
    # The rule is the terminal's alone. (ADR 0012 §4)
    assert "a yes means" not in json.dumps(document)


# -- `criteria`, declared ---------------------------------------------------- #


def judge(prompt: str) -> JudgeReply:
    return JudgeReply(score=1.0, reason="r")


def rubric(name: str) -> LlmRubric:
    return LlmRubric(rubric=name, judge=judge, threshold=0.7, tolerance=0.05, name=name)


def suite(**changes: Any) -> Suite:
    fields: dict[str, Any] = {
        "tenant": "acme",
        "environment": "dev",
        "name": "support",
        "cases": [Case(id="c")],
        "assertions": [rubric("overall"), rubric("accurate"), rubric("polite")],
    }
    fields.update(changes)
    return Suite(**fields)


def test_criteria_resolve_to_identities_and_leave_the_hash_alone() -> None:
    declared = suite(criteria={"overall": ["accurate", "polite"]})
    by_name = {a.name: a.identity for a in declared.assertions}
    assert declared.composites() == (
        Composite(by_name["overall"], (by_name["accurate"], by_name["polite"])),
    )
    assert declared.config_hash() == suite().config_hash()


@pytest.mark.parametrize(
    ("criteria", "said"),
    [
        ({"overall": ["overall"]}, "a criterion of itself"),
        ({"overall": ["accurate"], "polite": ["accurate"]}, "two composites"),
        ({"overall": ["nowhere"]}, "which no assertion is called"),
        ({"overall": []}, "with no criteria"),
    ],
)
def test_each_wrong_criteria_is_refused_by_name(
    criteria: dict[str, list[str]], said: str
) -> None:
    with pytest.raises(ValueError, match=said):
        suite(criteria=criteria)


def test_a_criterion_that_is_not_judged_is_refused() -> None:
    with pytest.raises(ValueError, match="not a judged check"):
        suite(
            assertions=[rubric("overall"), Contains(needle="x")],
            criteria={"overall": ["contains"]},
        )


TOML = """
[suite]
tenant = "acme"
environment = "dev"
name = "support"
cases = "cases.json"

[[assertions]]
type = "llm_rubric"
name = "overall"
rubric = "is it right and polite?"
judge = "openai/gpt-5-mini"
threshold = 0.7
tolerance = 0.05
{criteria}

[[assertions]]
type = "llm_rubric"
name = "accurate"
rubric = "is it right?"
judge = "openai/gpt-5-mini"
threshold = 0.7
tolerance = 0.05

[target]
type = "http"
url = "http://127.0.0.1:9/answer"
output_path = "data"

  [target.body]
  question = "case.vars.question"
"""


def write(tmp_path: Path, text: str) -> Path:
    (tmp_path / "cases.json").write_text('[{"id": "c", "vars": {"question": "?"}}]')
    path = tmp_path / "suite.toml"
    path.write_text(text)
    return path


def test_criteria_is_read_off_the_composite_s_table(tmp_path: Path) -> None:
    path = write(tmp_path, TOML.format(criteria='criteria = ["accurate"]'))
    loaded, _ = load_toml_suite(path)
    assert loaded.criteria == {"overall": ("accurate",)}
    # The control: the same suite without the key declares no composite.
    plain, _ = load_toml_suite(write(tmp_path, TOML.format(criteria="")))
    assert plain.composites() == ()
    assert plain.config_hash() == loaded.config_hash()


def test_criteria_in_the_suite_table_is_refused_with_where_it_goes(
    tmp_path: Path,
) -> None:
    text = TOML.format(criteria="").replace(
        'cases = "cases.json"',
        'cases = "cases.json"\ncriteria = {overall = ["accurate"]}',
    )
    with pytest.raises(UsageError, match="a key of the composite check"):
        load_toml_suite(write(tmp_path, text))


def test_a_projected_reading_names_no_check_and_one_token_per_check() -> None:
    """Under a projection (the MCP `explain` with `--names project`), a row's
    name is the verdict's own token: never the name in clear, and never a
    reviewed answer's `check` token beside a verdict's for the same check."""
    served = project_served(fixture_run(), Table())
    reading = reviewed_agreement(served, COMPOSITES)
    assert reading is not None
    said = json.dumps(agreement_json(reading))
    for name in ("accurate", "polite", "overall", "w1"):
        assert f'"{name}"' not in said, name
    verdicts = {
        v.assertion_id: v.score.name for case in served.results for v in case.verdicts
    }
    assert all(row.check == verdicts[row.assertion_id] for row in reading.rows)
    # The control: read in clear, the same rows carry the names.
    assert {row.check for row in read().rows} == {"accurate", "polite", "overall"}
