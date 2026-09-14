"""The decision journal: every hold and every escalation, with its reason.

    .digline/<tenant>/decisions/<suite>.jsonl        append-only, gitignored

**A hold is always written, and a hold most of all.** A hold nobody records is
indistinguishable from a cycle that never ran — which is the failure mode that
would make a quiet quarter unreadable, and a quiet quarter is what this whole
design is trying to earn.

Ignored rather than committed, on the precedent of the dogfood's own history
file: a private, append-forever record from which a reviewable artifact is
later distilled by an explicit command. Being ignored also closes a trap that
would otherwise be found the hard way — `git_commit` reads
`git status --porcelain`, so a tracked journal written during a cycle would
leave the tree dirty and stamp the very run it records as `-dirty`.

It is not a document. Nothing lists it, compares it, reports it or migrates it,
and by the rule the policy already follows it holds identifiers and never
contents — so there is nothing in it redaction would have had to reach.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, cast

#: The shape of a journal line. Its own number, because the journal is a format
#: and not a document: there is no migration, and a journal this file cannot
#: read is one it refuses rather than repairs.
JOURNAL_VERSION = 1

DECISIONS_DIRNAME = "decisions"


def journal_path(root: Path, tenant: str = "", suite: str = "") -> Path:
    """Where the decisions of one suite live.

    The tenant is a directory, here as everywhere: the perimeter is enforced by
    the filesystem rather than described by a field inside a file.
    """
    if tenant and suite:
        return root / ".digline" / tenant / DECISIONS_DIRNAME / f"{suite}.jsonl"
    # The single-suite convenience the example's own commands use.
    found = sorted((root / ".digline").glob(f"*/{DECISIONS_DIRNAME}/*.jsonl"))
    if found:
        return found[0]
    return root / ".digline" / "decisions.jsonl"


def read_journal(path: Path) -> list[dict[str, Any]]:
    """Every line, oldest first. A torn last line is discarded on read.

    The process was killed while writing it; it is the one line whose absence
    is expected. A line that fails to parse anywhere *but* at the end is a
    corrupt journal and is refused by name rather than repaired.
    """
    if not path.is_file():
        return []
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line]
    records: list[dict[str, Any]] = []
    for number, line in enumerate(lines, start=1):
        try:
            records.append(cast("dict[str, Any]", json.loads(line)))
        except json.JSONDecodeError:
            if number == len(lines):
                break
            raise ValueError(
                f"{path} line {number} is not readable, and it is not the last "
                "line — a torn tail is expected after a kill, a hole in the "
                "middle is a corrupt journal. It holds work nobody can redo, "
                "so it is named rather than repaired."
            ) from None
    return records


def append(path: Path, record: dict[str, Any]) -> None:
    """One line, flushed. Append-only: nothing here is ever rewritten in
    place by the loop, so a kill at any instant loses at most the line it was
    writing."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
        handle.flush()


def rewrite_journal(path: Path, records: Sequence[Mapping[str, Any]]) -> None:
    """Rewrite the whole file, for the one caller allowed to: the person
    answering *would you have wanted to be woken?*

    The loop only ever appends. Labelling is a human act, performed once, on a
    file the loop is not writing at the time — which is the only condition
    under which rewriting an append-only file is safe.

    There is no `version` parameter, and that is deliberate: every record
    carries its own, written by whoever appended it, so one passed in here
    would be a second place for the same fact to be wrong. A parameter that is
    accepted and thrown away is worse than no parameter.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "".join(json.dumps(record, sort_keys=True) + "\n" for record in records)
    path.write_text(body, encoding="utf-8")


def holds_in_a_row(records: Sequence[Mapping[str, Any]], clause: str) -> int:
    """How many cycles this clause has held **in an unbroken run**, newest
    first.

    Unbroken is the whole of it: a clause that held twice, woke somebody, and
    then held again is on its first cycle, not its third. `max_cycles` is a
    statement about a streak, because what it is trying to catch is a dip that
    stopped being a dip.

    `Mapping` and not `dict` because this only ever reads — the Python idiom is
    to ask for the least the function needs, so a caller holding something
    read-only can still call it. `decide.py` holds exactly that, and asking for
    `dict` here made a type error out of a function that mutates nothing.
    """
    count = 0
    for record in reversed(records):
        if record.get("clause") != clause:
            break
        if record.get("escalate"):
            break
        count += 1
    return count
