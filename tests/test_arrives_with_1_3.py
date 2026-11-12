"""The pages that say *"Arrives with digline 1.3."*, held to their row owed to
the next version.

`--max-cost` and the cost estimate, the judgements a case gets and their
counts, and `DiglineAws`'s fix for Quarkus dev mode's reload are on `main` and
in no release. The pages that describe them say so under the paragraph, in the
form 1.1's marks took, and RELEASING.md's *Owed to the next version* keeps the
row by which the release takes the marks out. A mark with no row is one the
cut does not know to take out; a row naming a page with no mark is a debt
already paid. Either is a page cut halfway, as `tests/test_record_node_page.py`
held for 1.1.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MARK = "> **Arrives with digline 1.3.**"
#: Where RELEASING.md's table *Owed to the next version* opens and closes, as
#: `tests/test_plugin_floors.py` reads it.
NEXT_OPENS = "**And the number each package owes: read *Owed to the next version*.**"
NEXT_CLOSES = "Empty is the normal state here too."


def _marked() -> set[str]:
    return {
        str(page.relative_to(ROOT))
        for page in sorted((ROOT / "docs").rglob("*.md"))
        if MARK in page.read_text(encoding="utf-8")
    }


def _rows() -> list[str]:
    releasing = (ROOT / "RELEASING.md").read_text(encoding="utf-8")
    start = releasing.find(NEXT_OPENS)
    end = releasing.find(NEXT_CLOSES, start)
    assert 0 <= start < end, "RELEASING.md no longer has *Owed to the next version*"
    return [
        line
        for line in releasing[start:end].splitlines()
        if line.startswith("| `") and '*"Arrives with digline 1.3."*' in line
    ]


def test_the_walk_finds_the_marks() -> None:
    """The control: a mark written another way would pass the test below over
    nothing."""
    assert "docs/guide.md" in _marked()


def test_the_marks_and_their_row_go_together() -> None:
    marked = _marked()
    rows = _rows()
    assert bool(marked) == bool(rows), (sorted(marked), rows)
    if rows:
        [row] = rows
        named = set(re.findall(r"`(docs/[^`]+\.md)`", row))
        assert named == marked, (
            f"marked and not in the row: {sorted(marked - named)}; "
            f"in the row and not marked: {sorted(named - marked)}"
        )
