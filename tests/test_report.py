"""The report: deterministic, escaped, honest about what it does not contain."""

from __future__ import annotations

from dataclasses import replace
from html import escape

import pytest

from digline.core import (
    CaseResult,
    Comparison,
    Disclosure,
    Run,
    Score,
    Verdict,
    compare,
    redact,
)
from digline.report import (
    LOCALES,
    TEXT,
    errored_verdicts,
    headline,
    render_html,
    render_run_html,
    run_tally,
    summary_lines,
    suspended_cases,
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


# --------------------------------------------------------------------------- #
# One run, with nothing held against it (friction 3)
# --------------------------------------------------------------------------- #
#
# `digline report` used to refuse a run with no baseline, and the refusal said
# "run it, look at the result, then promote" — while being the only way to
# look. The document below is what replaces that dead end.


def a_lone_run() -> Run:
    """A run with one of everything the document has a section for."""
    return Run(
        tenant="acme-bank",
        environment="staging",
        suite="qa",
        config_hash="cfg-1",
        created_at=CREATED_RUN,
        results=(
            CaseResult("capital-of-italy", (verdict("llm_rubric", 0.91),)),
            CaseResult("capital-of-france", (verdict("llm_rubric", 0.55),)),
            CaseResult("capital-of-spain", (verdict("contains", None),)),
            CaseResult("capital-of-peru", (), suspended="flaky on the Rossi account"),
        ),
    )


def test_a_run_with_no_reference_still_renders() -> None:
    for locale in LOCALES:
        document = render_run_html(a_lone_run(), locale=locale)
        assert document.startswith("<!DOCTYPE html>")
        assert document.endswith("</html>\n")
        assert escape(TEXT[locale]["noreference.title"]) in document


def test_the_no_reference_block_asks_no_question() -> None:
    """The slot a verdict occupies, saying why there is none.

    Not the question with an empty answer, and not an empty box: either would
    invite the reader to supply the answer themselves.
    """
    for locale in LOCALES:
        document = render_run_html(a_lone_run(), locale=locale)
        assert escape(TEXT[locale]["answer.question"]) not in document
        assert TEXT[locale]["answer.yes"] not in document
        assert escape(TEXT[locale]["noreference.sentence"]) in document


def test_the_verdict_block_is_neutral_not_green() -> None:
    """`worse` is red and `fine` is green, and either would be a claim. The
    third state is the absence of the claim, so it is the absence of the
    modifier — which is also why the stylesheet did not have to change."""
    document = render_run_html(a_lone_run(), locale="en")
    assert '<section class="answer">' in document
    assert 'class="answer fine"' not in document
    assert 'class="answer worse"' not in document


def test_the_tally_counts_the_run_and_not_outcomes() -> None:
    """An outcome is a relation between two runs. Printing six zeroes here
    would say "nothing regressed", which is the one thing this document is not
    entitled to say."""
    document = render_run_html(a_lone_run(), locale="en")
    for outcome in ("regressed", "improved", "unchanged", "missing"):
        assert f"<li>{outcome}" not in document
    assert "<li>cases <b>4</b></li>" in document
    assert "<li>checks <b>3</b></li>" in document
    assert "<li>cases not judged <b>1</b></li>" in document
    assert "<li>cases set aside <b>1</b></li>" in document


def test_the_cases_are_grouped_by_what_each_verdict_is() -> None:
    """The comparison groups by what a verdict *did*, which needs two runs.
    With one, the only grouping left is what it is."""
    document = render_run_html(a_lone_run(), locale="en")
    assert "What did not meet its threshold (1)" in document
    assert "What could not be judged (1)" in document
    assert "What is set aside (1)" in document
    assert "What met its threshold (1)" in document
    # Every case reaches exactly one section, and none is dropped.
    for case_id in ("capital-of-italy", "capital-of-france", "capital-of-spain"):
        assert document.count(f"<code>{case_id}</code>") == 1


def test_the_worst_sections_are_open_and_the_passing_one_is_not() -> None:
    document = render_run_html(a_lone_run(), locale="en")
    chunks = document.split("<details")[1:]
    assert [chunk.startswith(" open") for chunk in chunks] == [True, True, True, False]


def test_the_header_names_no_reference_it_does_not_have() -> None:
    """Absent rather than empty: a "Reference" row reading "—" would have the
    reader wondering which reference produced nothing."""
    document = render_run_html(a_lone_run(), locale="en")
    assert escape(TEXT["en"]["header.environment"]) in document
    assert escape(TEXT["en"]["header.baseline_environment"]) not in document


def test_a_failing_aggregate_carries_no_comparison_note() -> None:
    """ADR 0010 §10's sentence explains a measure that fails while the run is
    not *worse*. Without a reference there is no "not worse" to contrast with,
    so the sentence would be a comparison claim in a document that makes none.
    """
    run = replace(
        a_lone_run(),
        aggregate=(verdict("accuracy", 0.5, threshold=0.9),),
    )
    document = render_run_html(run, locale="en")
    assert "Overall" in document
    assert escape(TEXT["en"]["aggregates.failing_not_worse"]) not in document


def test_a_redacted_run_renders_without_the_reasons() -> None:
    run = redact(a_lone_run(), Disclosure())
    document = render_run_html(run, locale="en")
    assert escape(TEXT["en"]["header.redacted.value"]) in document
    assert "the judge explained itself" not in document
    assert "flaky on the Rossi account" not in document


def test_an_unknown_locale_fails_before_a_single_run_document_is_built() -> None:
    with pytest.raises(ValueError, match="unknown locale"):
        render_run_html(a_lone_run(), locale="de")  # type: ignore[arg-type]


# The absence test, and the reason it is phrased as an absence: the with-
# baseline document must be exactly what it was, and the cheapest thing to
# assert about "exactly what it was" that does not rot is that the new
# document's own heading never appears in it. Byte-for-byte equality was
# verified against six stored renders when this landed; pinning a digest here
# would fire on every legitimate change to the report from now on.
def test_the_no_reference_heading_never_appears_with_a_baseline() -> None:
    comparison, run, baseline = a_comparison()
    for locale in LOCALES:
        document = render_html(comparison, run, baseline, locale=locale)
        assert escape(TEXT[locale]["noreference.title"]) not in document
        assert escape(TEXT[locale]["noreference.sentence"]) not in document
        # The question is still asked, which is the other half of the same fact.
        assert escape(TEXT[locale]["answer.question"]) in document


# --------------------------------------------------------------------------- #
# The run's own facts, as structures rather than as expressions in a renderer
#
# The extraction ADR 0012 §2 makes a prerequisite. These are not new facts:
# every one was already printed. What is new is that one function produces
# each of them, so a reading and a document cannot count the same run twice
# and reach two numbers.
# --------------------------------------------------------------------------- #


def a_mixed_run() -> Run:
    """One case judged, one that errored, one set aside, and a run-level check
    that errored too — every state the tally distinguishes, in one run."""
    return Run(
        tenant="acme-bank",
        environment="staging",
        suite="qa",
        config_hash="cfg-1",
        created_at=CREATED_RUN,
        results=(
            CaseResult("capital-of-italy", (verdict("llm_rubric", 0.91),)),
            CaseResult(
                "who-is-the-president",
                (verdict("llm_rubric", None), verdict("contains", None)),
            ),
            CaseResult("the-rossi-account", (), suspended="fails since March"),
        ),
        aggregate=(verdict("precision", None),),
    )


def test_the_tally_counts_cases_and_checks_as_the_labels_say() -> None:
    tally = run_tally(a_mixed_run())
    assert tally.cases == 3
    assert tally.checks == 3
    # Cases, not verdicts: the one errored case carries two errored verdicts,
    # and both numbers are true of different things.
    assert tally.unjudged == 1
    assert tally.suspended == 1


def test_a_suspended_case_is_counted_once_by_both_readers() -> None:
    """The duplication this extraction removes, asserted rather than trusted.

    `headline()` and `_run_answer()` each used to write the count out. Two
    counters over one fact are two chances to disagree, and this is the test
    that would fail if one of them ever grew a rule the other did not.
    """
    run = a_mixed_run()
    baseline = replace(run, created_at=CREATED_BASE, environment="production")
    head = headline(compare(run, baseline), run, baseline, locale="en")
    assert head.suspended == suspended_cases(run) == run_tally(run).suspended


def test_a_run_with_nothing_set_aside_counts_none() -> None:
    """Not `a_lone_run()`: that fixture deliberately carries a suspension and
    an error, because it exists to exercise the document that has no
    reference. The zero has to be asserted on a run that really has none."""
    clean = a_run(verdict("llm_rubric", 0.91), when=CREATED_RUN)
    assert suspended_cases(clean) == 0
    assert run_tally(clean).suspended == 0
    assert run_tally(clean).unjudged == 0


def test_every_check_that_could_not_be_judged_is_named_from_the_run_alone() -> None:
    """The fact `unjudged_cases` cannot give: *which* ones.

    From the run and nothing else, which is the point — `_summarized()` names
    them out of a `Comparison`, so without a baseline nothing could.
    """
    found = errored_verdicts(a_mixed_run())
    assert [(e.scope, e.case_id, e.verdict.score.name) for e in found] == [
        ("case", "who-is-the-president", "llm_rubric"),
        ("case", "who-is-the-president", "contains"),
        # The aggregates last, and in run scope with no case to belong to:
        # `index_verdicts`' traversal, so there is one answer to which check
        # comes first.
        ("run", "", "precision"),
    ]


def test_a_run_that_judged_everything_names_nothing() -> None:
    assert errored_verdicts(a_run(verdict("llm_rubric", 0.91), when=CREATED_RUN)) == ()
