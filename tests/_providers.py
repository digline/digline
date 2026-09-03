"""A fake provider plugin, for the registry's tests and the loader's.

Here rather than in a test module for a reason that is the point of the thing
under test: an entry point names a module *by import path*, and
`EntryPoint.load()` imports it under that name. A test module has no stable
import name — `tests/` has no `__init__.py`, so pytest loads
`tests/test_registry.py` as top-level `test_registry` — and pointing an entry
point at `tests.test_registry` would import a **second copy** of it, whose
objects are equal to the originals and identical to none of them.

A plain module imported by name, the rule `_helpers.py` already sets, is the
one shape that gives `resolve()` back the very object this file defines.

The three fakes are **classes**, because that is what a plugin registers: a
`Provider` holds factories, and `AnthropicJudge` is constructed with the model
and its set-up before it grades anything. A fake that was already an instance
would type-check as the wrong thing and would hide the difference.
"""

from __future__ import annotations

from digline.core import ClaimReply, JudgeReply
from digline.run import Case, Response
from digline.targets import Provider

__all__ = [
    "BUCKET",
    "MISNAMED",
    "NOT_A_PROVIDER",
    "REGISTERED",
    "BucketTarget",
    "FakeClaimJudge",
    "FakeJudge",
    "FakeTarget",
]


class FakeTarget:
    """Built with a model and the settings the suite declared, called once per
    case — the shape of every plugin's target, with no provider behind it.

    The parameters are **named**, like every real plugin's: none of the three
    published ones takes a `**kwargs` bucket, and a fake that did would make the
    loader's refusals look different here from the way they look in use.
    """

    def __init__(
        self,
        model: str,
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> None:
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

    def __call__(self, case: Case) -> Response:
        return Response(output=f"{self.model} answered {case.id}")


class FakeJudge:
    def __init__(
        self,
        model: str,
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> None:
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

    def __call__(self, prompt: str) -> JudgeReply:
        return JudgeReply(score=1.0, reason=f"{self.model} read {len(prompt)}")


class FakeClaimJudge:
    def __init__(self, model: str) -> None:
        self.model = model

    def __call__(self, prompt: str) -> ClaimReply:
        return ClaimReply(
            supported=1, total=1, reason=f"{self.model} read {len(prompt)}"
        )


class BucketTarget:
    """A plugin that takes anything and names nothing.

    Exists for one decision: a `**kwargs` bucket is not "anything goes". ADR
    0007 §5 admits only the parameters a plugin *exposes* as declarative
    configuration, and what a bucket would buy is a plugin quietly accepting
    `temperture` — a setting written in the file, never reaching the model, in
    a run that goes green.
    """

    def __init__(self, model: str, **anything: object) -> None:
        self.model = model
        self.anything = anything

    def __call__(self, case: Case) -> Response:
        return Response(output=f"{self.model} answered {case.id}")


#: A well-formed plugin.
REGISTERED = Provider(
    name="fake", target=FakeTarget, judge=FakeJudge, claim_judge=FakeClaimJudge
)

#: Registered under one name, calling itself another.
MISNAMED = Provider(
    name="other", target=FakeTarget, judge=FakeJudge, claim_judge=FakeClaimJudge
)

#: A plugin whose target swallows every keyword it is given.
BUCKET = Provider(
    name="bucket", target=BucketTarget, judge=FakeJudge, claim_judge=FakeClaimJudge
)

#: A plugin that registered something that is not a `Provider` at all.
NOT_A_PROVIDER = "a string is not a plugin"
