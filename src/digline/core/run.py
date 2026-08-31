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
    ConfigValue,
    Disclosure,
    Score,
    Status,
    Verdict,
    canonical,
    travels,
)

__all__ = [
    "PERIMETER_FIELDS",
    "identity_of",
    "Artifact",
    "CaseResult",
    "Run",
    "SystemConfig",
    "artifacts_sha",
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
# 7: `Run.artifacts` joined the run — the files that *are* the thing under test,
#    the prompt above all. Additive: a file written before them declared none,
#    which is exactly what `{}` says. (ADR 0003)
# 8: `Run.target_config` and `Run.judge_config` joined the run — the parameters
#    that decided how the system answered, and the instrument that graded it.
#    Additive: a document written before them recorded no configuration, which
#    is what an empty one says, and a baseline promoted before them still
#    compares — every field reports `unknown` rather than a change. (ADR 0005)
SCHEMA_VERSION = 8


def _num(value: float) -> float:
    return round(value, FLOAT_PRECISION)


#: The one recorded field that describes the client's own perimeter rather than
#: the model. `https://llm-gw.internal.acme-bank.it/v1` names an internal
#: gateway and often the customer with it, so under redaction it gets the ADR
#: 0003 artifact treatment: the value goes, the key stays as withheld, and a
#: comparison across it answers `unknown`. Everything else here — a model id, a
#: temperature, a token cap, a region — is a measurement of the system and
#: travels in clear. (ADR 0005 §2)
PERIMETER_FIELDS = frozenset({"base_url"})


def identity_of(provider: str, model: str) -> str:
    """The label for one instrument: `anthropic/claude-haiku-4-5`.

    A **label**, not a key. A model id may itself contain a slash — OpenRouter
    names them `anthropic/claude-3.5-sonnet` — so `openai/anthropic/claude-3.5-
    sonnet` reads correctly and cannot be split back, which is fine because
    nothing splits it: it is compared for equality and shown to a reader.
    """
    return f"{provider}/{model}"


@dataclass(frozen=True, slots=True)
class SystemConfig:
    """The parameters that decided how the system answered, as it declared them.

    Flat and scalar, because the whole feature is the **named delta**:
    `temperature 0.3 -> 0.7` is a sentence a reviewer acts on, and a nested
    structure has no such sentence. What a plugin cannot say in one scalar is
    outside the contract, and ADR 0005 §1 keeps what is outside the contract out
    of the record — `additional_request_fields` and `extra_body` above all.

    `withheld` names the keys whose values were removed at a boundary, rather
    than dropping the key. Same distinction as `Artifact.withheld`: *this run
    kept it back* and *this run never had it* are different facts, and only the
    first one may be reported as `unknown` instead of as a change.

    `identities` names **which** instruments were in play, and is the judge
    side's answer to a question the target side cannot ask: a target is bound
    once per run, while a suite may hold several judges. It is recorded even
    when there is one, because "which graded" has to be comparable whatever the
    count — replacing one of two judges is exactly the change ADR 0005 §4
    exists to catch, and a record that fell silent as soon as there were two
    would go blind precisely there.

    `values` then elaborates: **only when there is a single identity** is there
    a single set-up to record. With two instruments in play there is no one
    `max_tokens`, and inventing a merged one would describe a judge nobody
    built.

    An empty one means the target declared nothing — a plain function, an
    `HttpTarget`, a run written before ADR 0005. Absent stays absent, and absent
    is never a change.
    """

    values: Mapping[str, ConfigValue] = field(default_factory=dict[str, "ConfigValue"])
    withheld: frozenset[str] = frozenset()
    #: `provider/model` per distinct instrument, sorted and distinct. Empty on
    #: the target side, where the set could only ever hold one element and would
    #: repeat what `values` already says.
    identities: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        # Sorted and de-duplicated here rather than by every caller: it is a
        # *set* that happens to be written as a tuple, and two runs listing the
        # same judges in two orders must produce the same document.
        object.__setattr__(self, "identities", tuple(sorted(set(self.identities))))
        if any(not label for label in self.identities):
            raise ValueError("SystemConfig.identities must not hold an empty label")
        both = sorted(set(self.values) & self.withheld)
        if both:
            raise ValueError(
                f"SystemConfig declares {', '.join(both)} both withheld and "
                "present: the flag would announce a guarantee the value "
                "contradicts"
            )
        # Read as `object`, because the annotation is a promise and this is the
        # check: a document is written by whoever holds it, and `_config_from_dict`
        # comes through here rather than trusting what it parsed.
        declared = cast(Mapping[str, object], self.values)
        for key, value in declared.items():
            # Refused where it is written rather than where it is read: a
            # nested value would reach the report as a delta nobody can read.
            if value is not None and not isinstance(value, str | int | float | bool):
                raise ValueError(
                    f"SystemConfig records {key!r} as a "
                    f"{type(value).__name__}, which is not a scalar: a "
                    "configuration is diffed field by field and rendered by "
                    "value"
                )
        if not self.values:
            return
        missing = sorted({"provider", "model"} - set(self.values))
        if missing:
            raise ValueError(
                f"SystemConfig is missing {', '.join(missing)}: a "
                "configuration that cannot say who answered, and as what, "
                "names no system"
            )
        if len(self.identities) > 1:
            raise ValueError(
                f"SystemConfig lists {len(self.identities)} instruments and a "
                "single set-up: with more than one in play there is no one "
                "set-up to record, and a merged one would describe something "
                "nobody built"
            )
        # Verified rather than believed, like every other claim in this module:
        # a single identity that contradicted `values` would be two answers to
        # "what graded this" in one object.
        declared_identity = identity_of(
            str(self.values["provider"]), str(self.values["model"])
        )
        if self.identities and self.identities[0] != declared_identity:
            raise ValueError(
                f"SystemConfig names {self.identities[0]!r} and describes "
                f"{declared_identity!r}: one object cannot answer 'what "
                "graded this' twice"
            )

    @property
    def recorded(self) -> bool:
        """Whether this side has a configuration at all.

        The question `compare()` asks first: a side that recorded nothing yields
        `unknown` for every field, never a column of fabricated `new`s.
        """
        return bool(self.values or self.withheld or self.identities)

    def redacted(self) -> SystemConfig:
        """The same configuration with the perimeter fields kept back."""
        gone = {key for key in self.values if key in PERIMETER_FIELDS}
        if not gone:
            return self
        return SystemConfig(
            values={k: v for k, v in self.values.items() if k not in gone},
            withheld=self.withheld | gone,
            # A provider and a model are measurements and travel in clear, so
            # the instruments a run used are named in a redacted document too.
            identities=self.identities,
        )


@dataclass(frozen=True, slots=True)
class Artifact:
    """One file that is the thing under test, as it was when the run happened.

    `sha` is the SHA-256 of the bytes and `text` is the content. **Redaction
    removes both**, leaving only the path and `withheld=True`.

    Dropping the digest is not caution for its own sake. A digest is a
    *verifier*: prompts live in a small, guessable space — the software house
    wrote the template and the customer tuned the numbers — so a few thousand
    candidates hashed against a leaked digest recover the text in milliseconds,
    and with it the end company's business rules. A digest that travelled would
    defeat the withholding it travelled beside. (ADR 0003 §4)

    The two absences are still different facts and a reader is owed both:
    `withheld=True` is *this suite chose not to send it*, while a run with no
    entry at all declared no artifacts (or predates them).

    Keys are plain strings and never `Path`: the core imports no `pathlib`, and
    the layering gate is what keeps that true.
    """

    sha: str = ""
    text: str | None = None
    withheld: bool = False

    def __post_init__(self) -> None:
        # Empty only where there is nothing to put in it: a complete artifact
        # without a digest would be a record of a file nobody can identify.
        if not self.sha and not self.withheld:
            raise ValueError("Artifact.sha must not be empty")
        if self.withheld and self.text is not None:
            raise ValueError(
                "Artifact declares itself withheld but carries its text: the "
                "flag would announce a guarantee nothing provides"
            )


def artifacts_sha(artifacts: Mapping[str, Artifact]) -> str:
    """One short digest for a whole artifact set.

    What `runs_page` labels a run with, so two runs of one prompt sort together
    at a glance.

    Empty when anything in the set was withheld. A redacted run has no digests
    to build from, and a label computed from their absence would be stable,
    identical across every redacted run, and mean nothing — which is worse than
    no label, because it looks like one.
    """
    if any(item.withheld or not item.sha for item in artifacts.values()):
        return ""
    payload = json.dumps(
        sorted((path, item.sha) for path, item in artifacts.items()),
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


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
    #: The files that *are* the thing under test — the prompt above all — keyed
    #: by the path the suite declared. Read by the CLI and handed to the driver,
    #: never opened here: the core touches no filesystem. (ADR 0003)
    artifacts: Mapping[str, Artifact] = field(default_factory=dict[str, "Artifact"])
    #: What decided how the system answered — provider, model, temperature, the
    #: token cap, the region or the endpoint host. Beside `config_hash` and
    #: never inside it: `config_hash` is the identity of the suite, this is the
    #: identity of the system, and a change here must leave two runs comparable
    #: for the same reason a changed prompt does. (ADR 0005 §3)
    target_config: SystemConfig = field(default_factory=SystemConfig)
    #: The measuring instrument. A judge that moved makes the scores less
    #: comparable with the baseline whatever the target did, which is a stronger
    #: statement than a target change and is reported as one. (ADR 0005 §4)
    judge_config: SystemConfig = field(default_factory=SystemConfig)
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
        # Checkable here, unlike the metadata: no `Disclosure` releases a
        # perimeter field, so a redacted run that still carries one is wrong
        # whatever policy produced it.
        for what, config in (
            ("target_config", self.target_config),
            ("judge_config", self.judge_config),
        ):
            leaked = sorted(set(config.values) & PERIMETER_FIELDS)
            if leaked:
                raise ValueError(
                    f"Run.redacted is set but {what} still carries "
                    f"{', '.join(leaked)}; build it with redact()"
                )
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
        # A prompt is the software house's file and the end company's rules at
        # the same time, so it leaves only where the suite said it may. Withheld
        # rather than dropped: the reader learns that there *was* an artifact
        # and that this suite kept it, which is not what an empty map says.
        #
        # The digest goes with the text. It is a verifier, and a prompt is
        # guessable enough that keeping it would hand over what withholding the
        # text was for. (ADR 0003 §4)
        artifacts=(
            dict(run.artifacts)
            if disclosure.artifacts
            else {path: Artifact(text=None, withheld=True) for path in run.artifacts}
        ),
        # A model id and a temperature are measurements of the system and cross
        # on their own merit. `base_url` is the client's topology, so it — and
        # only it — is kept back, by the same rule and with the same `unknown`
        # outcome as a withheld artifact. No `Disclosure` releases it: one
        # special field, one existing rule, no new mechanism. (ADR 0005 §2)
        target_config=run.target_config.redacted(),
        judge_config=run.judge_config.redacted(),
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
        "artifacts": {
            path: _artifact_to_dict(item)
            for path, item in sorted(run.artifacts.items())
        },
        "target_config": _config_to_dict(run.target_config),
        "judge_config": _config_to_dict(run.judge_config),
    }


def _config_to_dict(config: SystemConfig) -> dict[str, object]:
    """Absent rather than emptied, like every other payload field.

    A configuration nobody declared is `{}` — which is what a run written before
    ADR 0005 gains on migration, and what a plain-function target records today.
    """
    payload: dict[str, object] = {}
    if config.identities:
        payload["identities"] = list(config.identities)
    if config.values:
        payload["values"] = {key: config.values[key] for key in sorted(config.values)}
    if config.withheld:
        payload["withheld"] = sorted(config.withheld)
    return payload


def _config_from_dict(raw: Mapping[str, Any], where: str) -> SystemConfig:
    """Straight into the value, which does the checking.

    A document is written by whoever holds it, not only by this code, so what
    `SystemConfig` refuses on construction it refuses on the way in too.
    """
    values = cast(Mapping[str, ConfigValue], raw.get("values") or {})
    try:
        return SystemConfig(
            values=dict(values),
            withheld=frozenset(
                str(key) for key in cast(Sequence[Any], raw.get("withheld") or ())
            ),
            identities=tuple(
                str(label) for label in cast(Sequence[Any], raw.get("identities") or ())
            ),
        )
    except ValueError as exc:
        raise ValueError(f"{where}: {exc}") from exc


def _artifact_to_dict(artifact: Artifact) -> dict[str, object]:
    """Whatever is left after redaction, and nothing standing in for the rest.

    Absent rather than emptied, like every other payload field in this document
    (fixed decision 9): a withheld artifact carries neither `sha` nor `text`,
    and `withheld` is what tells a reader that it was kept back rather than
    never there. An empty string would be a value where there is none.
    """
    payload: dict[str, object] = {}
    if artifact.sha:
        payload["sha"] = artifact.sha
    if artifact.withheld:
        payload["withheld"] = True
    if artifact.text is not None:
        payload["text"] = artifact.text
    return payload


def _artifact_from_dict(raw: Mapping[str, Any], path: str) -> Artifact:
    where = f"artifact {path!r}"
    text = raw.get("text")
    withheld = bool(raw.get("withheld", False))
    sha = raw.get("sha")
    if sha is None and not withheld:
        raise ValueError(f"{where} is missing 'sha'")
    return Artifact(
        sha="" if sha is None else str(sha),
        text=None if text is None else str(text),
        withheld=withheld,
    )


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
        artifacts={
            path: _artifact_from_dict(item, path)
            for path, item in cast(
                Mapping[str, Mapping[str, Any]], raw.get("artifacts") or {}
            ).items()
        },
        target_config=_config_from_dict(
            cast(Mapping[str, Any], _required(raw, "target_config", "run")),
            "target_config",
        ),
        judge_config=_config_from_dict(
            cast(Mapping[str, Any], _required(raw, "judge_config", "run")),
            "judge_config",
        ),
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
