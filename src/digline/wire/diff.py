"""What `diff` says to a program. Symmetric, and with no `worse` in it.

The absence is the point, not an omission: a verdict exists only against an
approved reference, and neither side of a diff was approved by anybody, so there
is nothing here for a caller to gate on. (ADR 0008 §1)
"""

from __future__ import annotations

from digline.core import CheckDifference, Difference, Noise, Run
from digline.wire.compare import config_json
from digline.wire.contract import OUTPUT_VERSION

__all__ = ["check_json", "diff_json", "interval_json"]

def interval_json(noise: Noise) -> dict[str, object] | None:
    """One measured interval, or `null` where nothing measured it.

    `null` rather than zeros: a check at `samples=1` has no interval, and
    `{"min": 0, "max": 0}` would be a measurement nobody took.
    """
    if not noise.known:
        return None
    return {"min": noise.low, "max": noise.high, "samples": noise.count}


def check_json(check: CheckDifference) -> dict[str, object]:
    """One check as a pipeline reads it: symmetric, and without a `reason`.

    `left` and `right` rather than `before` and `after`, and `favours` rather
    than a sign somebody has to interpret. A consumer that swaps the two
    arguments gets the same rows with the two sides exchanged and `delta`
    negated, which is the columns moving and not the facts.

    The judge's `reason` is absent for `_delta_json`'s reason: a reason is
    payload, and stdout of a CI job is where logs go and stay.
    """
    return {
        "case_id": check.case_id,
        "scope": check.scope,
        "assertion": check.assertion,
        "outcome": check.outcome,
        "favours": check.favours,
        "left": None if check.left is None else check.left.score.score,
        "right": None if check.right is None else check.right.score.score,
        "delta": check.delta,
        "tolerance": check.tolerance,
        "flipped": check.flipped,
        "left_interval": interval_json(check.left_interval),
        "right_interval": interval_json(check.right_interval),
        "intervals_overlap": check.intervals_overlap,
        "intervals_disjoint": check.intervals_disjoint,
    }


def diff_json(
    difference: Difference,
    left: Run,
    right: Run,
    *,
    keys: tuple[str, str],
    labels: tuple[str, str],
    sentence: str,
    full: bool,
) -> dict[str, object]:
    """What `digline diff --json` prints.

    **There is no `worse` field, and its absence is the point** (ADR 0008 §1).
    `Headline` is not reused and no diff-shaped equivalent of it exists, so
    there is nothing here for a pipeline to gate on — which is the whole reason
    this command was not built as a flag on `compare`.

    The structure is symmetric: `runs.left` and `runs.right`, `favours_left` and
    `favours_right`, `left_exceeds` and `right_exceeds`. Swapping the two
    arguments exchanges every pair and changes nothing else.
    """
    payload: dict[str, object] = {
        "output_version": OUTPUT_VERSION,
        "tenant": difference.tenant,
        "suite": difference.suite,
        "runs": {
            side: {
                "key": key,
                "label": label,
                "created_at": run.created_at,
                "environment": run.environment,
            }
            for side, key, label, run in (
                ("left", keys[0], labels[0], left),
                ("right", keys[1], labels[1], right),
            )
        },
        "counts": {
            "total": difference.total,
            "differing": difference.differing,
            "favours_left": difference.favours_left,
            "favours_right": difference.favours_right,
            "within_tolerance": difference.within_tolerance,
            "only_left": difference.only_left,
            "only_right": difference.only_right,
            "errored": difference.errored,
            "interval_pairs": difference.interval_pairs,
            "left_exceeds": difference.left_exceeds,
            "right_exceeds": difference.right_exceeds,
        },
        "systems_differ": difference.systems_differ,
        "artifacts_differ": difference.artifacts_differ,
        "judges": list(difference.judges),
        "sentence": sentence,
    }
    if full:
        payload["checks"] = [check_json(c) for c in difference.checks]
        payload["target_config_deltas"] = [
            config_json(d) for d in difference.target_config_deltas
        ]
    return payload
