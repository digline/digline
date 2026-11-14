"""The pins `await_index.py` waits for before the examples run from PyPI.

Every package of this workspace that an example depends on, at the version
this tree declares for it: the core from the root `pyproject.toml`, each plugin
from its own under `packages/`. Printed as `name==version`, one per line, in
the order of the names.

Why not the core alone (RELEASING.md, *Owed to the next version*, P-1632): on
2026-11-10 the dispatch `42778062668` started 1 minute 53 seconds after
digline-mcp 0.9.0 was uploaded, waited for `digline==` alone, and its
`operator` leg installed digline-mcp 0.8.1, because the index the runner read
did not list 0.9.0 yet. A plugin an example installs is a pin like the core.

Read from the examples, not from a list: a plugin a new example depends on is
waited for without an edit here, and one no example names is not.

**What it does not cover, stated rather than assumed.** It waits for the
version this tree declares. An example whose range does not admit that version
resolves another, and a wait cannot speak for it; a lock pins what it pins.

Usage:

    python .github/example_pins.py [ROOT]
"""

from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path
from typing import cast

#: The name at the head of a PEP 508 requirement.
NAME = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")


def normalize(name: str) -> str:
    """PEP 503 normalisation, as `await_index.py` does."""
    return re.sub(r"[-_.]+", "-", name).lower()


def _project(path: Path) -> dict[str, object]:
    return dict(tomllib.loads(path.read_text(encoding="utf-8"))["project"])


def workspace(root: Path) -> dict[str, str]:
    """Each package this workspace builds, by its normalised name, and the
    version it declares."""
    found: dict[str, str] = {}
    for path in [
        root / "pyproject.toml",
        *sorted(root.glob("packages/*/pyproject.toml")),
    ]:
        project = _project(path)
        found[normalize(str(project["name"]))] = str(project["version"])
    return found


def named_by_examples(root: Path) -> set[str]:
    """Every distribution an example's `pyproject.toml` depends on, by its
    normalised name, optional dependencies included."""
    names: set[str] = set()
    for path in sorted(root.glob("examples/*/pyproject.toml")):
        project = _project(path)
        requirements = list(cast(list[object], project.get("dependencies", [])))
        optional = cast(
            dict[str, list[object]], project.get("optional-dependencies", {})
        )
        for group in optional.values():
            requirements.extend(group)
        for requirement in requirements:
            match = NAME.match(str(requirement))
            if match:
                names.add(normalize(match.group(1)))
    return names


def pins(root: Path) -> list[str]:
    """`name==version` for every workspace package an example names."""
    packages = workspace(root)
    wanted = sorted(named_by_examples(root) & set(packages))
    if not wanted:
        raise SystemExit(
            "::error title=No pins::no example depends on a package of this "
            "workspace, so the wait would hold the index to nothing"
        )
    return [f"{name}=={packages[name]}" for name in wanted]


if __name__ == "__main__":
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
    print("\n".join(pins(root)))
