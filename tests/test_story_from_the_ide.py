"""`docs/stories/from-the-ide-with-mcp.md`, held to what was run.

Every sentence of the story is a thing that was run, against a stand-in for
the provider, with a client of the `mcp` SDK in place of the IDE. Its
`console` blocks open with the command that printed them
(`tests/test_console_blocks.py`, which reads this page too).
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PAGE = REPO / "docs" / "stories" / "from-the-ide-with-mcp.md"
MARK = "> **Arrives with digline 1.1.**"


def test_the_story_carries_the_mark_under_its_title() -> None:
    """Until digline 1.1.0 and a `digline-mcp` with the thirteen tools are on
    PyPI, the story's commands need both from this repository, and the mark
    says so under the title. The cut takes it out (RELEASING.md, *Owed to the
    next version*)."""
    page = PAGE.read_text(encoding="utf-8")
    title, rest = page.split("\n", 1)
    assert title.startswith("# ")
    assert rest.lstrip("\n").startswith(MARK)
