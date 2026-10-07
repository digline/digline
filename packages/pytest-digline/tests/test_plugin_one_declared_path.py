"""ADR 0045 through pytest-digline: test plan entry 9, by its flag and its ini.

A real pytest run in a subprocess, started from the working directory under
test: `pytester` would start it from its own directory, and the directory is
what decides which prompt a bare relative path reads. The layout is #481's,
from `tests/_one_path.py`.

The run is not promoted, so a run that gets past the files under test ends on
"no baseline" (exit 4) after its run file is written. What these tests read is
that file and what the provider was sent, not the gate's verdict.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from tests._one_path import RELATIVE, layout, recorded, sent, sha


def _pytest(tmp_path: Path, cwd: str, how: str) -> subprocess.CompletedProcess[str]:
    """`--digline-suite eval/suite.py` from `R`, or the absolute suite from
    elsewhere; or the `digline_suites` ini, which pytest makes absolute."""
    root = tmp_path / "R"
    args = [
        sys.executable,
        "-m",
        "pytest",
        "-p",
        "no:cacheprovider",
        "--digline-run",
        "--digline-root",
        str(root),
        "--rootdir",
        str(root),
    ]
    if how == "ini":
        (root / "pytest.ini").write_text(
            "[pytest]\ndigline_suites =\n    eval/suite.py\n", "utf-8"
        )
        args += ["-c", str(root / "pytest.ini")]
    else:
        spec = "eval/suite.py" if cwd == "R" else str(root / "eval" / "suite.py")
        args += ["-c", os.devnull, "--digline-suite", spec]
    return subprocess.run(
        args, cwd=tmp_path / cwd, capture_output=True, text=True, check=False
    )


def _runs(root: Path) -> list[Path]:
    return list((root / ".digline").rglob("runs/*/*.json"))


@pytest.mark.parametrize("how", ["flag", "ini"])
def test_1_from_the_root_the_run_records_the_file_it_sent(
    tmp_path: Path, how: str
) -> None:
    root = layout(tmp_path)
    done = _pytest(tmp_path, "R", how)
    assert "no baseline" in done.stdout + done.stderr, done.stdout + done.stderr
    assert sent(tmp_path) == ["text of R\n"]
    (run,) = _runs(root)
    assert recorded(root, run.stem) == {
        "prompt.txt": {"sha": sha(root / "prompt.txt"), "text": "text of R\n"}
    }


@pytest.mark.parametrize("how", ["flag", "ini"])
def test_2_from_outside_the_run_is_refused_and_nothing_is_sent(
    tmp_path: Path, how: str
) -> None:
    root = layout(tmp_path)
    done = _pytest(tmp_path, "OUT", how)
    out = done.stdout + done.stderr
    assert "the target Stub of suite 'qa'" in out, out
    assert "(ADR 0042 §2)" in out
    assert sent(tmp_path) == []
    assert not _runs(root)


@pytest.mark.parametrize("how", ["flag", "ini"])
def test_4_a_relative_answer_is_refused_naming_the_target(
    tmp_path: Path, how: str
) -> None:
    root = layout(tmp_path, target=RELATIVE)
    done = _pytest(tmp_path, "R", how)
    out = done.stdout + done.stderr
    assert "the target Naming of suite 'qa'" in out, out
    assert "a relative path" in out
    assert not _runs(root)
