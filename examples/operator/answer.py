"""The label loop's seat: *would you have wanted to be woken?*

The decision journal records what the operator decided. This is where a person
records whether it was right — asked about a **hold** as much as about an
escalation, because a hold that should have woken somebody is the expensive
error and the one nothing else can see.

    python answer.py --config operator.toml

Three answers and not two. "It was wrong" and "it did not matter" are different
facts about a hold, and a scale that could not tell them apart would teach
itself that everything quiet was correct. `unsure` is the honest third, and it
is why the field is not a boolean.

What this file does **not** do is distil the answers into cases. That is the
ledger's business and it arrives with the ledger: what lands here is the field
and the question.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from journal import journal_path, read_journal, rewrite_journal

#: What may be typed. Anything else is asked again rather than guessed at: a
#: mismapped answer is a corrupted label, and a corrupted label is worse than a
#: missing one.
ANSWERS = {
    "y": "yes",
    "yes": "yes",
    "n": "no",
    "no": "no",
    "u": "unsure",
    "unsure": "unsure",
    "": "unsure",
}


def ask(prompt: str) -> str | None:
    """One answer, or `None` if the person walked away."""
    while True:
        try:
            raw = input(f"  {prompt} ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\n  ...stopped. What you answered is saved.")
            return None
        if raw in ANSWERS:
            return ANSWERS[raw]
        print("     y = yes, n = no, enter = unsure")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="operator.toml", type=Path)
    args = parser.parse_args(argv)

    root = Path(args.config).resolve().parent
    path = journal_path(root)
    records = read_journal(path)
    unanswered = [record for record in records if record.get("wanted") is None]
    if not unanswered:
        print(f"Nothing unanswered in {path.name}.")
        return 0

    print(
        f"\n=== {len(unanswered)} decision(s) to label ===\n"
        "Would you have wanted to be woken?  y = yes, n = no, enter = unsure\n"
    )
    answered = 0
    for record in unanswered:
        woke = "woke you" if record["escalate"] else "held"
        clause = record.get("clause")
        print(f"  {record['decided_at'][:16]}  {record['verdict']} — {woke}")
        if clause:
            print(f"    clause: {clause}")
        print(f"    {record['reason']}")
        wanted = ask("wanted waking?")
        if wanted is None:
            break
        record["wanted"] = wanted
        # **Now**, and never the cycle's own timestamp. The whole premise of a
        # label is that it is given later — days later, once you know whether
        # the quiet week was right — so stamping it with the moment the
        # decision was taken would erase the one fact the field exists to
        # carry, which is how long the answer took to arrive.
        record["answered_at"] = datetime.now(UTC).isoformat(timespec="seconds")
        answered += 1
        print()

    if answered:
        rewrite_journal(path, records)
        print(f"Saved {answered} answer(s) to {path}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
