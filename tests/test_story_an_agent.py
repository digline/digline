"""`docs/walkthroughs/an-agent.md`, held to what was run.

Its Python blocks are held the way `docs/guide.md`'s are (`tests/test_guide.py`):
every block is a whole file, and every file is run or imported. Here they are
also run: walking the page in order, each file is written where the page shows
it, and the agent's commands, `python traffic.py`, `python missing.py` and
`python later.py`, run against the stand-in the story ran against
(`tests/_story_agent_stand_in.py`), with the recorder switched on by the page's
own `digline record on`. What each prints must be what the page says it
printed, and `digline record status` must count the suite's calls, episodes
and interrupted turns as the page does.

And the rest of the page, in its order: `suggest`, then the person's edit of
the proposal, held by the `diff` the page shows; each `record import` and
each `promote` held line for line, with a run's key and a recording's time
put aside; `run`, `explain` and `compare` run for the state they leave, by
their exit codes. `view` is not run: the import command is what its button
writes. What `suggest`, `run`, `explain` and `compare` print is not held
here. Their `console` blocks open with the command that printed them
(`tests/test_console_blocks.py`, which reads this page too).
"""

from __future__ import annotations

import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

from tests._docs import console_sessions, python_files, python_snippets
from tests._story_agent_stand_in import serve

from doc_fences import BLOCK_RE, FILENAME_RE

REPO = Path(__file__).resolve().parents[1]
PAGE = REPO / "docs" / "walkthroughs" / "an-agent.md"
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


#: A run's key, which a run again names differently.
KEY = re.compile(r"\d{4}-\d\d-\d\dT\d\d-\d\d-\d\d-\d+-\d\d-\d\d-[0-9a-f]+")
#: When an answer was first recorded, which a run again reads differently.
WHEN = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d+\+00:00")


def _same(lines: list[str]) -> list[str]:
    """The lines but the blank ones, as the page's sessions hold them, with
    what a run again names differently put aside."""
    return [
        WHEN.sub("WHEN", KEY.sub("KEY", line.rstrip()))
        for line in lines
        if line.strip()
    ]


def _patched(original: str, diff: list[str]) -> str:
    """`original` with a normal `diff`'s hunks applied, as `patch` would.

    Only the `c` hunks the page shows; anything else fails here rather than
    being applied wrongly."""
    hunks: list[tuple[int, int, list[str]]] = []
    for line in diff:
        if (found := re.fullmatch(r"(\d+)(?:,(\d+))?c\d+(?:,\d+)?", line)) is not None:
            first = int(found.group(1))
            hunks.append((first, int(found.group(2) or first), []))
        elif line.startswith("> "):
            hunks[-1][2].append(line[2:])
        else:
            assert line == "---" or line.startswith("< "), line
    lines = original.splitlines()
    for first, last, new in reversed(hunks):
        lines[first - 1 : last] = new
    return "\n".join(lines) + "\n"


def test_the_story_imports_and_promotes_as_it_says(tmp_path: Path) -> None:
    """The whole page, in its order, against the stand-in: the proposal and
    the person's edit of it, the imports and the run, then a turn that
    refunds without looking, a yes to it, and the run that contradicts it.

    Held line for line, with a run's key and a recording's time put aside:
    what `diff` prints between the proposal and the suite, what each
    `record import` prints, the first `promote`, and the second `promote`'s
    refusal on standard error with its exit code `64`. `run`, `explain` and
    `compare` run for the state they leave, by their exit codes; what they
    print is not held here. `view` is not run: the page's import command is
    what its button writes."""
    eval_dir = tmp_path / "eval"
    eval_dir.mkdir()
    server = serve()
    env = _environment(server.server_port)
    ran: list[str] = []
    #: Each run key the page names, to the key the same run has here.
    keys: dict[str, str] = {}
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
                words = shlex.split(command)
                if command.startswith("digline view"):
                    continue
                if command == "diff suite.proposed.toml suite.toml":
                    proposed = (eval_dir / "suite.proposed.toml").read_text(
                        encoding="utf-8"
                    )
                    (eval_dir / "suite.toml").write_text(
                        _patched(proposed, session.expected), encoding="utf-8"
                    )
                    done = _run(["diff", *words[1:]], eval_dir, env)
                    assert done.returncode == 1, done.stderr
                    assert done.stdout.splitlines() == session.expected
                    ran.append(command)
                    continue
                if words[0] == "python":
                    argv = [sys.executable, *words[1:]]
                else:
                    words = [keys.get(word, word) for word in words]
                    argv = _cli(*words[1:])
                cwd = eval_dir if words[:2] == ["digline", "suggest"] else tmp_path
                done = _run(argv, cwd, env)
                ran.append(command)
                if command == "python missing.py":
                    assert done.returncode == 1, done.stderr
                elif words[:2] == ["digline", "run"]:
                    assert done.returncode == 0, done.stderr
                    keys[session.expected[-1]] = done.stdout.split()[-1]
                elif words[:2] in (["digline", "explain"], ["digline", "compare"]):
                    assert done.returncode == 1, (done.stdout, done.stderr)
                elif words[:2] == ["digline", "promote"] and "none" not in words:
                    assert done.returncode == 64, (done.stdout, done.stderr)
                    assert _same(done.stderr.splitlines()) == _same(session.expected)
                else:
                    assert done.returncode == 0, (command, done.stdout, done.stderr)
                    if words[:3] == ["digline", "record", "import"] or words[:2] == [
                        "digline",
                        "promote",
                    ]:
                        assert _same(done.stdout.splitlines()) == _same(
                            session.expected
                        ), command
    finally:
        server.shutdown()
    assert len(keys) == 2, keys
    assert [command.split(" --")[0] for command in ran] == [
        "digline record on",
        "python traffic.py",
        "digline record status",
        "python missing.py",
        "digline record status",
        "digline suggest",
        "diff suite.proposed.toml suite.toml",
        "digline record import",
        "digline run",
        "digline promote",
        "python later.py",
        "digline record import",
        "digline record import",
        "digline run",
        "digline explain",
        "digline compare",
        "digline promote",
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
