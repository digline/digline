"""`docs/walkthroughs/node.md`, held to what was run.

Every sentence of the story is a thing that was run, and its JavaScript
blocks are held the way `docs/record-node.md`'s are
(`tests/test_record_node_page.py`): each, in order, is one of
`recorders/node/test/story.test.mjs`'s, between a `// page:` line and an
`// end` line, which the CI job `recorder-node` runs against the stand-in the
story was run against. Its `console` blocks open with the command that
printed them (`tests/test_console_blocks.py`, which reads this page too).
"""

from __future__ import annotations

import re
from pathlib import Path

from tests.test_console_blocks import (
    _BLOCK,  # pyright: ignore[reportPrivateUsage]
    _pages,  # pyright: ignore[reportPrivateUsage]
)

REPO = Path(__file__).resolve().parents[1]
PAGE = REPO / "docs" / "walkthroughs" / "node.md"
STORY_TEST = REPO / "recorders" / "node" / "test" / "story.test.mjs"


def _lines(block: str) -> list[str]:
    return [line.strip() for line in block.strip("\n").splitlines()]


def test_every_javascript_block_on_the_story_is_one_the_node_tests_run() -> None:
    page = re.findall(r"```js\n(.*?)```", PAGE.read_text(encoding="utf-8"), re.S)
    run = re.findall(
        r"// page:\n(.*?)\n[ ]*// end", STORY_TEST.read_text(encoding="utf-8"), re.S
    )
    assert page, "the story has no JavaScript block"
    assert [_lines(block) for block in page] == [_lines(block) for block in run]


def _opening(page: str) -> tuple[str, str]:
    """The paragraph under the title, and what follows it."""
    title, rest = page.split("\n", 1)
    assert title.startswith("# ")
    lede, _, after = rest.lstrip("\n").partition("\n\n")
    return lede, after.lstrip("\n")


def test_the_page_opens_on_a_lede_of_one_sentence() -> None:
    """A paragraph under the title says what the page shows, in one sentence,
    so the site's opening band has a lede: on digline.dev,
    `tools/check-opening.py` declares a page without one by name. (The 1.1.0
    cut, ruled 2026-11-09.)"""
    lede, _ = _opening(PAGE.read_text(encoding="utf-8"))
    assert lede and not lede.startswith((">", "#", "-", "`")), lede
    assert lede.count(". ") == 0 and lede.endswith("."), lede


def test_the_page_carries_no_mark() -> None:
    """Its mark went at the cut of 1.1.0: what the page runs is on PyPI from
    that release on. (RELEASING.md, *Owed to the next version*)"""
    _, after = _opening(PAGE.read_text(encoding="utf-8"))
    assert after.startswith("## Who this is for"), after[:80]


def test_the_versions_the_story_says_are_the_ones_the_tests_install() -> None:
    """The story was run with the SDKs `recorders/node/package.json` pins, and
    its test runs with them: a Dependabot bump that moves them makes this red
    until the story is run again and says the new ones."""
    import json

    pinned = json.loads(
        (REPO / "recorders" / "node" / "package.json").read_text(encoding="utf-8")
    )["dependencies"]
    said = " ".join(PAGE.read_text(encoding="utf-8").split())
    for package in ("openai", "@anthropic-ai/sdk", "@aws-sdk/client-bedrock-runtime"):
        assert f"{package} {pinned[package]}" in said, package


def test_the_console_walk_reads_this_story() -> None:
    """The control for `tests/test_console_blocks.py` on this page: the walk
    reaches it, and finds console blocks in it to hold."""
    assert PAGE in _pages()
    assert _BLOCK.search(PAGE.read_text(encoding="utf-8"))
