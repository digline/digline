"""This repository's own release tags, when the checkout has them.

Eleven tests check a released digline against what this tree writes, and they
read that release from its tag: ten build an old reader from `git archive
<tag> src`, and one reads `SCHEMA_VERSION` out of every release in
`test_example_caps.RELEASED`. `actions/checkout` fetches one commit and no tags,
so on the `gates` job every one of them skips, and a skip at the bottom of a
green run is a silence, not a green.

So they share one way of declining, the one `_site.py` gives the nav gates: a
skip that says what went unverified, and a failure where the tags are certainly
fetched. `ci.yml`'s `readers` job fetches every `v0.*` tag and sets
`TAGS_REQUIRED`, and `test_releasing.py` holds that job's list to every test
that calls this module.
"""

from __future__ import annotations

import io
import os
import subprocess
import tarfile
from collections.abc import Sequence
from pathlib import Path
from typing import NoReturn

import pytest

__all__ = ["TAGS_REQUIRED", "archived_source", "tags_absent"]

ROOT = Path(__file__).resolve().parents[1]

#: Where a skip would be a **silence** rather than an absence, and is therefore
#: an error: set it wherever the tags are guaranteed to have been fetched.
#: `ci.yml`'s `readers` job fetches them and sets it. Unset everywhere else, so
#: a shallow clone is never blocked by it.
TAGS_REQUIRED = "DIGLINE_TAGS_REQUIRED"


def tags_absent(tags: Sequence[str]) -> NoReturn:
    """Decline a check because `tags` are not in this checkout, loudly where
    declining is not allowed.

    Every tag is named, not only the first: a fetch that brought some of them
    is fixed by learning which ones it missed, and a message that stopped at
    one would send the reader round once per tag.
    """
    listed = ", ".join(tags)
    if os.environ.get(TAGS_REQUIRED):
        pytest.fail(
            f"{TAGS_REQUIRED} is set, so this check may not skip — and "
            f"{len(tags)} tag(s) are not in this checkout: {listed}. Where that "
            "variable is set the tags are fetched beside the commit, so this is "
            "the wiring having broken rather than a shallow clone."
        )
    more = f" and {len(tags) - 1} more" if len(tags) > 1 else ""
    pytest.skip(
        f"{tags[0]}{more} {'are' if more else 'is'} not in this checkout "
        f"(shallow clone, no tags). Skipped, not passed: fetch the tags, or see "
        f"ci.yml's `readers` job, which sets {TAGS_REQUIRED} and where this skip "
        "is an error instead."
    )


def archived_source(tag: str, into: Path) -> Path:
    """`src/` as `tag` holds it, extracted under `into`; the directory to put on
    `PYTHONPATH` so the old reader, and not this checkout's install, runs."""
    archive = subprocess.run(  # noqa: S603
        ["git", "archive", tag, "src"],  # noqa: S607
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    if archive.returncode != 0:
        tags_absent([tag])
    with tarfile.open(fileobj=io.BytesIO(archive.stdout)) as tar:
        tar.extractall(into, filter="data")
    return into / "src"
