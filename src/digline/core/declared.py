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

__all__ = ["Declared", "nothing_judged"]


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

    Surface only: it answers `False`, today's behaviour, until the rule lands.
    """
    del run, declared
    return False
