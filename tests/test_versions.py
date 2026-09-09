"""One version number, and every place that claims to know it.

`pyproject.toml` is the number the release bumps. Everything else either reads
it or is a record of a version that has already shipped, and the difference
between the two is the whole of this file.

The failure it exists for is small and had already happened: `__version__` in
`digline/__init__.py` said `0.4.0` while `pyproject.toml` said `0.5.0`. Nothing
noticed, because a hand-written copy of a number is only wrong on the days
nobody reads it. That one is now derived from the installed distribution and
cannot drift at all — a claim that *cannot* go stale beats a claim that is
merely gated — and the rest are held here.

The gate has two halves:

- **`LIVE`** names the places that must say the current version, and pins each
  one to `pyproject.toml`. A release that bumps the version and forgets one of
  them fails here.
- **the sweep** reads every version literal in the documented files and demands
  it be either the current version or a registered record. Bump the version and
  every unregistered claim in the repository lights up at once, which is the
  half that keeps this file honest as the repository grows: a new page carrying
  a version number cannot pass without someone deciding which kind it is.

`RECORDED` is therefore an allowance for numbers that are *not* the current
one — "shipped in 0.2.0", a worked example, a third-party pin. Registering the
current version there is refused, because that would be exactly the way to
silence a claim that had gone stale.

Three trees are out of the sweep and stay out. `CHANGELOG.md` is dated history
in every line, and `docs/adr/` is immutable once a decision is accepted:
pinning either to the current release would be asking a record to change.
`tests/` is out because a test fixture names versions for a living — the floor
table in `test_plugin_floors.py` is nothing else — and sweeping them would
register more noise than it caught.
"""

from __future__ import annotations

import re
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

#: Three components, not four: `127.0.0.1` is an address and `0.28.1` is a
#: version, and the lookarounds are what tells them apart.
VERSION = re.compile(r"(?<![\d.])\d+\.\d+\.\d+(?![\d.])")


def current() -> str:
    with (ROOT / "pyproject.toml").open("rb") as handle:
        version = tomllib.load(handle)["project"]["version"]
    assert isinstance(version, str)
    return version


#: Every file the sweep reads. Anything not here is unguarded, so a new page
#: that names a version belongs in this list rather than outside it.
def swept() -> list[Path]:
    files = [
        path
        for path in ROOT.glob("*.md")
        # Written history in every line; and the local file is not committed.
        if path.name not in {"CHANGELOG.md", "CLAUDE.local.md"}
    ]
    files += [ROOT / "docker" / "README.md", ROOT / "docker" / "Dockerfile"]
    files += sorted(p for p in (ROOT / "src").rglob("*.py"))
    files += sorted(p for p in (ROOT / "docs").rglob("*.md") if "adr" not in p.parts)
    files += sorted((ROOT / ".claude").rglob("*.md"))
    return [path for path in files if path.is_file()]


#: file → literal → why it is a record and not a claim about this release.
#: A literal equal to the current version must never appear here; the test
#: below refuses it.
RECORDED: dict[str, dict[str, str]] = {
    "AGENTS.md": {
        "0.4.0": "'the one case in 0.4.0' — the state of a shipped release",
    },
    ".claude/skills/operating-digline/SKILL.md": {
        "0.4.0": "the byte-for-byte mirror of AGENTS.md, gated by test_agents.py",
    },
    "RELEASING.md": {
        "0.1.0": "a worked example of the tag format, with invented numbers",
        "0.1.1": "the same worked example",
        "0.1.3": "the same worked example",
        "0.2.0": "'v0.2.0 was tagged after a check that ran ruff' — what happened",
        "0.3.0": "'skipping it is what v0.3.0 cost' — the same",
        "0.4.0": "'a v0.4.0 rebuild sent an hour after the release' — the same",
    },
    "ROADMAP.md": {
        "0.2.0": "'shipped in 0.2.0' — when a decision landed",
        "0.3.0": "'extended in 0.3.0' — the same",
    },
    "docker/README.md": {
        "0.4.0": "a deliberate example of building an image for a release "
        "that exists — it named 0.3.1 until that turned out never to have "
        "shipped, which is the same class of claim this file gates",
        "0.28.1": "an httpx pin in an example Dockerfile, not a digline version",
        "2.2.3": "a pandas pin in the same example",
    },
    "docker/Dockerfile": {
        "0.3.0": "the plugin versions, pinned to their own pyproject files by "
        "tests/test_docker.py",
    },
    "src/digline/report/pages.py": {
        "0.4.0": "'0.4.0 rendering compare_page' — the state of a shipped release",
    },
}


#: Where the *current* version is written by hand. Each one is pinned, so a
#: release that bumps `pyproject.toml` and stops there fails here by name
#: rather than somewhere downstream.
LIVE: dict[str, str] = {
    "README.md": r"^## Status\s*\n+`([^`]+)`",
    "docker/Dockerfile": r"^ARG DIGLINE_VERSION=(\S+)$",
    "docker/README.md": r"^\| `([\d.]+)` \| that version of digline",
}


def test_the_live_claims_say_what_pyproject_says() -> None:
    version = current()
    for name, pattern in LIVE.items():
        text = (ROOT / name).read_text(encoding="utf-8")
        found = re.search(pattern, text, re.M)
        assert found is not None, (
            f"{name} no longer has the line this gate reads (pattern "
            f"{pattern!r}). If it moved, move the pattern with it rather than "
            "deleting the entry: the number in that line is written by hand."
        )
        assert found.group(1) == version, (
            f"{name} says {found.group(1)} and pyproject.toml says {version}. "
            "The release bumps pyproject; this one is written by hand and has "
            "fallen behind."
        )


def test_the_minor_tag_follows_the_release() -> None:
    """The image's tag table also promises a `<major>.<minor>` tag, and that
    one is a different shape from the rest — it went stale unnoticed, reading
    `0.4` after 0.5.0 had shipped."""
    version = current()
    minor = ".".join(version.split(".")[:2])
    text = (ROOT / "docker" / "README.md").read_text(encoding="utf-8")
    found = re.search(r"^\| `([\d.]+)` \| the newest patch on that minor", text, re.M)
    assert found is not None, "docker/README.md has no minor-tag row"
    assert found.group(1) == minor, (
        f"docker/README.md documents the minor tag `{found.group(1)}` while "
        f"this workspace is at {version}, whose minor tag is `{minor}`"
    )


def test_no_version_literal_is_left_unaccounted_for() -> None:
    """The sweep. Every number is the current one or a registered record."""
    version = current()
    unaccounted: list[str] = []
    for path in swept():
        name = path.relative_to(ROOT).as_posix()
        allowed = RECORDED.get(name, {})
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            for literal in VERSION.findall(line):
                if literal == version or literal in allowed:
                    continue
                unaccounted.append(f"{name}:{line_number}: {literal} — {line.strip()}")

    assert not unaccounted, (
        "these version literals are neither the current release "
        f"({version}) nor registered records:\n  "
        + "\n  ".join(unaccounted)
        + "\n\nEach one is a decision. If the line claims what digline is at "
        "*now*, update it — and add it to LIVE so the next release cannot "
        "forget it. If it records a version that has already shipped, or is "
        "not a digline version at all, add it to RECORDED with the reason. If "
        "the number adds nothing to the sentence, the best fix is to take it "
        "out: a claim that cannot go stale beats a gated one."
    )


def test_a_record_may_not_be_the_current_version() -> None:
    """Otherwise the allowance becomes the way to hide a claim that has gone
    stale: register today's number as "history" and the sweep stops looking."""
    version = current()
    guilty = [
        f"{name}: {why}"
        for name, entries in RECORDED.items()
        for literal, why in entries.items()
        if literal == version
    ]
    assert not guilty, (
        f"RECORDED registers {version}, which is the current release:\n  "
        + "\n  ".join(guilty)
        + "\nA record is a version that has already been superseded. Move "
        "these to LIVE, or leave them to the sweep, which accepts the current "
        "version everywhere."
    )


def test_every_recorded_file_is_swept_and_every_literal_is_still_there() -> None:
    """An allowance for a line that no longer exists is an allowance nobody
    can see is dead — and the next version literal added to that file inherits
    it."""
    swept_names = {path.relative_to(ROOT).as_posix() for path in swept()}
    stale: list[str] = []
    for name, entries in RECORDED.items():
        if name not in swept_names:
            stale.append(f"{name} is registered but not swept")
            continue
        found = set(VERSION.findall((ROOT / name).read_text(encoding="utf-8")))
        stale += [
            f"{name} no longer contains {literal} ({why})"
            for literal, why in entries.items()
            if literal not in found
        ]
    assert not stale, "RECORDED has entries nothing matches:\n  " + "\n  ".join(stale)


# --------------------------------------------------------------------------- #
# What the number is for
# --------------------------------------------------------------------------- #


def test_dunder_version_is_the_installed_version() -> None:
    """Derived, not written: this is the copy that was already false."""
    from importlib.metadata import version as installed

    import digline

    assert digline.__version__ == installed("digline")


def test_the_cli_prints_the_version_and_exits_zero() -> None:
    """Through the real entry point, because `action="version"` exits inside
    argparse and a test that called `build_parser()` alone would not see the
    exit code the shell does."""
    import digline

    done = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "digline.cli", "--version"],
        capture_output=True,
        text=True,
        check=False,
        cwd=ROOT,
    )
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == f"digline {digline.__version__}"


@pytest.mark.parametrize("flag", ["--version", "-h"])
def test_the_top_level_flags_need_no_subcommand(flag: str) -> None:
    """`digline --version` with no command after it: the flag sits on the top
    parser, above `required=True` on the subcommands."""
    done = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "digline.cli", flag],
        capture_output=True,
        text=True,
        check=False,
        cwd=ROOT,
    )
    assert done.returncode == 0, done.stderr
