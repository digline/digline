"""The pre-tag checklist is the one CI runs.

`RELEASING.md` tells a human what to run before tagging, and `ci.yml` tells the
runner. Two lists of the same commands drift, and the way this one drifted was
silent and expensive: v0.2.0 was tagged after a check over `src packages tests`
while CI checked `.`, so a Python sample inside `docs/api.md` — which
`ruff format` reformats, and which no narrower path list ever sees — failed on
the tag itself.

So the page is derived from the workflow rather than kept beside it: this reads
the `gates` job and fails if `RELEASING.md` has fallen behind. A checklist
nobody can trust is worse than none, because it is followed.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CI = ROOT / ".github" / "workflows" / "ci.yml"
RELEASING = ROOT / "RELEASING.md"

#: What each step is parameterised by in the matrix and is not part of the
#: command a person types.
MATRIX = " --python ${{ matrix.python }}"


def gate_commands() -> list[str]:
    """Every `run:` in the `gates` job, as a person would type it.

    The job is read by indentation rather than with a YAML parser: this
    repository has one runtime dependency and a test is not where a second one
    arrives. The shape it depends on — two-space job keys, six-space steps — is
    the shape `ci.yml` already has, and a rewrite that broke it would fail here
    loudly rather than quietly stop checking.
    """
    text = CI.read_text(encoding="utf-8")
    body = text.split("\n  gates:", 1)[1]
    # Up to the next job at the same indentation.
    body = re.split(r"\n  \w[\w-]*:\n", body)[0]
    found = [
        line.split("run:", 1)[1].strip().replace(MATRIX, "")
        for line in body.splitlines()
        if line.strip().startswith("run: ")
    ]
    return found


def test_the_workflow_still_looks_like_a_list_of_commands() -> None:
    """A guard on the guard: if the parse ever stops finding steps, every
    assertion below would pass over an empty list and prove nothing."""
    commands = gate_commands()
    assert len(commands) >= 4, commands


def test_releasing_names_every_gate_ci_runs() -> None:
    """The checklist may say more than CI does — never less."""
    page = RELEASING.read_text(encoding="utf-8")
    for command in gate_commands():
        assert command in page, (
            f"ci.yml runs `{command}` and RELEASING.md does not list it: "
            "a pre-tag checklist that is missing a gate is a tag that fails "
            "on the gate"
        )


def test_the_gates_are_run_over_the_whole_repository() -> None:
    """The specific mistake, pinned.

    `ruff` over a list of source directories misses `docs/` and `examples/`,
    and `ruff format` formats the Python blocks inside a Markdown file — so a
    sample in the documentation is checked by `.` and by nothing else.
    """
    commands = gate_commands()
    assert "uv run ruff format --check ." in commands
    assert "uv run ruff check ." in commands


def docs_job_commands() -> list[str]:
    """Every `run:` in the `docs` job, read the same way as `gates`."""
    text = CI.read_text(encoding="utf-8")
    body = text.split("\n  docs:", 1)[1]
    body = re.split(r"\n  \w[\w-]*:\n", body)[0]
    return [
        line.split("run:", 1)[1].strip()
        for line in body.splitlines()
        if line.strip().startswith("run: ")
    ]


def test_ci_still_builds_the_site_before_any_tag() -> None:
    """The `docs` job is a gate, not a convenience, so it is pinned like one.

    Without it the first time anyone learns that an example README broke the
    site is the `site` job of `publish.yml` — which runs *after* PyPI, the one
    step that cannot be taken back. That is what v0.3.0 cost.
    """
    commands = docs_job_commands()
    assert any("sync-docs.sh" in c for c in commands), commands
    assert any("mkdocs build --strict" in c for c in commands), commands


def test_releasing_tells_a_human_to_build_the_site_too() -> None:
    """The same rule the gates block already lives under: the checklist may say
    more than CI does, never less.

    Not derived command-for-command like `gate_commands`, because the paths
    genuinely differ — CI checks the site out beside the workspace, a person has
    it as a sibling clone — so what is pinned is the two steps that are the
    gate, and the reason a reader needs for running them.
    """
    page = RELEASING.read_text(encoding="utf-8")
    assert "tools/sync-docs.sh" in page
    assert "uv run mkdocs build --strict" in page
    # The consequence, without which nobody runs an optional-looking step.
    assert "after* PyPI" in page or "after PyPI" in page
