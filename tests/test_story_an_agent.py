"""`docs/stories/an-agent.md`, held to what was run.

Its Python blocks are held the way `docs/guide.md`'s are (`tests/test_guide.py`):
every block is a whole file, and every file is run or imported. Here they are
also run: walking the page in order, each file is written where the page shows
it, and the agent's commands, `python traffic.py`, `python missing.py` and
`python later.py`, run against the stand-in the story ran against
(`tests/_story_agent_stand_in.py`), with the recorder switched on by the page's
own `digline record on`. What each prints must be what the page says it
printed, and `digline record status` must count the suite's calls, episodes
and interrupted turns as the page does.

What this does not replay: `suggest`, `diff`, `view`, `import`, `run`,
`promote`, `explain` and `compare`. Their `console` blocks open with the
command that printed them (`tests/test_console_blocks.py`, which reads this
page too), and no more is held of them here.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from tests._docs import console_sessions, python_files, python_snippets
from tests._story_agent_stand_in import serve

from doc_fences import BLOCK_RE, FILENAME_RE

REPO = Path(__file__).resolve().parents[1]
PAGE = REPO / "docs" / "stories" / "an-agent.md"
TEXT = PAGE.read_text(encoding="utf-8")
MARK = "> **Arrives with digline 1.1.**"
#: The line of `agent.py` that hands the model's reply back as the SDK gave it.
PLAIN = 'messages.append({"role": "assistant", "content": reply.content})'


def test_the_story_carries_the_mark_under_its_title() -> None:
    """Until 1.1.0 is on PyPI the story's commands need digline from this
    repository, and the mark says so under the title. The cut takes it out
    (RELEASING.md, *Owed to the next version*)."""
    title, rest = TEXT.split("\n", 1)
    assert title.startswith("# ")
    assert rest.lstrip("\n").startswith(MARK)


def test_every_python_block_is_a_file_the_story_runs() -> None:
    """No snippet nobody executes: every block is a whole file, and each file
    is run by a command on the page or imported by a file that is."""
    assert python_snippets(TEXT) == []
    files = python_files(TEXT)
    assert set(files) == {
        "tools.py",
        "agent.py",
        "traffic.py",
        "missing.py",
        "later.py",
    }
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


def _environment(port: int) -> dict[str, str]:
    return {
        **os.environ,
        "ANTHROPIC_BASE_URL": f"http://127.0.0.1:{port}",
        "ANTHROPIC_API_KEY": "fake",
    }


def _run(
    argv: list[str], cwd: Path, env: dict[str, str]
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv, cwd=cwd, env=env, capture_output=True, text=True, check=False
    )


def _cli(*words: str) -> list[str]:
    return [sys.executable, "-m", "digline.cli", *words]


def test_the_story_records_what_it_says(tmp_path: Path) -> None:
    """The page's files, written in its order, against the stand-in: each
    `python` command prints what the page says, the turn that breaks exits
    with the page's last line, and each `record status` counts the suite as
    the page does."""
    server = serve()
    env = _environment(server.server_port)
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
                elif command.startswith(("digline record on", "digline record status")):
                    argv = _cli(*command.split()[1:])
                else:
                    continue
                done = _run(argv, tmp_path, env)
                if command == "python missing.py":
                    # The traceback is the page's first and last line, with
                    # its middle cut to `…`.
                    assert done.returncode == 1, (done.stdout, done.stderr)
                    said = done.stderr.splitlines()
                    assert said[0] == session.expected[0]
                    assert said[-1] == session.expected[-1] == "KeyError: '99'"
                    ran.append(command)
                    continue
                assert done.returncode == 0, (command, done.stdout, done.stderr)
                expected = session.expected
                if command.startswith("digline"):
                    expected = [
                        line for line in expected if line.startswith("  suite ")
                    ]
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
        "python missing.py",
        "digline record status --tenant acme",
        "python later.py",
    ]


def test_the_sdks_own_objects_are_recorded(tmp_path: Path) -> None:
    """The page's agent hands `reply.content` back as the SDK gave it, and
    says the wrapper records it: `traffic.py` leaves nothing `not recorded`,
    and the five calls of the page's status. (P-1588)"""
    files = python_files(TEXT)
    assert PLAIN in files["agent.py"]
    assert "to_dict" not in files["agent.py"]
    for name in ("tools.py", "agent.py", "traffic.py"):
        (tmp_path / name).write_text(files[name], encoding="utf-8")
    server = serve()
    env = _environment(server.server_port)
    try:
        on = _run(_cli("record", "on", "--tenant", "acme"), tmp_path, env)
        assert on.returncode == 0
        done = _run([sys.executable, "traffic.py"], tmp_path, env)
        assert done.returncode == 0, done.stderr
    finally:
        server.shutdown()
    status = _run(_cli("record", "status", "--tenant", "acme"), tmp_path, env)
    assert "not recorded" not in status.stdout
    assert "  suite support: 5 calls, 5 inside episodes, 0 orphans, 3 episodes;" in (
        status.stdout
    )
