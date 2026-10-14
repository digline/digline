"""What a suite declares it measures, and whether a run judged any of it.

A run document records no list of the cases its suite declares, so whether a
run judged anything cannot be read from the run alone: a suite that measures a
subject, in a run that carries none of its subject cases, would fall to its
canaries, and a judged canary would turn it green. The front end that loaded
the suite hands the declaration to every path that turns a run into a code or
a reference, and `None` where there is no suite behind the document.
(ADR 0049 §3)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from digline.core.run import Run

__all__ = ["Declared", "cases_that_count", "nothing_judged"]


@dataclass(frozen=True, slots=True)
class Declared:
    """The cases a suite declares, by kind.

    `subject` holds the cases that are neither a canary nor a calibration case;
    `watching` holds the canaries and the calibration cases. Two sets of ids
    and nothing else, because §3's definition needs nothing else, and a value
    in core must not carry the suite's payload.
    """

    subject: frozenset[str]
    watching: frozenset[str]


def nothing_judged(run: Run, declared: Declared | None) -> bool:
    """Whether none of the cases that count was judged. (ADR 0049 §3)

    The cases that count are, in three clauses, the first that applies: the
    subject cases the suite declares; if it declares none, its canaries and
    calibration cases; and with no declaration to read, the same two clauses
    applied to the cases the document carries.

    **The declaration decides, not the run.** A run that carries none of the
    declared subject cases still counts them, and judged none of them, so a
    judged canary cannot turn a subject suite green. A result the suite no
    longer declares counts under neither set.

    A case is judged when at least one of its verdicts is `pass` or `fail`:
    a suspended case has none, and an errored one has only `error`.
    Aggregates never count: a figure over the cases is not evidence that the
    cases were judged.
    """
    counting = cases_that_count(run, declared)
    return not any(
        verdict.status in ("pass", "fail")
        for case in run.results
        if case.case_id in counting
        for verdict in case.verdicts
    )


def cases_that_count(run: Run, declared: Declared | None) -> frozenset[str]:
    """The ids of the cases that count, by §3's three clauses: what
    `nothing_judged` reads, and what a refusal names. (ADR 0049 §3)

    A declared case the run does not carry is among them: absent is one of the
    ways a case goes unjudged.
    """
    if declared is not None:
        return declared.subject or declared.watching
    subject = frozenset(
        case.case_id
        for case in run.results
        if not case.canary and case.calibration is None
    )
    # With no subject case in the document, every case it carries is a canary
    # or a calibration case: the second clause, read off the run.
    return subject or frozenset(case.case_id for case in run.results)
