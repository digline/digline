"""A release is built only from a commit `main` contains.

Two halves, because the guard is two things. `.github/on_main.py` is the
check, and it is driven here against a real git repository with a local
`origin` and a local API that answers like GitHub's — every one of its three
refusals, the pass, and the wait that keeps a race from being a red.
`tools/release_wiring.py` is the wiring, and a guard whose wiring nobody checks
is one that sooner or later gets disconnected: it is run over both release
workflows, and over each way a workflow can get past it.

No network, for fixed decision 5 and because the refusals cannot be produced
on purpose against the real API.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from collections.abc import Generator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

from release_wiring import (
    GUARD,
    RELEASE_WORKFLOWS,
    chain,
    jobs,
    problems,
    ships,
)

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
SCRIPT = ROOT / ".github" / "on_main.py"

#: The jobs that build or publish today, as the markers must recognise them. A
#: marker that silently stops matching would leave a job unchecked; this is
#: what notices.
JOBS_THAT_SHIP = {
    "publish.yml": {"build", "testpypi", "pypi", "github-release", "site"},
    "docker-publish.yml": {"smoke", "publish"},
}


def workflow(name: str) -> str:
    return (WORKFLOWS / name).read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# The wiring
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("name", RELEASE_WORKFLOWS)
def test_every_job_that_ships_waits_for_the_guard(name: str) -> None:
    assert problems(name, workflow(name)) == []


@pytest.mark.parametrize("name", RELEASE_WORKFLOWS)
def test_the_markers_still_recognise_every_job_that_ships(name: str) -> None:
    found = jobs(workflow(name))
    shipping = {job for job, value in found.items() if ships(value)}
    assert JOBS_THAT_SHIP[name] <= shipping, (
        f"{name}: {sorted(JOBS_THAT_SHIP[name] - shipping)} no longer look like "
        "jobs that build or publish, so nothing checks what they wait for"
    )


def test_the_guard_asks_for_ancestry() -> None:
    """The job runs the script; the script is what asks the question."""
    text = SCRIPT.read_text(encoding="utf-8")
    assert '"merge-base", "--is-ancestor"' in text


_GUARD = """\
  on-main:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          fetch-depth: 0
      - run: python3 .github/on_main.py HEAD "$LABEL"
"""

PYPI_PUBLISH = "dc37677b2e1c63e2034f94d8a5b11f265b73ba33"

_PUBLISH = """\
  publish:
{needs}    runs-on: ubuntu-latest
    steps:
      - uses: pypa/gh-action-pypi-publish@{sha} # v1.14.2
"""


def publishing(needs: str = "") -> str:
    """A job that uploads to an index, waiting for whatever `needs` says."""
    return _PUBLISH.format(sha=PYPI_PUBLISH, needs=needs)


def synthetic(*jobs_: str) -> str:
    return "name: t\non:\n  push:\n    tags: ['v*']\njobs:\n" + "".join(jobs_)


def test_a_publishing_job_with_no_needs_fails_the_gate() -> None:
    """The case this exists for: a job added beside the guard, not behind it."""
    found = problems("t.yml", synthetic(_GUARD, publishing()))
    assert len(found) == 1 and "`publish` builds or publishes" in found[0], found


def test_a_workflow_without_the_guard_fails_the_gate() -> None:
    found = problems("t.yml", synthetic(publishing()))
    assert found and "no `on-main` job" in found[0], found


def test_a_chain_of_needs_passes_and_each_way_of_writing_it_is_read() -> None:
    middle = (
        "  build:\n    needs: on-main\n    runs-on: ubuntu-latest\n"
        "    steps:\n      - run: uv build\n"
    )
    for needs in (
        "    needs: build\n",
        "    needs: [lint, build]\n",
        "    needs:\n      - lint\n      - build\n",
    ):
        text = synthetic(_GUARD, middle, publishing(needs))
        assert problems("t.yml", text) == [], needs
        assert chain("publish", jobs(text)) >= {"build", GUARD}


def test_a_job_whose_chain_does_not_reach_the_guard_fails() -> None:
    lint = (
        "  lint:\n    runs-on: ubuntu-latest\n    steps:\n      - run: ruff check .\n"
    )
    text = synthetic(_GUARD, lint, publishing("    needs: lint\n"))
    assert any("`publish` builds or publishes" in p for p in problems("t.yml", text))


@pytest.mark.parametrize(
    "condition", ["always()", "${{ !cancelled() }}", "failure() || success()"]
)
def test_a_job_that_runs_past_a_failed_need_fails(condition: str) -> None:
    job = publishing(f"    needs: on-main\n    if: {condition}\n")
    found = problems("t.yml", synthetic(_GUARD, job))
    assert any("runs past a failed `needs:`" in p for p in found), found


@pytest.mark.parametrize(
    ("change", "said"),
    [
        (("fetch-depth: 0", "fetch-depth: 1"), "fetch-depth: 0"),
        (("    runs-on", "    if: false\n    runs-on"), "can be skipped"),
        (("    runs-on", "    continue-on-error: true\n    runs-on"), "stops nothing"),
        ((".github/on_main.py", "true"), "does not run"),
    ],
)
def test_a_guard_that_can_be_got_round_fails(
    change: tuple[str, str], said: str
) -> None:
    guard = _GUARD.replace(*change, 1)
    found = problems("t.yml", synthetic(guard, publishing("    needs: on-main\n")))
    assert any(said in p for p in found), found


def test_a_comment_does_not_make_a_job_ship() -> None:
    notes = (
        "  notes:\n    runs-on: ubuntu-latest\n    steps:\n"
        "      # after uv build and twine upload\n      - run: echo done\n"
    )
    assert problems("t.yml", synthetic(_GUARD, notes)) == []


# --------------------------------------------------------------------------- #
# The check
# --------------------------------------------------------------------------- #


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@t",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@t",
        },
    ).stdout.strip()


@pytest.fixture
def clone(tmp_path: Path) -> Path:
    """A clone of an `origin` whose `main` has one commit, with a branch `pr`
    one commit ahead of it that `main` does not contain."""
    origin, work = tmp_path / "origin.git", tmp_path / "work"
    _git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    _git(tmp_path, "clone", "-q", str(origin), str(work))
    _git(work, "commit", "-q", "--allow-empty", "-m", "on main")
    _git(work, "push", "-q", "origin", "HEAD:main")
    _git(work, "checkout", "-q", "-b", "pr")
    _git(work, "commit", "-q", "--allow-empty", "-m", "on the pull request")
    _git(work, "push", "-q", "origin", "pr")
    return work


@contextmanager
def api(answer: tuple[int, list[dict[str, Any]]]) -> Generator[str]:
    """A local API answering `GET /repos/o/r/commits/<sha>/pulls` with `answer`."""

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler's name
            status, body = answer
            data = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()


def check(
    clone: Path, commit: str, url: str = "http://127.0.0.1:9", **env: str
) -> subprocess.CompletedProcess[str]:
    """The script as the workflow runs it: in the checkout, on a tag's label."""
    return subprocess.run(
        [sys.executable, str(SCRIPT), commit, "v9.9.9"],
        cwd=clone,
        env={
            "PATH": os.environ["PATH"],
            "GITHUB_REPOSITORY": "o/r",
            "API": url,
            "ATTEMPTS": "2",
            "INTERVAL": "0",
            **env,
        },
        capture_output=True,
        text=True,
        timeout=60,
    )


def pull(
    number: int, state: str, head: str, *, merged: bool = False, base: str = "main"
) -> dict[str, Any]:
    return {
        "number": number,
        "state": state,
        "merged_at": "2026-09-26T10:00:00Z" if merged else None,
        "head": {"sha": head},
        "base": {"ref": base},
    }


def test_a_commit_on_main_passes(clone: Path) -> None:
    result = check(clone, "main")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "v9.9.9" in result.stdout and "is on main" in result.stdout


def test_a_commit_no_pull_request_carries_is_not_on_main(clone: Path) -> None:
    sha = _git(clone, "rev-parse", "pr")
    with api((200, [])) as url:
        result = check(clone, "pr", url)
    assert result.returncode == 1
    assert "::error title=not on main::" in result.stdout
    assert f"v9.9.9 ({sha})" in result.stdout


def test_a_commit_github_never_saw_is_not_on_main(clone: Path) -> None:
    """422 is what the API says for an unknown commit: an answer, not an outage."""
    with api((422, [])) as url:
        result = check(clone, "pr", url)
    assert "title=not on main::" in result.stdout
    assert "could not ask" not in result.stdout


def test_the_head_of_an_open_pull_request_says_merge_it(clone: Path) -> None:
    sha = _git(clone, "rev-parse", "pr")
    with api((200, [pull(41, "open", sha)])) as url:
        result = check(clone, "pr", url)
    assert result.returncode == 1
    assert (
        "title=head of open PR #41: merge it, then tag the merge commit or re-run::"
        in result.stdout
    )
    assert f"v9.9.9 ({sha}) is the head of open PR #41" in result.stdout


def test_a_merged_pull_request_main_does_not_show_yet_says_re_run(clone: Path) -> None:
    sha = _git(clone, "rev-parse", "pr")
    with api((200, [pull(42, "closed", sha, merged=True)])) as url:
        result = check(clone, "pr", url)
    assert result.returncode == 1
    assert (
        "title=on merged PR #42 but main does not show it yet: re-run::"
        in result.stdout
    )
    assert f"v9.9.9 ({sha})" in result.stdout


@pytest.mark.parametrize(
    "pulls",
    [
        [pull(43, "closed", "x")],  # closed without merging
        [pull(44, "closed", "x", merged=True, base="release")],  # merged, elsewhere
        [pull(45, "open", "x", base="release")],  # open, elsewhere
    ],
)
def test_a_pull_request_that_will_not_bring_it_to_main_is_not_on_main(
    clone: Path, pulls: list[dict[str, Any]]
) -> None:
    with api((200, pulls)) as url:
        result = check(clone, "pr", url)
    assert result.returncode == 1
    assert "title=not on main::" in result.stdout


def test_a_failed_lookup_still_refuses_and_says_so(clone: Path) -> None:
    with api((500, [])) as url:
        result = check(clone, "pr", url)
    assert result.returncode == 1
    assert "title=not on main::" in result.stdout
    assert "could not ask which pull request carries it: HTTP 500" in result.stdout


def test_a_merge_that_lands_while_it_waits_passes(clone: Path) -> None:
    """The race: the tag is pushed a moment before `main` shows the merge.

    The merge arrives after the first fetch and before the second, and the
    check passes without asking the API — which is unreachable here, so
    asking it would refuse.
    """

    def merge() -> None:
        _git(clone, "push", "-q", "origin", "pr:main")

    timer = threading.Timer(1.0, merge)
    timer.start()
    try:
        result = check(clone, "pr", ATTEMPTS="3", INTERVAL="3")
    finally:
        timer.join()
    assert result.returncode == 0, result.stdout + result.stderr
    assert "fetching again" in result.stdout
