"""Every name `docs/api.md` lists is a name the code has (#702).

`docs/api.md` is the first of the three levels a public name is read in
(`RELEASING.md`, *Choosing the version*): removing or renaming a name it lists
moves the minor. Nothing held the list to the code. The one test that compared
them, `test_the_api_doc_covers_every_public_assertion`, reads the other way
round and covers only the assertion classes.

**What is read is the list**, the section *What is imported from where*: every
name in backticks there. A name is held if it is in the `__all__` of one of the
packages the section names, or, written as `Class.method` or bare beside its
class, if it is an attribute of a class the section lists. That covers the
four methods of `FileResultStore` it names, which are in no `__all__` because a
method never is. Prose elsewhere in the page names internals on purpose and is
not the list.

**What it does not check:** which package a name is listed under. A name the
section puts under `digline.core` and only `digline.host` exports is held.
"""

from __future__ import annotations

import importlib
import re
from pathlib import Path

API = Path(__file__).resolve().parent.parent / "docs" / "api.md"
PACKAGES = (
    "digline.core",
    "digline.run",
    "digline.report",
    "digline.store",
    "digline.host",
    "digline.wire",
)
_NAME = re.compile(r"`([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)?)`")


def listed() -> list[str]:
    """The names in backticks in *What is imported from where*, in order, less
    the packages themselves, written in full or by their last part (`core`)."""
    text = API.read_text(encoding="utf-8")
    start = text.index("## What is imported from where")
    section = text[start : text.index("\n## ", start + 3)]
    names = [m.group(1) for m in _NAME.finditer(section)]
    packages = {p.rsplit(".", 1)[1] for p in PACKAGES}
    return [
        n
        for n in dict.fromkeys(names)
        if not n.startswith("digline") and n not in packages
    ]


def exported() -> dict[str, object]:
    found: dict[str, object] = {}
    for package in PACKAGES:
        module = importlib.import_module(package)
        for name in getattr(module, "__all__", ()):
            found.setdefault(name, getattr(module, name))
    return found


def unheld(names: list[str], exports: dict[str, object]) -> list[str]:
    classes = [v for n, v in exports.items() if isinstance(v, type) and n in names]
    missing: list[str] = []
    for name in names:
        if "." in name:
            owner, attribute = name.split(".", 1)
            if not (owner in exports and hasattr(exports[owner], attribute)):
                missing.append(name)
        elif name not in exports and not any(hasattr(c, name) for c in classes):
            missing.append(name)
    return missing


def test_the_section_is_read() -> None:
    """The control that the reading reads: names known to be listed are found,
    a method among them."""
    names = listed()
    assert {"Contains", "Suite", "FileResultStore", "read_baseline"} <= set(names)
    assert "FileResultStore.name_table_dir" in names


def test_a_name_the_code_does_not_have_is_caught() -> None:
    """The control that the check can fail: a listed name nobody exports."""
    assert unheld(
        ["Contains", "NoSuchName", "FileResultStore.no_such"], exported()
    ) == [
        "NoSuchName",
        "FileResultStore.no_such",
    ]


def test_every_name_the_api_doc_lists_is_in_the_code() -> None:
    assert unheld(listed(), exported()) == []


def test_the_exit_code_row_for_2_names_every_cause() -> None:
    """The row for `2` in *The exit code* listed five causes when there were
    six: `unpaired` (#642) shipped and the row was not told. It now names each
    by the key `unjudged_causes` carries, read here from `CauseOfTwo` so the
    two cannot part."""
    from typing import get_args

    from digline.core import CauseOfTwo

    text = API.read_text(encoding="utf-8")
    (row,) = [line for line in text.splitlines() if line.startswith("| `2` |")]
    causes = get_args(CauseOfTwo.__value__)
    assert causes
    missing = [cause for cause in causes if f"`{cause}`" not in row]
    assert missing == []
