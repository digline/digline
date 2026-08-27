"""The metrics cards, checked against the package they describe.

Three ways a card deck goes wrong, and one test each: a type gets added and
nobody writes its card; an example stops constructing; the metadata table
describes keys that no longer exist. The last one is why `showcase.py` is on the
page and is run here rather than transcribed.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from tests._docs import python_files, python_snippets, replay

ROOT = Path(__file__).resolve().parents[1]
METRICS = ROOT / "docs" / "metrics.md"
TEXT = METRICS.read_text(encoding="utf-8")


def exported() -> list[str]:
    """Every assertion and aggregate the package exports, minus the two bases.

    Derived from `__all__` rather than listed here: a hand-kept list has to be
    remembered, and the way forgetting it shows up is a *passing* test.
    """
    import digline.core as core

    bases = (core.AssertionBase, core.RunAssertionBase)
    return [
        name
        for name in core.__all__
        if isinstance(obj := getattr(core, name), type)
        and issubclass(obj, bases)
        and obj not in bases
    ]


def test_the_derivation_finds_what_it_should() -> None:
    """A guard on the guard: an empty list would make every check below vacuous."""
    assert len(exported()) >= 18, exported()


@pytest.mark.parametrize("name", exported())
def test_every_exported_metric_has_a_card(name: str) -> None:
    assert f"### `{name}`" in TEXT, f"{name} is exported and has no card"


@pytest.mark.parametrize("name", exported())
def test_every_card_says_when_to_use_it(name: str) -> None:
    """A card without "use it when" is a signature, and the signature is already
    in `api.md`. This deck exists to answer the other question."""
    card = TEXT.split(f"### `{name}`", 1)[1].split("\n### ", 1)[0]
    assert "**Use it when**" in card, name


def test_the_decision_tree_names_every_metric() -> None:
    tree = TEXT.split("```text\n", 1)[1].split("```", 1)[0]
    assert len(tree.splitlines()) <= 14, "the tree stopped being scannable"
    for name in exported():
        assert name in tree, f"{name} is on no branch of the tree"


def test_every_example_constructs(tmp_path: Path) -> None:
    """Each card's snippet is evaluated, not merely displayed.

    The namespace is the one the page promises the reader: the public API, plus
    the three things a card cannot supply — your judge, your claim judge, your
    autoevals scorer.

    The Targets cards read prompt files, so the snippets run against a directory
    that has them and a `__file__` that points into it. That is not a courtesy:
    it is what makes a renamed parameter fail here rather than in a suite.
    """
    import digline.core as core
    import digline.targets as targets
    from digline_anthropic import ANTHROPIC_PRICING, AnthropicTarget

    prompts = tmp_path / "prompts"
    prompts.mkdir()
    (prompts / "answer.md").write_text("Answer {question}.", encoding="utf-8")
    (prompts / "system.md").write_text("Be terse.", encoding="utf-8")

    namespace: dict[str, object] = {name: getattr(core, name) for name in core.__all__}
    namespace.update({name: getattr(targets, name) for name in targets.__all__})
    namespace["Path"] = Path
    namespace["__file__"] = str(tmp_path / "suite.py")
    namespace["AnthropicTarget"] = AnthropicTarget
    namespace["ANTHROPIC_PRICING"] = ANTHROPIC_PRICING

    def judge(prompt: str) -> core.JudgeReply:
        return core.JudgeReply(score=1.0, reason="stub")

    def claim_judge(prompt: str) -> core.ClaimReply:
        return core.ClaimReply(supported=1, total=1, reason="stub")

    def scorer(output: object, expected: object = None, **kwargs: object) -> None:
        return None

    namespace["judge"] = judge
    namespace["claim_judge"] = claim_judge
    namespace["scorer"] = scorer

    snippets = python_snippets(TEXT)
    assert len(snippets) >= 18, len(snippets)
    for snippet in snippets:
        exec(compile(snippet, "<card>", "exec"), dict(namespace))  # noqa: S102


def test_the_showcase_prints_what_the_page_says_it_prints(tmp_path: Path) -> None:
    """The metadata table, regenerated. If an assertion stops writing a key, or
    starts writing another, this is where the page finds out."""
    assert set(python_files(TEXT)) == {"showcase.py"}
    replay(TEXT, tmp_path)


def test_every_relative_link_resolves() -> None:
    for target in re.findall(r"\]\(([^)]+)\)", TEXT):
        if target.startswith(("http://", "https://", "#")):
            continue
        assert (METRICS.parent / target.split("#", 1)[0]).exists(), target
