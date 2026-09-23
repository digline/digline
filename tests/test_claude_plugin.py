"""The Claude Code plugin, held to what the rest of the repository says.

The plugin is packaging: the skill, a launch line for `digline-mcp`, and one
hook. Each of those is a copy of, or a pointer at, something that lives
elsewhere and moves on its own schedule, and a plugin that falls behind the
thing it packages is worse than no plugin — it is the version of the playbook
the user trusts. So every pointer is read against its target here. The version
and the ref it installs from are pinned in `test_versions.py::LIVE`, with the
other numbers written by hand.

The two scripts are exercised rather than read: the launcher's refusal is the
first thing a new user meets, and the hook's pattern is only as good as the
commands it has been shown.
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

import pytest

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "digline"
MARKETPLACE = ROOT / ".claude-plugin" / "marketplace.json"
MANIFEST = PLUGIN / ".claude-plugin" / "plugin.json"
SERVE = PLUGIN / "scripts" / "serve"
ASK = PLUGIN / "scripts" / "ask-a-person"

pytestmark = pytest.mark.skipif(
    sys.platform == "win32", reason="the plugin's scripts are POSIX sh"
)


def load(path: Path) -> dict[str, Any]:
    """JSON is untyped; the assertions below are what give it a shape."""
    data = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return cast(dict[str, Any], data)


def test_the_marketplace_installs_this_plugin_from_its_own_path() -> None:
    """A git-subdir source, so what a user installs is the tagged tree rather
    than whatever `main` holds between releases. The ref itself is gated in
    `test_versions.py`; this holds the path and the absence of a second
    version, which the documentation says silently shadows the first."""
    (entry,) = load(MARKETPLACE)["plugins"]
    assert entry["name"] == load(MANIFEST)["name"] == "digline"
    source = entry["source"]
    assert source["source"] == "git-subdir"
    assert (ROOT / source["path"]) == PLUGIN
    assert "version" not in entry, (
        "the version lives in plugin.json; set in both places the manifest "
        "shadows the marketplace entry without a warning"
    )


def test_the_description_names_the_absence_and_the_interruption() -> None:
    """Both, where a user decides to install. The absence is the server's: the
    point, not a limitation. The hook is the part that stops you mid-session,
    and a description that predicts the server but not the interruption
    under-promises the one thing the user will notice."""
    for description in (
        load(MANIFEST)["description"],
        load(MARKETPLACE)["plugins"][0]["description"],
    ):
        assert isinstance(description, str)
        assert "cannot promote a baseline" in description
        assert "approval is a person's commit" in description
        assert "hook that asks you" in description
        assert "`digline promote`" in description
        assert "`digline register`" in description


def test_the_skill_is_the_same_file_as_the_repository_skill() -> None:
    """Two copies, byte for byte. `test_agents.py` holds one of them against
    `AGENTS.md`; this holds the other against it, so the plugin cannot ship a
    playbook one rule short."""
    ours = ROOT / ".claude" / "skills" / "operating-digline" / "SKILL.md"
    shipped = PLUGIN / "skills" / "operating-digline" / "SKILL.md"
    assert shipped.read_bytes() == ours.read_bytes(), (
        f"{shipped.relative_to(ROOT)} differs from {ours.relative_to(ROOT)}. "
        "Edit one, copy it over the other."
    )


def test_no_plugin_surface_can_promote() -> None:
    """No skill, command or agent in the plugin is about promoting, and the MCP
    server it starts has no tool that could. The hook names `promote` and
    `register` in order to ask a person about them, so the scripts are not
    swept."""
    for path in PLUGIN.rglob("*"):
        if path.is_dir() or "scripts" in path.parts or path.suffix != ".md":
            continue
        if path.name == "SKILL.md":
            front = path.read_text(encoding="utf-8").split("---\n", 2)[1]
            assert "name: operating-digline" in front
            continue
        if path.name == "README.md" and path.parent == PLUGIN:
            continue
        pytest.fail(f"{path.relative_to(ROOT)}: a component nobody reviewed for this")
    assert not (PLUGIN / "commands").exists() and not (PLUGIN / "agents").exists()


@pytest.mark.parametrize("script", [SERVE, ASK], ids=lambda p: p.name)
def test_the_scripts_are_executable_in_the_index(script: Path) -> None:
    """The mode that ships is git's, not the working tree's."""
    assert script.stat().st_mode & stat.S_IXUSR
    listed = subprocess.run(
        ["git", "ls-files", "--stage", str(script.relative_to(ROOT))],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    if listed:  # an uncommitted file has no index mode yet
        assert listed.startswith("100755"), listed


def test_the_mcp_config_starts_the_launcher_on_the_project() -> None:
    config = load(PLUGIN / ".mcp.json")
    server = config["mcpServers"]["digline"]
    assert server["command"] == "${CLAUDE_PLUGIN_ROOT}/scripts/serve"
    assert server["args"] == ["${CLAUDE_PROJECT_DIR}"]


def test_the_launcher_refuses_without_the_projects_digline_mcp(tmp_path: Path) -> None:
    """The first thing a new user meets: one sentence naming the fix, on
    stderr, and nothing on stdout, which is the protocol channel — and nothing
    written into the repository, which `uv run` would have done."""
    done = subprocess.run(
        [str(SERVE), str(tmp_path)], capture_output=True, text=True, check=False
    )
    assert done.returncode == 1
    assert done.stdout == ""
    assert "uv add --dev digline-mcp" in done.stderr
    assert list(tmp_path.iterdir()) == []


def test_the_launcher_uses_the_projects_environment_and_nothing_else(
    tmp_path: Path,
) -> None:
    """Not PATH and not an active environment: a stand-in on PATH must lose to
    the project's own, whose arguments are what the real one receives."""
    decoy = tmp_path / "decoy"
    decoy.mkdir()
    for directory, word in ((decoy, "decoy"), (tmp_path / ".venv" / "bin", "project")):
        directory.mkdir(parents=True, exist_ok=True)
        fake = directory / "digline-mcp"
        fake.write_text(f'#!/bin/sh\necho {word} "$@"\n', encoding="utf-8")
        fake.chmod(0o755)
    env = {**os.environ, "PATH": f"{decoy}{os.pathsep}{os.environ['PATH']}"}
    env["VIRTUAL_ENV"] = str(decoy)
    done = subprocess.run(
        [str(SERVE), str(tmp_path)], capture_output=True, text=True, env=env, check=True
    )
    assert done.stdout.split() == ["project", "--root", str(tmp_path)]


def test_the_flag_the_launcher_passes_is_one_the_server_takes() -> None:
    """`--root` is written in a shell script nothing type-checks; the server's
    own parser is the authority on whether it still exists."""
    shown = subprocess.run(
        [sys.executable, "-m", "digline_mcp", "--help"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert "--root" in shown


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """A project the hook counts as digline's: `.digline/` at its root and a
    `.venv` whose python runs the matcher. The interpreter is this test run's
    own, linked where the project's would be."""
    (tmp_path / ".digline").mkdir()
    (tmp_path / ".venv" / "bin").mkdir(parents=True)
    (tmp_path / ".venv" / "bin" / "python").symlink_to(sys.executable)
    return tmp_path


def ask(command: str, project: Path) -> str:
    payload = json.dumps(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": command, "description": "run it"},
        }
    )
    done = subprocess.run(
        [str(ASK)],
        input=payload,
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ, "CLAUDE_PROJECT_DIR": str(project)},
    )
    return done.stdout


@pytest.mark.parametrize(
    ("command", "names"),
    [
        (command, "promote")
        for command in (
            "digline promote --suite suite.py --run latest",
            "uv run digline promote --suite suite.py --run k",
            ".venv/bin/digline promote --suite s.py --run k",
            "digline --root . promote --suite s.py --run k",
            "python -m digline.cli promote --suite s.py --run k",
            "DIGLINE_LIVE=1 digline promote --suite s.py --run k",
            "digline compare --suite s.py && digline promote --suite s.py --run k",
            "digline compare --suite s.py\ndigline promote --suite s.py --run k",
            "uv run --project . digline promote --suite s.py --run k",
            "uvx digline promote --suite s.py --run k",
        )
    ]
    + [
        (command, "register")
        for command in (
            "digline register --suite s.py --run k --disposition accepted",
            "uv run digline register --suite s.py --run latest --disposition unsure",
            "python -m digline.cli register --suite s --run k --disposition rejected",
        )
    ],
)
def test_the_hook_asks_a_person_before_a_persons_decision(
    command: str, names: str, project: Path
) -> None:
    """`promote` and `register` both commit a person's judgement, and AGENTS.md
    rule 1 holds them to one rule. `ask` and never `deny`: the human may tell
    the agent to. The reason names the command, so the person approves the
    decision they are actually looking at."""
    output = json.loads(ask(command, project))["hookSpecificOutput"]
    assert output["hookEventName"] == "PreToolUse"
    assert output["permissionDecision"] == "ask"
    reason = output["permissionDecisionReason"]
    assert reason.startswith(f"digline {names} ")
    assert "not a wall" in reason


@pytest.mark.parametrize(
    "command",
    [
        "digline run --suite suite.py",
        "digline compare --suite suite.py",
        "digline compare --suite s.py && git commit -m 'promote later'",
        "digline-mcp --root .",
        "grep -rn promote src/",
        "git commit -m 'register the new suite'",
        "digline view --suite s.py",
        "echo digline promote",
        "cat notes.md | grep 'digline promote'",
        "python -m pytest -k promote",
    ],
)
def test_the_hook_stays_silent_on_everything_else(command: str, project: Path) -> None:
    """A hook that asks about every digline command trains the person to
    approve without reading, which is the one thing it exists to prevent."""
    assert ask(command, project) == ""


def test_a_grep_for_the_command_is_not_the_command(project: Path) -> None:
    """Found by running the hook, not by reasoning about it: when it matched a
    string anywhere in the payload, searching the notes for the command asked a
    person to approve the search. The command is read from its first word, and
    this one is a grep."""
    assert ask('grep -r "digline register " notes/', project) == ""


@pytest.mark.parametrize(
    "missing", [".digline", ".venv"], ids=["no .digline", "no .venv"]
)
def test_the_hook_is_silent_where_digline_is_not(missing: str, project: Path) -> None:
    """At user scope the hook sees every repository's Bash. Without
    `.digline/` there is nothing for promote to write; without `.venv` the MCP
    server cannot start either, and no other interpreter is borrowed."""
    shutil.rmtree(project / missing)
    assert ask("digline promote --suite s.py --run k", project) == ""


def test_the_hook_is_silent_without_a_project() -> None:
    done = subprocess.run(
        [str(ASK)],
        input='{"tool_input": {"command": "digline promote --run k"}}',
        capture_output=True,
        text=True,
        check=True,
        env={k: v for k, v in os.environ.items() if k != "CLAUDE_PROJECT_DIR"},
    )
    assert done.stdout == ""


@pytest.mark.parametrize("subcommand", ["promote", "register"])
def test_the_commands_the_hook_watches_are_ones_the_cli_has(subcommand: str) -> None:
    """If one were renamed, the hook would go on matching a word nobody types
    and asking about nothing."""
    subprocess.run(
        [sys.executable, "-m", "digline.cli", subcommand, "--help"],
        capture_output=True,
        check=True,
    )
