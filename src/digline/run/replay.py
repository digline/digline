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

from collections.abc import Mapping, Sequence
from dataclasses import replace

from digline.core import RecordedResponse, Run, restore_output
from digline.run.driver import Mapper, Response, default_mapper, execute
from digline.run.suite import Case, Suite

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
        )


def _check(suite: Suite, source: Run) -> None:
    """The four refusals, in the order a reader meets them.

    Each one names what is missing, because each is a different mistake: a suite
    that never recorded, a suite that has since changed how many times it asks,
    a document that kept its answers back, and a perimeter being crossed.
    """
    if source.tenant != suite.tenant:
        raise ReplayError(
            f"the stored run belongs to tenant {source.tenant!r} and this "
            f"suite is {suite.tenant!r}: a replay does not cross a perimeter, "
            "for the reason a comparison does not"
        )

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


def rejudge(
    suite: Suite,
    source: Run,
    *,
    key: str,
    created_at: str,
    mapper: Mapper = default_mapper,
    git_commit: str | None = None,
    run_metadata: Mapping[str, object] | None = None,
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
    - `config_hash` is the current suite's: the rules moving is the point.

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
    )
    return replace(
        produced,
        target_config=source.target_config,
        artifacts=dict(source.artifacts),
        rejudged_from=key,
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
