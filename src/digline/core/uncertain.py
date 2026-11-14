"""The judged checks whose verdict on a case is not firm.

Two ways, either enough: the samples of a judged check did not all reach the
same verdict, or their mean sits within a margin of the threshold. The margin
is the check's own tolerance where it declares one, and `DEFAULT_MARGIN`
where it does not; which of the two is said with each case, so a reader
never has to guess the number. A fact about the measurement, read off the run
alone: it moves no exit code and changes no verdict. (P-1685, ADR 0012 §3 as
amended 2026-11-14)

Two kinds of case are left out, whatever their samples. A calibration case,
because its band says more than this would. And a reviewed answer, because
where the judge and the person disagree it has a fact of its own; on the
walkthrough from the IDE, three reviewed answers the judge agreed with
scored 1 against a threshold of 1, and each read as uncertain until they
were left out.

Found in a first use outside the project, on a Java application with a judged
suite: a case passed at 0.71 against 0.70, its three samples 1, 1 and 0, and
nothing a person read said the verdict was a coin flip.
"""

from __future__ import annotations

from dataclasses import dataclass

from digline.core.run import Run
from digline.core.types import Verdict

__all__ = ["DEFAULT_MARGIN", "Uncertain", "uncertain_cases"]

#: The margin where a check declares no tolerance: a `tolerance` of 0 cannot be
#: told from one never written, so both read as none declared.
DEFAULT_MARGIN = 0.05


@dataclass(frozen=True, slots=True)
class Uncertain:
    """One judged check on one case whose verdict is not firm, and why.

    `split` where the samples did not all agree, with `agreement`, the share
    that reached the majority verdict, and `errored`, how many could not
    judge; `near` where the mean is within `margin` of `threshold`.
    `declared` says whether `margin` is the check's tolerance or
    `DEFAULT_MARGIN`.
    """

    case_id: str
    check: str
    score: float
    threshold: float
    margin: float
    declared: bool
    split: bool
    near: bool
    agreement: float | None = None
    errored: int = 0


def _split(verdict: Verdict) -> tuple[bool, float | None, int]:
    metadata = verdict.score.metadata
    samples = metadata.get("samples")
    if not isinstance(samples, int) or samples < 2:
        return False, None, 0
    agreement = metadata.get("agreement")
    errored = metadata.get("errored_samples")
    share = float(agreement) if isinstance(agreement, int | float) else None
    failed = errored if isinstance(errored, int) else 0
    return (share is not None and share < 1.0) or failed > 0, share, failed


def uncertain_cases(run: Run) -> tuple[Uncertain, ...]:
    """Every judged check on a case that passed or failed and is not firm, in
    the run's order. A check in error is not here: it gave no verdict to be
    unsure of, and the unjudged count already says it. Nor is a calibration
    case, whose band says more than this would, nor a reviewed answer, which
    has a fact of its own where the judge and the person disagree: on the
    walkthrough from the IDE, three the judge agreed with scored 1 against a
    threshold of 1 and each read as uncertain."""
    found: list[Uncertain] = []
    for case in run.results:
        if case.calibration is not None or case.reviewed is not None:
            continue
        for verdict in case.verdicts:
            score = verdict.score.score
            if not verdict.judged or verdict.status == "error" or score is None:
                continue
            declared = verdict.tolerance > 0
            margin = verdict.tolerance if declared else DEFAULT_MARGIN
            # The tolerance is a limit like the threshold, and compared at the
            # same precision: a mean of 0.75 against 0.70 is within 0.05.
            near = abs(score - verdict.threshold) <= margin + 1e-9
            split, agreement, errored = _split(verdict)
            if not (split or near):
                continue
            found.append(
                Uncertain(
                    case_id=case.case_id,
                    check=verdict.score.name,
                    score=score,
                    threshold=verdict.threshold,
                    margin=margin,
                    declared=declared,
                    split=split,
                    near=near,
                    agreement=agreement if split else None,
                    errored=errored if split else 0,
                )
            )
    return tuple(found)
