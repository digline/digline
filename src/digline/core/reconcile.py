"""Whether a run recorded an answer to every question it was asked.

A pure comparison of two things the driver holds: what it asked of each case,
and the results it is about to record. The gaps come back **named**, case and
check, because a count of them sends somebody hunting while the names end the
question. (ADR 0027)

Nothing here decides what a case is asked. That is the driver's dispatch, and it
is passed in: a suspended case is asked nothing, a calibration case its one
check, every other case every assertion. Reading the dispatch back, rather than
subtracting a list of exclusions from a total, is what keeps this from going
stale the day somebody adds a kind of case. (ADR 0027 §1)
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Literal

from digline.core.run import CaseResult, Run
from digline.core.types import Score, Verdict

__all__ = [
    "UNRECONCILED",
    "Gap",
    "GapKind",
    "reconcile",
    "unreconciled",
    "unreconciled_verdict",
]

#: The `Score.metadata` key the driver sets on the errored verdict it records
#: in place of an answer that never came back. A boolean, so it travels under
#: `travels()` like every other measurement and survives `redact()` without a
#: schema bump. (ADR 0027 §3)
UNRECONCILED = "unreconciled"

#: `missing`: asked and not answered. `unasked`: answered and not asked — a
#: verdict for a check the case was not put, or a second one for a check it was.
type GapKind = Literal["missing", "unasked"]


@dataclass(frozen=True, slots=True)
class Gap:
    """One question the run and its record disagree about.

    `assertion_id` is empty when the whole result is the gap: a declared case
    with no result at all, or a result for a case nobody declared.
    """

    kind: GapKind
    case_id: str
    assertion_id: str = ""


def reconcile(
    asked: Mapping[str, frozenset[str]], results: Sequence[CaseResult]
) -> tuple[Gap, ...]:
    """Every disagreement between what was asked and what was recorded.

    `asked` maps each declared case id to the identities it was asked, in the
    suite's order. Two checks, in that order, and nothing else (ADR 0027 §1):

    1. every declared case has exactly one result;
    2. every result carries exactly one verdict per identity it was asked, and
       none it was not.

    Empty means the run reconciles. The order of the gaps is the suite's, then
    the order of anything recorded that the suite did not declare, so two runs
    with the same gaps name them the same way.
    """
    by_case: dict[str, list[CaseResult]] = {}
    for result in results:
        by_case.setdefault(result.case_id, []).append(result)

    gaps: list[Gap] = []
    for case_id, identities in asked.items():
        held = by_case.get(case_id, [])
        if not held:
            gaps.append(Gap("missing", case_id))
            continue
        for extra in held[1:]:
            # A second result for one case: every verdict in it is an answer
            # to a question already answered, so each is one gap.
            gaps.extend(Gap("unasked", case_id, v.assertion_id) for v in extra.verdicts)
            if not extra.verdicts:
                gaps.append(Gap("unasked", case_id))
        gaps.extend(_verdict_gaps(case_id, identities, held[0]))
    gaps.extend(Gap("unasked", case_id) for case_id in by_case if case_id not in asked)
    return tuple(gaps)


def _verdict_gaps(
    case_id: str, identities: frozenset[str], result: CaseResult
) -> list[Gap]:
    recorded = Counter(v.assertion_id for v in result.verdicts)
    gaps: list[Gap] = []
    # Missing first, in a fixed order: sorted, because a frozenset has none and
    # the names end up in a sentence somebody compares across two runs.
    gaps.extend(
        Gap("missing", case_id, identity)
        for identity in sorted(identities)
        if not recorded[identity]
    )
    for identity, count in recorded.items():
        surplus = count if identity not in identities else count - 1
        gaps.extend(Gap("unasked", case_id, identity) for _ in range(surplus))
    return gaps


def unreconciled_verdict(verdict: Verdict, reason: str) -> Verdict:
    """`verdict`, turned into the errored, marked verdict that stands for a gap.

    Everything that names the check — its name, identity, threshold, tolerance
    — is kept. The score is dropped, because a score for a question that was not
    asked, or that came back twice, is not a measurement of anything.
    """
    return replace(
        verdict,
        score=Score(name=verdict.score.name, score=None, metadata={UNRECONCILED: True}),
        status="error",
        reason=reason,
    )


def unreconciled(run: Run) -> tuple[tuple[str, str], ...]:
    """The `(case_id, check)` pairs this run recorded as gaps, in run order.

    Read off the run alone, like `scale_lost`, so the headline, the reading and
    promotion all say it without a reference. The marker counts only on an
    errored verdict: on anything else it would be a key an assertion happened to
    write, and it would be claiming a gap where an answer came back.
    """
    return tuple(
        (case.case_id, verdict.score.name)
        for case in run.results
        for verdict in case.verdicts
        if verdict.status == "error"
        and verdict.score.metadata.get(UNRECONCILED) is True
    )
