"""The report: a comparison rendered for someone who does not read code.

Pure functions. Nothing here opens a file, reads the clock or touches the
network — the caller writes the string wherever it belongs. The report is itself
a committable artifact, so it is deterministic byte for byte: the only dates it
shows are the ones the runs recorded.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from html import escape
from typing import Literal

from digline.core import AssertionDelta, CaseResult, Comparison, Outcome, Run
from digline.report.text import Locale, phrase, strings

__all__ = [
    "fmt_score",
    "DIRTY_SUFFIX",
    "SECTIONS",
    "SUMMARY_OUTCOMES",
    "Headline",
    "Section",
    "headline",
    "render_html",
    "summary_lines",
]

#: How the CLI marks a commit taken from a tree with uncommitted changes. The
#: report only reads it: reaching for git is the CLI's job alone.
DIRTY_SUFFIX = "-dirty"


#: Reading order, worst first. The layout is data so it can be reviewed without
#: reading markup, and so the order is one obvious edit rather than a rewrite.
@dataclass(frozen=True, slots=True)
class Section:
    key: str
    open_by_default: bool
    #: Which comparison outcomes land here. Empty for a section fed by the run
    #: itself rather than by the comparison.
    outcomes: Sequence[Outcome] = ()
    #: `suspended` reads the run: a case set aside produces no verdicts, so it
    #: produces no deltas, so the comparison cannot report it at all.
    source: Literal["outcomes", "suspended"] = "outcomes"


SECTIONS: Sequence[Section] = (
    Section("regressions", True, ("regressed",)),
    Section("unjudged", True, ("errored",)),
    Section("suspended", True, source="suspended"),
    Section("changes", False, ("new", "missing")),
    Section("improvements", False, ("improved",)),
    Section("unchanged", False, ("unchanged",)),
)

#: Fixed iteration order for counts, so two renders of one comparison are equal
#: byte for byte regardless of how the mapping was built.
OUTCOME_ORDER: Sequence[Outcome] = (
    "regressed",
    "errored",
    "new",
    "missing",
    "improved",
    "unchanged",
)


@dataclass(frozen=True, slots=True)
class Headline:
    """The first screen, and what a CLI exits on.

    It carries **four** facts, and they are deliberately not merged into one.

    A regression, a case the suite could not judge, and a case someone chose to
    set aside are three different events needing three different actions: an
    error is neither green nor a regression (ADR 0001), and a suspension is a
    decision rather than an outcome. `config_changed` then changes the meaning
    of all three — if the rules moved, the numbers compare different rules, and
    a reader who does not know that draws the wrong conclusion from every one.

    `sentence` is the same wording the report prints, so a CLI gate and the
    document a customer opens can never say two different things about one run.
    """

    worse: bool
    unjudged: int
    suspended: int
    config_changed: bool
    counts: Mapping[Outcome, int]
    reasons_available: bool
    sentence: str


def fmt_score(value: float) -> str:
    """Numbers keep the dot in every locale: two reports of one run must stay
    comparable line by line."""
    return f"{value:.6f}"


def headline(
    comparison: Comparison, run: Run, baseline: Run, *, locale: Locale
) -> Headline:
    strings(locale)  # fail here, not halfway through a document
    counts: dict[Outcome, int] = {o: comparison.counts.get(o, 0) for o in OUTCOME_ORDER}
    regressed = counts["regressed"]

    # Counted from the run, not from the comparison outcomes, and counted in
    # cases because that is what the sentence says.
    #
    # `errored` as an outcome only appears where a verdict *met* its counterpart
    # in the baseline: rule 1 of `compare()` classifies an absent counterpart as
    # `new` before rule 2 can call it `errored`. So a case that is both new and
    # unjudgeable — a case added to the suite that immediately fails to run — is
    # reported as `new`, and reading the tally would let the report announce
    # that every case could be judged while three of them could not.
    unjudged = sum(
        1
        for case in run.results
        if any(verdict.status == "error" for verdict in case.verdicts)
    )

    if regressed == 0:
        worse_text = phrase(locale, "fact.worse.none")
    elif regressed == 1:
        worse_text = phrase(locale, "fact.worse.one")
    else:
        worse_text = phrase(locale, "fact.worse.many", count=regressed)

    suspended = sum(1 for case in run.results if case.suspended is not None)

    if unjudged == 0:
        unjudged_text = phrase(locale, "fact.unjudged.none")
    elif unjudged == 1:
        unjudged_text = phrase(locale, "fact.unjudged.one")
    else:
        unjudged_text = phrase(locale, "fact.unjudged.many", count=unjudged)

    if suspended == 0:
        suspended_text = phrase(locale, "fact.suspended.none")
    elif suspended == 1:
        suspended_text = phrase(locale, "fact.suspended.one")
    else:
        suspended_text = phrase(locale, "fact.suspended.many", count=suspended)

    config_text = phrase(
        locale,
        "fact.config.changed" if comparison.config_changed else "fact.config.unchanged",
    )

    return Headline(
        worse=regressed > 0,
        unjudged=unjudged,
        suspended=suspended,
        config_changed=comparison.config_changed,
        counts=counts,
        reasons_available=not (run.redacted or baseline.redacted),
        # Config last, because it modifies the meaning of everything before it.
        sentence=" ".join((worse_text, unjudged_text, suspended_text, config_text)),
    )


def _detail(delta: AssertionDelta, locale: Locale) -> str:
    """Compose the explanation from the structured facts.

    `AssertionDelta.reason` is deliberately not echoed: it is English text
    generated by `compare()` for a developer, and reprinting it inside an
    Italian report would leak the engine's language into the document. Only the
    judge's own `reason` is quoted verbatim, because that is content rather than
    interface.
    """
    now, before = delta.current, delta.baseline
    errored_now = now is not None and now.status == "error"
    if delta.outcome == "new":
        # A case added to the suite that fails to run on its first day is `new`
        # by rule 1 of `compare()`, which classifies an absent counterpart
        # before rule 2 can call it `errored`. Saying only "new" would hide the
        # part that needs fixing.
        return phrase(locale, "detail.new.errored" if errored_now else "detail.new")
    if delta.outcome == "missing":
        return phrase(locale, "detail.missing")
    if delta.outcome == "errored":
        return phrase(locale, "detail.errored")

    assert now is not None and before is not None
    assert now.score.score is not None and before.score.score is not None
    was, is_now = fmt_score(before.score.score), fmt_score(now.score.score)

    if now.status != before.status:
        key = (
            "detail.flipped.worse"
            if before.status == "pass"
            else "detail.flipped.better"
        )
        text = phrase(locale, key, before=was, now=is_now)
        if now.threshold != before.threshold:
            text += phrase(
                locale,
                "detail.threshold_moved",
                before_threshold=fmt_score(before.threshold),
                now_threshold=fmt_score(now.threshold),
            )
        return text

    if delta.outcome == "regressed":
        return phrase(locale, "detail.dropped", before=was, now=is_now)
    if delta.outcome == "improved":
        return phrase(locale, "detail.rose", before=was, now=is_now)
    return phrase(locale, "detail.unchanged", now=is_now)


#: What separates the three fields of a summary line. Not a tab: the columns
#: have wildly different widths and aligning them would make the short lines
#: unreadable to buy neatness for the long ones.
SUMMARY_SEPARATOR = " · "

#: Which outcomes a terminal summary reports, in reading order. The rest is
#: noise on a command line — it belongs in the document, where it can be folded.
SUMMARY_OUTCOMES: Sequence[Outcome] = ("regressed", "errored")


def _summarized(comparison: Comparison) -> Sequence[AssertionDelta]:
    """Regressions first, then anything that could not run.

    The second group is *not* simply the `errored` outcome. A case added to the
    suite that fails on its first day is classified `new`, because rule 1 of
    `compare()` looks at presence before rule 2 looks at status — so selecting
    on the outcome alone would let the headline say "1 case could not be judged"
    while the list below it named nothing. The two must agree.
    """
    regressed = [d for d in comparison.deltas if d.outcome == "regressed"]
    unjudged = [
        d
        for d in comparison.deltas
        if d.outcome != "regressed"
        and d.current is not None
        and d.current.status == "error"
    ]
    return (*regressed, *unjudged)


def summary_lines(
    comparison: Comparison,
    run: Run,
    baseline: Run,
    *,
    locale: Locale,
    limit: int | None = None,
) -> Sequence[str]:
    """One line per regression and per unjudged check: what to fix, in order.

    The third field is produced by the **same** `_detail()` that fills the
    report's "what happened" column, so a terminal and a document can never
    describe one delta in two ways. That is the same reason `Headline.sentence`
    exists: two renderings of one fact drift apart the moment they have two
    sources.

    `limit` truncates, and when it does the last line **says so**. A silent
    "first twenty" reads exactly like "all twenty", which is the difference
    between a developer who fixes three regressions and one who fixes two.

    `run` and `baseline` are taken for symmetry with `headline()` and
    `render_html()` — the three entry points of this module accept the same
    three arguments — and are not read: a summary line is composed entirely
    from the delta, so it says the same thing whether or not the run is
    redacted.
    """
    strings(locale)  # fail here rather than halfway down a list
    chosen = _summarized(comparison)
    shown = chosen if limit is None else chosen[:limit]
    lines = [
        SUMMARY_SEPARATOR.join(
            (
                # A run-level verdict belongs to no case, so it says so rather
                # than opening the line with an empty field.
                d.case_id if d.scope == "case" else phrase(locale, "scope.run"),
                d.assertion,
                _detail(d, locale),
            )
        )
        for d in shown
    ]
    if len(shown) < len(chosen):
        lines.append(
            phrase(locale, "summary.truncated", shown=len(shown), total=len(chosen))
        )
    return tuple(lines)


def _reason(delta: AssertionDelta, locale: Locale, *, available: bool) -> str:
    """The judge's own words, when this report is allowed to carry them."""
    if not available:
        return phrase(locale, "reason.unavailable")
    source = delta.current if delta.current is not None else delta.baseline
    return "" if source is None else source.reason


CSS = """\
:root { color-scheme: light; }
body { font: 16px/1.5 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
       margin: 0 auto; max-width: 52rem; padding: 2rem 1rem; color: #16181d; }
h1 { font-size: 1.5rem; margin: 0 0 .25rem; }
h2 { font-size: 1.1rem; margin: 0 0 .25rem; }
.aggregates { margin: 0 0 2rem; }
dl.meta { display: grid; grid-template-columns: max-content 1fr; gap: .25rem 1rem;
          margin: 1rem 0 2rem; font-size: .9rem; }
dt { color: #5b6270; }
dd { margin: 0; }
.answer { border: 2px solid currentColor; border-radius: .5rem; padding: 1rem 1.25rem;
          margin: 0 0 2rem; }
.answer.worse { color: #8a1c1c; }
.answer.fine { color: #17552e; }
.answer .verdict { font-size: 2rem; font-weight: 700; line-height: 1; }
.answer p { color: #16181d; margin: .75rem 0 0; }
.tally { list-style: none; display: flex; flex-wrap: wrap; gap: 1rem;
         padding: 0; margin: 1rem 0 0; font-size: .85rem; color: #5b6270; }
.tally b { color: #16181d; }
details { border-top: 1px solid #d8dce3; padding: .75rem 0; }
summary { cursor: pointer; font-weight: 600; }
table { border-collapse: collapse; width: 100%; margin-top: .75rem;
        font-size: .9rem; }
th, td { border-bottom: 1px solid #e6e9ee; padding: .5rem .5rem .5rem 0;
         text-align: left; vertical-align: top; }
th { color: #5b6270; font-weight: 600; }
code { font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
       font-size: .875em; }
.empty { color: #5b6270; font-style: italic; margin: .5rem 0 0; }

/* Printing is the declared route to PDF, and a printed report that hides the
   regressions is a wrong report. Collapsed sections open on paper. */
@media print {
  body { max-width: none; padding: 0; color: #000; }
  details { display: block; }
  details > summary { list-style: none; }
  details > *:not(summary) { display: block !important; }
  details[open] > *, details:not([open]) > * { display: block !important; }
  .answer { border-color: #000; }
  a[href]::after { content: ""; }
}
"""


def _row(delta: AssertionDelta, locale: Locale, *, reasons: bool) -> str:
    reason = _reason(delta, locale, available=reasons)
    return (
        "<tr>"
        f"<td><code>{escape(delta.case_id)}</code></td>"
        f"<td><code>{escape(delta.assertion)}</code></td>"
        f"<td>{escape(_detail(delta, locale))}</td>"
        f"<td>{escape(reason)}</td>"
        "</tr>"
    )


def _suspended_row(case: CaseResult, locale: Locale, *, reasons: bool) -> str:
    stated = case.suspended if reasons else phrase(locale, "reason.unavailable")
    return (
        "<tr>"
        f"<td><code>{escape(case.case_id)}</code></td>"
        f"<td>{escape(stated or '')}</td>"
        "</tr>"
    )


def _table(head_keys: Sequence[str], rows: Sequence[str], locale: Locale) -> str:
    head = "".join(f"<th>{escape(phrase(locale, k))}</th>" for k in head_keys)
    return (
        f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(rows)}</tbody></table>"
    )


def _section(
    section: Section,
    comparison: Comparison,
    run: Run,
    locale: Locale,
    *,
    reasons: bool,
) -> str:
    title = escape(phrase(locale, f"section.{section.key}"))
    empty = f'<p class="empty">{escape(phrase(locale, "section.empty"))}</p>'
    open_attr = " open" if section.open_by_default else ""

    if section.source == "suspended":
        # Read from the run, not from the comparison: a suspended case produces
        # no verdicts, so it produces no deltas, so the comparison cannot report
        # it at all — and a coverage gap nobody sees is the reason suspension
        # had to be declared in the first place.
        cases = [c for c in run.results if c.suspended is not None]
        body = (
            empty
            if not cases
            else _table(
                ("column.case", "column.reason"),
                [_suspended_row(c, locale, reasons=reasons) for c in cases],
                locale,
            )
        )
        count = len(cases)
    else:
        wanted = frozenset(section.outcomes)
        rows = [d for d in comparison.deltas if d.outcome in wanted]
        body = (
            empty
            if not rows
            else _table(
                ("column.case", "column.check", "column.detail", "column.reason"),
                [_row(d, locale, reasons=reasons) for d in rows],
                locale,
            )
        )
        count = len(rows)

    return f"<details{open_attr}><summary>{title} ({count})</summary>{body}</details>"


def _aggregates(run: Run, locale: Locale, *, reasons: bool) -> str:
    """The run-level verdicts, above the cases.

    They come first because they are what gates a release: four runs of one
    unchanged prompt agreed with the human mark on 14, 14, 15, 15 of 21 cases
    while individual cases moved by three votes. The aggregate is the answer,
    the cases are the diagnosis.

    The two exclusions are printed **beside** every figure, never under it.
    `suspended_excluded` is the one number in this product that improves by
    doing less work — setting aside a failing case raises the ratio without
    anyone lying — so it travels with the ratio wherever the ratio goes.
    """
    if not run.aggregate:
        return ""

    rows: list[str] = []
    for verdict in run.aggregate:
        score = verdict.score.score
        result = phrase(locale, "detail.errored") if score is None else fmt_score(score)
        counted = phrase(
            locale,
            "aggregate.counted",
            considered=verdict.score.metadata.get("considered", 0),
            suspended=verdict.score.metadata.get("suspended_excluded", 0),
            errored=verdict.score.metadata.get("errored_excluded", 0),
        )
        why = verdict.reason if reasons else phrase(locale, "reason.unavailable")
        rows.append(
            "<tr>"
            f"<td><code>{escape(verdict.score.name)}</code></td>"
            f"<td><b>{escape(result)}</b> / {fmt_score(verdict.threshold)}</td>"
            f"<td>{escape(counted)}</td>"
            f"<td>{escape(why)}</td>"
            "</tr>"
        )

    table = _table(
        ("column.measure", "column.result", "column.detail", "column.reason"),
        rows,
        locale,
    )
    title = escape(phrase(locale, "aggregates.title"))
    return f'<section class="aggregates"><h2>{title}</h2>{table}</section>'


def _meta(comparison: Comparison, run: Run, baseline: Run, locale: Locale) -> str:
    """The header declares which two environments are being held against each
    other: comparing staging with a production reference is legitimate, and a
    reader must be able to see that is what they are looking at."""
    pairs = [
        ("header.tenant", comparison.tenant),
        ("header.suite", comparison.suite),
        ("header.environment", f"{comparison.environment} — {run.created_at}"),
        (
            "header.baseline_environment",
            f"{comparison.baseline_environment} — {baseline.created_at}",
        ),
    ]
    if run.git_commit is not None:
        commit = run.git_commit
        # A run produced from a dirty tree cannot be reproduced from the
        # repository, and a reader deciding whether to act on it deserves to
        # know that before the numbers, not after.
        if commit.endswith(DIRTY_SUFFIX):
            commit += phrase(locale, "header.dirty")
        pairs.append(("header.commit", commit))
    if run.redacted or baseline.redacted:
        pairs.append(("header.redacted", phrase(locale, "header.redacted.value")))
    return "".join(
        f"<dt>{escape(phrase(locale, key))}</dt><dd>{escape(value)}</dd>"
        for key, value in pairs
    )


def render_html(
    comparison: Comparison, run: Run, baseline: Run, *, locale: Locale
) -> str:
    """A self-contained HTML document, deterministic byte for byte.

    One inline stylesheet, no external asset, no script: collapsing uses
    `<details>`, which is markup rather than behaviour, so the report reads with
    JavaScript disabled and prints with every section open.

    Complete or redacted is not a parameter — it follows from `run.redacted` and
    `baseline.redacted`. When either side is redacted the document says so and
    states that the reasons are not included, rather than printing the marker.

    `locale` is mandatory and has no default: the language of a document with a
    recipient is not something to settle by omission.
    """
    head = headline(comparison, run, baseline, locale=locale)
    answer = phrase(locale, "answer.yes" if head.worse else "answer.no")
    tally = "".join(
        f"<li>{escape(outcome)} <b>{head.counts[outcome]}</b></li>"
        for outcome in OUTCOME_ORDER
    )
    sections = "".join(
        _section(s, comparison, run, locale, reasons=head.reasons_available)
        for s in SECTIONS
    )
    title = phrase(locale, "document.title", suite=comparison.suite)

    return (
        "<!DOCTYPE html>\n"
        f'<html lang="{escape(locale)}">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{escape(title)}</title>\n"
        f"<style>\n{CSS}</style>\n"
        "</head>\n"
        "<body>\n"
        f"<h1>{escape(title)}</h1>\n"
        f'<dl class="meta">{_meta(comparison, run, baseline, locale)}</dl>\n'
        f'<section class="answer {"worse" if head.worse else "fine"}">\n'
        f'<p class="verdict">{escape(phrase(locale, "answer.question"))} '
        f"{escape(answer)}</p>\n"
        f"<p>{escape(head.sentence)}</p>\n"
        f'<ul class="tally">{tally}</ul>\n'
        "</section>\n"
        f"{_aggregates(run, locale, reasons=head.reasons_available)}\n"
        f"{sections}\n"
        "</body>\n"
        "</html>\n"
    )
