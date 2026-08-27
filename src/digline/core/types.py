"""Core domain types.

Immutable values, no I/O, no imports from other digline packages. See
`docs/adr/0001-verdict-not-score.md` for why `Verdict` has three states and why
`Output` is a closed union.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from collections.abc import Set as AbstractSet
from dataclasses import asdict, dataclass, field, is_dataclass
from typing import Literal, cast

__all__ = [
    "ALL_KINDS",
    "CONVERSATION_ONLY",
    "STRUCTURED_ONLY",
    "FLOAT_PRECISION",
    "NOTHING_EXTRA",
    "REDACTED",
    "ClaimReply",
    "Disclosure",
    "EvaluatorInputs",
    "JudgeReply",
    "Message",
    "Output",
    "OutputKind",
    "Score",
    "Status",
    "TEXT_ONLY",
    "TEXT_OR_CONVERSATION",
    "TEXT_OR_STRUCTURED",
    "Verdict",
    "canonical",
    "normalize_output",
    "output_kind",
    "travels",
]

#: In-memory marker for a payload field that has been removed. On the wire the
#: field is *absent*, not set to this: a redacted document must carry nothing
#: from which the original could be guessed. The marker exists so that a
#: redacted `Verdict` is still a valid one — `reason` stays mandatory.
REDACTED = "<redacted>"


def travels(value: object) -> bool:
    """Whether a metadata value may cross a boundary on its own merit.

    Numbers and booleans may: they are measurements. Strings may not — nothing
    about a string says where it came from, and the conservative reading is the
    only safe one when the text may be a fragment of a customer's data.

    This is the rule for `Score.metadata`, which only assertions write. It is
    deliberately *not* the rule for `Run.metadata` — see `Disclosure`.
    """
    return isinstance(value, bool | int | float)


@dataclass(frozen=True, slots=True)
class Disclosure:
    """Metadata keys a suite declares may cross a boundary beyond the default.

    Declared in code, never read from data: widening what leaves a perimeter has
    to be an edit someone makes and a reviewer sees.

    The two halves follow different rules, and the asymmetry is the point:

    - `score_metadata` — written only by assertions, so measurements already
      travel by `travels()`. This adds *string* keys, e.g. a model name.
    - `run_metadata` — whatever an integration chose to annotate from
      production, so **nothing travels by default, numbers included**. `0.909091`
      written by `CostBudget` is a measurement; `1499.00` copied out of a
      customer's request is their data wearing the same clothes.

    The default is the empty one, so code that redacts without knowing the
    suite's policy discloses *less*, never more.

    `artifacts` follows that rule rather than making an exception of itself.
    The prompt is the software house's own file, which argues for letting it
    travel — but it is written *for* an end company and is where that company's
    rules end up, so no default can tell the two apart by looking. Opting in is
    one line in the suite, and the suite goes through a review. (ADR 0003)
    """

    score_metadata: frozenset[str] = frozenset()
    run_metadata: frozenset[str] = frozenset()
    #: Whether the declared artifacts — content and digest — cross a boundary.
    artifacts: bool = False


NOTHING_EXTRA = Disclosure()

# `type` (PEP 695, Python 3.12+) declares a lazy type alias: no `TypeAlias`
# needed, and the right-hand side is not evaluated until something inspects it.
type Status = Literal["pass", "fail", "error"]
type OutputKind = Literal["text", "structured", "conversation"]

# The baseline is a committed file whose purpose is to be read in a code review.
# A diff that churns on the seventeenth digit of a float gets read by nobody.
FLOAT_PRECISION = 6


def canonical(value: object) -> object:
    """Recursively reduce `value` to a JSON-serializable, deterministic form.

    Used both to serialize a baseline and to fingerprint an assertion, so
    determinism is not cosmetic here: a value whose canonical form varies
    between processes would make a committed baseline churn on every run and an
    assertion identity unstable across runs.

    That is why sets are sorted, floats are rounded, and anything unrecognised
    collapses to its **type name** rather than its `repr` — the default `repr`
    of a plain object embeds a memory address, which changes every process.
    """
    if value is None or isinstance(value, bool | int | str):
        return value
    if isinstance(value, float):
        # NaN and the infinities have no JSON representation and no meaningful
        # rounding; keep them as text so they survive visibly instead of
        # becoming `null`.
        if math.isnan(value) or math.isinf(value):
            return str(value)
        return round(value, FLOAT_PRECISION)
    if isinstance(value, bytes | bytearray):
        return value.hex()
    if isinstance(value, Mapping):
        items = cast(Mapping[object, object], value)
        return {str(k): canonical(items[k]) for k in sorted(items, key=str)}
    if isinstance(value, AbstractSet):
        # Set iteration order is not stable across processes; sorting the
        # rendered elements is what makes a `frozenset` field fingerprintable.
        return sorted(str(canonical(v)) for v in cast(AbstractSet[object], value))
    if isinstance(value, Sequence):
        return [canonical(v) for v in cast(Sequence[object], value)]
    if is_dataclass(value) and not isinstance(value, type):
        return canonical(asdict(value))
    return f"<{type(value).__name__}>"


@dataclass(frozen=True, slots=True)
class Message:
    """One conversation turn. `content` is text: structured tool calls belong in
    the `Mapping` branch of `Output`, not flattened into a string."""

    role: str
    content: str


# Closed union. Changing it later means rewriting every assertion, so it is
# settled now even though the first assertions mostly use the `str` branch.
type Output = str | Mapping[str, object] | Sequence[Message]


def output_kind(output: object) -> OutputKind | None:
    """The union branch `output` belongs to, or `None` if it is not a valid
    `Output`. Check order matters: `str` is itself a `Sequence`, so it has to be
    caught first.

    **An empty sequence is a `conversation`**, deliberately and not by accident
    of `all()` returning `True` on an empty iterable. A model that produced no
    turns is a real outcome worth judging — an agent that gave up, a filter that
    stripped everything — and calling it "not a valid Output" would report a
    configuration error where there was a behavioural one. Assertions that
    receive it judge an empty conversation on its merits.
    """
    if isinstance(output, str):
        return "text"
    if isinstance(output, Mapping):
        return "structured"
    if isinstance(output, Sequence):
        items = cast(Sequence[object], output)
        if all(isinstance(m, Message) for m in items):
            return "conversation"  # including the empty sequence, see above
    return None


def normalize_output(output: Output) -> object:
    """Canonical form for equality comparison, applied **recursively**.

    Needed because a conversation may arrive as a `list` or a `tuple`, and
    `["a"] == ("a",)` is `False` in Python: without normalization `equals` would
    fail because of the container type rather than the content.

    Recursion is what makes it correct at depth. A shallow `dict(output)` leaves
    `{"a": ["x"]}` and `{"a": ("x",)}` unequal — the same defect, one level
    down, where it is harder to notice. Structured agent output nests, so this
    is the common case rather than an edge one.
    """
    return _normalize(output)


def _normalize(value: object) -> object:
    if isinstance(value, str | bytes | bytearray):
        return value
    if isinstance(value, Mapping):
        items = cast(Mapping[object, object], value)
        # Dicts already compare by content regardless of insertion order, so the
        # keys are left alone; only the values need normalizing.
        return {k: _normalize(items[k]) for k in items}
    if isinstance(value, Sequence):
        return tuple(_normalize(v) for v in cast(Sequence[object], value))
    return value


@dataclass(frozen=True, slots=True)
class Score:
    """A raw score. Deliberately the same shape as `autoevals.Score` — an
    interoperability commitment rather than imitation: it makes the two-way
    adapter a handful of lines (see `digline.core.adapters`).

    `score is None` means "no score". It does not mean "passed": that case
    always translates to a `Verdict` with `status="error"`.
    """

    name: str
    score: float | None = None
    metadata: Mapping[str, object] = field(default_factory=dict[str, object])

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("Score.name must not be empty")
        if self.score is None:
            return
        # Checked explicitly rather than relying on `0.0 <= nan <= 1.0` being
        # False: that comparison rejects NaN by accident, with a message that
        # sends the reader looking for a range problem.
        if math.isnan(self.score):
            raise ValueError("Score.score must not be NaN")
        if not (0.0 <= self.score <= 1.0):
            raise ValueError(f"Score.score must be within [0, 1], got {self.score}")


@dataclass(frozen=True, slots=True)
class Verdict:
    """What an assertion produces and what a driver consumes. Never a bare
    `Score`: a number without a threshold is not an outcome.

    `threshold` does not accept `None`. With no "unset" state to represent, a
    default that always passes cannot exist (fixed decision 3).

    `tolerance` is recorded here and not only on the assertion, so `compare()`
    is self-sufficient with two arguments and a baseline file carries everything
    needed to interpret it.

    `assertion_id` is the identity `compare()` pairs on — see
    `AssertionBase.identity`. It defaults to the score name, which is correct
    whenever a case carries one assertion per name; assertions built through
    `AssertionBase` always supply the real fingerprint.
    """

    score: Score
    threshold: float
    status: Status
    reason: str
    tolerance: float = 0.0
    assertion_id: str = ""

    def __post_init__(self) -> None:
        # Standard frozen-dataclass idiom: `__post_init__` is the one place
        # allowed to write a field, and it must go through `object`.
        if not self.assertion_id:
            object.__setattr__(self, "assertion_id", self.score.name)

        # A Verdict carries exactly what gets persisted, at storage precision.
        #
        # Without this, a score of 0.9090909090909092 is written to the baseline
        # as 0.909091 and read back as 0.909091, while the next run holds the
        # unrounded value — so `compare()` sees a delta of -9e-8 and, with the
        # default tolerance of 0, reports a *phantom regression on every run*.
        # In-memory tests never catch it because both sides are unrounded; it
        # only appears against a baseline that has been through the disk.
        #
        # Rounding here rather than in `compare()` makes it an invariant of the
        # value instead of a courtesy of one caller: a Verdict and its
        # round-tripped copy are indistinguishable.
        object.__setattr__(self, "threshold", round(self.threshold, FLOAT_PRECISION))
        object.__setattr__(self, "tolerance", round(self.tolerance, FLOAT_PRECISION))
        if self.score.score is not None:
            rounded = round(self.score.score, FLOAT_PRECISION)
            if rounded != self.score.score:
                object.__setattr__(
                    self,
                    "score",
                    Score(
                        name=self.score.name,
                        score=rounded,
                        metadata=self.score.metadata,
                    ),
                )

        if not self.reason:
            raise ValueError(
                "Verdict.reason is mandatory: an outcome without a stated "
                "reason cannot be reviewed"
            )
        if not (0.0 <= self.threshold <= 1.0):
            raise ValueError(
                f"Verdict.threshold must be within [0, 1], got {self.threshold}"
            )
        if self.tolerance < 0.0:
            raise ValueError(
                f"Verdict.tolerance must not be negative, got {self.tolerance}"
            )
        if self.status == "error":
            if self.score.score is not None:
                raise ValueError("a Verdict in error must not carry a score")
            return
        if self.score.score is None:
            raise ValueError(
                "a missing score must produce status='error', never 'pass' or 'fail'"
            )
        # One fact, one source. `status` and `score >= threshold` are the same
        # statement, so a Verdict that disagrees with itself must not exist:
        # otherwise the run table and the pass/fail gate could tell a reviewer
        # two different stories about the same result.
        expected: Status = "pass" if self.score.score >= self.threshold else "fail"
        if self.status != expected:
            raise ValueError(
                f"status={self.status!r} contradicts score {self.score.score} "
                f"against threshold {self.threshold} (implies {expected!r})"
            )

    @property
    def passed(self) -> bool:
        """Derived, not stored: two sources of truth for one fact always drift
        apart eventually."""
        return self.status == "pass"

    @property
    def name(self) -> str:
        return self.score.name


@dataclass(frozen=True, slots=True)
class EvaluatorInputs:
    """The only input an assertion receives, built by a mapper.

    The core does not know what a trace, a matrix or a stream is: it receives
    *one* response. The matrix is an iteration the offline driver performs; this
    type has no notion of it (fixed decision 7).

    `input` is the name the surrounding ecosystem uses for this field, and
    `digline.core.adapters` is cheap only while the names line up. It shadows
    the builtin only inside the dataclass, where the builtin is not needed.

    `metadata` is what a mapper carries in from the outside, and **nothing in
    the core copies it into a `Score`**. That is structural, not a convention:
    an assertion writes its own `Score.metadata` from what it measured, and a
    mapper has no route into it. Whatever an integration wants to annotate from
    production belongs in `Run.metadata`, where the strict half of `Disclosure`
    applies.
    """

    output: Output
    input: str | None = None
    expected: Output | None = None
    context: Sequence[str] = ()
    cost_usd: float | None = None
    latency_ms: float | None = None
    metadata: Mapping[str, object] = field(default_factory=dict[str, object])


@dataclass(frozen=True, slots=True)
class JudgeReply:
    """A judge's reply. `score` within [0, 1], `reason` mandatory.

    Validated at construction rather than trusted, because this is the boundary
    where an LLM enters the core: it is the least reliable input in the system,
    and the docstring promising a range is worth nothing if nothing enforces it.
    """

    score: float
    reason: str

    def __post_init__(self) -> None:
        if math.isnan(self.score):
            raise ValueError("JudgeReply.score must not be NaN")
        if not (0.0 <= self.score <= 1.0):
            raise ValueError(
                f"JudgeReply.score must be within [0, 1], got {self.score}"
            )
        if not self.reason:
            raise ValueError(
                "JudgeReply.reason is mandatory: an unexplained judgement "
                "cannot be reviewed"
            )


@dataclass(frozen=True, slots=True)
class ClaimReply:
    """A judge's reply when the question is "how much of this is supported".

    Two counts rather than a ratio, and the division is done by the core. A
    model asked for `supported / total` returns a number nobody can check; asked
    for the two counts it returns something arithmetic can contradict — which is
    what `__post_init__` does below.

    Same boundary role as `JudgeReply`: this is where an LLM enters the core,
    so it is validated rather than trusted.
    """

    supported: int
    total: int
    reason: str

    def __post_init__(self) -> None:
        if self.total < 0 or self.supported < 0:
            raise ValueError(
                "ClaimReply counts must not be negative, got "
                f"supported={self.supported}, total={self.total}"
            )
        if self.supported > self.total:
            raise ValueError(
                f"ClaimReply says {self.supported} of {self.total} claims are "
                "supported, which is more claims than it found"
            )
        if not self.reason:
            raise ValueError(
                "ClaimReply.reason is mandatory: an unexplained judgement "
                "cannot be reviewed"
            )


TEXT_ONLY: frozenset[OutputKind] = frozenset({"text"})
TEXT_OR_STRUCTURED: frozenset[OutputKind] = frozenset({"text", "structured"})
TEXT_OR_CONVERSATION: frozenset[OutputKind] = frozenset({"text", "conversation"})
CONVERSATION_ONLY: frozenset[OutputKind] = frozenset({"conversation"})
STRUCTURED_ONLY: frozenset[OutputKind] = frozenset({"structured"})
ALL_KINDS: frozenset[OutputKind] = frozenset({"text", "structured", "conversation"})
