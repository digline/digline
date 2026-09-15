"""What reaches a terminal, and what a terminal is allowed to be told.

A stored document is **not trusted text**. `.digline/<tenant>/baselines/` is
committed and reviewed in a pull request, which is exactly where a string that
can rewrite the screen does its work: `\x1b[2K\r` erases the line being printed
and lets the next characters read as digline's own output — *"digline: Nothing
got worse."* — while the exit code, which is the contract, says otherwise.

So every sentence the CLI prints goes through `say()`, which shows every control
character in it as text rather than obeying it. The escaping itself is
`report.visible()` — it lives there because `pytest-digline` needs the same rule
and a front end may not import another front end. The rule is the sink and
not the field: a per-field fix would have to be remembered by whoever adds the
next field, and the last one — `digline_version` — was added by somebody who had
just written the sanitising rule for a different surface.

Two things deliberately do **not** go through it, and `emit()` is what says so
out loud rather than leaving a bare `print` to be mistaken for an oversight:

- **`--json`**, because a program parses it and `visible()` would corrupt it.
  **`json.dumps` does not escape DEL or C1.** It writes C0 as `\\u00XX`, and
  under `ensure_ascii=False` — how every document here is built — it leaves
  DEL (U+007F) and the C1 block (U+0080–U+009F) raw, and U+009B on its own opens
  the same sequence ESC `[` does. So `emit()` escapes exactly those two ranges.
  Until the 0.13.0 delta-pass this docstring said `json.dumps` escapes
  *every* control character, and `log --json` printed a C1 CSI from a committed
  register;
- **the HTML report**, because it is a document rather than a sentence: its
  values are HTML-escaped where they are rendered, and `report.escape()` writes
  C0, DEL and C1 as character references, so it reaches `emit()` with none of
  them raw.

**The standing rule.** Every source of third-party text reaches a terminal
through this module — `say()` for a sentence, `emit()` for a document — **by
construction, not by memory**. It is enforced in one place:
`tests/test_terminal_escapes.py::test_nothing_in_the_cli_prints_except_through_say_or_emit`,
which refuses a `print` or a stream write anywhere in `digline.cli` outside this
file. A new command, a new field or a new committed file is sanitised because
it cannot reach a terminal any other way. The family has bitten three times,
each at a door the rule was not yet written on: `say()` first, then the HTML
`emit()`, then the JSON one.
"""

from __future__ import annotations

import sys

__all__ = ["emit", "say", "visible"]

from digline.report import visible

#: DEL and C1 as JSON `\\u00XX` escapes — the two ranges `json.dumps` leaves raw.
#: C0 is not here because `json.dumps` has already escaped it.
_UNESCAPED_BY_JSON = {code: f"\\u{code:04x}" for code in (0x7F, *range(0x80, 0xA0))}


def say(text: str = "", *, err: bool = False) -> None:
    """Print one line to the terminal, with nothing in it that can rewrite it.

    `err=True` for the notes and warnings: stdout may be a pipeline reading a
    key or a JSON document, and a note that broke it would teach people to
    ignore notes.
    """
    print(visible(text), file=sys.stderr if err else sys.stdout)


def emit(document: str) -> None:
    """Print a **document** — JSON or HTML — with DEL and C1 escaped.

    Separate from `say()` so that bypassing its sanitiser is a decision with a
    name on it; anything else that reaches a terminal is a sentence and uses
    `say()`. What `emit()` does instead changes nothing a reader parses: outside
    a string literal JSON is ASCII, so a raw DEL or C1 can only be inside one,
    where `\\u009b` is the same value; and an HTML document arrives with none of
    them raw, because `report.escape()` already wrote them as references. At the
    sink, so every `--json` command inherits it — including the next one.
    (from the 0.13.0 delta-pass)
    """
    safe = document.translate(_UNESCAPED_BY_JSON)
    print(safe, end="" if safe.endswith("\n") else "\n")
