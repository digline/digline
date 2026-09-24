"""The run as a value, and its deterministic serialization.

`Run` is data, not an object that knows how to persist itself: the
`ResultStore` lives in `digline.store` and depends on the core, never the
other way round.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any, cast

from digline.core.aggregate import RunAssertion
from digline.core.calibration import CalibrationBand
from digline.core.protocols import Assertion
from digline.core.text import recordable
from digline.core.types import (
    NO_USAGE,
    NOTHING_EXTRA,
    REDACTED,
    Cause,
    ConfigValue,
    Disclosure,
    Message,
    Output,
    OutputKind,
    ResultAbsence,
    Score,
    Status,
    ToolStatus,
    Usage,
    Verdict,
    at_precision,
    canonical,
    output_kind,
    travels,
)

__all__ = [
    "ENDPOINT_PERIMETER_FIELDS",
    "MAX_RECORDED_CHARS",
    "OBSERVED_FIELDS",
    "PERIMETER_FIELDS",
    "identity_of",
    "Artifact",
    "CallTotals",
    "CaseResult",
    "RecordedResponse",
    "RecordedToolCall",
    "Run",
    "RunUsage",
    "SystemConfig",
    "CaseProgress",
    "artifacts_sha",
    "case_from_dict",
    "case_to_dict",
    "config_from_dict",
    "config_hash",
    "config_to_dict",
    "record_output",
    "record_trajectory",
    "totals_from_dict",
    "totals_to_dict",
    "trajectory_chars",
    "usage_from_dict",
    "usage_to_dict",
    "redact",
    "release_tuple",
    "restore_output",
    "run_from_json",
    "run_to_json",
    "without_responses",
]

# 16: `Run.pinned` joined the run — which declared files must not drift, by the
#    keys `artifacts` already uses. Additive: a run written before it pinned
#    nothing, which is what an absent key says. It leaves `config_hash` alone,
#    and it travels, being a declaration the suite author wrote about files whose
#    paths are already in the document rather than anything the end company
#    measured. (ADR 0029 §3)
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
# 9: `samples`, `sample_min` and `sample_max` joined every sampled verdict — the
#    raw per-sample scores and the interval they span, which `compare()` reads
#    as a noise floor. Additive twice over: a run at `samples=1` records none of
#    them and is byte for byte the file it was, and a run that already sampled
#    carries `metadata["scores"]`, from which the migration *derives* them
#    rather than inventing them. So no baseline needs re-promoting. (ADR 0006)
# 10: three passengers at once, which is what ADR 0014 §1's passenger rule
#    exists to make legitimate rather than convenient. `Run.digline_version` —
#    the document saying what wrote it (ADR 0014 §3); `CaseResult.responses` —
#    the target's answers, recorded only where the suite asked for them and
#    never crossing a boundary (ADR 0015); `CaseResult.canary` — the case that
#    watches the model instead of measuring it (ADR 0016). Additive three times
#    over: every one of them has a value the old document already justifies —
#    not recorded, none recorded, not a canary — so nothing is invented and no
#    baseline needs re-promoting.
# 11: two passengers, checked against ADR 0014 §1 in ADR 0018 §3.
#    `RecordedResponse.tool_calls` — the trajectory beside the answer it belongs
#    to, so a trajectory assertion can be re-judged instead of errored
#    (ADR 0018 §1, §4); and `Run.resumed_at` — one entry per leg of a resumed
#    run, pre-vetted by ADR 0017 §11 and boarding the first bump that something
#    else forced. Additive both times: `()` for a run that recorded no
#    trajectory and none is recoverable, absent for a run nobody resumed. So the
#    step writes nothing and no baseline needs re-promoting.
# 12: `CaseResult.calibration` — the check a calibration case calibrates and the
#    band its score has to land in, never the answer it carries (ADR 0024 §4,
#    §9). Checked against ADR 0014 §1: case data outside `config_hash`, as the
#    canary is; absent means *not a calibration case*, which is what every older
#    case was, so the step writes nothing; and what it adds to a document is a
#    name and two numbers. The first passenger of this version, and not the
#    last: `Verdict.scale` and `Run.judge_samples` are ruled onto the same bump,
#    so 12 stays open until they have boarded it.
#    `Run.judge_samples` boarded second: how many times each judged check asked
#    the judge per recorded answer, on a replay. Outside `config_hash` (it is a
#    replay's own parameter, not the suite's); absent means *did not measure the
#    judge's range*, which is what every older run did; a count of our own
#    calls. The range it produces is metadata on judged verdicts, numbers only.
#    `Verdict.judged` boarded third, and closes the train: `true` on a verdict
#    whose assertion `KIND` declares `judged`, absent otherwise. Outside
#    `identity` and `config_hash` (`KIND` is a `ClassVar`); absent means *not
#    recorded as judged*, never derived from a name; one boolean about the check.
#    It is what the shape reading reads. (ADR 0024 §6.4)
#
# 13: an open train, ruled for two passengers and boarding them as they are
#    built. Build order is not ruling order.
#    Boarded first: the tool call nobody named. `RecordedToolCall.tool` may be
#    `None`, and the document then omits `tool` and writes
#    `"tool_absence": "not_reported"` — never `null`, which every earlier
#    reader turns into a tool named "None". Checked against ADR 0014 §1 in ADR
#    0018 §1's 2026-09-17 amendment: payload inside `RecordedResponse`, outside
#    `config_hash`; the step writes nothing, because no schema-12 writer could
#    omit `tool`; `redact()` drops it with the response and promotion strips it.
#    The bump did not create the refusal an old reader gives — an omitted `tool`
#    was already refused by name — and a journal, whose version does not move
#    with this one, has only that refusal.
#    Boarded second, and closes the train: `Score.sample_means`, written as
#    `"sample_means": true` beside `samples` on a verdict whose samples are
#    means of judgements rather than judgements — a fold of folds, stamped in
#    `combine_samples`. Checked against ADR 0014 §1 in ADR 0024 §6.5: outside
#    `identity` and `config_hash`; the step writes nothing, but here absent
#    means *not stamped*, never *judgements*, because every 0.14.x run of a
#    `Repeated` check in a sampled suite wrote an unstamped fold the step could
#    not derive — the shape reading carries that by pairing; one boolean that
#    crosses with the samples it qualifies. Unlike the passenger before it, this
#    one needs the bump's refusal: 0.14.x would ignore the key and read means
#    as judgements.
#
# 14: an open train, and its first passenger is what a run consumed.
#    `Run.usage` — two lines of one bill, the target's and the judge's, on
#    every run; and `RecordedResponse.usage` — the four counts of one call,
#    under the recording switch that already governs the answer they belong to.
#    Until now digline recorded no token count anywhere: `ProviderTarget`
#    priced `Completion.usage`, kept the money and copied the counts into
#    `Response.metadata`, which is never persisted, and `JudgeBase.spent_usd`
#    reached no document at all. Checked against ADR 0014 §1 in ADR 0025 §7:
#    outside `config_hash` (what a run consumed cannot change what it was asked
#    to do); the step writes **nothing**, because `None` is the only honest
#    value for a run whose counts are gone and `0` would say a paid run
#    consumed nothing; and the grain decides the boundary — the run total is
#    the software house's own invoice and travels, the per-call count is
#    payload and rides the response. The bump creates no refusal and needs
#    none: an old reader ignoring `usage` misreads nothing, because no verdict
#    depends on it. It rides on the train alone (ADR 0025 §10).
#
# 15: one passenger, and the consumers were ready before the field was.
#    `Usage.thinking_tokens` — the output tokens a model spent thinking, where
#    the provider reports the split, as `int | None` where `None` is *not
#    reported* and is never guessed as `0`. A breakdown and not a new billable
#    quantity: both providers report it **inside** the output count, so
#    `Pricing.cost` does not read it and adding it would bill a reasoning call
#    twice — the inverse of `cache_write_tokens`, which is reported outside
#    `input_tokens` and must be added. Checked against ADR 0014 §1 in ADR 0026
#    §6: outside `config_hash` (what a call consumed is the thing measured);
#    the step writes **nothing**, because a call measured before this release
#    may well have thought and nothing in its document says how much; and the
#    grain decides the boundary exactly as it does for the four beside it — in
#    a total it crosses, on a recorded response it does not. The bump creates
#    no refusal and needs none, so it rides the train alone (ADR 0026 §7).
#
#    It exists because it was mistaken for shipped: ADR 0025's reconnaissance
#    proposed it, 0.16.0 shipped `Usage` with four counts, and the gap was
#    found by somebody sitting down to write the plugin patch that would fill
#    it.
SCHEMA_VERSION = 16

#: What a recorded tool call writes under `tool_absence` when the reporter did
#: not name the tool. The only value: digline records every name it is given, so
#: it has no omission of its own to declare. (ADR 0018 §1, amended 2026-09-17)
TOOL_NOT_REPORTED = "not_reported"


def _num(value: float) -> float:
    return at_precision(value)


def release_tuple(version: str) -> tuple[int, ...]:
    """The numeric release segment of a version, for comparing two of them.

    `"0.10.0"` -> `(0, 10, 0)`, and that example is the whole reason this
    function exists rather than a `<` between two strings: `"0.10.0" < "0.9.0"`
    is true lexically, so a string comparison would have stopped warning at
    exactly the release after the one that introduced it (ADR 0014 §4).

    Everything after the release segment is ignored — `1.2.0rc1`, `1.2.0.post1`
    and `1.2.0` all read as `(1, 2, 0)`. A pre-release is not far enough from
    its release to justify a second rule, and `packaging` is not a runtime
    dependency of digline: the core has one, and this is not where it takes
    another.

    Empty for anything that does not begin with a number, which is what an
    unrecorded version is: `()` compares less than every real release, so an
    absent value can never be read as *ahead*.
    """
    parts: list[int] = []
    for chunk in version.split("."):
        digits = ""
        for char in chunk:
            if not char.isdigit():
                break
            digits += char
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts)


#: The one recorded field that describes the client's own perimeter rather than
#: the model. `https://llm-gw.internal.acme-bank.it/v1` names an internal
#: gateway and often the customer with it, so under redaction it gets the ADR
#: 0003 artifact treatment: the value goes, the key stays as withheld, and a
#: comparison across it answers `unknown`. Everything else here — a model id, a
#: temperature, a token cap, a region — is a measurement of the system and
#: travels in clear. (ADR 0005 §2)
#:
#: `fingerprint` joins it for the same argument one field over. On the official
#: endpoint it is an opaque backend id and harmless; but `base_url` makes one
#: plugin cover every OpenAI-compatible server, and on a customer's own vLLM the
#: value is whatever *that server* wrote there — a build path, a container tag,
#: a hostname. Software nobody here reviews, describing the client's perimeter.
#: (ADR 0005 §9)
PERIMETER_FIELDS = frozenset({"base_url", "fingerprint"})

#: Withheld **only where the run went to an endpoint the suite named**, and in
#: clear otherwise.
#:
#: `resolved_model` was unconditional in the other direction for one afternoon,
#: on the ground that a model id is a public product name. That is true of
#: `claude-sonnet-5-20260115` and false of what a customer's own vLLM or gateway
#: puts in the same field: `acme-legal-assistant-prod-eu-west-v3` is a project
#: codename, an environment and a region, and it travelled beside a `base_url`
#: withheld for describing exactly that. It arrives in the *same reply from the
#: same server* as `fingerprint`, so it is in `fingerprint`'s trust category
#: whenever `fingerprint` is.
#:
#: The *sent* `model` is not in here and does not belong: it is written in the
#: suite and the suite goes through a review, which is the argument ADR 0003 §4
#: makes for opting artifacts in. Two model names, two provenances.
#: (ADR 0005 §9, amended)
#: The per-million rates a suite **declared** for its target's model, recorded in
#: `target_config` beside `pricing = "declared"` (ADR 0022 §2).
#:
#: A negotiated rate is the customer's commercial fact, in `base_url`'s class,
#: so at a named endpoint these are withheld exactly as `resolved_model` is. The
#: withholding is a **latch, not a constraint**: the value never prints, but
#: `config_hash` is computed from it and travels in clear beside inputs that all
#: cross the boundary, so the hash narrows it. A rate that cannot afford to be
#: narrowed belongs in a Python suite that prices without declaring, or at an
#: unnamed endpoint. (ADR 0022 §6)
DECLARED_PRICE_FIELDS = frozenset(
    {"input_per_mtok", "output_per_mtok", "cache_read_per_mtok", "cache_write_per_mtok"}
)

ENDPOINT_PERIMETER_FIELDS = frozenset({"resolved_model"}) | DECLARED_PRICE_FIELDS

#: The fields a provider **reported** rather than the target **sent**.
#:
#: They are recorded and compared like any other, and this set exists for one
#: reason: absence means something different for them, so the sentence a reader
#: is owed is different. `config.change.new` says *"not sent for the
#: reference"*, which is true of a temperature and false of a resolved model id
#: — nobody sent that, on either side. (ADR 0005 §9)
OBSERVED_FIELDS = frozenset({"resolved_model", "fingerprint"})


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

    @property
    def _at_named_endpoint(self) -> bool:
        """Whether this run went to an endpoint the suite named.

        Read from `withheld` as well as `values`, because `base_url` is itself a
        perimeter field: after one redaction it has moved, and a second pass that
        looked only at `values` would conclude *first-party* and let
        `resolved_model` through. `redact()` promises it never widens, and this
        is where that promise is kept. (ADR 0005 §9, amended)
        """
        return "base_url" in self.values or "base_url" in self.withheld

    def perimeter(self) -> frozenset[str]:
        """The fields this configuration keeps back at a boundary."""
        if not self._at_named_endpoint:
            return PERIMETER_FIELDS
        return PERIMETER_FIELDS | ENDPOINT_PERIMETER_FIELDS

    def redacted(self) -> SystemConfig:
        """The same configuration with the perimeter fields kept back."""
        perimeter = self.perimeter()
        gone = {key for key in self.values if key in perimeter}
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


def _pinned_from(
    raw: Mapping[str, Any], artifacts: Mapping[str, Artifact]
) -> tuple[str, ...]:
    """The declared must-not-drift paths, refused if one names nothing recorded.

    **The same refusal the write side makes, on the read side.** `read_pinned`
    catches a typo when the suite loads, and that is where the author is — but it
    only ever runs on the machine that produced the run. A document is read
    somewhere else and by somebody else: `<tenant>/baselines/` is committed and
    git-mergeable, so a pin naming nothing recorded arrives through an ordinary
    conflict resolution, no adversary required.

    Left unchecked it is the exact failure ADR 0029 §4 exists to prevent, reached
    by the other door: `artifact_deltas` iterates the paths the two runs recorded,
    a pin outside that set produces no row at all, and the comparison is green
    because the control silently does not exist. A refusal here costs a reader
    nothing and turns *no such control* into a sentence. (F-2, the 0.19.0
    delta-pass)
    """
    declared = tuple(
        sorted(str(path) for path in cast(Sequence[Any], raw.get("pinned") or ()))
    )
    unknown = [path for path in declared if path not in artifacts]
    if unknown:
        raise ValueError(
            f"run document pins {', '.join(unknown)}, which it records no "
            "artifact for: a pinned path outside the recorded set produces no "
            "comparison at all, so the document declares a control that cannot "
            "fire. Fix the `pinned` list or record the artifact"
        )
    return declared


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


#: The ceiling for one recorded field, in characters, and the rule is
#: **whole or nothing**: a response over it records neither its output nor its
#: input, and says so.
#:
#: Truncation is the option that looks kindest and is worst. A clipped answer
#: re-judged produces a score that looks like every other score — a plausible
#: number measured on evidence the document does not admit is partial.
#: `MAX_FAILURE_CHARS` clips a *reason* because a reason is a sentence for a
#: person and half a sentence still informs them; this is evidence for a re-run,
#: and half of it is not evidence. (ADR 0015 §3)
MAX_RECORDED_CHARS = 65_536


def record_output(output: Output) -> tuple[str, OutputKind]:
    """One answer as the document stores it, and which branch it came from.

    Text stays text — a model's reply is the common case and a reader opening a
    run file should find it readable rather than JSON-escaped. The other two
    branches become canonical JSON, so the same answer always produces the same
    bytes and a run file stays deterministic.

    `kind` is recorded beside it because the text alone cannot say: `"[]"` is a
    structured answer, a conversation with no turns, or a model that literally
    replied with two brackets, and a replay that guessed would grade a different
    thing from the one that was measured.
    """
    kind = output_kind(output)
    if kind is None:  # pragma: no cover - the driver only ever holds an Output
        raise ValueError("record_output was given something that is not an Output")
    if kind == "text":
        return cast(str, output), kind
    return (
        json.dumps(
            canonical(output), sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ),
        kind,
    )


def record_trajectory(
    metadata: Mapping[str, object],
) -> tuple[RecordedToolCall, ...] | None:
    """The trajectory a target reported, as the document will hold it.

    Reads `metadata["tool_calls"]`, which is where a target puts what the model
    called — the live record, beside `tools` and never inside it, so that
    `ToolsCalled`'s reader keeps its type (ADR 0018 §6). `()` where the target
    reported nothing, which is the ordinary case and records nothing.

    **Strict about shape, and deliberately.** A malformed entry raises rather
    than being skipped: a silently dropped call would produce a document that
    understates the trajectory, and a run file that disagrees with the assertion
    that judged it is worse than one that refuses to be written. The forgiving
    reader is the *assertion*, which reports *nobody said* as an error a person
    can act on.

    `arguments` is canonicalised here, by `record_output`'s rule, so a mapping
    and the same mapping in another key order produce the same bytes.
    """
    found = metadata.get("tool_calls")
    if found is None:
        # The target said nothing about tools — not that the model called none.
        return None
    if isinstance(found, str) or not isinstance(found, Sequence):
        raise ValueError(
            f"a target reported its tool calls as a {type(found).__name__}, not "
            "a sequence of calls: there is no trajectory to record"
        )
    calls: list[RecordedToolCall] = []
    for entry in cast("Sequence[object]", found):
        if not isinstance(entry, Mapping):
            raise ValueError(
                f"a target reported a tool call as a {type(entry).__name__}, "
                "not a mapping with a 'tool' in it"
            )
        item = cast("Mapping[str, object]", entry)
        # Defaulting to `success` is a plain-function target's contract from the
        # day the trajectory arrived, and changing it would reinterpret every
        # trajectory one has reported. A writer that does not know says
        # `not_reported`, the way every provider plugin does. (ADR 0018 §1,
        # amended 2026-09-15)
        raw_status = item.get("status", "success")
        raw_absence = item.get("result_absence")
        calls.append(
            RecordedToolCall(
                tool=_reported_tool(item),
                arguments=_recorded_arguments(item.get("arguments")),
                result=None if item.get("result") is None else str(item["result"]),
                status=cast(ToolStatus, str(raw_status)),
                result_absence=(
                    None
                    if raw_absence is None
                    else cast(ResultAbsence, str(raw_absence))
                ),
            )
        )
    return tuple(calls)


def _reported_tool(item: Mapping[str, object]) -> str | None:
    """The tool a target named, or `None` where it said it named none.

    `"tool": None` is the absence, and it is a statement: the reporter handed
    over a call and did not name the tool. A mapping with no `tool` key at all
    is not that statement but a malformed entry, and raises by this function's
    caller's rule — strict about shape. `str()` is no longer applied: it is what
    turned `None` into a tool named `"None"`. (ADR 0018 §1, amended 2026-09-17)
    """
    if "tool" not in item:
        raise ValueError(
            "a target reported a tool call with no 'tool' in it: a call whose "
            'tool nobody named says so with "tool": None'
        )
    tool = item["tool"]
    if tool is None or isinstance(tool, str):
        return tool
    raise ValueError(
        f"a target reported a tool call whose 'tool' is {type(tool).__name__}, "
        "not a name"
    )


def _recorded_arguments(value: object) -> str | None:
    """Canonical JSON for a mapping, the text itself for a string, `None` for
    nothing — which is *the target reported a call without them* and is not the
    same fact as an empty object."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return json.dumps(
        canonical(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )


def trajectory_chars(calls: Sequence[RecordedToolCall]) -> int:
    """How much text a trajectory would add to the record.

    Counted against `MAX_RECORDED_CHARS` with `output` and `input`, because the
    three are what a re-judge needs together: keeping the answer and dropping
    the calls that produced it would store evidence the document does not admit
    is partial. (ADR 0018 §1)
    """
    return sum(
        len(call.tool or "") + len(call.arguments or "") + len(call.result or "")
        for call in calls
    )


def restore_output(text: str, kind: OutputKind) -> Output:
    """`record_output` read backwards, for a replay.

    The inverse has to exist here rather than in the driver: what a document
    means is this module's business, and a second reader of these bytes would be
    a second answer to what they say.
    """
    if kind == "text":
        return text
    raw = json.loads(text)
    if kind == "structured":
        return cast(Mapping[str, object], raw)
    return tuple(
        Message(role=str(turn["role"]), content=str(turn["content"]))
        for turn in cast(Sequence[Mapping[str, Any]], raw)
    )


@dataclass(frozen=True, slots=True)
class RecordedToolCall:
    """One tool call the target reported, as the document holds it.

    Recorded only inside `RecordedResponse`, which is what gives it every
    boundary sentence it needs without inventing one: `redact()` drops the whole
    response, `digline.wire` does not know its name, and `promote_baseline`
    strips it. A tool argument is the end company's data by construction — a
    `lookup` carries the identifier it looked up — so nothing here travels and
    no `Disclosure` releases it. (ADR 0018 §2)

    `arguments` is canonical JSON, by the rule `record_output` already follows,
    so the same call always produces the same bytes and a run file stays
    diffable. `None` is *the target reported a call without them*, which is a
    different fact from an empty object and is not written as one.

    `result` and `status` are recorded because a tool that ran and **failed** is
    invisible to a names-only trajectory: the model called the right tool, the
    call raised, and the agent answered from nothing. `status` is also the one
    field here a fake cannot forge into vacuity — a tool that raises reports
    `error` whether or not the model is real. (ADR 0018 §1)

    **What a provider does not report is named, never defaulted.** A provider
    plugin sees the model *ask* for a client-side tool and nothing after, so its
    calls carry `status="not_reported"` and `result_absence="not_reported"`; a
    server tool that succeeded carries `result_absence="not_recorded"`, because
    its payload is bulk. An assertion may assert on the tool and its arguments,
    and errors — never fails — on a status or a result nobody reported. (ADR
    0018 §1, amended 2026-09-15)

    **`tool` is `None` where the reporter did not name the tool** — a provider
    whose reply carried a call without a name, or a target that said
    `"tool": None`. The document omits `tool` and writes
    `"tool_absence": "not_reported"` instead, never `null`: `null` is what an
    older reader turns into a tool named `"None"`. (ADR 0018 §1, amended
    2026-09-17)
    """

    #: The name, as reported. `None` is *the reporter did not name it*; `""` is
    #: refused, because a writer that does not know says `None`.
    tool: str | None
    arguments: str | None = None
    result: str | None = None
    status: ToolStatus = "success"
    #: Why `result` is empty, where the writer knows. `None` keeps its 0.12
    #: meaning: the target reported no result and said nothing about why.
    result_absence: ResultAbsence | None = None

    def __post_init__(self) -> None:
        if self.tool == "":
            raise ValueError(
                "RecordedToolCall.tool must not be empty: a call to nothing is "
                "not a call, and a call nobody named is recorded as None"
            )
        # The exact sentence 0.12.x raises for a value it does not know, kept
        # so that the refusal an old reader gives a newer document and the one
        # this reader gives a corrupt document read alike.
        if self.status not in ("success", "error", "not_reported"):
            raise ValueError(
                f"RecordedToolCall.status must be 'success', 'error' or "
                f"'not_reported', got {self.status!r}"
            )
        if self.result_absence not in (None, "not_reported", "not_recorded"):
            raise ValueError(
                "RecordedToolCall.result_absence must be 'not_reported' or "
                f"'not_recorded', got {self.result_absence!r}"
            )
        if self.result_absence is not None and self.result is not None:
            raise ValueError(
                f"RecordedToolCall declares its result {self.result_absence} "
                "and carries one: a reader cannot be told both"
            )


@dataclass(frozen=True, slots=True)
class RecordedResponse:
    """One answer the target gave, kept where it was born.

    Recorded only where the suite asked for it — `Suite.record_responses` — and
    **never crossing a boundary**: `redact()` drops it and `digline.wire` does
    not know its name. The target's output is the end company's data by
    construction, and `Verdict.reason` is already redacted *because the judge
    quotes it*. Releasing the thing quoted from while withholding the quote
    would not be a boundary. (ADR 0015 §4)

    `input` is the rendered prompt and is not an extra: the prompt is built
    inside the target, so a stored answer with no stored question cannot be
    re-judged by any assertion that reads the input — which is most of the ones
    that call a model.

    `cost_usd` and `latency_ms` ride along for a reason that is easy to discover
    too late: a suite holding a `CostBudget` re-judged without them does not fail
    that check, it **errors** it, turning a declared gate into a row nobody
    gated on.

    Two absences, and they are different facts a reader is owed:
    `withheld` is redaction, `oversize` is the recorder refusing a field over
    `MAX_RECORDED_CHARS`.
    """

    output: str | None = None
    kind: OutputKind | None = None
    input: str | None = None
    cost_usd: float | None = None
    latency_ms: float | None = None
    #: What the model called on the way to this answer, in the order it called
    #: it.
    #:
    #: **`None` and `()` are different facts**, on the rule `Completion.tools`
    #: already follows: `()` is a target saying *the model called nothing*, which
    #: `ToolsCalled` scores; `None` is a target that said nothing about tools at
    #: all, which it errors. ADR 0018 §1 kept only the tuple, on the ground that
    #: the distinction lived on the live record — and the replay is exactly the
    #: reader that needs it, so an honest zero-call run could be measured and
    #: then not re-judged. Corrected in 0.12.1; see that ADR's dated note.
    tool_calls: tuple[RecordedToolCall, ...] | None = None
    #: What this one call consumed, where the target reported it.
    #:
    #: `None` is a target that reported no counts — `HttpTarget` prices from a
    #: JSON path and has none, and a plain-function target has whatever its
    #: author built. It is never a zero: a call that consumed nothing is not a
    #: call that was made.
    #:
    #: **Payload, unlike the run's totals.** A per-call count is a fact about
    #: one of the end company's requests, so it rides the recorded answer it
    #: belongs to: `redact()` drops it with the response, `promote_baseline`
    #: strips it through `without_responses`, and `digline.wire` never learns
    #: its name. It is recorded under the switch that already governs the
    #: answer — `Suite.record_responses` — and gains none of its own, because a
    #: second flag is a second thing to forget. (ADR 0025 §1, §8)
    usage: Usage | None = None
    withheld: bool = False
    oversize: bool = False

    def __post_init__(self) -> None:
        if self.withheld and self.oversize:
            raise ValueError(
                "RecordedResponse declares itself both withheld and oversize: "
                "they are two different absences and a reader cannot be told "
                "both"
            )
        if self.withheld and (
            self.tool_calls is not None
            or any(
                value is not None
                for value in (
                    self.output,
                    self.kind,
                    self.input,
                    self.cost_usd,
                    self.latency_ms,
                    # A withheld answer keeps back what it consumed too: the
                    # counts are a measure of the text that was withheld, and
                    # releasing them beside a withheld marker would be the
                    # boundary leaking through the field that says it holds.
                    self.usage,
                )
            )
        ):
            raise ValueError(
                "RecordedResponse declares itself withheld but still carries "
                "what redaction removes: the flag would announce a guarantee "
                "nothing provides"
            )
        if self.oversize and (
            self.output is not None
            or self.input is not None
            or self.tool_calls is not None
        ):
            raise ValueError(
                "RecordedResponse declares itself oversize but carries text: "
                "over the ceiling the rule is whole or nothing, and a kept half "
                "is the truncation that rule exists to refuse"
            )
        if self.withheld or self.oversize:
            return
        if self.output is None:
            raise ValueError(
                "RecordedResponse carries no output and does not say why: a "
                "record of an answer nobody can read is not a record"
            )
        if self.kind is None:
            raise ValueError(
                "RecordedResponse carries an output without its kind: the text "
                "alone cannot say which branch of Output it came from, and a "
                "replay that guessed would judge a different thing"
            )

    @property
    def replayable(self) -> bool:
        """Whether this answer can be handed to the assertions again.

        Derived, so nothing can claim it: a withheld or oversize response has no
        text, and a replay built on one would be a weaker measurement wearing
        the declared suite's name.
        """
        return self.output is not None and self.kind is not None

    @property
    def replayable_trajectory(self) -> bool:
        """Whether a trajectory assertion can be handed this answer again.

        `()` qualifies and `None` does not, which is the whole of the fix: a
        recorded *zero-call* answer is a measurement and replays as one, while
        an answer from a target that never reported has nothing to replay and is
        refused before `Replay` speaks. Without the refusal the rebuilt metadata
        would have to invent `tools: []` — claiming the model called nothing
        about a target that never said so, which is the vacuous green this
        product refuses. (0.12.1)
        """
        return self.tool_calls is not None


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
    #: What the target answered, one entry per sample, in the order produced.
    #: Empty unless the suite asked for them, and **never** on a boundary: this
    #: is the payload in its most literal form. (ADR 0015 §1)
    responses: Sequence[RecordedResponse] = ()
    #: This case watched the model rather than measuring it. Recorded here and
    #: not only on the `Case`, because every reader downstream — the aggregates,
    #: the comparison, the report — meets the *run* and not the suite, and a
    #: case whose exclusion could only be learnt from the suite would be a case
    #: excluded invisibly. (ADR 0016 §1)
    canary: bool = False
    #: This case calibrated the judge rather than measuring the system: the
    #: check it names was graded on an answer the author wrote, and its score
    #: has to land inside the band. The answer itself is never here — it is
    #: payload and it is already in the committed cases file. (ADR 0024 §4)
    calibration: CalibrationBand | None = None

    def __post_init__(self) -> None:
        if not self.case_id:
            raise ValueError("CaseResult.case_id must not be empty")
        if self.canary and self.calibration is not None:
            raise ValueError(
                f"case {self.case_id!r} is both a canary and a calibration case: "
                "one asks the target and the other bypasses it"
            )
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
        if self.responses:
            raise ValueError(
                f"case {self.case_id!r} is suspended but carries recorded "
                "answers: a suspended case is never called, so there is nothing "
                "it could have answered"
            )


@dataclass(frozen=True, slots=True)
class CallTotals:
    """One line of the bill: what was asked for, and how much of it was counted.

    `calls` is every call this line covers. `counted` is how many of those
    reported their usage, and it is the field that keeps the rest honest: a
    total with no count of what it totals is the undercount that reads as good
    news. Two ordinary things make them differ — a target that reports no
    counts at all (`HttpTarget` prices from a JSON path and has none), and a
    resumed leg whose earlier calls were journaled without their answers. A
    reader acts on both identically: do not read this as the whole bill.
    (ADR 0025 §3)

    `spent_usd` is on the line rather than left to be summed, because the sum
    is only available where responses were recorded — that is, not on the
    ordinary run, which is exactly the one whose cost gets asked about.
    """

    calls: int = 0
    counted: int = 0
    tokens: Usage = NO_USAGE
    spent_usd: float = 0.0

    def __post_init__(self) -> None:
        if self.calls < 0 or self.counted < 0:
            raise ValueError("CallTotals counts must not be negative")
        if self.counted > self.calls:
            raise ValueError(
                f"CallTotals counted {self.counted} of {self.calls} calls: a "
                "line cannot count more calls than it covers"
            )
        if not math.isfinite(self.spent_usd):
            # **The guard above was written for the wrong half of the problem.**
            # `NaN` and `inf` are not negative, so a cost that is neither a
            # number nor an error passed it — and since 0.16.0 that value flows
            # into a run-level total, where two lines at 1e308 sum to `inf`.
            #
            # What it costs is not arithmetic but readability: the document is
            # written with a bare `Infinity` or `NaN`, which CPython's `json`
            # accepts as an extension and **no strict parser does**. So the run
            # file round-trips here and is refused by the first conforming
            # reader — another language's parser, a linter, or the MCP client's
            # JSON layer, which ADR 0011 §5 calls a worse destination than CI
            # stdout. Refused here rather than at the serializer: a document
            # that cannot be written is worse than one that cannot be read, and
            # the honest place to stop a number that is not a number is where it
            # is made. (B-1, the 0.16.0 delta-pass)
            raise ValueError(
                f"CallTotals.spent_usd is {self.spent_usd}, which is not a "
                "finite number: a bill that is not a number is not a bill, and "
                "it writes a document no strict JSON reader will parse"
            )
        if self.spent_usd < 0:
            raise ValueError("CallTotals.spent_usd must not be negative")

    @property
    def partial(self) -> bool:
        """Whether this total covers only part of what it was asked to cover.

        Derived, never stored: two sources of truth for one fact drift apart.
        A line that made no calls is not partial — it is a zero, which is what
        a replay's target line is (ADR 0025 §3).
        """
        return self.counted < self.calls

    def _folded(self, tokens: Usage, *, counted: int) -> Usage:
        """This line's counts with another call's — or with another line's.

        **A line that counted nothing is not an unreported measurement, it is
        no measurement**, and the difference matters for exactly one field.
        `NO_USAGE` carries `thinking_tokens=None`, and `Usage.__add__` makes any
        unreported side unreport the total (ADR 0026 §3) — correct between two
        calls, wrong against the seed of a fold, where it would turn every
        reported split in the run into *not reported*. The other four counts
        are zeros and would not have noticed.

        So the neutrality is decided by `counted`, which is the honest
        predicate: nothing counted, nothing to fold, take the other side whole.
        """
        if self.counted == 0:
            return tokens
        if counted == 0:
            return self.tokens
        return self.tokens + tokens

    def __add__(self, other: CallTotals) -> CallTotals:
        """Two lines of the same side, summed.

        A run's line is a fold over its cases, and a fold written by hand at
        each call site is a fold that drifts. `partial` survives the sum by
        construction: a line that counted less than it covered keeps that gap.
        """
        return CallTotals(
            calls=self.calls + other.calls,
            counted=self.counted + other.counted,
            tokens=self._folded(other.tokens, counted=other.counted),
            spent_usd=self.spent_usd + other.spent_usd,
        )

    def plus(self, *, tokens: Usage | None, spent_usd: float) -> CallTotals:
        """This line with one more call on it.

        `tokens=None` is a call that reported no counts: it raises `calls` and
        leaves `counted` where it was, which is the whole mechanism behind
        `partial`. The money is added either way — a call that could be priced
        was paid for whether or not its counts arrived.
        """
        return CallTotals(
            calls=self.calls + 1,
            counted=self.counted + (0 if tokens is None else 1),
            tokens=self.tokens if tokens is None else self._folded(tokens, counted=1),
            spent_usd=self.spent_usd + spent_usd,
        )


@dataclass(frozen=True, slots=True)
class RunUsage:
    """What the run consumed, as two lines of one bill.

    Separate because they move for different reasons and mean different things:
    the target line is what the *thing under test* cost, and the judge line is
    what the *instrument* cost. A sum would hide the one substitution ADR 0005
    §4 exists to catch, and the judge's half has never reached any document at
    all. (ADR 0025 §2)

    **Two judge instances configured identically are two bills, and they add.**
    `judge_config` records them as one identity — the instrument, not the
    instance — so a reader can meet one judge in the configuration and a total
    that reads like two. That is correct and it is stated rather than smoothed:
    equal configuration is not the same instrument, and merging the bill would
    hide a suite paying twice for what it believes is one judge. (ADR 0025 §4)
    """

    target: CallTotals = CallTotals()
    judge: CallTotals = CallTotals()


@dataclass(frozen=True, slots=True)
class CaseProgress:
    """One case as the driver finished it, for whoever is recording as it goes.

    Handed to `execute()`'s `on_case` callback and consumed by the journal
    (ADR 0017 §4). It lives in the core rather than beside `execute()` for a
    layering reason: the store may not import `digline.run`, so a value declared
    in the driver would either invert the dependency or force the store to
    accept an untyped object. It is a pure value made of core types, which is
    what this package is for.

    The observed configurations travel **with each case** rather than being
    asked for once at the end, because a journal that recorded only the verdicts
    would resume into the averaging ADR 0017 §7 exists to prevent: the identity
    the provider reported has to have been written down *before* the crash.
    Asking the target for it is a property read on an object the driver already
    holds — it calls nothing and costs nothing.

    `cause` names the layer that produced the error and is the one thing here
    the run document has no field for. That asymmetry is deliberate: the journal
    may hold what the document does not, precisely because it is deleted on
    success.
    """

    result: CaseResult
    observed_target: SystemConfig = field(default_factory=SystemConfig)
    observed_judge: SystemConfig = field(default_factory=SystemConfig)
    cause: Cause = ""
    #: What this case's target calls consumed, for the journal to write down.
    #:
    #: **Written whatever the suite records.** It is the journal's own fact
    #: about work already paid for, not a recording of the answer: a suite with
    #: `record_responses` off still spent the money, and a resumed run that
    #: could not say so would under-bill in silence. So it does not ride
    #: `Suite.record_responses`, which governs the *answer*. (ADR 0025 §11,
    #: corrected 2026-09-18)
    usage: CallTotals = field(default_factory=CallTotals)


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
    #: Which of those files the suite declared **must not drift**, by the same
    #: keys. A declaration, not a measurement: the author wrote it, and it is
    #: what lets a comparison lift a `changed` on a named path into an exit code.
    #:
    #: Recorded here rather than read from the suite at comparison time, so two
    #: archived documents answer the same way tomorrow as today — everything else
    #: that moves an exit code in this system is recorded in the document the
    #: exit code is about. Carried through `redact()` for `canary`'s reason: a
    #: redacted document that lost it would report an exit code its own contents
    #: could not account for. Outside `config_hash`. (ADR 0029 §3)
    pinned: tuple[str, ...] = ()
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
    #: The digline that wrote this document, beside the `schema_version` that
    #: says what shape it is. Stamped by `execute()`, never read from here: the
    #: core touches no process-global state, and a `Run` built by hand records
    #: nothing. `""` means **not recorded** — a migrated file, a document built
    #: in a test — and is never read as version zero. It survives redaction: a
    #: fact about the software house's own instrument, not about the end
    #: company. (ADR 0014 §3)
    digline_version: str = ""
    #: The stored run whose recorded answers this run was judged from, when it
    #: was judged from one. The declaration that keeps a replay from reading as
    #: a fresh measurement — and what `promote_baseline` refuses on, because a
    #: replay has no target variance and its interval would freeze a noise floor
    #: measured without the noise. (ADR 0015 §6, §7)
    rejudged_from: str | None = None
    #: When this document was promoted to be the baseline, as the promoter
    #: stamped it. Empty on a run — a run has not been promoted — and empty on a
    #: baseline promoted before this field existed, which is *not recorded* and
    #: never read as a date.
    #:
    #: `created_at` is when the run was **measured**; this is when a person
    #: **signed it off**, and the two are days apart in the ordinary case. It is
    #: passed in rather than read here for the reason `created_at` is: the core
    #: touches no clock, and neither does the store. (ADR 0014 §3)
    promoted_at: str = ""
    #: One entry per leg of a run that was resumed, in the order the legs ran.
    #: `()` is a run nobody resumed, which is the ordinary case and is what a
    #: document written before this field says by omitting it.
    #:
    #: A fact about the *process* and not about the suite, so it stays out of
    #: `config_hash`; and a fact about the software house's own instrument, so
    #: it survives `redact()` in clear, like `digline_version` and
    #: `promoted_at`. Pre-vetted against the passenger rule by ADR 0017 §11 and
    #: boarded by ADR 0018 §3, which is the bump that finally forced the move.
    resumed_at: tuple[str, ...] = ()
    #: How many times each judged check asked the judge per recorded answer, on
    #: a replay that measured the judge's own range. `0` is a run that did not,
    #: which is every run but those, and what a document written before this
    #: field says by omitting it. The verdicts record what a single judgement
    #: records; the range is in each judged verdict's metadata. A fact about our
    #: own instrument, so it survives `redact()`. (ADR 0024 §5.3, §9)
    judge_samples: int = 0
    #: What this run consumed, as two lines — the target's and the judge's.
    #:
    #: `None` is **not recorded**: a migrated document, a `Run` built by hand in
    #: a test, a library caller who built one directly. It is never read as
    #: zero, on the rule `digline_version = ""` already follows — a run measured
    #: last month consumed something, and nothing in its document can say what.
    #: A run that *was* recorded and reported nothing is `CallTotals(calls=n,
    #: counted=0)`, which is a different statement and looks like one.
    #:
    #: A fact about our own instrument and our own bill, so it survives
    #: `redact()` in clear, like `digline_version` and `resumed_at`. The
    #: per-call counts do not: they ride `RecordedResponse` and are payload.
    #: (ADR 0025 §1, §8)
    usage: RunUsage | None = None

    def __post_init__(self) -> None:
        if not self.tenant:
            raise ValueError("Run.tenant must not be empty")
        if not self.environment:
            raise ValueError("Run.environment must not be empty")
        if not self.suite:
            raise ValueError("Run.suite must not be empty")
        if not self.config_hash:
            raise ValueError("Run.config_hash must not be empty")
        if self.judge_samples == 1 or self.judge_samples < 0:
            raise ValueError(
                f"Run.judge_samples is {self.judge_samples}: it is 0 on a run "
                "that did not measure the judge's range, and at least 2 on one "
                "that did"
            )
        if self.judge_samples and self.rejudged_from is None:
            raise ValueError(
                "Run.judge_samples is set on a run that declares no "
                "rejudged_from: the judge's range is measured on answers that do "
                "not move, which only a replay has"
            )
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
            # `config.perimeter()` and not `PERIMETER_FIELDS`: on a compatible
            # endpoint that set includes `resolved_model`, and by the time this
            # runs `base_url` has moved to `withheld` — which is the half of
            # `_at_named_endpoint` that makes the check see it.
            leaked = sorted(set(config.values) & config.perimeter())
            if leaked:
                # Two readers reach this, and only one of them can act on
                # "build it with redact()". The other received the document and
                # does not hold the original — for them the sentence that helps
                # is which field is wrong and why the file is refused, so both
                # are said. A run digline 0.8.0 wrote from a compatible endpoint
                # is the one real instance: `resolved_model` travelled there and
                # is withheld from 0.8.1 (ADR 0005 §9, amended).
                raise ValueError(
                    f"Run.redacted is set but {what} still carries "
                    f"{', '.join(leaked)}: the document claims a perimeter it "
                    "does not keep. If you hold the unredacted run, build it "
                    "with redact(); if this arrived from elsewhere, it was "
                    "written by a version whose perimeter was wider and the "
                    "sender has to send it again"
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
            # The loudest one, checked the same way. A recorded answer is the
            # payload in its most literal form, and a document that claimed a
            # perimeter while carrying one would announce the opposite of what
            # it holds. (ADR 0015 §4)
            for response in case.responses:
                if not response.withheld:
                    raise ValueError(
                        f"Run.redacted is set but case {case.case_id!r} still "
                        "carries a recorded answer from the target. That is the "
                        "payload itself, not a sentence about it: build the "
                        "document with redact(), which keeps the count and "
                        "drops the text"
                    )


def config_hash(
    assertions: Iterable[Assertion],
    *,
    samples: int = 1,
    min_agreement: float | None = None,
    run_assertions: Iterable[RunAssertion] = (),
    pricing: str = "",
) -> str:
    """Fingerprint of the suite *configuration*.

    `pricing` is the digest of a price the suite **declared** for its target,
    or empty. It is here for the reason a threshold is: tokens are measured, but
    a `CostBudget` judges dollars, and dollars are tokens read on a declared
    rate — change the rate and the same run passes or fails against the same
    bar. The price is the ruler, not the thing measured. Empty leaves the hash
    byte-identical, so a suite that declares nothing hashes as it always did.
    (ADR 0022 §3, §4)

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
    body: list[object] = [entries, samples, min_agreement, aggregates]
    if pricing:
        # Appended only when present: every suite that declares no price keeps
        # the exact bytes, and so the exact hash and run keys, it had before.
        body.append(pricing)
    payload = json.dumps(body, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def pricing_digest(model: str, rates: Mapping[str, float | None]) -> str:
    """The identity of one declared price, as `config_hash` takes it.

    Over the model and its rates, canonically: two suites that declare the same
    price for the same model get the same digest whichever form they are
    written in (ADR 0007 §9). Unkeyed on purpose — ADR 0022 §6 weighed a salt
    and refused it, and declares what that costs instead.
    """
    payload = json.dumps(
        {
            "model": model,
            **{
                name: None if value is None else _num(float(value))
                for name, value in rates.items()
            },
        },
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
            # Copied explicitly, and stated rather than inherited. These are
            # fields on the value, so they bypass `travels()` entirely — the
            # rule that lets `spread` cross a boundary would never have been
            # asked about them. They travel for the same reason `spread` does:
            # they measure the system's own variability, not what it judged, and
            # the software house seeing how unstable a check is without seeing
            # what it looked at is exactly the arrangement ADR 0002 produces.
            # (ADR 0006 §4)
            samples=verdict.score.samples,
            sample_min=verdict.score.sample_min,
            sample_max=verdict.score.sample_max,
            # What those numbers are, beside them, for their reason: a fact
            # about how the scores were stored, never about the case. (ADR 0024
            # §6.5)
            sample_means=verdict.score.sample_means,
        ),
        threshold=verdict.threshold,
        status=verdict.status,
        reason=REDACTED,
        tolerance=verdict.tolerance,
        assertion_id=verdict.assertion_id,
        # A fact about the check, never about the case. (ADR 0024 §6.4)
        judged=verdict.judged,
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
                # The count survives and nothing else does. No `Disclosure`
                # releases this and none may be added: *this run recorded its
                # answers and kept them back* and *this run recorded none* are
                # different facts, and only the first needs a marker to say so.
                # (ADR 0015 §4)
                responses=tuple(
                    RecordedResponse(withheld=True) for _ in case.responses
                ),
                # Carried: *which* case watched the model is a fact about the
                # suite's design, not about the end company's data, and a
                # redacted document that lost it would report an exit code its
                # own contents could not account for.
                canary=case.canary,
                # Carried for the canary's reason: a name and two numbers, and a
                # redacted document that lost them would report an exit code
                # its own contents could not account for. (ADR 0024 §9)
                calibration=case.calibration,
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
        # Carried, whatever the disclosure says, for `canary`'s reason above: it
        # is a declaration the suite author wrote, not a measurement of the end
        # company's data, and it names paths this document already carries as
        # keys. A redacted run that lost it would be a run whose exit code its
        # own contents could not account for. No `Disclosure` gates it, because
        # the alternative is a control that redaction silently disarms — which is
        # the shape ADR 0029 §3 refused for `Artifact` and must not reappear
        # here. (ADR 0029 §3, §5)
        pinned=run.pinned,
        # A model id and a temperature are measurements of the system and cross
        # on their own merit. `base_url` is the client's topology, so it — and
        # only it — is kept back, by the same rule and with the same `unknown`
        # outcome as a withheld artifact. No `Disclosure` releases it: one
        # special field, one existing rule, no new mechanism. (ADR 0005 §2)
        target_config=run.target_config.redacted(),
        judge_config=run.judge_config.redacted(),
        redacted=True,
        # Carried, not dropped. Which digline wrote a document is what makes a
        # strange file supportable, and withholding it would buy no secrecy —
        # it names our own instrument, never the end company. (ADR 0014 §3)
        digline_version=run.digline_version,
        # A run key — a timestamp and a config hash — so it carries no payload
        # and travels. Withholding it would hide from a reader that the answers
        # were replayed, which is the one thing this field exists to say.
        rejudged_from=run.rejudged_from,
        # When a person signed this off is a fact about our own process, not
        # about the end company's data, so it travels like `digline_version`.
        promoted_at=run.promoted_at,
        # And so is when it was resumed: the legs of our own instrument, never
        # anything about what it measured. (ADR 0018 §3)
        resumed_at=run.resumed_at,
        # A count of our own judge calls, never anything about what was judged.
        # (ADR 0024 §9)
        judge_samples=run.judge_samples,
        # Carried in clear. A run total is the software house's own invoice for
        # its own run: it names no case, no request and nobody, and world 2 is
        # defined by needing the signal without holding the data. The *per-call*
        # counts are payload and go with the responses above, which is why the
        # split is by grain and not by field. (ADR 0025 §8)
        usage=run.usage,
    )


def without_responses(run: Run) -> Run:
    """The same run with the target's answers removed entirely.

    What `promote_baseline` writes. `<tenant>/baselines/` is **committed**, so
    promoting a run with recording on would put the model's answers into git as
    a side effect of the most routine action in the product — in the repository
    of a software house that may hold no right to keep that end company's data.

    Removed rather than withheld, unlike redaction: a withheld marker says *this
    document kept something back*, and a baseline kept nothing back — it is a
    reference of verdicts and never had answers to keep. Nothing is lost either,
    because a replay reads a stored **run**. (ADR 0015 §5)
    """
    if not any(case.responses for case in run.results):
        return run
    return replace(
        run,
        results=tuple(replace(case, responses=()) for case in run.results),
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
    # Absent when there is one sample, never `null`: an unsampled check records
    # nothing, so a run file from a suite left at `samples=1` is byte for byte
    # the file that suite produced before ADR 0006. (ADR 0006 §4)
    if verdict.score.sampled:
        payload["samples"] = [_num(value) for value in verdict.score.samples]
        assert verdict.score.sample_min is not None
        assert verdict.score.sample_max is not None
        payload["sample_min"] = _num(verdict.score.sample_min)
        payload["sample_max"] = _num(verdict.score.sample_max)
        # Beside the samples it qualifies, and only when true: every verdict
        # whose samples are judgements writes the document it wrote before.
        # (ADR 0024 §6.5)
        if verdict.score.sample_means:
            payload["sample_means"] = True
    # Omitted, not emptied: a redacted document must carry nothing from which
    # the reason could be guessed, not even its length.
    if not redacted:
        payload["reason"] = verdict.reason
    # Written only when true, the canary's convention: a suite with no judged
    # check writes the document it wrote before, and a key named for a
    # vocabulary would invite a reader to look for values it never holds.
    # (ADR 0024 §6.4)
    if verdict.judged:
        payload["judged"] = True
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
    # Read together, and left absent together. A half-present interval is
    # refused by `Score` rather than repaired here: the missing half is not
    # derivable, and a noise floor quietly built from one end would admit
    # movement in a direction nobody measured.
    raw_samples = raw.get("samples")
    samples = (
        ()
        if raw_samples is None
        else tuple(float(value) for value in cast(Sequence[Any], raw_samples))
    )
    return Verdict(
        score=Score(
            name=str(_required(raw, "assertion", where)),
            score=None if raw_score is None else float(raw_score),
            metadata=dict(cast(Mapping[str, object], raw.get("metadata") or {})),
            samples=samples,
            sample_min=(
                None if raw.get("sample_min") is None else float(raw["sample_min"])
            ),
            sample_max=(
                None if raw.get("sample_max") is None else float(raw["sample_max"])
            ),
            sample_means=_sample_means(raw),
        ),
        threshold=float(_required(raw, "threshold", where)),
        tolerance=float(_required(raw, "tolerance", where)),
        status=cast(Status, str(_required(raw, "status", where))),
        # A redacted document has no `reason` to read; the marker keeps the
        # reconstructed verdict valid without inventing content.
        reason=REDACTED if redacted else str(_required(raw, "reason", where)),
        assertion_id=str(_required(raw, "assertion_id", where)),
        # Absent is *not recorded as judged*, which is true of every verdict
        # written before 12, and nothing is guessed from a check's name.
        judged=bool(raw.get("judged", False)),
    )


def _sample_means(raw: Mapping[str, Any]) -> bool:
    """`sample_means`, where it is written, and only as `true`.

    Absent is *not stamped* — never *these are judgements*. A document written
    at 13 stamps every fold of folds, so there the two coincide; one migrated
    from 12 holds unstamped folds the step could not derive, and the shape
    reading carries that difference by pairing. The key is written only when
    true, so anything else in it is refused by name rather than read as either.
    (ADR 0024 §6.5)
    """
    if "sample_means" not in raw:
        return False
    if raw["sample_means"] is not True:
        raise ValueError(
            f"verdict: 'sample_means' is written only as true, got "
            f"{raw['sample_means']!r}"
        )
    return True


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
        "results": [case_to_dict(case, redacted=run.redacted) for case in run.results],
        "aggregate": [
            _verdict_to_dict(v, redacted=run.redacted) for v in run.aggregate
        ],
        "artifacts": {
            path: _artifact_to_dict(item)
            for path, item in sorted(run.artifacts.items())
        },
        "target_config": config_to_dict(run.target_config),
        "judge_config": config_to_dict(run.judge_config),
        # Absent when nothing is pinned, which is the common case and is what a
        # document written before schema 16 already says. Sorted, so the document
        # does not record the order somebody typed.
        **({"pinned": sorted(run.pinned)} if run.pinned else {}),
        # Absent rather than empty, like every other unrecorded thing in this
        # document: `""` would be a value where there is none, and a migrated
        # file is exactly the case that has none (ADR 0014 §2).
        **({"digline_version": run.digline_version} if run.digline_version else {}),
        # Absent on a run that measured, present on a replay. Absent is the
        # ordinary case, so the ordinary document is unchanged. (ADR 0015 §6)
        **({"rejudged_from": run.rejudged_from} if run.rejudged_from else {}),
        # Present only on a baseline, and only on one promoted by a caller that
        # supplied the time. Absent is both "this is a run" and "nobody
        # recorded it", and neither is a date. (ADR 0014 §3)
        **({"promoted_at": run.promoted_at} if run.promoted_at else {}),
        # Absent on a run nobody resumed, which is almost every run. Absent is
        # *not resumed*, and it is never an invented time. (ADR 0018 §3)
        **({"resumed_at": list(run.resumed_at)} if run.resumed_at else {}),
        # Absent on every run that did not measure the judge's range, which is
        # all of them but one kind of replay, so no other document moves.
        # (ADR 0024 §9)
        **({"judge_samples": run.judge_samples} if run.judge_samples else {}),
        # Absent where nothing recorded it, which is every document written
        # before schema 14 and every `Run` built by hand. Absent is *not
        # recorded* and never a run that consumed nothing. (ADR 0025 §7)
        **({"usage": _run_usage_to_dict(run.usage)} if run.usage is not None else {}),
    }


def config_to_dict(config: SystemConfig) -> dict[str, object]:
    """Absent rather than emptied, like every other payload field.

    Public alongside `case_to_dict`, and for the same reason: the journal
    records the configuration a run declared and the identity it observed, and
    it records them with the document's own serializer. (ADR 0017 §3)

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


def config_from_dict(raw: Mapping[str, Any], where: str) -> SystemConfig:
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


def case_to_dict(case: CaseResult, *, redacted: bool) -> dict[str, object]:
    """One case as the document holds it.

    Public because the journal writes its case records with it (ADR 0017 §3).
    Two serializers for one value is how a journal and a run file start to
    disagree about a sampled verdict, and the disagreement would surface as a
    resumed run whose reused half is subtly not what it would have been.
    """
    payload: dict[str, object] = {
        "case_id": case.case_id,
        "suspended": case.suspended is not None,
        "verdicts": [_verdict_to_dict(v, redacted=redacted) for v in case.verdicts],
    }
    # The *fact* of suspension travels — a reader must see that coverage shrank.
    # The stated reason does not: it is payload, omitted rather than emptied.
    if case.suspended is not None and not redacted:
        payload["suspended_reason"] = case.suspended
    # Absent unless the suite asked for them, which is what keeps a run file
    # from a suite that did not opt in byte for byte the file it was before
    # ADR 0015 existed.
    if case.responses:
        payload["responses"] = [_response_to_dict(r) for r in case.responses]
    # Written only when true. Otherwise the flag would be added to every case of
    # every committed baseline in the world to say what its absence already
    # says, and a suite with no canary would stop producing the bytes it
    # produced before. (ADR 0016 §9)
    if case.canary:
        payload["canary"] = True
    # Written only when present, for the canary's reason one line up. The answer
    # the case carries is not a field of this value and so cannot be written.
    # (ADR 0024 §9)
    if case.calibration is not None:
        payload["calibration"] = {
            "check": case.calibration.check,
            "low": _num(case.calibration.low),
            "high": _num(case.calibration.high),
        }
    return payload


def usage_to_dict(usage: Usage) -> dict[str, object]:
    """The counts, with the cache fields absent where they are zero.

    Absent is not a third meaning here, unlike everywhere else in this
    document: the two cache counts *default* to zero on `Usage`, so a provider
    that reports no cached tier and one that reports zero cached tokens are the
    same record and read back the same. `input_tokens` and `output_tokens` are
    always written — they have no default, and a call that reported usage
    reported those two.
    """
    payload: dict[str, object] = {
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
    }
    if usage.cache_read_tokens:
        payload["cache_read_tokens"] = usage.cache_read_tokens
    if usage.cache_write_tokens:
        payload["cache_write_tokens"] = usage.cache_write_tokens
    # Written whenever it was **reported**, zero included: a `0` a provider
    # gave is a measurement, and dropping it as a default would turn *this
    # reply did no thinking* into *nobody said*. Absent is the third state and
    # means not reported. (ADR 0026 §1)
    if usage.thinking_tokens is not None:
        payload["thinking_tokens"] = usage.thinking_tokens
    return payload


def usage_from_dict(raw: object, where: str) -> Usage:
    """The counts back, refusing anything that is not a record of them.

    Strict about `null` on purpose. A `"usage": null` that quietly became
    *nothing was counted* would be the asymmetry the 0.15.x delta-pass found on
    `status`, where an explicit null was indistinguishable from an omitted key
    and read as success. Absent is the absence here; null is a malformed file.
    """
    if not isinstance(raw, Mapping):
        raise ValueError(
            f"{where}: usage is {raw!r}, which is not a record of token counts"
        )
    counts = cast(Mapping[str, Any], raw)
    thinking = counts.get("thinking_tokens")
    if "thinking_tokens" in counts and thinking is None:
        raise ValueError(
            f"{where}: 'thinking_tokens' is null: a provider that reported no "
            "split omits the key, and null is a document saying nothing where "
            "absence already says it"
        )
    return Usage(
        input_tokens=int(_required(counts, "input_tokens", where)),
        output_tokens=int(_required(counts, "output_tokens", where)),
        cache_read_tokens=int(counts.get("cache_read_tokens") or 0),
        cache_write_tokens=int(counts.get("cache_write_tokens") or 0),
        # `or 0` would read a reported zero as absent and vice versa, which is
        # the one distinction this field exists for.
        thinking_tokens=None if thinking is None else int(thinking),
    )


def totals_to_dict(totals: CallTotals) -> dict[str, object]:
    """One line of the bill.

    `calls`, `counted` and `spent_usd` are written even at zero: they are what
    makes the line self-describing, and a line that had to be reconstructed
    from which keys are missing is not a bill. The token counts are omitted
    when nothing was counted, because `counted: 0` has already said so.
    """
    payload: dict[str, object] = {
        "calls": totals.calls,
        "counted": totals.counted,
        "spent_usd": _num(totals.spent_usd),
    }
    if totals.counted:
        payload["tokens"] = usage_to_dict(totals.tokens)
    return payload


def totals_from_dict(raw: object, where: str) -> CallTotals:
    if not isinstance(raw, Mapping):
        raise ValueError(f"{where}: {raw!r} is not a line of the bill")
    line = cast(Mapping[str, Any], raw)
    tokens = line.get("tokens")
    return CallTotals(
        calls=int(_required(line, "calls", where)),
        counted=int(_required(line, "counted", where)),
        tokens=NO_USAGE if tokens is None else usage_from_dict(tokens, where),
        spent_usd=float(line.get("spent_usd") or 0.0),
    )


def _run_usage_to_dict(usage: RunUsage) -> dict[str, object]:
    return {
        "target": totals_to_dict(usage.target),
        "judge": totals_to_dict(usage.judge),
    }


def _run_usage_from_dict(raw: object) -> RunUsage:
    """The two lines back.

    Called only where the key is **present**, so `None` here is an explicit
    `"usage": null` and is refused rather than read as *not recorded*. The
    absence is the missing key and nothing else — the asymmetry the 0.15.x
    delta-pass found on `status`, where `.get()` plus `is None` made an
    explicit null indistinguishable from an omitted one and it read as
    success. (ADR 0025 §7)
    """
    if not isinstance(raw, Mapping):
        raise ValueError(f"run: usage is {raw!r}, which is not two lines of a bill")
    both = cast(Mapping[str, Any], raw)
    return RunUsage(
        target=totals_from_dict(_required(both, "target", "run usage"), "target"),
        judge=totals_from_dict(_required(both, "judge", "run usage"), "judge"),
    )


def _response_to_dict(response: RecordedResponse) -> dict[str, object]:
    """Whatever the recorder kept, and nothing standing in for the rest.

    Absent rather than emptied, like every other payload field in this document:
    a withheld answer carries no text and no numbers, and the flag is what tells
    a reader it was kept back rather than never recorded.
    """
    payload: dict[str, object] = {}
    if response.withheld:
        payload["withheld"] = True
        return payload
    if response.oversize:
        payload["oversize"] = True
    if response.output is not None:
        payload["output"] = response.output
    if response.kind is not None:
        payload["kind"] = response.kind
    if response.input is not None:
        payload["input"] = response.input
    if response.cost_usd is not None:
        payload["cost_usd"] = _num(response.cost_usd)
    if response.latency_ms is not None:
        payload["latency_ms"] = _num(response.latency_ms)
    if response.usage is not None:
        payload["usage"] = usage_to_dict(response.usage)
    # Absent where the target said nothing about tools, `[]` where it said the
    # model called none. A suite whose target reports no trajectory writes the
    # file it wrote before this field existed; one whose agent answered without
    # calling anything records that it did. (0.12.1)
    if response.tool_calls is not None:
        payload["tool_calls"] = [_tool_call_to_dict(c) for c in response.tool_calls]
    return payload


def _tool_call_to_dict(call: RecordedToolCall) -> dict[str, object]:
    """Absent rather than emptied, like every other payload field here.

    `status` is written only when it is not `success`: `success` is what its
    absence already says, and writing it on every call of every recorded
    response would be a key that repeats the ordinary case. (ADR 0018 §1)

    `not_reported` is therefore always **written**, and that is load-bearing: a
    0.12.x reader refuses the value by name rather than reading its absence as
    success. (ADR 0018 §1, amended 2026-09-15)

    **A call nobody named omits `tool`** and says so under its own key. Never
    `"tool": null`: every reader before schema 13 does `str()` on it and reads a
    tool named `"None"`, silently. An omitted `tool` is one they refuse by name —
    and that refusal is the only one a journal gets, because `JOURNAL_VERSION`
    does not move with `SCHEMA_VERSION`. (ADR 0018 §1, amended 2026-09-17)
    """
    payload: dict[str, object] = (
        {"tool_absence": TOOL_NOT_REPORTED}
        if call.tool is None
        else {"tool": call.tool}
    )
    if call.arguments is not None:
        payload["arguments"] = call.arguments
    if call.result is not None:
        payload["result"] = call.result
    if call.result_absence is not None:
        payload["result_absence"] = call.result_absence
    if call.status != "success":
        payload["status"] = call.status
    return payload


def _no_null(entry: Mapping[str, Any], key: str) -> None:
    """Refuse `"<key>": null` where an absent key already means something.

    A document that omits the key is saying the ordinary thing; a document that
    writes null is saying nothing at all, and the two must not arrive as one
    value. No digline writer emits either null — `_tool_call_to_dict` omits what
    it does not have — so this refuses a hand-written or forged document and
    costs a well-formed one nothing.
    """
    if key in entry and entry[key] is None:
        raise ValueError(
            f"{key!r} is null: a call that reports no {key} omits the key, and "
            "null is a document saying nothing where absence already says "
            "something"
        )


def _tool_call_from_dict(raw: object) -> RecordedToolCall:
    """Straight into the value, which does the checking — `_response_from_dict`'s
    rule, for the same reason: a document is written by whoever holds it.

    The shape is checked before the fields are read. A `tool_calls` holding
    anything but mappings — `["lookup"]`, `[5]`, a bare object — used to reach
    `_required` and raise `AttributeError`, which is not a `ValueError` and so
    escaped the CLI's handlers as a traceback. The writer refuses those same
    shapes by name; the reader now does too. (0.12.1, from the release
    delta-pass)
    """
    if not isinstance(raw, Mapping):
        raise ValueError(
            f"recorded tool call: expected a mapping with a 'tool' in it, got "
            f"{type(raw).__name__}"
        )
    entry = cast("Mapping[str, Any]", raw)
    # **Absent and null are two different things, and `.get()` made them one.**
    # `status` omitted means *success* — the convention the writer follows, since
    # writing it on every call of every response would repeat the ordinary case
    # (ADR 0018 §1). An explicit `"status": null` is a document that says
    # nothing, and reading it as success forged the one field this record calls
    # "the one field a fake cannot forge into vacuity". `tool_absence`, one line
    # below in the same function, was already refused by name — the asymmetry
    # was the finding.
    #
    # The same collapse bit again two days later on `"usage": null`, caught
    # while building 0.16.0 and closed the same way: `in` decides whether a key
    # is there, and its value is then read on its merits. One family.
    # (0.15.0 delta-pass §3)
    _no_null(entry, "status")
    _no_null(entry, "result_absence")
    status = entry.get("status")
    absence = entry.get("result_absence")
    try:
        return RecordedToolCall(
            tool=_recorded_tool(entry),
            arguments=(
                None if entry.get("arguments") is None else str(entry["arguments"])
            ),
            result=None if entry.get("result") is None else str(entry["result"]),
            status=cast(ToolStatus, "success" if status is None else str(status)),
            result_absence=(
                None if absence is None else cast(ResultAbsence, str(absence))
            ),
        )
    except ValueError as exc:
        raise ValueError(f"recorded tool call: {exc}") from exc


def _recorded_tool(entry: Mapping[str, Any]) -> str | None:
    """`tool`, or its declared absence — and nothing a reader has to guess at.

    Refused by name, each of them: `"tool": null`, which is the shape an older
    reader misreads as `"None"` and so is never written; a `tool` beside
    `tool_absence`, which says two things; and a `tool_absence` other than
    `not_reported`, because digline records every name it is given and so has
    no omission of its own to declare. (ADR 0018 §1, amended 2026-09-17)
    """
    if "tool_absence" in entry:
        if "tool" in entry:
            raise ValueError(
                "carries both 'tool' and 'tool_absence': a call is either named "
                "or not, and a reader cannot be told both"
            )
        if entry["tool_absence"] != TOOL_NOT_REPORTED:
            raise ValueError(
                f"'tool_absence' must be {TOOL_NOT_REPORTED!r}, got "
                f"{entry['tool_absence']!r}"
            )
        return None
    tool = _required(entry, "tool", "recorded tool call")
    if not isinstance(tool, str):
        raise ValueError(
            f"'tool' is {'null' if tool is None else type(tool).__name__}, not a "
            "name: a call nobody named omits 'tool' and says "
            f'"tool_absence": {TOOL_NOT_REPORTED!r}'
        )
    return tool


#: The three branches `Output` has, as the document may spell them. Read from a
#: document rather than trusted from it, like every other field here: a `kind`
#: nothing checked reached `restore_output` and failed there, one layer from the
#: name of the field that was wrong — an errored case where the honest answer is
#: a refusal that says `kind`. (0.10.1, from the release delta-pass)
_OUTPUT_KINDS: frozenset[str] = frozenset({"text", "structured", "conversation"})


def _recorded_calls(raw: Mapping[str, Any]) -> tuple[RecordedToolCall, ...] | None:
    """The trajectory, with the **container** checked before it is walked.

    0.12.1 shape-checked the elements — a `tool_calls` holding `["lookup"]` or
    `[5]` is refused by name. The container itself was not, so a scalar reached
    a `for` loop and raised a bare `TypeError`, which is **not** a `ValueError`
    and so is in none of the CLI's handler lists: `digline migrate` aborted the
    whole run instead of printing its per-file `refused <file>: <reason>` line,
    and `digline view` unwound into `socketserver` — a traceback on the terminal
    and *no response at all* in the browser. Same class as 0.12.1, one level up.
    (0.15.0 delta-pass §3)

    A string is refused rather than walked: iterating one yields characters, so
    `"lookup"` would have become six refusals about the letters of a tool name.

    Absent is `None` and `[]` is `()` — the two facts ADR 0018 §1 keeps apart —
    and a null is neither, so it is refused by name like every other null here.
    """
    if "tool_calls" not in raw:
        return None
    calls = raw["tool_calls"]
    if calls is None:
        raise ValueError(
            "recorded response: 'tool_calls' is null: a target that said nothing "
            "about tools omits the key, and one that reported no calls writes []"
        )
    if isinstance(calls, str) or not isinstance(calls, Sequence):
        raise ValueError(
            f"recorded response: 'tool_calls' is a {type(calls).__name__}, not a "
            "list of calls: the trajectory is a list, and a reader cannot walk "
            "what is not one"
        )
    return tuple(_tool_call_from_dict(c) for c in cast("Sequence[object]", calls))


def _response_from_dict(raw: Mapping[str, Any]) -> RecordedResponse:
    """Straight into the value, which does the checking — `_config_from_dict`'s
    rule, for the same reason: a document is written by whoever holds it."""
    kind = raw.get("kind")
    if kind is not None and str(kind) not in _OUTPUT_KINDS:
        raise ValueError(
            f"recorded response: 'kind' is {str(kind)!r}, which is not one of "
            f"{', '.join(sorted(_OUTPUT_KINDS))}. The kind says which branch of "
            "Output the text came from, and a replay that guessed would judge a "
            "different thing from the one that was measured"
        )
    cost = raw.get("cost_usd")
    latency = raw.get("latency_ms")
    try:
        return RecordedResponse(
            output=None if raw.get("output") is None else str(raw["output"]),
            kind=None if kind is None else cast(OutputKind, str(kind)),
            input=None if raw.get("input") is None else str(raw["input"]),
            cost_usd=None if cost is None else float(cost),
            latency_ms=None if latency is None else float(latency),
            # Absent is `None` and `[]` is `()`: the two facts the document now
            # keeps apart. `or ()` would have collapsed them again.
            tool_calls=_recorded_calls(raw),
            # Absent is `None` — a target that reported no counts — and the
            # reader refuses a null rather than reading it as nothing counted.
            usage=(
                None
                if "usage" not in raw
                else usage_from_dict(raw["usage"], "recorded response")
            ),
            withheld=bool(raw.get("withheld", False)),
            oversize=bool(raw.get("oversize", False)),
        )
    except ValueError as exc:
        raise ValueError(f"recorded response: {exc}") from exc


def case_from_dict(raw: Mapping[str, Any], *, redacted: bool) -> CaseResult:
    """The inverse, and public for the same reason: a journal is read back."""
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
        responses=tuple(
            _response_from_dict(r)
            for r in cast(Sequence[Mapping[str, Any]], raw.get("responses") or ())
        ),
        canary=bool(raw.get("canary", False)),
        calibration=_calibration_from_dict(raw.get("calibration")),
    )


def _calibration_from_dict(raw: object) -> CalibrationBand | None:
    if raw is None:
        return None
    where = "case result calibration"
    if not isinstance(raw, Mapping):
        raise ValueError(f"{where} is not an object")
    fields_ = cast(Mapping[str, Any], raw)
    return CalibrationBand(
        check=str(_required(fields_, "check", where)),
        low=float(_required(fields_, "low", where)),
        high=float(_required(fields_, "high", where)),
    )


def run_from_dict(raw: object) -> Run:
    """A stored document read back into a `Run`, or a `ValueError` saying why not.

    **Every malformed shape is a refusal, never a crash.** A document is written
    by whoever holds it, and the reader below trusts its shape field by field:
    `results: 5`, `artifacts: [1]`, `target_config: 5` or a bare `[]` for the
    whole document raised `TypeError` or `AttributeError`, which the CLI does
    not handle — so the process died with a traceback and **exit 1**, which is
    `EXIT_WORSE`: a corrupted file read, to a gate, exactly like a regression.
    Nine of thirteen malformed shapes tried did that. (Security pass of
    2026-09-23, finding 6.)

    Checking each field's shape where it is read is the style elsewhere
    (`_tool_call_from_dict`), and it gives the better message. It is also
    thirteen places, each one a place to forget. So the whole document is
    checked for being an object, and any shape error from inside is re-raised
    as a `ValueError` naming the document as malformed, with the original
    chained. The cost is stated: a genuine bug in this reader would now exit
    64 with its type in the message rather than 1 with a traceback — and exit
    64 is still a failure, where exit 1 was a false verdict.
    """
    if not isinstance(raw, Mapping):
        raise ValueError(
            f"the run document is a JSON {type(raw).__name__}, not an object"
        )
    try:
        return _run_from_mapping(cast(Mapping[str, Any], raw))
    except (TypeError, AttributeError) as exc:
        raise ValueError(
            f"the run document does not have the shape of a run "
            f"({type(exc).__name__}: {exc})"
        ) from exc


def _run_from_mapping(raw: Mapping[str, Any]) -> Run:
    version = int(raw.get("schema_version", 0))
    if version != SCHEMA_VERSION:
        raise ValueError(
            f"schema_version {version} is not supported (expected {SCHEMA_VERSION})"
        )
    results = cast(Sequence[Mapping[str, Any]], raw.get("results") or ())
    redacted = bool(_required(raw, "redacted", "run"))
    artifacts = {
        path: _artifact_from_dict(item, path)
        for path, item in cast(
            Mapping[str, Mapping[str, Any]], raw.get("artifacts") or {}
        ).items()
    }
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
        results=tuple(case_from_dict(case, redacted=redacted) for case in results),
        aggregate=tuple(
            _verdict_from_dict(v, redacted=redacted)
            for v in cast(Sequence[Mapping[str, Any]], raw.get("aggregate") or ())
        ),
        metadata=dict(cast(Mapping[str, object], raw.get("metadata") or {})),
        artifacts=artifacts,
        pinned=_pinned_from(raw, artifacts),
        target_config=config_from_dict(
            cast(Mapping[str, Any], _required(raw, "target_config", "run")),
            "target_config",
        ),
        judge_config=config_from_dict(
            cast(Mapping[str, Any], _required(raw, "judge_config", "run")),
            "judge_config",
        ),
        # Not `_required`: a document migrated from 9 carries none, and that
        # absence is a fact rather than a malformed file (ADR 0014 §2).
        digline_version=str(raw.get("digline_version") or ""),
        rejudged_from=(
            None if raw.get("rejudged_from") is None else str(raw["rejudged_from"])
        ),
        promoted_at=str(raw.get("promoted_at") or ""),
        resumed_at=tuple(
            str(stamp) for stamp in cast(Sequence[Any], raw.get("resumed_at") or ())
        ),
        judge_samples=int(raw.get("judge_samples") or 0),
        # `in`, not `.get()`: an absent key is *not recorded* and a null is a
        # malformed document, and the two must not arrive here as one value.
        usage=(None if "usage" not in raw else _run_usage_from_dict(raw["usage"])),
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
    # `ensure_ascii=False` stays, and `recordable()` is what lets it: a single
    # unpaired surrogate anywhere in provider text makes the whole document
    # un-encodable, so the run ended at exit 64 with **no file** after every
    # call had been paid for, and `--resume` replayed and died at the same byte
    # forever. `ensure_ascii=True` would fix that by escaping every accent and
    # arrow in every recorded reason, in the one artifact a human reviews in a
    # pull request — the readability that the whole escaping argument rests on.
    # So the broken code point is neutralised and nothing else is touched.
    # (from the release delta-pass over 0.15.0)
    return (
        json.dumps(
            recordable(run_to_dict(run)),
            sort_keys=True,
            indent=2,
            ensure_ascii=False,
        )
        + "\n"
    )


def run_from_json(payload: str) -> Run:
    return run_from_dict(json.loads(payload))
