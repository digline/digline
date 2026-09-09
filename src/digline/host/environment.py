"""The clock and git.

**This is the only layer allowed to touch either.** The core takes `created_at`
as an argument and `git_commit` as data precisely so that a run stays
reproducible and every layer below stays testable without freezing time or
building a repository. Everything that reads the outside world lives here, in
one file, where it can be seen.
"""

from __future__ import annotations

import subprocess
from datetime import UTC, datetime
from pathlib import Path

__all__ = ["DIRTY_SUFFIX", "git_commit", "utc_now_iso"]

DIRTY_SUFFIX = "-dirty"


def utc_now_iso() -> str:
    """The clock, read once per command and passed down as a value.

    Microseconds are kept. They were truncated at first, for readability, until
    listing runs showed what that costs: a run's key is derived from its
    timestamp and its configuration, so two runs in the same second with the
    same suite produced the same key and the second silently replaced the first.
    A fast suite against a stubbed target does that on an ordinary Tuesday.

    A collision now needs two runs in the same microsecond, which takes a real
    coincidence rather than a normal one.
    """
    return datetime.now(UTC).isoformat()


def _git(root: Path, *args: str) -> str | None:
    try:
        done = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None  # git is not installed; not an error, just no commit
    return done.stdout.strip() if done.returncode == 0 else None


def git_commit(root: Path) -> str | None:
    """The commit this run was produced from, or `None` outside a repository.

    Being outside a repository is not an error: a run produced from a notebook
    or a container legitimately has no commit, and refusing to work there would
    make the tool unusable exactly where people try things first.

    A dirty tree yields `"<sha>-dirty"`. The run is recorded, but the marker
    travels with it, because such a run **cannot be reproduced from the
    repository** — and a reader deciding whether to act on the numbers needs to
    know that as a fact rather than as an assumption.
    """
    sha = _git(root, "rev-parse", "HEAD")
    if sha is None:
        return None
    status = _git(root, "status", "--porcelain")
    return f"{sha}{DIRTY_SUFFIX}" if status else sha
