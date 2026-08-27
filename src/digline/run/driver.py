"""The offline driver: run a declared suite against a target, return a `Run`.

`execute()` returns a `Run` and nothing else. It does not know about the store,
does not read the baseline, does not compare and does not promote. The full
cycle is composition outside the driver — `execute` → `write_run` → `compare` →
`promote_baseline` — and each step stays testable alone. A driver that knew
about the baseline would have two reasons to change.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable

from digline.core import (
    Artifact,
    Assertion,
    CaseOutcome,
    CaseResult,
    EvaluatorInputs,
    Label,
    Output,
    Run,
    Verdict,
    combine_samples,
    error_verdict,
)
from digline.run.suite import Case, Suite

__all__ = [
    "HasArtifacts",
    "Mapper",
    "Preflight",
    "Response",
    "Target",
    "default_mapper",
    "execute",
]

#: A failure message is quoted into a `reason`, which is payload and gets
#: redacted at a boundary — but it still lands in a committed run artifact, and
#: an exception carrying a whole response body would drown the file.
MAX_FAILURE_CHARS = 500


@dataclass(frozen=True, slots=True)
class Response:
    """What a target returns: not yet something that can be judged.

    `input` is the rendered prompt. It belongs here and not on the `Case`
    because rendering happens inside the target — the mapper never sees the
    template being filled — and without it `llm_rubric` would judge an answer
    without knowing the question.
    """

    output: Output
    input: str | None = None
    cost_usd: float | None = None
    latency_ms: float | None = None
    metadata: Mapping[str, object] = field(default_factory=dict[str, object])


class Target(Protocol):
    """The subject under evaluation: a prompt-and-provider pair, an agent, an
    endpoint.

    Deliberately singular. The `prompt × provider` matrix is a loop over several
    targets *above* `execute()`, never inside it — which is what lets the same
    driver work on a single case, the premise of the reactive side and the
    reason the core never learned what a matrix is.
    """

    def __call__(self, case: Case) -> Response: ...


@runtime_checkable
class Preflight(Protocol):
    """A target that can refuse a suite before the first call.

    Optional, and asked for rather than required: a target is a function, and
    most are. A target that composes a prompt from `case.vars` knows things the
    suite cannot check on its own — which variables the template asks for,
    whether the model has a price — and every one of those is cheaper to
    discover before the run than on case thirty-seven.
    """

    def preflight(self, cases: Sequence[Case]) -> None: ...


@runtime_checkable
class HasArtifacts(Protocol):
    """A target that names the files it is made of.

    The prompt is the thing under test (ADR 0003) and a target that builds one
    from a file knows which file. The CLI asks, and merges the answer into what
    the suite declared, so `artifacts=[…]` does not have to repeat a path the
    target already carries.
    """

    def artifacts(self) -> Sequence[Path]: ...


class Mapper(Protocol):
    """The boundary. Everything entering the core enters as `EvaluatorInputs`.

    The online driver will replace only what comes before this: a stream of
    production traces instead of a called target, with mapper and core
    unchanged. If a driver ever needs to reach `EvaluatorInputs` other than
    through a mapper, the boundary has broken.
    """

    def __call__(self, response: Response, case: Case) -> EvaluatorInputs: ...


def default_mapper(response: Response, case: Case) -> EvaluatorInputs:
    """The obvious mapping, for a target that returns what it was asked.

    Case and response metadata are kept under separate keys rather than merged:
    a merge would let one silently overwrite the other, and neither of them
    reaches a `Score` anyway.
    """
    return EvaluatorInputs(
        output=response.output,
        input=response.input,
        expected=case.expected,
        context=case.context,
        cost_usd=response.cost_usd,
        latency_ms=response.latency_ms,
        metadata={"case": dict(case.metadata), "response": dict(response.metadata)},
    )


def _clip(text: str) -> str:
    return text if len(text) <= MAX_FAILURE_CHARS else text[:MAX_FAILURE_CHARS] + "…"


def _failed(suite: Suite, reason: str) -> tuple[Verdict, ...]:
    """Every assertion on this case errors, because none of them could run."""
    return tuple(error_verdict(a, _clip(reason)) for a in suite.assertions)


def _judge(assertion: Assertion, inputs: EvaluatorInputs) -> Verdict:
    """Run one assertion, containing its failure to itself.

    An assertion is supposed to return an errored verdict rather than raise, but
    a third-party one may raise anyway. Catching it here means one broken custom
    assertion errors on its own line instead of killing the whole run.
    """
    try:
        return assertion(inputs)
    except Exception as exc:  # noqa: BLE001 — a broken assertion is `error`, not `fail`
        return error_verdict(
            assertion, _clip(f"assertion raised {type(exc).__name__}: {exc}")
        )


def _run_case(suite: Suite, target: Target, mapper: Mapper, case: Case) -> CaseResult:
    if case.suspended is not None:
        # The skip belongs to the driver, not to the core: an assertion is never
        # asked a question it then has to decline (ADR 0001). The run still
        # records the case, so the suspension is visible downstream.
        return CaseResult(case_id=case.id, verdicts=(), suspended=case.suspended)

    samples: list[EvaluatorInputs] = []
    for _ in range(suite.samples):
        try:
            response = target(case)
        except Exception as exc:  # noqa: BLE001 — a target that raises errors the case
            # The failure cannot be handed to the assertions: they do not read
            # `EvaluatorInputs.metadata`, and teaching them to would reopen the
            # channel ADR 0002 closes. The driver builds the verdicts itself.
            #
            # One failed call errors the whole case, sampled or not: a target
            # that cannot answer has not answered, and a partly-sampled case
            # would be a weaker measurement claiming to be the declared one.
            return CaseResult(
                case_id=case.id,
                verdicts=_failed(suite, f"target raised {type(exc).__name__}: {exc}"),
            )

        try:
            samples.append(mapper(response, case))
        except Exception as exc:  # noqa: BLE001 — same treatment, different diagnosis
            return CaseResult(
                case_id=case.id,
                verdicts=_failed(suite, f"mapper raised {type(exc).__name__}: {exc}"),
            )

    # With one sample `combine_samples` is the identity function, so this is
    # byte for byte what the driver produced before sampling existed.
    floor = 1.0 if suite.min_agreement is None else float(suite.min_agreement)
    return CaseResult(
        case_id=case.id,
        verdicts=tuple(
            combine_samples(
                [_judge(assertion, inputs) for inputs in samples],
                min_agreement=floor,
            )
            for assertion in suite.assertions
        ),
    )


def _outcomes(
    suite: Suite, results: Sequence[CaseResult], over: str
) -> tuple[CaseOutcome, ...]:
    """Every case as the aggregate sees it: its mark, and the verdict of the one
    check named by `over`.

    `Suite` has already refused an `over` that is absent or ambiguous, so a case
    that ran has exactly one verdict under that name — including a case whose
    target raised, where the driver built an errored verdict for every declared
    assertion. A suspended case has none, and is excluded rather than guessed at.
    """
    # Annotated: inferring the dict would widen the Literal to `str`.
    labels: dict[str, Label | None] = {c.id: c.label for c in suite.cases}
    return tuple(
        CaseOutcome(
            case_id=result.case_id,
            label=labels.get(result.case_id),
            verdict=next((v for v in result.verdicts if v.score.name == over), None),
        )
        for result in results
    )


def execute(
    suite: Suite,
    target: Target,
    *,
    created_at: str,
    mapper: Mapper = default_mapper,
    git_commit: str | None = None,
    run_metadata: Mapping[str, object] | None = None,
    artifacts: Mapping[str, Artifact] | None = None,
) -> Run:
    """Run `suite` against `target` and return the resulting `Run`.

    Serial on purpose in this first round: concurrency against real providers
    needs rate-limit keys, adaptive backoff and a single layer owning retries,
    which is an ADR of its own rather than a flag added here.

    `run_metadata` describes *this launch* — which model, which prompt version —
    rather than the declared suite, which is why it is an argument here and not
    a field on `Suite`. It lands in `Run.metadata`, where nothing travels across
    a boundary unless `suite.disclosure` names it.

    `created_at` is passed in rather than read from the clock, so a run stays
    reproducible and the driver's tests stay deterministic; `store.utc_now_iso()`
    exists for callers who want now.
    """
    # Asked before anything is called. A target that can check itself against
    # the suite says so by having the method; the ones that cannot are plain
    # functions and are left alone.
    if isinstance(target, Preflight):
        target.preflight(suite.cases)

    results: Sequence[CaseResult] = tuple(
        _run_case(suite, target, mapper, case) for case in suite.cases
    )
    # Aggregates are computed here because they are *recorded data*: they belong
    # in the run, so they are born where the verdicts are. The core stays pure
    # and `compare()` and the report only read them.
    aggregate = tuple(
        run_assertion(_outcomes(suite, results, run_assertion.over))
        for run_assertion in suite.run_assertions
    )
    return Run(
        tenant=suite.tenant,
        environment=suite.environment,
        suite=suite.name,
        config_hash=suite.config_hash(),
        created_at=created_at,
        git_commit=git_commit,
        results=results,
        aggregate=aggregate,
        metadata=dict(run_metadata or {}),
        # Already read, like `created_at` and `git_commit`: the driver produces
        # a `Run` and opens no files. What the suite *declares* is a list of
        # paths; turning those into bytes is the CLI's job. (ADR 0003)
        artifacts=dict(artifacts or {}),
    )
