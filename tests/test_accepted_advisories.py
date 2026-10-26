"""The accepted advisories, held to the page that declares them.

`.github/accepted_advisories.toml` is what the weekly dependency audit
subtracts. `SECURITY.md`'s *Advisories against a dependency* is where a reader
learns which advisories we declared, and why. They name the same advisories, in
both directions:

- a row in the file with no line in the section would be an acceptance the
  page does not tell anybody about;
- a line in the section with no row in the file would be a declaration the
  audit does not honour, and the issue would carry it every week.

"Named" is the GHSA identifier, anywhere in the section. So a section that one
day names an advisory it declares *fixed* would need a row too, and this test
would say so the first time, loudly: that is a decision to take then, not a
case to guess at now.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ACCEPTED = ROOT / ".github" / "accepted_advisories.toml"
SECURITY = ROOT / "SECURITY.md"
HEADING = "## Advisories against a dependency"

sys.path.insert(0, str(ROOT / ".github"))
from dependency_audit import read_accepted  # noqa: E402

GHSA = re.compile(r"GHSA(?:-[23456789cfghjmpqrvwx]{4}){3}")


def _section() -> str:
    text = SECURITY.read_text(encoding="utf-8")
    start = text.index(HEADING) + len(HEADING)
    end = text.find("\n## ", start)
    return text[start : end if end != -1 else len(text)]


def _rows() -> set[str]:
    return {row.ghsa for row in read_accepted(ACCEPTED.read_text(encoding="utf-8"))}


def test_every_row_of_the_file_is_declared_in_the_section() -> None:
    missing = _rows() - set(GHSA.findall(_section()))
    assert not missing, (
        f"accepted in {ACCEPTED.name} and not declared in SECURITY.md's "
        f"*Advisories against a dependency*: {sorted(missing)}"
    )


def test_every_advisory_the_section_names_is_a_row_of_the_file() -> None:
    missing = set(GHSA.findall(_section())) - _rows()
    assert not missing, (
        f"declared in SECURITY.md's *Advisories against a dependency* and not "
        f"accepted in {ACCEPTED.name}: {sorted(missing)}"
    )


def test_every_row_names_a_lock_this_repository_has() -> None:
    rows = read_accepted(ACCEPTED.read_text(encoding="utf-8"))
    assert rows
    for row in rows:
        assert (ROOT / row.manifest).is_file(), row


def test_the_section_names_at_least_one_advisory() -> None:
    """The two tests above pass on two empty sets: this is their control."""
    assert GHSA.findall(_section())


# --------------------------------------------------------------------------- #
# A version the page says the locks moved to, held to the locks (#691)
# --------------------------------------------------------------------------- #

#: An entry of the section: `- **<package>, [<GHSA>](…)…`, up to the next one.
_ENTRY = re.compile(r"^- \*\*([A-Za-z0-9_.-]+), \[(GHSA[^\]]+)\]", re.M)
#: The sentence an entry says the locks moved in, folded onto one line.
_MOVED = re.compile(r"moved from ([0-9][^ *]*) to ([0-9][^ *.]*(?:\.[0-9]+)*)")


def _moves() -> list[tuple[str, str, str]]:
    """(package, GHSA, version) for every entry that says its locks moved to a
    version, read from the page."""
    section = _section()
    starts = [match.start() for match in _ENTRY.finditer(section)]
    found: list[tuple[str, str, str]] = []
    for start, end in zip(starts, [*starts[1:], len(section)], strict=True):
        entry = section[start:end]
        head = _ENTRY.match(entry)
        assert head is not None
        moved = _MOVED.search(" ".join(entry.split()))
        if moved is not None:
            found.append((head.group(1), head.group(2), moved.group(2)))
    return found


def _locked(manifest: str, package: str) -> str | None:
    import tomllib

    lock = tomllib.loads((ROOT / manifest).read_text(encoding="utf-8"))
    versions = [p["version"] for p in lock["package"] if p["name"] == package]
    return versions[0] if versions else None


def test_every_lock_is_at_least_at_the_version_the_page_says_it_moved_to() -> None:
    """The page says the locks moved to a version, and the locks are held to
    it: a lock taken back below it reads the sentence false, and this is red.
    A lock above it is not a contradiction, so it passes. The locks are the
    ones the advisory's rows name, so the sentence and the file stay one fact.
    (#691)"""
    from packaging.version import Version

    behind: list[str] = []
    for package, ghsa, version in _moves():
        manifests = sorted(
            row.manifest
            for row in read_accepted(ACCEPTED.read_text(encoding="utf-8"))
            if row.ghsa == ghsa
        )
        assert manifests, f"{ghsa} names no lock in {ACCEPTED.name}"
        for manifest in manifests:
            locked = _locked(manifest, package)
            if locked is None or Version(locked) < Version(version):
                behind.append(f"{manifest}: {package} {locked}, below {version}")
    assert not behind, (
        "SECURITY.md says these locks moved to a version they are below:\n  "
        + "\n  ".join(behind)
    )


def test_the_page_says_at_least_one_lock_moved() -> None:
    """The control: a pattern that read no sentence would hold every lock."""
    assert _moves(), "no entry of the section says its locks moved to a version"
