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
    by_case,
    case_line,
    closing_lines,
    group_line,
    group_setup_line,
    input_line,
    setup_line,
    setups_said,
    status_setups_said,
)
from digline.host.proposal import Mark, ProposalFile, ProposedBlock
from digline.host.state import SuiteState
from digline.host.where import SuiteFound, record_lines
from digline.report import Locale, escape, phrase
from digline.report.pages import (
    answer_address,
    proposal_address,
    recorder_address,
    recordings_address,
    screen,
    setups_address,
    where_address,
)
from digline.report.render import excluded_fact
from digline.wire.record_compare import (
    SHORT,
    ComparedCase,
    ComparedSetup,
    RecordComparison,
)
from digline.wire.recorder import TenantRecorder
from digline.wire.where import (
    NO_SUITE_ARG,
    WHERE_DOCS,
    Where,
    docs_url,
    where_command,
)

__all__ = [
    "SHOWN_CHARS",
    "Field",
    "answer_page",
    "command_line",
    "import_fields",
    "proposal_page",
    "switch_fields",
    "recorder_page",
    "recordings_page",
    "setups_page",
    "state_page",
    "WHERE_DOCS",
    "where_command",
    "where_page",
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
    earlier = setups_said(found.by_setup)
    if earlier is not None:
        body.append(_p(earlier, "note"))
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
        body.append(_p(group_setup_line(group), "note"))
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
    columns = 7 if form else 6
    rows = ""
    # By case, as the command line lists them: a case answered more than once
    # under a row that says so, its answers below in the files' order, and
    # none marked as the one to choose. (ADR 0061, as noted 2026-11-12)
    for case, found_answers in by_case(answers):
        if len(found_answers) > 1:
            rows += (
                f'<tr class="case"><td colspan="{columns}">'
                f"{escape(case_line(case, found_answers))}</td></tr>"
            )
        rows += "".join(
            _answer_row(found, answer, order, locale, form=form)
            for answer in found_answers
        )
    return (
        f'<div class="fits"><table class="answers"><thead><tr>{head}</tr></thead>'
        f"<tbody>{rows}</tbody></table></div>\n"
    )


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
        _tag(setup, order, locale, "" if setup == answer.in_force else earlier)
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
            if value.children:
                # An episode's child setups, one per line: a digest and the
                # model it names.
                unrecorded = phrase(locale, "view.setups.unrecorded")
                lines = "".join(
                    f"<div><code>{escape(child.digest)}</code> · "
                    f"{escape(child.model or unrecorded)}</div>"
                    for child in value.children
                )
                cells.append(f"<td>{lines}</td>")
                continue
            # In quotes, never through JSON: a prompt shown with its quotes
            # escaped reads as code. A list of messages is its first one's
            # text, and how many there are.
            shown = f'"{value.preview}"' + ("…" if value.clipped else "")
            if value.message_count is not None:
                key_of_count = (
                    "view.setups.messages.one"
                    if value.message_count == 1
                    else "view.setups.messages.many"
                )
                said = phrase(locale, key_of_count, count=value.message_count)
            elif value.clipped:
                said = phrase(locale, "view.setups.chars", chars=value.chars)
            else:
                said = ""
            length = f'<div class="note">{escape(said)}</div>' if said else ""
            cells.append(f"<td><code>{escape(shown)}</code>{length}</td>")
        rows.append(f"<tr><td><code>{escape(key.key)}</code></td>{''.join(cells)}</tr>")
    heading = phrase(locale, "view.setups.keys", same=same)
    return (
        f"<h2>{escape(heading)}</h2>\n"
        '<div class="fits"><table class="keys">'
        "<thead><tr><th></th><th>A</th><th>B</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table></div>\n"
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
        if case.kind == "episode" and (setup.calls or setup.models):
            # The shape of the episode's steps beside its setup's name.
            tag += f'<div class="note">{escape(_shape(setup, locale))}</div>'
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


def _shape(setup: ComparedSetup, locale: Locale) -> str:
    """`episode_shape`, in the page's language."""
    unrecorded = phrase(locale, "view.setups.unrecorded")
    calls = " / ".join(str(n) for n in setup.calls) or unrecorded
    models = ", ".join(setup.models) or unrecorded
    return phrase(locale, "view.setups.episode", calls=calls, models=models)


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
    for entry in status.suites:
        if entry.from_gate:
            # A run's own calls, recorded while it was in progress and counted
            # in no column of the table, as `digline record status` says it.
            body.append(
                _p(
                    phrase(
                        locale,
                        "view.recorder.from_gate",
                        suite=entry.suite,
                        count=entry.from_gate,
                    ),
                    "note",
                )
            )
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


# --------------------------------------------------------------------------- #
# Where the project is
# --------------------------------------------------------------------------- #


def _docs_link(page: str, anchor: str) -> str:
    href = docs_url(page, anchor)
    return f'<a href="{escape(href)}">{escape(page)}</a>'


#: The page and anchor that say more about each language's lines: Python's
#: wrapper and the proxy are sections of `record.md`, Java and Node have pages
#: of their own.
LANGUAGE_DOCS: dict[str, tuple[str, str]] = {
    "Python": ("record.md", "wrapping-the-client"),
    "Java": ("record-java.md", ""),
    "Node": ("record-node.md", ""),
    "any other": ("record.md", "through-the-proxy-digline-record-proxy"),
}


def _languages(tenant: str, suite: str | None, locale: Locale) -> str:
    """Where recording starts, by language: one block per language, open on
    a click with no script, each with three lines from its page, with the
    page's tenant and suite in place of the documentation's example, and a
    link to the page that says the rest."""
    blocks = [f"<h2>{escape(phrase(locale, 'view.where.language'))}</h2>\n"]
    for language, page, lines in record_lines(tenant, suite):
        doc, anchor = LANGUAGE_DOCS[language]
        blocks.append(
            f"<details><summary>{escape(language)}</summary>\n"
            f'<pre class="snippet">{escape(chr(10).join(lines))}</pre>\n'
            + _p(phrase(locale, "view.where.lines", page=page), "note")
            + f"<p>{_docs_link(doc, anchor)}</p>\n"
            + "</details>\n"
        )
    return "".join(blocks)


def _shapes(found: Where, locale: Locale) -> str:
    rows = "".join(
        f"<li>{escape(shape.says())} · ×{count}</li>" for shape, count in found.shapes
    )
    return f"<h2>{escape(phrase(locale, 'view.where.shapes'))}</h2>\n<ul>{rows}</ul>\n"


def _suites_found(found: Where, suites: Sequence[SuiteFound], locale: Locale) -> str:
    """The suites the tenant's store holds, on a server started without one:
    each by its name and what is filed under it, and the command that serves
    it. The file that declares it is the person's, so the command names it as
    theirs to fill in."""
    rows = "".join(
        "<li>"
        + escape(
            phrase(
                locale,
                "view.where.suite_found",
                suite=item.name,
                recordings=item.recordings,
                runs=item.runs,
            )
        )
        + "</li>"
        for item in suites
    )
    command = shlex.join(["digline", "view", "--suite", NO_SUITE_ARG])
    return (
        f"<h2>{escape(phrase(locale, 'view.where.suites', tenant=found.tenant))}</h2>\n"
        f"<ul>{rows}</ul>\n"
        f'<pre class="snippet">{escape(command)}</pre>\n'
    )


def where_page(
    found: Where,
    *,
    suite: str | None,
    suite_arg: str | None,
    root: Sequence[str],
    locale: Locale,
    writes: Sequence[str] | None,
    suites: Sequence[SuiteFound] = (),
) -> str:
    """Where the project is: the state's sentence as the heading, two
    sentences under it, the command for the next step, and the page that
    says more. `writes` is the recorder page's: the flags `digline record on`
    carries on a server that writes, where the switch is offered as a button
    with its command under it, and `None` on one that does not.

    `suite` is `None` on a server started without `--suite`, where the page is
    the tenant's: its first sentence speaks of no suite, and the suites the
    store holds are listed, each to be served with its own file."""
    values = {
        "count": found.count,
        "suite": found.suite or suite or "",
        "tenant": found.tenant,
        "exit_code": found.exit_code,
        "last_import": found.last_import or phrase(locale, "view.where.never"),
    }
    heading = phrase(locale, f"view.where.{found.state}.title", **values)
    said = (
        "view.where.nothing_recorded.tenant"
        if found.state == "nothing_recorded" and suite is None
        else f"view.where.{found.state}.say"
    )
    body = [f"<h1>{escape(heading)}</h1>\n", _p(phrase(locale, said, **values))]
    if found.state == "nothing_recorded":
        body.append(_languages(found.tenant, suite, locale))
    if found.state == "no_suite_yet" and found.shapes:
        body.append(_shapes(found, locale))
    if found.state == "no_suite_yet" and found.proposal is not None:
        # The sentence says the proposal is there; the link opens it, read
        # only. (ADR 0063, the read-only view ruled 2026-11-09)
        written = phrase(
            locale, "view.where.no_suite_yet.proposal", proposal=found.proposal
        )
        address = proposal_address(found.tenant, found.suite or suite or "")
        body.append(
            f"<p>{escape(written)} "
            f'<a href="{escape(address)}?locale={locale}">'
            f"{escape(phrase(locale, 'view.where.proposal.open'))}</a></p>\n"
        )
    if found.state == "unassigned" and found.capture is not True:
        # The import refuses `--from _unassigned` for a suite that declares no
        # capture source: the declaration comes first, and the command after.
        body.append(
            f"<p>{escape(phrase(locale, 'view.where.unassigned.declare'))} "
            f"{_docs_link('declarative.md', 'capture')}</p>\n"
        )
    here = (
        None
        if suite is None
        else {
            "to_import": recordings_address(found.tenant, suite),
            "new_setup": setups_address(found.tenant, suite),
        }.get(found.state)
    )
    if here is not None:
        body.append(
            f'<p><a href="{escape(here)}?locale={locale}">'
            f"{escape(phrase(locale, 'view.where.open'))}</a></p>\n"
        )
    command = where_command(found, suite_arg, root)
    if found.state == "recording_off" and writes is not None:
        body.append(
            f"<h2>{escape(phrase(locale, 'view.where.command'))}</h2>\n"
            f'<form method="post" action="{escape(recorder_address(found.tenant))}"'
            ' class="writes">\n'
            f'<input type="hidden" name="locale" value="{locale}">\n'
            '<input type="hidden" name="action" value="on">\n'
            f'<div class="picker"><button type="submit">'
            f"{escape(phrase(locale, 'view.switch.on'))}</button></div>\n"
            + _command(["digline", "record", "on", *writes], [], locale)
            + "</form>\n"
        )
    elif command:
        body.append(
            f"<h2>{escape(phrase(locale, 'view.where.command'))}</h2>\n"
            f'<pre class="snippet">{escape(shlex.join(command))}</pre>\n'
        )
    if suite is None and suites:
        body.append(_suites_found(found, suites, locale))
    links = " · ".join(
        _docs_link(page, anchor) for page, anchor in WHERE_DOCS[found.state]
    )
    body.append(f"<p>{escape(phrase(locale, 'view.where.docs'))}: {links}</p>\n")
    if suite is None:
        title = phrase(locale, "view.title.where_tenant", tenant=found.tenant)
        label = phrase(locale, "view.where.tenant_label", tenant=found.tenant)
    else:
        title = phrase(locale, "view.title.where", suite=suite)
        label = suite
    return screen(title, "".join(body), locale=locale, suite=label, here="where")


# -- the state of a suite ------------------------------------------------------ #


def state_page(
    state: SuiteState,
    *,
    suite: str,
    suite_arg: str | None,
    root: Sequence[str],
    locale: Locale,
) -> str:
    """The state of a suite, whole, in the order of ADR 0066 §1: the cases
    and the checks each is asked, the reviewed answers, the checks no case is
    asked, the newest run, the reference in force, the recordings waiting,
    and the next step. Each line renders a field of `SuiteState`, which reads
    it where its command does; nothing is worked out here. It reads, and
    takes no POST."""
    tenant = state.where.tenant
    body = [
        f"<h1>{escape(phrase(locale, 'view.state.heading', suite=suite))}</h1>\n",
        f"<h2>{escape(phrase(locale, 'view.state.cases'))}</h2>\n",
    ]
    if state.cases:
        body.append(
            _p(phrase(locale, "view.state.cases.count", count=len(state.cases)))
        )
        rows = "".join(
            f"<tr><td><code>{escape(item.case_id)}</code></td><td>"
            + (
                escape(", ".join(item.checks))
                if item.checks
                else escape(phrase(locale, "view.state.case.asked_nothing"))
            )
            + "</td></tr>\n"
            for item in state.cases
        )
        body.append(
            "<table><thead><tr>"
            + _head("view.state.column", ("case", "checks"), locale)
            + f"</tr></thead>\n<tbody>\n{rows}</tbody></table>\n"
        )
    else:
        body.append(_p(phrase(locale, "view.state.cases.none")))
    if state.idle_checks:
        body.append(
            _p(
                phrase(
                    locale,
                    "view.where.idle_checks",
                    checks=", ".join(state.idle_checks),
                ),
                "note",
            )
        )
    body.append(f"<h2>{escape(phrase(locale, 'view.state.reviewed'))}</h2>\n")
    body.append(
        _p(
            phrase(
                locale,
                "view.state.reviewed.count",
                good=state.reviewed.good,
                bad=state.reviewed.bad,
            )
        )
    )
    body.append(f"<h2>{escape(phrase(locale, 'view.state.newest'))}</h2>\n")
    if state.newest is None:
        body.append(_p(phrase(locale, "view.state.newest.none")))
    else:
        key, code = state.newest
        body.append(
            _p(phrase(locale, "view.state.newest.run", run=key, exit_code=code))
        )
    body.append(f"<h2>{escape(phrase(locale, 'view.state.reference'))}</h2>\n")
    if state.baseline_refused:
        body.append(_p(state.baseline_refused, "note"))
    elif state.baseline_key is None:
        body.append(_p(phrase(locale, "view.state.reference.none")))
    else:
        body.append(
            _p(
                phrase(
                    locale,
                    "view.state.reference.key",
                    reference=state.baseline_key,
                    at=state.promoted_at or phrase(locale, "view.state.unknown"),
                )
            )
        )
        excluded = excluded_fact(state.excluded, locale)
        if excluded:
            body.append(_p(excluded))
    body.append(f"<h2>{escape(phrase(locale, 'view.state.recordings'))}</h2>\n")
    body.append(_waiting(state, tenant, locale))
    body.append(f"<h2>{escape(phrase(locale, 'view.state.next'))}</h2>\n")
    values = {
        "count": state.where.count,
        "suite": suite,
        "tenant": tenant,
        "exit_code": state.where.exit_code,
        "last_import": state.where.last_import or phrase(locale, "view.where.never"),
    }
    body.append(_p(phrase(locale, f"view.where.{state.where.state}.title", **values)))
    command = where_command(state.where, suite_arg, root)
    if command:
        body.append(f'<pre class="snippet">{escape(shlex.join(command))}</pre>\n')
    body.append(
        f'<p><a href="{escape(where_address(tenant, suite))}?locale={locale}">'
        f"{escape(phrase(locale, 'view.state.where'))}</a></p>\n"
    )
    title = phrase(locale, "view.title.state", suite=suite)
    return screen(title, "".join(body), locale=locale, suite=suite, here="state")


def _waiting(state: SuiteState, tenant: str, locale: Locale) -> str:
    """The suite's recordings waiting, as `digline record status --suite`
    says them: how many came after the last import, and the line on the
    recordings under an earlier setup, in the sentence the import says."""
    entry = state.recordings
    if entry is None:
        return _p(phrase(locale, "view.state.recordings.none", tenant=tenant))
    if entry.since_last_import is None:
        lines = [_p(phrase(locale, "view.state.recordings.not_read"))]
    elif entry.imported:
        lines = [
            _p(
                phrase(
                    locale,
                    "view.state.recordings.since",
                    count=entry.since_last_import,
                )
            )
        ]
    else:
        lines = [
            _p(
                phrase(
                    locale,
                    "view.state.recordings.never",
                    count=entry.since_last_import,
                )
            )
        ]
    earlier = status_setups_said(entry)
    if earlier is not None:
        lines.append(_p(earlier))
    return "".join(lines)


# -- the proposal ------------------------------------------------------------- #


def _shown(value: object) -> str:
    """A value as the file writes it: a string quoted, a table and a list as
    JSON, a number and a boolean as they read."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return repr(value)
    return json.dumps(value, ensure_ascii=False)


#: The class each mark is drawn with, and the words it is said in.
_MARK_CLASS = {
    "placeholder": "placeholder",
    "assistant": "assisted",
    "draft": "assisted",
}


def _marked(mark: Mark | None, locale: Locale) -> str:
    if mark is None:
        return "<td></td>"
    words = phrase(locale, f"view.proposal.mark.{mark.kind}")
    return f'<td class="{_MARK_CLASS[mark.kind]}">{escape(words)}</td>'


def _proposed(number: int, block: ProposedBlock, locale: Locale) -> str:
    title = f"{number}. {block.type}" + (f" · {block.name}" if block.name else "")
    parts = [f"<h3>{escape(title)}</h3>\n"]
    if block.why:
        parts.append(_p(" ".join(line.strip() for line in block.why)))
    if block.said:
        said = " ".join(line.strip() for line in block.said)
        parts.append(
            f'<p class="note">{escape(phrase(locale, "view.proposal.said"))}: '
            f"{escape(said.removeprefix('the assistant: '))}</p>\n"
        )
    columns = "".join(
        f"<th>{escape(phrase(locale, f'view.proposal.{name}'))}</th>"
        for name in ("key", "value", "mark")
    )
    rows = "".join(
        f"<tr><td><code>{escape(param.key)}</code></td>"
        f"<td><code>{escape(_shown(param.value))}</code></td>"
        f"{_marked(param.mark, locale)}</tr>"
        for param in block.params
    )
    parts.append(
        f"<table><thead><tr>{columns}</tr></thead><tbody>{rows}</tbody></table>\n"
    )
    return "".join(parts)


def proposal_page(
    found: ProposalFile | None,
    *,
    suite: str,
    places: Sequence[str],
    lines: tuple[Sequence[str], Sequence[str]],
    shown_path: str | None,
    invalid: str | None,
    locale: Locale,
) -> str:
    """The proposal `digline suggest` wrote for `suite`, as the file holds it,
    read only: what it declares, each check in the file's order with why it
    is there and how each value is marked, the counterexample and the
    calibration skeleton, then the command that writes one, without and with
    `--model`, shown and never run. Nothing is ranked or chosen (ADR 0037 §6),
    and no recording is read: the page is the file's text alone. With no file,
    where it looked; with a file it could not read, why.
    (ADR 0063, the read-only view ruled 2026-11-09)"""
    body = [
        f"<h1>{escape(phrase(locale, 'view.proposal.heading', suite=suite))}</h1>\n",
        _p(phrase(locale, "view.proposal.lead"), "note"),
    ]
    if found is None and invalid is None:
        body.append(_p(phrase(locale, "view.proposal.none", suite=suite)))
        body.append(
            "<ul>"
            + "".join(f"<li><code>{escape(place)}</code></li>" for place in places)
            + "</ul>\n"
        )
    if invalid is not None:
        body.append(_p(phrase(locale, "view.proposal.invalid", error=invalid)))
    if found is not None:
        body.append(
            f"<h2>{escape(phrase(locale, 'view.proposal.file'))}</h2>\n"
            f"<p><code>{escape(shown_path or str(found.path))}</code></p>\n"
        )
        if found.header:
            body.append(_p(" ".join(found.header), "note"))
        body.append(f"<h2>{escape(phrase(locale, 'view.proposal.declaration'))}</h2>\n")
        for table, values in found.declaration.items():
            rows = "".join(
                f"<tr><td><code>{escape(key)}</code></td>"
                f"<td><code>{escape(_shown(value))}</code></td></tr>"
                for key, value in values.items()
            )
            body.append(
                f"<h3><code>[{escape(table)}]</code></h3>\n"
                f"<table><tbody>{rows}</tbody></table>\n"
            )
        if found.notes:
            body.append(
                f"<h3>{escape(phrase(locale, 'view.proposal.notes'))}</h3>\n"
                f'<pre class="snippet">{escape(chr(10).join(found.notes))}</pre>\n'
            )
        body.append(f"<h2>{escape(phrase(locale, 'view.proposal.checks'))}</h2>\n")
        body.extend(
            _proposed(number, block, locale)
            for number, block in enumerate(found.checks, start=1)
        )
        for key, text in (
            ("counterexample", found.counterexample),
            ("calibration", found.calibration),
        ):
            if text is not None:
                body.append(
                    f"<h2>{escape(phrase(locale, f'view.proposal.{key}'))}</h2>\n"
                    f'<pre class="snippet">{escape(text)}</pre>\n'
                )
        if found.unread:
            body.append(
                f"<h2>{escape(phrase(locale, 'view.proposal.unread'))}</h2>\n"
                f'<pre class="snippet">{escape(chr(10).join(found.unread))}</pre>\n'
            )
    plain, with_model = lines
    body.append(
        f"<h2>{escape(phrase(locale, 'view.where.command'))}</h2>\n"
        + _p(phrase(locale, "view.proposal.commands"))
        + f'<pre class="snippet">{escape(shlex.join(plain))}</pre>\n'
        + f'<pre class="snippet">{escape(shlex.join(with_model))}</pre>\n'
    )
    if found is not None or invalid is not None:
        body.append(
            _p(
                phrase(
                    locale,
                    "view.proposal.overwrite",
                    path=shown_path or (str(found.path) if found else ""),
                ),
                "note",
            )
        )
    return screen(
        phrase(locale, "view.title.proposal", suite=suite),
        "".join(body),
        locale=locale,
        suite=suite,
        here="proposal",
    )
