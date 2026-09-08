"""What `compare` says to a program: the headline, and the deltas behind it.

The same object the CLI prints under `--json` and the MCP server returns from
its `compare` tool — one function, so the two cannot disagree. (ADR 0011 §4, §6)
"""

from __future__ import annotations

import dataclasses

from digline.core import AssertionDelta, Comparison, ConfigDelta
from digline.report import Headline
from digline.wire.contract import OUTPUT_VERSION, exit_code

__all__ = ["compare_json", "config_json", "delta_json"]

def delta_json(delta: AssertionDelta) -> dict[str, object]:
    """The structured facts, and deliberately **not** the verdict's `reason`.

    A reason is payload, and stdout of a CI job is a place logs go and stay. A
    pipeline that genuinely needs the judge's words can read the run file, from
    inside the perimeter where it is allowed to.

    `scope` is emitted even though a run-scoped delta always carries
    `case_id == ""`: deriving the kind of a delta from an empty string asks the
    consumer to know a convention instead of reading a field, and an empty
    `case_id` is equally what a malformed one would look like.

    `within_noise` and the interval ride beside the outcome rather than inside
    it, in `--json` for the same reason as in the document: `Outcome` gains no
    sixth member, so a pipeline that already knows the five keeps working, and
    one that wants to tell "nothing moved" from "what moved was noise" reads a
    field. The interval is emitted on a regression too — that is the sentence
    "beyond the noise of this check" in machine form. (ADR 0006 §9)
    """
    before = None if delta.baseline is None else delta.baseline.score.score
    after = None if delta.current is None else delta.current.score.score
    return {
        "case_id": delta.case_id,
        "scope": delta.scope,
        "assertion": delta.assertion,
        "outcome": delta.outcome,
        "before": before,
        "after": after,
        "delta": delta.delta,
        "within_noise": delta.within_noise,
        "noise_min": delta.noise_min,
        "noise_max": delta.noise_max,
        "noise_samples": delta.noise_samples,
    }


def config_json(delta: ConfigDelta) -> dict[str, object]:
    """A configuration delta as a pipeline reads it.

    The values travel, unlike a verdict's `reason`: a model id and a temperature
    are measurements of the system, and a withheld field carries no value to
    print in the first place — redaction removed it before this was built
    (ADR 0005 §2).
    """
    return {
        "field": delta.field,
        "outcome": delta.outcome,
        "before": delta.before,
        "after": delta.after,
        "withheld": delta.withheld,
    }


def compare_json(
    comparison: Comparison, head: Headline, *, full: bool
) -> dict[str, object]:
    """The headline, not the document: a pipeline wants the facts, and the
    sentence it carries is the same one a customer will read.

    Assembled here rather than inside a command because there are two callers.
    While there was one, building it inline was fine; the moment a second
    surface returns the same object, a shape assembled in a command body is a
    shape that drifts the first time somebody edits the command. (ADR 0011 §6)
    """
    payload: dict[str, object] = {"output_version": OUTPUT_VERSION}
    payload.update(dataclasses.asdict(head))
    # The number `AGENTS.md` §6 calls the contract, computed by the one function
    # that knows the precedence — a regression outranks an unjudged case. A
    # caller left to derive it from `worse` and `unjudged` has to know that
    # rule, and `exit_code()` exists so that nobody has to. Over MCP there is no
    # process to exit, which is why it has to be a field there; it is a field
    # here too so the two surfaces cannot answer differently. (ADR 0011 §4)
    payload["exit_code"] = exit_code(head)
    if full:
        payload["deltas"] = [delta_json(d) for d in comparison.deltas]
        payload["target_config_deltas"] = [
            config_json(d) for d in comparison.target_config_deltas
        ]
        payload["judge_config_deltas"] = [
            config_json(d) for d in comparison.judge_config_deltas
        ]
    return payload
