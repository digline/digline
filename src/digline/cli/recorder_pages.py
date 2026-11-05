"""The recorder's three views of `digline view`, as pure functions. (ADR 0061 §1)

Each takes the structure the command's own host function returns and gives
back a page; none reads a file or computes a fact of its own. The recordings
are `import_listing`'s `ImportListing`, laid out with the sentences
`listing_lines` prints; the answers across setups are `record_compare`'s
`RecordComparison`; the recorder is `recorder_status`'s `TenantRecorder`. A
page and a command that worked a fact out twice would be two places that can
disagree.

**Why here and not in `digline.report.pages`.** The import's structure lives in
`digline.host`, which the report may not import, and `digline.cli` is the one
layer that sees both. The functions are pure all the same, and tested without
a socket.

**Nothing is judged, ranked or proposed** (ADR 0037 §6, at the page by ADR 0061
§2). The answers come in the files' order and the setups in the order of their
first answer; nothing is pre-selected and there is nothing that acts on many.
The one number the page draws that the command does not print is an answer's
length, in the chart, and it is the length of the text the table shows.

**The two writes, and under each button the command** (ADR 0061 §2). On a
server started with `--allow-record`, the recordings carry a form that names
answers good or bad with the person's mark, and the recorder two forms that
switch it on and off. Each form is drawn from a list of `Field`s, each naming
the flag it fills, and the line under its button is `command_line` of that
list as the form is served: the command that does what the button does. The
page's script keeps the line equal to the fields as they are edited, reading
the flags from the attributes written here; it holds none of its own (ADR 0061
§7). Without the flag the page has no form, and says where the writes are.
"""

from __future__ import annotations

import json
import shlex
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlencode

from digline.host.importing import (
    ImportAnswer,
    ImportListing,
    answer_state,
    closing_lines,
    group_line,
    input_line,
    setup_line,
)
from digline.report import Locale, escape, phrase
from digline.report.pages import (
    answer_address,
    recorder_address,
    recordings_address,
    screen,
    setups_address,
)
from digline.wire.record_compare import SHORT, ComparedCase, RecordComparison
from digline.wire.recorder import TenantRecorder

__all__ = [
    "SHOWN_CHARS",
    "Field",
    "answer_page",
    "command_line",
    "import_fields",
    "switch_fields",
    "recorder_page",
    "recordings_page",
    "setups_page",
]

#: How much of an answer the listing shows before `show all`. The whole answer
#: is one link away, on a page of its own.
SHOWN_CHARS = 200

#: The data block the chart reads, and the two files that draw it (ADR 0061 §7).
_SCRIPTS = (
    '<script src="/static/uPlot.iife.min.js"></script>\n'
    '<script src="/static/chart.js"></script>\n'
)

#: digline's one script, on a page with a form and no chart: the half of it
#: that keeps a command line equal to its form (ADR 0061 §7).
_GLUE = '<script src="/static/chart.js"></script>\n'


def _p(text: str, cls: str = "") -> str:
    attribute = f' class="{cls}"' if cls else ""
    return f"<p{attribute}>{escape(text)}</p>\n"


def _hue(setup: str, order: Sequence[str]) -> str:
    """The class that gives a setup its colour: one per setup, in the order the
    page lists them, the same in a table, the chart and a row."""
    index = order.index(setup) if setup in order else 0
    return f"setup s{index % 3 + 1}"


def _tag(setup: str, order: Sequence[str], locale: Locale, suffix: str = "") -> str:
    """A setup by the first eight characters of its digest, as `digline record
    compare` prints it; the whole digest, which the cases file holds, is in the
    title, so a browser shows it without a script."""
    title = phrase(locale, "view.setups.digest", digest=setup)
    return (
        f'<code class="{_hue(setup, order)}" title="{escape(title)}">'
        f"{escape(setup[:SHORT])}</code>{escape(suffix)}"
    )


def _head(
    prefix: str, names: Sequence[str], locale: Locale, *, numbers: bool = False
) -> str:
    """Table headings, one per name, each the phrase `prefix.name`."""
    cls = ' class="num"' if numbers else ""
    return "".join(
        f"<th{cls}>{escape(phrase(locale, f'{prefix}.{name}'))}</th>" for name in names
    )


def _writes_note(locale: Locale, writes: Sequence[str] | None) -> str:
    if writes is not None:
        return ""
    return _p(phrase(locale, "view.writes.behind"), "note")


# --------------------------------------------------------------------------- #
# The command under each button
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class Field:
    """One field of a form that writes, as the command line reads it.

    `name` and `value` are what the form posts. `flag` is the option the field
    fills, and `word` the value the line gives it: the field's own value where
    the person types it, the answer's id for a yes or no, nothing for a switch.
    `set` is whether the form is served with it filled or chosen."""

    name: str
    value: str
    flag: str
    word: str | None
    set: bool
    kind: str = "text"


def command_line(base: Sequence[str], fields: Sequence[Field]) -> str:
    """The command a form runs: its base and, in the form's order, each field
    that is set, its flag and its word. Each word is quoted for a POSIX
    shell, the way the page's script quotes it."""
    words = list(base)
    for field in fields:
        if not field.set:
            continue
        words.append(field.flag)
        if field.word is not None:
            words.append(field.word)
    return shlex.join(words)


def _command(base: Sequence[str], fields: Sequence[Field], locale: Locale) -> str:
    """The line under a button, and the base the page's script starts from."""
    return (
        f'<pre class="snippet command" data-base="{escape(shlex.join(base))}">'
        f"{escape(command_line(base, fields))}</pre>\n"
        f"{_p(phrase(locale, 'view.command.note'), 'note')}"
    )


def _input(field: Field, label: str) -> str:
    """A field the person fills, with the flag it fills written on it."""
    common = f'name="{escape(field.name)}" data-flag="{escape(field.flag)}"' + (
        ""
        if field.word is None or field.kind in ("text", "number")
        else f' data-value="{escape(field.word)}"'
    )
    if field.kind == "checkbox":
        checked = " checked" if field.set else ""
        return (
            f'<label><input type="checkbox" {common} value="{escape(field.value)}"'
            f"{checked}> {escape(label)}</label>\n"
        )
    # Text, with a numeric keyboard where a number is asked for, and not
    # `type="number"`: a browser shows that in the system's locale, `0,5`, and
    # what is typed should be what the line and the form carry. One that is not
    # a number is refused in the command's words.
    mode = ' inputmode="decimal"' if field.kind == "number" else ""
    return (
        f"<label>{escape(label)} "
        f'<input type="text"{mode} {common} value="{escape(field.value)}">'
        "</label>\n"
    )


# --------------------------------------------------------------------------- #
# The recordings, as the import lists them
# --------------------------------------------------------------------------- #


def import_fields(found: ImportListing) -> list[Field]:
    """The import's form as it is served: for each answer that can be named,
    a yes and a no, neither chosen, then the person's mark, empty. Nothing is
    chosen in advance (ADR 0037 §6)."""
    fields: list[Field] = []
    for answer in found.answers:
        if not answer.electable:
            continue
        for value, flag in (("good", "--good"), ("bad", "--bad")):
            fields.append(
                Field(f"answer:{answer.id}", value, flag, answer.id, False, "radio")
            )
    fields.append(Field("by", "", "--by", "", False))
    return fields


def recordings_page(
    found: ImportListing, *, locale: Locale, writes: Sequence[str] | None
) -> str:
    """A suite's recordings, grouped, under the declaration that says where a
    named answer would go: `listing_lines`' sentences, and each answer a row.

    `writes` is the flags every command of this page carries, `--tenant`,
    `--suite` and `--root` as the server was started with them, on a server
    that writes; `None` on one that does not, and then there is no form."""
    declaration = found.declaration
    title = phrase(locale, "view.title.recordings", suite=declaration.suite)
    order = tuple(
        dict.fromkeys(setup for answer in found.answers for setup in answer.setups)
    )
    body = [
        f"<h1>{escape(title)}</h1>\n",
        _p(declaration.line(), "declaration"),
        _p(setup_line(found), "note"),
    ]
    fields = import_fields(found)
    form = writes is not None and len(fields) > 1
    if form:
        address = recordings_address(declaration.tenant, declaration.suite)
        body.append(
            f'<form method="post" action="{escape(address)}" class="writes" '
            "data-writes>\n"
            f'<input type="hidden" name="locale" value="{locale}">\n'
        )
    for number, group in enumerate(found.groups, start=1):
        body.append(f"<h2>{escape(group_line(number, group))}</h2>\n")
        body.append(_answers_table(found, group.answers, order, locale, form=form))
    if form and writes is not None:
        base = ["digline", "record", "import", *writes]
        by = fields[-1]
        body.append(
            '<div class="picker">'
            + _input(by, phrase(locale, "view.import.by"))
            + f'<button type="submit">{escape(phrase(locale, "view.import.button"))}'
            "</button></div>\n" + _command(base, fields, locale) + "</form>\n"
        )
    body.extend(_p(line, "note") for line in closing_lines(found))
    body.append(_writes_note(locale, writes))
    if form:
        body.append(_GLUE)
    return screen(
        title,
        "".join(body),
        locale=locale,
        suite=declaration.suite,
        here="recordings",
    )


def _answers_table(
    found: ImportListing,
    answers: Sequence[ImportAnswer],
    order: Sequence[str],
    locale: Locale,
    *,
    form: bool = False,
) -> str:
    head = _head("view.recordings.column", ("id", "when", "setup", "answer"), locale)
    head += _head("view.recordings.column", ("times",), locale, numbers=True)
    head += _head("view.recordings.column", ("state",), locale)
    if form:
        head += _head("view.recordings.column", ("elect",), locale)
    rows = "".join(
        _answer_row(found, answer, order, locale, form=form) for answer in answers
    )
    return f"<table><thead><tr>{head}</tr></thead><tbody>{rows}</tbody></table>\n"


def _answer_row(
    found: ImportListing,
    answer: ImportAnswer,
    order: Sequence[str],
    locale: Locale,
    *,
    form: bool = False,
) -> str:
    declaration = found.declaration
    whole = answer_address(declaration.tenant, declaration.suite, answer.id)
    earlier = f" ({phrase(locale, 'view.recordings.earlier')})"
    setups = ", ".join(
        _tag(setup, order, locale, "" if setup == found.setup else earlier)
        for setup in answer.setups
    )
    shown = answer.text[:SHOWN_CHARS]
    more = ""
    if shown != answer.text:
        shown += "…"
        label = escape(phrase(locale, "view.recordings.whole"))
        more = f' <a href="{escape(whole)}?locale={locale}">{label}</a>'
    attached = (
        f'<div class="note">'
        f"{escape(phrase(locale, 'view.recordings.attached', count=answer.attached))}"
        "</div>"
        if answer.attached
        else ""
    )
    # An episode the proxy read with no case given takes its first call's,
    # and says so beside the id, as `digline record import` does after the
    # input. (ADR 0062 §3)
    first_call = (
        f'<div class="note">'
        f"{escape(phrase(locale, 'view.recordings.from_first_call'))}</div>"
        if answer.case_from_first_call
        else ""
    )
    when = answer.first_at or phrase(locale, "view.recordings.undated")
    return (
        "<tr>"
        f'<td><a href="{escape(whole)}?locale={locale}">'
        f'<code class="key">{escape(answer.id)}</code></a>{first_call}{attached}</td>'
        f'<td class="when">{escape(when)}</td>'
        f"<td>{setups}</td>"
        f'<td class="said">{escape(shown)}{more}</td>'
        f'<td class="num">×{answer.times}</td>'
        f'<td class="state">{escape(answer_state(answer))}</td>'
        f"{_elect(answer) if form else ''}"
        "</tr>"
    )


def _elect(answer: ImportAnswer) -> str:
    """A yes and a no for an answer that can be named, neither chosen; nothing
    for one that cannot. The flag is the label: it is what the command takes,
    and a flag is not translated."""
    if not answer.electable:
        return "<td></td>"
    choices = "".join(
        f'<label class="pick"><input type="radio" name="answer:{escape(answer.id)}" '
        f'value="{value}" data-flag="{flag}" data-value="{escape(answer.id)}"> '
        f"{flag}</label>"
        for value, flag in (("good", "--good"), ("bad", "--bad"))
    )
    return f'<td class="act">{choices}</td>'


def answer_page(found: ImportListing, answer: ImportAnswer, *, locale: Locale) -> str:
    """One recorded answer, whole, with the input it was given."""
    declaration = found.declaration
    title = phrase(
        locale, "view.title.answer", answer=answer.id, suite=declaration.suite
    )
    order = tuple(dict.fromkeys(answer.setups))
    when = answer.first_at or phrase(locale, "view.recordings.undated")
    back = phrase(locale, "view.answer.back")
    href = recordings_address(declaration.tenant, declaration.suite)
    body = (
        f"<h1>{escape(title)}</h1>\n"
        + _p(declaration.line(), "declaration")
        + '<dl class="meta">'
        + f"<dt>{escape(phrase(locale, 'view.recordings.column.when'))}</dt>"
        + f"<dd>{escape(when)}</dd>"
        + f"<dt>{escape(phrase(locale, 'view.recordings.column.setup'))}</dt>"
        + f"<dd>{', '.join(_tag(s, order, locale) for s in answer.setups)}</dd>"
        + f"<dt>{escape(phrase(locale, 'view.recordings.column.times'))}</dt>"
        + f"<dd>×{answer.times}</dd>"
        + f"<dt>{escape(phrase(locale, 'view.recordings.column.state'))}</dt>"
        + f"<dd>{escape(answer_state(answer))}</dd>"
        + "</dl>\n"
        + f"<h2>{escape(phrase(locale, 'view.answer.input'))}</h2>\n"
        + f'<pre class="snippet">{escape(input_line(answer))}</pre>\n'
        + f"<h2>{escape(phrase(locale, 'view.answer.response'))}</h2>\n"
        + f'<pre class="snippet">{escape(answer.text)}</pre>\n'
        + f'<p><a href="{escape(href)}?locale={locale}">{escape(back)}</a></p>\n'
    )
    return screen(
        title, body, locale=locale, suite=declaration.suite, here="recordings"
    )


# --------------------------------------------------------------------------- #
# One suite's answers across setups
# --------------------------------------------------------------------------- #


def setups_page(found: RecordComparison, *, locale: Locale) -> str:
    """`record_compare`'s structure: per case, the answers under each setup in
    the order they were recorded, the setups by their digests; two setups side
    by side with the keys they differ on; and, for one case, the chart."""
    title = phrase(locale, "view.title.setups", suite=found.suite)
    order = found.setups
    body = [
        f"<h1>{escape(title)}</h1>\n",
        _p(
            phrase(locale, "view.setups.lead", suite=found.suite, tenant=found.tenant),
            "note",
        ),
        f"<h2>{escape(phrase(locale, 'view.setups.setups'))}</h2>\n",
        f"<p>{' '.join(_tag(s, order, locale) for s in order) or '—'}</p>\n",
    ]
    if len(order) > 1:
        body.append(_pair_form(found, locale))
    kept = [
        part
        for part in (
            None if found.case is None else f"case {found.case}",
            None if found.since is None else f"since {found.since}",
        )
        if part is not None
    ]
    if kept:
        body.append(
            _p(phrase(locale, "view.setups.only", filters=", ".join(kept)), "note")
        )
        every = setups_address(found.tenant, found.suite)
        label = escape(phrase(locale, "view.setups.every_case"))
        body.append(f'<p><a href="{escape(every)}?locale={locale}">{label}</a></p>\n')
    if found.pair is not None:
        a, b = (setup[:SHORT] for setup in found.pair)
        body.append(_p(phrase(locale, "view.setups.side", a=a, b=b)))
    if found.setup_keys is not None:
        body.append(_keys(found, locale))
    chart = len(found.cases) == 1 and found.case is not None
    if chart:
        body.append(_chart(found.cases[0], locale))
    if not found.cases:
        body.append(
            _p(
                phrase(
                    locale, "view.setups.empty", suite=found.suite, tenant=found.tenant
                ),
                "empty",
            )
        )
    for case in found.cases:
        body.append(_case(found, case, order, locale))
    body.append(_not_shown(found, locale))
    if chart:
        body.append(_SCRIPTS)
    return screen(title, "".join(body), locale=locale, suite=found.suite, here="setups")


def _pair_form(found: RecordComparison, locale: Locale) -> str:
    """Two setups to put side by side: a GET with the two, as `--setup A B
    --show-setup` names them. Nothing is chosen in advance: each list opens on
    an empty choice."""
    chosen = found.pair or ("", "")
    empty = '<option value=""></option>'

    def options(selected: str) -> str:
        return empty + "".join(
            f'<option value="{escape(setup[:SHORT])}"'
            f"{' selected' if setup == selected else ''}>"
            f"{escape(setup[:SHORT])}</option>"
            for setup in found.setups
        )

    case = (
        ""
        if found.case is None
        else f'<input type="hidden" name="case" value="{escape(found.case)}">\n'
    )
    return (
        '<form method="get" class="picker">\n'
        f'<input type="hidden" name="locale" value="{locale}">\n'
        f"{case}"
        f"<label>{escape(phrase(locale, 'view.setups.pick'))} "
        f'<select name="setup">{options(chosen[0])}</select></label>\n'
        f"<label>{escape(phrase(locale, 'view.setups.and'))} "
        f'<select name="setup">{options(chosen[1])}</select></label>\n'
        f'<button type="submit">{escape(phrase(locale, "view.setups.go"))}</button>\n'
        "</form>\n"
    )


def _keys(found: RecordComparison, locale: Locale) -> str:
    """The keys two setups differ on: each value by its first line, clipped,
    and its length where that line is not all of it. Never a prompt whole."""
    keys = found.setup_keys or ()
    same = found.same_keys or 0
    if not keys:
        return _p(phrase(locale, "view.setups.keys.none", same=same), "note")
    rows: list[str] = []
    for key in keys:
        cells: list[str] = []
        for side, value in (("A", key.a), ("B", key.b)):
            if value is None:
                cells.append(
                    f'<td class="absent">'
                    f"{escape(phrase(locale, 'view.setups.absent', side=side))}</td>"
                )
                continue
            shown = json.dumps(value.preview, ensure_ascii=False)
            length = (
                f'<div class="note">'
                f"{escape(phrase(locale, 'view.setups.chars', chars=value.chars))}"
                "</div>"
                if value.clipped
                else ""
            )
            cells.append(f"<td><code>{escape(shown)}</code>{length}</td>")
        rows.append(f"<tr><td><code>{escape(key.key)}</code></td>{''.join(cells)}</tr>")
    heading = phrase(locale, "view.setups.keys", same=same)
    return (
        f"<h2>{escape(heading)}</h2>\n"
        "<table><thead><tr><th></th><th>A</th><th>B</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>\n"
    )


def _case(
    found: RecordComparison, case: ComparedCase, order: Sequence[str], locale: Locale
) -> str:
    heading = phrase(locale, "view.setups.case", case_id=case.id, kind=case.kind)
    # The pair chosen stays chosen: the case alone, side by side as before.
    query = [("case", case.id)]
    query += [("setup", setup[:SHORT]) for setup in found.pair or ()]
    query.append(("locale", locale))
    alone = setups_address(found.tenant, found.suite) + "?" + urlencode(query)
    link = (
        ""
        if found.case is not None
        else f' <a href="{escape(alone)}">'
        f"{escape(phrase(locale, 'view.setups.over_time'))}</a>"
    )
    columns = _head("view.setups.column", ("when", "setup", "digest", "answer"), locale)
    columns += _head("view.setups.column", ("times",), locale, numbers=True)
    rows: list[str] = []
    for setup in case.setups:
        side = ""
        if found.pair is not None:
            side = "A " if setup.setup == found.pair[0] else "B "
        tag = f"{escape(side)}{_tag(setup.setup, order, locale)}"
        if not setup.answers:
            rows.append(
                f'<tr><td></td><td>{tag}</td><td colspan="3" class="absent">'
                f"{escape(phrase(locale, 'view.setups.nothing'))}</td></tr>"
            )
        for answer in setup.answers:
            undated = phrase(locale, "view.recordings.undated")
            last = phrase(locale, "view.setups.through", last=answer.last_at or undated)
            through = (
                f'<div class="note">{escape(last)}</div>' if answer.times > 1 else ""
            )
            when = answer.first_at or undated
            rows.append(
                "<tr>"
                f'<td class="when">{escape(when)}</td>'
                f"<td>{tag}</td>"
                f"<td><code>{escape(answer.digest)}</code></td>"
                f'<td class="said">{escape(answer.text)}</td>'
                f'<td class="num">×{answer.times}{through}</td>'
                "</tr>"
            )
    return (
        f"<h2>{escape(heading)}{link}</h2>\n"
        f'<p class="note"><code>'
        f"{escape(json.dumps(case.vars, ensure_ascii=False, sort_keys=True))}"
        "</code></p>\n"
        f"<table><thead><tr>{columns}</tr></thead><tbody>{''.join(rows)}</tbody>"
        "</table>\n"
    )


def _seconds(recorded_at: str | None) -> float | None:
    """`recorded_at` as seconds since the epoch, for the chart's axis, or
    `None` where it carries no instant with its offset. A recorded value read,
    never the clock."""
    if recorded_at is None:
        return None
    try:
        instant = datetime.fromisoformat(recorded_at)
    except ValueError:
        return None
    return None if instant.tzinfo is None else instant.timestamp()


def _chart(case: ComparedCase, locale: Locale) -> str:
    """One case over time, one series per setup: a point for each answer at
    the instant it was first recorded, and a second at the same height at the
    instant a run of equal answers ended. The numbers go in a data block the
    page carries and the browser does not run; `chart.js` hands them to uPlot.
    """
    points: list[tuple[float, str, int]] = []
    for setup in case.setups:
        for answer in setup.answers:
            for at in dict.fromkeys(
                (answer.first_at, answer.last_at if answer.times > 1 else None)
            ):
                seconds = _seconds(at)
                if seconds is not None:
                    points.append((seconds, setup.setup, len(answer.text)))
    names = [setup.setup for setup in case.setups]
    xs = sorted({point[0] for point in points})
    ys: list[list[int | None]] = [[None] * len(xs) for _ in names]
    for seconds, setup, length in points:
        ys[names.index(setup)][xs.index(seconds)] = length
    data = {
        "setups": [name[:SHORT] for name in names],
        "x": xs,
        "y": ys,
        "ymax": max((length for _, _, length in points), default=1) * 1.15,
        "label": phrase(locale, "view.setups.chart.label"),
    }
    # `<` written `<`: a label or a digest cannot close the block.
    block = json.dumps(data, sort_keys=True).replace("<", "\\u003c")
    return (
        '<div class="card">'
        '<div id="series-chart" class="chart"></div>'
        f'<script type="application/json" id="series-data">{block}</script>'
        f'<p class="legend-note">{escape(phrase(locale, "view.setups.chart"))}</p>'
        "</div>\n"
    )


def _not_shown(found: RecordComparison, locale: Locale) -> str:
    """What the suite's recordings hold that is not a case, counted as the
    import counts it."""
    counts = [
        ("orphans", found.orphans),
        ("detached", found.detached),
        ("interrupted", found.interrupted),
        ("oversize", found.oversize),
        ("unreadable", found.unreadable),
    ]
    if found.since is not None:
        counts.append(("undated", found.undated))
    parts = ", ".join(
        f"{count} {phrase(locale, f'view.not_shown.{name}')}" for name, count in counts
    )
    return _p(f"{phrase(locale, 'view.not_shown')}: {parts}", "note")


# --------------------------------------------------------------------------- #
# The recorder of one tenant
# --------------------------------------------------------------------------- #


def switch_fields(status: TenantRecorder) -> list[Field]:
    """`digline record on`'s form as it is served: each value the switch file
    declares already in its field, so the line under the button is the command
    that writes the file as it is, and an empty field keeps what the file has,
    as an absent flag does."""
    declared = set(status.declared)

    def value(key: str, held: object) -> str:
        return "" if key not in declared or held is None else str(held)

    fields = [
        Field(
            "production",
            "1",
            "--production",
            None,
            "production" in declared,
            "checkbox",
        ),
    ]
    for key, held, kind in (
        ("sample", status.sample, "number"),
        ("redact", status.redact, "text"),
        ("ceiling", status.ceiling, "number"),
        ("interval", status.interval, "number"),
    ):
        shown = value(key, held)
        fields.append(Field(key, shown, f"--{key}", shown, bool(shown), kind))
    return fields


def _switch_forms(status: TenantRecorder, writes: Sequence[str], locale: Locale) -> str:
    """The recorder switched on, with its values, and switched off: two forms,
    each with the command under its button."""
    address = recorder_address(status.tenant)
    fields = switch_fields(status)
    inputs = "".join(
        _input(field, phrase(locale, f"view.switch.{field.name}")) for field in fields
    )
    hidden = f'<input type="hidden" name="locale" value="{locale}">\n'
    on = (
        f'<form method="post" action="{escape(address)}" class="writes" data-writes>\n'
        f"{hidden}"
        '<input type="hidden" name="action" value="on">\n'
        f'<div class="picker">{inputs}'
        f'<button type="submit">{escape(phrase(locale, "view.switch.on"))}</button>'
        "</div>\n"
        + _command(["digline", "record", "on", *writes], fields, locale)
        + "</form>\n"
    )
    off = (
        f'<form method="post" action="{escape(address)}" class="writes" data-writes>\n'
        f"{hidden}"
        '<input type="hidden" name="action" value="off">\n'
        '<div class="picker">'
        f'<button type="submit">{escape(phrase(locale, "view.switch.off"))}</button>'
        "</div>\n"
        + _command(["digline", "record", "off", *writes], [], locale)
        + "</form>\n"
    )
    return f"<h2>{escape(phrase(locale, 'view.switch.title'))}</h2>\n{on}{off}"


def recorder_page(
    status: TenantRecorder,
    *,
    suite: str,
    locale: Locale,
    writes: Sequence[str] | None,
) -> str:
    """A tenant's recorder: four figures, the switch and its values, where it
    writes, and its recordings by suite. `suite` is the suite this server was
    started for, the one whose import is read; every other says *not read*.
    `writes` is as `recordings_page` has it: the flags every command of the
    page carries, on a server that writes, and `None` on one that does not."""
    title = phrase(locale, "view.title.recorder", tenant=status.tenant)
    state = (
        "on"
        if status.switch == "valid" and status.on
        else "off"
        if status.switch == "valid"
        else status.switch
    )
    body = [
        f"<h1>{escape(title)}</h1>\n",
        _figures(status, suite, locale),
        '<dl class="meta">',
        f"<dt>{escape(phrase(locale, 'view.recorder.switch'))}</dt>",
        f"<dd>{escape(phrase(locale, f'view.recorder.state.{state}'))} · "
        f"<code>{escape(status.switch_path)}</code></dd>",
    ]
    if status.refusal is not None:
        body.append(
            f"<dt>{escape(phrase(locale, 'view.recorder.refused'))}</dt>"
            f"<dd>{escape(status.refusal)}</dd>"
        )
    if status.switch == "valid":
        body.append(
            f"<dt>{escape(phrase(locale, 'view.recorder.values'))}</dt>"
            f"<dd>{_values(status, locale)}</dd>"
        )
    body.append(
        f"<dt>{escape(phrase(locale, 'view.recorder.writes_to'))}</dt>"
        f"<dd><code>{escape(status.recordings_path)}</code></dd>"
        "</dl>\n"
    )
    if status.switch == "absent":
        body.append(_p(phrase(locale, "view.recorder.absent"), "note"))
    if status.stopped_at_ceiling:
        body.append(_p(phrase(locale, "view.recorder.stopped"), "empty"))
    body.append(_suites(status, locale))
    if status.uncounted:
        # What a process that keeps no counts did not record is not known,
        # which is not the same as nothing (ADR 0062 §2).
        body.append(
            _p(
                phrase(locale, "view.recorder.uncounted", count=status.uncounted),
                "note",
            )
        )
    if status.unreadable:
        body.append(
            _p(
                phrase(locale, "view.recorder.unreadable", count=status.unreadable),
                "note",
            )
        )
    if writes is not None:
        body.append(_switch_forms(status, writes, locale))
        body.append(_GLUE)
    body.append(_writes_note(locale, writes))
    return screen(title, "".join(body), locale=locale, suite=suite, here="recorder")


def _figure(label: str, value: str, note: str = "") -> str:
    small = f"<small>{escape(note)}</small>" if note else ""
    return (
        f'<div class="figure"><span class="label">{escape(label)}</span>'
        f'<span class="value">{escape(value)}</span>{small}</div>'
    )


def _figures(status: TenantRecorder, suite: str, locale: Locale) -> str:
    """The four figures ADR 0061 §1 opens the page with: the size of the
    recordings, the ceiling, the recordings held and those still to import,
    which is a number only for the suite whose draft was read."""
    calls = sum(entry.calls for entry in status.suites)
    episodes = sum(entry.episodes for entry in status.suites)
    read = next((entry for entry in status.suites if entry.suite == suite), None)
    if read is None or read.since_last_import is None:
        to_import = (
            phrase(locale, "view.recorder.not_read"),
            phrase(locale, "view.recorder.not_read.note"),
        )
    else:
        since = "since" if read.imported else "never"
        to_import = (
            str(read.since_last_import),
            phrase(locale, f"view.recorder.to_import.{since}", suite=suite),
        )
    ceiling = (
        phrase(locale, "view.recorder.ceiling.none")
        if status.ceiling is None
        else str(status.ceiling)
    )
    return (
        '<div class="figures">'
        + _figure(
            phrase(locale, "view.recorder.size"),
            str(status.size),
            phrase(locale, "view.recorder.size.note"),
        )
        + _figure(phrase(locale, "view.recorder.ceiling"), ceiling)
        + _figure(
            phrase(locale, "view.recorder.held"),
            str(calls + episodes),
            phrase(locale, "view.recorder.held.note", calls=calls, episodes=episodes),
        )
        + _figure(phrase(locale, "view.recorder.to_import"), *to_import)
        + "</div>\n"
    )


def _values(status: TenantRecorder, locale: Locale) -> str:
    """The switch's values as the recorder will use them, each marked
    declared or default, as `digline record status` marks them."""
    declared = set(status.declared)
    parts: list[str] = []
    for key, value in (
        ("sample", status.sample),
        ("redact", status.redact),
        ("ceiling", status.ceiling),
        ("interval", status.interval),
    ):
        mark = "declared" if key in declared else "default"
        parts.append(
            f"<code>{escape(key)} {escape(str(value))}</code> "
            f'<span class="note">{escape(phrase(locale, f"view.recorder.{mark}"))}'
            "</span>"
        )
    if "production" in declared:
        parts.append("<code>production</code>")
    return " · ".join(parts)


def _suites(status: TenantRecorder, locale: Locale) -> str:
    if not status.suites:
        return _p(phrase(locale, "view.recorder.no_suite"), "empty")
    numbers = ("calls", "inside", "orphans", "episodes", "interrupted")
    head = (
        f"<th>{escape(phrase(locale, 'view.recorder.column.suite'))}</th>"
        + "".join(
            f'<th class="num">'
            f"{escape(phrase(locale, f'view.recorder.column.{name}'))}</th>"
            for name in numbers
        )
        + f"<th>{escape(phrase(locale, 'view.recorder.column.not_recorded'))}</th>"
        + f"<th>{escape(phrase(locale, 'view.recorder.column.since'))}</th>"
    )
    rows: list[str] = []
    for entry in status.suites:
        if entry.imported is None or entry.since_last_import is None:
            since = phrase(locale, "view.recorder.not_read")
        elif entry.imported:
            since = str(entry.since_last_import)
        else:
            since = phrase(locale, "view.recorder.never", count=entry.since_last_import)
        missed = ", ".join(f"{why} {n}" for why, n in entry.not_recorded.items())
        values = (
            entry.calls,
            entry.inside_episodes,
            entry.orphans,
            entry.episodes,
            entry.interrupted,
        )
        rows.append(
            f"<tr><td><code>{escape(entry.suite)}</code></td>"
            + "".join(f'<td class="num">{value}</td>' for value in values)
            + f"<td>{escape(missed)}</td><td>{escape(since)}</td></tr>"
        )
    return (
        f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(rows)}</tbody></table>\n"
    )
