"""Reading the files a page of documentation carries in its fences.

One reader, shared by the two things that run a page: `tests/_docs.py`, which
replays the guide on every build, and `tools/home_capture.py`, which runs its
first chapter to produce what the home of digline.dev shows. Two readers of the
same convention would drift, and the page would then mean one thing to the test
and another to the site.

The convention is visible in the rendered page: a ```python block whose **first
line is `# name.py`** is a file, written under that name.
"""

from __future__ import annotations

import re

__all__ = ["BLOCK_RE", "FILENAME_RE", "blocks", "python_files"]

BLOCK_RE = re.compile(r"```(\w+)\n(.*?)```", re.DOTALL)
FILENAME_RE = re.compile(r"^# ([\w-]+\.py)\s*$")


def blocks(text: str, language: str) -> list[str]:
    return [body for lang, body in BLOCK_RE.findall(text) if lang == language]


def python_files(text: str) -> dict[str, str]:
    """Every block that is a file, by the name written on its first line.

    A name used twice is a later version of the same file — that is how a guide
    shows a suite growing. The last version in `text` wins, so a caller that
    wants the files as a chapter has them passes the text up to that chapter.
    """
    files: dict[str, str] = {}
    for body in blocks(text, "python"):
        first, _, _rest = body.partition("\n")
        if (match := FILENAME_RE.match(first)) is not None:
            files[match.group(1)] = body
    return files
