"""The capture behind the home of digline.dev.

`tools/home_capture.py` runs digline and writes what the home shows. These pin
the two things it promises: that the regression it captures is one the CLI
really reported, and that `--check` refuses a file captured by another version.
"""

from __future__ import annotations

import importlib.metadata
import json
from email.message import Message
from pathlib import Path
from typing import Any

import pytest
from packaging.requirements import Requirement

import home_capture


def _pyproject(tmp_path: Path, version: str) -> Path:
    path = tmp_path / "pyproject.toml"
    path.write_text(f'[project]\nname = "digline"\nversion = "{version}"\n')
    return path


def _capture_file(tmp_path: Path, version: str) -> Path:
    path = tmp_path / "home.json"
    path.write_text(json.dumps({"digline_version": version}))
    return path


def test_check_passes_when_the_capture_matches_the_package(tmp_path: Path) -> None:
    problems = home_capture.check(
        _capture_file(tmp_path, "1.2.3"), _pyproject(tmp_path, "1.2.3")
    )
    assert problems == []


def test_check_fails_when_the_package_moved(tmp_path: Path) -> None:
    problems = home_capture.check(
        _capture_file(tmp_path, "1.2.3"), _pyproject(tmp_path, "1.3.0")
    )
    assert len(problems) == 1
    assert "1.2.3" in problems[0] and "1.3.0" in problems[0]


def test_check_fails_when_there_is_no_capture(tmp_path: Path) -> None:
    problems = home_capture.check(tmp_path / "home.json", _pyproject(tmp_path, "1.2.3"))
    assert len(problems) == 1


def test_the_check_mode_exits_non_zero(tmp_path: Path) -> None:
    assert home_capture.main(["--check", "--out", str(tmp_path / "none")]) == 1


def _verdict(**fields: Any) -> dict[str, Any]:
    return {"metadata": {}, **fields}


def test_band_is_absent_when_nothing_was_sampled() -> None:
    document = {"results": [{"verdicts": [_verdict(score=1.0)]}]}
    assert home_capture.band([document]) == "absent: samples=1"


def test_band_says_zero_width_when_every_sample_agreed() -> None:
    verdict = _verdict(sample_min=1.0, sample_max=1.0, metadata={"samples": 3})
    document = {"results": [{"verdicts": [verdict]}]}
    assert home_capture.band([document]).startswith("zero-width: samples=3")


def test_runtime_dependencies_leave_out_extras_and_inactive_markers() -> None:
    found = home_capture.runtime_dependencies(
        [
            "typing-extensions>=4",
            'rich>=13; extra == "pretty"',
            'tomli>=2; python_version < "3.0"',
            'colorama; sys_platform != "no-such-platform"',
        ]
    )
    assert found["names"] == ["colorama", "typing-extensions"]
    assert found["count"] == 2


def test_runtime_dependencies_read_the_installed_digline() -> None:
    found = home_capture.runtime_dependencies()
    declared = [
        Requirement(line) for line in importlib.metadata.requires("digline") or ()
    ]
    unconditional = {r.name for r in declared if r.marker is None}
    assert unconditional <= set(found["names"])
    assert found["count"] == len(found["names"])
    assert "importlib.metadata" in found["source"]


def test_requires_python_reads_the_installed_digline() -> None:
    declared = importlib.metadata.metadata("digline")["Requires-Python"]
    found = home_capture.requires_python()
    assert found["specifier"] == declared
    assert "importlib.metadata" in found["source"]


def test_requires_python_refuses_a_distribution_that_declares_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A distribution whose metadata carries no such header: `Message` is the
    # shape importlib.metadata hands back, and it answers None for a key it
    # does not hold.
    def without_the_header(_name: str) -> Message:
        return Message()

    monkeypatch.setattr(home_capture, "metadata", without_the_header)
    with pytest.raises(home_capture.CaptureError):
        home_capture.requires_python()


def test_a_guide_that_moved_stops_the_derivation() -> None:
    files = {"app.py": "", "rules.py": "", "support.py": ""}
    with pytest.raises(home_capture.CaptureError):
        home_capture.prompt_fixture(files)


def test_the_capture_is_what_the_cli_printed(tmp_path: Path) -> None:
    result = home_capture.capture(tmp_path)

    quick = result["scenarios"]["quickstart"]
    assert [c["exit"] for c in quick["commands"]] == [0, 0, 0]
    assert quick["band"] == "absent: samples=1"

    regression = result["scenarios"]["prompt_regression"]
    compared = regression["commands"][-2]
    assert compared["cmd"] == "digline compare --suite support.py --run latest"
    assert compared["exit"] == 1
    assert "prompt.md · +1 −1 lines" in compared["stdout"]
    as_json = regression["commands"][-1]
    assert as_json["cmd"].endswith("--json full")
    assert set(as_json) == {"cmd", "stderr", "exit"}
    assert as_json["cmd"] in regression["compare_json"]["source"]
    assert regression["compare_json"]["exit_code"] == as_json["exit"] == 1
    assert regression["compare_json"]["artifacts_changed"] is True
    assert regression["band"] == "absent: samples=1"
    (changed,) = regression["change"]["files"]
    assert f"-{home_capture.SIGNATURE_LINE}" in changed["diff"]
    assert f"+{home_capture.CHANGED_LINE}" in changed["diff"]
    assert len(regression["run_ids"]) == 2

    dependencies = result["runtime_dependencies"]
    assert dependencies["count"] == len(dependencies["names"])
    assert result["requires_python"]["specifier"]
