"""The first round of assertions.

Each one is an immutable dataclass that structurally satisfies the `Assertion`
protocol. None imports a provider, opens a file or touches the network: the only
reachable outside dependency is the `Judge` injected into `LlmRubric`.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, fields, is_dataclass
from typing import Any, ClassVar, Literal, cast

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError

from digline.core.pii import ITALIAN_PII, PiiPattern
from digline.core.protocols import Assertion, ClaimJudge, Judge
from digline.core.types import (
    ALL_KINDS,
    FLOAT_PRECISION,
    TEXT_ONLY,
    TEXT_OR_CONVERSATION,
    TEXT_OR_STRUCTURED,
    EvaluatorInputs,
    Message,
    Output,
    OutputKind,
    Score,
    Verdict,
    canonical,
    normalize_output,
    output_kind,
)

__all__ = [
    "Affix",
    "AssertionBase",
    "Contains",
    "CostBudget",
    "Equals",
    "Faithfulness",
    "IsJson",
    "JsonSchema",
    "LatencyBudget",
    "Length",
    "Levenshtein",
    "LlmRubric",
    "NotContains",
    "PiiAbsent",
    "Regex",
    "budget_score",
    "error_verdict",
    "levenshtein_distance",
]


def dataclass_identity(obj: object, excluded: frozenset[str]) -> str:
    """A stable fingerprint of a dataclass's declared fields, minus `excluded`.

    Shared by `AssertionBase` and `RunAssertionBase`: one derivation means one
    set of rules about what counts as a different check, and no chance of the
    two drifting apart.
    """
    if not is_dataclass(obj):
        raise TypeError(
            f"{type(obj).__name__} is not a dataclass, so its identity cannot "
            "be derived from its declared fields. Decorate it with "
            "@dataclass(frozen=True), or override `identity` with a stable "
            "fingerprint of what it checks."
        )
    payload = {"__type__": type(obj).__name__}
    for f in fields(cast(Any, obj)):
        if f.name in excluded:
            continue
        payload[f.name] = cast(Any, canonical(getattr(obj, f.name)))
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def error_verdict(assertion: Assertion, reason: str) -> Verdict:
    """The verdict for an assertion that could not be evaluated at all.

    Public because a driver needs it. When a target raises, every assertion on
    that case has to yield `error`, and the driver cannot get there by handing
    the failure to the assertions: they do not read `EvaluatorInputs.metadata`,
    and teaching them to read it for this would reopen the one channel ADR 0002
    closes — the route by which a mapper could put production data where an
    assertion writes its own.

    Everything an errored verdict contains is already on the `Assertion`
    protocol: name, identity, threshold, tolerance. Nothing has to be invented.
    """
    return Verdict(
        score=Score(name=assertion.name, score=None),
        threshold=assertion.threshold,
        tolerance=assertion.tolerance,
        status="error",
        reason=reason,
        assertion_id=assertion.identity,
    )


class AssertionBase:
    """Shared `Verdict` constructors, and the public extension point: a
    third-party assertion inherits from here and gets the `accepts` check plus
    the three exits (`_error`, `_graded`, `_binary`) for free.

    Deliberately not a dataclass: its annotations stay plain type declarations
    and are not collected as fields by subclasses, which remain free to order
    their own parameters as needed.

    **Contract: a subclass must itself be a dataclass.** `identity` is derived
    from the declared fields, so there is nothing to fingerprint otherwise. A
    subclass that cannot be one must override `identity`.
    """

    __slots__ = ()

    name: str
    threshold: float
    tolerance: float
    accepts: frozenset[OutputKind]

    #: Fields deliberately outside `identity`. They describe *how* a result is
    #: judged, not *what* is checked, and they already travel in every `Verdict`.
    IDENTITY_EXCLUDED: ClassVar[frozenset[str]] = frozenset({"threshold", "tolerance"})

    @property
    def identity(self) -> str:
        """Fingerprint of *what this assertion checks*: its type and its
        parameters — needle, pattern, schema, rubric, cap, the kind of judge.

        Threshold and tolerance are excluded on purpose. They are how a result
        is judged, not what is checked, and folding them in would make a raised
        threshold produce a `new` plus a `missing` instead of pairing the
        verdicts — which is precisely the comparison worth looking at, since it
        shows the effect of the configuration change. `compare()` reports that
        case as a flip and names the moved threshold in its reason; it can only
        do so if the two verdicts still meet. `config_hash` keeps them, so
        promoting a baseline across a threshold change is still refused.

        Derived generically from the dataclass fields, so a new assertion gets a
        correct identity without writing one. `canonical` is what makes it
        stable across processes: a `frozenset` field would otherwise fingerprint
        differently on every run, and an injected `Judge` — a function object
        whose `repr` carries a memory address — would do the same.

        A `Judge` therefore contributes its type name rather than its value: two
        different judges are indistinguishable here. That is a deliberate limit,
        not an oversight — which judge is wired in is a property of the run
        environment, not of the assertion the suite declares.
        """
        return dataclass_identity(self, self.IDENTITY_EXCLUDED)

    def _error(self, reason: str) -> Verdict:
        # One construction site for errored verdicts, shared with the driver.
        # The cast is safe in practice: `AssertionBase` alone is not callable,
        # but every instance reaching here is a concrete assertion that is.
        return error_verdict(cast(Assertion, self), reason)

    def _graded(
        self, value: float, reason: str, metadata: Mapping[str, object] | None = None
    ) -> Verdict:
        # Rounded before the comparison, not after: `Verdict` stores at this
        # precision, so deriving the status from the unrounded value could
        # disagree with the stored score for a value sitting exactly on the
        # threshold — and `Verdict.__post_init__` would rightly reject it.
        value = round(value, FLOAT_PRECISION)
        return Verdict(
            score=Score(name=self.name, score=value, metadata=dict(metadata or {})),
            threshold=self.threshold,
            tolerance=self.tolerance,
            status="pass"
            if value >= round(self.threshold, FLOAT_PRECISION)
            else "fail",
            reason=reason,
            assertion_id=self.identity,
        )

    def _binary(self, ok: bool, reason: str) -> Verdict:
        return self._graded(1.0 if ok else 0.0, reason)

    def _accept(self, output: Output) -> Verdict | None:
        """`None` if the output can be judged, otherwise the error `Verdict`.

        This is where the "no silent conversions" rule lives: `contains` on a
        `Mapping` must not stringify the dict and search inside it, because the
        result would be true or false for reasons unrelated to what the test
        author meant.
        """
        kind = output_kind(output)
        if kind is None:
            return self._error(
                f"output of type {type(output).__name__} is not a valid Output "
                "(expected str, Mapping or Sequence[Message])"
            )
        if kind not in self.accepts:
            accepted = ", ".join(sorted(self.accepts))
            return self._error(
                f"{self.name} does not accept '{kind}' output (accepts: {accepted})"
            )
        return None


def _as_text(output: Output) -> str:
    """Only callable once `_accept` has admitted the `text` branch."""
    assert isinstance(output, str)
    return output


@dataclass(frozen=True, slots=True)
class Equals(AssertionBase):
    """Exact equality with `inputs.expected`, on the same `Output` branch.

    Comparing different branches (a string against a dict) is a configuration
    mistake rather than a model failure, so it yields `error`.
    """

    name: str = "equals"
    threshold: float = 1.0
    tolerance: float = 0.0
    accepts: frozenset[OutputKind] = ALL_KINDS

    def __call__(self, inputs: EvaluatorInputs) -> Verdict:
        if (err := self._accept(inputs.output)) is not None:
            return err
        if inputs.expected is None:
            return self._error(
                "expected is missing: equals cannot judge without an expected value"
            )
        if (err := self._accept(inputs.expected)) is not None:
            return err

        got_kind, want_kind = output_kind(inputs.output), output_kind(inputs.expected)
        if got_kind != want_kind:
            return self._error(
                f"output is '{got_kind}' but expected is '{want_kind}': "
                "Output branches are not comparable"
            )

        ok = normalize_output(inputs.output) == normalize_output(inputs.expected)
        return self._binary(
            ok, "identical to expected" if ok else "differs from expected"
        )


@dataclass(frozen=True, slots=True)
class Contains(AssertionBase):
    """A substring present in the textual output."""

    needle: str
    case_sensitive: bool = True
    name: str = "contains"
    threshold: float = 1.0
    tolerance: float = 0.0
    accepts: frozenset[OutputKind] = TEXT_ONLY

    def __post_init__(self) -> None:
        if not self.needle:
            raise ValueError(
                "Contains.needle must not be empty: searching for '' always passes"
            )

    def __call__(self, inputs: EvaluatorInputs) -> Verdict:
        if (err := self._accept(inputs.output)) is not None:
            return err
        text = _as_text(inputs.output)
        haystack, needle = (
            (text, self.needle)
            if self.case_sensitive
            else (text.casefold(), self.needle.casefold())
        )
        ok = needle in haystack
        return self._binary(
            ok, f"'{self.needle}' {'found' if ok else 'not found'} in the output"
        )


@dataclass(frozen=True, slots=True)
class NotContains(AssertionBase):
    """A substring that must be *absent* from the textual output.

    Not `Contains` with an inverted threshold: a threshold reads as "how good",
    and a suite that expresses "must not apologise" as `threshold=0.0` would be
    green for every output including the ones that do apologise. The negation
    belongs in the assertion, where it can also say so in its `reason`.
    """

    needle: str
    case_sensitive: bool = True
    name: str = "not_contains"
    threshold: float = 1.0
    tolerance: float = 0.0
    accepts: frozenset[OutputKind] = TEXT_ONLY

    def __post_init__(self) -> None:
        if not self.needle:
            # The mirror of `Contains`: there, `''` always passes; here it always
            # fails. Both are checks that say nothing about the output.
            raise ValueError(
                "NotContains.needle must not be empty: '' is in every output, "
                "so the check would always fail"
            )

    def __call__(self, inputs: EvaluatorInputs) -> Verdict:
        if (err := self._accept(inputs.output)) is not None:
            return err
        text = _as_text(inputs.output)
        haystack, needle = (
            (text, self.needle)
            if self.case_sensitive
            else (text.casefold(), self.needle.casefold())
        )
        absent = needle not in haystack
        return self._binary(
            absent,
            f"'{self.needle}' {'absent from' if absent else 'present in'} the output",
        )


#: Which end of the output an `Affix` looks at.
type AffixEnd = Literal["start", "end"]


@dataclass(frozen=True, slots=True)
class Affix(AssertionBase):
    """A prefix or a suffix, depending on `at`.

    One assertion with a parameter rather than `StartsWith` and `EndsWith`,
    because the two differ by one method call and every rule around them —
    empty affix, case folding, what the reason says — would otherwise have to
    be written and maintained twice.

    The default `name` follows `at` (`starts_with` / `ends_with`), so the two
    uses stay distinguishable in a report and unambiguous as an aggregate's
    `over` even though they are one class.
    """

    affix: str
    at: AffixEnd = "start"
    case_sensitive: bool = True
    name: str = ""
    threshold: float = 1.0
    tolerance: float = 0.0
    accepts: frozenset[OutputKind] = TEXT_ONLY

    def __post_init__(self) -> None:
        if not self.affix:
            raise ValueError(
                "Affix.affix must not be empty: every output starts and ends with ''"
            )
        if self.at not in ("start", "end"):
            raise ValueError(f"Affix.at must be 'start' or 'end', got {self.at!r}")
        if not self.name:
            # `object.__setattr__` is how a frozen dataclass fills in a derived
            # default: normal assignment would raise. Done here rather than in a
            # property because `name` is a declared field and therefore part of
            # `identity` — it has to hold its final value before anyone reads it.
            object.__setattr__(
                self, "name", "starts_with" if self.at == "start" else "ends_with"
            )

    def __call__(self, inputs: EvaluatorInputs) -> Verdict:
        if (err := self._accept(inputs.output)) is not None:
            return err
        text = _as_text(inputs.output)
        haystack, affix = (
            (text, self.affix)
            if self.case_sensitive
            else (text.casefold(), self.affix.casefold())
        )
        ok = (
            haystack.startswith(affix)
            if self.at == "start"
            else haystack.endswith(affix)
        )
        verb = "starts with" if self.at == "start" else "ends with"
        return self._binary(
            ok, f"the output {verb if ok else 'does not ' + verb} '{self.affix}'"
        )


@dataclass(frozen=True, slots=True)
class IsJson(AssertionBase):
    """The output decodes as JSON.

    `text` only, and deliberately so: a `structured` output has already been
    decoded by whoever produced it, so this check could only ever pass on one —
    a vacuously green assertion, which decision 3 of `CLAUDE.md` forbids. Use
    `JsonSchema` when the shape matters.

    The complement of `JsonSchema` on the other side too: there, undecodable
    text is `error`, because the question asked was about a shape and could not
    be answered. Here it is `fail`, because being decodable *is* the question.

    `top_level` narrows what counts: `"object"` or `"array"` when a bare `4`
    would not do. `Score.metadata` carries the decoded kind either way, so a
    report can show what actually arrived.
    """

    top_level: Literal["any", "object", "array"] = "any"
    name: str = "is_json"
    threshold: float = 1.0
    tolerance: float = 0.0
    accepts: frozenset[OutputKind] = TEXT_ONLY

    def __post_init__(self) -> None:
        if self.top_level not in ("any", "object", "array"):
            raise ValueError(
                "IsJson.top_level must be 'any', 'object' or 'array', got "
                f"{self.top_level!r}"
            )

    def __call__(self, inputs: EvaluatorInputs) -> Verdict:
        if (err := self._accept(inputs.output)) is not None:
            return err
        try:
            decoded = json.loads(_as_text(inputs.output))
        except json.JSONDecodeError as exc:
            # The message carries a position, not the text at that position:
            # quoting the offending characters would put payload in a reason.
            return self._graded(
                0.0,
                f"does not decode as JSON: {exc.msg} at line {exc.lineno} "
                f"column {exc.colno}",
                metadata={"json_kind": "invalid"},
            )

        kind = (
            "object"
            if isinstance(decoded, dict)
            else "array"
            if isinstance(decoded, list)
            else "scalar"
        )
        ok = self.top_level == "any" or kind == self.top_level
        return self._graded(
            1.0 if ok else 0.0,
            f"decodes as JSON ({kind})"
            if ok
            else f"decodes as JSON but the top level is {kind}, not {self.top_level}",
            metadata={"json_kind": kind},
        )


#: What a `Length` counts.
type LengthUnit = Literal["characters", "words"]


@dataclass(frozen=True, slots=True)
class Length(AssertionBase):
    """The output's length, in characters or in words, within bounds.

    At least one of `minimum` and `maximum` is required: two open ends is an
    assertion that passes on everything.

    Words are counted with `str.split()`, i.e. runs of whitespace — not a
    tokenizer. Said here because "words" is the kind of word that invites an
    assumption, and a suite comparing against a provider's token count would be
    comparing two different quantities.
    """

    minimum: int | None = None
    maximum: int | None = None
    unit: LengthUnit = "characters"
    name: str = "length"
    threshold: float = 1.0
    tolerance: float = 0.0
    accepts: frozenset[OutputKind] = TEXT_ONLY

    def __post_init__(self) -> None:
        if self.minimum is None and self.maximum is None:
            raise ValueError(
                "Length needs a minimum, a maximum or both: with neither, every "
                "output passes"
            )
        if self.minimum is not None and self.minimum < 0:
            raise ValueError(f"Length.minimum must not be negative, got {self.minimum}")
        if (
            self.minimum is not None
            and self.maximum is not None
            and self.minimum > self.maximum
        ):
            raise ValueError(
                f"Length.minimum ({self.minimum}) is above its maximum "
                f"({self.maximum}): no output can satisfy both"
            )
        if self.unit not in ("characters", "words"):
            raise ValueError(
                f"Length.unit must be 'characters' or 'words', got {self.unit!r}"
            )

    def __call__(self, inputs: EvaluatorInputs) -> Verdict:
        if (err := self._accept(inputs.output)) is not None:
            return err
        text = _as_text(inputs.output)
        measured = len(text) if self.unit == "characters" else len(text.split())

        # The measurement travels even when the check passes: "how long are the
        # answers getting" is a question the metadata can answer and a pass/fail
        # cannot.
        metadata: dict[str, object] = {"length": measured, "unit": self.unit}
        if self.minimum is not None:
            metadata["minimum"] = self.minimum
        if self.maximum is not None:
            metadata["maximum"] = self.maximum

        if self.minimum is not None and measured < self.minimum:
            return self._graded(
                0.0,
                f"{measured} {self.unit}, below the minimum of {self.minimum}",
                metadata=metadata,
            )
        if self.maximum is not None and measured > self.maximum:
            return self._graded(
                0.0,
                f"{measured} {self.unit}, above the maximum of {self.maximum}",
                metadata=metadata,
            )
        bounds = (
            f"at least {self.minimum}"
            if self.maximum is None
            else f"at most {self.maximum}"
            if self.minimum is None
            else f"between {self.minimum} and {self.maximum}"
        )
        return self._graded(
            1.0, f"{measured} {self.unit}, within bounds ({bounds})", metadata=metadata
        )


def levenshtein_distance(a: str, b: str) -> int:
    """Edit distance between two strings: insertions, deletions, substitutions.

    Written out rather than taken from a package. It is twenty lines, it is the
    textbook algorithm, and `digline.core` importing a third-party library to
    compare two strings would be a dependency in the layer that Plumbline
    imports — decision 6 of `CLAUDE.md` keeps that layer bare.

    Two rows instead of the full matrix: the recurrence only ever reads the
    previous row, so an output of a few thousand characters costs `O(len(b))`
    memory instead of `O(len(a) * len(b))`.
    """
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)

    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        current = [i]
        for j, cb in enumerate(b, start=1):
            current.append(
                min(
                    previous[j] + 1,  # deletion
                    current[j - 1] + 1,  # insertion
                    previous[j - 1] + (ca != cb),  # substitution
                )
            )
        previous = current
    return previous[-1]


@dataclass(frozen=True, slots=True)
class Levenshtein(AssertionBase):
    """How close the output is to `inputs.expected`, on a 0..1 scale.

        similarity = 1 - distance / max(len(output), len(expected))

    Graded, which is the point: `Equals` answers "identical or not", and a model
    that drifts from an exact match to a near one looks exactly like a model
    that drifts to gibberish. Here the first shows as `0.97` and the second as
    `0.2`, and `compare()` can see the difference between them.

    Reads `inputs.expected` rather than holding its own target string, for the
    same reason `Equals` does: the expected value is the case's data and belongs
    with the case, not duplicated into the assertion's identity.

    Two empty strings score `1.0` — they are identical — and the denominator is
    never zero because that branch is taken first.
    """

    name: str = "levenshtein"
    threshold: float = 0.9
    tolerance: float = 0.0
    accepts: frozenset[OutputKind] = TEXT_ONLY

    def __post_init__(self) -> None:
        if not (0.0 <= self.threshold <= 1.0):
            raise ValueError(
                f"Levenshtein.threshold must be within [0, 1], got {self.threshold}"
            )

    def __call__(self, inputs: EvaluatorInputs) -> Verdict:
        if (err := self._accept(inputs.output)) is not None:
            return err
        if inputs.expected is None:
            return self._error(
                "expected is missing: levenshtein cannot judge without an "
                "expected value"
            )
        if not isinstance(inputs.expected, str):
            return self._error(
                f"expected is '{output_kind(inputs.expected)}' but levenshtein "
                "compares text"
            )

        got = _as_text(inputs.output)
        want = inputs.expected
        longest = max(len(got), len(want))
        if longest == 0:
            return self._graded(
                1.0, "both empty", metadata={"distance": 0, "length": 0}
            )

        distance = levenshtein_distance(got, want)
        similarity = 1.0 - distance / longest
        # The lengths and the distance travel; the two strings do not. A reason
        # that quoted them would be the judge's citation problem again — useful
        # inside the perimeter, unpublishable outside it.
        return self._graded(
            similarity,
            f"{distance} edit(s) over {longest} characters "
            f"(similarity {similarity:.6f})",
            metadata={"distance": distance, "length": longest},
        )


@dataclass(frozen=True, slots=True)
class Regex(AssertionBase):
    """A regular expression searched in the textual output (`re.search`)."""

    pattern: str
    name: str = "regex"
    threshold: float = 1.0
    tolerance: float = 0.0
    accepts: frozenset[OutputKind] = TEXT_ONLY

    def __post_init__(self) -> None:
        # An invalid pattern is a configuration error and must be loud at suite
        # load time, not silently `error` on every single case.
        try:
            re.compile(self.pattern)
        except re.error as exc:
            raise ValueError(f"Regex.pattern does not compile: {exc}") from exc

    def __call__(self, inputs: EvaluatorInputs) -> Verdict:
        if (err := self._accept(inputs.output)) is not None:
            return err
        ok = re.search(self.pattern, _as_text(inputs.output)) is not None
        return self._binary(
            ok, f"pattern /{self.pattern}/ {'matched' if ok else 'did not match'}"
        )


@dataclass(frozen=True, slots=True)
class JsonSchema(AssertionBase):
    """Validates the output against a JSON Schema.

    Accepts both `structured` (already decoded) and `text`, which is parsed as
    JSON — if it is not JSON the outcome is `error`, not `fail`: an undecodable
    output is a different problem from a schema violation, and conflating them
    makes the diff unreadable.
    """

    schema: Mapping[str, object]
    name: str = "json_schema"
    threshold: float = 1.0
    tolerance: float = 0.0
    accepts: frozenset[OutputKind] = TEXT_OR_STRUCTURED

    def __post_init__(self) -> None:
        try:
            Draft202012Validator.check_schema(dict(self.schema))
        except SchemaError as exc:
            raise ValueError(
                f"JsonSchema.schema is not a valid schema: {exc.message}"
            ) from exc

    def __call__(self, inputs: EvaluatorInputs) -> Verdict:
        if (err := self._accept(inputs.output)) is not None:
            return err

        # The explicit annotation is what makes jsonschema pick the first
        # `iter_errors` overload: with `Any` the resolution stays ambiguous.
        instance: str | int | float | bool | Mapping[str, Any] | Sequence[Any] | None
        if isinstance(inputs.output, str):
            try:
                instance = json.loads(inputs.output)
            except json.JSONDecodeError as exc:
                return self._error(f"output is not decodable as JSON: {exc}")
        else:
            instance = dict(cast(Mapping[str, Any], inputs.output))

        validator = Draft202012Validator(dict(self.schema))
        # The second `iter_errors` overload declares `instance: Unknown` in the
        # jsonschema types: an upstream limitation, not one of our call site.
        raw = cast(
            Iterable[ValidationError],
            validator.iter_errors(instance),  # pyright: ignore[reportUnknownMemberType]
        )
        errors = sorted(raw, key=lambda e: [str(p) for p in e.path])
        if not errors:
            return self._binary(True, "conforms to the schema")
        first = errors[0]
        location = "/".join(str(p) for p in first.path) or "(root)"
        return self._binary(
            False,
            f"{len(errors)} violation(s), first at {location}: {first.message}",
        )


@dataclass(frozen=True, slots=True)
class LlmRubric(AssertionBase):
    """An LLM judgement against a textual rubric.

    `threshold` and `tolerance` are both mandatory and have no default: an LLM
    judge is not reproducible, and an implicit tolerance over a noisy value is
    just another way of being vacuously green.
    """

    rubric: str
    judge: Judge
    threshold: float
    tolerance: float
    name: str = "llm_rubric"
    accepts: frozenset[OutputKind] = TEXT_OR_CONVERSATION

    def __post_init__(self) -> None:
        if not self.rubric:
            raise ValueError("LlmRubric.rubric must not be empty")
        if not (0.0 <= self.threshold <= 1.0):
            raise ValueError(
                f"LlmRubric.threshold must be within [0, 1], got {self.threshold}"
            )

    def _render(self, inputs: EvaluatorInputs) -> str:
        if isinstance(inputs.output, str):
            body = inputs.output
        else:
            turns = [m for m in inputs.output if isinstance(m, Message)]
            body = "\n".join(f"{m.role}: {m.content}" for m in turns)
        parts = [f"Rubric:\n{self.rubric}"]
        if inputs.input is not None:
            parts.append(f"Input:\n{inputs.input}")
        if inputs.context:
            parts.append("Context:\n" + "\n".join(inputs.context))
        parts.append(f"Output to judge:\n{body}")
        return "\n\n".join(parts)

    def __call__(self, inputs: EvaluatorInputs) -> Verdict:
        if (err := self._accept(inputs.output)) is not None:
            return err

        try:
            reply = self.judge(self._render(inputs))
        except Exception as exc:  # noqa: BLE001 — a judge that blows up is `error`, not `fail`
            return self._error(f"the judge raised {type(exc).__name__}: {exc}")

        if not (0.0 <= reply.score <= 1.0):
            return self._error(
                f"the judge returned a score outside [0, 1]: {reply.score}"
            )
        if not reply.reason:
            return self._error("the judge did not justify its score")
        return self._graded(reply.score, reply.reason)


@dataclass(frozen=True, slots=True)
class PiiAbsent(AssertionBase):
    """No personal identifier appears in the output.

    Binary, and deliberately: "a bit of PII" is not a degree of quality, so a
    graded score would only invite a threshold that means "some leakage is
    fine".

    **What travels is counts, never text.** `Score.metadata` carries one entry
    per declared pattern plus `pii_total`, and the `reason` names the kinds
    found and how many. Neither ever carries what was matched — that is the
    payload, and it is the payload precisely *because* it is an identifier.
    Every pattern is reported, including the ones that found nothing, so the
    keys stay the same across runs and samples: `pii_iban: 0` also says "we
    looked".

    **The counts are not equally certain.** `iban`, `codice_fiscale` and
    `partita_iva` carry a checksum and are verified, so a count there means
    "found one". `email` and `phone_it` have nothing to verify against, so they
    over-report by design — a run of digits shaped like a phone number is often
    an order reference. See `digline.core.pii`.

    Text only. A `structured` output would need a decision about which fields
    can hold prose, and taking that decision silently is how a check ends up
    scanning the keys and not the values.
    """

    patterns: tuple[PiiPattern, ...] = ITALIAN_PII
    name: str = "pii_absent"
    threshold: float = 1.0
    tolerance: float = 0.0
    accepts: frozenset[OutputKind] = TEXT_ONLY

    def __post_init__(self) -> None:
        if not self.patterns:
            raise ValueError(
                "PiiAbsent needs at least one pattern: with none, every output passes"
            )
        seen = [p.name for p in self.patterns]
        duplicates = sorted({n for n in seen if seen.count(n) > 1})
        if duplicates:
            # Two patterns under one name would sum into a single count, so a
            # reader could not tell which of them fired.
            raise ValueError(
                f"PiiAbsent has more than one pattern named {duplicates}: "
                "their counts would be indistinguishable"
            )

    def __call__(self, inputs: EvaluatorInputs) -> Verdict:
        if (err := self._accept(inputs.output)) is not None:
            return err
        text = _as_text(inputs.output)

        counts = {p.name: p.count(text) for p in self.patterns}
        total = sum(counts.values())
        metadata: dict[str, object] = {f"pii_{k}": v for k, v in counts.items()}
        metadata["pii_total"] = total

        if total == 0:
            checked = ", ".join(sorted(counts))
            return self._graded(
                1.0, f"no identifier found (checked: {checked})", metadata=metadata
            )
        breakdown = ", ".join(f"{v} {k}" for k, v in sorted(counts.items()) if v)
        return self._graded(
            0.0,
            f"{total} identifier(s) found: {breakdown}",
            metadata=metadata,
        )


@dataclass(frozen=True, slots=True)
class Faithfulness(AssertionBase):
    """How much of the output the context actually supports.

    The judge is asked to decompose rather than to score: it returns how many
    claims the output makes and how many of them the context supports, and the
    core does the division. A model asked directly for a fraction returns a
    number nobody can check; `ClaimReply` returns two counts, and arithmetic can
    contradict them — `supported > total` is refused at construction.

    **Why `tolerance` is mandatory, and what to do about the noise.** `total` is
    the judge's own decision: the same paragraph is three claims to one judge
    and five to another, so the denominator moves even when the output does not.
    That is a different noise from a judge scoring the same text differently —
    it is structural, and no threshold absorbs it. The remedy is `Suite.samples`
    with `Repeated`: several judgements of one output, folded by `min_agreement`
    before the verdict is settled. Tolerance covers the wobble that remains.

    Text only. In a conversation or a structured output, deciding which part
    holds the claims to be checked is a real decision — the last turn? every
    assistant turn? which fields? — and it must not be taken in silence.

    An empty `context` is `error`, never a pass: faithfulness to nothing is the
    vacuously green assertion decision 3 forbids. `total == 0` is `error` too —
    an output that makes no claims has no fraction to report, and calling that
    `1.0` would reward saying nothing.
    """

    judge: ClaimJudge
    threshold: float
    tolerance: float
    name: str = "faithfulness"
    accepts: frozenset[OutputKind] = TEXT_ONLY

    def __post_init__(self) -> None:
        if not (0.0 <= self.threshold <= 1.0):
            raise ValueError(
                f"Faithfulness.threshold must be within [0, 1], got {self.threshold}"
            )

    def _render(self, inputs: EvaluatorInputs) -> str:
        parts = [
            "Decide which claims in the output are supported by the context.",
            "A claim is supported only if the context states it or entails it. "
            "Knowing it to be true from elsewhere does not make it supported.",
            "Context:\n" + "\n".join(inputs.context),
        ]
        if inputs.input is not None:
            parts.append(f"Input:\n{inputs.input}")
        parts.append(f"Output to check:\n{_as_text(inputs.output)}")
        parts.append(
            "Report how many claims the output makes and how many of them the "
            "context supports."
        )
        return "\n\n".join(parts)

    def __call__(self, inputs: EvaluatorInputs) -> Verdict:
        if (err := self._accept(inputs.output)) is not None:
            return err
        if not inputs.context:
            return self._error(
                "context is empty: faithfulness needs something to be faithful to"
            )

        try:
            reply = self.judge(self._render(inputs))
        except Exception as exc:  # noqa: BLE001 — a judge that blows up is `error`, not `fail`
            return self._error(f"the judge raised {type(exc).__name__}: {exc}")

        if reply.total == 0:
            return self._error(
                "the judge found no claims in the output: there is no fraction "
                "to report, and a perfect score would reward saying nothing"
            )
        if reply.supported > reply.total:
            return self._error(
                f"the judge reported {reply.supported} supported of "
                f"{reply.total} claims, which is more claims than it found"
            )
        if not reply.reason:
            return self._error("the judge did not justify its counts")

        return self._graded(
            reply.supported / reply.total,
            reply.reason,
            metadata={
                "claims_total": reply.total,
                "claims_supported": reply.supported,
            },
        )


def budget_score(measured: float, cap: float) -> float:
    """Map a measured value against a cap onto a score in `(0, 1]`.

        score = cap / (cap + measured)

    Properties that make this the right shape for a budget, in order of why
    each one was needed:

    - **Exactly at cap scores `0.5`**, so a threshold of `0.5` means "within
      budget" and nothing has to be encoded twice.
    - **Strictly decreasing and never saturating.** This is the point. The
      obvious alternative, `1 - measured / (2 * cap)`, has to be clamped at `0`
      to stay a valid `Score`, and past twice the cap the clamp makes every
      overrun look identical: 3x and 10x over budget both score `0.0`, so
      `compare()` could no longer tell a bad regression from a catastrophic
      one. Here `2.5x` scores `0.2857` and `10x` scores `0.0909` — still
      distinct, still ordered.
    - **Intrinsically bounded.** With `cap > 0` and `measured >= 0` the result
      is always in `(0, 1]` by construction, so `Score`'s range invariant holds
      without a clamp. No clamp means no blind spot to document.

    The score is deliberately non-linear: it compresses as the overrun grows.
    That is acceptable because the score exists to make drift *comparable*, not
    to be read as a quantity — the raw `measured`, `cap` and `ratio` always
    travel alongside it in `Score.metadata`.
    """
    return cap / (cap + measured)


@dataclass(frozen=True, slots=True)
class CostBudget(AssertionBase):
    """A declared spending cap. Exceeding the budget fails the run.

    Scored by `budget_score(cost_usd, max_usd)`: `0.5` exactly at the cap, above
    it when under budget, below it when over. Graded rather than binary so
    `compare()` sees cost drift — from 0.01 to 0.09 under a 0.10 cap — which a
    threshold alone would never catch.

    `Score.metadata` always carries `cost_usd`, `max_usd` and their `ratio`: the
    score is a comparable quantity, the metadata is the raw truth.

    `tolerance` is mandatory and has no default, for the same reason it is
    mandatory on `LlmRubric`: cost is noisy by nature — token counts vary with
    sampling, retries and provider-side changes — so a tolerance of zero would
    make every single run report a fabricated regression or improvement.
    """

    max_usd: float
    tolerance: float
    name: str = "cost_budget"
    threshold: float = 0.5
    accepts: frozenset[OutputKind] = ALL_KINDS

    def __post_init__(self) -> None:
        if self.max_usd <= 0:
            raise ValueError(f"CostBudget.max_usd must be positive, got {self.max_usd}")

    def __call__(self, inputs: EvaluatorInputs) -> Verdict:
        # A budget does not read the output: it has nothing to reject on type.
        if inputs.cost_usd is None:
            return self._error(
                "cost_usd is missing: an unverifiable budget is not a budget met"
            )
        if inputs.cost_usd < 0:
            return self._error(f"cost_usd is negative: {inputs.cost_usd}")

        within = inputs.cost_usd <= self.max_usd
        return self._graded(
            budget_score(inputs.cost_usd, self.max_usd),
            f"{inputs.cost_usd:.6f} USD against a {self.max_usd:.6f} cap "
            f"({'within' if within else 'over'} budget)",
            metadata={
                "cost_usd": inputs.cost_usd,
                "max_usd": self.max_usd,
                "ratio": inputs.cost_usd / self.max_usd,
            },
        )


@dataclass(frozen=True, slots=True)
class LatencyBudget(AssertionBase):
    """A declared latency cap. Same scale as `CostBudget`.

    Scored by `budget_score(latency_ms, max_ms)`, with `Score.metadata` always
    carrying `latency_ms`, `max_ms` and their `ratio`.

    `tolerance` is mandatory for the same reason as on `CostBudget`, and more
    acutely: latency depends on the network and on provider load, so it is the
    noisiest signal in the system.
    """

    max_ms: float
    tolerance: float
    name: str = "latency_budget"
    threshold: float = 0.5
    accepts: frozenset[OutputKind] = ALL_KINDS

    def __post_init__(self) -> None:
        if self.max_ms <= 0:
            raise ValueError(
                f"LatencyBudget.max_ms must be positive, got {self.max_ms}"
            )

    def __call__(self, inputs: EvaluatorInputs) -> Verdict:
        if inputs.latency_ms is None:
            return self._error(
                "latency_ms is missing: an unverifiable budget is not a budget met"
            )
        if inputs.latency_ms < 0:
            return self._error(f"latency_ms is negative: {inputs.latency_ms}")

        within = inputs.latency_ms <= self.max_ms
        return self._graded(
            budget_score(inputs.latency_ms, self.max_ms),
            f"{inputs.latency_ms:.3f} ms against a {self.max_ms:.3f} cap "
            f"({'within' if within else 'over'} budget)",
            metadata={
                "latency_ms": inputs.latency_ms,
                "max_ms": self.max_ms,
                "ratio": inputs.latency_ms / self.max_ms,
            },
        )
