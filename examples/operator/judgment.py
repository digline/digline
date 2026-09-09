"""Layer 3: the only part of the alert a model writes.

It reads `cycle.json` — the wire's verdicts and the deterministic dossier built
from them — and writes a paragraph saying what it thinks happened. It is an
**opinion**, and `dossier.py` labels it as one: the instrument measured layers 1
and 2, and this interprets them.

    DIGLINE_LIVE=1 ANTHROPIC_API_KEY=... python judgment.py --cycle cycle.json

Skipped entirely without a key, and the alert then says the layer was not run.
That is the same opt-in every example in this repository uses, and it is why the
loop is demonstrable by somebody who has no account anywhere.

**What the model is shown is what already crossed the boundary.** `cycle.json`
holds `compare --json` output: names, statuses, scores, thresholds, intervals.
It holds no judge `reason`, no case input, no suspension sentence — those are
payload, and payload stays inside the perimeter it was measured in. Nothing in
this file re-reads the run to enrich the prompt, and nothing may.
"""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Sequence
from pathlib import Path
from typing import Any, cast

from dossier import evidence

MODEL = "claude-haiku-4-5"

SYSTEM = """\
You are the operator watching a digline suite. You classify a measurement; you
do not repair the system, and you never recommend promoting a baseline — a
baseline is an approved reference and the approval is a person's.

You are given two layers of a three-layer alert: the machine facts from
digline's wire, and a deterministic record of what the operator did. Write the
third layer.

Rules you are held to, which the operator already applied mechanically:
- one bad run is a draw until it repeats;
- several cases flipping together is investigated, never retried;
- "within noise" explains a comparison, it never excuses a red exit code;
- an exit code of 2 means the run could not be judged, and nothing downstream
  of it is meaningful.

Write at most 150 words, in plain prose, in English. Say what you think moved
and what you would look at first — the model, the judge, the prompt, the
dependency floor, in that order of likelihood. If the evidence does not support
a conclusion, say that instead of manufacturing one. Do not restate the tables.
Do not open with a heading."""


def build_prompt(cycle: dict[str, Any]) -> str:
    return (
        f"The operator's deterministic classification is: {cycle['verdict']}.\n\n"
        f"{evidence(cycle)}"
    )


def ask(prompt: str) -> str:  # pragma: no cover - needs a key
    import anthropic

    reply = anthropic.Anthropic().messages.create(
        model=MODEL,
        max_tokens=400,
        system=SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )
    # Only the text blocks: the SDK's `content` is a union, and a thinking or
    # tool block has no `.text` at all — which a type checker says before a
    # traceback does.
    return "".join(block.text for block in reply.content if block.type == "text")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cycle", default="cycle.json", type=Path)
    parser.add_argument("--out", default="judgment.md", type=Path)
    args = parser.parse_args(argv)

    if os.environ.get("DIGLINE_LIVE") != "1":
        # Two switches, deliberately: a key that happens to be exported on this
        # machine is not the same as somebody deciding to spend money today.
        print("DIGLINE_LIVE is not 1: the judgment layer is not run")
        return 0

    cycle = cast(
        "dict[str, Any]", json.loads(Path(args.cycle).read_text(encoding="utf-8"))
    )
    Path(args.out).write_text(ask(build_prompt(cycle)), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
