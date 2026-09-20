"""The gate on the actions the workflows use: a commit, and the version it is.

A tag is a name the other repository can move. `actions/checkout@v5` is
whatever that repository decides `v5` means on the morning the job runs, and a
branch is worse; what runs here publishes to PyPI and signs a release, so it
has to be a commit nobody can change under us. Every `uses:` in
`.github/workflows/` is a 40-character commit sha, and the exact version that
commit is tagged with is written after it, because a sha alone says nothing to
a reader and nothing to the person updating it:

    uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1

Refused:

- a tag (`@v7`), a branch (`@main`), or a sha shorter than 40 characters;
- a pin with no comment after it, or a comment that does not name an exact
  version — `# v7.0.1`, never `# v7`. A major is a tag that moves, so beside a
  fixed commit it says nothing about what is pinned there. A prerelease after
  the patch is a version (`# v3.0.0-beta.6`).

A local action (`uses: ./…`) and a container (`uses: docker://…`) are not
pinned this way and are left alone.

`tests/test_actions_pinned.py` runs this over this repository and over each
way it must fail. digline.dev has the same gate, as `tools/check-actions.py`,
and RUNBOOK.md there has the procedure for updating a pin.
"""

from __future__ import annotations

import re
from pathlib import Path

# `uses:` as a workflow writes it, and whatever follows on the line.
USES = re.compile(r"^\s*(?:-\s*)?uses:\s*(?P<ref>\S+)\s*(?P<rest>.*?)\s*$")
SHA = re.compile(r"\A[0-9a-f]{40}\Z")
# major.minor.patch, and whatever a repository appends to it.
VERSION = re.compile(r"\A#\s*v?\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.]+)?\s*$")
LOCAL = ("./", "docker://")
WORKFLOWS = Path(".github/workflows")


def workflows(root: Path) -> list[Path]:
    """Every workflow of the repository, in a fixed order."""
    folder = root / WORKFLOWS
    return sorted(p for p in folder.glob("*") if p.suffix in (".yml", ".yaml"))


def problems(root: Path) -> list[str]:
    """What is wrong with the actions this repository uses; [] is a pass."""
    found: list[str] = []
    for path in workflows(root):
        where = path.relative_to(root).as_posix()
        lines = path.read_text(encoding="utf-8").splitlines()
        for number, line in enumerate(lines, start=1):
            match = USES.match(line)
            if not match:
                continue
            ref, rest = match.group("ref"), match.group("rest")
            if ref.startswith(LOCAL):
                continue
            action, _, version = ref.partition("@")
            if not SHA.match(version):
                at = f"{version!r}" if version else "nothing"
                found.append(
                    f"{where}:{number}: {action} is used at {at}, and an action "
                    "is used at a full 40-character commit — a tag and a "
                    "branch move under us"
                )
            elif not VERSION.match(rest):
                found.append(
                    f"{where}:{number}: {action} is pinned, and the exact "
                    f"version it is at is not written after it — {rest!r}, "
                    "wanted a comment naming the tag, as in `# v7.0.1`; a "
                    "major on its own, `# v7`, is a tag that moves"
                )
    return found


def used(root: Path) -> list[str]:
    """Every `uses:` of the repository, as written."""
    refs: list[str] = []
    for path in workflows(root):
        for line in path.read_text(encoding="utf-8").splitlines():
            match = USES.match(line)
            if match and not match.group("ref").startswith(LOCAL):
                refs.append(match.group("ref"))
    return refs


if __name__ == "__main__":  # pragma: no cover - a hand's run, tests are the gate
    import sys

    root = Path(__file__).resolve().parents[1]
    found = problems(root)
    for problem in found:
        print(f"actions: {problem}", file=sys.stderr)
    if not found:
        count = len(used(root))
        print(
            f"actions: {count} action(s), every one at a full commit with its version"
        )
    raise SystemExit(1 if found else 0)
