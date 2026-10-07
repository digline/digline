"""The delete's refusal about the baseline, callable on its own.

`delete_run` asks one question of the baseline: is the suite's current
reference the one promoted from the key being deleted. It is condition 8's
shape turned round. That condition asks what the baseline is *now*, beside the
write. This one asks it beside the removal, for the same reason: the answer is
a fact about the store at this instant, so the read belongs to each backend.
This function writes the sentence and does no reading. (ADR 0044 §3.2)

Here and not in `digline.core` for `promotion.py`'s reason: it returns a type
`store.protocol` defines.
"""

from __future__ import annotations

from digline.core.run import Run, key_of
from digline.store.protocol import PromotedRunError, RunRef

__all__ = ["refusal_for_a_promoted_run"]


def refusal_for_a_promoted_run(
    ref: RunRef, baseline: Run | None
) -> PromotedRunError | None:
    """The refusal owed when `baseline` was promoted from `ref.key`, else `None`.

    Compared by key, never by the run: a baseline whose run was removed by hand
    still rests on that key, and the delete of the key is refused the same way.

    `baseline` is the one **you** read, in the plan, before the first removal.
    A baseline that could not be read is not `None`: the reading's error
    refuses the delete, because *could not look* is not *not under the
    baseline* (#365).
    """
    if baseline is None:
        return None
    if key_of(baseline.created_at, baseline.config_hash) != ref.key:
        return None
    # The signature's own time where one was recorded, and nothing where it was
    # not, as condition 8 says it. (ADR 0014 §3)
    when = f" (promoted at {baseline.promoted_at})" if baseline.promoted_at else ""
    return PromotedRunError(
        f"run {ref.key} of suite {ref.suite} is the one its current baseline "
        f"was promoted from{when}. A delete never removes the run under the "
        "baseline: promote another run first, with `digline promote --suite … "
        f"--run <key> --replacing {ref.key}`, and delete this one after."
    )
