"""The JSON contract as it stands, diffed between two references (#709).

The delta-pass lists the keys of the JSON contract a release added or moved
(`RELEASING.md`, *New public surface is three kinds of thing*). The contract is
assembled in `src/digline/wire/contract.py` from three tables: `_BASE`, and
`_ADDED` and `_ADDED_WORDS` beside it. A bump of `OUTPUT_VERSION` folds the
last two into the first and empties them, so a diff of any one table depends
on whether a fold happened between the two references, and somebody had to
choose which table to diff.

This diffs none of them. It reads, in each tree, the contract `_lines(_SHAPES)`
derives from all three: the line a failing contract test prints, one per key,
`name.key: types`, with `?` after the key where the key may be absent. A fold
changes nothing it reads.

    uv run python tools/contract_diff.py THEN [NOW]

`THEN` and `NOW` are git references; `NOW` defaults to `HEAD`. Each is
extracted with `git archive` into a directory of its own and its contract is
read by a separate interpreter, because one process cannot import two
`digline` packages. It prints one line per key added, removed or changed, in
name order, and nothing when nothing moved. It exits 0 either way: what it
prints is a list to read, not a verdict.

**What it does not see.** The contract records keys and their JSON types. A
value whose meaning changed under the same key and type is the rule of
2026-10-12 in `RELEASING.md`, and a diff of types cannot see it.
"""

from __future__ import annotations

import io
import json
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: Run in the extracted tree's interpreter environment, with its `src/` first on
#: the path: the contract that tree derives, as JSON lines.
_READ = (
    "import json, sys; sys.path.insert(0, sys.argv[1]); "
    "from digline.wire.contract import _SHAPES, _lines; "
    "print(json.dumps(_lines(_SHAPES)))"
)


def contract_at(ref: str, repo: Path = ROOT) -> list[str]:
    """The contract `ref` derives, as `_lines(_SHAPES)` writes it."""
    archive = subprocess.run(
        ["git", "-C", str(repo), "archive", "--format=tar", ref, "src"],
        capture_output=True,
        check=True,
    ).stdout
    with tempfile.TemporaryDirectory() as tree:
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
            tar.extractall(tree, filter="data")
        done = subprocess.run(
            [sys.executable, "-c", _READ, str(Path(tree) / "src")],
            capture_output=True,
            text=True,
            check=True,
        )
    return list(json.loads(done.stdout))


def _keyed(lines: list[str]) -> dict[str, str]:
    """`{name.key: line}`, the key read without its `?`, so a key that became
    optional is one key that changed rather than one removed and one added."""
    return {line.split(": ", 1)[0].rstrip("?"): line for line in lines}


def diff(then: list[str], now: list[str]) -> list[str]:
    """One line per key added, removed or changed, in name order."""
    before, after = _keyed(then), _keyed(now)
    lines: list[str] = []
    for key in sorted(set(before) | set(after)):
        if key not in before:
            lines.append(f"added    {after[key]}")
        elif key not in after:
            lines.append(f"removed  {before[key]}")
        elif before[key] != after[key]:
            old, new = before[key], after[key]
            if old.split(": ", 1)[0] == new.split(": ", 1)[0]:
                old_types, new_types = old.split(": ", 1)[1], new.split(": ", 1)[1]
                lines.append(f"changed  {key}: {old_types} -> {new_types}")
            else:
                lines.append(f"changed  {old} -> {new}")
    return lines


def main(argv: list[str]) -> int:
    if not 1 <= len(argv) <= 2:
        print("usage: contract_diff.py THEN [NOW]", file=sys.stderr)
        return 64
    then, now = argv[0], argv[1] if len(argv) == 2 else "HEAD"
    for line in diff(contract_at(then), contract_at(now)):
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
