"""The README, executed.

Every ```python block on the package's front page is run here, in a directory
holding the files it names. A quickstart that does not import, or that names an
argument the constructor stopped having, fails this file rather than the first
person who copies it.

Nothing in those blocks makes a call: constructing a target or a judge builds no
client and opens no socket — which is itself the property being checked, since
it is what lets `digline list` and a preflight work with no key and no SDK.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

import pytest

PACKAGE = Path(__file__).resolve().parents[1]
README = PACKAGE / "README.md"
TEXT = README.read_text(encoding="utf-8")

BLOCK_RE = re.compile(r"```python\n(.*?)```", re.DOTALL)


def blocks() -> list[str]:
    return BLOCK_RE.findall(TEXT)


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """What the snippets assume around them: a suite file to be `__file__`, and
    the prompts it points at."""
    prompts = tmp_path / "prompts"
    prompts.mkdir()
    (prompts / "answer.md").write_text("Answer this: {question}\n", encoding="utf-8")
    (prompts / "system.md").write_text("Be brief.\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def run(source: str, workspace: Path) -> dict[str, Any]:
    namespace: dict[str, Any] = {
        "__name__": "readme",
        "__file__": str(workspace / "suite.py"),
    }
    exec(compile(source, "README.md", "exec"), namespace)  # noqa: S102
    return namespace


def test_the_readme_has_the_examples_it_promises() -> None:
    """A target, two judges, one cost figure."""
    assert len(blocks()) == 4


def test_every_python_block_runs(workspace: Path) -> None:
    for source in blocks():
        run(source, workspace)


def test_the_target_block_builds_what_it_says(workspace: Path) -> None:
    target = run(blocks()[0], workspace)["target"]
    assert target.model == "claude-sonnet-5"
    assert target.prefill == "{"
    # Both files are under test, so both are in the run.
    assert len(target.artifacts()) == 2


def test_the_judge_blocks_produce_the_two_protocols(workspace: Path) -> None:
    from digline.core import ClaimJudge, Judge

    rubric = run(blocks()[1], workspace)["rubric"]
    faithful = run(blocks()[2], workspace)["faithful"]
    assert isinstance(rubric.judge, Judge)
    assert isinstance(faithful.judge, ClaimJudge)


def test_the_counters_start_where_the_readme_says(workspace: Path) -> None:
    judge = run(blocks()[3], workspace)["judge"]
    assert (judge.calls, judge.spent_usd, judge.latency_ms) == (0, 0.0, 0.0)


def test_no_block_needs_a_network_or_a_key(workspace: Path) -> None:
    """The SDK is imported on first *call*, so a page of constructions must
    leave `anthropic` unimported — with or without it installed."""
    before = "anthropic" in sys.modules
    for source in blocks():
        run(source, workspace)
    assert ("anthropic" in sys.modules) == before


def test_every_relative_link_resolves() -> None:
    """A link on a PyPI page that 404s is worse than no link."""
    for target in re.findall(r"\]\((?!https?://)([^)]+)\)", TEXT):
        assert (PACKAGE / target).exists(), target
