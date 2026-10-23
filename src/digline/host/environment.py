"""The clock and git.

**This is the only layer allowed to touch either.** The core takes `created_at`
as an argument and `git_commit` as data precisely so that a run stays
reproducible and every layer below stays testable without freezing time or
building a repository. Everything that reads the outside world lives here, in
one file, where it can be seen.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from digline.store.file_store import STORE_DIRNAME

__all__ = [
    "DIRTY_SUFFIX",
    "ProcessState",
    "git_commit",
    "process_state",
    "this_process",
    "unignored",
    "unignored_notes",
    "utc_now_iso",
]

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


#: What a journal's process is doing, as far as this process can tell.
ProcessState = Literal["running", "ended", "elsewhere", "unknown"]


def this_process() -> tuple[int, str]:
    """This process's id and this host's name, for a journal's header. (#478)"""
    return os.getpid(), socket.gethostname()


def process_state(pid: int | None, host: str) -> ProcessState:
    """Whether the process a journal recorded is still running.

    Only on this host, and only where a signal 0 can ask: `elsewhere` for a
    journal opened on another host, `unknown` for one that records no process or
    on a system that cannot ask. **`running` says a process with that id is
    running**, which is the digline that opened the leg unless the id was
    reused; the invitation says it that way. (#478)
    """
    if pid is None or not host or sys.platform == "win32":
        # On Windows `os.kill` with a signal it does not know ends the process.
        return "unknown"
    if host != socket.gethostname():
        return "elsewhere"
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return "ended"
    except PermissionError:
        return "running"  # it exists, and belongs to another user
    except OSError:
        return "unknown"
    return "running"


#: The rules the generated `.digline/.gitignore` writes, each with the
#: directory it keeps out of git. (#523)
_IGNORED = {"*/runs/": "runs", "*/name-table/": "name-table"}


def unignored(root: Path, tenant: str) -> tuple[str, ...]:
    """The rules of the generated `.gitignore` that git does not apply to this
    tenant's directories, in its order. Empty where git cannot answer.

    Git is asked, not the file read: `git check-ignore` applies every rule git
    reads, wherever and however it is written. Asked of a path under each
    directory, which need not exist. Exit 0 is ignored and 1 is not; anything
    else — no repository, no git — is no answer, and nothing is said. (#523)
    """
    missing: list[str] = []
    for rule, directory in _IGNORED.items():
        probe = f"{STORE_DIRNAME}/{tenant}/{directory}/__digline_probe__"
        try:
            done = subprocess.run(
                ["git", "-C", str(root), "check-ignore", "-q", probe],
                capture_output=True,
                check=False,
            )
        except OSError:
            return ()
        if done.returncode == 1:
            missing.append(rule)
        elif done.returncode != 0:
            return ()
    return tuple(missing)


def unignored_notes(tenant: str, missing: tuple[str, ...]) -> tuple[str, ...]:
    """One sentence for each rule `unignored` found missing. The same words on
    every front end that writes a run. (#523)"""
    said = {
        "*/runs/": (
            f"git does not ignore {STORE_DIRNAME}/{tenant}/runs/, so `git add` "
            "would commit run files, which are written unredacted, and the "
            "journals of runs in flight, which name the host they ran on. Add "
            f"`*/runs/` to {STORE_DIRNAME}/.gitignore"
        ),
        "*/name-table/": (
            f"git does not ignore {STORE_DIRNAME}/{tenant}/name-table/, so `git "
            "add` would commit the name table, the re-identification key, which "
            f"is never committed. Add `*/name-table/` to {STORE_DIRNAME}/.gitignore"
        ),
    }
    return tuple(said[rule] for rule in missing)
