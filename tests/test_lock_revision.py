"""Every `uv.lock` keeps the `revision` declared for it here, and says so by name.

The `revision` at the top of a lock is the format of the `uv` that last wrote
it, not something this repository chose: a `uv` that rewrites a lock writes its
own number. And nothing here fixes the tool. No `pyproject.toml` sets
`required-version`, `setup-uv` is pinned by commit and given no `version`, so
CI takes the newest, and a person relocks with whatever is installed. So a lock
regenerated for another reason can change format on the way, in a diff that
reads as one more line.

Observed, each one a rewrite by a different `uv`:
- 2026-10-26, Dependabot moved every lock from 3 to 5 (`34beafe8`, `ec0c935d`);
- 2026-10-26, the nltk move by hand moved the root and `llamaindex` from 5 back
  to 3 (`246dcd84`), and the root has kept 3 since;
- 2026-10-27, `uv` 0.11.14 moved the example locks from 5 to 3 while they were
  relocked to digline 0.35.0, caught before the commit and redone with
  `uv` 0.13.6 (`519f5c5a`, which took `llamaindex` back to 5);
- 2026-10-28, `uvx --from uv uv` moved the root from 3 to 5 while it was
  relocked for pytest-digline 0.5.0, caught before the commit.

**The table records a state, not a decision.** The root at 3 and the seven
examples at 5 is nobody's choice: it is which `uv` ran last on each. Nothing
here says the mix is wanted. A lock with no row is red, so a new one is
recorded and not assumed. RELEASING.md names this test where the locks are
regenerated: step 5 of *Before the tag: moving the number*, and *Before the
tag: the home capture*.

**Normalising every lock to one `revision` is owed, and not done here.** A
`uv` rewrites a lock only when something in it changes (measured 2026-10-28:
`uv` 0.13.6 on an unchanged root lock wrote nothing), and the format moves with
that rewrite. So a normalisation made before the tool is fixed lasts until the
next relock by another `uv`. It goes with the pin, after the release chain of
0.35.0.

**The cause is that nothing fixes the tool**, as above: no `required-version`,
and `setup-uv` pinned by commit with no `version`, so CI takes the newest `uv`.
Fixing it is the repair. **This test is the alarm, not the repair**: it says
which lock moved, and the pin, made after the chain, is what stops it moving.
"""

from __future__ import annotations

import subprocess
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

_DEPENDABOT = (
    "5 since Dependabot's bump of the examples group (ec0c935d, 2026-10-26), "
    "the format of the uv that wrote it; every relock since kept it"
)

#: The lock, its `revision`, and why it reads that.
REVISIONS: dict[str, tuple[int, str]] = {
    "uv.lock": (
        3,
        "3 since the nltk move by hand (246dcd84, 2026-10-26) rewrote "
        "Dependabot's 5 (34beafe8) with a uv that writes 3; the bump to 0.35.0, "
        "digline-mcp 0.7.0 and pytest-digline 0.5.0 relocked it at 3",
    ),
    "examples/classifier/uv.lock": (5, _DEPENDABOT),
    "examples/langchain/uv.lock": (5, _DEPENDABOT),
    "examples/llamaindex/uv.lock": (
        5,
        "5 from Dependabot (ec0c935d), 3 after the nltk move by hand (246dcd84), "
        "and 5 again since the relock to digline 0.35.0 with uv 0.13.6 "
        "(519f5c5a, 2026-10-27)",
    ),
    "examples/mcp-tools/uv.lock": (5, _DEPENDABOT),
    "examples/prompt-first/uv.lock": (5, _DEPENDABOT),
    "examples/quickstart-toml/uv.lock": (5, _DEPENDABOT),
    "examples/rag/uv.lock": (5, _DEPENDABOT),
}


def _tracked_locks() -> list[str]:
    """Git is the authority for which locks are committed, as it is for the
    example caps: a lock left by a local experiment is not one of them."""
    listed = subprocess.run(  # noqa: S603
        ["git", "ls-files", "-z", "--", "uv.lock", "*/uv.lock"],  # noqa: S607
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if listed.returncode != 0:
        pytest.skip("not a git checkout, so no lock here can be called committed")
    return sorted(entry for entry in listed.stdout.split("\0") if entry)


def revision_mismatches(root: Path, declared: dict[str, tuple[int, str]]) -> list[str]:
    """One sentence per lock that does not read its declared `revision`,
    naming the file."""
    wrong: list[str] = []
    for name, (expected, reason) in sorted(declared.items()):
        path = root / name
        if not path.is_file():
            wrong.append(f"{name}: declared here and not in the tree")
            continue
        found = tomllib.loads(path.read_text(encoding="utf-8")).get("revision")
        if found != expected:
            wrong.append(
                f"{name}: revision {found!r}, declared {expected} ({reason}). "
                "A uv other than the one that wrote it has rewritten it: relock "
                "with that uv, or change the row here and say why"
            )
    return wrong


def test_every_committed_lock_has_a_row() -> None:
    tracked = _tracked_locks()
    # The positive control: the root lock is committed, so an empty listing is
    # a broken query and not a tree with no locks.
    assert "uv.lock" in tracked, tracked
    assert sorted(REVISIONS) == tracked, (
        "a lock with no row, or a row with no lock: "
        f"{sorted(set(tracked) ^ set(REVISIONS))}"
    )


def test_every_lock_reads_its_declared_revision() -> None:
    assert not revision_mismatches(ROOT, REVISIONS), "\n".join(
        revision_mismatches(ROOT, REVISIONS)
    )


def test_a_lock_moved_to_another_revision_is_named(tmp_path: Path) -> None:
    """The control: a copy of a lock moved to another format is red, and the
    sentence names the file."""
    name = "uv.lock"
    text = (ROOT / name).read_text(encoding="utf-8")
    assert "\nrevision = 3\n" in text
    moved = text.replace("\nrevision = 3\n", "\nrevision = 5\n", 1)
    (tmp_path / name).write_text(moved, encoding="utf-8")
    wrong = revision_mismatches(tmp_path, {name: REVISIONS[name]})
    assert len(wrong) == 1
    assert wrong[0].startswith(f"{name}: revision 5, declared 3")
