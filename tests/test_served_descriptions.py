"""PyPI's served descriptions, read after the upload — driven locally.

`.github/served_descriptions.py` runs in the `pypi` job of `publish.yml`, after
the upload. What is pinned here is the part that is ours: **what it refuses**
(any of the seven wordings, also across a line break), **what it waits for**
(the JSON page behind `/simple/`), and **what it does not judge** (an index
that never answers). The index is a local server, for fixed decision 5 and
because a refused description cannot be produced on purpose against PyPI.

**What no test here proves**: that PyPI still renders a README into
`info.description` unchanged. That is how the page read on 2026-10-13 served
it, and the first release after this lands is the next reading.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Generator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / ".github" / "served_descriptions.py"

sys.path.insert(0, str(ROOT / ".github"))
from served_descriptions import WORDINGS  # noqa: E402

CLEAN = "# pytest-digline\n\nA pytest plugin that gates on a committed baseline.\n"


@contextmanager
def server(routes: dict[str, list[tuple[int, bytes]]]) -> Generator[str]:
    """Answers each path from its list in turn, repeating the last answer."""
    seen: dict[str, int] = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            answers = routes.get(self.path, [(404, b"")])
            count = seen.get(self.path, 0)
            seen[self.path] = count + 1
            status, body = answers[min(count, len(answers) - 1)]
            self.send_response(status)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{httpd.server_address[1]}"
    finally:
        httpd.shutdown()


def workspace(tmp_path: Path) -> Path:
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "digline-0.34.0-py3-none-any.whl").write_bytes(b"")
    (dist / "digline-0.34.0.tar.gz").write_bytes(b"")
    (dist / "pytest_digline-0.4.0-py3-none-any.whl").write_bytes(b"")
    return tmp_path


def page(description: str | None) -> bytes:
    return json.dumps({"info": {"description": description}}).encode()


CORE = "/pypi/digline/0.34.0/json"
PLUGIN = "/pypi/pytest-digline/0.4.0/json"


def run(cwd: Path, **env: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=cwd,
        env={**os.environ, "TIMEOUT": "0", "INTERVAL": "0", **env},
        capture_output=True,
        text=True,
        check=False,
    )


def test_clean_descriptions_pass_and_each_package_is_named(tmp_path: Path) -> None:
    cwd = workspace(tmp_path)
    routes = {CORE: [(200, page(CLEAN))], PLUGIN: [(200, page(CLEAN))]}
    with server(routes) as url:
        done = run(cwd, INDEX=url)
    assert done.returncode == 0, done.stderr
    assert "clean    digline 0.34.0" in done.stdout
    assert "clean    pytest-digline 0.4.0" in done.stdout


#: The seven, written here and not imported, so that the script's list is held
#: to a set nobody edits by editing the script: a wording dropped or replaced
#: there is red here. Each is cited, with where it was, in the script.
GOLDEN = frozenset(
    {
        "What pytest cannot carry",
        "not something a plugin can change",
        "pytest cannot carry that distinction",
        "pytest erases",
        "what pytest's exit code cannot carry",
        "what pytest's single exit code cannot tell apart",
        "the runner erases",
    }
)


def test_the_scripts_wordings_are_the_seven_corrected_ones() -> None:
    assert len(WORDINGS) == len(set(WORDINGS))
    assert set(WORDINGS) == GOLDEN


@pytest.mark.parametrize("wording", WORDINGS)
def test_each_corrected_wording_served_again_is_refused(
    tmp_path: Path, wording: str
) -> None:
    cwd = workspace(tmp_path)
    served = f"{CLEAN}\nSome text, then {wording}, then more.\n"
    routes = {CORE: [(200, page(CLEAN))], PLUGIN: [(200, page(served))]}
    with server(routes) as url:
        done = run(cwd, INDEX=url)
    assert done.returncode == 1
    assert f"pytest-digline 0.4.0: {wording!r}" in done.stderr


def test_a_wording_wrapped_across_two_lines_is_still_refused(tmp_path: Path) -> None:
    """How two of the seven were written: #552 removed *"pytest cannot carry
    that"* and *"distinction"* on two lines."""
    cwd = workspace(tmp_path)
    served = (
        f"{CLEAN}\nthe run could not be judged. pytest cannot carry that\n"
        "distinction, and\n"
    )
    routes = {CORE: [(200, page(CLEAN))], PLUGIN: [(200, page(served))]}
    with server(routes) as url:
        done = run(cwd, INDEX=url)
    assert done.returncode == 1
    assert "'pytest cannot carry that distinction'" in done.stderr


def test_a_page_behind_simple_is_waited_for(tmp_path: Path) -> None:
    cwd = workspace(tmp_path)
    routes = {
        CORE: [(200, page(CLEAN))],
        PLUGIN: [(404, b""), (404, b""), (200, page(CLEAN))],
    }
    with server(routes) as url:
        done = run(cwd, INDEX=url, TIMEOUT="5", INTERVAL="0.05")
    assert done.returncode == 0, done.stderr
    assert "served   " in done.stdout and "read 3" in done.stdout


def test_a_404_that_holds_for_the_whole_wait_is_refused(tmp_path: Path) -> None:
    cwd = workspace(tmp_path)
    with server({CORE: [(200, page(CLEAN))]}) as url:
        done = run(cwd, INDEX=url)
    assert done.returncode == 1
    assert "answered 404 for pytest-digline 0.4.0 until the last read" in done.stderr


def test_an_index_that_never_answers_is_not_judged(tmp_path: Path) -> None:
    cwd = workspace(tmp_path)
    with server({CORE: [(503, b"")], PLUGIN: [(503, b"")]}) as url:
        done = run(cwd, INDEX=url)
    assert done.returncode == 2
    assert "not judged" in done.stderr


def test_an_empty_description_is_read_as_clean(tmp_path: Path) -> None:
    cwd = workspace(tmp_path)
    routes = {CORE: [(200, page(None))], PLUGIN: [(200, page(""))]}
    with server(routes) as url:
        done = run(cwd, INDEX=url)
    assert done.returncode == 0, done.stderr


def test_a_dist_with_no_wheel_is_refused_rather_than_passed(tmp_path: Path) -> None:
    (tmp_path / "dist").mkdir()
    done = run(tmp_path, INDEX="http://127.0.0.1:9")
    assert done.returncode == 1
    assert "would pass by reading nothing" in done.stderr


# --- where it runs: publish.yml -------------------------------------------------


def test_the_step_runs_in_pypi_after_its_wait_on_every_tag() -> None:
    """In `pypi`, which runs on every tag: pytest-digline's README, where the
    last corrected wording was, ships on a tag of its own, and `github-release`
    runs on workspace tags only."""
    workflow = yaml.safe_load(
        (ROOT / ".github" / "workflows" / "publish.yml").read_text()
    )
    job = workflow["jobs"]["pypi"]
    assert "if" not in job
    steps = list(job["steps"])
    (check,) = [
        i
        for i, s in enumerate(steps)
        if "served_descriptions.py" in str(s.get("run", ""))
    ]
    (wait,) = [
        i for i, s in enumerate(steps) if "await_index.py" in str(s.get("run", ""))
    ]
    assert check > wait
    assert "if" not in steps[check]
    assert steps[check]["env"] == {"TIMEOUT": "600", "INTERVAL": "10"}
    assert "if" in workflow["jobs"]["github-release"]
