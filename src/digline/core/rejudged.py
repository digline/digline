"""A re-judge read against the run it was made from: which reviewed answers
changed verdict, for which check, and whether toward the person or away.

A rubric's text is part of its check's identity, so a corrected rubric is a new
identity, and `diff` reads it as one check gone and one arrived. This pairs by
**check name and case** instead, between a run and a re-judge made from it,
which is the only pairing that can say what a corrected rubric did to the
verdicts it was corrected for. It never pairs two verdicts of one name whose
types differ, or whose type the run it was made from did not record: two checks
of different kinds under one name are not one check that changed. (ADR 0067
§1 (d), as noted 2026-11-22)

Pure, from the two runs alone. The front end reads the source run by the key
the re-judge declares, `rejudged_from`, and hands it in.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from digline.core.compare import DifferentTenantsError
from digline.core.run import CaseResult, Run
from digline.core.types import CheckType, Status, Verdict

__all__ = [
    "PairedCheck",
    "RubricComparison",
    "UnpairedCheck",
    "Unpaired",
    "VerdictChange",
    "rubric_comparison",
]

#: Why a check's verdicts were not paired by name:
#: - `type_changed`: its type in the re-judge is not the one the source
#:   recorded, which includes a check digline has no word for that took the
#:   place of one it has;
#: - `type_not_recorded`: the source recorded no type for it, a run written
#:   before schema 25 or a check digline has no word for;
#: - `name_shared`: two checks carry the name on one answer, so the name does
#:   not say which verdict is which.
type Unpaired = Literal["type_changed", "type_not_recorded", "name_shared"]


@dataclass(frozen=True, slots=True)
class PairedCheck:
    """A check whose verdicts were paired by name: its type, unchanged, and
    its identity in each run. A changed identity is a changed check: its
    rubric, or another of the settings that make it what it is."""

    check: str
    check_type: CheckType
    before_id: str
    after_id: str

    @property
    def changed(self) -> bool:
        return self.before_id != self.after_id


@dataclass(frozen=True, slots=True)
class UnpairedCheck:
    """A check whose verdicts were not paired, and why. `before` and `after`
    are its types where it has them."""

    check: str
    why: Unpaired
    before: CheckType | None = None
    after: CheckType | None = None


@dataclass(frozen=True, slots=True)
class VerdictChange:
    """One reviewed answer whose verdict changed for one paired check.

    `toward` is `True` where the new verdict is the person's and the old one
    was not, `False` where it moved away from hers, and `None` where either
    side could not be judged, which is toward nothing."""

    case_id: str
    check: str
    held_out: bool
    before: Status
    after: Status
    toward: bool | None


@dataclass(frozen=True, slots=True)
class RubricComparison:
    """The comparison of a re-judge with the run it was made from.

    `answers` is the reviewed answers it read: in both runs, with a person's
    verdict in the re-judge. `changes` names the held-in ones that changed;
    a held-out answer is counted, never named, in `held_out_changes`, as the
    agreement reading counts it. (ADR 0067 §1 (e))
    """

    source: str
    answers: int
    paired: tuple[PairedCheck, ...]
    unpaired: tuple[UnpairedCheck, ...]
    changes: tuple[VerdictChange, ...]
    held_out_changes: int
    #: `False` where the front end could not read the source run, which it
    #: says rather than leaving the comparison out in silence; every figure
    #: above is then empty. Built by `unread`.
    read: bool = True

    @classmethod
    def unread(cls, source: str) -> RubricComparison:
        """The comparison of a re-judge whose source could not be read."""
        return cls(source, 0, (), (), (), 0, read=False)


def rubric_comparison(source: Run, rejudged: Run) -> RubricComparison | None:
    """`rejudged` against `source`, the run it was re-judged from, or `None`
    where `rejudged` declares no source or no reviewed answer is in both.

    Refused across tenants, as every operation that pairs two runs is
    (fixed decision 8).
    """
    if rejudged.rejudged_from is None:
        return None
    if source.tenant != rejudged.tenant:
        raise DifferentTenantsError(
            f"cannot compare across tenants: the re-judge is {rejudged.tenant!r}, "
            f"the run it was made from is {source.tenant!r}"
        )
    earlier = {case.case_id: case for case in source.results}
    pairs: list[tuple[CaseResult, CaseResult]] = []
    for case in rejudged.results:
        before = earlier.get(case.case_id)
        reviewed = case.reviewed
        if reviewed is None or reviewed.good is None:
            continue
        if before is None or before.reviewed is None:
            continue
        pairs.append((before, case))
    if not pairs:
        return None

    # The checks the person said something about, in the order the re-judge
    # wrote them, each with what pairing it found.
    order: list[str] = []
    for _, after in pairs:
        assert after.reviewed is not None
        for verdict in after.verdicts:
            name = verdict.score.name
            expected = after.reviewed.expects_pass(verdict.assertion_id)
            if expected is not None and name not in order:
                order.append(name)

    paired: list[PairedCheck] = []
    unpaired: list[UnpairedCheck] = []
    for name in order:
        olds = [v for before, _ in pairs for v in _named(before.verdicts, name)]
        news = [v for _, after in pairs for v in _named(after.verdicts, name)]
        if not olds:
            # A check the source did not run on these answers: nothing to pair.
            continue
        shared = any(
            len(_named(case.verdicts, name)) > 1 for pair in pairs for case in pair
        )
        # Annotated: a comprehension over a `Literal` widens it to `str`.
        old_types: set[CheckType | None] = {v.check_type for v in olds}
        new_types: set[CheckType | None] = {v.check_type for v in news}
        old_type = _one(old_types)
        new_type = _one(new_types)
        if shared:
            unpaired.append(UnpairedCheck(name, "name_shared", old_type, new_type))
        elif None in old_types:
            unpaired.append(UnpairedCheck(name, "type_not_recorded", None, new_type))
        elif old_types != new_types or old_type is None:
            unpaired.append(UnpairedCheck(name, "type_changed", old_type, new_type))
        else:
            assert new_type is not None
            paired.append(
                PairedCheck(
                    check=name,
                    check_type=new_type,
                    before_id=min(v.assertion_id for v in olds),
                    after_id=min(v.assertion_id for v in news),
                )
            )

    named = {check.check for check in paired}
    changes: list[VerdictChange] = []
    held_out = 0
    for before, after in pairs:
        reviewed = after.reviewed
        assert reviewed is not None
        for verdict in after.verdicts:
            name = verdict.score.name
            expected = reviewed.expects_pass(verdict.assertion_id)
            if name not in named or expected is None:
                continue
            olds = _named(before.verdicts, name)
            if not olds or olds[0].status == verdict.status:
                continue
            if reviewed.held_out:
                held_out += 1
                continue
            changes.append(
                VerdictChange(
                    case_id=after.case_id,
                    check=name,
                    held_out=False,
                    before=olds[0].status,
                    after=verdict.status,
                    toward=_toward(olds[0].status, verdict.status, expected),
                )
            )
    return RubricComparison(
        source=rejudged.rejudged_from,
        answers=len(pairs),
        paired=tuple(paired),
        unpaired=tuple(unpaired),
        changes=tuple(changes),
        held_out_changes=held_out,
    )


def _named(verdicts: Sequence[Verdict], name: str) -> list[Verdict]:
    return [v for v in verdicts if v.score.name == name]


def _one(types: set[CheckType | None]) -> CheckType | None:
    """The type, where the run gives the name one; `None` otherwise."""
    return next(iter(types)) if len(types) == 1 else None


def _toward(before: Status, after: Status, expected: bool) -> bool | None:
    if "error" in (before, after):
        return None
    return (after == "pass") == expected
