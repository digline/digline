"""The report: deterministic, escaped, honest about what it does not contain."""

from __future__ import annotations

from html import escape

import pytest

from digline.core import (
    CaseResult,
    Comparison,
    Run,
    Score,
    Verdict,
    compare,
    redact,
)
from digline.report import (
    LOCALES,
    TEXT,
    headline,
    render_html,
    summary_lines,
)

CREATED_RUN = "2026-08-25T11:00:00+00:00"
CREATED_BASE = "2026-08-25T10:00:00+00:00"


def verdict(
    name: str,
    score: float | None,
    *,
    threshold: float = 0.7,
    reason: str = "the judge explained itself",
) -> Verdict:
    if score is None:
        return Verdict(
            score=Score(name=name, score=None),
            threshold=threshold,
            status="error",
            reason=reason,
            assertion_id=f"id-{name}",
        )
    return Verdict(
        score=Score(name=name, score=score),
        threshold=threshold,
        status="pass" if score >= threshold else "fail",
        reason=reason,
        assertion_id=f"id-{name}",
    )


def a_run(*verdicts: Verdict, when: str, environment: str = "staging") -> Run:
    return Run(
        tenant="acme-bank",
        environment=environment,
        suite="qa",
        config_hash="cfg-1",
        created_at=when,
        results=(CaseResult("capital-of-italy", verdicts),),
    )


def a_comparison() -> tuple[Comparison, Run, Run]:
    baseline = a_run(
        verdict("llm_rubric", 0.91), when=CREATED_BASE, environment="production"
    )
    run = a_run(verdict("llm_rubric", 0.78), when=CREATED_RUN)
    return compare(run, baseline), run, baseline


# --------------------------------------------------------------------------- #
# The first screen
# --------------------------------------------------------------------------- #


def test_the_headline_carries_three_facts() -> None:
    """Regressions and unjudged cases need different actions, and
    `config_changed` changes the meaning of both."""
    comparison, run, baseline = a_comparison()
    head = headline(comparison, run, baseline, locale="en")
    assert head.worse is True
    assert head.unjudged == 0
    assert head.config_changed is False


def test_an_unjudged_case_is_not_counted_as_a_regression() -> None:
    baseline = a_run(verdict("llm_rubric", 0.91), when=CREATED_BASE)
    run = a_run(verdict("llm_rubric", None), when=CREATED_RUN)
    head = headline(compare(run, baseline), run, baseline, locale="en")
    assert head.worse is False
    assert head.unjudged == 1
    assert "1 case could not be judged" in head.sentence


def test_a_new_case_that_could_not_run_is_still_counted_as_unjudged() -> None:
    """Found by running the thing rather than by reading it.

    `compare()` classifies a verdict with no counterpart as `new` before it can
    call it `errored`, so counting the tally would let the report say every case
    was judged while a newly added, immediately broken one was not. The fact is
    about this run, so it is counted from the run."""
    baseline = a_run(verdict("llm_rubric", 0.91), when=CREATED_BASE)
    run = Run(
        tenant="acme-bank",
        environment="staging",
        suite="qa",
        config_hash="cfg-1",
        created_at=CREATED_RUN,
        results=(
            CaseResult("capital-of-italy", (verdict("llm_rubric", 0.91),)),
            CaseResult("brand-new-and-broken", (verdict("llm_rubric", None),)),
        ),
    )
    comparison = compare(run, baseline)
    assert comparison.counts.get("errored", 0) == 0  # the outcome says `new`
    head = headline(comparison, run, baseline, locale="en")
    assert head.unjudged == 1
    assert "1 case could not be judged" in head.sentence


def test_unjudged_counts_cases_not_checks() -> None:
    """The sentence says "cases", so a case whose three checks all errored is
    one unjudged case, not three."""
    baseline = a_run(verdict("llm_rubric", 0.91), when=CREATED_BASE)
    run = Run(
        tenant="acme-bank",
        environment="staging",
        suite="qa",
        config_hash="cfg-1",
        created_at=CREATED_RUN,
        results=(
            CaseResult(
                "all-broken",
                (
                    verdict("llm_rubric", None),
                    verdict("contains", None),
                    verdict("cost_budget", None),
                ),
            ),
        ),
    )
    assert headline(compare(run, baseline), run, baseline, locale="en").unjudged == 1


def test_the_sentence_mentions_a_changed_configuration() -> None:
    baseline = a_run(verdict("llm_rubric", 0.91), when=CREATED_BASE)
    run = Run(
        tenant="acme-bank",
        environment="staging",
        suite="qa",
        config_hash="cfg-2",
        created_at=CREATED_RUN,
        results=(CaseResult("capital-of-italy", (verdict("llm_rubric", 0.91),)),),
    )
    head = headline(compare(run, baseline), run, baseline, locale="en")
    assert head.config_changed is True
    assert "compare different rules" in head.sentence


def test_the_cli_and_the_report_say_the_same_sentence() -> None:
    comparison, run, baseline = a_comparison()
    head = headline(comparison, run, baseline, locale="it")
    assert head.sentence in render_html(comparison, run, baseline, locale="it")


# --------------------------------------------------------------------------- #
# summary_lines: the terminal and the document, one string
# --------------------------------------------------------------------------- #


def many_regressions(count: int) -> tuple[Comparison, Run, Run]:
    def side(scores: list[float], when: str) -> Run:
        return Run(
            tenant="acme-bank",
            environment="staging",
            suite="qa",
            config_hash="cfg-1",
            created_at=when,
            results=tuple(
                CaseResult(f"case-{i}", (verdict(f"check-{i}", s),))
                for i, s in enumerate(scores)
            ),
        )

    baseline = side([0.91] * count, CREATED_BASE)
    run = side([0.78] * count, CREATED_RUN)
    return compare(run, baseline), run, baseline


def test_a_summary_line_names_the_case_the_check_and_the_change() -> None:
    """ "1 check got worse" without saying which sends the reader to open an HTML
    file to learn a fact that fits on one line."""
    comparison, run, baseline = a_comparison()
    lines = summary_lines(comparison, run, baseline, locale="en")
    assert len(lines) == 1
    case, assertion, detail = lines[0].split(" · ")
    assert case == "capital-of-italy"
    assert assertion == "llm_rubric"
    assert "0.910000" in detail and "0.780000" in detail


def test_the_terminal_line_and_the_report_row_come_from_one_string() -> None:
    """The guarantee this function exists for. If someone ever composes the two
    separately, this fails — which is the only way they stay in step."""
    comparison, run, baseline = many_regressions(3)
    document = render_html(comparison, run, baseline, locale="it")
    lines = summary_lines(comparison, run, baseline, locale="it")

    assert len(lines) == 3
    for line in lines:
        _case, _assertion, detail = line.split(" · ")
        assert escape(detail) in document, detail


def test_only_regressions_and_unjudged_checks_are_summarized() -> None:
    """The rest is noise on a command line; it belongs in the document, where it
    can be folded away."""
    baseline = a_run(
        verdict("worse", 0.91),
        verdict("better", 0.50),
        verdict("same", 0.80),
        when=CREATED_BASE,
    )
    run = a_run(
        verdict("worse", 0.78),
        verdict("better", 0.95),
        verdict("same", 0.80),
        verdict("broken", None),
        when=CREATED_RUN,
    )
    lines = summary_lines(compare(run, baseline), run, baseline, locale="en")
    named = [line.split(" · ")[1] for line in lines]
    assert named == ["worse", "broken"]  # regressions first, then unjudged


def test_a_check_that_is_new_and_broken_is_still_listed() -> None:
    """Found by a test expectation that turned out to be right about the product
    and wrong about the code.

    `compare()` calls it `new`, because presence is examined before status. If
    the summary selected on the outcome alone, the headline would say "1 case
    could not be judged" and the list below it would name nothing."""
    baseline = a_run(verdict("kept", 0.91), when=CREATED_BASE)
    run = Run(
        tenant="acme-bank",
        environment="staging",
        suite="qa",
        config_hash="cfg-1",
        created_at=CREATED_RUN,
        results=(
            CaseResult("capital-of-italy", (verdict("kept", 0.91),)),
            CaseResult("brand-new", (verdict("fresh", None),)),
        ),
    )
    comparison = compare(run, baseline)
    assert comparison.counts.get("errored", 0) == 0  # the outcome says `new`

    head = headline(comparison, run, baseline, locale="en")
    lines = summary_lines(comparison, run, baseline, locale="en")

    assert head.unjudged == 1
    assert len(lines) == 1, "the headline counts it, so the list must name it"
    case, assertion, detail = lines[0].split(" · ")
    assert (case, assertion) == ("brand-new", "fresh")
    assert "could not run" in detail


def test_a_truncated_summary_says_how_many_it_left_out() -> None:
    """A silent "first two" reads exactly like "all two", which is the
    difference between fixing three regressions and fixing two."""
    comparison, run, baseline = many_regressions(5)
    lines = summary_lines(comparison, run, baseline, locale="en", limit=2)
    assert len(lines) == 3  # two deltas plus the notice
    assert "showing the first 2 of 5" in lines[-1]


def test_an_untruncated_summary_says_nothing_extra() -> None:
    comparison, run, baseline = many_regressions(3)
    assert len(summary_lines(comparison, run, baseline, locale="en", limit=3)) == 3
    assert len(summary_lines(comparison, run, baseline, locale="en")) == 3


def test_a_clean_comparison_summarizes_to_nothing() -> None:
    baseline = a_run(verdict("llm_rubric", 0.91), when=CREATED_BASE)
    run = a_run(verdict("llm_rubric", 0.91), when=CREATED_RUN)
    assert summary_lines(compare(run, baseline), run, baseline, locale="en") == ()


def test_the_summary_is_localized_like_everything_else() -> None:
    comparison, run, baseline = a_comparison()
    english = summary_lines(comparison, run, baseline, locale="en")[0]
    italian = summary_lines(comparison, run, baseline, locale="it")[0]
    assert english != italian
    assert "Il punteggio è sceso" in italian


def test_an_unknown_locale_fails_before_any_line_is_built() -> None:
    comparison, run, baseline = a_comparison()
    with pytest.raises(ValueError, match="unknown locale"):
        summary_lines(comparison, run, baseline, locale="de")  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# Determinism
# --------------------------------------------------------------------------- #


def test_two_renders_are_identical_byte_for_byte() -> None:
    """The report is a committable artifact: a diff must only move when a fact
    moves. Nothing here may be read from the clock."""
    comparison, run, baseline = a_comparison()
    first = render_html(comparison, run, baseline, locale="en")
    second = render_html(comparison, run, baseline, locale="en")
    assert first == second


def test_only_the_recorded_dates_appear() -> None:
    comparison, run, baseline = a_comparison()
    document = render_html(comparison, run, baseline, locale="en")
    assert CREATED_RUN in document and CREATED_BASE in document


def test_dates_and_numbers_are_not_localized() -> None:
    """Two reports of one run in two languages must stay comparable line by
    line, so formats do not move with the locale."""
    comparison, run, baseline = a_comparison()
    for locale in LOCALES:
        document = render_html(comparison, run, baseline, locale=locale)
        assert CREATED_RUN in document  # ISO, not reformatted
        assert "0.780000" in document  # dot, not comma
        assert "0,780000" not in document


# --------------------------------------------------------------------------- #
# The header declares what is being held against what
# --------------------------------------------------------------------------- #


def test_the_header_names_both_environments() -> None:
    comparison, run, baseline = a_comparison()
    document = render_html(comparison, run, baseline, locale="en")
    assert "staging" in document
    assert "production" in document


def test_the_header_names_the_customer_and_the_suite() -> None:
    comparison, run, baseline = a_comparison()
    document = render_html(comparison, run, baseline, locale="en")
    assert "acme-bank" in document and "qa" in document


# --------------------------------------------------------------------------- #
# Escaping
# --------------------------------------------------------------------------- #


def test_a_reason_containing_markup_is_escaped() -> None:
    """A reason is arbitrary text an LLM produced from arbitrary input, and the
    document is opened in a browser by the end company: this is a real attack
    surface, not a formatting detail."""
    hostile = "<script>alert('x')</script> & <img src=x onerror=1>"
    baseline = a_run(verdict("llm_rubric", 0.91), when=CREATED_BASE)
    run = a_run(verdict("llm_rubric", 0.10, reason=hostile), when=CREATED_RUN)
    document = render_html(compare(run, baseline), run, baseline, locale="en")

    # The property is that no *tag* survives, not that no word does. The string
    # `onerror=1` stays visible as text inside `&lt;img …&gt;`, which is inert:
    # asserting on the word would be checking the vocabulary instead of the
    # construct — the same mistake as flagging `rubric` inside `llm_rubric`.
    assert "<script" not in document
    assert "<img" not in document
    assert "&lt;script&gt;" in document
    assert "&lt;img src=x onerror=1&gt;" in document
    assert "&amp;" in document


def test_a_hostile_case_id_is_escaped() -> None:
    hostile_run = Run(
        tenant="acme-bank",
        environment="staging",
        suite="qa",
        config_hash="cfg-1",
        created_at=CREATED_RUN,
        results=(CaseResult("<b>case</b>", (verdict("llm_rubric", 0.10),)),),
    )
    document = render_html(
        compare(hostile_run, hostile_run), hostile_run, hostile_run, locale="en"
    )
    assert "<b>case</b>" not in document
    assert "&lt;b&gt;case&lt;/b&gt;" in document


# --------------------------------------------------------------------------- #
# Redacted inputs
# --------------------------------------------------------------------------- #


def test_a_redacted_input_makes_the_report_redacted_without_a_flag() -> None:
    """Not a parameter: it follows from the inputs, so nobody can produce a
    complete-looking report from redacted data by forgetting an argument."""
    baseline = a_run(verdict("llm_rubric", 0.91), when=CREATED_BASE)
    run = redact(a_run(verdict("llm_rubric", 0.78), when=CREATED_RUN))

    head = headline(compare(run, baseline), run, baseline, locale="en")
    assert head.reasons_available is False

    document = render_html(compare(run, baseline), run, baseline, locale="en")
    assert "produced from redacted data" in document
    assert "the judge explained itself" not in document
    assert "<redacted>" not in document  # the marker is never shown
    assert "Not included in this report" in document


def test_a_complete_input_carries_the_judge_words() -> None:
    comparison, run, baseline = a_comparison()
    document = render_html(comparison, run, baseline, locale="en")
    assert "the judge explained itself" in document


# --------------------------------------------------------------------------- #
# Print
# --------------------------------------------------------------------------- #


def test_the_print_stylesheet_opens_collapsed_sections() -> None:
    """Printing is the declared route to PDF, and a printed report that hides
    the regressions is a wrong report."""
    comparison, run, baseline = a_comparison()
    document = render_html(comparison, run, baseline, locale="en")
    assert "@media print" in document
    # The block runs to the end of the stylesheet; splitting on the first "}"
    # would cut it at the first nested rule.
    print_block = document.split("@media print", 1)[1].split("</style>", 1)[0]
    assert "details" in print_block
    assert "display: block !important" in print_block


def test_the_document_needs_no_script_to_be_read() -> None:
    comparison, run, baseline = a_comparison()
    document = render_html(comparison, run, baseline, locale="en")
    assert "<script" not in document.lower()
    assert "http://" not in document and "https://" not in document


# --------------------------------------------------------------------------- #
# Locale
# --------------------------------------------------------------------------- #


def test_both_locales_cover_exactly_the_same_keys() -> None:
    """A key present in one language and missing in the other is a blank cell in
    a document a customer reads."""
    reference = set(TEXT["en"])
    for locale in LOCALES:
        assert set(TEXT[locale]) == reference, f"{locale} diverges"


def test_every_locale_renders() -> None:
    comparison, run, baseline = a_comparison()
    for locale in LOCALES:
        document = render_html(comparison, run, baseline, locale=locale)
        assert document.startswith("<!DOCTYPE html>")
        assert f'<html lang="{locale}"' in document


def test_an_unknown_locale_fails_at_the_call_not_halfway() -> None:
    """A truncated report still looks like a report."""
    comparison, run, baseline = a_comparison()
    with pytest.raises(ValueError, match="unknown locale"):
        render_html(comparison, run, baseline, locale="de")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="unknown locale"):
        headline(comparison, run, baseline, locale="de")  # type: ignore[arg-type]


def test_the_two_locales_differ_in_wording_but_not_in_shape() -> None:
    comparison, run, baseline = a_comparison()
    english = render_html(comparison, run, baseline, locale="en")
    italian = render_html(comparison, run, baseline, locale="it")
    assert english != italian
    assert "È peggiorato?" in italian
    assert "Did it get worse?" in english
    # Same structure: one <details> per declared section, in both.
    assert english.count("<details") == italian.count("<details")


def test_the_engine_english_is_not_leaked_into_the_italian_report() -> None:
    """`AssertionDelta.reason` is written by `compare()` for a developer. The
    report composes its own sentences from the structured facts instead."""
    comparison, run, baseline = a_comparison()
    assert "score dropped from" in comparison.deltas[0].reason
    assert "score dropped from" not in render_html(
        comparison, run, baseline, locale="it"
    )


# --------------------------------------------------------------------------- #
# Sections
# --------------------------------------------------------------------------- #


def test_regressions_come_before_everything_else() -> None:
    comparison, run, baseline = a_comparison()
    document = render_html(comparison, run, baseline, locale="en")
    assert document.index("What got worse") < document.index("What stayed the same")


def test_regressions_and_unjudged_are_open_by_default() -> None:
    comparison, run, baseline = a_comparison()
    document = render_html(comparison, run, baseline, locale="en")
    first_two = document.split("<details")[1:3]
    assert all(chunk.startswith(" open") for chunk in first_two)


def test_an_empty_section_says_so_rather_than_disappearing() -> None:
    comparison, run, baseline = a_comparison()
    document = render_html(comparison, run, baseline, locale="en")
    assert "Nothing in this section." in document


def test_every_delta_appears_exactly_once() -> None:
    baseline = a_run(
        verdict("llm_rubric", 0.91), verdict("contains", 1.0), when=CREATED_BASE
    )
    run = a_run(verdict("llm_rubric", 0.78), verdict("contains", 1.0), when=CREATED_RUN)
    comparison = compare(run, baseline)
    document = render_html(comparison, run, baseline, locale="en")
    for delta in comparison.deltas:
        assert document.count(f"<code>{delta.assertion}</code>") == 1
