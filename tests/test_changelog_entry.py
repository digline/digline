"""The GitHub Release notes, cut out of CHANGELOG.md the way publish.yml cuts them."""

from __future__ import annotations

import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / ".github" / "changelog_entry.py"

CHANGELOG = """\
# Changelog

## Unreleased

## 0.13.30 — 2026-12-01

Not this one.

## 0.13.3 — 2026-09-16

**The headline.**

- a point

## 0.13.2 — 2026-09-16

Older.
"""


def run(*args: str, cwd: Path = ROOT) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def test_the_entry_is_the_body_between_its_heading_and_the_next(
    tmp_path: Path,
) -> None:
    path = tmp_path / "CHANGELOG.md"
    path.write_text(CHANGELOG, encoding="utf-8")
    done = run("0.13.3", str(path))
    assert done.returncode == 0, done.stderr
    assert done.stdout == "**The headline.**\n\n- a point\n"


def test_a_version_with_no_entry_is_refused_by_name(tmp_path: Path) -> None:
    path = tmp_path / "CHANGELOG.md"
    path.write_text(CHANGELOG, encoding="utf-8")
    done = run("0.13.4", str(path))
    assert done.returncode == 1
    assert done.stdout == ""
    assert "0.13.4" in done.stderr


def test_an_empty_entry_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "CHANGELOG.md"
    path.write_text("## 0.1.0 — 2026-01-01\n\n\n## 0.0.9 — x\n", encoding="utf-8")
    done = run("0.1.0", str(path))
    assert done.returncode == 1
    assert "empty" in done.stderr


def test_the_current_version_has_an_entry_in_the_real_changelog() -> None:
    """What the job will ask for on the next tag. Before the bump this is the
    version already released, whose entry must still be there."""
    with (ROOT / "pyproject.toml").open("rb") as handle:
        version = tomllib.load(handle)["project"]["version"]
    done = run(version)
    assert done.returncode == 0, done.stderr
    assert f"digline **{version}**" in done.stdout


def test_publish_runs_it_after_pypi_on_workspace_tags_only() -> None:
    workflow = (ROOT / ".github" / "workflows" / "publish.yml").read_text()
    job = workflow.split("\n  github-release:\n", 1)[1].split("\n  site:\n", 1)[0]
    assert "needs: pypi" in job
    assert "if: startsWith(github.ref_name, 'v')" in job
    assert "contents: write" in job
    assert ".github/changelog_entry.py" in job
