"""The four screens of `digline view`, as pure functions.

Each one takes values and returns a string. The server is transport: it reads
the store, calls one of these, and writes the bytes. No test here needs a
socket, and no screen can depend on being served.

The comparison screen does not render a comparison of its own — it calls
`render_html`, the same function `digline report` writes to a file, and adds
a navigation bar. If the page and the exported document ever disagreed about a
run, that would be a defect rather than a difference of medium, so there is only
one function that can be wrong.

The look is the report's: the same palette, the same type, the same table. Two
deliberate departures, both because a screen is not a document:

- **Wider.** The report is prose with narrow tables and lives at `52rem`; the
  run list is a grid with one column per aggregate and needs the room.
- **Readable dates.** The report keeps ISO, because it is committed and two
  renderings must diff line by line. Here the heading is `26 Aug 08:51` and the
  full key sits under it in monospace — the ISO instant is still there, in the
  one string that is also the address of the run.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from html import escape
from typing import cast

from digline.core import Run, Verdict, artifacts_sha, compare
from digline.report.history import CaseEntry, CaseHistory
from digline.report.render import CSS, render_html
from digline.report.text import LOCALES, MONTHS, Locale, phrase

__all__ = [
    "VIEW_CSS",
    "case_page",
    "compare_page",
    "fmt3",
    "human_time",
    "locale_of",
    "nav",
    "phrase",
    "runs_page",
    "suspend_page",
    "suspension_snippet",
]

#: Added to the report's stylesheet, never replacing it: everything shared —
#: colour, type, table rules, the print block — comes from `CSS`, so the two
#: keep looking like one product without either being told about the other.
VIEW_CSS = """\
body.wide { max-width: 68rem; }
nav.bar { display: flex; flex-wrap: wrap; gap: 1rem; align-items: baseline;
          border-bottom: 1px solid #d8dce3; padding: 0 0 .75rem;
          margin: 0 0 1.75rem; font-size: .9rem; }
nav.bar a { color: #5b6270; text-decoration: none; }
nav.bar a:hover { color: #16181d; text-decoration: underline; }
nav.bar .suite { color: #16181d; font-weight: 600; }
nav.bar .spacer { flex: 1; }
nav.bar .here { color: #16181d; font-weight: 700; }

/* One row is one run: a readable moment, with its address beneath it. */
.when { font-weight: 600; white-space: nowrap; }
.key { display: block; font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
       font-size: .7rem; color: #7a828f; margin-top: .15rem;
       user-select: all; -webkit-user-select: all; }
.key:hover { color: #16181d; }

/* Which prompt produced this run. A label beside the moment rather than a
   column of its own: it is read to group runs, not to be compared down a
   column, and the table is already wide. */
.stamp { display: inline-block; font-size: .7rem; color: #5b6270; margin-left: .5rem;
         font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }

tbody tr:nth-child(even) { background: #fafbfc; }
tbody tr.is-baseline { background: #eef4ef; }
tbody tr.is-baseline:hover, tbody tr:hover { background: #f0f3f7; }
td, th { white-space: nowrap; }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }

/* The row's own actions, and — where a row can do less — the marker that says
   why, in the same place the missing button would have been. One column, one
   answer per run. */
td.act, th.act { text-align: right; }
td.act form { display: inline; margin: 0; }
td.act .chip { margin-left: 0; }
td.act a.action { margin-right: .6rem; }
td.act button { font-size: .8rem; padding: .2rem .55rem; }
a.action { color: #2f4f7a; text-decoration: none; }
a.action:hover { text-decoration: underline; }

/* Produced under another configuration: comparable still, promotable no
   longer. Attenuated rather than hidden — those numbers were measured, only
   under other rules. */
tbody tr.stale td { color: #868e9b; }
tbody tr.stale td.commit code { color: inherit; }
/* The delta too: a bright red change against a baseline measured under other
   rules is the one number on that row that should not shout. */
tbody tr.stale td .delta { color: #868e9b; }

.chip { display: inline-block; font-size: .7rem; font-weight: 600;
        text-transform: uppercase; letter-spacing: .04em; padding: .1rem .4rem;
        border-radius: .25rem; background: #e3eae4; color: #17552e;
        margin-left: .4rem; vertical-align: .05em; }
.chip.warn { background: #f6e9e0; color: #8a4b1c; }
.chip.plain { background: #eceff3; color: #5b6270; }

.delta { font-size: .75rem; font-variant-numeric: tabular-nums; display: block;
         margin-top: .1rem; }
.delta.up { color: #17552e; }
.delta.down { color: #8a1c1c; }
.delta.same { color: #98a0ad; }

.picker { display: flex; flex-wrap: wrap; gap: .75rem; align-items: baseline;
          background: #f7f8fa; border: 1px solid #e6e9ee; border-radius: .375rem;
          padding: .75rem 1rem; margin: 1.75rem 0 .5rem; font-size: .9rem; }
button { font: inherit; font-size: .9rem; padding: .35rem .8rem; cursor: pointer;
         border: 1px solid #c3c9d3; border-radius: .25rem; background: #fff; }
button:hover { border-color: #16181d; }
select, input[type=text] { font: inherit; font-size: .9rem; padding: .25rem; }

.votes { color: #7a828f; font-size: .75rem; font-variant-numeric: tabular-nums;
         margin-top: .15rem; }
td.absent { color: #98a0ad; font-style: italic; }
.commit code { color: #16181d; }
pre.snippet { background: #f5f6f8; border: 1px solid #d8dce3; border-radius: .375rem;
              padding: .75rem 1rem; overflow-x: auto; font-size: .875rem;
              user-select: all; -webkit-user-select: all; }
p.note { color: #5b6270; font-size: .85rem; margin: .5rem 0 0; max-width: 46rem; }
"""


# --------------------------------------------------------------------------- #
# Shared formatting
# --------------------------------------------------------------------------- #


def human_time(created_at: str, locale: Locale, *, seconds: bool = False) -> str:
    """`2026-08-26T08:51:04.123456+00:00` becomes `26 Aug 08:51`.

    Sliced rather than parsed: `digline.report` may not import `datetime`,
    and the layering gate enforces it. That rule is about the clock, and it
    holds here for a better reason than compliance — this function formats a
    string that was *recorded*, and it must never be able to ask what time it
    is now.

    Anything not shaped like the timestamps we write is returned untouched. A
    screen that showed `26 Aug 08:51` for a value it had not understood would
    be worse than one that showed the raw string.
    """
    date, _, rest = created_at.partition("T")
    parts = date.split("-")
    if len(parts) != 3 or len(rest) < 5:
        return created_at
    _year, month, day = parts
    if not (month.isdigit() and day.isdigit() and 1 <= int(month) <= 12):
        return created_at
    clock = rest[:8] if seconds and len(rest) >= 8 else rest[:5]
    return f"{int(day)} {MONTHS[locale][int(month) - 1]} {clock}"


def _when_labels(
    created: Sequence[tuple[str, str]], locale: Locale
) -> Mapping[str, str]:
    """A readable label per run, at the coarsest resolution that separates them.

    Minutes are what a person wants to read, and minutes are enough — except in
    the one situation this page exists for. A calibration is four runs of an
    unchanged configuration launched back to back, so they land in the same
    minute and every heading reads `26 Aug 12:40`. Found by looking at the
    screenshot, not by thinking about it.

    When any two collide the *whole column* moves to seconds, not just the pair.
    Mixed precision down one column reads as data — as though those two runs
    were somehow more precisely known — when it is only formatting.

    It escalates once and stops. Two runs within one second are possible and the
    label will repeat; the key underneath is what separates them, and that is
    the job the key has. Going to microseconds would trade a duplicate nobody
    reads for a heading nobody can.
    """
    plain = {key: human_time(at, locale) for key, at in created}
    rendered = list(plain.values())
    if len(set(rendered)) == len(rendered):
        return plain
    return {key: human_time(at, locale, seconds=True) for key, at in created}


def fmt3(value: float) -> str:
    """Three decimals on a screen, six in a document.

    The report writes six because a baseline is diffed and the seventh digit of
    a float is where a spurious change hides. A column read down to pick a
    median is read, not diffed, and `0.619` is read faster than `0.619048`.
    """
    return f"{value:.3f}"


def _delta(now: float, before: float | None, locale: Locale) -> str:
    """The signed change against the baseline, beneath the number.

    This is the whole "which run do I promote" reading, done in one glance:
    without it the columns are four absolute numbers and the comparison happens
    in the reader's head.
    """
    if before is None:
        return ""
    change = round(now - before, 3)
    note = escape(phrase(locale, "view.column.aggregate_note"))
    if change == 0:
        return f'<span class="delta same" title="{note}">±0.000</span>'
    kind = "up" if change > 0 else "down"
    return f'<span class="delta {kind}" title="{note}">{change:+.3f}</span>'


def _score(verdict: Verdict) -> str:
    return "—" if verdict.score.score is None else fmt3(verdict.score.score)


def _votes(verdict: Verdict) -> str:
    """The raw per-sample scores of a sampled check, or empty.

    This is the column the calibration table was built by hand for: a combined
    score of `0.667` says the samples disagreed, and only the votes say how.
    """
    raw = verdict.score.metadata.get("scores")
    if not isinstance(raw, Sequence) or isinstance(raw, str) or not raw:
        return ""
    items = cast(Sequence[object], raw)
    values = [float(v) for v in items if isinstance(v, int | float)]
    if not values:
        return ""
    return " · ".join(fmt3(v) for v in values)


def _stamp(run: Run, locale: Locale) -> str:
    """`prompt a1b2c3` — the digest of the files that were under test.

    Short on purpose: it is read to tell two prompts apart at a glance, and
    twelve hex characters do that as well as sixty-four while fitting beside a
    date. The full digests are in the run file. Nothing at all when the suite
    declared no artifacts. (ADR 0003)
    """
    if not run.artifacts:
        return ""
    told = phrase(locale, "view.artifacts.stamp", sha=artifacts_sha(run.artifacts))
    title = phrase(locale, "view.artifacts.title", count=len(run.artifacts))
    return f'<span class="stamp" title="{escape(title)}">{escape(told)}</span>'


def _run_cell(key: str, when: str, *, stamp: str = "", href: str = "") -> str:
    """A moment a person can read, and the address underneath it.

    The key used to be the heading, wrapped over four lines, and was also a
    link — three jobs for one string, none of them done. Now the moment names
    the run and the key identifies it; `user-select: all` makes one click
    select the whole thing, which is what it is for.

    It carries no marker any more: what a run can and cannot do is answered in
    the column where the doing happens, not beside its name.
    """
    # Only the moment is a link. Wrapping the key too made it blue and
    # underlined, and put a click that navigates on top of a click that selects.
    moment = f'<span class="when">{escape(when)}</span>'
    if href:
        moment = f'<a href="{escape(href)}">{moment}</a>'
    return f'<td>{moment}{stamp}<code class="key">{escape(key)}</code></td>'


def _commit_cell(run: Run, locale: Locale) -> str:
    """The short commit, and what a missing one means.

    A dash said nothing. There are two ways to have no clean commit and they
    call for different reactions: a dirty tree means this run is not
    reproducible from the repository, and no repository at all means the
    question does not apply.
    """
    if run.git_commit is None:
        note = phrase(locale, "view.commit.none")
        return f'<td class="commit"><span class="chip plain">{escape(note)}</span></td>'
    commit = run.git_commit
    dirty = commit.endswith("-dirty")
    short = commit.removesuffix("-dirty")[:7]
    chip = (
        f'<span class="chip warn">{escape(phrase(locale, "view.commit.dirty"))}</span>'
        if dirty
        else ""
    )
    return f'<td class="commit"><code>{escape(short)}</code>{chip}</td>'


def _errored_cases(run: Run) -> int:
    """How many cases this run could not judge.

    Read here rather than asked of the store, because it decides whether the
    row offers a promotion at all — and `promote_baseline` refuses an errored
    run anyway. Showing the refusal before it happens is the difference between
    a screen that explains and one that argues.
    """
    return len(
        {
            case.case_id
            for case in run.results
            for verdict in case.verdicts
            if verdict.status == "error"
        }
    )


def nav(locale: Locale, *, here: str, suite: str) -> str:
    """The bar every screen carries: where you are, and the language switch.

    The switch is a link and not a preference: the view is a developer's tool
    with no state of its own, so nothing is remembered between requests. The
    document a customer receives still takes its locale from `report --locale`,
    which is mandatory there and defaulted here — a terminal and a document are
    different things (see `CLAUDE.md`).
    """
    runs_class = ' class="here"' if here == "runs" else ""
    parts: list[str] = [
        f'<a href="/?locale={locale}"{runs_class}>'
        f"{escape(phrase(locale, 'view.nav.runs'))}</a>",
        f'<span class="suite">{escape(suite)}</span>',
        '<span class="spacer"></span>',
    ]
    for candidate in LOCALES:
        mark = ' class="here"' if candidate == locale else ""
        parts.append(f'<a href="?locale={candidate}"{mark}>{candidate}</a>')
    return f'<nav class="bar">{"".join(parts)}</nav>\n'


def _document(title: str, locale: Locale, body: str, *, wide: bool = False) -> str:
    return (
        "<!DOCTYPE html>\n"
        f'<html lang="{escape(locale)}">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{escape(title)}</title>\n"
        f"<style>\n{CSS}{VIEW_CSS}</style>\n"
        "</head>\n"
        f"<body{' class="wide"' if wide else ''}>\n"
        f"{body}"
        "</body>\n"
        "</html>\n"
    )


# --------------------------------------------------------------------------- #
# 1. The runs
# --------------------------------------------------------------------------- #


def runs_page(
    runs: Sequence[tuple[str, Run]],
    *,
    baseline_key: str | None,
    config_hash: str,
    locale: Locale,
    suite: str,
    ignored: str = "",
    message: str = "",
) -> str:
    """Every readable run, newest first, with its aggregates beside it.

    The aggregates are the point. Choosing which run to promote means reading
    precision and accuracy down a column and taking the median — with key, date
    and commit alone the choice cannot be made, and the first green run gets
    promoted instead, which is how an unlucky baseline gets frozen.

    **Every action belongs to a row.** There is no selection to make first and
    no control above the table acting on whatever is ticked: a row compares
    itself with the baseline, and a row that may become the baseline says so
    with a button. Where the button is absent the marker in its place names the
    refusal that would have come — `BASELINE`, `OLDER CONFIG`, `NOT JUDGED` —
    so the rule is met before the click and not through one.

    `config_hash` is the configuration currently in force, and it is mandatory
    for the reason `environment` is: a screen that had to guess it would tell
    every run it is current, or none of them, and either answer is confidently
    wrong.
    """
    ordered = sorted(runs, key=lambda pair: (pair[1].created_at, pair[0]), reverse=True)
    measures: list[str] = []
    for _key, run in ordered:
        for verdict in run.aggregate:
            if verdict.score.name not in measures:
                measures.append(verdict.score.name)

    baseline_scores: dict[str, float] = {}
    for key, run in ordered:
        if key == baseline_key:
            baseline_scores = {
                v.score.name: v.score.score
                for v in run.aggregate
                if v.score.score is not None
            }

    body: list[str] = [nav(locale, here="runs", suite=suite)]
    title = phrase(locale, "view.title.runs", suite=suite)
    body.append(f"<h1>{escape(title)}</h1>\n")
    if message:
        body.append(f'<p class="note">{escape(message)}</p>\n')

    if not ordered:
        body.append(f'<p class="empty">{escape(phrase(locale, "view.no_runs"))}</p>\n')
    else:
        labels = _when_labels([(k, r.created_at) for k, r in ordered], locale)
        body.append(
            _runs_table(
                ordered,
                measures,
                baseline_scores,
                baseline_key,
                config_hash,
                labels,
                locale,
            )
        )
        if not measures:
            body.append(
                f'<p class="note">{escape(phrase(locale, "view.no_aggregates"))}</p>\n'
            )
        # Below the table, because it answers a question the table raises. Only
        # when there are two runs to put on either side of it: with one, the
        # bar could ask nothing a comparison would answer.
        if len(ordered) > 1:
            body.append(_compare_form(ordered, labels, locale))

    if ignored:
        told = phrase(locale, "view.ignored", note=ignored)
        body.append(f'<p class="note">{escape(told)}</p>\n')
    return _document(title, locale, "".join(body), wide=True)


def _runs_table(
    ordered: Sequence[tuple[str, Run]],
    measures: Sequence[str],
    baseline_scores: Mapping[str, float],
    baseline_key: str | None,
    config_hash: str,
    labels: Mapping[str, str],
    locale: Locale,
) -> str:
    head = (
        "".join(
            f"<th>{escape(phrase(locale, key))}</th>"
            for key in (
                "view.column.key",
                "view.column.env",
                "view.column.commit",
            )
        )
        + f'<th class="num">{escape(phrase(locale, "view.column.cases"))}</th>'
        + "".join(f'<th class="num">{escape(name)}</th>' for name in measures)
        + f'<th class="act">{escape(phrase(locale, "view.column.actions"))}</th>'
    )

    rows: list[str] = []
    for key, run in ordered:
        is_baseline = key == baseline_key
        # Only a run that is *not* the baseline is attenuated for an old
        # configuration: the dimming is the row-wide half of the `OLDER CONFIG`
        # marker, and the baseline does not carry that marker — it already
        # carries its own, and the report is where a reference under changed
        # rules is called out.
        stale = not is_baseline and run.config_hash != config_hash
        classes = " ".join(
            name for name, on in (("is-baseline", is_baseline), ("stale", stale)) if on
        )
        rows.append(f'<tr class="{classes}">' if classes else "<tr>")
        rows.append(
            _run_cell(key, labels.get(key, run.created_at), stamp=_stamp(run, locale))
        )
        rows.append(f"<td>{escape(run.environment)}</td>")
        rows.append(_commit_cell(run, locale))
        rows.append(f'<td class="num">{len(run.results)}</td>')

        by_name = {v.score.name: v for v in run.aggregate}
        for measure in measures:
            verdict = by_name.get(measure)
            if verdict is None or verdict.score.score is None:
                rows.append('<td class="num absent">—</td>')
                continue
            delta = (
                ""
                if is_baseline
                else _delta(verdict.score.score, baseline_scores.get(measure), locale)
            )
            rows.append(f'<td class="num">{_score(verdict)}{delta}</td>')
        rows.append(
            _actions_cell(
                key,
                run,
                is_baseline=is_baseline,
                stale=stale,
                has_baseline=baseline_key is not None,
                locale=locale,
            )
        )
        rows.append("</tr>")
    return (
        f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(rows)}</tbody></table>\n"
    )


def _actions_cell(
    key: str,
    run: Run,
    *,
    is_baseline: bool,
    stale: bool,
    has_baseline: bool,
    locale: Locale,
) -> str:
    """What this row can do — and, where it can do less, why.

    Two actions, both belonging to the run they sit beside. Comparing is a
    `GET`, so it is a link; promoting writes, so it is a form of its own with
    the key already in it. Nothing here reads a selection, which is what lets
    the promotion of one run and the comparison of another be one click each
    rather than two clicks and a tick.

    The button appears only where `promote_baseline` would accept, and where it
    does not the marker names the refusal that would have come. The order is
    `promote_baseline`'s own — configuration before errors — so the page can
    never announce a different reason from the one the call would give. The
    refusal in the store stays: it is the second line, not the first way the
    rule is met.
    """
    parts: list[str] = []
    # No link on the baseline's own row — a run compared with itself has
    # nothing to report — and none at all before there is a baseline, rather
    # than a link whose only possible answer is a 404.
    if has_baseline and not is_baseline:
        parts.append(
            f'<a class="action" href="/compare?run={escape(key)}&amp;locale={locale}"'
            f' title="{escape(phrase(locale, "view.action.compare.title"))}">'
            f"{escape(phrase(locale, 'view.action.compare'))}</a>"
        )

    if is_baseline:
        parts.append(_chip("view.baseline", locale))
    elif stale:
        parts.append(
            _chip("view.chip.older_config", locale, warn=True, why="view.promote.older")
        )
    elif errored := _errored_cases(run):
        parts.append(
            _chip(
                "view.chip.errored",
                locale,
                warn=True,
                why="view.promote.errored",
                count=errored,
            )
        )
    else:
        parts.append(
            '<form method="post" action="/promote">'
            f'<input type="hidden" name="locale" value="{locale}">'
            f'<input type="hidden" name="run" value="{escape(key)}">'
            f'<button type="submit">'
            f"{escape(phrase(locale, 'view.promote.button'))}</button>"
            "</form>"
        )
    return f'<td class="act">{"".join(parts)}</td>'


def _chip(
    key: str, locale: Locale, *, warn: bool = False, why: str = "", **params: object
) -> str:
    """A marker, and the sentence behind it.

    The chip is three words because a column of them has to be scannable; the
    `title` is the paragraph, because "why can't I" deserves a fact about this
    run and not a shorter version of the same three words.
    """
    tooltip = f' title="{escape(phrase(locale, why, **params))}"' if why else ""
    label = escape(phrase(locale, key, **params))
    return f'<span class="chip{" warn" if warn else ""}"{tooltip}>{label}</span>'


def _compare_form(
    runs: Sequence[tuple[str, Run]], labels: Mapping[str, str], locale: Locale
) -> str:
    """Free comparison of any two runs, under the table it draws from.

    Comparing against the baseline is the release question, and it is now a
    button on every row — so it is gone from here: an `against` list that
    offered "baseline" alongside the runs would be two ways to ask one
    question, and the shorter one is already on the row.

    What is left is the question no row can ask: run 1 against run 3 of a
    calibration, which is the noise reading, and the one that says what
    tolerance to set.

    The options read as moments, not as keys: a select whose entries are
    forty-nine characters of slug is a select nobody chooses from.
    """
    options = "".join(
        f'<option value="{escape(key)}">'
        f"{escape(labels.get(key, run.created_at))} · {escape(run.environment)}"
        "</option>"
        for key, run in runs
    )
    return (
        '<form method="get" action="/compare" class="picker">\n'
        f'<input type="hidden" name="locale" value="{locale}">\n'
        f"<label>{escape(phrase(locale, 'view.compare.pick'))} "
        f'<select name="run">{options}</select></label>\n'
        f"<label>{escape(phrase(locale, 'view.compare.against'))} "
        f'<select name="against">{options}</select></label>\n'
        f'<button type="submit">{escape(phrase(locale, "view.compare.go"))}</button>\n'
        "</form>\n"
    )


# --------------------------------------------------------------------------- #
# 2. The comparison
# --------------------------------------------------------------------------- #


def compare_page(run: Run, against: Run, *, locale: Locale, suite: str) -> str:
    """The exported report, with a navigation bar in front of it.

    `render_html` is called, not reimplemented, and nothing else is touched —
    not the width, not the dates. This page *is* the document, so it keeps the
    document's rules: ISO timestamps, six decimals, `52rem`. Removing the bar
    yields exactly what `digline report` writes, which is what the test
    asserts byte for byte.
    """
    document = render_html(compare(run, against), run, against, locale=locale)
    bar = nav(locale, here="compare", suite=suite)
    # The view's stylesheet has to reach the bar, and the report's `<style>` is
    # the only one in the document.
    document = document.replace("</style>\n", f"{VIEW_CSS}</style>\n", 1)
    return document.replace("<body>\n", f"<body>\n{bar}", 1)


# --------------------------------------------------------------------------- #
# 3. One case, down the runs
# --------------------------------------------------------------------------- #


def case_page(history: CaseHistory, *, locale: Locale, suite: str) -> str:
    """The calibration table: one row per run, one column per assertion.

    Sampled checks show their raw votes under the combined score. That is the
    view that was built by hand with a script to decide which run to promote,
    and building it by hand is what put it on this list.
    """
    names = history.assertion_names
    head = (
        f"<th>{escape(phrase(locale, 'view.column.run'))}</th>"
        f"<th>{escape(phrase(locale, 'view.column.env'))}</th>"
        + "".join(f'<th class="num">{escape(name)}</th>' for name in names)
    )

    labels = _when_labels([(e.run_key, e.created_at) for e in history.entries], locale)
    rows = "".join(
        _case_row(entry, history, names, labels, locale) for entry in history.entries
    )
    title = phrase(locale, "view.title.case", case_id=history.case_id, suite=suite)
    heading = phrase(locale, "view.case.title", case_id=history.case_id)
    note = phrase(locale, "view.case.votes_note")
    set_aside = phrase(locale, "view.suspend.title", case_id=history.case_id)
    body = (
        nav(locale, here="case", suite=suite)
        + f"<h1>{escape(title)}</h1>\n"
        + f"<h2>{escape(heading)}</h2>\n"
        + f"<table><thead><tr>{head}</tr></thead><tbody>{rows}</tbody></table>\n"
        + f'<p class="note">{escape(note)}</p>\n'
        + f'<p class="note"><a href="/suspend/{escape(history.case_id)}'
        + f'?locale={locale}">{escape(set_aside)}</a></p>\n'
    )
    return _document(title, locale, body, wide=True)


def _case_row(
    entry: CaseEntry,
    history: CaseHistory,
    names: Sequence[str],
    labels: Mapping[str, str],
    locale: Locale,
) -> str:
    prefix = (
        "<tr>"
        + _run_cell(
            entry.run_key,
            labels.get(entry.run_key, entry.created_at),
            href=f"/compare?run={entry.run_key}&locale={locale}",
        )
        + f"<td>{escape(entry.environment)}</td>"
    )
    if not entry.present or entry.suspended is not None:
        key = "view.case.absent" if not entry.present else "view.case.suspended"
        span = len(names) or 1
        return (
            prefix
            + f'<td class="absent" colspan="{span}">'
            + f"{escape(phrase(locale, key))}</td></tr>"
        )

    by_name = history.scores(entry)
    cells: list[str] = []
    for name in names:
        verdict = by_name.get(name)
        if verdict is None:
            cells.append('<td class="num absent">—</td>')
            continue
        votes = _votes(verdict)
        extra = f'<div class="votes">{escape(votes)}</div>' if votes else ""
        cells.append(f'<td class="num">{_score(verdict)}{extra}</td>')
    return prefix + "".join(cells) + "</tr>"


# --------------------------------------------------------------------------- #
# 4. Suspension — which shows, and does not write
# --------------------------------------------------------------------------- #


def suspension_snippet(case_id: str, reason: str) -> str:
    """The line to add to the suite. Produced, never applied.

    A suspension is a field on `Case`, and `Case` is Python in the user's
    repository. A page that edited it would be writing code from a browser, and
    the reason would land outside the review where every other decision about
    the suite is made. So the page hands over the edit and the developer
    commits it.
    """
    quoted = reason.replace("\\", "\\\\").replace('"', '\\"')
    return f'Case(id="{case_id}", suspended="{quoted}")'


def suspend_page(
    case_id: str, *, reason: str, locale: Locale, suite: str, error: str = ""
) -> str:
    title = phrase(locale, "view.title.suspend", case_id=case_id, suite=suite)
    body: list[str] = [
        nav(locale, here="suspend", suite=suite),
        f"<h1>{escape(phrase(locale, 'view.suspend.title', case_id=case_id))}</h1>\n",
        f'<p class="note">{escape(phrase(locale, "view.suspend.explain"))}</p>\n',
        '<form method="get" class="picker">\n',
        f'<input type="hidden" name="locale" value="{locale}">\n',
        f"<label>{escape(phrase(locale, 'view.suspend.reason'))} "
        f'<input type="text" name="reason" size="44" '
        f'value="{escape(reason)}"></label>\n',
        f'<button type="submit">{escape(phrase(locale, "view.suspend.show"))}'
        "</button>\n",
        "</form>\n",
    ]
    if error:
        body.append(f'<p class="empty">{escape(error)}</p>\n')
    elif reason:
        snippet = suspension_snippet(case_id, reason)
        body.append(f'<pre class="snippet">{escape(snippet)}</pre>\n')
        hint = phrase(locale, "view.copy_snippet")
        body.append(f'<p class="note">{escape(hint)}</p>\n')
    return _document(title, locale, "".join(body))


def locale_of(
    raw: Mapping[str, Sequence[str]] | None, default: Locale = "en"
) -> Locale:
    """The requested locale, or the default.

    `en` by default because this is a developer's screen, not a document: the
    mandatory `--locale` of `report` exists because a customer did not choose
    English, and nobody receives this page.
    """
    if not raw:
        return default
    values = raw.get("locale") or ()
    candidate = values[0] if values else ""
    return candidate if candidate in LOCALES else default  # pyright: ignore[reportReturnType]
