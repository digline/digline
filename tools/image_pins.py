"""Which versions the image build installs, when the pinned ones are not out yet.

`docker/Dockerfile` pins the four versions this workspace declares, and
`tests/test_docker.py` makes that mandatory: the moment `pyproject.toml` moves
to a new version, the image's `ARG`s move with it. So between the commit that
bumps the version and the tag that releases it, the Dockerfile names versions
**PyPI does not serve yet** — and every build of that image fails at the index
wait, for days, through no fault of the tree. That is a red nobody can act on,
and a red nobody can act on is a red nobody reads.

The short window between the tag and `publish` is a different thing and is
already documented (RELEASING.md, *After the tag*): there the CHANGELOG heading
is **dated**, the release is under way, and the red is minutes long and
self-healing. This file is about the long one, where the heading still says
`unreleased`.

**What this does not do is skip.** A build that is skipped says nothing about
an image whose Dockerfile is being edited — and the window is exactly when it
is being edited. So inside the window the image is still built, against **the
last versions the index actually serves**, and the summary says so. What that
build stops covering is the pin itself; the pin is covered twice over anyway,
by `tests/test_docker.py` in the tree and by the real build at release.

**The window is read from a declaration, never guessed from the index.** The
CHANGELOG heading `## 0.17.0 — unreleased` is a statement by the author that
this version is not out yet, and it is already machine-read elsewhere (the home
capture reads the newest *dated* heading, RELEASING.md). Asking only *is it on
PyPI?* would answer yes to the same question for a pin that is simply wrong:
`0.17.O`, with a letter for a zero, is not on the index and never will be. Such
a pin is not declared anywhere, so it is not in a window, so it goes red — in
the window as outside it. That is the discrimination this file exists for, and
`tests/test_image_pins.py` tests each half of it.

Nothing here decides a red. A pin that is not substituted is handed on
unchanged to `.github/await_index.py`, which is the one thing in this
repository with a deadline and the one thing that fails.

Usage:

    python3 tools/image_pins.py --manifest /tmp/pins.txt --out /tmp/pins.txt

Environment:

    FORCE_REAL_PINS   `true` builds the pins exactly as written, window or not
    INDEX             passed through to `.github/await_index.py`
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: `## 0.17.0 — unreleased` and `## digline-anthropic 0.5.3 — unreleased`, the
#: two shapes RELEASING.md gives a heading on a branch ahead of its tag. The
#: em dash is the repository's, and it is required: a heading written with a
#: hyphen is not the declaration this reads, and is better failed than guessed.
#: `## Unreleased`, the section every branch carries, has no version and is
#: deliberately not a declaration about any pin.
DECLARATION = re.compile(
    r"^##[ \t]+(?:(?P<package>[a-z][a-z0-9-]*)[ \t]+)?"
    r"(?P<version>\d+\.\d+\.\d+)[ \t]+—[ \t]+unreleased[ \t]*$",
    re.MULTILINE,
)

#: A heading with no package name is the core's, the way the changelog writes it.
CORE = "digline"


def declared_unreleased(changelog: str) -> dict[str, str]:
    """The versions the changelog says are not released, by package.

    One per package: a second heading for the same package would mean two
    unreleased versions of one thing, which the release procedure cannot
    produce. The first wins, since the file is newest first.
    """
    declared: dict[str, str] = {}
    for match in DECLARATION.finditer(changelog):
        package = match.group("package") or CORE
        declared.setdefault(package, match.group("version"))
    return declared


def arg_name(package: str) -> str:
    """`digline-anthropic` -> `DIGLINE_ANTHROPIC_VERSION`, the Dockerfile's ARG.

    Derived rather than listed, so this cannot drift from `docker_pins.sh`'s
    four lines. `tests/test_image_pins.py` checks that every name it derives is
    an `ARG` the Dockerfile actually declares, which is what makes deriving it
    safe.
    """
    return package.upper().replace("-", "_") + "_VERSION"


def _ordered(version: str) -> tuple[int, ...] | None:
    """`0.16.0` -> `(0, 16, 0)`; anything else -> `None`, and is not a candidate.

    Only the three-number shape is comparable here. A pre-release or a local
    version is a thing this fallback must never pick on its own: the image ships
    what a reader would install, and that is a plain release.
    """
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        return None
    return tuple(int(part) for part in version.split("."))


def newest(versions: set[str]) -> str | None:
    """The highest plain release among these, or `None` if there is not one."""
    candidates = [(order, v) for v in versions if (order := _ordered(v))]
    if not candidates:
        return None
    return max(candidates)[1]


def decide(
    pins: list[tuple[str, str]],
    served: dict[str, set[str]],
    declared: dict[str, str],
    *,
    forced: bool = False,
) -> tuple[list[tuple[str, str]], list[str]]:
    """The versions to build with, and a line for each one that was moved.

    A pin is moved only when all four of these hold: it is not served, the
    changelog declares *that exact version* unreleased, the index has some
    other release of the package to fall back to, and the build was not asked
    for the pins as written. Otherwise the pin is handed on untouched, and
    whether that is fine or fatal is the index wait's question, not this one.
    """
    chosen: list[tuple[str, str]] = []
    notes: list[str] = []
    for package, version in pins:
        available = served.get(package, set())
        if forced or version in available:
            chosen.append((package, version))
            continue
        if declared.get(package) != version:
            # Either nothing is declared for this package, or something else
            # is. A pin that no declaration covers is on its own: it may be
            # propagating, it may be a typo, and the wait is what tells them
            # apart. Nothing is substituted under it.
            chosen.append((package, version))
            continue
        fallback = newest(available)
        if fallback is None:
            # Declared unreleased and the index has no release of it at all —
            # a package whose first release this is. There is no older version
            # to build against, and inventing one is worse than the red.
            notes.append(
                f"`{package}=={version}` is declared unreleased and the index "
                f"serves no release of `{package}` to fall back to, so the pin "
                "stands as written."
            )
            chosen.append((package, version))
            continue
        chosen.append((package, fallback))
        notes.append(
            f"`{package}=={version}` is declared unreleased in `CHANGELOG.md` "
            f"and the index does not serve it, so this build installed "
            f"`{package}=={fallback}`, the newest it does serve."
        )
    return chosen, notes


def summary(notes: list[str], forced: bool) -> str:
    """What the job says about itself, in the words a reader needs.

    A build that installed something other than what the Dockerfile says has to
    declare it where the result is read, or the green is a lie by omission.
    """
    if forced:
        return (
            "### The image was built with the pins as written\n\n"
            "`image_pins_as_written` was set, so no version was substituted "
            "and an absence from the index is a failure.\n"
        )
    if not notes:
        return ""
    return (
        "### The image was built against published versions\n\n"
        + "".join(f"- {note}\n" for note in notes)
        + "\nThis is the window between the version bump and the tag "
        "(RELEASING.md, *The window before the tag*). What this build no longer "
        "covers is the pin itself: that is held by `tests/test_docker.py::"
        "test_the_image_pins_the_versions_this_workspace_declares` in the "
        "tree, and built for real by `docker-publish.yml` at release.\n"
    )


def _append(variable: str, text: str) -> None:
    """Append to one of the runner's files, if we are on a runner at all."""
    path = os.environ.get(variable)
    if not path or not text:
        return
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(text)


def main(argv: list[str]) -> int:
    manifest = out = None
    changelog = ROOT / "CHANGELOG.md"
    rest = argv[1:]
    while rest:
        argument = rest.pop(0)
        if argument in {"--manifest", "--out", "--changelog"} and rest:
            value = rest.pop(0)
            if argument == "--manifest":
                manifest = Path(value)
            elif argument == "--out":
                out = Path(value)
            else:
                changelog = Path(value)
        else:
            print(
                f"::error title=Not an argument this takes::{argument!r}; "
                "usage: --manifest PATH [--out PATH] [--changelog PATH]",
                file=sys.stderr,
            )
            return 1

    if manifest is None:
        print(
            "::error title=No manifest to read::this needs the pins "
            "`docker_pins.sh` derived, and has nothing to decide about without "
            "them.",
            file=sys.stderr,
        )
        return 1

    # The one reader of the index in this repository — headers, variants,
    # edges and all. Imported here rather than at the top so that deciding
    # stays testable without a network or a server in front of it.
    sys.path.insert(0, str(ROOT / ".github"))
    from await_index import Absent, parse_pin, served_versions  # noqa: PLC0415

    pins = [parse_pin(pin) for pin in manifest.read_text(encoding="utf-8").split()]
    forced = os.environ.get("FORCE_REAL_PINS", "").lower() == "true"

    served: dict[str, set[str]] = {}
    for package, _ in pins:
        if package in served or forced:
            continue
        try:
            served[package] = served_versions(package)
        except Absent as absent:
            # No page at all, or no way to reach one. Not knowing is not the
            # same as knowing it is absent, and either way this substitutes
            # nothing: the pin stands and the wait decides.
            print(f"the index says nothing about {package}: {absent}")
            served[package] = set()

    declared = declared_unreleased(changelog.read_text(encoding="utf-8"))
    chosen, notes = decide(pins, served, declared, forced=forced)

    print("this build installs:")
    for (package, version), (_, asked) in zip(chosen, pins, strict=True):
        moved = "" if version == asked else f"   (the Dockerfile says {asked})"
        print(f"  {package}=={version}{moved}")
    for note in notes:
        print(f"note: {note}")

    if out is not None:
        out.write_text(
            "".join(f"{package}=={version}\n" for package, version in chosen),
            encoding="utf-8",
        )

    _append(
        "GITHUB_OUTPUT",
        "build_args<<IMAGE_PINS\n"
        + "".join(f"{arg_name(p)}={v}\n" for p, v in chosen)
        + "IMAGE_PINS\n",
    )
    _append("GITHUB_STEP_SUMMARY", summary(notes, forced))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
