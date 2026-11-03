"""`ci` does not run again what it already ran on the same tree.

`.github/queue_tested.py` answers two questions. On a push to `main`: did a
`merge_group` run of `ci` on the pushed SHA run every repeated job green? On a
queue entry: is the queue's tree the tree the four required checks already
passed on, on the pull request's head? `ci.yml` skips what repeats when the
answer is yes. Driven here on listings shaped like the API's, cut down to the
fields that are read. The push case uses #769's queue run (40554731971) on
9b3cde9d; the queue case uses #756's queue commit 1277f6bf, whose tree is its
head e47a0795's, and that head's pull_request run 40525556004. All were read on
2026-10-28.

**What no test here proves**: that GitHub moves `main` to the commit the queue
tested, and that a `pull_request` run checks out the head's tree when the base
is an ancestor of it. Both were measured, the first on 30 pull requests in 30,
the second on 15 in 15 from the checkout logs, and the first runs after this
lands are their next reading.
"""

from __future__ import annotations

import sys
import tomllib
import urllib.error
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
CI = ROOT / ".github" / "workflows" / "ci.yml"

sys.path.insert(0, str(ROOT / ".github"))
import queue_tested  # noqa: E402
from queue_tested import (  # noqa: E402
    GATES,
    IMAGE,
    PYTHONS,
    REPEATED,
    REQUIRED,
    WORKFLOW,
    gates_verdict,
    tree_verdict,
    verdict,
)

SHA = "9b3cde9d6072641bb127e2bbc31e2c443f1874f6"
RUN = 40554731971
SKIPPABLE = ("gates", "readers", "glyphs", "image-touched")

QUEUED = "1277f6bfef3675018cd5cbeabe972e8fed26317e"
BASE = "dae32b35a4f88264c6055d56c08904a2d69bdfc2"
HEAD = "e47a0795a1eac03af8230fe178a2f08e0d4e92c3"
TREE = "554f06f5d3d55c640dc9b263ec3f5e618d132723"
PR_RUN = 40525556004


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


@pytest.mark.parametrize(
    "name", ["The site's fonts set every character of these docs", IMAGE]
)
@pytest.mark.parametrize("conclusion", [None, "failure", "missing"])
def test_on_a_push_the_gates_skip_while_the_others_do_not(
    name: str, conclusion: str | None
) -> None:
    """The split of 2026-11-03. `glyphs` or the image still running (`None`)
    when `main` moves, or red: the three that read outside the tree run again,
    and the gates legs, which passed this tree, do not."""
    jobs = {RUN: _jobs(**{name: conclusion})}
    assert not verdict(SHA, [_run()], jobs)[0]
    gates, reason = gates_verdict(SHA, [_run()], jobs)
    assert gates
    assert str(RUN) in reason and SHA in reason


def test_a_gates_leg_the_queue_skipped_on_its_tree_counts_as_passed() -> None:
    """On a queue entry whose tree already passed, the legs run with every step
    skipped and conclude `success`: the queue's tree condition held."""
    assert gates_verdict(SHA, [_run()], {RUN: _jobs()})[0]


@pytest.mark.parametrize("name", GATES)
@pytest.mark.parametrize(
    "conclusion", ["failure", "cancelled", "skipped", None, "missing"]
)
def test_on_a_push_any_gates_leg_not_green_in_the_queue_is_not_passed(
    name: str, conclusion: str | None
) -> None:
    gates, reason = gates_verdict(SHA, [_run()], {RUN: _jobs(**{name: conclusion})})
    assert not gates
    assert name in reason


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
def test_on_a_push_only_a_queue_run_of_ci_on_this_sha_passes_the_gates(
    run: Any,
) -> None:
    assert not gates_verdict(SHA, [run], {RUN: _jobs()})[0]


def _push_without_a_queue_run(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, head_tree: str
) -> str:
    """A push whose SHA has no queue run, asked of its own tree: the pushed
    commit is a merge of BASE and HEAD, and HEAD's pull_request run is green."""

    def listing(path: str) -> Any:
        if "event=merge_group" in path:
            return {"workflow_runs": []}
        if path.endswith(f"/git/commits/{QUEUED}"):
            return _commit()
        if path.endswith(f"/git/commits/{HEAD}"):
            return _commit(sha=HEAD, tree=head_tree, parents=(BASE,))
        if path.endswith(f"/compare/{BASE}...{HEAD}"):
            return {"status": "ahead", "behind_by": 0}
        if "/actions/workflows/ci.yml/runs?" in path:
            assert f"head_sha={HEAD}" in path and "event=pull_request" in path
            return {"workflow_runs": [_run(sha=HEAD, event="pull_request", id=PR_RUN)]}
        assert path.endswith(f"/actions/runs/{PR_RUN}/jobs?per_page=100"), path
        return {"jobs": _pr_jobs()}

    output = tmp_path / "output"
    monkeypatch.setattr(queue_tested, "get", listing)
    monkeypatch.setenv("GITHUB_REPOSITORY", "digline/digline")
    monkeypatch.setenv("GITHUB_EVENT_NAME", "push")
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    assert queue_tested.main([QUEUED]) == 0
    return output.read_text(encoding="utf-8")


def test_on_a_push_the_tree_that_passed_on_the_pull_request_skips_the_gates(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The queue's own condition, asked of the pushed commit: the gates legs
    skip, and the three that read outside the tree do not."""
    written = _push_without_a_queue_run(monkeypatch, tmp_path, TREE)
    assert written.startswith("tested=false\nreason=no merge_group run")
    assert "\ngates=true\ngates_reason=pull_request run" in written


def test_on_a_push_a_tree_that_differs_skips_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    written = _push_without_a_queue_run(monkeypatch, tmp_path, "0" * 40)
    assert written.startswith("tested=false\n")
    assert "\ngates=false\ngates_reason=" in written
    assert "is not the head's tree" in written


@pytest.mark.parametrize("event", ["push", "merge_group"])
def test_an_unreadable_api_answers_false_and_exits_0(
    event: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Fails towards testing: a wrong `false` costs one run of the suite."""

    def refuse(path: str) -> Any:
        raise urllib.error.URLError("refused")

    output = tmp_path / "output"
    monkeypatch.setattr(queue_tested, "get", refuse)
    monkeypatch.setenv("GITHUB_REPOSITORY", "digline/digline")
    monkeypatch.setenv("GITHUB_EVENT_NAME", event)
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    assert queue_tested.main([SHA]) == 0
    written = output.read_text(encoding="utf-8")
    assert written.startswith("tested=false\nreason=")
    assert "\ngates=false\ngates_reason=" in written
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
    monkeypatch.setenv("GITHUB_EVENT_NAME", "push")
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    assert queue_tested.main([SHA]) == 0
    written = output.read_text(encoding="utf-8")
    assert written.startswith("tested=true\nreason=merge_group run")
    assert "\ngates=true\ngates_reason=merge_group run" in written
    assert written.count("\n") == 4


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
        condition = " ".join(jobs[key]["if"].split())
        assert "!cancelled()" in condition, key
        # Skipped whole on a push only: on a queue entry `readers`, `glyphs`
        # and the image read things outside the tree, and `gates` skips by
        # its steps.
        # The gates legs read their own answer; the three that read outside
        # the tree read `tested`.
        answer = "gates" if key == "gates" else "tested"
        push_only = (
            "!(github.event_name == 'push' && "
            f"needs.queue-tested.outputs.{answer} == 'true')"
        )
        assert push_only in condition, key
    waiting = {
        key
        for key, job in jobs.items()
        if "queue-tested" in (job.get("needs") or ())
        or "queue-tested" in str(job.get("if", ""))
    }
    assert waiting == set(SKIPPABLE)


def test_on_a_queue_entry_every_step_of_the_gates_legs_is_skipped_and_named() -> None:
    """A matrix job skipped by its `if:` reports one check without the
    version, and the required `gates (3.12)` would never arrive. So the legs
    run and every step but the notice is skipped; the notice says why."""
    steps = _jobs_of_ci()["gates"]["steps"]
    notice, rest = steps[0], steps[1:]
    assert notice["if"] == "needs.queue-tested.outputs.gates == 'true'"
    assert notice["env"]["REASON"] == "${{ needs.queue-tested.outputs.gates_reason }}"
    assert "::notice::" in notice["run"]
    assert rest, "the gates job has no steps"
    skip = "needs.queue-tested.outputs.gates != 'true'"
    for step in rest:
        if step.get("name") == "Types":
            continue
        assert step.get("if") == skip, step
    # Types is skipped the same way, and runs on one leg only: the leg of the
    # version `pyproject.toml` tells pyright to check against.
    with (ROOT / "pyproject.toml").open("rb") as handle:
        version = tomllib.load(handle)["tool"]["pyright"]["pythonVersion"]
    assert version in PYTHONS
    (types,) = [step for step in rest if step.get("name") == "Types"]
    assert types["if"] == f"{skip} && matrix.python == '{version}'", types


def test_the_answer_is_asked_on_a_push_and_on_a_queue_entry() -> None:
    job = _jobs_of_ci()["queue-tested"]
    assert (
        job["if"] == "github.event_name == 'push' || github.event_name == 'merge_group'"
    )
    assert job["permissions"] == {"contents": "read", "actions": "read"}
    assert job["outputs"]["tested"] == "${{ steps.read.outputs.tested }}"
    assert job["outputs"]["reason"] == "${{ steps.read.outputs.reason }}"
    assert job["outputs"]["gates"] == "${{ steps.read.outputs.gates }}"
    assert job["outputs"]["gates_reason"] == "${{ steps.read.outputs.gates_reason }}"


def test_the_required_checks_are_the_gates_legs_and_the_readers() -> None:
    names = {job.get("name", key) for key, job in _jobs_of_ci().items()}
    names |= {f"gates ({python})" for python in PYTHONS}
    assert len(REQUIRED) == 4 and set(REQUIRED) <= names


def _commit(
    sha: str = QUEUED, tree: str = TREE, parents: tuple[str, ...] = (BASE, HEAD)
) -> Any:
    return {"sha": sha, "tree": {"sha": tree}, "parents": [{"sha": p} for p in parents]}


def _pr_jobs(**conclusions: str | None) -> list[Any]:
    green: dict[str, str | None] = {name: "success" for name in REQUIRED}
    # A red `docs` on the head, an ADR before its site entry, is not read.
    green["The site still builds from these docs"] = "failure"
    green.update(conclusions)
    return [{"name": n, "conclusion": c} for n, c in green.items() if c != "missing"]


def _tree(
    commit: Any = None,
    head: Any = None,
    behind_by: int | None = 0,
    runs: Any = None,
    jobs: Any = None,
) -> tuple[bool, str]:
    return tree_verdict(
        QUEUED,
        _commit() if commit is None else commit,
        _commit(sha=HEAD, parents=("8b2fbce2bca35c2bc105f766f4f1e3e5bcef38c0",))
        if head is None
        else head,
        {"behind_by": behind_by},
        [_run(sha=HEAD, event="pull_request", id=PR_RUN)] if runs is None else runs,
        {PR_RUN: _pr_jobs()} if jobs is None else jobs,
    )


def test_a_queue_tree_the_four_checks_passed_on_is_tested() -> None:
    tested, reason = _tree()
    assert tested
    assert str(PR_RUN) in reason and TREE in reason


def test_a_tree_that_differs_is_not() -> None:
    tested, reason = _tree(head=_commit(sha=HEAD, tree="0" * 40, parents=(BASE,)))
    assert not tested
    assert "is not the head's tree" in reason


@pytest.mark.parametrize("behind_by", [1, None])
def test_a_base_the_head_does_not_contain_is_not(behind_by: int | None) -> None:
    """The head run checked out the head merged into the base of its moment:
    only a base the head contains makes that the head's own tree."""
    tested, reason = _tree(behind_by=behind_by)
    assert not tested
    assert "is not an ancestor" in reason


@pytest.mark.parametrize("parents", [(HEAD,), (BASE, HEAD, "f" * 40)])
def test_a_commit_that_is_not_a_merge_of_one_head_is_not(
    parents: tuple[str, ...],
) -> None:
    tested, reason = _tree(commit=_commit(parents=parents))
    assert not tested
    assert f"has {len(parents)} parents" in reason


def test_a_head_read_that_is_not_the_second_parent_is_not() -> None:
    assert not _tree(head=_commit(sha="e" * 40, parents=(BASE,)))[0]


@pytest.mark.parametrize("name", REQUIRED)
@pytest.mark.parametrize(
    "conclusion", ["failure", "cancelled", "skipped", None, "missing"]
)
def test_any_required_check_not_green_on_the_head_is_not(
    name: str, conclusion: str | None
) -> None:
    tested, reason = _tree(jobs={PR_RUN: _pr_jobs(**{name: conclusion})})
    assert not tested
    assert "no pull_request run" in reason


@pytest.mark.parametrize(
    "run",
    [
        _run(sha="0" * 40, event="pull_request", id=PR_RUN),
        _run(sha=HEAD, event="merge_group", id=PR_RUN),
        _run(
            sha=HEAD,
            event="pull_request",
            path=".github/workflows/codeql.yml",
            id=PR_RUN,
        ),
    ],
    ids=["another-sha", "merge_group", "another-workflow"],
)
def test_only_a_pull_request_run_of_ci_on_the_head_counts(run: Any) -> None:
    assert not _tree(runs=[run])[0]


def test_the_cli_reads_the_queue_case_from_the_api(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def listing(path: str) -> Any:
        if path.endswith(f"/git/commits/{QUEUED}"):
            return _commit()
        if path.endswith(f"/git/commits/{HEAD}"):
            return _commit(
                sha=HEAD, parents=("8b2fbce2bca35c2bc105f766f4f1e3e5bcef38c0",)
            )
        if path.endswith(f"/compare/{BASE}...{HEAD}"):
            return {"status": "ahead", "behind_by": 0}
        if "/actions/workflows/ci.yml/runs?" in path:
            assert f"head_sha={HEAD}" in path and "event=pull_request" in path
            return {"workflow_runs": [_run(sha=HEAD, event="pull_request", id=PR_RUN)]}
        assert path.endswith(f"/actions/runs/{PR_RUN}/jobs?per_page=100"), path
        return {"jobs": _pr_jobs()}

    output = tmp_path / "output"
    monkeypatch.setattr(queue_tested, "get", listing)
    monkeypatch.setenv("GITHUB_REPOSITORY", "digline/digline")
    monkeypatch.setenv("GITHUB_EVENT_NAME", "merge_group")
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    assert queue_tested.main([QUEUED]) == 0
    written = output.read_text(encoding="utf-8")
    # On a queue entry only the gates legs are asked.
    assert written.startswith("tested=false\nreason=")
    assert "\ngates=true\ngates_reason=pull_request run" in written
