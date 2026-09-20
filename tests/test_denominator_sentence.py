"""The denominator in the sentence, not in a column.

"43 of 50 cases judged, 7 could not be" rather than a bare figure, in the three
places a run is read: the headline `compare` prints and the report opens with,
the reading `explain` gives, and the line naming each run-level figure. It is
the third question of the denominator article turned on digline itself: the
counts were recorded all along — in the verdict's metadata and in a column of
the HTML report — and were never where somebody reads.

Presentation only. No fact is added and nothing crosses the wire that did not
before; what changes is that the sentence carries the count it is a count of.
And a run that left nothing out reads as it always did — no parenthesis of
zeros on every line of a clean suite.
"""

from __future__ import annotations

import re

import pytest

from digline.core import (
    Accuracy,
    CaseOutcome,
    CaseResult,
    Run,
    Score,
    Status,
    Verdict,
    compare,
    denominator,
)
from digline.report import (
    explain_text,
    facts,
    headline,
    render_html,
    render_run_html,
    summary_lines,
)
from digline.report.render import denominator_sentence
from digline.wire import explain_json

CREATED = "2026-09-19T10:00:00+00:00"
LATER = "2026-09-19T11:00:00+00:00"
CHECK = "classified"


def outcome(case_id: str, status: Status, *, canary: bool = False) -> CaseOutcome:
    score = {"pass": 1.0, "fail": 0.0, "error": None}[status]
    return CaseOutcome(
        case_id,
        None if canary else "positive",
        Verdict(
            score=Score(name=CHECK, score=score),
            threshold=1.0,
            status=status,
            reason="the judge explained itself",
            assertion_id=f"id-{CHECK}",
        ),
        canary=canary,
    )


def suspended(case_id: str) -> CaseOutcome:
    return CaseOutcome(case_id, "positive", None)


def run_of(*outcomes: CaseOutcome, when: str = LATER, threshold: float = 0.9) -> Run:
    """A run whose `accuracy` is the real assertion over the real matrix."""
    accuracy = Accuracy(over=CHECK, threshold=threshold, tolerance=0.0)(outcomes)
    return Run(
        tenant="acme",
        environment="test",
        suite="triage",
        config_hash="cfg",
        created_at=when,
        results=tuple(
            CaseResult(
                case_id=o.case_id,
                verdicts=() if o.verdict is None else (o.verdict,),
                suspended="set aside" if o.verdict is None else None,
                canary=o.canary,
            )
            for o in outcomes
        ),
        aggregate=(accuracy,),
    )


def fifty(*, errored: int, failed: int = 0) -> Run:
    """Fifty cases: `errored` could not be judged, `failed` were judged wrong."""
    return run_of(
        *(
            outcome(
                f"c{i:02}",
                "error" if i < errored else "fail" if i < errored + failed else "pass",
            )
            for i in range(50)
        ),
        when=LATER if errored else CREATED,
    )


# --------------------------------------------------------------------------- #
# The run's own count: the headline, `compare`, the reading, the run document
# --------------------------------------------------------------------------- #


def test_the_headline_states_what_the_unjudged_count_is_a_count_of() -> None:
    reference, run = fifty(errored=0, failed=4), fifty(errored=7)
    head = headline(compare(run, reference), run, reference, locale="en")
    assert "43 of 50 cases judged, 7 could not be." in head.sentence
    # The bare count is gone rather than repeated beside the new sentence.
    assert "7 cases could not be judged" not in head.sentence


def test_a_clean_run_reads_as_it_always_did() -> None:
    """The readability half of the brief, and the reason the zero form was
    kept: a suite with no errors carries no count of them."""
    reference, run = fifty(errored=0, failed=4), fifty(errored=0, failed=3)
    comparison = compare(run, reference)
    head = headline(comparison, run, reference, locale="en")
    assert "Every case could be judged." in head.sentence
    assert " of 50 " not in head.sentence
    for line in (
        *summary_lines(comparison, run, reference, locale="en"),
        *explain_text(facts(run, comparison), locale="en"),
        *explain_text(facts(run), locale="en"),
    ):
        assert "counted" not in line, line
        assert "could not be" not in line, line


def test_suspended_cases_are_not_counted_as_judged() -> None:
    """The three numbers add up across the two clauses: judged, could not be,
    set aside."""
    run = run_of(
        *(outcome(f"c{i}", "pass") for i in range(6)),
        outcome("e1", "error"),
        outcome("e2", "error"),
        suspended("s1"),
        suspended("s2"),
    )
    head = headline(compare(run, run), run, run, locale="en")
    assert "6 of 10 cases judged, 2 could not be. 2 cases are suspended." in (
        head.sentence
    )
    # The reading takes the suspended count off its own `suspended` fact, and
    # must arrive at the same six.
    reading = explain_text(facts(run), locale="en")
    assert "6 of 10 cases judged, 2 could not be." in reading
    assert "2 cases are suspended." in reading


def test_a_run_of_one_case_keeps_the_bare_sentence() -> None:
    """Arithmetic rather than a sentence: "0 of 1 cases"."""
    run = run_of(outcome("only", "error"))
    head = headline(compare(run, run), run, run, locale="en")
    assert "1 case could not be judged." in head.sentence
    assert "0 of 1" not in head.sentence


def test_the_reading_says_it_from_its_own_facts() -> None:
    """Rendered off the fact list alone: the tally's `cases` and `suspended`
    facts are the numbers the sentence divides by, and the wire carries the
    same facts it always did."""
    reference, run = fifty(errored=0, failed=4), fifty(errored=7)
    reading = facts(run, compare(run, reference))
    assert "43 of 50 cases judged, 7 could not be." in explain_text(
        reading, locale="en"
    )
    assert "43 of 50 cases judged, 7 could not be." in explain_text(
        facts(run), locale="en"
    )
    wire = explain_json(reading, scope="comparison", exit_code=2)
    assert "counted" not in str(wire)


def test_the_run_document_says_it_above_its_tally() -> None:
    assert "<p>43 of 50 cases judged, 7 could not be.</p>" in render_run_html(
        fifty(errored=7), locale="en"
    )
    # And stays byte for byte what it was when every case was judged: the
    # tally already says 0, and a sentence saying so again is the parenthesis
    # of zeros in another place.
    clean = render_run_html(fifty(errored=0), locale="en")
    assert "cases judged" not in clean
    assert "Every case could be judged" not in clean


@pytest.mark.parametrize(
    ("errored", "headline_says", "reading_says"),
    [
        (
            7,
            "Casi giudicati: 43 su 50; 7 non è stato possibile giudicarli.",
            "Casi valutati: 43 su 50; 7 non lo sono stati.",
        ),
        (
            1,
            "Casi giudicati: 49 su 50; 1 non è stato possibile giudicarlo.",
            "Casi valutati: 49 su 50; 1 non lo è stato.",
        ),
        # The label and the colon are why this reads: "1 casi giudicati" would
        # not, and the participle cannot agree with a number it does not know.
        (
            49,
            "Casi giudicati: 1 su 50; 49 non è stato possibile giudicarli.",
            "Casi valutati: 1 su 50; 49 non lo sono stati.",
        ),
    ],
)
def test_both_locales(errored: int, headline_says: str, reading_says: str) -> None:
    reference, run = fifty(errored=0), fifty(errored=errored)
    head = headline(compare(run, reference), run, reference, locale="it")
    assert headline_says in head.sentence
    assert reading_says in explain_text(facts(run), locale="it")


# --------------------------------------------------------------------------- #
# The figure's own count: every run-level figure, wherever it is named
# --------------------------------------------------------------------------- #


def test_a_figure_that_left_cases_out_says_how_many_and_why() -> None:
    """The line `compare` prints for an aggregate that moved, and the report's
    "what happened" column, which are one function."""
    reference = run_of(*(outcome(f"c{i}", "pass") for i in range(10)), when=CREATED)
    run = run_of(
        *(outcome(f"c{i}", "pass") for i in range(7)),
        outcome("c7", "fail"),
        outcome("c8", "error"),
        outcome("c9", "error"),
    )
    comparison = compare(run, reference)
    (line,) = [
        line
        for line in summary_lines(comparison, run, reference, locale="en")
        if "accuracy" in line
    ]
    assert line.endswith("8 of 10 cases counted; 2 could not be judged.")
    document = render_html(comparison, run, reference, locale="en")
    assert "8 of 10 cases counted; 2 could not be judged." in document


def test_the_reading_names_the_figure_it_is_under_the_bar_with() -> None:
    run = run_of(
        *(outcome(f"c{i}", "pass") for i in range(6)),
        outcome("c6", "fail"),
        outcome("c7", "error"),
    )
    (line,) = [
        line for line in explain_text(facts(run), locale="en") if "accuracy" in line
    ]
    assert line.endswith("7 of 8 cases counted; 1 could not be judged.")


def test_a_figure_that_could_not_be_computed_says_why() -> None:
    """Every case errored, so the aggregate errored too — and the sentence is
    the reason: none of them was counted."""
    run = run_of(*(outcome(f"c{i}", "error") for i in range(3)))
    (line,) = [
        line for line in explain_text(facts(run), locale="en") if "accuracy" in line
    ]
    assert line.endswith("0 of 3 cases counted; 3 could not be judged.")


def test_a_case_level_check_carries_no_denominator() -> None:
    reference = run_of(*(outcome(f"c{i}", "pass") for i in range(3)), when=CREATED)
    run = run_of(outcome("c0", "fail"), outcome("c1", "error"), outcome("c2", "pass"))
    for line in summary_lines(compare(run, reference), run, reference, locale="en"):
        if not line.startswith("whole run"):
            assert "counted" not in line, line


def test_every_exclusion_is_named_so_the_two_numbers_add_up() -> None:
    """The canary is left out on purpose and is named anyway: a figure whose
    exclusions are not all named has a denominator nobody can reconcile."""
    run = run_of(
        *(outcome(f"c{i}", "pass") for i in range(5)),
        outcome("e", "error"),
        suspended("s"),
        outcome("k1", "pass", canary=True),
        outcome("k2", "pass", canary=True),
    )
    (verdict,) = run.aggregate
    said = denominator_sentence(denominator(verdict), locale="en", whole=False)
    assert said == (
        "5 of 9 cases counted; 1 could not be judged, 1 suspended, 2 canaries."
    )
    considered, seen = map(int, re.findall(r"\d+", said)[:2])
    named = sum(int(n) for n in re.findall(r"(\d+) [a-z]", said.split(";")[1]))
    assert considered + named == seen


def test_the_calibration_case_and_the_unlabelled_one_are_named_too() -> None:
    verdict = Verdict(
        score=Score(
            name="accuracy",
            score=1.0,
            metadata={
                "considered": 4,
                "errored_excluded": 0,
                "suspended_excluded": 0,
                "unlabelled_excluded": 1,
                "canary_excluded": 0,
                "calibration_excluded": 2,
            },
        ),
        threshold=0.9,
        status="pass",
        reason="accuracy 1.000000 = 4/4",
        assertion_id="id-accuracy",
    )
    assert denominator_sentence(denominator(verdict), locale="en", whole=False) == (
        "4 of 7 cases counted; 1 without a label, 2 calibration cases."
    )
    assert denominator_sentence(denominator(verdict), locale="it", whole=False) == (
        "Casi contati: 4 su 7; 1 senza etichetta, 2 casi di calibrazione."
    )


def test_the_report_cell_is_a_sentence_and_not_a_row_of_zeros() -> None:
    clean = fifty(errored=0)
    assert "All 50 cases counted." in render_run_html(clean, locale="en")
    assert "Contati tutti i 50 casi." in render_run_html(clean, locale="it")
    partial = fifty(errored=7)
    assert "43 of 50 cases counted; 7 could not be judged." in render_run_html(
        partial, locale="en"
    )


def test_a_verdict_with_no_recorded_matrix_gets_no_invented_count() -> None:
    """A reference written before aggregates recorded their matrix: the dash,
    never a zero nobody measured."""
    old = Verdict(
        score=Score(name="accuracy", score=0.9),
        threshold=0.8,
        status="pass",
        reason="accuracy 0.9",
        assertion_id="id-accuracy",
    )
    assert denominator(old) is None
    assert denominator_sentence(None, locale="en", whole=True) == ""
    run = Run(
        tenant="acme",
        environment="test",
        suite="triage",
        config_hash="cfg",
        created_at=CREATED,
        results=(CaseResult("c0", ()),),
        aggregate=(old,),
    )
    document = render_run_html(run, locale="en")
    assert "<td>—</td>" in document
    assert "0 counted" not in document
