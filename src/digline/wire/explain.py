"""What `explain` says to a program: the fact list, and no prose.

The other rendering of `digline.report.explain`'s list. The prose is one render
of it and this is the other; neither is the source, which is what stops a
terminal and a pipeline from coming to describe one run differently (ADR 0012
§3).

**No sentence crosses here.** `compare_json` ships `Headline.sentence` because a
gate and a customer's document must never word one run two ways, so the wire is
where that single wording lives. A reading's prose is derivable from the list
by construction, so shipping it would ship a derived value and invite a consumer
to parse English with the typed facts beside it.

**And no reason crosses here, because none exists.** The types in
`report/explain.py` have no field for one — that is ADR 0012 §4, and it is why
this module needs no filter and `tests/test_wire_boundary.py` has nothing to
catch on this surface.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import assert_never

from digline.report.explain import CheckFact, Fact, SettingFact, TallyFact
from digline.wire.contract import OUTPUT_VERSION

__all__ = ["explain_json", "fact_json"]


def fact_json(fact: Fact) -> dict[str, object]:
    """One fact, as a program reads it.

    `about` before `kind`, and both are emitted: the three shapes have kinds of
    their own and two of them share the word `within_noise`, so a consumer
    discriminates on `about` first and then on `kind`. Deriving the shape from
    which keys happen to be present would ask a consumer to know a convention
    instead of reading a field.
    """
    match fact:
        case CheckFact():
            return {
                "about": "check",
                "kind": fact.kind,
                "scope": fact.scope,
                "case_id": fact.case_id,
                "assertion": fact.assertion,
                "assertion_id": fact.assertion_id,
                "before": fact.before,
                "after": fact.after,
                "delta": fact.delta,
                "threshold": fact.threshold,
                # The interval flattened rather than nested, like `delta_json`'s:
                # a pipeline that already reads `noise_min` off a comparison
                # reads it the same way here.
                "noise_min": fact.noise.low,
                "noise_max": fact.noise.high,
                "noise_samples": fact.noise.count,
            }
        case SettingFact():
            return {
                "about": "setting",
                "kind": fact.kind,
                "name": fact.name,
                # `None` where there was nothing to compare against, which is
                # not a sixth outcome: it is the absence of a comparison.
                "outcome": fact.outcome,
                "before": fact.before,
                "after": fact.after,
                "withheld": fact.withheld,
                "added": fact.added,
                "removed": fact.removed,
            }
        case TallyFact():
            return {
                "about": "run",
                "kind": fact.kind,
                "count": fact.count,
                "state": fact.state,
            }
    assert_never(fact)


def explain_json(
    reading: Sequence[Fact], *, scope: str, exit_code: int
) -> dict[str, object]:
    """The whole reading, for a program.

    `scope` says which of the two documents this is — `"comparison"` or
    `"run"` — rather than leaving a consumer to infer it from which kinds
    turned up. A run whose comparison found nothing and a run with no reference
    at all produce different readings, and the difference must not be something
    you deduce from an absence.
    """
    return {
        "output_version": OUTPUT_VERSION,
        "scope": scope,
        # The same number the process exits with, for the same reason it is on
        # `compare --json`: over MCP there is no process to exit, and the two
        # surfaces must not answer differently. (ADR 0011 §4)
        "exit_code": exit_code,
        "facts": [fact_json(fact) for fact in reading],
    }
