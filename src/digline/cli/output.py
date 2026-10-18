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

**Standard output carries digline alone.** What the suite, the application it
imports, a target or a judge prints is assigned to standard error, the
perimeter of the person who ran the command (ADR 0043 §8, amended 2026-10-18).
`own_stdout()` does it for the length of a command: it keeps digline a private
copy of the descriptor standard output was, and points descriptor 1 at standard
error, so whatever writes there, `print`, `os.write(1, ...)` or a child
process, lands on standard error. `say()` and `emit()` write to the copy. One
place, so no window the user's code runs in has to be remembered:
`tests/test_stdout_carries_digline_alone.py` holds each window, and
`tests/test_terminal_escapes.py` refuses `sys.stdout` in a front end outside
this file.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Generator
from contextlib import contextmanager
from typing import TextIO

__all__ = ["emit", "flush", "own_stdout", "say", "visible"]

from digline.core import json_visible
from digline.report import visible

#: digline's own standard output while `own_stdout()` holds it; `None` outside,
#: where it is `sys.stdout` as it always was.
_ours: TextIO | None = None


def _stdout() -> TextIO:
    return _ours if _ours is not None else sys.stdout


@contextmanager
def own_stdout(*, give_back: bool = True) -> Generator[None]:
    """Standard output for digline alone, for the length of the block.

    A private duplicate of descriptor 1 becomes digline's standard output, and
    descriptor 1 is pointed at standard error, so what the user's code writes
    there, at any level, reaches standard error. On the way out what it left in
    Python's buffer is flushed while descriptor 1 still points at standard
    error, digline's own output is flushed, and descriptor 1 is put back.

    **The flush before the redirection is not a precaution.** Python holds what
    is written to `sys.stdout` in a buffer and writes it to whatever descriptor
    1 is when it flushes: a byte held across the redirection lands on the other
    side of it. That is how two import lines reached the MCP server's protocol
    stream after the SDK pointed the descriptor back (ADR 0043 §8).

    Only when `sys.stdout` is descriptor 1. A caller that replaced it, pytest's
    capture among them, is left as it is: the descriptor is not the stream it
    reads.

    `give_back=False` is for the process's own entry, `main.entry()`: the
    descriptor is not put back, so what the user's code writes after the
    command, from a thread still running, an `atexit` handler or a `__del__`,
    still reaches standard error. Put back, it reached standard output after
    digline's own lines, where `key=$(digline run ...)` reads. A caller of
    `main()` inside its own process gets it back, or its own `print` would land
    on standard error for the rest of that process.
    """
    global _ours
    try:
        backed = sys.stdout.fileno() == 1
    except (AttributeError, OSError, ValueError):
        backed = False
    if not backed:
        yield
        return
    sys.stdout.flush()
    private = os.dup(1)
    ours = os.fdopen(
        private,
        "w",
        encoding=sys.stdout.encoding,
        errors=sys.stdout.errors,
        # Line-buffered where the original was, a terminal, so a line reaches
        # whoever is watching as it is said.
        buffering=1 if sys.stdout.line_buffering else -1,
    )
    os.dup2(2, 1)
    _ours = ours
    try:
        yield
    finally:
        sys.stdout.flush()
        ours.flush()
        if give_back:
            os.dup2(private, 1)
            _ours = None
            ours.close()


def say(text: str = "", *, err: bool = False) -> None:
    """Print one line to the terminal, with nothing in it that can rewrite it.

    `err=True` for the notes and warnings: stdout may be a pipeline reading a
    key or a JSON document, and a note that broke it would teach people to
    ignore notes.
    """
    print(visible(text), file=sys.stderr if err else _stdout())


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

    **Now a second belt rather than the only one.** `digline.wire` neutralises
    those two ranges in the *values* it renders, so a document arriving here
    holds none of them raw and this call changes nothing. It stays because the
    rule is the sink: an HTML document does not come through `wire`, and the next
    thing printed here may not either. (from the release delta-pass over 0.15.0)
    """
    safe = json_visible(document)
    print(safe, end="" if safe.endswith("\n") else "\n", file=_stdout())


def flush() -> None:
    """Write what digline has said so far, now: a caller reading a line, such
    as the port `digline view` bound, should not wait for a buffer."""
    _stdout().flush()
