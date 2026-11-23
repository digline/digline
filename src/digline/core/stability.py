"""Stability at a fixed rubric: which reviewed answers the judge could not
hold to one verdict. (ADR 0067 §3, as noted 2026-11-22)

A reviewed answer's verdict on a check is **stable** when every judgement of
that check reached the same verdict, and **unstable** otherwise. Three ways,
each enough:

- **across runs**: the runs read gave it different verdicts. The runs read are
  this run and every other run of the suite, in the same perimeter, that holds
  at least one of this run's reviewed answers judged by a check of the same
  identity; they are paired by case and identity, so a run judged under
  another rubric pairs nothing and is not read;
- **within a run**: the samples of one verdict were not all on one side of
  the threshold, or one of them could not judge (`directions`, in
  `digline.core.sampling`). Read on the reviewed answer itself: the
  `uncertain` fact leaves every reviewed answer out, by design, and its
  *near the threshold* half is not a disagreement of the samples;
- **under `--judge-samples`**: the widest answer's `judge_min` and
  `judge_max` fall on the two sides of the threshold.

Only the checks a person said something about are read, on the answers that
carry her verdict. A verdict in error in this run is not read here: it is
unjudged, and the agreement reading already counts it apart.

Pure, from the runs alone. The front end reads the other runs from the store
and hands them in, as it hands in the source of a re-judge.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from digline.core.compare import DifferentTenantsError
from digline.core.run import Run, key_of
from digline.core.sampling import directions
from digline.core.types import Verdict, meets

__all__ = [
    "Instability",
    "Judgements",
    "Stability",
    "Unsteady",
    "reviewed_stability",
]

#: Why a verdict is unstable, the first that holds in this order:
#: - `runs`: the runs read did not give it one verdict;
#: - `samples`: within one run, its samples were not all on one side of the
#:   threshold, or one could not judge;
#: - `judge_samples`: under `--judge-samples`, the widest answer's lowest and
#:   highest score fall on the two sides of the threshold.
type Unsteady = Literal["runs", "samples", "judge_samples"]


@dataclass(frozen=True, slots=True)
class Judgements:
    """Every judgement of one check on one reviewed answer, in every run read,
    and how many of them went against the person's verdict: passed where she
    said no, or failed where she said yes. A judgement that could not judge is
    in `of` and never in `against`. (ADR 0067 §6, as noted 2026-11-22)"""

    against: int
    of: int


@dataclass(frozen=True, slots=True)
class Instability:
    """One reviewed answer whose verdict on one check is unstable, and why."""

    case_id: str
    check: str
    assertion_id: str
    held_out: bool
    why: Unsteady


@dataclass(frozen=True, slots=True)
class Stability:
    """The stability of one run's reviewed answers, read across `runs_read`
    runs, this one included.

    `measured` is true from two runs read: with one, stability across runs
    was not measured, and only what one run shows, its samples, sets an
    answer apart.
    """

    runs_read: int
    unstable: tuple[Instability, ...]
    judgements: tuple[tuple[str, str, Judgements], ...] = ()

    @property
    def measured(self) -> bool:
        return self.runs_read >= 2

    def is_unstable(self, case_id: str, assertion_id: str) -> bool:
        return any(
            item.case_id == case_id and item.assertion_id == assertion_id
            for item in self.unstable
        )

    def judged(self, case_id: str, assertion_id: str) -> Judgements | None:
        """The judgements of that check on that answer, or `None` where it is
        not one this reading read."""
        return next(
            (
                found
                for case, identity, found in self.judgements
                if case == case_id and identity == assertion_id
            ),
            None,
        )


def reviewed_stability(run: Run, others: Sequence[Run] = ()) -> Stability:
    """The stability of `run`'s reviewed answers, read across `run` and
    `others`, the suite's other stored runs.

    An other run is read where it holds one of `run`'s reviewed answers, by
    case, judged by a check of the same identity; one that holds none is not
    counted in `runs_read`. `run` itself among `others`, by key, is passed
    over. Refused across tenants, as every operation that pairs two runs is
    (fixed decision 8).
    """
    own = key_of(run.created_at, run.config_hash)
    wanted: dict[tuple[str, str], tuple[Verdict, bool, bool, str]] = {}
    for case in run.results:
        reviewed = case.reviewed
        if reviewed is None or reviewed.good is None:
            continue
        for verdict in case.verdicts:
            expected = reviewed.expects_pass(verdict.assertion_id)
            if expected is None:
                continue
            wanted[(case.case_id, verdict.assertion_id)] = (
                verdict,
                expected,
                reviewed.held_out,
                verdict.score.name,
            )

    seen: dict[tuple[str, str], list[Verdict]] = {
        key: [found[0]] for key, found in wanted.items()
    }
    read = 1
    for other in others:
        if other.tenant != run.tenant:
            raise DifferentTenantsError(
                f"cannot read stability across tenants: the run is "
                f"{run.tenant!r}, another run of the suite is {other.tenant!r}"
            )
        if key_of(other.created_at, other.config_hash) == own:
            continue
        matched = False
        for case in other.results:
            for verdict in case.verdicts:
                key = (case.case_id, verdict.assertion_id)
                if key in wanted:
                    seen[key].append(verdict)
                    matched = True
        read += matched

    unstable: list[Instability] = []
    judgements: list[tuple[str, str, Judgements]] = []
    for (case_id, identity), (verdict, expected, held_out, name) in wanted.items():
        verdicts = seen[(case_id, identity)]
        against = of = 0
        for each in verdicts:
            passed, failed, errored = _judgements(each)
            against += failed if expected else passed
            of += passed + failed + errored
        judgements.append((case_id, identity, Judgements(against, of)))
        if verdict.status == "error":
            # Unjudged in this run, and counted there: a judge that could not
            # answer here is not read as one that changed its mind.
            continue
        why = _why(verdicts)
        if why is not None:
            unstable.append(Instability(case_id, name, identity, held_out, why))
    return Stability(
        runs_read=read, unstable=tuple(unstable), judgements=tuple(judgements)
    )


def _judgements(verdict: Verdict) -> tuple[int, int, int]:
    """`(passed, failed, errored)` across one verdict's samples, or the
    verdict itself counted once where it kept no sample."""
    counted = directions(verdict)
    if sum(counted):
        return counted
    if verdict.status == "pass":
        return 1, 0, 0
    if verdict.status == "fail":
        return 0, 1, 0
    return 0, 0, 1


def _why(verdicts: Sequence[Verdict]) -> Unsteady | None:
    if len({verdict.status for verdict in verdicts}) > 1:
        return "runs"
    for verdict in verdicts:
        passed, failed, errored = directions(verdict)
        if (passed and failed) or errored:
            return "samples"
    for verdict in verdicts:
        low = verdict.score.metadata.get("judge_min")
        high = verdict.score.metadata.get("judge_max")
        if (
            isinstance(low, int | float)
            and isinstance(high, int | float)
            and meets(float(low), verdict.threshold)
            != meets(float(high), verdict.threshold)
        ):
            return "judge_samples"
    return None
