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
holds `explain --json` output: names, outcomes, scores, thresholds, intervals.
It holds no judge `reason`, no case input, no suspension sentence — those are
payload, and the fact list has no field for any of them. Payload stays inside
the perimeter it was measured in. Nothing in this file re-reads the run to
enrich the prompt, and nothing may.
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

Read layer 1 before you suspect anything, and rule out what it already rules
out. There is no order of suspects to follow; there are facts to consult, by
name:
- the "nothing differed" line — "Underneath it, nothing differed: not the
  system under test, not the judge, not a file under test." It means no setting
  of the target, no setting of the judge and no file under test changed. The
  prompt under test is a file under test, so it did not change either;
- `artifacts_changed`, which layer 1 renders in that same line as "a file under
  test": a changed file is named there, and "not a file under test" is the fact
  that none changed;
- the canary line, stated before layer 1. A canary is the case that watches the
  model behind the alias, and `explain` reports one only when it moved. A case
  whose name happens to contain the word is not the canary.

If nothing differed and the canary line says a canary is declared and none
moved, the model is EXCLUDED: not the first suspect, not a suspect, and not
something you recommend looking at.

If the canary line says no canary is declared, or that whether one is declared
was not recorded, nothing in this cycle watches the model. It is then neither
excluded nor suspected: say exactly that, and do not rank it.

Name only what the facts leave standing, and say which fact set aside each thing
you exclude.

Write at most 150 words, in plain prose, in English. Say what you think moved
and what you would look at first. If the evidence does not support a
conclusion, say that instead of manufacturing one. Do not restate the tables.
Do not open with a heading."""

#: The output ceiling, set so that the 150-word cap in `SYSTEM` is the limit
#: that binds and this one is a backstop. 150 English words are about 200
#: tokens; the ceiling was 400, and pilot-zero's cycle 5 reached it mid-sentence
#: at about 270 words. At 1024 a reply that still stops here has overrun the cap
#: roughly fourfold, and the alert says it was cut rather than ending mid-word.
MAX_TOKENS = 1024


def canary_line(cycle: dict[str, Any]) -> str:
    """The canary, stated — because layers 1 and 2 never state it.

    Three states, and only one of them excludes anything:

    - **moved** — a run reports a `canary` fact;
    - **declared and unmoved** — the suite declares one and no run reports it;
    - **not declared** — nothing watches the model, so its silence proves
      nothing. A declared absence, never a zero: a suite with no canary cannot
      clear the model, and a sentence reading "no canary moved" would let it.

    `explain` emits a `canary` fact only when one moved, and it is silent alike
    about a canary that held and a suite that has none, so the declaration comes
    from `cycle.json`'s `canaries_declared`, which `loop.py` reads off the suite.
    A cycle written before that key existed says so and clears nothing.

    Everything here is from the same `cycle.json` `evidence` renders: no payload
    and nothing from outside the cycle, only sentences for facts that crossed.
    """
    moved = [
        str(run["key"])
        for run in cycle["runs"]
        for fact in run["explain"]["facts"]
        if fact["about"] == "run" and fact["kind"] == "canary" and fact["state"]
    ]
    if moved:
        return "Canary: MOVED, in run(s) " + ", ".join(f"`{k}`" for k in moved) + "."
    declared = cycle.get("canaries_declared")
    if declared is None:
        return (
            "Canary: whether this suite declares one was not recorded — this "
            "cycle predates the record. The model is neither excluded nor "
            "suspected."
        )
    if declared == 0:
        return (
            "Canary: no canary declared. Nothing in this suite watches the model, "
            "so the model is neither excluded nor suspected."
        )
    return (
        f"Canary: {declared} declared, and none moved — no run of this cycle "
        "reports a `canary` fact, and `explain` reports one only when a canary "
        "moved."
    )


def build_prompt(cycle: dict[str, Any], decision: dict[str, Any] | None = None) -> str:
    return (
        f"The operator's deterministic classification is: {cycle['verdict']}.\n\n"
        f"{canary_line(cycle)}\n\n"
        f"{evidence(cycle, decision)}"
    )


def ask(prompt: str) -> tuple[str, str | None]:  # pragma: no cover - needs a key
    """The text, and why the model stopped writing it.

    `stop_reason` travels with the text because the text alone cannot say
    whether it is whole: `end_turn` is a finished answer, `max_tokens` is one
    cut at the ceiling, and a document that stops mid-sentence without
    declaring it reads as a conclusion the model never reached.
    """
    import anthropic

    reply = anthropic.Anthropic().messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )
    # Only the text blocks: the SDK's `content` is a union, and a thinking or
    # tool block has no `.text` at all — which a type checker says before a
    # traceback does.
    text = "".join(block.text for block in reply.content if block.type == "text")
    return text, reply.stop_reason


def record(stop_reason: str | None) -> dict[str, Any]:
    """`judgment.json`: how the judgment ended, for `dossier.py` to declare."""
    return {"model": MODEL, "max_tokens": MAX_TOKENS, "stop_reason": stop_reason}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cycle", default="cycle.json", type=Path)
    parser.add_argument("--decision", type=Path, help="the seat, when it ran")
    parser.add_argument("--out", default="judgment.md", type=Path)
    parser.add_argument(
        "--record",
        default="judgment.json",
        type=Path,
        help="how the judgment ended: the model, the ceiling, the stop reason",
    )
    args = parser.parse_args(argv)

    if os.environ.get("DIGLINE_LIVE") != "1":
        # Two switches, deliberately: a key that happens to be exported on this
        # machine is not the same as somebody deciding to spend money today.
        print("DIGLINE_LIVE is not 1: the judgment layer is not run")
        return 0

    cycle = cast(
        "dict[str, Any]", json.loads(Path(args.cycle).read_text(encoding="utf-8"))
    )
    decision: dict[str, Any] | None = None
    if args.decision is not None and Path(args.decision).is_file():
        decision = cast(
            "dict[str, Any]",
            json.loads(Path(args.decision).read_text(encoding="utf-8")),
        )
    text, stop_reason = ask(build_prompt(cycle, decision))
    Path(args.out).write_text(text, encoding="utf-8")
    Path(args.record).write_text(
        json.dumps(record(stop_reason), indent=2) + "\n", encoding="utf-8"
    )
    print(f"judgment: stop_reason={stop_reason}, max_tokens={MAX_TOKENS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
