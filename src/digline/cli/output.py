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

- **`--json`**, because `json.dumps` already escapes every control character,
  and a second escaping would corrupt a document a program parses;
- **the HTML report**, because it is a document rather than a sentence: its
  values are already HTML-escaped where they are rendered, and stripping
  characters out of it here would change the artifact a reader keeps.
"""

from __future__ import annotations

import sys

__all__ = ["emit", "say", "visible"]

from digline.report import visible


def say(text: str = "", *, err: bool = False) -> None:
    """Print one line to the terminal, with nothing in it that can rewrite it.

    `err=True` for the notes and warnings: stdout may be a pipeline reading a
    key or a JSON document, and a note that broke it would teach people to
    ignore notes.
    """
    print(visible(text), file=sys.stderr if err else sys.stdout)


def emit(document: str) -> None:
    """Print a **document** — JSON or HTML — exactly as it was built.

    Separate from `say()` so that bypassing the sanitiser is a decision with a
    name on it. See this module's docstring for why these two are safe without
    it; anything else that reaches a terminal is a sentence and uses `say()`.
    """
    print(document, end="" if document.endswith("\n") else "\n")
