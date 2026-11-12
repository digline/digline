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

import argparse
import importlib.util
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


def _hook() -> Any:
    """The hook's module, loaded by path.

    `plugins/` is not a package and must not become one: the script runs in the
    user's `.venv` with the standard library and nothing else, which is the
    whole reason it may not import digline. Loading it by path here is how a
    test reads its tables without giving it an installable name.
    """
    spec = importlib.util.spec_from_file_location(
        "ask_a_person", PLUGIN / "scripts" / "ask_a_person.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


REASONS: dict[str, str] = _hook().REASONS

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


#: Every skill the plugin ships, by directory, read off the tree.
SKILLS = sorted(path.name for path in (PLUGIN / "skills").iterdir() if path.is_dir())


def test_the_plugin_and_the_repository_carry_the_same_skills() -> None:
    """A skill added to one place and not the other reaches only half of the
    users; read both directories rather than a list written here."""
    ours = sorted(
        path.name for path in (ROOT / ".claude" / "skills").iterdir() if path.is_dir()
    )
    assert ours == SKILLS
    assert {"operating-digline", "proposing-a-suite"} <= set(SKILLS)


@pytest.mark.parametrize("skill", SKILLS)
def test_the_skill_is_the_same_file_as_the_repository_skill(skill: str) -> None:
    """Two copies, byte for byte. `test_agents.py` holds one of them against
    `AGENTS.md`; this holds the other against it, so the plugin cannot ship a
    playbook one rule short.

    The repository's copy is also the one skills.sh ships: `npx skills add
    digline/digline` reads `.claude/skills/operating-digline/SKILL.md` from
    `main`, not the plugin's, as the `skillPath` of its `skills-lock.json`
    records. Moving or deleting `.claude/skills/` changes what those users
    receive, which nothing in the path suggests. Each skill the plugin ships
    is held the same way, `proposing-a-suite` since it joined."""
    ours = ROOT / ".claude" / "skills" / skill / "SKILL.md"
    shipped = PLUGIN / "skills" / skill / "SKILL.md"
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
            # Reviewed for this: `proposing-a-suite` names `promote` only to
            # forbid it, and its tests below hold the prohibitions in place.
            assert (
                "name: operating-digline" in front or "name: proposing-a-suite" in front
            ), front
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
    assert "--names {clear,project}" in shown


def test_the_launcher_declares_clear_to_a_server_that_takes_it(tmp_path: Path) -> None:
    """The project open in the editor is its user's own, so its names may leave
    in clear; the script says so, and when that is wrong. A server whose usage
    lists `--names` is started with `--names clear`, and one from before the
    declaration, as the test above starts, without it. (ADR 0054 §1)"""
    bin_ = tmp_path / ".venv" / "bin"
    bin_.mkdir(parents=True)
    fake = bin_ / "digline-mcp"
    fake.write_text(
        '#!/bin/sh\nif [ "$1" = --help ]; then echo "--names {clear,project}"; '
        'exit 0; fi\necho project "$@"\n',
        encoding="utf-8",
    )
    fake.chmod(0o755)
    done = subprocess.run(
        [str(SERVE), str(tmp_path)], capture_output=True, text=True, check=True
    )
    assert done.stdout.split() == [
        "project",
        "--root",
        str(tmp_path),
        "--names",
        "clear",
    ]
    script = SERVE.read_text(encoding="utf-8")
    assert "the project open in the editor is its user's own" in " ".join(
        script.replace("#", "").split()
    )


@pytest.mark.parametrize(
    ("given", "passed"),
    [
        ("acme", ["--tenant", "acme"]),
        ("", []),
        (None, []),
        # A client that does not substitute leaves the placeholder as written.
        ("${user_config.tenant}", []),
    ],
    ids=["given", "empty", "absent", "unsubstituted"],
)
def test_the_launcher_passes_the_tenant_the_configuration_gives(
    tmp_path: Path, given: str | None, passed: list[str]
) -> None:
    """`tenant` in the plugin's userConfig reaches the server as `--tenant`,
    through the variable `.mcp.json` sets; an empty one, or a placeholder no
    client filled in, starts the server without it."""
    bin_ = tmp_path / ".venv" / "bin"
    bin_.mkdir(parents=True)
    fake = bin_ / "digline-mcp"
    fake.write_text(
        '#!/bin/sh\nif [ "$1" = --help ]; then echo "--names {clear,project}"; '
        'exit 0; fi\necho project "$@"\n',
        encoding="utf-8",
    )
    fake.chmod(0o755)
    env = {k: v for k, v in os.environ.items() if k != "DIGLINE_PLUGIN_TENANT"}
    if given is not None:
        env["DIGLINE_PLUGIN_TENANT"] = given
    done = subprocess.run(
        [str(SERVE), str(tmp_path)], capture_output=True, text=True, env=env, check=True
    )
    assert done.stdout.split() == [
        "project",
        "--root",
        str(tmp_path),
        "--names",
        "clear",
        *passed,
    ]


def test_the_tenant_the_server_is_handed_is_one_the_plugin_declares() -> None:
    """`.mcp.json` reads `${user_config.tenant}`, so `plugin.json` declares
    it, optional, and the server's own usage lists `--tenant`."""
    server = load(PLUGIN / ".mcp.json")["mcpServers"]["digline"]
    assert server["env"] == {"DIGLINE_PLUGIN_TENANT": "${user_config.tenant}"}
    option = load(PLUGIN / ".claude-plugin" / "plugin.json")["userConfig"]["tenant"]
    assert option["type"] == "string" and option["required"] is False
    shown = subprocess.run(
        [sys.executable, "-m", "digline_mcp", "--help"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert "--tenant" in shown


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
            # ADR 0032 §4c, closed in 0.20.1: `uv tool run` is `uvx` spelled
            # out, and `uv` recognises what it runs by these same rules rather
            # than by the word `digline`.
            "uv tool run digline promote --suite s.py --run k",
            "uv tool run --from digline digline promote --suite s.py --run k",
            "uv run python -m digline.cli promote --suite s.py --run k",
            "uvx --from digline python -m digline.cli promote --suite s.py --run k",
            "python -m digline.cli.main promote --suite s.py --run k",
            "python -m digline.cli.__main__ promote --suite s.py --run k",
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
        # Bare `view` is a reading tool and stays in this company. The one
        # spelling that no longer belongs here has a test of its own below.
        "digline view --suite s.py",
        "digline view --port 0 --suite s.py",
        'grep -r "digline view --allow-promote" notes/',
        'grep -r "digline view --allow-record" notes/',
        "echo digline promote",
        "cat notes.md | grep 'digline promote'",
        "python -m pytest -k promote",
        "uv run pytest -k promote",
        "uv tool run ruff check .",
        # Not a spelling that runs: `digline` has no `__main__`.
        "python -m digline promote --suite s.py --run k",
        # `record` reads, except where it writes a yes or no or switches on.
        "digline record import --tenant acme --suite s.py",
        "digline record off --tenant acme",
        "digline record status --json",
        "digline record compare --tenant acme --suite s.py --setup a b",
        'grep -r "digline record on" notes/',
        'grep -r "digline record import --good" notes/',
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


@pytest.mark.parametrize(
    "command",
    [
        "digline view --allow-promote --suite s.py",
        "digline view --suite s.py --allow-promote",
        "digline --root . view --allow-promote --suite s.py",
        "uvx digline view --allow-promote",
        "digline compare --suite s.py && digline view --allow-promote",
    ],
)
def test_the_hook_asks_before_the_flag_that_makes_the_decision_ambient(
    command: str, project: Path
) -> None:
    """`digline view --allow-promote` is not a smaller thing than `digline
    promote` but a larger one: the same decision, standing for every run in the
    store for as long as the server is up. So the hook reads a word that is not
    the subcommand — a change to its reach, not to its principle, because the
    word is still one of the parsed simple command. (ADR 0032 §3)"""
    output = json.loads(ask(command, project))["hookSpecificOutput"]
    assert output["permissionDecision"] == "ask"
    reason = output["permissionDecisionReason"]
    assert reason.startswith("digline view --allow-promote ")
    assert "not a wall" in reason


@pytest.mark.parametrize(
    ("command", "names"),
    [
        (command, "record import")
        for command in (
            "digline record import --tenant acme --suite s.py --good cap-1-2 --by Ada",
            "digline record import --tenant acme --suite s.py --bad=cap-1-2 --by Ada",
            "uv run digline record import --suite s.py --tenant acme --bad cap-1-2",
            "digline --root . record --tenant acme import --good cap-1-2 --by Ada",
        )
    ]
    + [
        (command, "record on")
        for command in (
            "digline record on --tenant acme",
            "digline record --tenant acme on --sample 0.5",
            "python -m digline.cli record on --tenant acme --production",
        )
    ]
    + [
        (command, "view --allow-record")
        for command in (
            "digline view --allow-record --suite s.py",
            "digline --root . view --suite s.py --allow-record",
            "uvx digline view --port 0 --allow-record",
        )
    ],
)
def test_the_hook_asks_before_a_record_that_decides(
    command: str, names: str, project: Path
) -> None:
    """An import that names an answer writes a person's yes or no under their
    name, and `record on` decides what of an application's calls is kept: each
    is a person's, so each is asked, and the listing, `off`, `status` and
    `compare` above are not. `view --allow-record` serves both from a page, for
    as long as the server is up, and is asked the same way. (ADR 0059 §1, ADR
    0058 §10, ADR 0061 §4)"""
    output = json.loads(ask(command, project))["hookSpecificOutput"]
    assert output["permissionDecision"] == "ask"
    reason = output["permissionDecisionReason"]
    assert reason.startswith(f"digline {names} ")
    assert "not a wall" in reason


def _runnable_modules() -> set[str]:
    """Every module `python -m` can run under `src/digline/`, read off the tree:
    a package with a `__main__.py` (runnable by its own name and as
    `<package>.__main__`), and a module with a `__main__` guard."""
    src = ROOT / "src"
    found: set[str] = set()
    for path in (src / "digline").rglob("*.py"):
        dotted = ".".join(path.relative_to(src).with_suffix("").parts)
        if path.name == "__main__.py":
            found |= {dotted.removesuffix(".__main__"), dotted}
        elif 'if __name__ == "__main__"' in path.read_text(encoding="utf-8"):
            found.add(dotted)
    return found


def test_the_modules_the_hook_reads_are_the_ones_that_run() -> None:
    """`MODULES` is a list written by hand, and ADR 0032 §4c found it wrong both
    ways: it named `digline`, which cannot run, and missed `digline.cli.main`,
    which can. The hook may not import digline, so it cannot ask at run time;
    this asks the tree instead, and runs each one to be sure it is the CLI.
    (ADR 0032 §8: derive the spellings from what accepts them.)"""
    runnable = _runnable_modules()
    assert set(_hook().MODULES) == runnable
    for module in sorted(runnable):
        done = subprocess.run(
            [sys.executable, "-m", module, "--version"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert done.returncode == 0 and done.stdout.startswith("digline "), module


#: The wrappers the hook's docstring names as passing without a prompt. Held
#: both ways: each is silent, and the docstring names exactly these, so a hook
#: that starts reading one cannot leave the sentence claiming it does not.
UNREAD_WRAPPERS = ("env", "time", "nohup", "exec", "sudo", "command")


@pytest.mark.parametrize("wrapper", UNREAD_WRAPPERS)
def test_what_the_docstring_says_is_not_read_is_not_read(
    wrapper: str, project: Path
) -> None:
    assert ask(f"{wrapper} digline promote --suite s.py --run k", project) == ""
    assert f"`{wrapper}`" in (_hook().__doc__ or ""), (
        f"the hook passes `{wrapper} digline …` silently and its docstring does "
        "not say so"
    )


#: Every flag the hook watches, with the subcommand and action it is read in.
WATCHED_FLAGS = sorted(
    (subcommand, rule.action, flag)
    for subcommand, rules in _hook().FLAGGED.items()
    for rule in rules
    for flag in rule.flags
)


@pytest.mark.parametrize(
    ("subcommand", "action", "flag"), WATCHED_FLAGS, ids=lambda v: str(v)
)
def test_a_watched_flag_has_no_spelling_but_its_own(
    subcommand: str, action: str | None, flag: str
) -> None:
    """The hook matches a watched flag as a whole word, so the CLI must accept
    no other spelling of it — and argparse accepts every unambiguous prefix of
    an option unless the parser refuses abbreviations. On 0.20.0 `digline view
    --a` started the promoting server with the hook silent, and a POST with no
    `Origin` then promoted with nobody asked (0.20.0 delta-pass, F-1). Derived
    from the hook's own table, so a flag it starts watching is held to this
    without anybody remembering to add it."""
    from digline.cli.main import build_parser

    # A flag that takes a value is given one, so what is measured is the
    # spelling, not a missing argument.
    parser = build_parser()
    commands = next(
        cast("dict[str, argparse.ArgumentParser]", a.choices)  # pyright: ignore[reportUnknownMemberType]
        for a in parser._actions  # pyright: ignore[reportPrivateUsage]
        if isinstance(a.choices, dict)  # pyright: ignore[reportUnknownMemberType]
    )
    option = commands[subcommand]._option_string_actions[flag]  # pyright: ignore[reportPrivateUsage]
    takes = option.nargs != 0
    head = [subcommand, *([action] if action else [])]

    def accepted(word: str) -> bool:
        try:
            build_parser().parse_args(
                [*head, "--suite", "s.py", word, *(["x"] if takes else [])]
            )
        except SystemExit:
            return False
        return True

    assert accepted(flag), (
        f"`digline {subcommand} {flag}` is not a spelling the CLI takes"
    )
    taken = [flag[:end] for end in range(3, len(flag)) if accepted(flag[:end])]
    assert not taken, (
        f"`digline {subcommand}` accepts {', '.join(taken)} as {flag}, and the "
        "hook, which matches the whole word, would not ask for any of them"
    )


@pytest.mark.parametrize("watched", sorted(REASONS))
def test_the_commands_the_hook_watches_are_ones_the_cli_has(watched: str) -> None:
    """If one were renamed, the hook would go on matching a word nobody types
    and asking about nothing. Read from `REASONS` rather than listed here, so a
    key added to the hook without a command behind it fails rather than passes
    unexamined — and the flagged spelling is checked as a whole, because a flag
    argparse does not take is the same defect as a subcommand it does not have.
    """
    subprocess.run(
        [sys.executable, "-m", "digline.cli", *watched.split(), "--help"],
        capture_output=True,
        check=True,
    )


# --------------------------------------------------------------------------- #
# The proposing-a-suite skill, held to the CLI, the registry and the docs
# --------------------------------------------------------------------------- #

PROPOSING = PLUGIN / "skills" / "proposing-a-suite" / "SKILL.md"
AGENTS = ROOT / "AGENTS.md"
PROPOSING_PAGE = ROOT / "docs" / "proposing-a-suite.md"

#: Where the procedure is written, each read by a different agent: the skill
#: by Claude Code with the plugin, the section of `AGENTS.md` by any agent that
#: reads that file, and the page by the person.
PROCEDURE = (PROPOSING, AGENTS, PROPOSING_PAGE)


def _spans(path: Path) -> list[str]:
    """Every inline code span, with a line break inside one read as a space."""
    import re

    text = path.read_text(encoding="utf-8").replace("\n", " ")
    return re.findall(r"`([^`]+)`", text)


def _subcommands() -> dict[str, argparse.ArgumentParser]:
    from digline.cli.main import build_parser

    return next(
        cast("dict[str, argparse.ArgumentParser]", a.choices)  # pyright: ignore[reportUnknownMemberType]
        for a in build_parser()._actions  # pyright: ignore[reportPrivateUsage]
        if isinstance(a.choices, dict)  # pyright: ignore[reportUnknownMemberType]
    )


def _positional_choices(parser: argparse.ArgumentParser) -> set[str]:
    return {
        str(choice)
        for action in parser._actions  # pyright: ignore[reportPrivateUsage]
        if not action.option_strings and action.choices is not None
        for choice in cast("list[object]", action.choices)  # pyright: ignore[reportUnknownMemberType]
    }


def _cited_commands(path: Path) -> list[list[str]]:
    import shlex

    return [shlex.split(span) for span in _spans(path) if span.startswith("digline ")]


@pytest.mark.parametrize("path", PROCEDURE, ids=lambda p: p.name)
def test_every_command_the_procedure_cites_is_one_the_cli_has(path: Path) -> None:
    """A command written in prose nothing runs: the parser is the authority on
    whether its subcommand, its action and each of its flags exist. A command
    cited with all its values is also parsed whole; one cited bare, as an act
    the procedure forbids, is held to its words alone."""
    from digline.cli.main import build_parser

    commands = _subcommands()
    cited = _cited_commands(path)
    assert cited, f"{path.name} cites no digline command"
    for words in cited:
        sub = commands.get(words[1])
        assert sub is not None, f"`{' '.join(words)}`: no subcommand {words[1]!r}"
        actions = _positional_choices(sub)
        if actions and len(words) > 2 and not words[2].startswith("-"):
            assert words[2] in actions, f"`{' '.join(words)}`: no action {words[2]!r}"
        for word in words[2:]:
            if word.startswith("--"):
                assert word in sub._option_string_actions, (  # pyright: ignore[reportPrivateUsage]
                    f"`{' '.join(words)}`: `digline {words[1]}` takes no {word}"
                )
        if any(word.startswith("<") for word in words) or len(words) > 3:
            filled = [w.strip("<>") if w.startswith("<") else w for w in words[1:]]
            try:
                build_parser().parse_args(filled)
            except SystemExit as exc:  # pragma: no cover - the message is the point
                raise AssertionError(f"`{' '.join(words)}` does not parse") from exc


@pytest.mark.parametrize("path", PROCEDURE, ids=lambda p: p.name)
def test_every_flag_the_procedure_names_alone_is_one_the_cli_has(path: Path) -> None:
    """`--good` and `--bad`, named to forbid them, are still spellings of
    something: a flag the CLI dropped would leave the prohibition guarding a
    word nobody types."""
    flags = {
        flag
        for sub in _subcommands().values()
        for flag in sub._option_string_actions  # pyright: ignore[reportPrivateUsage]
    }
    for span in _spans(path):
        if span.startswith("--"):
            assert span.split()[0] in flags, f"{path.name} names {span}"


def test_every_metric_the_skill_cites_is_in_the_registry() -> None:
    """Every name in code style that looks like a class is a check the suite
    formats can build, read off the registry the TOML loader uses, so a
    renamed metric fails here rather than in a person's first suite."""
    import re

    from digline.host.toml_suite import AGGREGATES, ASSERTIONS

    registry = {kind.__name__ for kind in (*ASSERTIONS.values(), *AGGREGATES.values())}
    cited = {
        name
        for span in _spans(PROPOSING)
        for name in re.findall(r"^([A-Z][A-Za-z0-9]+)$", span)
    }
    assert {"LlmRubric", "Repeated", "Accuracy"} <= cited, cited
    assert cited <= registry, sorted(cited - registry)


@pytest.mark.parametrize("path", PROCEDURE, ids=lambda p: p.name)
def test_every_page_and_record_the_procedure_cites_exists(path: Path) -> None:
    """A page named for a step is where the agent goes to do it: one that
    moved leaves the step pointing nowhere."""
    import re

    text = path.read_text(encoding="utf-8").replace("\n", " ")
    pages = set(re.findall(r"`(docs/[^`]+\.md)`", text))
    pages |= {
        f"docs/{link}"
        for link in re.findall(r"\]\(([a-z0-9-]+\.md)(?:#[^)]*)?\)", text)
    }
    pages |= set(re.findall(r"\]\((docs/[^)#]+\.md)", text))
    assert pages, f"{path.name} cites no page"
    for page in pages:
        assert (ROOT / page).is_file(), f"{path.name} cites {page}"
    for number in re.findall(r"ADR (\d{4})", text):
        assert list((ROOT / "docs" / "adr").glob(f"{number}-*.md")), number


#: The sentence the counterexample rule is stated in, and the three phrases
#: the skill forbids an agent to write about its own work.
COUNTEREXAMPLE = "A suite that cannot fail measures nothing."
FORBIDDEN = ('"I labelled"', '"I promoted"', '"I imported"')


@pytest.mark.parametrize(
    ("path", "times"), ((PROPOSING, 2), (AGENTS, 1)), ids=("skill", "AGENTS.md")
)
def test_the_procedure_states_the_counterexample_and_the_three_prohibitions(
    path: Path, times: int
) -> None:
    """The skill states the counterexample among its three rules and again at
    the step that writes the case, so it is counted in both places."""
    text = " ".join(path.read_text(encoding="utf-8").split())
    assert text.lower().count(COUNTEREXAMPLE.lower().rstrip(".")) == times
    for phrase in FORBIDDEN:
        assert phrase in text, phrase


def test_agents_md_sends_the_reader_to_the_skill() -> None:
    """The section is the procedure for an agent without the plugin, and it
    points at the skill that says each step in full."""
    text = AGENTS.read_text(encoding="utf-8")
    assert "plugins/digline/skills/proposing-a-suite/SKILL.md" in text
    assert (ROOT / "plugins/digline/skills/proposing-a-suite/SKILL.md").is_file()


def test_the_proposing_skill_declares_its_frontmatter() -> None:
    import re

    text = PROPOSING.read_text(encoding="utf-8")
    front = text.split("---\n", 2)[1]
    assert re.search(r"^name: proposing-a-suite$", front, re.MULTILINE), front
    description = re.search(r"^description: (.+)$", front, re.MULTILINE)
    assert description is not None and "USE WHEN" in description.group(1)
