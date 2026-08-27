"""Executing a document.

A page of documentation is a script with prose around it. These helpers read it
back as one: every fenced block is either a file to write, a snippet to
evaluate, or a terminal session to replay — and a document whose output was
typed by hand fails, which is the only way a printed number stays true.

The conventions are visible in the rendered page, not hidden in an attribute:

- a ```python block whose **first line is `# name.py`** is a file, written into
  the working directory under that name;
- any other ```python block is a **snippet**, evaluated against a namespace that
  already holds the public API;
- a ```console block is a **session**: `$ ` lines are commands, run in that same
  working directory in document order, and the lines beneath each one must come
  back out of it.

Run keys are the one thing that legitimately differs between two executions, so
they are normalised away — and only they.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

__all__ = [
    "KEY_RE",
    "Session",
    "console_sessions",
    "normalise",
    "python_files",
    "python_snippets",
    "replay",
    "run_command",
]

ROOT = Path(__file__).resolve().parents[1]

#: `2026-08-26T15-44-09-282929-00-00-e7421ec503ccefe8` — the slugged instant and
#: the config hash. It changes on every run and means nothing to the reader.
KEY_RE = re.compile(r"\d{4}-\d{2}-\d{2}T[\d-]+-[0-9a-f]{16}")

_BLOCK_RE = re.compile(r"```(\w+)\n(.*?)```", re.DOTALL)
_FILENAME_RE = re.compile(r"^# ([\w-]+\.py)\s*$")


def normalise(line: str) -> str:
    return KEY_RE.sub("<KEY>", line).rstrip()


def _blocks(text: str, language: str) -> list[str]:
    return [body for lang, body in _BLOCK_RE.findall(text) if lang == language]


def python_files(text: str) -> dict[str, str]:
    """Every block that is a file, by the name written on its first line.

    A name used twice is a later version of the same file — that is how a guide
    shows a suite growing. `replay` writes each version at the point the page
    introduces it, so both versions really run.
    """
    files: dict[str, str] = {}
    for body in _blocks(text, "python"):
        first, _, _rest = body.partition("\n")
        if (match := _FILENAME_RE.match(first)) is not None:
            files[match.group(1)] = body
    return files


def python_snippets(text: str) -> list[str]:
    """The blocks that are not files: fragments the reader is meant to copy."""
    return [
        body
        for body in _blocks(text, "python")
        if _FILENAME_RE.match(body.partition("\n")[0]) is None
    ]


class Session:
    """One `$ command` and the lines the page says it prints."""

    def __init__(self, command: str) -> None:
        self.command = command
        self.expected: list[str] = []

    def __repr__(self) -> str:  # pragma: no cover — pytest failure output only
        return f"Session({self.command!r})"


def _sessions_in(body: str) -> list[Session]:
    sessions: list[Session] = []
    for line in body.splitlines():
        if line.startswith("$ "):
            sessions.append(Session(line[2:].strip()))
        elif line.strip() and sessions:
            sessions[-1].expected.append(normalise(line))
    return sessions


def console_sessions(text: str) -> list[Session]:
    return [s for body in _blocks(text, "console") for s in _sessions_in(body)]


_SUBSTITUTION_RE = re.compile(r"\$\(([^)]+)\)")


def run_command(command: str, workdir: Path) -> subprocess.CompletedProcess[str]:
    """A command from a page, run for real.

    Only the two forms a page is allowed to show. Anything else is a documented
    command nobody can check, which is the thing this module exists to prevent.

    `$(...)` is honoured because a run key cannot be written on a page — it
    differs on every execution — so the only copyable way to name one is to
    compute it. The inner command runs first, exactly as a shell would run it.
    """
    while (found := _SUBSTITUTION_RE.search(command)) is not None:
        inner = run_command(found.group(1), workdir)
        assert inner.returncode == 0, f"`{found.group(1)}` failed: {inner.stderr}"
        command = (
            command[: found.start()] + inner.stdout.strip() + command[found.end() :]
        )
    parts = command.split()
    if parts[0] == "digline":
        argv = [sys.executable, "-m", "digline.cli", *parts[1:]]
    elif parts[0] == "python":
        argv = [sys.executable, *parts[1:]]
    else:
        raise AssertionError(f"a page may not show `{parts[0]}`: {command}")
    return subprocess.run(
        argv, cwd=workdir, capture_output=True, text=True, check=False
    )


def _subsequence(expected: list[str], actual: list[str]) -> str | None:
    """`None` if every expected line appears, in order, among the actual ones.

    In order rather than merely present: two lines swapped is a page that
    describes a different execution from the one that happened. Gaps are
    allowed, so a page may quote the three lines that matter out of thirty.
    """
    remaining = list(actual)
    for line in expected:
        while remaining and remaining[0] != line:
            remaining.pop(0)
        if not remaining:
            return line
        remaining.pop(0)
    return None


def replay(text: str, workdir: Path) -> list[Session]:
    """Walk the page top to bottom, writing files and running commands.

    Document order **is** execution order. A file is written at the point the
    page introduces it, so a later version of the same file only takes effect
    from there down — which is how a guide shows a suite growing without the
    last chapter quietly rewriting the first one. A page that promoted before it
    ran would be a page nobody can follow, and this is what catches it.
    """
    sessions: list[Session] = []
    for lang, body in _BLOCK_RE.findall(text):
        if lang == "python":
            first, _, _rest = body.partition("\n")
            if (match := _FILENAME_RE.match(first)) is not None:
                (workdir / match.group(1)).write_text(body, encoding="utf-8")
        elif lang == "console":
            for session in _sessions_in(body):
                sessions.append(session)
                _check(session, workdir)
    return sessions


def _check(session: Session, workdir: Path) -> None:
    done = run_command(session.command, workdir)
    actual = [
        normalise(line)
        for line in (done.stdout + done.stderr).splitlines()
        if line.strip()
    ]
    missing = _subsequence([e for e in session.expected if e], actual)
    assert missing is None, (
        f"`{session.command}` never printed {missing!r}\n"
        f"--- it printed ---\n" + "\n".join(actual)
    )
