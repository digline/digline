"""The push to `main` does not run again what the merge queue just ran.

`.github/queue_tested.py` answers whether a `merge_group` run of `ci` on the
pushed SHA ran every repeated job green, and `ci.yml` skips those jobs on the
push when it did. Driven here on listings shaped like the API's, cut down to
the fields that are read; the run and job ids are those of #769's queue run
(40554731971) on 9b3cde9d, read on 2026-10-28.

**What no test here proves**: that GitHub moves `main` to the commit the queue
tested. That was measured on the 30 pull requests merged up to #769, 30 in
30, and the first push after this lands is its next reading.
"""

from __future__ import annotations

import sys
import urllib.error
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
CI = ROOT / ".github" / "workflows" / "ci.yml"

sys.path.insert(0, str(ROOT / ".github"))
import queue_tested  # noqa: E402
from queue_tested import IMAGE, PYTHONS, REPEATED, WORKFLOW, verdict  # noqa: E402

SHA = "9b3cde9d6072641bb127e2bbc31e2c443f1874f6"
RUN = 40554731971
SKIPPABLE = ("gates", "readers", "glyphs", "image-touched")


def _run(
    sha: str = SHA, event: str = "merge_group", path: str = WORKFLOW, id: int = RUN
) -> Any:
    return {"id": id, "head_sha": sha, "event": event, "path": path}


def _jobs(**conclusions: str | None) -> list[Any]:
    """Every job of a green queue run, with `conclusions` overriding by name;
    a conclusion of `missing` drops the job."""
    green: dict[str, str | None] = {name: "success" for name in REPEATED}
    green[IMAGE] = "skipped"
    green["The site still builds from these docs"] = "success"
    green.update(conclusions)
    return [{"name": n, "conclusion": c} for n, c in green.items() if c != "missing"]


def _jobs_of_ci() -> dict[str, Any]:
    return yaml.safe_load(CI.read_text(encoding="utf-8"))["jobs"]


def test_a_queue_run_with_every_repeated_job_green_is_tested() -> None:
    tested, reason = verdict(SHA, [_run()], {RUN: _jobs()})
    assert tested
    assert str(RUN) in reason and SHA in reason


def test_the_image_built_green_in_the_queue_is_tested_too() -> None:
    assert verdict(SHA, [_run()], {RUN: _jobs(**{IMAGE: "success"})})[0]


def test_a_commit_with_no_queue_run_is_not() -> None:
    """What a commit that did not come through the queue looks like."""
    tested, reason = verdict(SHA, [], {})
    assert not tested
    assert "no merge_group run" in reason


@pytest.mark.parametrize(
    "run",
    [
        _run(sha="0" * 40),
        _run(event="pull_request"),
        _run(event="push"),
        _run(path=".github/workflows/codeql.yml"),
    ],
    ids=["another-sha", "pull_request", "push", "another-workflow"],
)
def test_only_a_merge_group_run_of_ci_on_this_sha_counts(run: Any) -> None:
    assert not verdict(SHA, [run], {RUN: _jobs()})[0]


@pytest.mark.parametrize("name", REPEATED)
@pytest.mark.parametrize(
    "conclusion", ["failure", "cancelled", "skipped", None, "missing"]
)
def test_any_repeated_job_not_green_is_not_tested(
    name: str, conclusion: str | None
) -> None:
    """`None` is a job still running; `missing`, one the run does not have."""
    tested, reason = verdict(SHA, [_run()], {RUN: _jobs(**{name: conclusion})})
    assert not tested
    assert name in reason


@pytest.mark.parametrize("conclusion", ["failure", "cancelled", None, "missing"])
def test_the_image_red_or_unfinished_is_not_tested(conclusion: str | None) -> None:
    assert not verdict(SHA, [_run()], {RUN: _jobs(**{IMAGE: conclusion})})[0]


def test_a_red_docs_in_the_queue_does_not_stop_the_skip() -> None:
    """`docs` is not repeated on the push — it runs a different build there —
    so its red in the queue (an ADR before its site entry, #748) is not read."""
    jobs = _jobs(**{"The site still builds from these docs": "failure"})
    assert verdict(SHA, [_run()], {RUN: jobs})[0]


def test_one_green_queue_run_among_several_is_enough() -> None:
    runs = [_run(id=1), _run(id=RUN)]
    jobs = {1: _jobs(**{"gates (3.13)": "failure"}), RUN: _jobs()}
    assert verdict(SHA, runs, jobs)[0]


def test_an_unreadable_api_answers_false_and_exits_0(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Fails towards testing: a wrong `false` costs one run of the suite."""

    def refuse(path: str) -> Any:
        raise urllib.error.URLError("refused")

    output = tmp_path / "output"
    monkeypatch.setattr(queue_tested, "get", refuse)
    monkeypatch.setenv("GITHUB_REPOSITORY", "digline/digline")
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    assert queue_tested.main([SHA]) == 0
    assert output.read_text(encoding="utf-8") == "tested=false\n"
    assert "::warning::" in capsys.readouterr().out


def test_the_cli_writes_true_for_a_green_queue_run(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def listing(path: str) -> Any:
        if "/actions/workflows/ci.yml/runs?" in path:
            assert f"head_sha={SHA}" in path and "event=merge_group" in path
            return {"workflow_runs": [_run()]}
        assert path.endswith(f"/actions/runs/{RUN}/jobs?per_page=100")
        return {"jobs": _jobs()}

    output = tmp_path / "output"
    monkeypatch.setattr(queue_tested, "get", listing)
    monkeypatch.setenv("GITHUB_REPOSITORY", "digline/digline")
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    assert queue_tested.main([SHA]) == 0
    assert output.read_text(encoding="utf-8") == "tested=true\n"


def test_the_versions_held_are_the_gates_matrix() -> None:
    """A version added to the matrix and not here would be read as missing,
    which tests in full: safe, and the cut silently gone. Held equal instead."""
    matrix = _jobs_of_ci()["gates"]["strategy"]["matrix"]["python"]
    assert tuple(matrix) == PYTHONS


def test_every_repeated_name_is_a_job_of_ci() -> None:
    names = {job.get("name", key) for key, job in _jobs_of_ci().items()}
    names |= {f"gates ({python})" for python in PYTHONS}
    assert set(REPEATED) | {IMAGE} <= names


def test_the_repeated_jobs_wait_for_the_answer_and_only_they_do() -> None:
    jobs = _jobs_of_ci()
    for key in SKIPPABLE:
        assert jobs[key]["needs"] == "queue-tested", key
        condition = jobs[key]["if"]
        assert "!cancelled()" in condition, key
        assert "needs.queue-tested.outputs.tested != 'true'" in condition, key
    waiting = {
        key
        for key, job in jobs.items()
        if "queue-tested" in (job.get("needs") or ())
        or "queue-tested" in str(job.get("if", ""))
    }
    assert waiting == set(SKIPPABLE)


def test_the_answer_is_asked_on_a_push_only() -> None:
    job = _jobs_of_ci()["queue-tested"]
    assert job["if"] == "github.event_name == 'push'"
    assert job["permissions"] == {"contents": "read", "actions": "read"}
    assert job["outputs"]["tested"] == "${{ steps.read.outputs.tested }}"
