"""When each method or attribute a plugin calls arrived, read from git (#702).

`tools/plugin_calls.py` lists each `(module, class, attribute)` a shipped
plugin reads on something digline gives it. This dates each one, and its
output is what `CALLED` in `tests/test_plugin_floors.py` holds.

For every release tag `v*`, in version order, every `src/digline/**.py` at
that tag is parsed with `ast`, read with `git show`, nothing checked out. An
entry is present at a tag when the class of that name, **in the module that
defines it today**, defines the attribute in its own body: a `def`, an
annotated field or an assignment. A module's attribute, class `""`, is a
top-level `def` or assignment in that module. The date is the first tag from
which the entry is present at every later tag.

So a class that moved is dated to the release that moved it, the rule
`INTRODUCED` applies to an imported name; the tag at which the attribute is
first present in any module is printed beside it. An entry no tag answers
is printed `undated`, with the reason, and is never estimated.

**What it does not see.** Presence is by name: an attribute that had the same
name and meant something else at an earlier tag is read as the same one. And
it needs the tags, which a shallow clone does not have.

    uv run python tools/plugin_call_dates.py

prints one line per entry: the key, the version, and a note.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from plugin_calls import scan  # noqa: E402

Key = tuple[str, str, str]


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(ROOT), *args], capture_output=True, text=True, check=True
    ).stdout


def _version(tag: str) -> tuple[int, ...]:
    return tuple(int(part) for part in tag.removeprefix("v").split("."))


def release_tags() -> list[str]:
    tags = _git("tag", "-l", "v*").split()
    return sorted(
        (t for t in tags if t.removeprefix("v").replace(".", "").isdigit()),
        key=_version,
    )


def _defined(body: list[ast.stmt]) -> set[str]:
    names: set[str] = set()
    for node in body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            names.add(node.name)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
        elif isinstance(node, ast.Assign):
            names.update(t.id for t in node.targets if isinstance(t, ast.Name))
    return names


def surface(tag: str) -> dict[tuple[str, str], set[str]]:
    """`{(module, class or ""): the names it defines in its own body}`."""
    found: dict[tuple[str, str], set[str]] = {}
    for path in _git("ls-tree", "-r", "--name-only", tag, "--", "src/digline").split():
        if not path.endswith(".py"):
            continue
        module = path.removeprefix("src/").removesuffix(".py").replace("/", ".")
        module = module.removesuffix(".__init__")
        try:
            tree = ast.parse(_git("show", f"{tag}:{path}"))
        except SyntaxError:
            continue
        found[(module, "")] = _defined(tree.body)
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                found.setdefault((module, node.name), set()).update(_defined(node.body))
    return found


def date(entries: list[Key]) -> list[tuple[Key, str | None, str]]:
    """Each entry with its version, or None and the reason, and a note."""
    tags = release_tags()
    here: dict[Key, list[bool]] = {e: [] for e in entries}
    anywhere: dict[Key, list[bool]] = {e: [] for e in entries}
    for tag in tags:
        seen = surface(tag)
        for entry in entries:
            module, cls, attr = entry
            here[entry].append(attr in seen.get((module, cls), set()))
            anywhere[entry].append(
                any(
                    attr in names
                    for (m, c), names in seen.items()
                    if c == cls and (cls or m == module)
                )
            )
    out: list[tuple[Key, str | None, str]] = []
    for entry in entries:
        marks = here[entry]
        if not any(marks):
            note = "in no release tag"
            if any(anywhere[entry]):
                note += f"; in another module from {tags[anywhere[entry].index(True)]}"
            out.append((entry, None, note))
            continue
        last_absent = max((i for i, m in enumerate(marks) if not m), default=-1)
        if last_absent == len(tags) - 1:
            out.append((entry, None, f"absent at {tags[-1]}"))
            continue
        first = marks.index(True)
        notes: list[str] = []
        gaps = [tags[i] for i in range(first, len(tags)) if not marks[i]]
        if gaps:
            notes.append("absent at " + ", ".join(gaps))
        elsewhere = tags[anywhere[entry].index(True)]
        if elsewhere != tags[first]:
            notes.append(f"in another module from {elsewhere}")
        out.append((entry, tags[last_absent + 1].removeprefix("v"), "; ".join(notes)))
    return out


def main(argv: list[str]) -> int:
    if argv:
        print("usage: plugin_call_dates.py", file=sys.stderr)
        return 64
    _, _, defined = scan()
    entries = sorted({(m, c, a) for (_, m, c, a) in defined})
    for entry, version, note in date(entries):
        print(f"{entry}  {version or 'undated'}  {note}".rstrip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
