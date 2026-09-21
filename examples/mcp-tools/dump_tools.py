"""Write the server's tool definitions to `tools.json`, canonically.

    uv run python dump_tools.py

Run it in the same step that runs the suite, immediately before it. digline
never fetches `tools/list` for you — it reads this file off disk — so a dump
that stopped running leaves a stale SHA that `compare` reports as *unchanged*,
which is worse than no check because it reads as a verification that happened.

**Canonical is the whole point.** The tools are sorted by name, the keys are
sorted, and the output is indented:

- a server may return its tools in any order, and a reordered list is a
  different SHA;
- a JSON object has no order, and no client library promises you one;
- the report's diff is line-oriented, so a single-line blob reports `+1 -1`
  for a typo and for a rewritten instruction alike, and distinguishes nothing.

Without those three, the file changes on every run, the report says so every
time, and within a week you have trained yourself to scroll past the one line
that was meant to be the alarm.

digline canonicalises tool-call *arguments* inside `ToolCalledWith` and does
**not** canonicalise artifacts: it hashes the bytes on disk, because an
artifact is any file a suite declares and a hash that reformatted its subject
would be hashing something other than the file under test. So the normalising
is yours, on the way in, and this is it.
"""

from __future__ import annotations

import json
from pathlib import Path

import server

HERE = Path(__file__).parent
TOOLS = HERE / "tools.json"


def canonical_dump() -> str:
    """The exact text that lands in `tools.json`."""
    tools = sorted(server.list_tools(), key=lambda tool: str(tool["name"]))
    return json.dumps(tools, sort_keys=True, indent=2, ensure_ascii=False) + "\n"


def main() -> None:
    TOOLS.write_text(canonical_dump(), encoding="utf-8")
    print(f"wrote {TOOLS.name}")


if __name__ == "__main__":
    main()
