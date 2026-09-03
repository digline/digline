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
    "MISNAMED",
    "NOT_A_PROVIDER",
    "REGISTERED",
    "FakeClaimJudge",
    "FakeJudge",
    "FakeTarget",
]


class FakeTarget:
    """Built with a model and whatever the suite declared, called once per
    case — the shape of every plugin's target, with no provider behind it."""

    def __init__(self, model: str, **settings: object) -> None:
        self.model = model
        self.settings = settings

    def __call__(self, case: Case) -> Response:
        return Response(output=f"{self.model} answered {case.id}")


class FakeJudge:
    def __init__(self, model: str, **settings: object) -> None:
        self.model = model
        self.settings = settings

    def __call__(self, prompt: str) -> JudgeReply:
        return JudgeReply(score=1.0, reason=f"{self.model} read {len(prompt)}")


class FakeClaimJudge:
    def __init__(self, model: str, **settings: object) -> None:
        self.model = model
        self.settings = settings

    def __call__(self, prompt: str) -> ClaimReply:
        return ClaimReply(
            supported=1, total=1, reason=f"{self.model} read {len(prompt)}"
        )


#: A well-formed plugin.
REGISTERED = Provider(
    name="fake", target=FakeTarget, judge=FakeJudge, claim_judge=FakeClaimJudge
)

#: Registered under one name, calling itself another.
MISNAMED = Provider(
    name="other", target=FakeTarget, judge=FakeJudge, claim_judge=FakeClaimJudge
)

#: A plugin that registered something that is not a `Provider` at all.
NOT_A_PROVIDER = "a string is not a plugin"
