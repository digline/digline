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

import pytest

ROOT = Path(__file__).resolve().parents[1]
CI = ROOT / ".github" / "workflows" / "ci.yml"
RELEASING = ROOT / "RELEASING.md"
CONTRIBUTING = ROOT / "CONTRIBUTING.md"

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


@pytest.mark.parametrize("page", [RELEASING, CONTRIBUTING], ids=lambda p: p.name)
def test_every_copy_of_the_gates_names_every_gate_ci_runs(page: Path) -> None:
    """The checklist may say more than CI does — never less.

    `CONTRIBUTING.md` says it is a copy of the `gates` job, and until #446
    nothing held it to that: it had fallen two commands and the type-gate split
    behind, and its bare `pytest -m "not live"` was the command that, with `-n`
    added, let `test_type_gate.py` race the tests that read `src/`."""
    text = page.read_text(encoding="utf-8")
    for command in gate_commands():
        assert command in text, (
            f"ci.yml runs `{command}` and {page.name} does not list it: "
            "a copy of the gates that is missing one is a red that arrives "
            "after the push"
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
    # A pull request is its merge commit, ahead of origin/main, which the site's
    # sync refuses: there the job builds through the site's own preview target,
    # which is still `mkdocs build --strict` with only omitted pages loosened.
    assert any(c.startswith("make preview") for c in commands), commands


def test_releasing_tells_a_human_to_build_the_site_too() -> None:
    """The same rule the gates block already lives under: the checklist may say
    more than CI does, never less.

    Not derived command-for-command like `gate_commands`, because the paths
    genuinely differ — CI checks the site out beside the workspace, a person has
    it as a sibling clone — so what is pinned is the target that *is* the gate,
    and the reason a reader needs for running it.

    It pinned `tools/sync-docs.sh` and `uv run mkdocs build --strict` until
    0.13.2, which is one release too long. That pair is not the gate: the sync
    refuses a checkout ahead of `origin/main`, which a release branch always is,
    and the build after it renders whatever `docs/product/` already held and
    reports success. Pinning it here is what kept the checklist advertising a
    check that can pass having looked at nothing, so the page may still name the
    pair — it explains what not to do — and what is *held* is `make preview`,
    the target the `docs` job calls, which
    `test_ci_still_builds_the_site_before_any_tag` pins to that job from the
    other side.
    """
    page = RELEASING.read_text(encoding="utf-8")
    assert "make preview" in page
    # The consequence, without which nobody runs an optional-looking step.
    assert "after* PyPI" in page or "after PyPI" in page


def job_body(name: str) -> str:
    """One job of `ci.yml`, up to the next, read as `gate_commands` reads."""
    text = CI.read_text(encoding="utf-8")
    assert f"\n  {name}:\n" in text, f"ci.yml has no `{name}` job"
    body = text.split(f"\n  {name}:\n", 1)[1]
    return re.split(r"\n  \w[\w-]*:\n", body)[0]


def test_the_glyph_check_is_a_job_of_its_own() -> None:
    """Pinned for the reason it exists: where it runs is the whole fix.

    Twice on 2026-09-29 an ADR carried a character the site's font subsets do
    not hold, and the site refused it only after the merge. The site's check
    was never run here, and where it would naturally have gone — a step of
    `docs` — is the one job that is red by design on every pull request adding
    an ADR. A refusal there looks exactly like the expected red. So the check
    lives in `glyphs`, and never in `docs`.
    """
    glyphs = job_body("glyphs")
    assert "tools/check-glyphs.py site" in glyphs
    assert "tools/check-glyphs.py --selftest" in glyphs
    assert "check-glyphs" not in job_body("docs"), (
        "the glyph check is in the `docs` job, which is red by design on every "
        "pull request that adds an ADR: a refusal there cannot be told apart "
        "from the expected red"
    )


def test_the_glyph_job_builds_the_preview_on_every_event() -> None:
    """Only the preview lets a page with no nav line through, and `main`
    carries one between an ADR and its site entry. A strict build here would
    bring `docs`' expected red into this job, which is what it is apart from.
    """
    glyphs = job_body("glyphs")
    assert "run: make preview DIGLINE=.." in glyphs
    assert "if: github.event_name" not in glyphs


def test_the_glyph_check_cannot_pass_on_a_build_without_our_pages() -> None:
    """The check reads the build, not this repository. A build that carried
    none of these pages would be green having looked at nothing, so the job
    proves the pages are there before it checks them."""
    glyphs = job_body("glyphs")
    assert "for f in docs/*.md docs/adr/*.md" in glyphs
    steps = [line.strip() for line in glyphs.splitlines() if "- name:" in line]
    names = [step.split("- name:", 1)[1].strip() for step in steps]
    control = names.index("The build holds every page of this checkout")
    assert control < names.index("Every character in the site's fonts"), names


def test_releasing_runs_the_glyph_check_too() -> None:
    """The checklist may say more than CI does, never less."""
    assert "uv run tools/check-glyphs.py site" in RELEASING.read_text(encoding="utf-8")


def site_reading_tests() -> dict[str, str]:
    """`{test name: file}` for every test that reads the site config.

    Derived by reading the test tree, so the list cannot go stale the way a
    written one does — which is the failure this whole pair exists for.
    """
    found: dict[str, str] = {}
    for path in sorted((ROOT / "tests").glob("test_*.py")):
        current = ""
        for line in path.read_text(encoding="utf-8").splitlines():
            # Reset on *any* top-level definition, not only on the next test: a
            # helper written below a test would otherwise inherit its name, and
            # this very file — whose helper names the call site in a string —
            # was the first thing it misread.
            if line.startswith(("def ", "class ")):
                current = line[4:].split("(")[0] if line.startswith("def test_") else ""
            elif "require_site_config()" in line and current:
                found[current] = path.name
    return found


def test_ci_runs_every_test_that_reads_the_site_config() -> None:
    """A nav gate that CI does not run is a gate that only ever skips.

    The three these cover sat at the bottom of a green run as part of
    `10 skipped`, which is a silence rather than an absence: nothing anywhere
    had checked that a page carries its `nav` line. The `docs` job runs them by
    node id now, with `DIGLINE_SITE_REQUIRED` set so they may not decline — and
    this holds that list to the tree, because the next one written would
    otherwise be skipped everywhere and nobody would learn it from a number.
    """
    workflow = CI.read_text(encoding="utf-8")
    missing = [
        f"{file}::{name}"
        for name, file in site_reading_tests().items()
        if f"{file}::{name}" not in workflow
    ]
    assert not missing, (
        "these tests read digline.dev's config and the `docs` job does not run "
        "them, so they skip everywhere and their check is performed by "
        "nothing:\n  " + "\n  ".join(missing)
    )


def test_the_nav_gates_are_forbidden_to_skip_where_ci_runs_them() -> None:
    """The variable is the whole mechanism, so it is pinned with the step.

    Without `DIGLINE_SITE_REQUIRED`, a `docs` job whose site checkout silently
    produced no `mkdocs.yml` would run the three, skip all three, and report
    success — the same silence, one layer further in.
    """
    workflow = CI.read_text(encoding="utf-8")
    assert "DIGLINE_SITE_REQUIRED" in workflow
    assert "And the control that must fail" in workflow, (
        "the negative half is part of the gate: a check that cannot fail has "
        "verified nothing, and this one's value is that it refuses to skip"
    )


FOLLOWUP = ROOT / ".github" / "workflows" / "release-followup.yml"


def test_no_workflow_step_pipes_a_verdict_into_tee_without_pipefail() -> None:
    """A pipeline's exit status is its **last** command's, and `tee` succeeds.

    Measured, not imagined: the first run of `release-followup.yml` found three
    steps of the runbook undone, opened the issue that said so, and reported
    success — the script's `exit 1` was swallowed by `| tee -a
    "$GITHUB_STEP_SUMMARY"`. The issue was right and the run was green, which is
    the pair this whole workflow exists to make impossible.

    Written over every workflow rather than over the one that had it, because
    the mistake is the shell's and not this file's: GitHub runs `run:` with
    `bash -e`, which does not set `pipefail`.
    """
    offenders: list[str] = []
    for path in sorted((ROOT / ".github" / "workflows").glob("*.yml")):
        for block in path.read_text(encoding="utf-8").split("- name: "):
            if "| tee" in block and "set -o pipefail" not in block:
                offenders.append(f"{path.name}: {block.splitlines()[0]}")
    assert not offenders, (
        "these steps pipe into `tee`, so their exit status is tee's and a "
        "failure inside them is silently green. Add `set -o pipefail`:\n  "
        + "\n  ".join(offenders)
    )
