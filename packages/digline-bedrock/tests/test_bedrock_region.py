"""The sentence for a missing region names the variable botocore reads. (#688)

botocore reads the region from `AWS_DEFAULT_REGION`, not from `AWS_REGION`:
set on its own, `AWS_REGION` gives no region, and a user who followed a
sentence naming it got the same sentence back. Measured on 2026-10-24 with no
profile and no instance metadata, at boto3/botocore 1.35.0 — the oldest this
plugin admits — and at 1.43.114, the locked one: `AWS_DEFAULT_REGION` gave a
region at both, `AWS_REGION` alone at neither.

No network and no AWS here: `boto3.client` is replaced by one that raises
`NoRegionError`, which is what botocore raises at construction when the chain
gives no region.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
from botocore.exceptions import (  # pyright: ignore[reportMissingTypeStubs]
    NoRegionError,
)

from digline_bedrock import BedrockTarget
from digline_bedrock.client import build_client

#: `AWS_REGION` as a variable of its own, not as the tail of AWS_DEFAULT_REGION.
AWS_REGION = re.compile(r"(?<![A-Z_])AWS_REGION\b")


@pytest.fixture
def no_region(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*args: Any, **kwargs: Any) -> Any:
        raise NoRegionError()

    monkeypatch.setattr("boto3.client", refuse)


def _sentence() -> str:
    with pytest.raises(ValueError) as raised:
        build_client(None)
    return str(raised.value)


@pytest.mark.usefixtures("no_region")
def test_the_sentence_names_aws_default_region() -> None:
    said = _sentence()
    assert "set AWS_DEFAULT_REGION" in said
    assert not AWS_REGION.search(said), said


@pytest.mark.usefixtures("no_region")
def test_the_sentence_still_names_the_argument_and_the_client() -> None:
    said = _sentence()
    assert "Pass `region=` to the target" in said
    assert "pass a `client=` that already has one" in said


@pytest.mark.usefixtures("no_region")
def test_a_target_with_no_region_says_it_at_construction(tmp_path: Path) -> None:
    prompt = tmp_path / "answer.md"
    prompt.write_text("Answer this: {question}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="set AWS_DEFAULT_REGION"):
        BedrockTarget(prompt, "anthropic.claude-3-haiku-20240307-v1:0", 64)


def test_the_docstring_names_the_variable_the_chain_reads() -> None:
    doc = build_client.__doc__ or ""
    assert "AWS_DEFAULT_REGION" in doc
    assert not AWS_REGION.search(doc), doc


def test_the_pattern_tells_the_two_variables_apart() -> None:
    """The control for the two tests that refuse `AWS_REGION`: it is found on
    its own and not inside `AWS_DEFAULT_REGION`."""
    assert AWS_REGION.search("set AWS_REGION, or")
    assert not AWS_REGION.search("set AWS_DEFAULT_REGION, or")
