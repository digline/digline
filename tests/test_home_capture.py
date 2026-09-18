"""The capture behind the home of digline.dev.

`tools/home_capture.py` runs digline and writes what the home shows. These pin
the two things it promises: that the regression it captures is one the CLI
really reported, and that `--check` refuses a file captured by another version.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
from email.message import Message
from pathlib import Path
from typing import Any

import pytest
from packaging.requirements import Requirement

import home_capture


def _changelog(tmp_path: Path, *headings: str) -> Path:
    path = tmp_path / "CHANGELOG.md"
    path.write_text("# Changelog\n\n" + "\n\n".join(headings) + "\n")
    return path


#: A steady scenario as the capture writes one, with the four things the
#: sentence on digline.dev/start/ says: green, a check inside the noise, a case
#: set aside, a file under test changed under rules that did not.
def _steady(**overrides: Any) -> dict[str, Any]:
    facts: dict[str, Any] = {
        "counts": {"regressed": 0, "unchanged": 9},
        "deltas": [{"assertion": "cost_budget", "within_noise": True}],
        "suspended": 1,
        "artifacts_changed": True,
        "config_changed": False,
        "sentence": "Nothing got worse compared with the reference.",
    }
    facts.update(overrides)
    return {
        "commands": [{"cmd": "digline compare --suite support.py", "exit": 0}],
        "compare_json": facts,
    }


def _capture_file(
    tmp_path: Path, version: str, steady: dict[str, Any] | None = None
) -> Path:
    path = tmp_path / "home.json"
    path.write_text(
        json.dumps(
            {
                "digline_version": version,
                "scenarios": {"steady": _steady() if steady is None else steady},
            }
        )
    )
    return path


def test_check_passes_when_the_capture_matches_the_newest_release(
    tmp_path: Path,
) -> None:
    problems = home_capture.check(
        _capture_file(tmp_path, "1.2.3"), _changelog(tmp_path, "## 1.2.3 — 2026-01-01")
    )
    assert problems == []


def test_check_fails_when_the_steady_scenario_is_missing(tmp_path: Path) -> None:
    """The one /start/ reads. A capture without it is a page without a source."""
    path = tmp_path / "home.json"
    path.write_text(json.dumps({"digline_version": "1.2.3", "scenarios": {}}))
    problems = home_capture.check(path, _changelog(tmp_path, "## 1.2.3 — 2026-01-01"))
    assert len(problems) == 1
    assert "no `steady` scenario" in problems[0]


@pytest.mark.parametrize(
    ("overrides", "needle"),
    [
        ({"counts": {"regressed": 1}}, "green comparison"),
        ({"deltas": [{"assertion": "cost_budget", "within_noise": False}]}, "noise"),
        ({"suspended": 0}, "suspended case"),
        ({"artifacts_changed": False}, "changed file under test"),
        ({"config_changed": True}, "unchanged suite"),
    ],
)
def test_check_fails_when_the_steady_scenario_lost_what_it_shows(
    tmp_path: Path, overrides: dict[str, Any], needle: str
) -> None:
    """Each of the four claims /start/ makes, taken away one at a time."""
    problems = home_capture.check(
        _capture_file(tmp_path, "1.2.3", _steady(**overrides)),
        _changelog(tmp_path, "## 1.2.3 — 2026-01-01"),
    )
    assert len(problems) == 1, problems
    assert needle in problems[0]


def test_check_fails_when_a_steady_command_did_not_exit_zero(tmp_path: Path) -> None:
    scenario = _steady()
    scenario["commands"] = [{"cmd": "digline compare --suite support.py", "exit": 1}]
    problems = home_capture.check(
        _capture_file(tmp_path, "1.2.3", scenario),
        _changelog(tmp_path, "## 1.2.3 — 2026-01-01"),
    )
    assert len(problems) == 1
    assert "exited 1, not 0" in problems[0]


def test_check_fails_when_a_newer_release_is_dated(tmp_path: Path) -> None:
    problems = home_capture.check(
        _capture_file(tmp_path, "1.2.3"),
        _changelog(tmp_path, "## 1.3.0 — 2026-02-01", "## 1.2.3 — 2026-01-01"),
    )
    assert len(problems) == 1
    assert "1.2.3" in problems[0] and "1.3.0" in problems[0]


def test_an_untagged_version_is_not_a_release_to_capture(tmp_path: Path) -> None:
    """The home is a public claim about what is released: a version set ahead
    of its tag, with an undated heading, holds the capture to the last release —
    the same reading digline.dev's hook makes, so the two cannot disagree."""
    changelog = _changelog(
        tmp_path,
        "## Unreleased",
        "## 1.3.0 — unreleased",
        "## digline-openai 9.9.9 — 2026-03-01",
        "## 1.2.3 — 2026-01-01",
    )
    assert home_capture.check(_capture_file(tmp_path, "1.2.3"), changelog) == []
    assert home_capture.check(_capture_file(tmp_path, "1.3.0"), changelog)


def test_check_fails_when_nothing_is_dated(tmp_path: Path) -> None:
    problems = home_capture.check(
        _capture_file(tmp_path, "1.2.3"), _changelog(tmp_path, "## 1.2.3 - 2026-01-01")
    )
    assert len(problems) == 1 and "no heading" in problems[0]


def test_check_fails_when_there_is_no_capture(tmp_path: Path) -> None:
    problems = home_capture.check(
        tmp_path / "home.json", _changelog(tmp_path, "## 1.2.3 — 2026-01-01")
    )
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


# ── the lists the home shows ──────────────────────────────────────────────────


def test_the_commands_are_the_parser_s_in_its_order() -> None:
    from digline.cli import build_parser

    found = home_capture.cli_commands()
    names = [item["name"] for item in found["items"]]
    assert names, "the capture found no command, so the home would show none"
    assert names[0] == "run" and {"compare", "promote", "report"} <= set(names)
    assert all(item["help"].strip() for item in found["items"])
    assert found["items"] == home_capture.cli_commands(build_parser())["items"]
    assert "build_parser" in found["source"]


def test_the_commands_refuse_an_argparse_without_the_private_list() -> None:
    """The one private attribute the capture leans on, taken away."""
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers()
    subparsers.add_parser("one", help="the only one")
    assert home_capture.cli_commands(parser)["items"] == [
        {"name": "one", "help": "the only one"}
    ]
    del subparsers._choices_actions  # pyright: ignore[reportPrivateUsage]
    with pytest.raises(home_capture.CaptureError, match="_choices_actions"):
        home_capture.cli_commands(parser)


def test_the_commands_refuse_a_parser_with_none() -> None:
    parser = argparse.ArgumentParser()
    parser.add_subparsers()
    with pytest.raises(home_capture.CaptureError):
        home_capture.cli_commands(parser)


def test_the_commands_leave_out_one_declared_without_help() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers()
    subparsers.add_parser("public", help="shown")
    subparsers.add_parser("hidden")
    names = [i["name"] for i in home_capture.cli_commands(parser)["items"]]
    assert names == ["public"]


def test_every_exported_check_is_listed_with_a_kind_and_an_anchor() -> None:
    found = home_capture.checks()
    listed = {item["name"]: item for item in found["items"]}
    assert set(listed) == {cls.__name__ for cls in home_capture.exported_checks()}
    assert len(listed) >= 22
    assert listed["LlmRubric"] == {
        "name": "LlmRubric",
        "kind": "judged",
        "anchor": "llmrubric",
    }
    assert listed["CostBudget"]["kind"] == "budget"
    assert listed["F1"]["kind"] == "aggregate"
    assert listed["Repeated"]["kind"] == listed["FromAutoevals"]["kind"] == "wrapper"
    assert listed["Contains"]["kind"] == "deterministic"
    assert "KIND" in found["source"] and "docs/metrics.md" in found["source"]


def _card(name: str) -> str:
    return f"# The metrics\n\n## Per case\n\n### `{name}`\n\nText.\n"


def test_the_checks_refuse_a_class_without_a_kind() -> None:
    class Undeclared:
        pass

    with pytest.raises(home_capture.CaptureError, match="declares no KIND"):
        home_capture.checks(_card("Undeclared"), [Undeclared])


def test_the_checks_refuse_a_kind_outside_the_five() -> None:
    class Invented:
        KIND = "heuristic"

    with pytest.raises(home_capture.CaptureError, match="not one of"):
        home_capture.checks(_card("Invented"), [Invented])


def test_the_checks_refuse_a_check_without_a_card() -> None:
    class Uncarded:
        KIND = "deterministic"

    with pytest.raises(home_capture.CaptureError, match="no card"):
        home_capture.checks(_card("SomethingElse"), [Uncarded])


def test_the_checks_refuse_an_anchor_two_headings_share() -> None:
    class Twice:
        KIND = "deterministic"

    with pytest.raises(home_capture.CaptureError, match="more than one heading"):
        home_capture.checks(_card("Twice") + "\n## Twice\n", [Twice])


def test_a_hash_line_inside_a_fence_is_not_a_heading() -> None:
    class Fenced:
        KIND = "deterministic"

    text = _card("Fenced") + "\n```python\n# Fenced\n```\n"
    assert home_capture.checks(text, [Fenced])["items"][0]["anchor"] == "fenced"


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("`Equals`", "equals"),
        ("`F1`", "f1"),
        ("What each one puts in the verdict", "what-each-one-puts-in-the-verdict"),
        ("What is left out of a denominator", "what-is-left-out-of-a-denominator"),
    ],
)
def test_heading_ids_are_the_ones_the_site_builds(title: str, expected: str) -> None:
    """Read off the built digline.dev page for `docs/metrics.md`, 2026-09-16."""
    assert home_capture.heading_id(title) == expected
