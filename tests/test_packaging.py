"""Every distribution that calls itself typed ships the marker that says so.

`Typing :: Typed` is a classifier — a sentence on a PyPI page — and `py.typed`
is the file a type checker actually reads (PEP 561). They are two claims about
the same thing, and nothing kept them together: `digline-mcp` and
`pytest-digline` both classified themselves typed while shipping no marker, so
a consumer importing either under pyright got `reportMissingTypeStubs` for a
package whose every function is annotated.

The failure is invisible from inside this repository, which is why it lasted:
the workspace resolves every package from source, and the source is where the
annotations are. Only somebody installing the wheel sees it — the same shape as
`tests/test_plugin_floors.py`'s trap, and the same reason it is checked here
rather than hoped for.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]

#: Every distribution this repository publishes: the root and the workspace.
DISTRIBUTIONS = [
    ROOT / "pyproject.toml",
    *sorted(ROOT.glob("packages/*/pyproject.toml")),
]

TYPED = "Typing :: Typed"


def manifest(path: Path) -> dict[str, Any]:
    """The whole file. `Any` and not a narrowed shape on purpose: this reads two
    keys out of a document whose schema is somebody else's, and an isinstance
    ladder down to them would be five assertions guarding one fact."""
    return tomllib.loads(path.read_text(encoding="utf-8"))


def named(path: Path) -> str:
    return str(manifest(path)["project"]["name"])


def classifiers(path: Path) -> list[str]:
    return [str(entry) for entry in manifest(path)["project"].get("classifiers", [])]


def shipped_packages(path: Path) -> list[Path]:
    """The directories the wheel is built out of, as hatchling is told them."""
    targets = manifest(path).get("tool", {}).get("hatch", {}).get("build", {})
    wheel = targets.get("targets", {}).get("wheel", {})
    return [path.parent / str(package) for package in wheel.get("packages", [])]


@pytest.mark.parametrize("path", DISTRIBUTIONS, ids=lambda p: p.parent.name)
def test_a_distribution_that_declares_types_ships_the_marker(path: Path) -> None:
    """The classifier is the promise; `py.typed` is what keeps it."""
    if TYPED not in classifiers(path):
        pytest.skip(f"{named(path)} does not claim to be typed")

    shipped = shipped_packages(path)
    assert shipped, f"{named(path)} names no wheel packages to look in"
    for package in shipped:
        marker = package / "py.typed"
        assert marker.is_file(), (
            f"{named(path)} classifies itself {TYPED!r} but {package.name} "
            f"ships no py.typed. A consumer type-checking against the wheel "
            f"gets `reportMissingTypeStubs` and, with library code turned off, "
            f"`Unknown` for every name it imports."
        )


@pytest.mark.parametrize("path", DISTRIBUTIONS, ids=lambda p: p.parent.name)
def test_a_marker_is_never_shipped_without_the_classifier(path: Path) -> None:
    """The other direction, because a PyPI page that does not say `Typed` is a
    page somebody filters past. Two claims, one fact: neither may move alone."""
    for package in shipped_packages(path):
        if (package / "py.typed").is_file():
            assert TYPED in classifiers(path), (
                f"{named(path)} ships {package.name}/py.typed and does not "
                f"classify itself {TYPED!r}"
            )
