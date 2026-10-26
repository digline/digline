"""`dist_manifest.py`: the roster the publish workflow verifies, and the
packages the install check leaves out because their own cap excludes this core
(#717).

The install check in `pypi` installs every package this tag built, pinned, from
the index. On a minor that raises the plugins' caps, a plugin PyPI already
serves still caps the core below this release, so the manifest cannot resolve
on any index. `plugins_against_core.py` classifies such a plugin as *excluded*
in `testpypi`; the install check is handed that classification and leaves the
plugin out, saying which and why. It leaves out only the **served** version the
classification read: a version this tag itself publishes is never left out,
because nothing has verified it yet.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / ".github" / "dist_manifest.py"

WHEELS = (
    "digline-0.34.0-py3-none-any.whl",
    "digline_anthropic-0.6.1-py3-none-any.whl",
    "digline_mcp-0.6.2-py3-none-any.whl",
    "pytest_digline-0.3.1-py3-none-any.whl",
)


def run(tmp_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    dist = tmp_path / "dist"
    dist.mkdir(exist_ok=True)
    for wheel in WHEELS:
        (dist / wheel).write_bytes(b"")
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(tmp_path / "manifest"), *args],
        cwd=tmp_path,
        env={**os.environ},
        capture_output=True,
        text=True,
        check=False,
    )


def read(tmp_path: Path, name: str) -> list[str]:
    return (tmp_path / "manifest" / name).read_text(encoding="utf-8").splitlines()


def test_without_exclusions_the_roster_is_dist_whole(tmp_path: Path) -> None:
    done = run(tmp_path)
    assert done.returncode == 0, done.stderr
    assert read(tmp_path, "pins.txt") == [
        "digline==0.34.0",
        "digline-anthropic==0.6.1",
        "digline-mcp==0.6.2",
        "pytest-digline==0.3.1",
    ]


def test_an_empty_exclusion_is_no_exclusion(tmp_path: Path) -> None:
    """What the step passes when `testpypi` classified nothing as excluded."""
    done = run(tmp_path, "--excluding")
    assert done.returncode == 0, done.stderr
    assert len(read(tmp_path, "pins.txt")) == 4


def test_a_classified_plugin_is_left_out_of_all_three_files_and_named(
    tmp_path: Path,
) -> None:
    done = run(tmp_path, "--excluding", "digline-mcp==0.6.2", "pytest-digline==0.3.1")
    assert done.returncode == 0, done.stderr
    assert read(tmp_path, "pins.txt") == [
        "digline==0.34.0",
        "digline-anthropic==0.6.1",
    ]
    assert read(tmp_path, "names.txt") == ["digline", "digline-anthropic"]
    assert read(tmp_path, "imports.txt") == ["digline", "digline_anthropic"]
    for name, version in (("digline-mcp", "0.6.2"), ("pytest-digline", "0.3.1")):
        assert f"left out {name} {version}" in done.stdout
    assert "excluded by its own cap" in done.stdout
    assert "plugins_against_core.py" in done.stdout


def test_a_version_this_tag_publishes_is_never_left_out(tmp_path: Path) -> None:
    """The classification read the newest version PyPI served before this tag;
    `dist/` holds a newer one, which this tag publishes and nothing has
    verified. It stays in the manifest, and the step says why."""
    done = run(tmp_path, "--excluding", "digline-mcp==0.6.1")
    assert done.returncode == 0, done.stderr
    assert "digline-mcp==0.6.2" in read(tmp_path, "pins.txt")
    assert "kept digline-mcp 0.6.2" in done.stdout
    assert "0.6.1" in done.stdout


@pytest.mark.parametrize(
    ("excluded", "said"),
    [
        ("digline==0.34.0", "the core"),
        ("digline-openai==0.5.2", "not in dist/"),
        ("digline-mcp", "name==version"),
    ],
)
def test_an_exclusion_that_cannot_be_right_is_refused(
    tmp_path: Path, excluded: str, said: str
) -> None:
    done = run(tmp_path, "--excluding", excluded)
    assert done.returncode == 1
    assert said in done.stderr
    assert not (tmp_path / "manifest" / "pins.txt").exists()
