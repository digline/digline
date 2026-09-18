"""The offline driver: run a declared suite against a target, return a `Run`.

`execute()` returns a `Run` and nothing else. It does not know about the store,
does not read the baseline, does not compare and does not promote. The full
cycle is composition outside the driver — `execute` → `write_run` → `compare` →
`promote_baseline` — and each step stays testable alone. A driver that knew
about the baseline would have two reasons to change.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, fields, is_dataclass, replace
from pathlib import Path
from typing import Protocol, runtime_checkable

from digline import __version__
from digline.core import (
    MAX_RECORDED_CHARS,
    Artifact,
    Assertion,
    CallTotals,
    CaseOutcome,
    CaseProgress,
    CaseResult,
    Cause,
    ConfigValue,
    EvaluatorInputs,
    HasConfig,
    Label,
    Output,
    RecordedResponse,
    Run,
    RunAssertion,
    RunUsage,
    SystemConfig,
    Usage,
    Verdict,
    combine_samples,
    error_verdict,
    fold_judgements,
    identity_of,
    judged,
    record_output,
    record_trajectory,
    trajectory_chars,
    with_noise_interval,
)
from digline.core.protocols import DeclaresPrice
from digline.run.suite import Calibration, Case, Suite

__all__ = [
    "Billable",
    "HasArtifacts",
    "HasConfig",
    "Mapper",
    "Preflight",
    "Response",
    "Target",
    "default_mapper",
    "execute",
    "judge_config",
    "judge_totals",
    "judges",
    "target_config",
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
    #: What the call consumed, where the target knows. `None` is a target that
    #: reports no counts, which is an honest answer and not a zero.
    #:
    #: **Typed, and the only thing the document reads.** `ProviderTarget` also
    #: copies the four counts into `metadata` for assertions that read them
    #: live, and that copy stays — but a recorded fact whose source is a string
    #: key is a fact one typo away from absent, so the run's totals and the
    #: recorded response are built from this field alone. (ADR 0025 §5)
    usage: Usage | None = None
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
class Billable(Protocol):
    """A judge that can say what it has spent since it was built.

    Asked for rather than required, like every other optional thing a target or
    a judge may answer: an assertion's judge is any object with a `config`, and
    a suite may hold one somebody wrote by hand. `JudgeBase` satisfies this;
    one that does not contributes no line, because a bill nobody kept cannot be
    invented from the outside.

    The three are **monotone for the life of the object and never reset**
    (ADR 0004 §3), so a run's share of them is the difference between a reading
    before the first case and one after the last — which is the only shape that
    stays correct when a suite reuses a judge across runs. (ADR 0025 §4)
    """

    calls: int
    spent_usd: float
    tokens: Usage


@runtime_checkable
class HasArtifacts(Protocol):
    """A target that names the files it is made of.

    The prompt is the thing under test (ADR 0003) and a target that builds one
    from a file knows which file. The CLI asks, and merges the answer into what
    the suite declared, so `artifacts=[…]` does not have to repeat a path the
    target already carries.
    """

    def artifacts(self) -> Sequence[Path]: ...


def target_config(target: object) -> SystemConfig:
    """What the target says it was configured to do, or nothing.

    Asked rather than required, like `preflight()` and `artifacts()`: a `Target`
    is any callable and most are plain functions. One that declares nothing
    records nothing, and nothing is not a change (ADR 0005 §6).

    Bound once per run — `execute()` takes one target — so one configuration per
    run, at the same level `Run.artifacts` sits at. The `prompt x provider`
    matrix is a loop *above* the driver, and each cell is its own run with its
    own configuration.

    Asked twice by `execute()`: before the first case, so a malformed one fails
    before the suite is paid for, and after the last, so a target that could
    only learn its configuration by answering still records one (ADR 0005 §8).
    """
    if not isinstance(target, HasConfig):
        return SystemConfig()
    return SystemConfig(values=dict(target.config))


def judge_config(suite: Suite) -> SystemConfig:
    """The configuration of the instrument that graded, collected from the
    assertions that hold one.

    A judge is bound *per assertion* — `LlmRubric(judge=...)`,
    `Faithfulness(judge=...)`, either of them inside a `Repeated` — so unlike a
    target it has to be found rather than received. The walk follows a wrapper
    through to what it wraps, which is the one place a judge hides.

    **Which** instruments graded is always recorded, one identity per distinct
    `provider/model`, however many there are. That is the half a suite with two
    judges cannot afford to lose: replacing one of two graders is precisely the
    change ADR 0005 §4 exists to catch, and a record that fell silent as soon as
    a suite grew a second judge would go blind exactly there.

    **How** it was set up is recorded only when there is one of them. Judges
    sharing an identity but disagreeing on a scalar record no value for that
    scalar — a `ScoreJudge` capped at 400 tokens beside a `ClaimCountJudge`
    capped at 800 is two set-ups, and writing one down would be a fact nobody
    established. With two identities there is no single set-up at all, and the
    identity list carries the whole answer.

    A judge that declares nothing — no `provider`, no `model` — is passed over
    the way a plain-function target is: what names no instrument records none.
    """
    found = [dict(judge.config) for judge in judges(suite.assertions)]
    declared = [c for c in found if c.get("provider") and c.get("model")]
    if not declared:
        return SystemConfig()

    identities = tuple(
        sorted({identity_of(str(c["provider"]), str(c["model"])) for c in declared})
    )
    if len(identities) > 1:
        return SystemConfig(identities=identities)

    first, rest = declared[0], declared[1:]
    agreed: dict[str, ConfigValue] = {
        key: value
        for key, value in first.items()
        if all(other.get(key, _MISSING) == value for other in rest)
    }
    # `provider` and `model` survive the merge by construction: a single
    # identity is what makes them equal across every judge here.
    return SystemConfig(values=agreed, identities=identities)


#: Distinct from `None`, which is a value a config may legitimately hold.
_MISSING = object()


def judge_totals(suite: Suite) -> CallTotals:
    """What every judge in the suite has spent **since it was built**.

    A reading, not a run's share: `execute()` takes one before the first case
    and one after the last, and the difference is what the run spent
    (ADR 0025 §4).

    **Deduplicated by object identity.** One judge instance bound to two
    assertions is one instrument and one bill; counting it once per assertion
    would double the judging cost of every suite that shares a judge, which is
    most of them. Two distinct instances configured identically are two objects
    and two bills, and they add — correct, and stated in ADR 0025 §4 because a
    reader meets them as one identity in `judge_config` and a total that looks
    like two.

    A judge that cannot say what it spent is passed over entirely: it raises no
    `calls`, so it never widens the gap between `calls` and `counted` with a
    number nobody measured.
    """
    seen: dict[int, Billable] = {}
    for judge in judges(suite.assertions):
        if isinstance(judge, Billable):
            seen.setdefault(id(judge), judge)
    total = CallTotals()
    for judge in seen.values():
        total = CallTotals(
            calls=total.calls + judge.calls,
            counted=total.counted + judge.calls,
            tokens=total.tokens + judge.tokens,
            spent_usd=total.spent_usd + judge.spent_usd,
        )
    return total


def _judge_share(before: CallTotals, after: CallTotals) -> CallTotals:
    """This run's share of what the judges have spent.

    Subtraction, not the later reading: a judge object reused across two runs
    would otherwise report the first run's calls on the second's document. The
    counts cannot go backwards — every field is monotone — so a negative here
    would mean a judge that reset itself, and `CallTotals` refuses it at
    construction rather than recording a negative bill.
    """
    return CallTotals(
        calls=after.calls - before.calls,
        counted=after.counted - before.counted,
        tokens=Usage(
            input_tokens=after.tokens.input_tokens - before.tokens.input_tokens,
            output_tokens=after.tokens.output_tokens - before.tokens.output_tokens,
            cache_read_tokens=(
                after.tokens.cache_read_tokens - before.tokens.cache_read_tokens
            ),
            cache_write_tokens=(
                after.tokens.cache_write_tokens - before.tokens.cache_write_tokens
            ),
        ),
        spent_usd=after.spent_usd - before.spent_usd,
    )


def judges(assertions: Sequence[object]) -> list[HasConfig]:
    """Every configured judge an assertion holds, wrappers followed through.

    Public because the host seeds each one's observed identity when a run is
    resumed (ADR 0017 §7): the judge that graded the first leg has to meet the
    second leg's first reply, or an alias that rolled between them would be
    averaged away instead of raising.

    Read off the dataclass fields rather than from a fixed attribute name:
    `LlmRubric` calls it `judge` today and the next assertion that asks a model
    something may not, and a collector that knew one name would silently record
    nothing for the others — the failure that looks like a passing test.
    """
    found: list[HasConfig] = []
    seen: set[int] = set()
    stack = list(assertions)
    while stack:
        current = stack.pop()
        if (
            id(current) in seen
            or not is_dataclass(current)
            or isinstance(current, type)
        ):
            continue
        seen.add(id(current))
        for declared in fields(current):
            value = getattr(current, declared.name, None)
            if isinstance(value, HasConfig):
                found.append(value)
            elif is_dataclass(value) and not isinstance(value, type):
                stack.append(value)
    return found


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


def recorded(response: Response) -> RecordedResponse:
    """One answer as the document will hold it, or the reason it does not.

    Whole or nothing, and the ceiling applies to `output`, `input` and the
    trajectory together: they are what a re-judge needs *as a set*, so keeping
    one of them would store a question with no answer, an answer with no
    question, or an answer whose calls the document does not admit it dropped.
    Over the ceiling the entry records the measurements and says `oversize`,
    which is a different absence from redaction's and is written as one.
    (ADR 0015 §3, ADR 0018 §1)
    """
    text, kind = record_output(response.output)
    calls = record_trajectory(response.metadata)
    if (
        len(text) > MAX_RECORDED_CHARS
        or (response.input is not None and len(response.input) > MAX_RECORDED_CHARS)
        or trajectory_chars(calls or ()) > MAX_RECORDED_CHARS
    ):
        return RecordedResponse(
            oversize=True,
            cost_usd=response.cost_usd,
            latency_ms=response.latency_ms,
            # Kept with the other measurements: `oversize` is a refusal to store
            # *text*, and four integers are not text.
            usage=response.usage,
        )
    return RecordedResponse(
        output=text,
        kind=kind,
        input=response.input,
        cost_usd=response.cost_usd,
        latency_ms=response.latency_ms,
        tool_calls=calls,
        usage=response.usage,
    )


def _clip(text: str) -> str:
    return text if len(text) <= MAX_FAILURE_CHARS else text[:MAX_FAILURE_CHARS] + "…"


def _stamped(assertion: Assertion, verdict: Verdict) -> Verdict:
    """The verdict, marked when a model placed it on a scale.

    Stamped here, where the assertion and its verdict are both in hand, and not
    by the assertion: `KIND` is a declaration about a class, and the one place
    that reads it for the document is the one place every verdict passes.
    (ADR 0024 §6.4)
    """
    return replace(verdict, judged=True) if judged(assertion) else verdict


def _failed(suite: Suite, reason: str) -> tuple[Verdict, ...]:
    """Every assertion on this case errors, because none of them could run."""
    return tuple(_stamped(a, error_verdict(a, _clip(reason))) for a in suite.assertions)


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


def _graded(
    suite: Suite,
    assertion: Assertion,
    samples: Sequence[EvaluatorInputs],
    judge_samples: int,
) -> Verdict:
    """One check over a case's samples, folded.

    With `judge_samples` below 2, or on a check nothing judges, each sample is
    judged once — byte for byte what the driver always did. Otherwise a judged
    check is asked `judge_samples` times per sample, **serially, in call
    order**, and `fold_judgements` records what a single judgement would have
    recorded and puts the judge's own range in metadata. (ADR 0024 §5)
    """
    floor = 1.0 if suite.min_agreement is None else float(suite.min_agreement)
    if judge_samples < 2 or not judged(assertion):
        return _stamped(
            assertion,
            combine_samples(
                [_judge(assertion, inputs) for inputs in samples], min_agreement=floor
            ),
        )
    return _stamped(
        assertion,
        fold_judgements(
            [
                [_judge(assertion, inputs) for _ in range(judge_samples)]
                for inputs in samples
            ],
            min_agreement=floor,
        ),
    )


def _replaying(target: Target) -> bool:
    """Whether this run is judging stored answers rather than calling anything.

    The import is local because `digline.run.replay` imports this module — the
    same reason `execute()` imports `Replay` inside its own body for
    `judge_samples`.
    """
    from digline.run.replay import Replay

    return isinstance(target, Replay)


def _run_case(
    suite: Suite, target: Target, mapper: Mapper, case: Case, judge_samples: int = 0
) -> tuple[CaseResult, Cause, CallTotals]:
    """The case, which layer errored it, and what its calls consumed.

    The cause rather than the result alone because the journal records it and
    the run document has no field for it (ADR 0017 §3). It is read once, by the
    announcement before a resumed leg, and never acted on automatically.

    The third element is this case's share of the target line. **A call that
    raised is not on it** — neither its money nor a `calls` of its own — on the
    rule `JudgeBase._ask` already follows for the judge: its cost is unknown,
    and counting it at zero would be the undercount that reads as good news.
    A call that returned and whose *mapping* then failed is on it, because the
    target answered and was paid. (ADR 0025 §3)
    """
    if case.suspended is not None:
        # The skip belongs to the driver, not to the core: an assertion is never
        # asked a question it then has to decline (ADR 0001). The run still
        # records the case, so the suspension is visible downstream.
        return (
            CaseResult(
                case_id=case.id,
                verdicts=(),
                suspended=case.suspended,
                canary=case.canary,
            ),
            "",
            # A case nobody called consumed nothing, and that is a measurement
            # rather than an absence: the zero is right here.
            CallTotals(),
        )
    if case.calibration is not None:
        return _calibrate(suite, mapper, case, case.calibration, judge_samples)

    line = CallTotals()
    samples: list[EvaluatorInputs] = []
    # Collected beside the mapped inputs rather than derived from them: what a
    # re-judge replays is what the *target* answered, and `EvaluatorInputs` is
    # already one mapper's reading of it. (ADR 0015 §1)
    answers: list[RecordedResponse] = []
    for _ in range(suite.samples):
        try:
            response = target(case)
        except Exception as exc:  # noqa: BLE001 — a target that raises errors the case
            # The failure cannot be handed to the assertions. What they may read
            # of `EvaluatorInputs.metadata` is what a *response* reported —
            # `ToolsCalled` reads the trajectory out of it — and there is no
            # response here; inventing one to carry a driver's diagnosis would
            # reopen the channel ADR 0002 closes. The driver builds the verdicts
            # itself.
            #
            # One failed call errors the whole case, sampled or not: a target
            # that cannot answer has not answered, and a partly-sampled case
            # would be a weaker measurement claiming to be the declared one.
            return (
                CaseResult(
                    case_id=case.id,
                    verdicts=_failed(
                        suite, f"target raised {type(exc).__name__}: {exc}"
                    ),
                    canary=case.canary,
                ),
                "target",
                line,
            )

        line = line.plus(tokens=response.usage, spent_usd=response.cost_usd or 0.0)
        if suite.record_responses:
            answers.append(recorded(response))

        try:
            samples.append(mapper(response, case))
        except Exception as exc:  # noqa: BLE001 — same treatment, different diagnosis
            return (
                CaseResult(
                    case_id=case.id,
                    verdicts=_failed(
                        suite, f"mapper raised {type(exc).__name__}: {exc}"
                    ),
                    canary=case.canary,
                ),
                "mapper",
                line,
            )

    # With one sample `combine_samples` is the identity function, so this is
    # byte for byte what the driver produced before sampling existed.
    verdicts = tuple(
        _graded(suite, assertion, samples, judge_samples)
        for assertion in suite.assertions
    )
    return (
        CaseResult(
            case_id=case.id,
            verdicts=verdicts,
            responses=tuple(answers),
            canary=case.canary,
        ),
        # An assertion that errored here answered about an answer that arrived:
        # the target was paid and the judging is what failed, which is a
        # different bill from the one above and a different thing to tell a
        # reader about before retrying it.
        "assertion" if any(v.status == "error" for v in verdicts) else "",
        line,
    )


def _calibrate(
    suite: Suite,
    mapper: Mapper,
    case: Case,
    calibration: Calibration,
    judge_samples: int = 0,
) -> tuple[CaseResult, Cause, CallTotals]:
    """A calibration case: the author's answer, graded by one check.

    **The target is not called.** The answer is known to be partially correct
    only because the author wrote it, so the driver builds the `Response` from
    the declaration — no cost, no latency, no trajectory, because no call was
    made — and hands it to the mapper like any other. That the mapper is on the
    path is the point: it is where the context a judge reads is built. (ADR 0024
    §4.1)

    **Only the named check runs**, and the skip belongs here for the reason a
    suspension's does: an assertion is never asked a question it then has to
    decline. `CostBudget` and `LatencyBudget` read figures a call nobody made
    does not have, and `ToolsCalled` a trajectory nobody produced; run on this
    case each would error, and every suite with a budget and a calibration case
    would exit 2 on every run for nothing. The skip is recorded rather than
    hidden: the run carries the band, whose `check` is the one verdict the case
    holds. (ADR 0024 §4.3)

    `suite.samples` repeats the judge alone here. Nothing is recorded into
    `responses`, whatever the suite asked for: the answer is already in the
    committed cases file. (ADR 0024 §4.7)
    """
    band = calibration.band
    # `Suite` has already refused a check that is absent or ambiguous.
    check = next(a for a in suite.assertions if a.name == calibration.check)
    response = Response(output=calibration.output, input=calibration.input)
    samples: list[EvaluatorInputs] = []
    for _ in range(suite.samples):
        try:
            samples.append(mapper(response, case))
        except Exception as exc:  # noqa: BLE001 — the ordinary case's treatment
            return (
                CaseResult(
                    case_id=case.id,
                    verdicts=(
                        _stamped(
                            check,
                            error_verdict(
                                check,
                                _clip(f"mapper raised {type(exc).__name__}: {exc}"),
                            ),
                        ),
                    ),
                    calibration=band,
                ),
                "mapper",
                CallTotals(),
            )
    verdict = _graded(suite, check, samples, judge_samples)
    return (
        CaseResult(case_id=case.id, verdicts=(verdict,), calibration=band),
        "assertion" if verdict.status == "error" else "",
        # The target is not called here, so the target line gets a zero. What
        # the *judge* spent grading this case is on the judge line, where it
        # belongs: a calibration case is paid for, just not by the target.
        CallTotals(),
    )


def _outcomes(
    suite: Suite, results: Sequence[CaseResult], run_assertion: RunAssertion
) -> tuple[CaseOutcome, ...]:
    """Every case the aggregate counts: its mark, and the verdict of the one
    check named by `over`.

    `Suite` has already refused an `over` that is absent or ambiguous, so a case
    that ran has exactly one verdict under that name — including a case whose
    target raised, where the driver built an errored verdict for every declared
    assertion. A suspended case has none, and is excluded rather than guessed at.

    **A scoped aggregate is filtered here**, and that is the whole of "the same
    machinery on a subset": `with_noise_interval` is handed a shorter list and
    needs no branch, so the per-sample re-evaluation of ADR 0006 §7 is
    restricted to the group because what it re-evaluates already is.

    Filtering here rather than inside the aggregate is deliberate.
    `per_sample_outcomes` gives up unless every judged case in the list carries
    the same number of samples; over the group, that condition is about the
    group, and one odd case elsewhere in the run cannot silence its interval.
    (ADR 0010 §7)
    """
    # Annotated: inferring the dict would widen the Literal to `str`.
    labels: dict[str, Label | None] = {c.id: c.label for c in suite.cases}
    over = run_assertion.over
    # `getattr` rather than an attribute, for the reason `expand_by_group` reads
    # the flag that way: `RunAssertion` is a structural Protocol and a custom
    # aggregate that never heard of groups must go on satisfying it.
    group: str | None = getattr(run_assertion, "group", None)
    if group is None:
        counted = results
    else:
        groups = {c.id: c.group for c in suite.cases}
        counted = [r for r in results if groups.get(r.case_id) == group]
    return tuple(
        CaseOutcome(
            case_id=result.case_id,
            label=labels.get(result.case_id),
            verdict=next((v for v in result.verdicts if v.score.name == over), None),
            # Read off the *result* rather than the suite, because that is where
            # every other reader of this fact will find it — a stored run has no
            # suite beside it. (ADR 0016 §1)
            canary=result.canary,
            calibration=result.calibration is not None,
        )
        for result in counted
    )


def price_digest_of(target: object) -> str:
    """The declared-price digest a target contributes to `config_hash`, or `""`.

    One function for every call site that computes the hash — `execute`, the
    journal header, `promote`, `view`, `rejudge` — so none of them can come to
    read a target's price differently. (ADR 0022 §4)
    """
    return target.price_digest if isinstance(target, DeclaresPrice) else ""


def execute(
    suite: Suite,
    target: Target,
    *,
    created_at: str,
    mapper: Mapper = default_mapper,
    git_commit: str | None = None,
    run_metadata: Mapping[str, object] | None = None,
    artifacts: Mapping[str, Artifact] | None = None,
    done: Mapping[str, CaseResult] | None = None,
    on_case: Callable[[CaseProgress], None] | None = None,
    pricing: str | None = None,
    judge_samples: int = 0,
    spent: CallTotals | None = None,
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

    `done` maps `case_id` to a result somebody already holds — a journal, after
    a killed run (ADR 0017 §4). Those cases are **not called**, and their
    results are placed where the *suite* puts them rather than where the journal
    does, so a resumed run's `results` are in the same order as an uninterrupted
    one's. The driver still knows nothing about the store: what it receives is a
    mapping of values.

    `on_case` is called once per finished case, before the next one starts. It
    is deliberately **not** wrapped: everything else here is contained — a
    target that raises errors its case, a broken assertion errors its own line —
    and the failure this one would hide is a recorder that stopped recording
    while the run went on for another six hundred calls, which is the loss the
    journal exists to end.

    `spent` is what the **earlier legs of this same run** consumed, read off
    the journal and carried in so the finished document states the whole run's
    bill rather than the last leg's (ADR 0025 §11). It is mandatory whenever
    `done` is non-empty and refused otherwise: a resumed run whose earlier legs
    had no bill beside them would under-bill in silence, and a caller that
    genuinely kept no figures says so explicitly with `CallTotals(calls=n)`.
    Nothing is derived from `done` itself — a number reconstructed by arithmetic
    is one that eventually disagrees with the calls that were made.

    `judge_samples` asks each judged check that many times per answer. It is a
    measurement of the judge on answers that do not move, so it is refused on
    any target but a `Replay`, before the first call: on a live target the
    answers move too, and the range would be the target's and the judge's
    together under the judge's name. The run returned carries no marker of it;
    `rejudge` stamps `Run.judge_samples` beside `rejudged_from`. (ADR 0024 §5.2)
    """
    if judge_samples:
        # Imported here: `replay` imports this module.
        from digline.run.replay import Replay

        if judge_samples < 2:
            raise ValueError(
                f"judge_samples is {judge_samples}: asking the judge once is an "
                "ordinary judgement, and a range needs at least two"
            )
        if not isinstance(target, Replay):
            raise ValueError(
                "judge_samples measures the judge on answers that do not move, so "
                "it runs only on a replay: on a live target the range would mix "
                "the target's variance into the judge's. Use `rejudge`"
            )
    # Asked before anything is called. A target that can check itself against
    # the suite says so by having the method; the ones that cannot are plain
    # functions and are left alone.
    if isinstance(target, Preflight):
        target.preflight(suite.cases)
    # Asked here for the same reason as `preflight`: a target whose declared
    # configuration is malformed must say so before the suite is paid for, not
    # after. The answer is discarded — it is asked for again below.
    target_config(target)
    # And the judge's, for the same reason and discarded the same way: a judge
    # that names no price or no instrument should say so before the suite is
    # paid for. The answer recorded is the one taken after the last case.
    judge_config(suite)

    # Read before the first case, because a judge's counters are monotone for
    # the life of the object: what this run spent is the difference between
    # this reading and the one after the last case. A suite that builds its
    # judge fresh starts at zero and the subtraction is a no-op; one that
    # reuses it across runs is the case this exists for. (ADR 0025 §4)
    judging_before = judge_totals(suite)

    reuse = dict(done or {})
    unknown = sorted(set(reuse) - {case.id for case in suite.cases})
    if unknown:
        # Refused here rather than in the caller, because it is an invariant of
        # this function: a run assembled out of two suites would be a document
        # naming one configuration over cases from another. A journal is
        # refused earlier and by a wider rule (ADR 0017 §6); this catches the
        # library caller who builds `done` by hand.
        raise ValueError(
            f"done names {len(unknown)} case(s) the suite does not declare "
            f"({', '.join(unknown)}): a run may not be assembled out of two "
            "case sets"
        )
    if reuse and spent is None:
        # Checked after the wider invariant above, which is about whether these
        # cases belong to this run at all — a question that comes before what
        # they cost.
        raise ValueError(
            f"done names {len(reuse)} case(s) already run and no `spent` beside "
            "them: their calls were paid for, and a run that cannot add them up "
            "would report a bill missing a whole leg. Pass the journal's "
            "`Pending.spent`, or `CallTotals(calls=…)` if you kept no figures"
        )
    # `spent` with an empty `done` is **not** refused: a resume where every
    # journalled case is being retried reuses nothing and still owes the earlier
    # legs' money. What was already paid does not depend on what will be called.

    results: list[CaseResult] = []
    # Starts from what the earlier legs paid, so the total is the run's and not
    # this leg's. A case reused from `done` adds nothing of its own here: its
    # calls are already inside `spent`, and counting them again out of its
    # recorded answers would bill them twice. (ADR 0025 §11)
    billed = spent or CallTotals()
    for case in suite.cases:
        if case.id in reuse:
            results.append(reuse[case.id])
            continue
        result, cause, line = _run_case(suite, target, mapper, case, judge_samples)
        results.append(result)
        billed = billed + line
        if on_case is not None:
            # Asked per case rather than once at the end, because a recorder
            # that kept only the verdicts would resume into the averaging ADR
            # 0005 §8 refuses: the identity the provider reported has to be on
            # disk before the crash. Both are property reads on objects this
            # function already holds. (ADR 0017 §7)
            on_case(
                CaseProgress(
                    result=result,
                    observed_target=target_config(target),
                    observed_judge=judge_config(suite),
                    cause=cause,
                    # Written to the journal whatever the suite records: the
                    # money is spent either way, and a leg that did not say so
                    # is a leg the resumed document cannot bill. (ADR 0025 §11)
                    usage=line,
                )
            )
    # And asked again, because a target may only be able to *learn* its
    # configuration by answering: the model call an `HttpTarget` evaluates
    # happens on the other side of HTTP, so the application reports it in the
    # response and there is nothing to read until a case has run (ADR 0005 §8).
    # A target that declares statically gives the same answer both times.
    declared = target_config(target)
    # The judge is asked again too. Its observed identity — which instrument
    # *actually* graded, as the provider reported it — does not exist until it
    # has been asked something, and a judge whose alias rolled is ADR 0005 §4's
    # reduced comparability with nobody to notice it. A judge that declares
    # statically gives the same answer both times. (ADR 0005 §9)
    grading = judge_config(suite)
    # Aggregates are computed here because they are *recorded data*: they belong
    # in the run, so they are born where the verdicts are. The core stays pure
    # and `compare()` and the report only read them.
    #
    # `with_noise_interval` evaluates each one once more per sample index, so an
    # aggregate — which has no samples of its own — still records how far it
    # moves. It costs no call to anything: the per-case samples already exist
    # and a `RunAssertion` is a pure function. (ADR 0006 §7)
    aggregate = tuple(
        with_noise_interval(run_assertion, _outcomes(suite, results, run_assertion))
        for run_assertion in suite.run_assertions
    )
    return Run(
        tenant=suite.tenant,
        environment=suite.environment,
        suite=suite.name,
        # The declared price is read off the target, unless the caller already
        # knows it: a replay's target is a wrapper around stored answers and
        # declares nothing, so `rejudge` passes the real target's digest.
        # (ADR 0022 §4)
        config_hash=suite.config_hash(
            pricing=price_digest_of(target) if pricing is None else pricing
        ),
        created_at=created_at,
        git_commit=git_commit,
        results=tuple(results),
        aggregate=aggregate,
        metadata=dict(run_metadata or {}),
        # Asked of the target and of the judges, not passed in: unlike an
        # artifact this needs no filesystem, so the driver can ask directly and
        # a library caller gets it without going through the CLI. (ADR 0005 §6)
        target_config=declared,
        judge_config=grading,
        # Already read, like `created_at` and `git_commit`: the driver produces
        # a `Run` and opens no files. What the suite *declares* is a list of
        # paths; turning those into bytes is the CLI's job. (ADR 0003)
        artifacts=dict(artifacts or {}),
        # Stamped here and not in the core, which reads no process-global state.
        # The driver is what produces a document, so the document's claim about
        # its own provenance has one author — beside `created_at` and
        # `git_commit`, which arrive for the same reason. (ADR 0014 §3)
        digline_version=__version__,
        # The bill, as two lines. Always recorded — even all zeros — because a
        # run that was executed knows what it consumed, and `None` is reserved
        # for a document nobody recorded one on. (ADR 0025 §1)
        usage=RunUsage(
            # A replay calls no target, so its target line is a zero and not a
            # partial: the recorded `cost_usd` it replays was spent by the run
            # that measured, and restating it here would bill this run for
            # another's calls. The per-case figure still feeds `CostBudget`,
            # which is what made it ride the record. (ADR 0025 §3)
            target=CallTotals() if _replaying(target) else billed,
            judge=_judge_share(judging_before, judge_totals(suite)),
        ),
    )
