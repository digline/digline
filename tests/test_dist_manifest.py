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


def test_a_classification_that_found_nothing_keeps_the_roster_whole(
    tmp_path: Path,
) -> None:
    """What the step passes when `testpypi` classified and found nothing to
    exclude: the marker alone."""
    done = run(tmp_path, "--classification", "classified")
    assert done.returncode == 0, done.stderr
    assert len(read(tmp_path, "pins.txt")) == 4


@pytest.mark.parametrize(
    "given",
    [
        pytest.param(("--classification", ""), id="an empty output"),
        pytest.param(("--classification",), id="no value at all"),
        pytest.param(
            ("--classification", "digline-mcp==0.6.2"), id="words with no marker"
        ),
    ],
)
def test_a_classification_never_made_stops_the_install_check(
    tmp_path: Path, given: tuple[str, ...]
) -> None:
    """GitHub gives an empty string for an output no step wrote, so an empty
    value cannot mean *nothing to exclude*: it is also *never classified*, and
    read as the first it is a false green. Only a value that begins with the
    marker is a classification; anything else stops the check before a
    manifest is written. A missed exclusion fails an install; a missed
    classification read as none passes one. (#731)"""
    done = run(tmp_path, *given)
    assert done.returncode == 1
    assert "never classified" in done.stderr
    assert not (tmp_path / "manifest" / "pins.txt").exists()


def test_a_classified_plugin_is_left_out_of_all_three_files_and_named(
    tmp_path: Path,
) -> None:
    done = run(
        tmp_path,
        "--classification",
        "classified",
        "digline-mcp==0.6.2",
        "pytest-digline==0.3.1",
    )
    assert done.returncode == 0, done.stderr
    assert read(tmp_path, "pins.txt") == [
        "digline==0.34.0",
        "digline-anthropic==0.6.1",
    ]
    assert not (tmp_path / "manifest" / "names.txt").exists()
    assert read(tmp_path, "imports.txt") == ["digline", "digline_anthropic"]
    for name, version in (("digline-mcp", "0.6.2"), ("pytest-digline", "0.3.1")):
        assert f"left out {name} {version}" in done.stdout
    assert "excluded by its own cap" in done.stdout
    assert "plugins_against_core.py" in done.stdout


def test_a_version_this_tag_publishes_is_never_left_out(tmp_path: Path) -> None:
    """The classification read the newest version PyPI served before this tag;
    `dist/` holds a newer one, which this tag publishes and nothing has
    verified. It stays in the manifest, and the step says why."""
    done = run(tmp_path, "--classification", "classified digline-mcp==0.6.1")
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
    done = run(tmp_path, "--classification", f"classified {excluded}")
    assert done.returncode == 1
    assert said in done.stderr
    assert not (tmp_path / "manifest" / "pins.txt").exists()


def test_exclusions_in_one_argument_are_read_one_by_one(tmp_path: Path) -> None:
    """The job's output is one string; a shell that does not split an unquoted
    variable, as zsh does not, passes it as one argument. Measured on
    v0.34.0's dist, before this: both plugins were kept, read as one version
    with a space in it."""
    done = run(
        tmp_path,
        "--classification",
        "classified digline-mcp==0.6.2 pytest-digline==0.3.1",
    )
    assert done.returncode == 0, done.stderr
    assert read(tmp_path, "pins.txt") == [
        "digline==0.34.0",
        "digline-anthropic==0.6.1",
    ]
