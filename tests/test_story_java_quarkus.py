"""`docs/walkthroughs/java-quarkus-bedrock.md`, held to what was run.

Every sentence of the story is a thing that was run, and its Java blocks are
held the way `docs/record-java.md`'s are (`tests/test_recorder_java.py`):
each, in order, is one of `StoryTest`'s, between a `// page:` line and an
`// end` line, which the Java tests compile and run against a fake Bedrock.
Its `console` blocks open with the command that printed them
(`tests/test_console_blocks.py`, which reads this page too).
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PAGE = REPO / "docs" / "walkthroughs" / "java-quarkus-bedrock.md"
STORY_TEST = REPO / "recorders/java/src/test/java/dev/digline/StoryTest.java"
MARK = "> **Arrives with digline 1.1.**"


def _lines(block: str) -> list[str]:
    return [line.strip() for line in block.strip("\n").splitlines()]


def test_every_java_block_on_the_story_is_one_the_java_tests_run() -> None:
    page = re.findall(r"```java\n(.*?)```", PAGE.read_text(encoding="utf-8"), re.S)
    run = re.findall(
        r"// page:\n(.*?)\n[ ]*// end", STORY_TEST.read_text(encoding="utf-8"), re.S
    )
    assert page, "the story has no Java block"
    assert [_lines(block) for block in page] == [_lines(block) for block in run]


def test_the_story_carries_the_mark_under_its_title() -> None:
    """Until 1.1.0 is on PyPI the story's commands need digline from this
    repository, and the mark says so under the title. The cut takes it out
    (RELEASING.md, *Owed to the next version*)."""
    page = PAGE.read_text(encoding="utf-8")
    title, rest = page.split("\n", 1)
    assert title.startswith("# ")
    assert rest.lstrip("\n").startswith(MARK)
