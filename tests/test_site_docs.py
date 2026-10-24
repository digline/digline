"""The dispatch that tells digline.dev digline's documentation moved. (#521)

`.github/workflows/site-docs.yml` runs on a push to `main`, asks
`.github/site_reads.py` whether the push touched anything the site copies out
of this repository, and if it did posts a `digline-docs` dispatch to
digline.dev, whose `docs.yml` builds from the tip of `main` and deploys.

Pinned here:
- **what the site reads**, held to `tools/sync-docs.sh` in the site's own
  checkout where this machine has one, and skipped where it has none, like the
  other tests of the site;
- **what counts as touched**: each of the five paths, nothing else, and a push
  with no base to compare with counts as touched;
- **the workflow's shape**: a push to `main` and nothing else, never a queue
  entry, a concurrency that does not cancel, the token read on the step, and a
  step that cannot swallow its own failure.

**What no test here proves**: that digline.dev accepts the dispatch. That is
`tools/check-deploy.py` over there, and the first push after this lands is
its reading.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml
from tests._site import require_site_config

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / ".github" / "site_reads.py"
WORKFLOW = ROOT / ".github" / "workflows" / "site-docs.yml"

sys.path.insert(0, str(ROOT / ".github"))
from site_reads import SITE_READS, touched  # noqa: E402

# --- what the site reads --------------------------------------------------


def _copied_by_sync_docs(script: str) -> set[str]:
    """The paths `sync-docs.sh` copies out of the digline checkout, as it
    writes them: `"$src/<path>"` in a `cp`, and `"$src"/<glob>` in the loop."""
    quoted = {
        match.group(1)
        for line in script.splitlines()
        if line.lstrip().startswith("cp ")
        for match in re.finditer(r'"\$src/([^"]+)"', line)
    }
    looped = {
        match.group(1) for match in re.finditer(r'for \w+ in "\$src"/(\S+?);', script)
    }
    # `cp -R "$src/docs/."` copies the directory's content: the path is docs/.
    return {path[:-2] if path.endswith("/.") else path for path in quoted} | {
        path for path in looped
    }


def test_the_paths_are_the_ones_sync_docs_copies() -> None:
    """The list this repository dispatches on is the list the site copies.
    A path the site reads and this list misses is a change that does not reach
    the site, which is #521 again."""
    config = require_site_config()
    script = (config.parent / "tools" / "sync-docs.sh").read_text(encoding="utf-8")
    copied = _copied_by_sync_docs(script)
    assert copied, "nothing read out of sync-docs.sh: the reader is broken"
    assert {p.rstrip("/") for p in SITE_READS} == copied, (
        f"site_reads.py dispatches on {sorted(SITE_READS)} and the site's "
        f"sync-docs.sh copies {sorted(copied)}"
    )


def test_the_reader_of_sync_docs_reads_each_form() -> None:
    """The control for the test above, with no site needed: each of the two
    ways the script names a path is read."""
    script = (
        'cp -R "$src/docs/." "$out/"\n'
        'cp "$src/CHANGELOG.md" "$out/changelog.md"\n'
        'for readme in "$src"/examples/*/README.md; do\n'
    )
    assert _copied_by_sync_docs(script) == {
        "docs",
        "CHANGELOG.md",
        "examples/*/README.md",
    }


# --- what counts as touched -----------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "docs/api.md",
        "docs/adr/0053-promote-refuses-a-pin-nobody-named.md",
        "CHANGELOG.md",
        "ROADMAP.md",
        "docker/README.md",
        "examples/operator/README.md",
    ],
)
def test_a_path_the_site_reads_is_touched(path: str) -> None:
    assert touched([path]) == [path]


@pytest.mark.parametrize(
    "path",
    [
        "src/digline/core/compare.py",
        "README.md",
        "AGENTS.md",
        "CONTRIBUTING.md",
        "docker/Dockerfile",
        "examples/operator/dossier.py",
        "examples/operator/alerts/draw.md",
        "docsy/api.md",
        ".github/workflows/site-docs.yml",
    ],
)
def test_a_path_the_site_does_not_read_is_not(path: str) -> None:
    assert touched([path]) == []


def _run(*args: str, stdin: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        input=stdin,
        capture_output=True,
        text=True,
        check=False,
    )


def test_the_command_line_says_dispatch_for_a_touched_push() -> None:
    done = _run(stdin="src/digline/core/compare.py\ndocs/api.md\n")
    assert done.returncode == 0, done.stderr
    assert done.stdout.splitlines()[-1] == "dispatch=true"
    assert "docs/api.md" in done.stdout


def test_the_command_line_says_no_dispatch_when_nothing_the_site_reads_moved() -> None:
    done = _run(stdin="src/digline/core/compare.py\nREADME.md\n")
    assert done.returncode == 0, done.stderr
    assert done.stdout.splitlines()[-1] == "dispatch=false"


def test_the_command_line_says_dispatch_with_no_base() -> None:
    """No base to compare with — a branch's first push — is not a push that
    touched nothing: what moved is unknown, so the site is told."""
    done = _run("--no-base", stdin="")
    assert done.returncode == 0, done.stderr
    assert done.stdout.splitlines()[-1] == "dispatch=true"


# --- the workflow -----------------------------------------------------------


def _workflow() -> Any:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _job(name: str) -> dict[str, Any]:
    return _workflow()["jobs"][name]


def test_it_runs_on_a_push_to_main_and_on_nothing_else() -> None:
    """Not a queue entry: the site builds from `main`'s tip, and an entry is
    not on `main` yet. A queue merge reaches `main` as a push."""
    on = _workflow()[True]  # PyYAML reads the key `on` as True.
    assert on == {"push": {"branches": ["main"]}}


def test_a_newer_push_does_not_cancel_an_older_one() -> None:
    """`ci.yml` cancels: 6 of its last 100 push runs on `main` were. A
    cancelled dispatch is a change that never reaches the site."""
    concurrency = _workflow()["concurrency"]
    assert concurrency["cancel-in-progress"] is False


def test_the_diff_is_between_the_push_s_two_ends() -> None:
    (check,) = [s for s in _job("touched")["steps"] if s.get("id") == "check"]
    assert check["env"]["BEFORE"] == "${{ github.event.before }}"
    assert check["env"]["HEAD"] == "${{ github.sha }}"
    assert "git diff --name-only" in check["run"]
    assert "site_reads.py" in check["run"]


def test_the_dispatch_waits_for_the_answer() -> None:
    job = _job("dispatch")
    assert job["needs"] == "touched"
    assert job["if"] == "needs.touched.outputs.dispatch == 'true'"


def test_the_token_is_read_on_the_step_and_the_job_holds_nothing() -> None:
    """As the `site` job of `publish.yml` does: the job's token holds no
    permission, and the secret is in one step's environment only."""
    job = _job("dispatch")
    assert job["permissions"] == {}
    assert "env" not in job
    (step,) = job["steps"]
    assert step["env"] == {"GH_TOKEN": "${{ secrets.DIGLINE_DEV_DISPATCH_TOKEN }}"}
    assert "event_type=digline-docs" in step["run"]
    assert "repos/digline/digline.dev/dispatches" in step["run"]


def test_the_step_cannot_swallow_its_own_failure() -> None:
    """A dispatch that fails and goes green is the silence #521 is about. The
    step runs under the default shell, which stops at the first failure, and
    nothing in it turns a failure into a success."""
    (step,) = _job("dispatch")["steps"]
    run = step["run"]
    assert "shell" not in step
    assert "continue-on-error" not in step
    assert "continue-on-error" not in _job("dispatch")
    assert "|| true" not in run
    assert "|| :" not in run
    assert "set +e" not in run
    assert "exit 1" in run, "a missing token must fail, not skip"
