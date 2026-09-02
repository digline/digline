"""The other repository, when it is on this machine.

digline.dev renders pages out of this repository — `docs/`, the changelog, the
roadmap, one page per example README, one per decision record — and it builds
`--strict`. A page in its docs tree with no line in its `nav` is a warning, and
a warning is a failed build, which runs *after* PyPI in `publish.yml`.

So the gates that read that config live here rather than in a test module:
`_helpers.py` sets the rule that everything shared is a plain module and no test
module imports another, and two test files now need this.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

__all__ = ["SITE_CONFIG_CANDIDATES", "nav_lists", "require_site_config", "site_config"]

ROOT = Path(__file__).resolve().parents[1]

#: Where the site's config is looked for, in order. `DIGLINE_SITE_CONFIG` is
#: what CI sets; the sibling checkout is what a developer has when they work on
#: both, and mirrors `sync-docs.sh`'s own default of `../digline`.
SITE_CONFIG_CANDIDATES = ("../digline.dev/mkdocs.yml", "_site/mkdocs.yml")


def site_config() -> Path | None:
    """The site's `mkdocs.yml`, if this machine has it.

    Never fetched. This repository makes no network call the user did not ask
    for, and a test is not where that rule gets an exception — so the check runs
    where the file is already on disk, which is the `docs` job in `ci.yml`, and
    skips politely everywhere else.
    """
    if (given := os.environ.get("DIGLINE_SITE_CONFIG")) is not None:
        return Path(given)
    for candidate in SITE_CONFIG_CANDIDATES:
        if (path := ROOT / candidate).is_file():
            return path
    return None


def require_site_config() -> Path:
    """`site_config()`, or skip the test with the one sentence that says how."""
    config = site_config()
    if config is None:
        pytest.skip(
            "the site config is not on this machine. Set DIGLINE_SITE_CONFIG, "
            "or clone digline/digline.dev beside this repository; ci.yml's "
            "`docs` job does the second"
        )
    return config


def nav_lists(nav: str, page: str) -> bool:
    """Whether `nav` carries a line ending in `page`.

    Read with a regex rather than a YAML parser, like `test_releasing.py` reads
    the workflow: this repository has one runtime dependency and a test is not
    where a second one arrives. Anchored at the end of the line because the text
    before it is a label somebody chose, and this has no opinion about it.
    """
    return re.search(rf"{re.escape(page)}\s*$", nav, re.M) is not None
