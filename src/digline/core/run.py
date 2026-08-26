"""The run as a value, and its deterministic serialization.

`Run` is data, not an object that knows how to persist itself: the
`ResultStore` lives in `digline.store` and depends on the core, never the
other way round.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, cast

from digline.core.aggregate import RunAssertion
from digline.core.protocols import Assertion
from digline.core.types import (
    FLOAT_PRECISION,
    NOTHING_EXTRA,
    REDACTED,
    Disclosure,
    Score,
    Status,
    Verdict,
    canonical,
    travels,
)

__all__ = [
    "CaseResult",
    "Run",
    "config_hash",
    "redact",
    "run_from_json",
    "run_to_json",
]

# 2: `assertion_id` joined the verdict — `compare()` pairs on it, so a file
#    written without it cannot be compared correctly.
# 3: `tenant` and `redacted` joined the run. A file without a tenant cannot be
#    placed in a perimeter, and one without the redaction flag cannot be told
#    apart from a complete document. Both must be rejected, not guessed at.
# 4: `environment` joined the run. A comparison that cannot say whether it is
#    reading staging or production is a comparison nobody should act on.
# 5: `CaseResult.suspended` joined the run. A file written without it cannot
#    distinguish a case deliberately set aside from one that was never there.
# 6: `Run.aggregate` joined the run — verdicts about the run rather than about a
#    case. A file without them cannot be compared on the figure that gates a
#    release.
SCHEMA_VERSION = 6


def _num(value: float) -> float:
    return round(value, FLOAT_PRECISION)


@dataclass(frozen=True, slots=True)
class CaseResult:
    """The verdicts produced for a single test case, or the reason there are
    none.

    `suspended` carries the stated reason a case was not evaluated. It is
    recorded rather than left implicit so that suspension travels through the
    store and reaches the report: a suite whose coverage silently shrank is
    indistinguishable from one that never covered the case, and the reader in
    world 3 has no code with which to tell them apart.

    The reason is **payload**. A developer will write things like "fails on the
    Rossi account", so it is redacted exactly like a verdict's reason.
    """

    case_id: str
    verdicts: Sequence[Verdict] = ()
    suspended: str | None = None

    def __post_init__(self) -> None:
        if not self.case_id:
            raise ValueError("CaseResult.case_id must not be empty")
        if self.suspended is None:
            return
        if not self.suspended:
            raise ValueError(
                f"case {self.case_id!r} is suspended without a stated reason: "
                "an empty reason is refused for the same cause as an empty "
                "Verdict.reason — nobody can review it"
            )
        if self.verdicts:
            raise ValueError(
                f"case {self.case_id!r} is suspended but carries verdicts: "
                "suspension means it was not evaluated"
            )


@dataclass(frozen=True, slots=True)
class Run:
    """One execution of the suite, with its anchors.

    `tenant` names the perimeter the run belongs to — one end customer of a
    software house, one project of a team. It is mandatory because a run that
    does not know its perimeter cannot be compared, stored or promoted without
    someone guessing, and guessing is how one customer's results end up next to
    another's. `compare()` and `promote_baseline` both refuse to cross it.

    `environment` names *where within that perimeter* the run happened —
    production, staging, acceptance. It is deliberately not part of the tenant
    and not part of the layout: the same customer's staging and production are
    the same perimeter, holding the same data under the same ownership.
    Comparing staging against the baseline is the pre-release check, so it must
    stay legal; `compare()` reports both environments and constrains neither.

    `redacted` says this value carries no payload, and is **verified rather than
    believed** — see `__post_init__`.

    `config_hash` covers assertions, thresholds and tolerances — not the test
    data, which changes on its own schedule. `git_commit` is optional because
    the core cannot query git: whoever builds the `Run` supplies it if known.

    `created_at` is passed in by the caller rather than read from the clock: the
    core touches no process-global state, and its tests stay deterministic.
    """

    tenant: str
    environment: str
    suite: str
    config_hash: str
    created_at: str
    git_commit: str | None = None
    results: Sequence[CaseResult] = ()
    #: Verdicts about the run itself — precision, recall — rather than about any
    #: one case. Same type, same rules: a mandatory threshold makes each one a
    #: gate, and `compare()` reports whether it regressed.
    aggregate: Sequence[Verdict] = ()
    metadata: Mapping[str, object] = field(default_factory=dict[str, object])
    redacted: bool = False

    def __post_init__(self) -> None:
        if not self.tenant:
            raise ValueError("Run.tenant must not be empty")
        if not self.environment:
            raise ValueError("Run.environment must not be empty")
        if not self.suite:
            raise ValueError("Run.suite must not be empty")
        if not self.config_hash:
            raise ValueError("Run.config_hash must not be empty")
        if not self.redacted:
            return
        # `redacted` is a claim about the contents, so it is checked against
        # them. Otherwise `Run(..., redacted=True)` could be built with full
        # reasons and the serializer would believe it — the flag would announce
        # a guarantee nothing provides, which is worse than no flag at all. Same
        # family as a status that cannot contradict its threshold.
        #
        # Only the reasons can be checked here. Whether a metadata value should
        # have survived depends on the `Disclosure` that produced this run, and
        # a `Run` does not carry one: use `redact()` and the flag is correct by
        # construction.
        for verdict in self.aggregate:
            if verdict.reason != REDACTED:
                raise ValueError(
                    f"Run.redacted is set but the aggregate verdict for "
                    f"{verdict.score.name!r} still carries a reason; build it "
                    "with redact()"
                )
        for case in self.results:
            if case.suspended is not None and case.suspended != REDACTED:
                raise ValueError(
                    f"Run.redacted is set but case {case.case_id!r} still "
                    "carries its suspension reason; build it with redact()"
                )
            for verdict in case.verdicts:
                if verdict.reason != REDACTED:
                    raise ValueError(
                        f"Run.redacted is set but the verdict for "
                        f"{verdict.score.name!r} on case {case.case_id!r} still "
                        "carries a reason; build it with redact()"
                    )


def config_hash(
    assertions: Iterable[Assertion],
    *,
    samples: int = 1,
    min_agreement: float | None = None,
    run_assertions: Iterable[RunAssertion] = (),
) -> str:
    """Fingerprint of the suite *configuration*.

    Built from each assertion's `identity` **plus its threshold and tolerance**,
    sorted so the result is independent of declaration order.

    The two halves are deliberately split. `identity` covers what an assertion
    checks — needle, pattern, schema, cap — and is what `compare()` pairs on, so
    it must survive a threshold change or the verdicts would stop meeting.
    Threshold and tolerance are added back here because they still change what
    the suite *means*: a baseline recorded under a threshold of 0.7 cannot be
    promoted as the reference for a suite that now demands 0.9.

    So a raised threshold is comparable but not promotable — which is the
    behaviour we want: look at the diff, then decide to re-baseline.

    `samples` joins them for the same reason, so a run sampled three times is
    comparable with a run sampled once — the checks are the same — but not
    promotable as its baseline.

    It does not cover the test data: goldens and cases change constantly, and
    tying them into the fingerprint would make the baseline useless the moment a
    case is added. Nothing here ever sees a case.
    """
    entries = sorted(
        (a.identity, _num(a.threshold), _num(a.tolerance)) for a in assertions
    )
    # `samples` belongs here and not in any assertion's identity: it changes how
    # confidently every check is judged, exactly as a threshold changes where
    # the bar sits. A baseline taken at one sample is not a reference for a
    # suite that now takes three.
    aggregates = sorted(
        (a.identity, _num(float(a.threshold)), _num(float(a.tolerance)))
        for a in run_assertions
    )
    payload = json.dumps(
        [entries, samples, min_agreement, aggregates],
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _redact_verdict(verdict: Verdict, disclosure: Disclosure) -> Verdict:
    return Verdict(
        score=Score(
            name=verdict.score.name,
            score=verdict.score.score,
            metadata={
                k: v
                for k, v in verdict.score.metadata.items()
                if travels(v) or k in disclosure.score_metadata
            },
        ),
        threshold=verdict.threshold,
        status=verdict.status,
        reason=REDACTED,
        tolerance=verdict.tolerance,
        assertion_id=verdict.assertion_id,
    )


def redact(run: Run, disclosure: Disclosure = NOTHING_EXTRA) -> Run:
    """Return `run` without its payload: the verdict travels, the payload stays.

    This is the primitive, and `run_to_json(..., redacted=True)` is built on it
    rather than the other way round. A redaction that lived only in the
    serializer would be an opt-out every future transport — a Postgres store, an
    HTTP push, an export — would have to remember, and the one that forgets
    sends the payload with nothing to stop it (fixed decision 5).

    What survives is what a verdict *is*: name, identity, status, score,
    threshold, tolerance. What goes is `reason` — the judge quotes the output,
    so it is the output — and metadata not covered by `disclosure`.

    Applying it twice with the same `disclosure` changes nothing; applying it
    again with a narrower one narrows further. It never widens: what has been
    removed cannot come back.
    """
    return Run(
        tenant=run.tenant,
        environment=run.environment,
        suite=run.suite,
        config_hash=run.config_hash,
        created_at=run.created_at,
        git_commit=run.git_commit,
        results=tuple(
            CaseResult(
                case_id=case.case_id,
                verdicts=tuple(_redact_verdict(v, disclosure) for v in case.verdicts),
                # The reason a case was set aside is payload for the same cause
                # as a judge's reason: a developer writes it about real data.
                suspended=None if case.suspended is None else REDACTED,
            )
            for case in run.results
        ),
        aggregate=tuple(_redact_verdict(v, disclosure) for v in run.aggregate),
        # Nothing here travels on its own merit, numbers included: an amount
        # copied out of a customer's request is their data wearing the same
        # clothes as a measurement.
        metadata={
            k: v for k, v in run.metadata.items() if k in disclosure.run_metadata
        },
        redacted=True,
    )


def _verdict_to_dict(verdict: Verdict, *, redacted: bool) -> dict[str, object]:
    payload: dict[str, object] = {
        "assertion": verdict.score.name,
        "assertion_id": verdict.assertion_id,
        "score": None if verdict.score.score is None else _num(verdict.score.score),
        "status": verdict.status,
        "threshold": _num(verdict.threshold),
        "tolerance": _num(verdict.tolerance),
        "metadata": canonical(verdict.score.metadata),
    }
    # Omitted, not emptied: a redacted document must carry nothing from which
    # the reason could be guessed, not even its length.
    if not redacted:
        payload["reason"] = verdict.reason
    return payload


def _required(raw: Mapping[str, Any], key: str, where: str) -> Any:
    """Read a mandatory field, naming it when it is absent.

    No silent fallbacks. A default here would defeat the reason
    `SCHEMA_VERSION` exists: a file missing a field is a file this version
    cannot interpret, and reading it as if it could is exactly how a comparison
    ends up meaningless while staying syntactically valid. A tolerance quietly
    read as `0.0`, for instance, turns every recorded drift into a regression.
    """
    if key not in raw:
        raise ValueError(f"{where} is missing the mandatory field {key!r}")
    return raw[key]


def _verdict_from_dict(raw: Mapping[str, Any], *, redacted: bool) -> Verdict:
    where = "verdict"
    raw_score = _required(raw, "score", where)
    return Verdict(
        score=Score(
            name=str(_required(raw, "assertion", where)),
            score=None if raw_score is None else float(raw_score),
            metadata=dict(cast(Mapping[str, object], raw.get("metadata") or {})),
        ),
        threshold=float(_required(raw, "threshold", where)),
        tolerance=float(_required(raw, "tolerance", where)),
        status=cast(Status, str(_required(raw, "status", where))),
        # A redacted document has no `reason` to read; the marker keeps the
        # reconstructed verdict valid without inventing content.
        reason=REDACTED if redacted else str(_required(raw, "reason", where)),
        assertion_id=str(_required(raw, "assertion_id", where)),
    )


def run_to_dict(run: Run) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "tenant": run.tenant,
        "environment": run.environment,
        "redacted": run.redacted,
        "suite": run.suite,
        "config_hash": run.config_hash,
        "created_at": run.created_at,
        "git_commit": run.git_commit,
        "metadata": canonical(run.metadata),
        "results": [_case_to_dict(case, redacted=run.redacted) for case in run.results],
        "aggregate": [
            _verdict_to_dict(v, redacted=run.redacted) for v in run.aggregate
        ],
    }


def _case_to_dict(case: CaseResult, *, redacted: bool) -> dict[str, object]:
    payload: dict[str, object] = {
        "case_id": case.case_id,
        "suspended": case.suspended is not None,
        "verdicts": [_verdict_to_dict(v, redacted=redacted) for v in case.verdicts],
    }
    # The *fact* of suspension travels — a reader must see that coverage shrank.
    # The stated reason does not: it is payload, omitted rather than emptied.
    if case.suspended is not None and not redacted:
        payload["suspended_reason"] = case.suspended
    return payload


def _case_from_dict(raw: Mapping[str, Any], *, redacted: bool) -> CaseResult:
    where = "case result"
    suspended: str | None = None
    if bool(_required(raw, "suspended", where)):
        suspended = (
            REDACTED if redacted else str(_required(raw, "suspended_reason", where))
        )
    return CaseResult(
        case_id=str(_required(raw, "case_id", where)),
        verdicts=tuple(
            _verdict_from_dict(v, redacted=redacted)
            for v in cast(Sequence[Mapping[str, Any]], raw.get("verdicts") or ())
        ),
        suspended=suspended,
    )


def run_from_dict(raw: Mapping[str, Any]) -> Run:
    version = int(raw.get("schema_version", 0))
    if version != SCHEMA_VERSION:
        raise ValueError(
            f"schema_version {version} is not supported (expected {SCHEMA_VERSION})"
        )
    results = cast(Sequence[Mapping[str, Any]], raw.get("results") or ())
    redacted = bool(_required(raw, "redacted", "run"))
    return Run(
        tenant=str(_required(raw, "tenant", "run")),
        environment=str(_required(raw, "environment", "run")),
        redacted=redacted,
        suite=str(_required(raw, "suite", "run")),
        config_hash=str(_required(raw, "config_hash", "run")),
        created_at=str(_required(raw, "created_at", "run")),
        # `git_commit` is the one optional field: a run produced outside a
        # repository legitimately has none.
        git_commit=None if raw.get("git_commit") is None else str(raw["git_commit"]),
        results=tuple(_case_from_dict(case, redacted=redacted) for case in results),
        aggregate=tuple(
            _verdict_from_dict(v, redacted=redacted)
            for v in cast(Sequence[Mapping[str, Any]], raw.get("aggregate") or ())
        ),
        metadata=dict(cast(Mapping[str, object], raw.get("metadata") or {})),
    )


def run_to_json(
    run: Run, *, redacted: bool = False, disclosure: Disclosure = NOTHING_EXTRA
) -> str:
    """Deterministic serialization: sorted keys, fixed float precision,
    trailing newline. Two identical runs produce identical bytes.

    With `redacted=True` the document is that of `redact(run, disclosure)`:
    payload keys are absent rather than emptied, and `"redacted": true` sits at
    the top level so no reader can mistake it for a complete document.
    """
    if redacted:
        run = redact(run, disclosure)
    return (
        json.dumps(
            run_to_dict(run),
            sort_keys=True,
            indent=2,
            ensure_ascii=False,
        )
        + "\n"
    )


def run_from_json(payload: str) -> Run:
    return run_from_dict(cast(Mapping[str, Any], json.loads(payload)))
