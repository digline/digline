"""This plugin is findable by name.

ADR 0004 §1 says a plugin ships a target and both judges; ADR 0007 §3 says a
suite may name it as `openai/<model>` and never as an import. The line that
makes the second true lives in `pyproject.toml`, which no other test in this
package reads — so a release that dropped it would publish a plugin that works
in Python and is invisible to a TOML suite.
"""

from __future__ import annotations

from digline.targets import Provider, installed, resolve
from digline_openai import (
    PROVIDER,
    OpenAIClaimJudge,
    OpenAIJudge,
    OpenAITarget,
)


def test_the_record_is_the_three_factories_adr_0004_requires() -> None:
    assert isinstance(PROVIDER, Provider)
    assert PROVIDER.name == "openai"
    assert PROVIDER.target is OpenAITarget
    assert PROVIDER.judge is OpenAIJudge
    assert PROVIDER.claim_judge is OpenAIClaimJudge


def test_the_entry_point_is_declared_and_resolves() -> None:
    """Reads the installed metadata, not this source: what is under test is the
    registration, and an editable install carries it the same way a wheel does.
    """
    assert "openai" in installed()
    assert resolve("openai") is PROVIDER
