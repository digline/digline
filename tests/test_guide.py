"""The guide, executed from the first line to the last.

Eight chapters that build on each other, so the page is replayed as one session
in one directory: the files are written where the page introduces them, the
commands run in the order the page gives them, and every printed line has to
come back out. A guide whose chapter 6 depends on chapter 4 having been followed
is a guide that has to be checked that way.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from tests._docs import console_sessions, python_files, python_snippets, replay

ROOT = Path(__file__).resolve().parents[1]
GUIDE = ROOT / "docs" / "guide.md"
TEXT = GUIDE.read_text(encoding="utf-8")


def test_the_guide_has_the_eight_chapters_in_order() -> None:
    """The order is the point: it is the order the problems arrive in."""
    chapters = re.findall(r"^## (\d)\. (.+)$", TEXT, re.MULTILINE)
    assert [number for number, _title in chapters] == list("12345678")


def anchor(heading: str) -> str:
    """The fragment GitHub gives a heading: lowercased, punctuation dropped,
    spaces hyphenated."""
    kept = "".join(c for c in heading.lower() if c.isalnum() or c in " -")
    return "#" + kept.replace(" ", "-")


def test_the_index_reaches_every_chapter_and_nothing_else() -> None:
    """An index whose links go nowhere is worse than no index: it is a promise
    the page makes and breaks in the one place a hurried reader looks first."""
    headings = re.findall(r"^## (\d\. .+)$", TEXT, re.MULTILINE)
    assert len(headings) == 8, headings

    index = TEXT.split("\n1. [", 1)[1].split("\n\nThree files", 1)[0]
    linked = re.findall(r"\]\((#[^)]+)\)", "1. [" + index)
    assert linked == [anchor(h) for h in headings]


def test_every_code_block_is_a_file_the_guide_runs() -> None:
    """No snippet nobody executes. A fragment on a page is a fragment that rots,
    so here every block is a whole file, and every file is either run or
    imported by one that is — `rules.py` is never a command, but changing it is
    half of chapters 4, 5 and 8."""
    assert python_snippets(TEXT) == []

    files = python_files(TEXT)
    reachable = " ".join(session.command for session in console_sessions(TEXT))
    reachable += " " + " ".join(files.values())
    for name in files:
        assert name in reachable, f"{name} is shown but neither run nor imported"


def test_the_guide_replays(tmp_path: Path) -> None:
    """Every file written, every command run, every line checked."""
    workdir = tmp_path / "guide"
    workdir.mkdir()
    sessions = replay(TEXT, workdir)
    assert len(sessions) >= 20, len(sessions)


@pytest.mark.parametrize(
    ("name", "must_contain"),
    [
        ("support.py", "tenant="),
        ("app.py", "def judge("),
        ("triage.py", "Precision("),
    ],
)
def test_the_guide_shows_the_files_it_talks_about(name: str, must_contain: str) -> None:
    assert must_contain in python_files(TEXT)[name]


def test_the_measured_evidence_is_the_measured_evidence() -> None:
    """`14, 14, 15, 15 of 21` is a real measurement, quoted in the core, in the
    report and in ADR 0002. If the guide ever drifts from it, one of them is
    wrong and it matters which."""
    assert "14, 14, 15, 15 cases out of 21" in TEXT
    source = (ROOT / "src" / "digline" / "core" / "aggregate.py").read_text(
        encoding="utf-8"
    )
    assert "14, 14, 15, 15 of 21" in source


def test_every_relative_link_resolves() -> None:
    for target in re.findall(r"\]\(([^)]+)\)", TEXT):
        if target.startswith(("http://", "https://", "#")):
            continue
        assert (GUIDE.parent / target.split("#", 1)[0]).exists(), target
