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
ASK = PLUGIN / "scripts" / "ask-before-promote"

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


def test_the_description_names_the_absence() -> None:
    """The point, not a limitation: said where a user decides to install."""
    for description in (
        load(MANIFEST)["description"],
        load(MARKETPLACE)["plugins"][0]["description"],
    ):
        assert isinstance(description, str)
        assert "cannot promote a baseline" in description
        assert "approval is a person's commit" in description


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
    server it starts has no tool that could. The hook names `promote` in order
    to ask a person about it, so the scripts are not swept."""
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


def ask(command: str) -> str:
    payload = json.dumps(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": command, "description": "run it"},
        }
    )
    done = subprocess.run(
        [str(ASK)], input=payload, capture_output=True, text=True, check=True
    )
    return done.stdout


@pytest.mark.parametrize(
    "command",
    [
        "digline promote --suite suite.py --run latest",
        "uv run digline promote --suite suite.py --run k",
        ".venv/bin/digline promote --suite s.py --run k",
        "digline --root . promote --suite s.py --run k",
        "python -m digline.cli promote --suite s.py --run k",
        "DIGLINE_LIVE=1 digline promote --suite s.py --run k",
        "digline compare --suite s.py && digline promote --suite s.py --run k",
    ],
)
def test_the_hook_asks_a_person_before_promote(command: str) -> None:
    """`ask` and never `deny`: AGENTS.md lets the human tell the agent to."""
    output = json.loads(ask(command))["hookSpecificOutput"]
    assert output["hookEventName"] == "PreToolUse"
    assert output["permissionDecision"] == "ask"
    assert "not a wall" in output["permissionDecisionReason"]


@pytest.mark.parametrize(
    "command",
    [
        "digline run --suite suite.py",
        "digline compare --suite suite.py",
        "digline compare --suite s.py && git commit -m 'promote later'",
        "digline-mcp --root .",
        "grep -rn promote src/",
    ],
)
def test_the_hook_stays_silent_on_everything_else(command: str) -> None:
    """A hook that asks about every digline command trains the person to
    approve without reading, which is the one thing it exists to prevent."""
    assert ask(command) == ""


def test_the_command_the_hook_watches_is_one_the_cli_has() -> None:
    """If `promote` were renamed, the hook would go on matching a word nobody
    types and asking about nothing."""
    subprocess.run(
        [sys.executable, "-m", "digline.cli", "promote", "--help"],
        capture_output=True,
        check=True,
    )
