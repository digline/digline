"""What a `--judge-samples` replay measured about its judge, in one sentence.

**Never the repeatability without the scale.** A judge that has gone binary is
*more* repeatable, not less: every answer at 1.00, every time, is a range of
zero. So the sentence always carries the calibration result beside the range,
and where the suite declares no calibration case it says what that costs —
printed alone, a zero would be fixed decision 3's vacuous green, measured on the
judge. (ADR 0024 §1, §5.4)

It belongs to the command that produced the measurement, `digline rejudge`, and
to nothing else: not to every later report of a re-judged run, and not to
`explain`, whose fact list ADR 0012 §3 closes. Amending that list a third time,
for a place the record does not ask for, would make it stop being closed. If
this measurement ever earns a place in the report, it gets its own decision.

Pure, like the rest of this package.
"""

from __future__ import annotations

from dataclasses import dataclass

from digline.core import Run, at_precision
from digline.report.render import fmt_score
from digline.report.text import Locale, phrase, strings

__all__ = ["judge_reading"]


@dataclass(frozen=True, slots=True)
class _Widest:
    check: str
    case_id: str
    answer: int
    low: float
    high: float
    count: int


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


def judge_reading(run: Run, *, locale: Locale) -> str:
    """The judge's widest range on one answer, and the calibration beside it.

    The widest across every judged verdict of the run, in the run's own order —
    cases as recorded, checks as declared — and on a tie the first one met, for
    the rule `fold_judgements` applies inside a verdict: identical data names
    the same answer every time.
    """
    strings(locale)
    widest: _Widest | None = None
    errored = 0
    count = run.judge_samples
    for case in run.results:
        for verdict in case.verdicts:
            metadata = verdict.score.metadata
            errored += int(_number(metadata.get("judge_errored")) or 0)
            low = _number(metadata.get("judge_min"))
            high = _number(metadata.get("judge_max"))
            answer = _number(metadata.get("judge_answer"))
            if low is None or high is None or answer is None:
                continue
            if widest is None or at_precision(high - low) > at_precision(
                widest.high - widest.low
            ):
                widest = _Widest(
                    verdict.score.name, case.case_id, int(answer), low, high, count
                )

    if widest is None:
        text = phrase(locale, "judged.range.none")
    else:
        text = phrase(
            locale,
            "judged.range",
            range=fmt_score(at_precision(widest.high - widest.low)),
            count=widest.count,
            check=widest.check,
            answer=widest.answer,
            case=widest.case_id,
        )
    if errored:
        key = "judged.errored.one" if errored == 1 else "judged.errored.many"
        text += phrase(locale, key, count=errored)
    return text + _calibration(run, locale)


def _calibration(run: Run, locale: Locale) -> str:
    """The calibration result: the first case outside its band, else the first
    calibration case the run holds, else the sentence about declaring none."""
    found: list[tuple[str, dict[str, object]]] = []
    for case in run.results:
        band = case.calibration
        if band is None:
            continue
        verdict = next((v for v in case.verdicts if v.score.name == band.check), None)
        values: dict[str, object] = {
            "case": case.case_id,
            "low": fmt_score(band.low),
            "high": fmt_score(band.high),
        }
        if verdict is None or verdict.score.score is None:
            found.append(("judged.calibration.unjudged", values))
            continue
        values["score"] = fmt_score(verdict.score.score)
        where = "inside" if band.holds(verdict.score.score) else "outside"
        found.append((f"judged.calibration.{where}", values))
    if not found:
        return phrase(locale, "judged.calibration.none")
    key, values = next(
        (item for item in found if item[0] == "judged.calibration.outside"), found[0]
    )
    return phrase(locale, key, **values)
