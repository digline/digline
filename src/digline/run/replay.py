"""Re-judging a stored run: the honest answer to a response cache.

A cache hands back an old answer *as though it were a new one*: nothing in the
resulting document says the model was never asked, so a suite can go green
against answers produced by a model that has since been replaced. That is fixed
decision 3's vacuously green assertion arriving through the plumbing.

What this does instead is replay a stored run's recorded answers through the
**current** suite's assertions and write a run that declares where the answers
came from — `Run.rejudged_from` — so no reader and no pipeline can mistake it
for a measurement. It costs no call to the target and every call to the judge,
which is the whole point: what is under examination is the judge, or the
threshold, or the rubric.

Every refusal here is a refusal to produce a *weaker* measurement wearing the
declared suite's name. (ADR 0015 §6)
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace

from digline.core import (
    Before,
    MaxSteps,
    Never,
    RecordedResponse,
    Run,
    Subsequence,
    ToolCalledWith,
    restore_output,
)
from digline.run.driver import (
    Mapper,
    Response,
    default_mapper,
    execute,
    live_step,
)
from digline.run.suite import TRAJECTORY_CHECKS, Case, Suite

__all__ = ["Replay", "ReplayError", "rejudge"]


class ReplayError(Exception):
    """Raised when a stored run cannot be replayed through this suite."""


class Replay:
    """A target that answers out of a stored run, in the order it answered.

    Stateful, which a target is allowed to be — it is any callable — and here it
    has to be: `Suite.samples` means the driver asks the same case N times, and
    what a replay owes it is the N *different* answers that were recorded, not
    the first one N times.

    Everything it could refuse is refused in `__init__`, before the driver is
    started and before a judge is paid. A refusal discovered on case thirty-seven
    is a refusal that has already cost money.
    """

    def __init__(self, suite: Suite, source: Run) -> None:
        _check(suite, source)
        self._source = source
        self._pending: dict[str, list[RecordedResponse]] = {
            case.case_id: list(case.responses) for case in source.results
        }

    def __call__(self, case: Case) -> Response:
        queue = self._pending.get(case.id)
        if not queue:
            # Unreachable through `rejudge`, which counts every case up front.
            # Kept because a `Replay` is constructible on its own, and a target
            # that ran out of answers must say so rather than repeat one.
            raise ReplayError(
                f"case {case.id!r} has no recorded answer left in run "
                f"{self._source.created_at}: a replay hands back what was "
                "recorded, and repeating one would be a sample nobody measured"
            )
        answer = queue.pop(0)
        assert answer.output is not None and answer.kind is not None
        return Response(
            output=restore_output(answer.output, answer.kind),
            input=answer.input,
            cost_usd=answer.cost_usd,
            latency_ms=answer.latency_ms,
            metadata=_reported_trajectory(answer),
        )


def _reported_trajectory(answer: RecordedResponse) -> Mapping[str, object]:
    """What a trajectory assertion reads, rebuilt from what was recorded.

    This is the half of a replay that did not exist, and its absence was not
    cosmetic: `Response.metadata` was never reconstructed, so a replayed
    `ToolsCalled` read an empty mapping, took its *nobody reported* branch and
    returned **error** — a declared gate quietly becoming a row nobody gated on,
    which is exactly what ADR 0015 §1 made `cost_usd` ride the record to avoid.
    (ADR 0018 §4)

    **Both keys or neither.** `tools` is what `ToolsCalled` reads and
    `tool_calls` what `ToolCalledWith` reads; writing one without the other
    would answer one assertion and error the other over the same recording.

    **From schema 23, what was recorded is handed back as recorded.** `tools`
    comes from the document where it was recorded, and `finish` beside it, so a
    reply that ended on a tool call and named none, or whose two lists
    disagreed, is judged on the trajectory the live run judged. Where `tools`
    was not recorded — every document before 23 — the names are derived from
    `tool_calls` as before, so an older document replays exactly as it did.
    `tools` may now arrive without `tool_calls`: the one assertion that reads
    the calls is refused that replay by `_check`. (ADR 0057)

    **`()` is not `None`, and collapsing them was a defect.** A recorded
    response carrying no calls is a target that reported *the model called
    nothing* — a real measurement, which `ToolsCalled` scores rather than
    errors. Returning `{}` for it made the replay say *nobody reported*, so an
    honest run in which the agent answered from memory could not be re-judged at
    all: it scored `fail` when it was measured and was refused when it was
    replayed. The distinction is the whole reason `Completion.tools` separates
    the two, and the replay now preserves it — empty keys for an empty
    trajectory, no keys only where the response is one `_check` has already
    refused. (0.12.1, from the release delta-pass)
    """
    # `None` reaches here only where the suite declares **no** trajectory
    # assertion — `_check` refuses it otherwise, before a judge is paid. Nothing
    # reads these keys on that path, so the honest answer is to write neither
    # rather than to invent `tools: []` and claim the model called nothing about
    # a target that never said so.
    #
    # An `assert` stood here for an hour and was wrong: it read the refusal as a
    # universal invariant when the refusal is conditional on the suite, so every
    # replay of a plain-function target died with `AssertionError`. The guard
    # belongs where the fact is known, which is `_check`.
    found: dict[str, object] = {}
    if answer.tools is not None:
        found["tools"] = list(answer.tools)
    elif answer.tool_calls is not None:
        found["tools"] = [call.tool for call in answer.tool_calls]
    if answer.tool_calls is not None:
        found["tool_calls"] = [
            {
                "tool": call.tool,
                "arguments": call.arguments,
                "result": call.result,
                "status": call.status,
                "result_absence": call.result_absence,
            }
            for call in answer.tool_calls
        ]
    if answer.finish is not None:
        found["finish"] = answer.finish
    # The steps, in the live form `steps_as_reported` writes: a tool step
    # carries its call as `tool_calls` carries it here, so the checks that
    # read both find the same calls. Absent where not recorded, which is every
    # document before schema 23. (ADR 0060 §5)
    if answer.steps is not None:
        found["steps"] = [live_step(step) for step in answer.steps]
    return found


def _serves(check: object, answer: RecordedResponse) -> bool:
    """Whether a recorded answer gives back what this trajectory check reads.
    (ADR 0057; ADR 0060 §4, §5)"""
    if isinstance(check, ToolCalledWith):
        # The arguments, which only `tool_calls` carries.
        return answer.replayable_trajectory
    if isinstance(check, MaxSteps):
        # The steps and nothing else: no fallback counts turns.
        return answer.replayable_steps
    if isinstance(check, Subsequence | Before | Never):
        return answer.replayable_steps or answer.replayable_tools
    # `ToolsCalled`: the names, recorded or derived from the calls.
    return answer.replayable_tools


def _check(suite: Suite, source: Run) -> None:
    """The five refusals, in the order a reader meets them.

    Each one names what is missing, because each is a different mistake: a suite
    that never recorded, a suite that has since changed how many times it asks,
    a document that kept its answers back, a perimeter being crossed, and a
    suite that judges a trajectory over a run that recorded none.

    The fifth is a refusal rather than an errored check on purpose: an errored
    check *is* the defect ADR 0018 was written to close, so a replay that
    produced one quietly would be the gate-that-is-not-a-gate wearing a
    different hat. (ADR 0018 §4)
    """
    if source.tenant != suite.tenant:
        raise ReplayError(
            f"the stored run belongs to tenant {source.tenant!r} and this "
            f"suite is {suite.tenant!r}: a replay does not cross a perimeter, "
            "for the reason a comparison does not"
        )

    # Which assertions would read a trajectory. Named types rather than a
    # protocol because the two that read one are the two the core ships, and a
    # third-party assertion that reads `metadata["tool_calls"]` is not
    # discoverable from here — it gets the errored check, which is the outcome
    # this refusal exists to spare the two that *are* knowable.
    trajectory_checks = [
        assertion
        for assertion in suite.assertions
        if isinstance(assertion, TRAJECTORY_CHECKS)
    ]

    recorded = {case.case_id: case for case in source.results}
    if not any(case.responses for case in source.results):
        raise ReplayError(
            "the stored run recorded no answers, so there is nothing to "
            "re-judge. Recording is opt-in: set `record_responses=True` on the "
            "suite and run it again — a run already produced cannot gain "
            "answers nobody kept"
        )

    for case in suite.cases:
        if case.suspended is not None:
            # Never called, so it recorded nothing, and the driver will set it
            # aside again exactly as it did the first time.
            continue
        if case.calibration is not None:
            # It carries its own answer and the driver never asks the target for
            # it, so ADR 0015 §6's second refusal does not apply: a replay
            # re-judges it from the declaration, exactly as a live run does.
            # (ADR 0024 §4.7)
            continue
        if case.reviewed_answer is not None:
            # The same: the answer is the person's, in the declaration, and the
            # target is never asked for it. (ADR 0059 §1)
            continue
        stored = recorded.get(case.id)
        if stored is None or not stored.responses:
            raise ReplayError(
                f"case {case.id!r} has no recorded answer in the stored run. A "
                "case added since it was produced cannot be re-judged from it, "
                "and judging the rest would be a narrower measurement carrying "
                "the declared suite's name"
            )
        held = [r for r in stored.responses if not r.replayable]
        if held:
            why = (
                "withheld at a boundary"
                if held[0].withheld
                else "over the size ceiling"
            )
            raise ReplayError(
                f"case {case.id!r} has a recorded answer that is {why}, so it "
                "cannot be judged again. A partial replay is a weaker "
                "measurement claiming to be the declared one — the rule the "
                "driver already applies when one call of a sampled case fails"
            )
        if len(stored.responses) != suite.samples:
            raise ReplayError(
                f"case {case.id!r} recorded {len(stored.responses)} answer(s) "
                f"and this suite samples {suite.samples} time(s). A replay at "
                "one count over a run taken at another is a different "
                "measurement wearing the suite's name: set `samples` to what "
                "was recorded, or produce a new run"
            )
        # Each check asks for what it reads. `ToolCalledWith` reads the calls,
        # which only `tool_calls` carries. `ToolsCalled` reads the names, which
        # schema 23 records as `tools` and which `tool_calls` can still give,
        # so a target that reported names and no calls is re-judged on them
        # rather than refused. The three on order read the steps or the names;
        # `MaxSteps` reads the steps alone, which a document before schema 23
        # never holds. (ADR 0057; ADR 0060 §4, §5)
        unserved = [
            check
            for check in trajectory_checks
            if not all(_serves(check, r) for r in stored.responses)
        ]
        counted = [check for check in unserved if isinstance(check, MaxSteps)]
        if counted:
            raise ReplayError(
                f"case {case.id!r} has a recorded answer with no steps, and this "
                f"suite holds {counted[0].name!r}, which counts them. Steps are "
                "recorded from schema 23, where the target reported them, so a "
                "run produced before, or by a target that reports none, cannot "
                "give them back. Re-judge without it, or produce a new run"
            )
        if unserved:
            raise ReplayError(
                f"case {case.id!r} has a recorded answer from a target that "
                f"reported no trajectory, and this suite holds "
                f"{unserved[0].name!r}, which judges one. The run was "
                "produced before trajectories were recorded, or by a target "
                "that does not report them — so re-judging it would error that "
                "check rather than measure it, which is a declared gate "
                "becoming a row nobody gated on. Produce a new run with a "
                "target that reports its trajectory"
            )


def rejudge(
    suite: Suite,
    source: Run,
    *,
    key: str,
    created_at: str,
    mapper: Mapper = default_mapper,
    git_commit: str | None = None,
    run_metadata: Mapping[str, object] | None = None,
    pricing: str = "",
    judge_samples: int = 0,
    on_unpriced: Callable[[str], None] | None = None,
) -> Run:
    """Judge `source`'s recorded answers with `suite`, and say so in the run.

    What is fresh and what is carried through follows from what actually
    happened, which is the whole discipline of this function:

    - the **judge** configuration is measured now, because the judge really ran
      and is the thing under examination;
    - the **target** configuration and the **artifacts** are carried from the
      source, because they describe the system and the prompt that produced
      these answers — recording today's prompt beside yesterday's answers would
      claim one produced the other;
    - `created_at`, `git_commit` and `digline_version` are this evaluation's,
      because this evaluation is happening now;
    - `config_hash` is the current suite's: the rules moving is the point. Its
      declared price is `pricing`, the digest of the target the suite would run
      today — the replay wrapper answers from stored responses and declares no
      price of its own (ADR 0022 §4).

    `judge_samples` asks each judged check that many times per recorded answer
    and stamps the count on the run: what each verdict records is unchanged, and
    the judge's own range is in its metadata (ADR 0024 §5).

    The run it returns cannot be promoted (`ReplayedRunError`), which is ADR
    0015 §7 and is enforced in the store rather than here: a value does not know
    what a caller intends to do with it.
    """
    produced = execute(
        suite,
        Replay(suite, source),
        created_at=created_at,
        mapper=mapper,
        git_commit=git_commit,
        run_metadata=run_metadata,
        pricing=pricing,
        judge_samples=judge_samples,
        # A re-judge pays the judge, so the judge's sentences reach the front
        # end as `run`'s do, once each, after the run. (ADR 0004 §8.3)
        on_unpriced=on_unpriced,
    )
    return replace(
        produced,
        target_config=source.target_config,
        artifacts=dict(source.artifacts),
        rejudged_from=key,
        judge_samples=judge_samples,
        # The answers are the source's, so is what is known of the modules that
        # produced them. (ADR 0052, decision 2)
        modules_unchecked=source.modules_unchecked,
    )


def replayable_cases(source: Run) -> Sequence[str]:
    """Which cases of a stored run carry answers that can be judged again.

    For a front end that wants to say what a replay will cover before it starts
    — the same courtesy `planned_calls` pays before a real run.
    """
    return tuple(
        case.case_id
        for case in source.results
        if case.responses and all(r.replayable for r in case.responses)
    )
