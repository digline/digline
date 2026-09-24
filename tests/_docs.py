"""Executing a document.

A page of documentation is a script with prose around it. These helpers read it
back as one: every fenced block is either a file to write, a snippet to
evaluate, or a terminal session to replay — and a document whose output was
typed by hand fails, which is the only way a printed number stays true.

The conventions are visible in the rendered page, not hidden in an attribute:

- a ```python block whose **first line is `# name.py`** is a file, written into
  the working directory under that name (the reading lives in
  `tools/doc_fences.py`, shared with the script that captures the site's home);
- any other ```python block is a **snippet**, evaluated against a namespace that
  already holds the public API;
- a ```console block is a **session**: `$ ` lines are commands, run in that same
  working directory in document order, and the lines beneath each one must come
  back out of it.

Run keys, and the instant a run was created, are the things that legitimately
differ between two executions, so they are compared by **identity** rather than
by value — and only they. The first time a key on the page meets a key the
command printed, the two are bound for the rest of the page: the same key on the
page must be the same run every time it appears, and two different keys on the
page must be two different runs. A key copied from one output onto another
fails that way.

What identity cannot catch, because the value itself is never compared: a key
that appears once, or one renamed consistently everywhere it appears. And a
quoted line binds to the **first** printed line of its shape, so a page that
skips rows of a listing binds its keys to the wrong runs and fails later —
quote a listing from its top.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

from doc_fences import BLOCK_RE, FILENAME_RE, blocks, python_files

__all__ = [
    "KEY_RE",
    "Bindings",
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

#: `2026-08-26T15:44:09.282929+00:00` — the same instant the key is slugged
#: from, as `digline list` prints it in its CREATED column. Only the full form a
#: run carries, so a date a page states on purpose is still compared.
INSTANT_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}\+00:00")


#: Either of the two, in the order they occur on a line.
TOKEN_RE = re.compile(f"{KEY_RE.pattern}|{INSTANT_RE.pattern}")


def normalise(line: str) -> str:
    """The line with every key and instant blanked: its *shape*, which must be
    equal for two lines to match before their tokens are compared."""
    return INSTANT_RE.sub("<INSTANT>", KEY_RE.sub("<KEY>", line)).rstrip()


class Bindings:
    """Which printed token each token on the page stands for, one to one.

    Keys and instants share the table and never collide, being spelt
    differently; a run's key and its CREATED instant are bound each on its own.
    """

    def __init__(self) -> None:
        self.page_to_run: dict[str, str] = {}
        self.run_to_page: dict[str, str] = {}
        self.order: dict[str, int] = {}

    def match(self, expected: str, actual: str) -> bool:
        """Whether `actual` is `expected`, binding any token seen for the first time.

        Nothing is bound unless the whole line matches, so a line that fails
        leaves the bindings as they were for the next candidate.
        """
        if normalise(expected) != normalise(actual):
            return False
        pending: dict[str, str] = {}
        taken: dict[str, str] = {}
        pairs = zip(TOKEN_RE.findall(expected), TOKEN_RE.findall(actual), strict=True)
        for page, run in pairs:
            bound = self.page_to_run.get(page, pending.get(page))
            if bound is not None:
                if bound != run:
                    return False
                continue
            owner = self.run_to_page.get(run, taken.get(run))
            if owner is not None and owner != page:
                return False
            pending[page] = run
            taken[run] = page
        for page, run in pending.items():
            self.page_to_run[page] = run
            self.run_to_page[run] = page
        return True

    def command(self, command: str) -> str:
        """`command` with each key the page wrote replaced by the key it stands
        for in this execution.

        A page may name a key in a command only once the page has *printed* it:
        that is how a reader gets one — `compare` prints the key of the baseline
        it compared against, and `promote --replacing` names it back (ADR 0031
        §2). A key the page never printed is a key no reader could have copied,
        so it is refused rather than run.
        """

        def bound(found: re.Match[str]) -> str:
            page = found.group(0)
            run = self.page_to_run.get(page)
            assert run is not None, (
                f"`{command}` names {page}, which the page has not printed yet: "
                "a reader could not have copied it from anywhere"
            )
            return run

        return KEY_RE.sub(bound, command)

    def seen(self, line: str) -> None:
        """Number every token of a page line by first appearance on the page."""
        for token in TOKEN_RE.findall(line):
            self.order.setdefault(token, len(self.order) + 1)

    def label(self, line: str) -> str:
        """`line` with each token named by the order the page first used it:
        `<KEY 3>` is the third distinct token on the page, wherever it appears,
        so the same key reads the same in every error about it."""

        def name(found: re.Match[str]) -> str:
            token = found.group(0)
            kind = "KEY" if KEY_RE.fullmatch(token) else "INSTANT"
            return f"<{kind} {self.order[token]}>"

        return TOKEN_RE.sub(name, line).rstrip()


def python_snippets(text: str) -> list[str]:
    """The blocks that are not files: fragments the reader is meant to copy."""
    return [
        body
        for body in blocks(text, "python")
        if FILENAME_RE.match(body.partition("\n")[0]) is None
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
            sessions[-1].expected.append(line.rstrip())
    return sessions


def console_sessions(text: str) -> list[Session]:
    return [s for body in blocks(text, "console") for s in _sessions_in(body)]


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


def _subsequence(
    expected: list[str], actual: list[str], bindings: Bindings
) -> str | None:
    """`None` if every expected line appears, in order, among the actual ones.

    In order rather than merely present: two lines swapped is a page that
    describes a different execution from the one that happened. Gaps are
    allowed, so a page may quote the three lines that matter out of thirty —
    but a gap never excuses a key: every key quoted is bound to the run it
    stood beside, for the rest of the page.
    """
    remaining = list(actual)
    for line in expected:
        while remaining and not bindings.match(line, remaining[0]):
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
    # One set of bindings for the whole page, not per chapter: chapter 6 names
    # the run chapter 5 promoted, and it has to be that run.
    bindings = Bindings()
    for lang, body in BLOCK_RE.findall(text):
        if lang == "python":
            first, _, _rest = body.partition("\n")
            if (match := FILENAME_RE.match(first)) is not None:
                (workdir / match.group(1)).write_text(body, encoding="utf-8")
        elif lang == "console":
            for session in _sessions_in(body):
                sessions.append(session)
                _check(session, workdir, bindings)
    return sessions


def _check(session: Session, workdir: Path, bindings: Bindings) -> None:
    done = run_command(bindings.command(session.command), workdir)
    actual = [
        line.rstrip()
        for line in (done.stdout + done.stderr).splitlines()
        if line.strip()
    ]
    for line in session.expected:
        bindings.seen(line)
    missing = _subsequence([e for e in session.expected if e], actual, bindings)
    assert missing is None, (
        f"`{session.command}` never printed {bindings.label(missing)!r}\n"
        f"--- it printed ---\n" + "\n".join(map(normalise, actual))
    )
