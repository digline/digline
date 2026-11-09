"""`docs/walkthroughs/python-three-prompts.md`, held to what was run.

Its Python blocks are held the way `docs/guide.md`'s are (`tests/test_guide.py`):
every block is a whole file, and every file is run or imported. Here they are
also run: walking the page in order, each file is written where the page shows
it, and the application's commands, `python traffic.py` and `python later.py`,
run against the stand-in the story ran against
(`tests/_story_python_stand_in.py`), with the recorder switched on by the
page's own `digline record on`. What each prints must be what the page says it
printed, and `digline record status` must count the calls of each suite as the
page does.

What this does not replay: `suggest`, `view`, `import`, `run`, `promote`,
`compare` and `pytest`. Their `console` blocks open with the command that
printed them (`tests/test_console_blocks.py`, which reads this page too), and
no more is held of them here.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from tests._docs import console_sessions, python_files, python_snippets
from tests._story_python_stand_in import serve

from doc_fences import BLOCK_RE, FILENAME_RE

REPO = Path(__file__).resolve().parents[1]
PAGE = REPO / "docs" / "walkthroughs" / "python-three-prompts.md"
TEXT = PAGE.read_text(encoding="utf-8")
MARK = "> **Arrives with the next pytest-digline.**"


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
    lede, _ = _opening(TEXT)
    assert lede and not lede.startswith((">", "#", "-", "`")), lede
    assert lede.count(". ") == 0 and lede.endswith("."), lede


def test_the_mark_follows_the_lede() -> None:
    """Until the next pytest-digline is on PyPI the page needs it from this
    repository, and the mark under the lede says so. That release's pull
    request takes it out (RELEASING.md, *Owed to the next version*)."""
    _, after = _opening(TEXT)
    assert after.startswith(MARK), after[:80]


def test_every_python_block_is_a_file_the_story_runs() -> None:
    """No snippet nobody executes: every block is a whole file, and each file
    is run by a command on the page or imported by a file that is."""
    assert python_snippets(TEXT) == []
    files = python_files(TEXT)
    assert set(files) == {"prompts.py", "hiring.py", "traffic.py", "later.py"}
    reachable = " ".join(session.command for session in console_sessions(TEXT))
    reachable += " " + " ".join(files.values())
    for name in files:
        assert name.removesuffix(".py") in reachable, f"{name}: not run or imported"


def _without_environment(command: str) -> str:
    """The command after the `NAME=value` words the page sets before it."""
    words = command.split()
    while words and "=" in words[0]:
        words.pop(0)
    return " ".join(words)


def test_the_story_records_what_it_says(tmp_path: Path) -> None:
    """The page's files, written in its order, against the stand-in: each
    `python` command prints what the page says, and each `record status`
    counts each suite's calls as the page does."""
    server = serve()
    env = {
        **os.environ,
        "ANTHROPIC_BASE_URL": f"http://127.0.0.1:{server.server_port}",
        "ANTHROPIC_API_KEY": "fake",
    }
    ran: list[str] = []
    try:
        for lang, body in BLOCK_RE.findall(TEXT):
            if lang == "python":
                first = body.partition("\n")[0]
                if (match := FILENAME_RE.match(first)) is not None:
                    (tmp_path / match.group(1)).write_text(body, encoding="utf-8")
                continue
            if lang != "console":
                continue
            for session in console_sessions(f"```console\n{body}```"):
                command = _without_environment(session.command)
                if command.startswith("python "):
                    argv = [sys.executable, *command.split()[1:]]
                    expected = session.expected
                elif command.startswith(("digline record on", "digline record status")):
                    argv = [sys.executable, "-m", "digline.cli", *command.split()[1:]]
                    expected = [
                        line for line in session.expected if line.startswith("  suite ")
                    ]
                else:
                    continue
                done = subprocess.run(
                    argv,
                    cwd=tmp_path,
                    env=env,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                assert done.returncode == 0, (command, done.stdout, done.stderr)
                printed = [line.rstrip() for line in done.stdout.splitlines()]
                for line in expected:
                    assert line in printed, (command, line, printed)
                ran.append(command)
    finally:
        server.shutdown()
    assert ran == [
        "digline record on --tenant acme",
        "python traffic.py",
        "digline record status --tenant acme",
        "python traffic.py",
        "digline record status --tenant acme",
        "python later.py",
    ]
