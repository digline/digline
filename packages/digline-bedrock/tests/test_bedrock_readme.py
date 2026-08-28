"""The README, executed.

Every ```python block on the package's front page is run here, in a directory
holding the files it names. A quickstart that does not import, or that names an
argument the constructor stopped having, fails this file rather than the first
person who copies it.

`AWS_REGION` is set for the duration, because the first example's whole claim is
that the region comes from the chain. Nothing else is needed: building a client
reaches no network and asks for no credentials, which is what makes a page of
constructions runnable in CI with no AWS account behind it.
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
    prompts = tmp_path / "prompts"
    prompts.mkdir()
    (prompts / "answer.md").write_text("Answer this: {question}\n", encoding="utf-8")
    monkeypatch.setenv("AWS_REGION", "eu-west-1")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "eu-west-1")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def run(source: str) -> dict[str, Any]:
    namespace: dict[str, Any] = {"__name__": "readme"}
    exec(compile(source, "README.md", "exec"), namespace)  # noqa: S102
    return namespace


def test_the_readme_has_the_examples_it_promises() -> None:
    """Two targets, two judges, one cost figure, two price lists. If a section
    goes, this number moves and somebody has to look at why."""
    assert len(blocks()) == 7


@pytest.mark.parametrize("index", range(7))
def test_every_python_block_runs(workspace: Path, index: int) -> None:
    run(blocks()[index])


def test_the_region_comes_from_the_chain_and_from_the_argument(
    workspace: Path,
) -> None:
    """The two quickstarts make two different claims, and both are checkable."""
    from_chain = run(blocks()[0])["target"]
    explicit = run(blocks()[1])["target"]
    assert from_chain.region == "eu-west-1"
    assert explicit.region == "us-east-1"
    # And each one is priced by its own region.
    assert from_chain.pricing.knows("eu.anthropic.claude-sonnet-4-20250514-v1:0")
    assert explicit.pricing.knows("us.anthropic.claude-haiku-4-5-20251001-v1:0")


def test_the_judge_examples_produce_the_two_protocols(workspace: Path) -> None:
    from digline.core import ClaimJudge, Judge

    rubric = run(blocks()[2])["rubric"]
    faithful = run(blocks()[3])["faithful"]
    assert isinstance(rubric.judge, Judge)
    assert isinstance(faithful.judge, ClaimJudge)
    assert run(blocks()[4])["judge"].calls == 0


def test_the_pricing_examples_price_what_they_claim(workspace: Path) -> None:
    from digline.targets import Usage

    overridden = run(blocks()[5])["target"]
    assert overridden.pricing.knows("amazon.nova-pro-v1:0")
    overridden.preflight([])

    imported = run(blocks()[6])["target"]
    assert (
        imported.pricing.cost("my-imported-model", Usage(1_000_000, 1_000_000)) == 0.0
    )


def test_no_block_needs_a_network_or_a_credential(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The premise of every example above, made falsifiable.

    Constructing builds a client — that is where the region comes from — but
    botocore resolves credentials on the *first call*, not in the constructor.
    So the page runs with every credential taken out of the environment, which
    is what CI looks like. If construction ever started needing an account, this
    is where it would show.
    """
    for name in (
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_SESSION_TOKEN",
        "AWS_PROFILE",
        "AWS_ROLE_ARN",
    ):
        monkeypatch.delenv(name, raising=False)

    for source in blocks():
        namespace = run(source)
        bound = [k for k in namespace if not k.startswith("__")]
        assert bound, "a block that binds nothing is a block that shows nothing"


def test_every_relative_link_resolves() -> None:
    """A link on a PyPI page that 404s is worse than no link."""
    for target in re.findall(r"\]\((?!https?://)([^)]+)\)", TEXT):
        assert (PACKAGE / target).exists(), target
