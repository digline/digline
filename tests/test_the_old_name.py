"""`Quoted` is `Written`, and the old name stands only where it is declared.

`digline.core.Quoted` was renamed `Written` with no alias. A search of the
repository for the old name by whole word does not answer zero, and zero is
the wrong number: six lines keep it, each for a reason in one of three
classes, and `KEPT` declares them.

- **released history**, which is not rewritten: the changelog entry of a
  released version and two passages of accepted records that describe the
  tree of their time;
- **the English word**, not the class: two comments;
- **the changelog line that announces the rename**, which has to name the old
  name for whoever reads it against the last release.

The count is fixed at six and red both ways: a seventh line is a use of the
class that came back or a word nobody declared, and a declared line that is
gone is a declaration that no longer says anything.

**Whole word, by the names gate's derivation** (`named_in` in
`packages/digline-mcp/tests/test_names_gate.py`): a name is continued only by
a letter or a digit touching it, as `str.isalnum` reads them, and bounded by
anything else. So `Quoted.of`, `` `Quoted` `` and `(digline.core.Quoted)` are
the name, and `QuotedText` or `Quoted2` are not.

**This file is left out of the search**, by its own path: its table has to
name the old name to declare where it stays.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import NamedTuple

ROOT = Path(__file__).resolve().parents[1]
OLD = "Quoted"
THIS = Path(__file__).resolve().relative_to(ROOT).as_posix()


class Kept(NamedTuple):
    path: str
    #: Text the line carries, so a declared line is found wherever the file
    #: around it moves.
    excerpt: str
    reason: str


HISTORY = "released history, not rewritten"
ENGLISH = "the English word, not the class"
ANNOUNCED = "the changelog line that announces the rename"

KEPT: tuple[Kept, ...] = (
    Kept(
        "CHANGELOG.md",
        "exception carries it as a field (`digline.core.Quoted`)",
        HISTORY,
    ),
    Kept(
        "docs/adr/0043-a-message-digline-did-not-write.md",
        "wraps the `OSError` of its own reads in a `Quoted`",
        HISTORY,
    ),
    Kept(
        "docs/adr/0054-the-names-a-server-lets-out.md",
        "refusal holds that refusal's object, in `Quoted.cause`",
        HISTORY,
    ),
    Kept(
        ".github/mcp_registry.py",
        "Quoted from `internal/validators/registries/pypi.go`",
        ENGLISH,
    ),
    Kept(
        ".github/workflows/publish.yml",
        "# names it. Quoted, so an empty value",
        ENGLISH,
    ),
    Kept(
        "CHANGELOG.md",
        "**`digline.core.Quoted` is now `Written`, with no alias.**",
        ANNOUNCED,
    ),
)


def stands_in(text: str, name: str) -> bool:
    """Whether `name` stands in `text` as a name: the names gate's rule."""
    start = text.find(name)
    while start != -1:
        end = start + len(name)
        before = text[start - 1] if start > 0 else ""
        after = text[end] if end < len(text) else ""
        if not before.isalnum() and not after.isalnum():
            return True
        start = text.find(name, start + 1)
    return False


def lines_naming(name: str, root: Path = ROOT) -> list[tuple[str, str]]:
    """Every `(path, line)` of a tracked text file where `name` stands as a
    name, this file left out."""
    tracked = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z"],
        check=True,
        capture_output=True,
    ).stdout.split(b"\0")
    found: list[tuple[str, str]] = []
    for raw in tracked:
        path = raw.decode()
        if not path or path == THIS:
            continue
        try:
            text = (root / path).read_text(encoding="utf-8")
        except (UnicodeDecodeError, FileNotFoundError, IsADirectoryError):
            continue
        found.extend(
            (path, line) for line in text.splitlines() if stands_in(line, name)
        )
    return found


def unexplained(
    found: list[tuple[str, str]], kept: tuple[Kept, ...] = KEPT
) -> list[str]:
    """A line found that no declaration covers, and a declaration no line meets."""
    problems: list[str] = []
    met: set[Kept] = set()
    for path, line in found:
        covering = [k for k in kept if k.path == path and k.excerpt in line]
        if covering:
            met.update(covering)
        else:
            problems.append(f"{path}: names {OLD} and is not declared: {line.strip()}")
    problems.extend(
        f"{k.path}: declared ({k.reason}) and no longer names {OLD}: {k.excerpt}"
        for k in kept
        if k not in met
    )
    return problems


def test_the_old_name_stands_only_where_it_is_declared() -> None:
    found = lines_naming(OLD)
    assert not unexplained(found), "\n".join(unexplained(found))
    assert len(found) == len(KEPT) == 6


def test_the_declared_lines_are_six_in_three_classes() -> None:
    assert len(KEPT) == 6
    assert {k.reason for k in KEPT} == {HISTORY, ENGLISH, ANNOUNCED}


def test_the_search_finds_a_name_it_knows() -> None:
    """The control in the same derivation: the new name is found, in its own
    module, so a search that answers six is a search that looks."""
    found = lines_naming("Written")
    assert any(path == "src/digline/core/refused.py" for path, _ in found)
    assert len(found) > 6


def test_the_matcher_is_the_names_gates() -> None:
    assert stands_in(f"`{OLD}.of(exc)`", OLD)
    assert stands_in(f"(digline.core.{OLD})", OLD)
    assert stands_in(f"_{OLD}", OLD)
    assert not stands_in(f"{OLD}Text", OLD)
    assert not stands_in(f"{OLD}2", OLD)
    assert not stands_in(f"Un{OLD.lower()}", OLD)


def test_a_seventh_line_and_a_missing_one_are_both_red() -> None:
    """Both directions, on a listing built here rather than the tree."""
    found = [(k.path, f"... {k.excerpt} ...") for k in KEPT]
    assert unexplained(found) == []
    seventh = [*found, ("src/digline/core/refused.py", f"class {OLD}:")]
    assert unexplained(seventh) == [
        f"src/digline/core/refused.py: names {OLD} and is not declared: class {OLD}:"
    ]
    missing = found[1:]
    assert unexplained(missing) == [
        f"{KEPT[0].path}: declared ({KEPT[0].reason}) and no longer names {OLD}: "
        f"{KEPT[0].excerpt}"
    ]
