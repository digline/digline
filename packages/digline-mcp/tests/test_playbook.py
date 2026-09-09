"""The descriptions carry AGENTS.md, and this is what keeps them in step.

A tool description reaches the model deciding whether to call the tool, which
makes it the one place the operating rules reach an agent that never read them.
The sibling of `tests/test_agents.py`, which does this for the shipped skill:
between them, a rule reworded in one place cannot stay stale in the other two.
(ADR 0011 §9, §13)
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from digline_mcp.descriptions import DESCRIPTIONS

AGENTS = Path(__file__).resolve().parents[3] / "AGENTS.md"


def flat(text: str) -> str:
    """Whitespace collapsed to single spaces, lowercased.

    Both sides need it: `AGENTS.md` is hard-wrapped at 76 columns, so a phrase
    long enough to be specific is a phrase that spans a newline, and a literal
    `in` would fail on the wrap rather than on the meaning.
    """
    return re.sub(r"\s+", " ", text).lower()


#: The rule each tool's description has to carry, as a phrase that appears in
#: `AGENTS.md` itself. Not the whole sentence — a description rewords for its
#: own context — but a phrase specific enough that it cannot survive the rule
#: being rewritten.
CARRIES: dict[str, tuple[str, ...]] = {
    "list_runs": ("never from the first one that goes green",),
    "get_run": ("Do not retry it", "flipping together"),
    "compare": (
        "stop and report what got worse",
        "arguing with the instrument",
        "measures your patience rather than the system",
    ),
    "run": (
        "say the figure out loud in your recommendation",
        "Decide the number of re-runs before running them",
    ),
}


def test_agents_md_is_where_this_thinks_it_is() -> None:
    """A guard on the guard: a moved file would make every check below pass over
    an empty string."""
    assert AGENTS.is_file(), AGENTS
    assert "## 1. The prime rule" in AGENTS.read_text(encoding="utf-8")


@pytest.mark.parametrize("tool", sorted(CARRIES))
def test_each_description_carries_its_rule(tool: str) -> None:
    text = flat(DESCRIPTIONS[tool])
    for phrase in CARRIES[tool]:
        assert flat(phrase) in text, (
            f"the {tool!r} description no longer carries {phrase!r}. It is the "
            "rule that governs this tool's misuse, and a description is the "
            "only place an agent that never read AGENTS.md will meet it."
        )


@pytest.mark.parametrize("tool", sorted(CARRIES))
def test_the_rule_is_still_in_agents_md(tool: str) -> None:
    """The other direction, and the half that catches drift.

    If a rule is reworded in `AGENTS.md` and not here, the description is
    quoting a rule the project no longer states — which is worse than not
    quoting one, because it reads as current.
    """
    agents = flat(AGENTS.read_text(encoding="utf-8"))
    for phrase in CARRIES[tool]:
        assert flat(phrase) in agents, (
            f"AGENTS.md no longer says {phrase!r}, which the {tool!r} tool "
            "description quotes. Update both, or the tool teaches a rule the "
            "project has stopped making."
        )


def test_every_tool_has_a_description() -> None:
    assert set(DESCRIPTIONS) == {
        "list_runs",
        "get_run",
        "get_baseline",
        "compare",
        "diff",
        "run",
    }
    for name, text in DESCRIPTIONS.items():
        assert len(text) > 200, f"{name} has no room for a rule in it"


def test_no_description_tells_an_agent_it_may_promote() -> None:
    """`promote` appears on this surface in exactly one register: as something a
    person runs."""
    for name, text in DESCRIPTIONS.items():
        lowered = text.lower()
        if "promote" in lowered:
            assert "the human runs" in lowered or "recommend" in lowered, name
