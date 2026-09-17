"""`docs/selection.md`, executed.

The page is a recipe a reader copies, so a file on it that does not run, or an
output typed by hand, is a recipe that fails on the reader's machine first.
Replayed the way the guide is: every file written, every command run, every
printed line checked.
"""

from __future__ import annotations

import re
from pathlib import Path

from tests._docs import console_sessions, python_files, python_snippets, replay

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "docs" / "selection.md"
TEXT = PAGE.read_text(encoding="utf-8")


def test_the_page_replays(tmp_path: Path) -> None:
    sessions = replay(TEXT, tmp_path)
    assert len(sessions) == 4, len(sessions)


def test_every_code_block_is_a_file_the_page_runs() -> None:
    assert python_snippets(TEXT) == []
    files = python_files(TEXT)
    reachable = " ".join(session.command for session in console_sessions(TEXT))
    reachable += " " + " ".join(files.values())
    for name in files:
        assert Path(name).stem in reachable, f"{name} is shown but never used"


def test_the_bare_list_error_is_the_one_the_core_gives() -> None:
    """The page quotes it; the core owns it."""
    from digline.core import EvaluatorInputs, JsonSchema

    verdict = JsonSchema(schema={"type": "object"})(
        EvaluatorInputs(output=["inv-204"])  # type: ignore[arg-type]
    )
    assert verdict.reason in TEXT, verdict.reason


def test_the_stated_line_count_is_the_file_on_the_page() -> None:
    """The count tells a copier the extra lines are rules, not decoration; a
    count that drifted from the file would be the page's first false sentence."""
    lines = len(python_files(TEXT)["selection.py"].splitlines())
    assert f"**The file is {lines} lines" in TEXT, lines


def test_the_silence_warning_comes_before_the_recipes() -> None:
    """The warning is the page's point; a reader who copies recipe 2 without
    reading down to it is the reader it exists for."""
    headings = re.findall(r"^## (.+)$", TEXT, re.MULTILINE)
    warning = headings.index("An empty selection passes `within`")
    assert warning < headings.index("Recipe 1: a fixed catalogue")


def test_every_relative_link_resolves() -> None:
    for target in re.findall(r"\]\(([^)]+)\)", TEXT):
        if target.startswith(("http://", "https://", "#")):
            continue
        assert (PAGE.parent / target.split("#", 1)[0]).exists(), target
