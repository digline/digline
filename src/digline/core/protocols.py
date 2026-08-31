"""Core abstractions. Protocols only: the core does not implement anything that
touches the outside world, it receives it injected.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol, runtime_checkable

from digline.core.types import (
    ClaimReply,
    ConfigValue,
    EvaluatorInputs,
    JudgeReply,
    OutputKind,
    Verdict,
)

__all__ = ["Assertion", "AsyncJudge", "ClaimJudge", "HasConfig", "Judge"]


@runtime_checkable
class HasConfig(Protocol):
    """Something that can say what it was configured to do.

    Asked for, never required — the same family as `Preflight` and
    `HasArtifacts` on the driver side. A `Target` is any callable and a `Judge`
    may be a two-line function in a test; making this a member of either
    protocol would stop both from being what they are. What declares nothing
    records nothing, and absent is not a change (ADR 0005 §6).

    `provider` and `model` are present whenever anything is: a configuration
    that cannot say who answered is not one.
    """

    @property
    def config(self) -> Mapping[str, ConfigValue]:
        """Flat, scalar, and only what was actually sent.

        A parameter left unset is **absent** rather than `None`: "we did not
        send it, the provider's default applied" and "we sent nothing for it"
        are different facts, and only absence states the first one honestly.
        """
        ...


@runtime_checkable
class Judge(Protocol):
    """The only I/O an assertion can reach, and the core does not supply it.

    The judge is injected: the core composes the judging prompt and validates
    the reply, but does not know who produces it. That is what keeps an
    assertion a pure function and the core free of I/O (fixed decision 1).

    In tests a fake judge is injected and `llm_rubric` becomes deterministic.
    """

    def __call__(self, prompt: str) -> JudgeReply: ...


@runtime_checkable
class ClaimJudge(Protocol):
    """A judge asked to decompose rather than to score.

    Separate from `Judge` because the two answer different questions and return
    different shapes. A `Judge` returns a score it decided; a `ClaimJudge`
    returns *what it found* — how many claims the output makes and how many of
    them the context supports — and the core does the division. That keeps the
    one piece of arithmetic in the one place that can be tested.
    """

    def __call__(self, prompt: str) -> ClaimReply: ...


@runtime_checkable
class AsyncJudge(Protocol):
    """Async variant, declared but not yet used.

    The online driver cannot score a stream of production responses with a
    blocking judge. Whether that becomes a parallel protocol or a single `async`
    protocol with a sync adapter is deferred to the ADR that introduces
    `digline.online`. What is recorded here is only that the core must not
    rule it out, and that no assertion assumes judging is instantaneous.
    """

    async def __call__(self, prompt: str) -> JudgeReply: ...


class Assertion(Protocol):
    """A pure function from `EvaluatorInputs` to `Verdict`. No I/O beyond an
    injected dependency; callable without any runner.

    Members are declared as read-only properties rather than attributes: that is
    the form a `frozen=True` dataclass field satisfies structurally. Declaring
    them as mutable attributes would force implementations to give up
    immutability.
    """

    @property
    def name(self) -> str:
        """Human-facing label in the verdict, the baseline and the comparison.
        It must be stable: renaming it shows up in the diff as a `new` plus a
        `missing`. It is *not* what `compare()` pairs on — see `identity`."""
        ...

    @property
    def identity(self) -> str:
        """Fingerprint of this assertion's full configuration, used by
        `compare()` to pair a verdict with its counterpart in the baseline.

        It exists because pairing by position is wrong and wrong silently: with
        two `contains` on the same case, swapping their order would produce a
        fabricated `regressed` plus a fabricated `improved`, and removing the
        first of three would report the third as `missing` while comparing the
        second against the first's baseline. Identity has to come from what the
        assertion *is*, not from where it sits in a list.
        """
        ...

    @property
    def threshold(self) -> float: ...

    @property
    def tolerance(self) -> float:
        """The margin below which a difference from the baseline is noise rather
        than a regression. `0.0` for deterministic assertions; explicit and
        mandatory for an LLM judgement, which is not reproducible."""
        ...

    @property
    def accepts(self) -> frozenset[OutputKind]:
        """The `Output` branches this assertion can judge. A branch it does not
        accept yields `status="error"`, never a silent conversion."""
        ...

    def __call__(self, inputs: EvaluatorInputs) -> Verdict: ...
