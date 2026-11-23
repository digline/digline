"""Stability at a fixed rubric, and the contradiction accepted by name: the
fourth pull request of ADR 0067 §10, with the rulings of 2026-11-22 (P-1716,
P-1717).

What is held here, each with the mutation that turns it red, listed in the
session's report:

- **an acceptance is refused on a stable contradiction**, by name;
- **taken where the samples split**, and recorded with the judgements that
  went against the person;
- **taken where the runs read disagree**, the judgements counted across them;
- **not carried to a later run**: the next run's promotion is refused until
  it is accepted again;
- **a held-out answer is named only with `--show-held-out`**, and the
  report, which has no options, counts it and says where it is shown;
- **an unstable verdict is in neither figure** of the agreement reading;
- **the number of runs read** is said, in the reading and in `--json`;
- around them: `judge_min` and `judge_max` across the threshold, an errored
  sample, the refusals of an acceptance that names nobody, a case the run
  does not carry or one no judge contradicted, compare's sentence in en and
  it, and the reference's record of the acceptance.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any

from tests._helpers import cli

from digline.core import (
    AcceptedContradiction,
    CaseResult,
    Reviewed,
    Run,
    Score,
    Verdict,
    reviewed_agreement,
    reviewed_stability,
    run_from_json,
)
from digline.report import explain_text, facts
from digline.report.render import accepted_fact, render_run_html
from digline.store.promotion import refusal_for_acceptances
from digline.wire import EXIT_OK, EXIT_USAGE, explain_json

TONE = "t" * 16
CREATED = "2026-11-22T09:00:00+00:00"
LATER = "2026-11-22T10:00:00+00:00"


def verdict(status: str, scores: tuple[float, ...] = (), **metadata: Any) -> Verdict:
    """A judged verdict on `tone`, at a threshold of 0.6: `scores` are its
    samples where it kept any."""
    score = (
        sum(scores) / len(scores)
        if scores
        else {"pass": 1.0, "fail": 0.0, "error": None}[status]
    )
    return Verdict(
        score=Score(
            name="tone",
            score=None if status == "error" else score,
            samples=scores,
            sample_min=min(scores) if scores else None,
            sample_max=max(scores) if scores else None,
            metadata=metadata,
        ),
        threshold=0.6,
        status=status,  # pyright: ignore[reportArgumentType]
        reason="the judge's words",
        tolerance=0.05,
        judged=True,
        assertion_id=TONE,
    )


def answer(
    case_id: str, judged: Verdict, *, good: bool, held_out: bool = False
) -> CaseResult:
    return CaseResult(
        case_id,
        (judged,),
        reviewed=Reviewed(
            check="tone", assertion_id=TONE, good=good, held_out=held_out
        ),
    )


def run_of(*results: CaseResult, created_at: str = CREATED) -> Run:
    return Run(
        tenant="acme",
        environment="dev",
        suite="support",
        config_hash="0" * 16,
        created_at=created_at,
        results=results,
    )


# -- stability, read on the core --------------------------------------------- #


def test_one_run_measures_nothing_across_runs_and_its_split_samples_are_unstable() -> (
    None
):
    """Mutation: dropping `samples` from `_why` turns it red."""
    run = run_of(
        answer("steady", verdict("pass", (1.0, 1.0, 1.0)), good=True),
        answer("split", verdict("pass", (1.0, 1.0, 0.0)), good=False),
    )
    stability = reviewed_stability(run)
    assert (stability.runs_read, stability.measured) == (1, False)
    assert [(u.case_id, u.why) for u in stability.unstable] == [("split", "samples")]


def test_an_errored_sample_makes_a_verdict_unstable() -> None:
    run = run_of(
        answer(
            "errored",
            verdict("pass", (1.0, 1.0), samples=3, errored_samples=1),
            good=False,
        )
    )
    assert [u.why for u in reviewed_stability(run).unstable] == ["samples"]


def test_judge_samples_on_the_two_sides_of_the_threshold_are_unstable() -> None:
    """Decision 4 of P-1717. Mutation: dropping the `judge_samples` branch of
    `_why` turns it red."""
    wide = verdict("pass", judge_samples=3, judge_min=0.2, judge_max=1.0)
    narrow = verdict("pass", judge_samples=3, judge_min=0.7, judge_max=1.0)
    run = run_of(answer("wide", wide, good=True), answer("narrow", narrow, good=True))
    assert [(u.case_id, u.why) for u in reviewed_stability(run).unstable] == [
        ("wide", "judge_samples")
    ]


def test_runs_read_are_those_holding_one_of_its_answers_at_the_same_identity() -> None:
    """Decision 2 of P-1717: a run is read where it holds one of this run's
    reviewed answers judged by a check of the same identity. Mutation:
    counting every other run as read turns it red."""
    run = run_of(answer("a", verdict("pass"), good=True))
    same = run_of(answer("a", verdict("pass"), good=True), created_at=LATER)
    moved = dataclasses.replace(
        same,
        created_at="2026-11-22T11:00:00+00:00",
        results=(
            CaseResult(
                "a",
                (dataclasses.replace(verdict("fail"), assertion_id="u" * 16),),
                reviewed=Reviewed(check="tone", assertion_id="u" * 16, good=True),
            ),
        ),
    )
    stability = reviewed_stability(run, (same, moved))
    assert (stability.runs_read, stability.measured, stability.unstable) == (
        2,
        True,
        (),
    )
    reading = reviewed_agreement(run, (), stability)
    assert reading is not None
    assert (reading.runs_read, reading.stability_measured) == (2, True)
    said = explain_text(facts(run, stability=stability), locale="en")
    assert (
        "Stability was read across 2 runs of this suite with these checks: every "
        "verdict held." in said
    )
    payload = json.loads(
        json.dumps(
            explain_json(facts(run, stability=stability), reading="run", exit_code=0)
        )
    )
    [tally] = [f for f in payload["facts"] if f.get("kind") == "agreement"]
    assert tally["agreement"]["runs_read"] == 2


def test_a_verdict_that_changed_between_runs_is_unstable_and_its_judgements_count() -> (
    None
):
    """The judgements across every run read: 3 of 6 against the person.
    Mutation: counting this run's judgements alone turns it red."""
    run = run_of(answer("flip", verdict("pass", (1.0, 1.0, 1.0)), good=False))
    other = run_of(
        answer("flip", verdict("fail", (0.0, 0.0, 0.0)), good=False),
        created_at=LATER,
    )
    stability = reviewed_stability(run, (other,))
    assert [(u.case_id, u.why) for u in stability.unstable] == [("flip", "runs")]
    judged = stability.judged("flip", TONE)
    assert judged is not None
    assert (judged.against, judged.of) == (3, 6)


def test_an_unstable_verdict_is_in_neither_figure_and_is_named() -> None:
    """ADR 0067 §3. Hand count: `agree` agrees and `split` passed a no but is
    unstable, so the figure after review is 1 of 1, and `split` is named
    apart. Mutation: counting an unstable verdict in the figures turns it
    red."""
    run = run_of(
        answer("agree", verdict("pass", (1.0, 1.0, 1.0)), good=True),
        answer("split", verdict("pass", (1.0, 1.0, 0.0)), good=False),
    )
    reading = reviewed_agreement(run)
    assert reading is not None
    [row] = reading.rows
    assert (row.after.agree, row.after.passed_no, row.after.judged) == (1, 0, 1)
    assert row.unstable == 1
    said = explain_text(facts(run), locale="en")
    assert (
        "1 verdict is unstable and counted in neither figure: split, tone (its "
        "samples split)." in said
    )


# -- the held-out answers, named on request ---------------------------------- #


def _agreement_json(run: Run, *, show_held_out: bool) -> Any:
    payload = json.loads(
        json.dumps(
            explain_json(
                facts(run), reading="run", exit_code=1, show_held_out=show_held_out
            )
        )
    )
    [tally] = [f for f in payload["facts"] if f.get("kind") == "agreement"]
    return tally["agreement"]


def _agreement_block(text: str) -> str:
    """The agreement reading alone: the gate's sentence above it and the
    sections below it name a contradiction whatever the option, as the gate
    does (§3)."""
    return text.split("How the judge agrees")[1].split("How it was set up")[0]


HELD = run_of(
    answer("in-no", verdict("pass"), good=False),
    answer("aside-no", verdict("pass"), good=False, held_out=True),
)


def test_a_held_out_disagreement_is_counted_and_named_only_on_request() -> None:
    """ADR 0067 §1 (e). Mutation: `agreement_lines` ignoring `show_held_out`
    turns it red."""
    hidden = _agreement_block("\n".join(explain_text(facts(HELD), locale="en")))
    assert "aside-no" not in hidden
    assert (
        "1 held-out verdict disagrees with the person, counted and not named: "
        "digline explain --show-held-out names it." in hidden
    )
    shown = explain_text(facts(HELD), locale="en", show_held_out=True)
    assert (
        "The held-out answers, shown on request: read before the rubric is "
        "frozen, these answers are no longer held out." in shown
    )
    assert (
        "aside-no, tone, held out: passed where the person said no. The judge "
        "said: the judge's words" in shown
    )
    counted = _agreement_json(HELD, show_held_out=False)
    assert counted["held_out_disagreed"] == 1
    assert counted["held_out_disagreements"] == []
    named = _agreement_json(HELD, show_held_out=True)
    assert named["held_out_disagreements"] == [
        {"case_id": "aside-no", "check": "tone", "direction": "passed_no"}
    ]


def test_the_gate_sentence_still_names_a_held_out_contradiction() -> None:
    """The gate is the gate (§3): its sentence names every contradiction,
    held out or not, with or without the option."""
    said = "\n".join(explain_text(facts(HELD), locale="en"))
    assert "aside-no" in said.split("How the judge agrees")[0]


def test_the_report_counts_a_held_out_answer_and_sends_the_reader_to_explain() -> None:
    """The report has no options (§1 (e), P-1716). Mutation: dropping the
    held-out branch of `reviewed_section` turns it red."""
    page = render_run_html(HELD, locale="en")
    section = page.split("What the judge said of the reviewed answers")[1].split(
        "</details>"
    )[0]
    assert "in-no" in section
    assert "aside-no" not in section
    assert (
        "1 held-out answer is counted here and not shown: digline explain "
        "--show-held-out shows it." in section
    )
    italian = render_run_html(HELD, locale="it")
    assert "digline explain --show-held-out la mostra." in italian


# -- the acceptance, on the promotion's own terms ----------------------------- #


SPLIT = run_of(answer("split", verdict("pass", (1.0, 1.0, 0.0)), good=False))
STEADY = run_of(answer("steady", verdict("pass", (1.0, 1.0, 1.0)), good=False))


def test_an_acceptance_names_a_person_a_carried_case_and_a_contradiction() -> None:
    stability = reviewed_stability(SPLIT)
    nobody = refusal_for_acceptances(SPLIT, {"split"}, " ", stability=stability)
    assert nobody is not None and "names nobody" in str(nobody)
    typo = refusal_for_acceptances(SPLIT, {"splt"}, "Ada", stability=stability)
    assert typo is not None and "carries no case splt" in str(typo)
    agreed = run_of(answer("fine", verdict("pass", (1.0, 1.0, 0.0)), good=True))
    nothing = refusal_for_acceptances(
        agreed, {"fine"}, "Ada", stability=reviewed_stability(agreed)
    )
    assert nothing is not None and "no judge contradicted the person on fine" in (
        str(nothing)
    )
    assert refusal_for_acceptances(SPLIT, {"split"}, "Ada", stability=stability) is None


def test_an_acceptance_on_a_stable_contradiction_is_refused_by_name() -> None:
    """ADR 0067 §6. Mutation: `refusal_for_acceptances` not asking stability
    turns it red."""
    refused = refusal_for_acceptances(
        STEADY, {"steady"}, "Ada", stability=reviewed_stability(STEADY)
    )
    assert refused is not None
    assert (
        "`steady`'s judge contradicted the person on every judgement of tone, "
        "across the one run read: correct the rubric or revise the verdict"
    ) in str(refused)


def test_compare_says_an_accepted_contradiction_in_en_and_it() -> None:
    accepted = (
        AcceptedContradiction(
            case_id="refund-tone",
            check="tone",
            direction="passed_no",
            against=2,
            judgements=3,
            by="Ada",
            at="2026-11-14T10:00:00+00:00",
        ),
    )
    assert accepted_fact(accepted, "en") == (
        "1 contradiction accepted at promotion: refund-tone, `tone`, passed where "
        "the person said no, 2 of 3 judgements, by Ada, 2026-11-14."
    )
    assert accepted_fact(accepted, "it") == (
        "1 contraddizione accettata alla promozione: refund-tone, `tone`, "
        "promossa dove la persona ha detto no, 2 giudizi su 3 contro la persona, "
        "da Ada, 2026-11-14."
    )
    assert accepted_fact((), "en") == ""


# -- end to end: promote, compare, explain ------------------------------------ #


SUITE_PY = """
from pathlib import Path

from digline.core import JudgeReply, LlmRubric
from digline.run import Case, Response, ReviewedAnswer, Suite

FLIP = Path(__file__).with_name("flip.txt")
SEEN = {}


def judge(prompt):
    if "Flip" in prompt:
        state = FLIP.read_text(encoding="utf-8").strip() if FLIP.exists() else "pass"
        return JudgeReply(score=1.0 if state == "pass" else 0.0, reason="flip")
    if "Split" in prompt:
        n = SEEN.get("split", 0)
        SEEN["split"] = n + 1
        return JudgeReply(score=0.0 if n % 3 == 2 else 1.0, reason="split")
    return JudgeReply(score=1.0, reason="passes everything")


def answer(case_id, output, good, held_out=False):
    return Case(
        id=case_id,
        reviewed_answer=ReviewedAnswer(
            output=output,
            check="tone",
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
        LlmRubric(
            rubric="polite", judge=judge, threshold=0.6, tolerance=0.05, name="tone"
        )
    ],
    cases=[
        answer("yes-good", "Fourteen days.", True),
CASES
    ],
    samples=3,
    min_agreement="2/3",
)


def target(case):
    return Response(output="Fourteen days.", input="How long?")
"""


def _write(root: Path, cases: str) -> None:
    (root / "suite.py").write_text(SUITE_PY.replace("CASES", cases), encoding="utf-8")


def _run(root: Path) -> str:
    done = cli(root, "run", "--suite", "suite.py")
    assert done.returncode in (EXIT_OK, 1), done.stderr
    return sorted((root / ".digline" / "acme" / "runs").rglob("*.json"))[-1].stem


def _promote(root: Path, key: str, *accepting: str, replacing: str = "none") -> Any:
    extra = [part for case in accepting for part in ("--accept-contradiction", case)]
    return cli(
        root,
        "promote",
        "--suite",
        "suite.py",
        "--run",
        key,
        "--replacing",
        replacing,
        *extra,
        *(("--by", "Ada") if accepting else ()),
    )


def _reference(root: Path) -> Run:
    path = next((root / ".digline" / "acme" / "baselines").rglob("*.json"))
    return run_from_json(path.read_text(encoding="utf-8"))


def test_a_stable_contradiction_is_refused_at_promotion_across_two_runs(
    tmp_path: Path,
) -> None:
    _write(tmp_path, '        answer("steady-no", "A year.", False),')
    first = _run(tmp_path)
    _run(tmp_path)
    refused = _promote(tmp_path, first, "steady-no")
    assert refused.returncode == EXIT_USAGE, refused.stderr
    assert (
        "`steady-no`'s judge contradicted the person on every judgement of tone, "
        "across the 2 runs read: correct the rubric or revise the verdict"
    ) in refused.stderr


def test_split_samples_are_accepted_recorded_said_and_not_carried(
    tmp_path: Path,
) -> None:
    """Taken where the samples split, recorded with 2 of 3 judgements against
    the person, said by compare, and refused again at the next run's
    promotion. Mutation: condition 12 passing over what the reference in
    force accepted turns the last half red."""
    _write(tmp_path, '        answer("split-no", "Split.", False),')
    first = _run(tmp_path)
    taken = _promote(tmp_path, first, "split-no")
    assert taken.returncode == EXIT_OK, taken.stderr
    assert (
        "contradiction accepted at promotion: split-no, tone, 2 of 3 judgements "
        "against the person, by Ada" in taken.stdout
    )
    [accepted] = _reference(tmp_path).accepted_contradictions
    assert (
        accepted.case_id,
        accepted.check,
        accepted.direction,
        accepted.against,
        accepted.judgements,
        accepted.by,
    ) == ("split-no", "tone", "passed_no", 2, 3, "Ada")

    second = _run(tmp_path)
    compared = cli(tmp_path, "compare", "--suite", "suite.py", "--run", second)
    assert (
        "1 contradiction accepted at promotion: split-no, `tone`, passed where the "
        "person said no, 2 of 3 judgements, by Ada" in compared.stdout
    ), compared.stdout + compared.stderr

    again = _promote(tmp_path, second, replacing=first)
    assert again.returncode == EXIT_USAGE, again.stderr
    assert "the judge contradicted a person on 1 reviewed answer" in again.stderr


def test_a_verdict_the_runs_disagree_on_is_accepted_with_every_judgement(
    tmp_path: Path,
) -> None:
    """One run read: stable, refused. A second run that judged it the other
    way: unstable, taken, 3 of 6 judgements against the person. Mutation:
    dropping `runs` from `_why` turns it red."""
    _write(tmp_path, '        answer("flip-no", "Flip.", False),')
    first = _run(tmp_path)
    alone = _promote(tmp_path, first, "flip-no")
    assert alone.returncode == EXIT_USAGE, alone.stderr
    assert "across the one run read" in alone.stderr

    (tmp_path / "flip.txt").write_text("fail", encoding="utf-8")
    _run(tmp_path)
    taken = _promote(tmp_path, first, "flip-no")
    assert taken.returncode == EXIT_OK, taken.stderr
    [accepted] = _reference(tmp_path).accepted_contradictions
    assert (accepted.against, accepted.judgements) == (3, 6)

    explained = cli(tmp_path, "explain", "--suite", "suite.py", "--run", first)
    assert (
        "Stability was read across 2 runs of this suite with these checks."
        in explained.stdout
    ), explained.stdout + explained.stderr
    assert "flip-no, tone (the runs read disagree)" in explained.stdout


def test_explain_show_held_out_names_what_it_otherwise_counts(tmp_path: Path) -> None:
    _write(
        tmp_path,
        '        answer("in-no", "A year.", False),\n'
        '        answer("aside-no", "A year.", False, held_out=True),',
    )
    key = _run(tmp_path)
    plain = cli(tmp_path, "explain", "--suite", "suite.py", "--run", key)
    assert "aside-no" not in _agreement_block(plain.stdout), plain.stdout
    shown = cli(
        tmp_path, "explain", "--suite", "suite.py", "--run", key, "--show-held-out"
    )
    assert (
        "aside-no, tone, held out: passed where the person said no. The judge said: "
        "mean of 3 samples" in shown.stdout
    ), shown.stdout + shown.stderr
