"""The classifier under test — the part you would replace with your own.

It decides whether an expense report needs a human to look at it. Deterministic
given a run and a sample, and *not* the same on every sample: a real classifier
near its own boundary answers differently when asked twice, and a suite that
never sees that measures a system nobody runs.

No API key: the point of the example is the evaluation, not the model.
"""

from __future__ import annotations

import hashlib
from collections import Counter
from pathlib import Path
from typing import Any

#: Reports the classifier is sure about, one way or the other.
_CLEAR_REVIEW = {"amount_over_cap", "no_receipt", "duplicate_claim", "weekend_bar"}
_CLEAR_APPROVE = {"taxi_short", "coffee_two", "train_standard", "hotel_capped"}

#: The handful it is genuinely unsure about. A classifier that wobbled on
#: everything would not be in production; one that wobbles on nothing does not
#: exist.
_WOBBLY = {"dinner_client", "taxi_long", "hotel_over", "lunch_team"}

_run_index: int | None = None
_calls: Counter[str] = Counter()


def _run_seed() -> int:
    """Which run this is. Only `digline run` calls the target, so only a run
    advances it — `compare` and `promote` import the suite and leave it alone."""
    global _run_index
    if _run_index is None:
        counter = Path(".wobble")
        seen = int(counter.read_text()) if counter.exists() else 0
        counter.write_text(str(seen + 1))
        _run_index = seen
    return _run_index


def _coin(*parts: object) -> float:
    """A stable number in [0, 1) from whatever it is given.

    A hash and not `random`: it has to give the same answer on this machine and
    on the next one, and be different for each (run, case, sample).
    """
    raw = "|".join(str(part) for part in parts).encode("utf-8")
    return int.from_bytes(hashlib.sha256(raw).digest()[:4], "big") / 2**32


def classify(case_id: str, report: dict[str, Any]) -> dict[str, Any]:
    """Replace the body with a call to your model, or your model's client."""
    sample = _calls[case_id]
    _calls[case_id] += 1

    if case_id in _CLEAR_REVIEW:
        confidence = 0.90 + 0.05 * _coin(_run_seed(), case_id, sample)
        return {"decision": "review", "confidence": round(confidence, 3)}
    if case_id in _CLEAR_APPROVE:
        confidence = 0.88 + 0.05 * _coin(_run_seed(), case_id, sample)
        return {"decision": "approve", "confidence": round(confidence, 3)}

    # Everything else sits near the boundary. Most of those the classifier still
    # answers the same way every time — including the ones it gets wrong, which
    # is what an error floor is. A few genuinely wobble, and those are why
    # `samples=5` is in the suite.
    leaning = float(report.get("amount_eur", 0)) > 120 or not report.get("receipt")
    if case_id in _WOBBLY and _coin(_run_seed(), case_id, sample) < 0.15:
        leaning = not leaning
    decision = "review" if leaning else "approve"
    return {"decision": decision, "confidence": 0.55 + 0.1 * _coin(case_id, sample)}
