"""The promotion conditions, callable on their own.

`promote_baseline` is held to eight conditions, and they live in **three
places** because they answer three different questions:

1. **The reading.** Conditions 1 and 7 — tenant and suite — ask whether the
   document says it is where it was found. That is a question about the read,
   and it is answered as the run is read (`read_run`).
2. **The document.** Conditions 2, 3, 4, 5 and 6 answer from the run alone.
   Anybody, anywhere, holding the same document gets the same answer, so they
   are a function: `refusals_for`.
3. **The write.** Condition 8 asks whether the baseline present *now* is still
   the one the run was compared against. That is a question about the store at
   this instant, and it belongs to each backend, beside its own write.

**Why 8 is not in `refusals_for`, since a single call would have been tidier.**
Taking the current baseline's key as a parameter would mean somebody had
already read it, and between that read and the write sits the window ADR 0031
leaves open in *Not decided here* (*"The check and the rename are two system
calls… Closing that needs a lock."*). One function would not close that window:
it would **hide** it, because the call would look like a complete check while
reporting a fact one instant old. Each backend closes it with what it has — an
in-process lock, a transaction — in the same gesture as the write.
`refusal_for_a_moved_baseline` below writes 8's sentence and makes no claim
about when the baseline was read; the reading, and the lock around it, are the
backend's.

Here and not in `digline.core`: these raise the types `store.protocol` defines,
and nothing under `core/` may import `store` (`tests/test_layering.py`). The
helpers the conditions lean on — `unreconciled`, `scale_lost`, `key_of` — are
core, and are imported from there.
"""

from __future__ import annotations

from digline.core.calibration import scale_lost
from digline.core.reconcile import unreconciled
from digline.core.run import Run, key_of
from digline.store.protocol import (
    BaselineMovedError,
    ConfigMismatchError,
    ErroredRunError,
    ReplayedRunError,
    UncalibratedRunError,
)

__all__ = [
    "PromotionRefusal",
    "refusal_for_a_moved_baseline",
    "refusals_for",
]

#: What `refusals_for` can return. A closed set: a condition that needs a type
#: not named here is a change to this union and to the protocol's list, which
#: is the point of writing it down rather than returning bare `Exception`.
type PromotionRefusal = (
    ConfigMismatchError | ReplayedRunError | ErroredRunError | UncalibratedRunError
)


def refusals_for(run: Run, expected_config_hash: str) -> tuple[PromotionRefusal, ...]:
    """Every refusal the document itself carries, in the order they are owed.

    Empty when the document refuses nothing — the idiom `unreconciled` and
    `scale_lost`, the two functions this one leans on, already use for *nothing
    wrong*.

    **The order is the contract, not the order of a body.** Condition 6 comes
    before 3 because it is the stronger statement: it names the checks and not
    only the cases, and a run that does not reconcile does not know what it
    measured (ADR 0027 §3). The two share an exception type, so before this was
    a sequence you could look at, the order could only be inferred from which
    exception escaped.

    **A caller raises the first and is meant to choose that**: the tuple exists
    so that the choice — the first, all of them, none — stays with whoever
    calls. `FileResultStore` raises `refusals[0]`, which is what the body it
    replaced did.

    Silent about conditions 1 and 7, which belong to the reading, and about 8,
    which belongs to the write. See this module's docstring for why that is
    three places and not one.

    The run is named by the key its own document claims —
    `key_of(run.created_at, run.config_hash)` — because that is the only key a
    function holding nothing but the run can compute, and the only one a
    baseline has at all.
    """
    key = key_of(run.created_at, run.config_hash)
    refusals: list[PromotionRefusal] = []

    if run.config_hash != expected_config_hash:
        refusals.append(
            ConfigMismatchError(
                f"run {key} was produced with config_hash "
                f"{run.config_hash}, the current configuration is "
                f"{expected_config_hash}: promoting it would record scores "
                "obtained under a configuration other than the one in force"
            )
        )

    if run.rejudged_from is not None:
        refusals.append(
            ReplayedRunError(
                f"run {key} was judged from the recorded answers of "
                f"{run.rejudged_from}, not from the target. Promoting it would "
                "make a reference out of a measurement the target never took "
                "part in: its interval is the judge's wobble alone, and every "
                "ordinary movement of the target would then read as beyond the "
                "noise. Promote a run that measured"
            )
        )

    # Before the general refusal below, which would also fire: this is the
    # stronger statement and it names the checks, not only the cases. A run
    # that does not reconcile does not know what it measured, and a reference
    # nobody can say that of is no reference. (ADR 0027 §3)
    gaps = unreconciled(run)
    if gaps:
        named = ", ".join(f"{case} · {check}" for case, check in gaps)
        refusals.append(
            ErroredRunError(
                f"run {key} does not reconcile with what its suite asked, at "
                f"{len(gaps)} check(s) ({named}): this is not a regression, and "
                "what the run measured is not known. A baseline has to be a "
                "measurement somebody can state; run the suite again"
            )
        )

    errored = sorted(
        {
            case.case_id
            for case in run.results
            for verdict in case.verdicts
            if verdict.status == "error"
        }
    )
    # Condition 3 says *any* verdict, and a run-level one is a verdict: an
    # aggregate in `error` is a figure nobody has, and a reference missing its
    # gate is no reference either. Read here and not in the exit code, which
    # ADR 0010 §8 keeps on case verdicts only. (#374)
    figures = sorted(
        {verdict.score.name for verdict in run.aggregate if verdict.status == "error"}
    )
    if errored or figures:
        what: list[str] = []
        remedies: list[str] = []
        if errored:
            what.append(f"{len(errored)} case(s) ({', '.join(errored)})")
            remedies.append("fix the case or remove it from the suite")
        if figures:
            what.append(f"{len(figures)} run-level check(s) ({', '.join(figures)})")
            # Not "fix the figure": an aggregate that cannot be computed is the
            # suite asking a question its cases cannot answer. (ADR 0010 §8)
            remedies.append("change the suite so the check can be computed")
        remedy = ", and ".join(remedies)
        refusals.append(
            ErroredRunError(
                f"run {key} could not judge {' and '.join(what)}: a baseline is "
                "an approved reference and an error is not one. "
                f"{remedy[0].upper()}{remedy[1:]}; promoting it would freeze a "
                "red line no reader could tell apart from a new failure"
            )
        )

    lost = scale_lost(run)
    if lost:
        names = ", ".join(sorted({item.case_id for item in lost}))
        refusals.append(
            UncalibratedRunError(
                f"run {key} has {len(lost)} calibration case(s) outside "
                f"their declared band ({names}): the judged scores in it are not "
                "placed on the scale they are compared on, and a reference "
                "scored by a judge that lost its scale hides the loss for as "
                "long as it stands. Promote a run whose calibration held"
            )
        )

    return tuple(refusals)


def refusal_for_a_moved_baseline(
    run: Run,
    current: Run | None,
    expected: str | None,
    *,
    removed_by: str,
) -> BaselineMovedError | None:
    """Condition 8's sentence, and only the sentence. `None` when the baseline
    present is the one the caller compared against. (ADR 0031 §4)

    **One answer, not a sequence, and the asymmetry is the information**: five
    conditions can fire at once, this is one question with one answer.

    `current` is the baseline **you** read, inside whatever makes your write
    atomic. This function does no reading and makes no claim about when yours
    happened: the window between that read and the write is yours to close, and
    a lock here would be a lock in the wrong process (ADR 0031, *Not decided
    here*).

    Compared by key, never by the file's bytes: `digline migrate` rewrites every
    committed baseline when the schema moves, and a reference whose bytes
    changed while its verdicts did not is the same reference.

    `removed_by` is the one clause only a backend can write: where a reader
    looks to see what removed a reference that is no longer there. The file
    store passes a `git log --` line; a database would name something else.
    """
    key = key_of(run.created_at, run.config_hash)
    found = None if current is None else key_of(current.created_at, current.config_hash)
    if found == expected:
        return None

    compare = (
        f"Compare it with the current one — digline compare --run {key} — "
        f"and promote with --replacing {found} if it still holds"
    )
    if current is None:
        return BaselineMovedError(
            f"run {key} was not promoted: it was compared against baseline "
            f"{expected}, and that baseline is no longer there — suite "
            f"{run.suite!r} has none now. A reference that disappeared was "
            f"removed by a commit: {removed_by}"
        )
    # The signature's own time where one was recorded, and nothing where it was
    # not: a baseline promoted before `promoted_at` existed was signed at a time
    # nobody wrote down. (ADR 0014 §3)
    when = f" (promoted {current.promoted_at})" if current.promoted_at else ""
    if expected is None:
        return BaselineMovedError(
            f"run {key} was not promoted: --replacing none says suite "
            f"{run.suite!r} has no baseline yet, and it has one: {found}{when}. "
            "Promoting it would replace a reference nobody compared it "
            f"against. {compare}"
        )
    return BaselineMovedError(
        f"run {key} was not promoted: it was compared against baseline "
        f"{expected}, and the baseline of suite {run.suite!r} is now "
        f"{found}{when}. Promoting it would replace a reference nobody "
        f"compared it against. {compare}"
    )
