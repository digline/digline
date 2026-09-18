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

__all__ = [
    "SITE_CONFIG_CANDIDATES",
    "SITE_REQUIRED",
    "nav_lists",
    "require_site_config",
    "site_config",
    "why_absent",
]

ROOT = Path(__file__).resolve().parents[1]

#: Where the site's config is looked for, in order. `DIGLINE_SITE_CONFIG` is
#: what CI sets; the sibling checkout is what a developer has when they work on
#: both, and mirrors `sync-docs.sh`'s own default of `../digline`.
SITE_CONFIG_CANDIDATES = ("../digline.dev/mkdocs.yml", "_site/mkdocs.yml")

#: Where a skip would be a **silence** rather than an absence, and is therefore
#: an error: set it wherever the site is guaranteed to be on disk. `ci.yml`'s
#: `docs` job clones digline.dev and sets it, which is the one place these
#: checks may not quietly decline to run. Unset everywhere else, so a developer
#: without the site beside them is never blocked by it.
SITE_REQUIRED = "DIGLINE_SITE_REQUIRED"


def site_config() -> Path | None:
    """The site's `mkdocs.yml`, if this machine has it.

    Never fetched. This repository makes no network call the user did not ask
    for, and a test is not where that rule gets an exception — so the checks
    built on this run only where the file is already on disk: a developer with
    both repositories side by side, or anywhere `DIGLINE_SITE_CONFIG` points at
    one. Everywhere else they skip, **CI included** — the `gates` job clones no
    site, and what catches the same defect there is the real `--strict` build in
    the `docs` job, which clones it itself. These are the fast local warning,
    not the authority.
    """
    if (given := os.environ.get("DIGLINE_SITE_CONFIG")) is not None:
        # A path that is set and is not a file is treated as absent rather than
        # returned, so the caller decides what an absence means. Returned, it
        # became a `FileNotFoundError` three frames later in whichever test read
        # it first — a crash that names neither the variable nor the typo in it.
        given_path = Path(given)
        return given_path if given_path.is_file() else None
    for candidate in SITE_CONFIG_CANDIDATES:
        if (path := ROOT / candidate).is_file():
            return path
    return None


def why_absent() -> str:
    """Why there is no site config, in the words the reader needs to act on.

    One sentence, and it names the *variable* when the variable is the problem:
    a `DIGLINE_SITE_CONFIG` pointing at a path that does not exist looks exactly
    like no site at all, and the difference is the whole of what somebody has to
    fix.
    """
    given = os.environ.get("DIGLINE_SITE_CONFIG")
    if given is not None:
        return f"DIGLINE_SITE_CONFIG is set to {given!r}, and there is no file there"
    return (
        "digline.dev is not on this machine: none of "
        f"{', '.join(SITE_CONFIG_CANDIDATES)} is a file, and "
        "DIGLINE_SITE_CONFIG is not set"
    )


def require_site_config() -> Path:
    """`site_config()`, or decline — loudly where declining is not allowed.

    **A skip is not a pass, and the difference has to be legible.** These checks
    sat at the bottom of a green run as `10 skipped`, which nobody reads: the
    nav line they exist for was verified by nothing, anywhere, and the run said
    so in a number. So the skip now states what went unverified rather than only
    how to fix it — and in the one place the site is certainly present,
    `SITE_REQUIRED` turns it into a failure, because there a skip could only
    mean the wiring broke.
    """
    config = site_config()
    if config is not None:
        return config
    absence = why_absent()
    if os.environ.get(SITE_REQUIRED):
        pytest.fail(
            f"{SITE_REQUIRED} is set, so this check may not skip — and it has "
            f"nothing to read: {absence}. Where that variable is set the site "
            "is cloned beside this repository, so this is the wiring having "
            "broken rather than a machine without the site on it."
        )
    pytest.skip(
        f"skipped, not passed: nothing here has checked that this page has a "
        f"line in digline.dev's nav, because {absence}. Clone "
        "digline/digline.dev beside this repository, or point "
        "DIGLINE_SITE_CONFIG at its mkdocs.yml; ci.yml's `docs` job does the "
        f"first and sets {SITE_REQUIRED}, where this skip is an error instead."
    )


def nav_lists(nav: str, page: str) -> bool:
    """Whether `nav` carries a line ending in `page`.

    Read with a regex rather than a YAML parser, like `test_releasing.py` reads
    the workflow: this repository has one runtime dependency and a test is not
    where a second one arrives. Anchored at the end of the line because the text
    before it is a label somebody chose, and this has no opinion about it.
    """
    return re.search(rf"{re.escape(page)}\s*$", nav, re.M) is not None
