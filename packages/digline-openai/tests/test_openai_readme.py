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
    """What the README's snippets assume around them: a prompt, and the one
    variable the Azure example reads by name."""
    prompts = tmp_path / "prompts"
    prompts.mkdir()
    (prompts / "answer.md").write_text("Answer this: {question}\n", encoding="utf-8")
    (prompts / "system.md").write_text("Be brief.\n", encoding="utf-8")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "sk-not-a-real-key")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_the_readme_has_the_examples_it_promises() -> None:
    """Three providers, two judges, one cost figure. If a section goes, this
    number moves and somebody has to look at why."""
    assert len(blocks()) == 7


@pytest.mark.parametrize("index", range(7))
def test_every_python_block_runs(workspace: Path, index: int) -> None:
    namespace: dict[str, Any] = {"__name__": "readme"}
    exec(compile(blocks()[index], f"README.md[{index}]", "exec"), namespace)  # noqa: S102


def test_the_quickstarts_build_what_they_say_they_build(workspace: Path) -> None:
    """Executing is not enough: a block that quietly built the wrong endpoint
    would still run. These are the three sentences the README makes."""
    built: list[dict[str, Any]] = []
    for source in blocks():
        namespace: dict[str, Any] = {"__name__": "readme"}
        exec(compile(source, "README.md", "exec"), namespace)  # noqa: S102
        built.append(namespace)

    official, azure, ollama = built[0], built[1], built[2]
    assert official["target"].chat.base_url is None
    assert official["target"].model == "gpt-5"
    assert "azure.com" in azure["target"].chat.base_url
    assert ollama["target"].chat.base_url == "http://localhost:11434/v1"
    # And the self-hosted model is priced, at zero, on purpose.
    assert ollama["target"].pricing.knows("llama3.2")
    assert ollama["target"].pricing.cost("llama3.2", _a_million()) == 0.0


def test_the_judge_examples_produce_the_two_protocols(workspace: Path) -> None:
    from digline.core import ClaimJudge, Judge

    namespaces: list[dict[str, Any]] = []
    for source in blocks():
        namespace: dict[str, Any] = {"__name__": "readme"}
        exec(compile(source, "README.md", "exec"), namespace)  # noqa: S102
        namespaces.append(namespace)

    rubric = namespaces[3]["rubric"]
    faithful = namespaces[4]["faithful"]
    assert isinstance(rubric.judge, Judge)
    assert isinstance(faithful.judge, ClaimJudge)
    # The local judge runs at the local endpoint, which is the whole claim.
    assert namespaces[5]["local"].chat.base_url == "http://localhost:11434/v1"
    assert namespaces[6]["judge"].calls == 0


def test_no_block_needs_a_network_or_a_key(workspace: Path) -> None:
    """The SDK is imported on first *call*, so a page of constructions must
    leave `openai` unimported — with or without it installed."""
    import sys

    before = "openai" in sys.modules
    for source in blocks():
        exec(compile(source, "README.md", "exec"), {"__name__": "readme"})  # noqa: S102
    assert ("openai" in sys.modules) == before


def test_every_relative_link_resolves() -> None:
    """A link on a PyPI page that 404s is worse than no link."""
    for target in re.findall(r"\]\((?!https?://)([^)]+)\)", TEXT):
        assert (PACKAGE / target).exists(), target


def _a_million() -> Any:
    from digline.targets import Usage

    return Usage(input_tokens=1_000_000, output_tokens=1_000_000)
