"""What the run tools say to a program.

`run_json` is what `digline run --json` prints and what the MCP `run` tool
returns: a run was written, and here is how to name it. It carries no verdict —
it reports that a run happened, not whether it was any good.
"""

from __future__ import annotations

from digline.run import CallPlan
from digline.store import RunRef
from digline.wire.contract import OUTPUT_VERSION

__all__ = ["run_json"]


def run_json(ref: RunRef, plan: CallPlan) -> dict[str, object]:
    """The written run, named, with what it cost to make.

    `sentence` is `CallPlan.sentence()` — the line the CLI prints to stderr
    before the first call. Over MCP there is no stderr, and `AGENTS.md` §7 asks
    an agent to say what a hunt cost; the acknowledged integer covers the calls
    to the target only, so the sentence is what carries the judge repeats a
    caller has to include when it reports the spend. (ADR 0011 §2, §4)
    """
    return {
        "output_version": OUTPUT_VERSION,
        "key": ref.key,
        "tenant": ref.tenant,
        "suite": ref.suite,
        "sentence": plan.sentence(),
    }
