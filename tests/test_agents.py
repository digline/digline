"""The playbook, in two places that must not drift apart.

`AGENTS.md` is read by an agent that finds it in the repository root; the skill
in `.claude/skills/operating-digline/` is read by one that loads it before
acting. Two copies of the same rules, and the drift between a repository file
and a skill is exactly the class of trap this repository gates elsewhere: the
one that is wrong stays plausible, because nothing reads them side by side.

So this does. The rule *list* is the contract — same rules, same order, same
words in the headings — while the prose around them is allowed to differ,
because the two are read in different situations and the introductions say so.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

AGENTS = ROOT / "AGENTS.md"
SKILL = ROOT / ".claude" / "skills" / "operating-digline" / "SKILL.md"

#: A rule is a numbered level-2 heading — `## 3. One bad run is a draw…`. The
#: numbering is the house style the guide's chapters already use, and it is what
#: makes "the same rules in the same order" a thing a test can read rather than
#: a thing a reviewer has to notice.
RULE_RE = re.compile(r"^## (\d+)\. (.+)$", re.MULTILINE)


def rules(path: Path) -> list[tuple[str, str]]:
    return RULE_RE.findall(path.read_text(encoding="utf-8"))


def test_both_files_exist_where_they_are_looked_for() -> None:
    """The location is half of each deliverable.

    An agent arriving in a repository reads `AGENTS.md` at the root, and Claude
    Code loads a skill from `.claude/skills/<name>/SKILL.md`. Either file is
    inert one directory away from where it is looked for, and inert is
    indistinguishable from absent.
    """
    assert AGENTS.is_file(), f"{AGENTS} is where an agent looks for the playbook"
    assert SKILL.is_file(), f"{SKILL} is where Claude Code loads the skill from"


def test_the_rule_pattern_still_finds_the_rules() -> None:
    """A guard on the guard: two empty lists compare equal and prove nothing."""
    found = rules(AGENTS)
    assert len(found) >= 8, found
    assert [number for number, _ in found] == [
        str(n) for n in range(1, len(found) + 1)
    ], "the rules are numbered from 1 with no gap"


def test_the_skill_and_agents_md_carry_the_same_rules() -> None:
    """Same headings, same order, in both files.

    A rule added to one and not the other is the failure this exists for: the
    agent that read the other copy behaves by a playbook that is quietly one
    rule short, and behaves *confidently*, because nothing told it there was a
    rule it never saw.
    """
    in_agents = rules(AGENTS)
    in_skill = rules(SKILL)
    assert in_agents == in_skill, (
        "the rule lists have drifted apart.\n"
        f"  {AGENTS.relative_to(ROOT)}: {[t for _, t in in_agents]}\n"
        f"  {SKILL.relative_to(ROOT)}: {[t for _, t in in_skill]}\n"
        "Both files carry the same rules, numbered the same way and in the same "
        "order. The prose around them may differ; the list may not."
    )


def test_the_skill_declares_its_frontmatter() -> None:
    """A skill with no `name` and no `description` is never loaded.

    The description is what decides whether the skill is reached for at all, so
    an empty one is a file that exists and never runs.
    """
    text = SKILL.read_text(encoding="utf-8")
    assert text.startswith("---\n"), "a SKILL.md opens with YAML frontmatter"
    front = text.split("---\n", 2)[1]
    assert re.search(r"^name: operating-digline$", front, re.MULTILINE), front
    description = re.search(r"^description: (.+)$", front, re.MULTILINE)
    assert description is not None and len(description.group(1)) > 40, front
