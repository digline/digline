"""Fixtures for this package's tests. The fakes are in `_bedrock_fakes`."""

from __future__ import annotations

from pathlib import Path

import pytest
from _bedrock_fakes import FakeClient


@pytest.fixture
def client() -> FakeClient:
    return FakeClient()


@pytest.fixture
def prompt(tmp_path: Path) -> Path:
    path = tmp_path / "answer.md"
    path.write_text("What is the capital of {country}?\n", encoding="utf-8")
    return path
