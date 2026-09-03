"""A plugin cannot claim to work with a core that does not have its API.

The trap, in full, because it is the kind that only shows up in somebody else's
environment: a plugin imports a name that arrived in digline 0.5.0 while its own
`pyproject.toml` still says `digline>=0.2.0`. Everything passes here — the
workspace has one core and it is the newest one — the wheel builds, the wheel
uploads, and then a user with digline 0.4.0 installed runs `pip install
digline-anthropic`, the resolver honours the floor it was given, and the plugin
fails on its first import.

Nothing else catches it. `publish.yml` installs each plugin wheel with the core
wheel built beside it, which is the newest core by construction. The tests here
run against the source. The floor is a promise about versions that are *not*
present, so the only thing that can check it is a rule about what the sources
reach for.

That rule: **every name a plugin imports out of `digline` has to be listed in
`INTRODUCED` below, and the plugin's floor has to be at least the highest of
them.** A name that is not listed fails this file rather than passing quietly,
which is the point — the moment a plugin reaches for a new part of the core,
somebody has to say which version it appeared in, and that is exactly the
moment the floor needs deciding.
"""

from __future__ import annotations

import ast
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ROOT / "packages"

#: When each name became part of digline's public surface, as the release that
#: first carried it. Verified against the history — `git log -S` on the
#: definition, then `git describe --contains` on the commit — rather than
#: remembered.
#:
#: A name here can be *too low* only by mistake, and the mistake is invisible
#: while every floor is above it. So the table is checked into the record: 0.1.0
#: is the first release, and anything claiming it should be a name that has
#: been there from the start.
INTRODUCED: dict[str, str] = {
    # 0.1.0 — the first published surface.
    "ModelPrice": "0.1.0",
    "Pricing": "0.1.0",
    "ProviderTarget": "0.1.0",
    "Usage": "0.1.0",
    "UnknownModelError": "0.1.0",
    "PromptTemplate": "0.1.0",
    "render_value": "0.1.0",
    # 0.1.3 — a plugin became a target *and* a judge (ADR 0004).
    "JudgeBase": "0.1.3",
    "ScoreJudge": "0.1.3",
    "ClaimCountJudge": "0.1.3",
    "loads_lenient": "0.1.3",
    # 0.2.0 — the configuration of the system under test (ADR 0005).
    "ConfigValue": "0.2.0",
    "CONTRACT_FIELDS": "0.2.0",
    "declared_config": "0.2.0",
    "endpoint_host": "0.2.0",
    "sent": "0.2.0",
    # 0.5.0 — providers as entry points (ADR 0007 §3).
    "Provider": "0.5.0",
    "ProviderNotFound": "0.5.0",
    "installed": "0.5.0",
    "resolve": "0.5.0",
    "split_coordinate": "0.5.0",
}


def plugins() -> list[Path]:
    found = sorted(p for p in PACKAGES.iterdir() if (p / "pyproject.toml").is_file())
    assert found, "no plugin found; this file would prove nothing"
    return found


def version_tuple(text: str) -> tuple[int, ...]:
    return tuple(int(part) for part in text.split("."))


def floor(plugin: Path) -> str:
    """The `digline>=X` a plugin's metadata declares."""
    with (plugin / "pyproject.toml").open("rb") as handle:
        project = tomllib.load(handle)["project"]
    for dependency in project["dependencies"]:
        text = str(dependency).replace(" ", "")
        if text.startswith("digline>="):
            return text.removeprefix("digline>=").split(",")[0]
    pytest.fail(f"{plugin.name} declares no `digline>=` floor at all")


def imported_from_digline(plugin: Path) -> set[str]:
    """Every name the plugin's sources take out of `digline`."""
    names: set[str] = set()
    for source in sorted((plugin / "src").rglob("*.py")):
        tree = ast.parse(source.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith(
                "digline."
            ):
                names.update(alias.name for alias in node.names)
    return names


@pytest.mark.parametrize("plugin", plugins(), ids=lambda p: p.name)
def test_every_core_name_a_plugin_imports_is_dated(plugin: Path) -> None:
    """The half that keeps the table honest.

    An undated name cannot be checked against a floor, so it fails here with
    the one question that needs answering."""
    undated = sorted(imported_from_digline(plugin) - set(INTRODUCED))
    assert not undated, (
        f"{plugin.name} imports {undated} from digline, and "
        "tests/test_plugin_floors.py does not say which release introduced "
        "them. Add each one to INTRODUCED with the version it first shipped "
        "in — `git log -S'<name>' --reverse -- src/` then "
        "`git describe --tags --contains <commit>` — and then check that this "
        "plugin's `digline>=` floor is at least that high."
    )


@pytest.mark.parametrize("plugin", plugins(), ids=lambda p: p.name)
def test_the_floor_covers_every_core_name_the_plugin_uses(plugin: Path) -> None:
    """The trap itself. A floor below the newest name the sources import is a
    published promise that the package cannot keep."""
    declared = floor(plugin)
    used = imported_from_digline(plugin) & set(INTRODUCED)
    needed = max(used, key=lambda name: version_tuple(INTRODUCED[name]))
    assert version_tuple(declared) >= version_tuple(INTRODUCED[needed]), (
        f"{plugin.name} declares `digline>={declared}` and imports "
        f"`{needed}`, which arrived in digline {INTRODUCED[needed]}. A user "
        f"who has digline {declared} installed would get this plugin and an "
        f"ImportError: raise the floor to >={INTRODUCED[needed]}."
    )


@pytest.mark.parametrize("plugin", plugins(), ids=lambda p: p.name)
def test_a_dated_name_still_exists_in_the_core(plugin: Path) -> None:
    """The table names the public surface, so a name removed from the core has
    to be removed from here too — otherwise the floor is computed against a
    version claim nobody can meet."""
    import digline.core
    import digline.targets

    for name in imported_from_digline(plugin) & set(INTRODUCED):
        assert hasattr(digline.core, name) or hasattr(digline.targets, name), name
