"""A `console` block on a documentation page says which command printed it.

A block fenced as `console` reads as a terminal, and a reader takes its lines
for what a command prints. Without the `$ ` line before them, the block does
not say which command, and nothing ties the lines to one: two of them showed
messages digline no longer prints in those words, and one of the two was
missing the `digline: ` its command writes before a refusal (#649).

The form is the one the pages already use, `docs/migrate.md`'s first block
among them: the command on a `$ ` line, then what it printed. The pages a test
replays (`tests/_docs.py`) are held to more than this; this holds every page
under `docs/` to this much.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

_BLOCK = re.compile(r"^```console\n(.*?)^```", re.S | re.M)

#: Blocks known to open with output, by page and the first line they show,
#: each with where it is owed. Not a list to grow: a block added without its
#: command is red, and this table is for the ones a decision left as they are.
WITHOUT_A_COMMAND: dict[tuple[str, str], str] = {
    (
        "docs/log.md",
        "Run-to-run spread",
    ): "#649, group 4: an excerpt of `digline log`, over a store built for the page",
}


def _blocks_without_a_command() -> list[tuple[str, int, str]]:
    found: list[tuple[str, int, str]] = []
    for page in sorted((ROOT / "docs").glob("*.md")):
        text = page.read_text(encoding="utf-8")
        for match in _BLOCK.finditer(text):
            first = match.group(1).split("\n", 1)[0]
            if not first.startswith("$ "):
                line = text[: match.start()].count("\n") + 1
                found.append((str(page.relative_to(ROOT)), line, first))
    return found


def test_every_console_block_opens_with_the_command_that_printed_it() -> None:
    unexplained = [
        f"{page}:{line}: {first!r}"
        for page, line, first in _blocks_without_a_command()
        if (page, first) not in WITHOUT_A_COMMAND
    ]
    assert not unexplained, (
        "a `console` block that shows output with no `$ ` line before it does "
        "not say which command printed it:\n  " + "\n  ".join(unexplained)
    )


def test_every_exception_is_still_a_block_without_a_command() -> None:
    """An exception whose block was given its command is a row to delete."""
    seen = {(page, first) for page, _, first in _blocks_without_a_command()}
    stale = [key for key in WITHOUT_A_COMMAND if key not in seen]
    assert not stale, stale


def test_the_walk_finds_console_blocks_at_all() -> None:
    """The control: a pattern that matched nothing would pass every page."""
    text = (ROOT / "docs" / "migrate.md").read_text(encoding="utf-8")
    assert _BLOCK.search(text)
