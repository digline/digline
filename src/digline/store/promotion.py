"""The promotion conditions, callable on their own.

`promote_baseline`'s conditions are named in ADR 0002 §8 and not counted
here, for the reason §8 gives. They live in **three places** because they
answer three different questions:

1. **The reading.** Conditions 1 and 7 — tenant and suite — ask whether the
   document says it is where it was found. That is a question about the read,
   and it is answered as the run is read (`read_run`).
2. **The document.** Conditions 2 to 6, 9 and 10 answer from the run, and 10
   from the suite's declaration beside it, which a run document does not carry
   and the caller hands in as it hands in the configuration hash. Anybody,
   anywhere, holding the same two gets the same answer, so they are a
   function: `refusals_for`.
3. **The write.** Condition 8 asks whether the baseline present *now* is still
   the one the run was compared against. That is a question about the store at
   this instant, and it belongs to each backend, beside its own write.
   Condition 11 follows it there, because it is asked of the run **against
   that baseline**: whether a pin is a cause of 2 that nobody named
   (`refusal_for_unaccepted_pins`). Three other causes of 2 are 3, 5 and 10,
   which answer from the run alone and stay in `refusals_for`. (ADR 0053)
   The sixth, `unpaired`, is no condition at all: it holds on exactly the
   re-baseline a person makes after redefining a check, which is the way out
   of it. (#642)

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

import shlex
from collections.abc import Collection

from digline.core.calibration import scale_lost
from digline.core.compare import compare
from digline.core.declared import Declared, cases_that_count, nothing_judged
from digline.core.gate import causes_of_two, pins_implicated
from digline.core.reconcile import unreconciled
from digline.core.run import CrossingRefusedError, Run, crossing_refusal, key_of
from digline.store.protocol import (
    BaselineMovedError,
    ConfigMismatchError,
    ErroredRunError,
    NothingJudgedError,
    ReplayedRunError,
    UnacceptedPinsError,
    UncalibratedRunError,
)

__all__ = [
    "PromotionRefusal",
    "refusal_for_a_moved_baseline",
    "refusal_for_unaccepted_pins",
    "refusals_for",
]

#: What `refusals_for` can return. A closed set: a condition that needs a type
#: not named here is a change to this union and to the protocol's list, which
#: is the point of writing it down rather than returning bare `Exception`.
type PromotionRefusal = (
    ConfigMismatchError
    | ReplayedRunError
    | ErroredRunError
    | UncalibratedRunError
    | CrossingRefusedError
    | NothingJudgedError
)


def refusals_for(
    run: Run, expected_config_hash: str, *, declared: Declared | None
) -> tuple[PromotionRefusal, ...]:
    """Every refusal the document itself carries, in the order they are owed.

    Empty when the document refuses nothing — the idiom `unreconciled` and
    `scale_lost`, the two functions this one leans on, already use for *nothing
    wrong*.

    **The order is the contract, not the order of a body.** Condition 6 comes
    before 3 because it is the stronger statement: it names the checks and not
    only the cases, and a run that does not reconcile does not know what it
    measured (ADR 0027 §3). The two share an exception type, so before this was
    a sequence you could look at, the order could only be inferred from which
    exception escaped. **Condition 9 comes first**, and that is a choice made
    when it was written, not a consequence of ADR 0042, which does not place
    it: an artifact that must not cross is refused until the suite changes,
    whereas a configuration that moved may be the change somebody intended.
    Saying first what has to be repaired anyway saves a round.

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

    # Condition 9, first of the document's (the docstring says why), and
    # whatever the `Disclosure`: a baseline is the complete run, every
    # artifact's text included, written to `baselines/`, which is versioned
    # and gets pushed. Promotion is an exit,
    # and the predicate is the one `redact()` and `run_document` apply.
    # (ADR 0042 §3)
    crossing = crossing_refusal(
        run,
        going=(
            "a baseline carries every artifact's text into baselines/, which is "
            "versioned, whatever the suite discloses"
        ),
    )
    if crossing is not None:
        refusals.append(crossing)

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

    # Condition 10, before 3: never send the reader to the aggregate, which is
    # always the symptom. A run whose every case is suspended errors its
    # aggregates too, and a person told first that a figure could not be
    # computed investigates the figure. Where the cases errored, the cause is
    # the case, so the refusal says, case by case, which of the three states
    # it is in, and carries 3's remedy for the errored ones: an order in a list
    # cannot say "it depends on why", and a sentence can. Read against the
    # suite's declaration, as the exit code reads it, whether or not the suite
    # declares an aggregate. (ADR 0049 §3, §5)
    if nothing_judged(run, declared):
        carried = {case.case_id: case for case in run.results}
        states: list[str] = []
        unjudgeable = False
        for case_id in sorted(cases_that_count(run, declared)):
            case = carried.get(case_id)
            if case is None:
                states.append(f"{case_id} (absent)")
            elif case.suspended is not None:
                states.append(f"{case_id} (suspended)")
            else:
                unjudgeable = True
                states.append(f"{case_id} (could not be judged)")
        remedy = (
            " For a case that could not be judged, fix the case or remove it "
            "from the suite."
            if unjudgeable
            else ""
        )
        refusals.append(
            NothingJudgedError(
                f"run {key} judged none of the {len(states)} case(s) its suite "
                f"measures: {', '.join(states)}. A reference is a measurement, "
                f"and this run measured nothing.{remedy} Run the suite with at "
                "least one of its cases judged"
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

    **One answer, not a sequence, and the asymmetry is the information**: the
    document's conditions can fire together, this is one question with one
    answer.

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


def refusal_for_unaccepted_pins(
    run: Run,
    current: Run | None,
    accepting: Collection[str],
    *,
    declared: Declared | None,
) -> UnacceptedPinsError | None:
    """Condition 11's question and its sentence. `None` when the paths
    `accepting` names are exactly the paths the pin causes implicate, which is
    nothing when no pin cause holds. (ADR 0053)

    `current` is the baseline **you** read for condition 8, inside whatever
    makes your write atomic: the pin causes are relations, and the reference
    they are read against is the one this promotion replaces. `None` is a
    first promotion, where no relation exists and no pin cause can hold.

    **Any cause, not the code.** The causes are `causes_of_two`'s, the tuple
    `exit_code` reads behind a regression; this never asks whether the code is
    2, so a run that drifted and got worse is refused like one that only
    drifted. Only the pin causes are asked here: three of the other four answer
    from the run alone and are conditions 3, 5 and 10, in `refusals_for`.

    **`unpaired` is not asked, here or anywhere a promotion looks.** It is a
    relation like the pin causes, read from this very pair, and on this pair it
    holds exactly when a check was redefined under its name since the reference
    — the change the promotion is there to accept. Refused, the re-baseline that
    clears it could never be made. `tests/test_unpaired.py` holds that it is
    not. (#642)

    **Exactly the set**: a path more is an authorisation for a file that did
    not move, a path fewer leaves a movement nobody named, and both halves of
    a lost pin are one fact, since nothing says whether one file became the
    other. The sentence names the set either way.
    """
    comparison = None if current is None else compare(run, current)
    causes = causes_of_two(run, comparison, declared=declared)
    implicated = (
        pins_implicated(comparison)
        if "pinned_drifted" in causes or "pinned_lost" in causes
        else ()
    )
    accepted = frozenset(accepting)
    if accepted == frozenset(implicated):
        return None

    key = key_of(run.created_at, run.config_hash)
    found = (
        "none" if current is None else key_of(current.created_at, current.config_hash)
    )
    if not implicated:
        return UnacceptedPinsError(
            f"run {key} was not promoted: --accepting-pin named "
            f"{_paths(accepted)}, and against baseline {found} no file declared "
            "not to change moved or lost its path. An authorisation names what "
            "moved; promote without it"
        )

    assert comparison is not None  # a pin cause needs a reference
    what: list[str] = []
    if comparison.pinned_changed:
        what.append(
            f"{_paths(comparison.pinned_changed)} declared not to change moved "
            f"since baseline {found}"
        )
    if "pinned_lost" in causes:
        what.append(
            f"{_paths(comparison.pinned_gone)} declared not to change in baseline "
            f"{found} is gone, and {_paths(comparison.pinned_unreferenced)} "
            "declared not to change here has no reference, so whether one "
            "became the other was not judged"
        )
    named = ""
    if accepted:
        extra = sorted(accepted - set(implicated))
        missing = sorted(set(implicated) - accepted)
        named = f" --accepting-pin named {_paths(accepted)}"
        if extra:
            named += f"; {_paths(extra)} is not among the paths implicated"
        if missing:
            named += f"; {_paths(missing)} is implicated and was not named"
        named += "."
    command = " ".join(
        [
            "digline promote",
            f"--run {shlex.quote(key)}",
            f"--replacing {shlex.quote(found)}",
            *(f"--accepting-pin {shlex.quote(path)}" for path in implicated),
        ]
    )
    return UnacceptedPinsError(
        f"run {key} was not promoted: {'; and '.join(what)}.{named} Promoting it "
        "would make that movement the reference with nobody having named it. "
        f"Compare it — digline compare --run {key} — and if the change was "
        f"meant, accept it from the command line by naming each path: {command}"
    )


def _paths(paths: Collection[str]) -> str:
    """Paths for a sentence, sorted so the same set reads the same way."""
    return ", ".join(sorted(paths))
