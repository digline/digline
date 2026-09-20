"""The window before a tag, and every way it must not swallow a real failure.

`tools/image_pins.py` lets the image build during the days when the Dockerfile
pins a version that is not released yet. Anything that lets a build go green on
versions nobody asked for has to be tested from the other side first: what it
must still fail on. So each half is tested beside its opposite — a gate that
substitutes everything passes every "it built" test, and one that substitutes
nothing passes every "it went red" test, and only the pair says this
discriminates.

The three halves the procedure names:

- declared unreleased and absent from the index -> built against the last
  published version, and the summary says which;
- absent and *not* declared -> handed on untouched, so the index wait fails it;
- a pin with a letter in it (`0.17.O`) -> untouched inside the window too,
  because a declaration is about a version, not about a package.
"""

from __future__ import annotations

import re
from pathlib import Path

from image_pins import (
    arg_name,
    decide,
    declared_unreleased,
    newest,
    summary,
)

ROOT = Path(__file__).resolve().parents[1]

#: The four pins as `docker_pins.sh` derives them, at the versions of the
#: window this was written in. Values are arbitrary here: what is under test is
#: the decision, not the release.
PINS = [
    ("digline", "0.17.0"),
    ("digline-anthropic", "0.5.3"),
    ("digline-openai", "0.5.2"),
    ("digline-bedrock", "0.5.1"),
]

PUBLISHED = {
    "digline": {"0.15.3", "0.16.0"},
    "digline-anthropic": {"0.5.1", "0.5.2"},
    "digline-openai": {"0.5.0", "0.5.1"},
    "digline-bedrock": {"0.5.0", "0.5.1"},
}

CHANGELOG = """# Changelog

## Unreleased

### Changed

- Something not attached to a version.

## 0.17.0 — unreleased

## digline-anthropic 0.5.3 — unreleased

## digline-openai 0.5.2 — unreleased

## digline-bedrock — no release, and this is why

## 0.16.0 — 2026-09-19
"""


def _moved(pins, served, changelog=CHANGELOG, **kwargs):
    """The decision, as `{package: version built}` plus the notes."""
    chosen, notes = decide(pins, served, declared_unreleased(changelog), **kwargs)
    return dict(chosen), notes


# --------------------------------------------------------------------------
# What the declaration is, and what it is not


def test_a_bare_heading_declares_the_core():
    assert declared_unreleased("## 0.17.0 — unreleased")["digline"] == "0.17.0"


def test_a_named_heading_declares_that_package():
    declared = declared_unreleased("## digline-anthropic 0.5.3 — unreleased")
    assert declared == {"digline-anthropic": "0.5.3"}


def test_the_section_every_branch_carries_declares_nothing():
    # `## Unreleased` names no version, so it cannot say anything about a pin.
    assert declared_unreleased("## Unreleased\n\n### Changed\n") == {}


def test_a_dated_heading_declares_nothing():
    # This is the release commit: the heading has been dated, the release is
    # under way, and an absence from the index is the short expected red the
    # index wait already handles.
    assert declared_unreleased("## 0.17.0 — 2026-09-21") == {}


def test_a_heading_written_with_a_hyphen_is_not_a_declaration():
    # The repository writes an em dash. Accepting a hyphen too would mean
    # guessing at the shape of a statement whose whole value is being explicit.
    assert declared_unreleased("## 0.17.0 - unreleased") == {}


def test_the_newest_heading_wins_for_a_package():
    twice = "## 0.18.0 — unreleased\n\n## 0.17.0 — unreleased\n"
    assert declared_unreleased(twice) == {"digline": "0.18.0"}


# --------------------------------------------------------------------------
# The window: what gets built instead


def test_a_declared_version_the_index_lacks_is_built_at_the_newest_published():
    built, notes = _moved(PINS, PUBLISHED)
    assert built["digline"] == "0.16.0"
    assert built["digline-anthropic"] == "0.5.2"
    assert built["digline-openai"] == "0.5.1"
    assert any("0.17.0" in note and "0.16.0" in note for note in notes)


def test_a_pin_the_index_already_serves_is_left_alone():
    # digline-bedrock is at 0.5.1, which is published and declared nowhere.
    built, notes = _moved(PINS, PUBLISHED)
    assert built["digline-bedrock"] == "0.5.1"
    assert not any("bedrock" in note for note in notes)


def test_the_summary_names_the_version_that_was_installed():
    _, notes = _moved(PINS, PUBLISHED)
    written = summary(notes, forced=False)
    assert "`digline==0.16.0`" in written
    assert "CHANGELOG.md" in written
    assert "test_the_image_pins_the_versions_this_workspace_declares" in written


def test_a_build_that_moved_nothing_writes_no_summary():
    # Silence is the right answer outside the window: a job that explains
    # itself when there is nothing to explain teaches people to skip the text.
    _, notes = _moved(PINS, {p: {v} for p, v in PINS})
    assert summary(notes, forced=False) == ""


# --------------------------------------------------------------------------
# What must still go red


def test_a_version_no_declaration_covers_is_handed_on_untouched():
    # Nothing in the changelog says 0.99.0 is coming. It may be propagating
    # seconds after a publish, it may never exist; the index wait is what
    # tells those apart, and it only gets the chance if the pin reaches it.
    built, notes = _moved([("digline", "0.99.0")], PUBLISHED)
    assert built["digline"] == "0.99.0"
    assert notes == []


def test_a_mangled_pin_is_not_covered_by_the_declaration_beside_it():
    # `0.17.O` with a letter for a zero, while `0.17.0` is declared unreleased.
    # A declaration is about one exact version, so this is on its own and goes
    # to the wait, which fails naming it.
    built, notes = _moved([("digline", "0.17.O")], PUBLISHED)
    assert built["digline"] == "0.17.O"
    assert notes == []


def test_the_pins_as_written_input_substitutes_nothing():
    built, notes = _moved(PINS, PUBLISHED, forced=True)
    assert built["digline"] == "0.17.0"
    assert notes == []
    assert "as written" in summary(notes, forced=True)


def test_a_first_release_has_nothing_to_fall_back_to_and_says_so():
    # Declared unreleased, and the index serves no release of it at all. There
    # is no older version to build against, so the pin stands and the wait
    # fails it — with the reason written down rather than left to be guessed.
    built, notes = _moved(
        [("digline-mcp", "0.1.0")],
        {"digline-mcp": set()},
        changelog="## digline-mcp 0.1.0 — unreleased",
    )
    assert built["digline-mcp"] == "0.1.0"
    assert any("no release of `digline-mcp` to fall back to" in n for n in notes)


def test_a_prerelease_is_never_what_the_fallback_picks():
    # The image ships what a reader would install. `newest` therefore reads
    # only plain releases, and a package that has nothing else is the case
    # above: no fallback, not a release candidate.
    assert newest({"0.16.0", "0.17.0rc1", "0.17.0.dev1"}) == "0.16.0"
    assert newest({"0.17.0rc1"}) is None
    assert newest({"0.9.0", "0.10.0"}) == "0.10.0"


# --------------------------------------------------------------------------
# The one thing that could drift


def test_every_arg_name_it_derives_is_an_arg_the_dockerfile_declares():
    # `arg_name` derives `DIGLINE_ANTHROPIC_VERSION` from `digline-anthropic`
    # rather than repeating `docker_pins.sh`'s four lines. That is only safe
    # while the derivation matches the file it is deriving for, which is what
    # this reads back — from both ends, the script's package names and the
    # Dockerfile's ARGs.
    script = (ROOT / ".github" / "docker_pins.sh").read_text(encoding="utf-8")
    packages = re.findall(r"^[A-Z_]+ ([a-z0-9-]+)$", script, re.MULTILINE)
    assert packages, "docker_pins.sh no longer lists its packages this way"

    dockerfile = (ROOT / "docker" / "Dockerfile").read_text(encoding="utf-8")
    declared = set(re.findall(r"^ARG ([A-Z_]+)=", dockerfile, re.MULTILINE))
    for package in packages:
        assert arg_name(package) in declared
