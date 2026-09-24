"""What `compare` says to a program: the headline, and the deltas behind it.

The same object the CLI prints under `--json` and the MCP server returns from
its `compare` tool — one function, so the two cannot disagree. (ADR 0011 §4, §6)
"""

from __future__ import annotations

import dataclasses

from digline.core import (
    AssertionDelta,
    Comparison,
    ConfigDelta,
    Run,
    SuiteDelta,
    key_of,
)
from digline.report import Headline, Shape, ShapeSide, shape
from digline.wire.contract import OUTPUT_VERSION, exit_code
from digline.wire.text import neutralised

__all__ = ["compare_json", "config_json", "delta_json", "rule_json"]


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
        # Which row produced the exit code, when the headline says a canary
        # moved. A pipeline that reads only the number sees no change in kind;
        # one that wants to point at the check has the field. (ADR 0016 §8)
        "canary": delta.canary,
        # The row that belongs to a calibration case, which `counts` leaves out:
        # a pipeline reading every row can tell why this one is not among them.
        # (ADR 0024 §4.4)
        "calibration": delta.calibration,
        # Two aggregates computed over different numbers of cases. It rides
        # beside the outcome for the reason `within_noise` does, and it is the
        # field a pipeline needed most: before it existed this row read
        # `"outcome": "unchanged"` for a gate that had been measured over a
        # smaller suite, which is not a silence a consumer can detect.
        # (ADR 0012 §3, amended 2026-09-18)
        "denominator_moved": delta.denominator_moved,
    }


def _side_json(side: ShapeSide) -> dict[str, int]:
    return {
        "extremes": side.extremes,
        "scores": side.scores,
        "single_claim": side.single_claim,
        "claims_unrecorded": side.claims_unrecorded,
        "sample_means": side.sample_means,
    }


def shape_json(item: Shape) -> dict[str, object]:
    """One judged check's shape: counts only, so a consumer computes any share
    it wants and nothing rounded here is taken for a measurement. `reference`
    is `null` where the reference records no judged verdict for the check."""
    return {
        "check": item.check,
        "assertion_id": item.assertion_id,
        "run": _side_json(item.run),
        "reference": None if item.reference is None else _side_json(item.reference),
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


def rule_json(delta: SuiteDelta) -> dict[str, object]:
    """A rule delta as a pipeline reads it.

    Everything here travels and none of it is ever withheld: a threshold, a
    tolerance and a sample count are the bars a suite declared, not anything the
    system said, and `redact()` keeps all three. There is no `withheld` key for
    that reason — `config_json` has one because a configuration can carry a
    perimeter value, and a rule cannot. (ADR 0028 §1)

    `direction` is `""` where the movement has no direction, which is every
    `samples` row. A consumer that reads it as a verb must read the empty string
    as *no verb* rather than as *unchanged*.
    """
    return {
        "rule": delta.rule,
        "assertion_id": delta.assertion_id,
        "scope": delta.scope,
        "outcome": delta.outcome,
        "direction": delta.direction,
        "field": delta.field,
        "before": delta.before,
        "after": delta.after,
        "expansion": delta.expansion,
    }


def compare_json(
    comparison: Comparison, head: Headline, *, baseline: Run, full: bool
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
    # The reference this comparison was made against, by the key a promotion
    # has to name to replace it — in every shape, not only `full`, because the
    # one thing a caller does next with a comparison it accepts is promote.
    # Derived here from the document rather than handed in, so no caller can
    # pass the key of a different reference. An added key under
    # `OUTPUT_VERSION = 2`'s rule. (ADR 0031 §2)
    payload["baseline_key"] = key_of(baseline.created_at, baseline.config_hash)
    if full:
        payload["deltas"] = [delta_json(d) for d in comparison.deltas]
        # The shape reading's numbers, beside the deltas they are read from. An
        # added key, and a list with no verdict in it: nothing here says *more*.
        # (ADR 0024 §6.3)
        payload["shape"] = [shape_json(item) for item in shape(comparison)]
        payload["target_config_deltas"] = [
            config_json(d) for d in comparison.target_config_deltas
        ]
        payload["judge_config_deltas"] = [
            config_json(d) for d in comparison.judge_config_deltas
        ]
        # Beside the two configuration lists, because it answers the same
        # question about the other half of the comparison: those name the system
        # that answered, this names the rules it was held to. Under `full` for
        # their reason, and an added key under `OUTPUT_VERSION = 2`'s rule
        # rather than a bump. (ADR 0028 §8)
        payload["suite_deltas"] = [rule_json(d) for d in comparison.suite_deltas]
    return neutralised(payload)
