"""The counts a reviewer reads at the PyPI gate are in the job summary.

On digline-anthropic-v0.6.1 the `pypi` job waited ten seconds, which was the
time to the click, and the session watching the run polled every twenty: the
counts reached the reviewer after the approval. A watch is a race against the
person it exists to inform. So `publish.yml` writes the counts to the job
summary, on the run's page, before the `pypi` job starts waiting.
(RELEASING.md, *Status*, digline-anthropic-v0.6.1)

Held here: the two sections the helper writes, the selection written by
`select_unpublished.py` against a fake index, and the shape of the workflow —
PyPI asked before the gate, and no step that feeds the summary pipes a command
that could fail.
"""

from __future__ import annotations

import importlib.util
import os
import re
import subprocess
import sys
import threading
from collections.abc import Generator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import ModuleType

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "publish.yml"
SELECT = ROOT / ".github" / "select_unpublished.py"


def helper() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "gate_summary", ROOT / ".github" / "gate_summary.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


#: twine's own output, colour codes included, as the build job logged it.
TWINE = (
    "Checking dist/digline-0.27.0-py3-none-any.whl: \x1b[32mPASSED\x1b[0m\n"
    "Checking dist/digline_anthropic-0.6.1.tar.gz: \x1b[32mPASSED\x1b[0m\n"
)


def test_the_twine_count_is_read_from_twines_own_lines() -> None:
    section = helper().twine_section(TWINE)
    assert "**2 PASSED**" in section
    assert "`dist/digline_anthropic-0.6.1.tar.gz`" in section


def test_a_count_that_is_not_found_is_never_written_as_zero() -> None:
    """A summary that read `0 PASSED` because twine changed its wording would be
    a green nobody checked."""
    gate = helper()
    assert "not found" in gate.twine_section("something else entirely\n")
    assert "0 PASSED" not in gate.twine_section("something else entirely\n")
    section = gate.install_section("TestPyPI", "", "")
    assert section.count("not found") == 2


def test_the_install_section_carries_the_imports_and_the_calls() -> None:
    section = helper().install_section(
        "TestPyPI",
        "imported 6: digline, digline_anthropic, digline_bedrock, digline_mcp, "
        "digline_openai, pytest_digline\n",
        "digline: tenant 'northwind' · 3 cases × 1 sample = 3 calls to the target\n"
        "digline: target: 3 calls, no counts reported, 0.015720 USD (counted 0 of 3)\n"
        "some other line\n",
    )
    assert "**imported 6**" in section
    assert "3 calls to the target" in section
    assert "target: 3 calls" in section
    assert "some other line" not in section


# --------------------------------------------------------------------------- #
# select_unpublished.py, against an index that answers what it is told to
# --------------------------------------------------------------------------- #


@contextmanager
def an_index(released: set[str]) -> Generator[str]:
    """`/pypi/<name>/<version>/json` answers 200 for `released`, 404 else."""

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            parts = self.path.strip("/").split("/")
            key = f"{parts[1]}/{parts[2]}" if len(parts) >= 3 else ""
            self.send_response(200 if key in released else 404)
            self.end_headers()
            self.wfile.write(b"{}")

        def log_message(self, format: str, *args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()


def test_the_selection_is_written_where_the_reviewer_reads_it(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    for name in (
        "digline-0.27.0-py3-none-any.whl",
        "digline-0.27.0.tar.gz",
        "digline_anthropic-0.6.1-py3-none-any.whl",
        "digline_anthropic-0.6.1.tar.gz",
    ):
        (dist / name).write_bytes(b"x")
    summary = tmp_path / "summary.md"
    output = tmp_path / "output.txt"
    preview = tmp_path / "preview"
    with an_index({"digline/0.27.0"}) as index:
        done = subprocess.run(
            [sys.executable, str(SELECT)],
            cwd=tmp_path,
            env={
                **os.environ,
                "INDEX": index,
                "OUT": str(preview),
                "SUMMARY_TITLE": "PyPI's selection, read before the gate",
                "GITHUB_OUTPUT": str(output),
                "GITHUB_STEP_SUMMARY": str(summary),
            },
            capture_output=True,
            text=True,
            check=False,
        )
    assert done.returncode == 0, done.stderr
    written = summary.read_text(encoding="utf-8")
    assert "### PyPI's selection, read before the gate" in written
    assert "**2 publish, 2 skip**" in written
    assert "- publish `digline_anthropic-0.6.1.tar.gz`" in written
    assert "count=2" in output.read_text(encoding="utf-8")
    # A preview lands where nothing publishes from.
    assert sorted(p.name for p in preview.iterdir()) == [
        "digline_anthropic-0.6.1-py3-none-any.whl",
        "digline_anthropic-0.6.1.tar.gz",
    ]
    assert not (tmp_path / "to-publish").exists()


# --------------------------------------------------------------------------- #
# The workflow's shape
# --------------------------------------------------------------------------- #


def jobs() -> dict[str, dict[str, object]]:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]


def steps(job: str) -> list[dict[str, object]]:
    return list(jobs()[job]["steps"])  # type: ignore[arg-type]


def test_pypi_is_asked_before_the_gate_and_nothing_is_published_from_it() -> None:
    """The preview runs in the job the gate waits on, against PyPI, into a
    directory no publish step reads."""
    (preview,) = [s for s in steps("testpypi") if s.get("id") == "preview"]
    env = preview["env"]
    assert isinstance(env, dict)
    assert env["INDEX"] == "https://pypi.org"
    assert env["OUT"] != "to-publish" and "SUMMARY_TITLE" in env
    assert jobs()["pypi"]["needs"] == "testpypi"
    for job in ("testpypi", "pypi"):
        for step in steps(job):
            with_ = step.get("with")
            if isinstance(with_, dict) and "packages-dir" in with_:
                assert with_["packages-dir"] == "to-publish/"


def test_every_count_the_reviewer_reads_is_written_before_the_gate() -> None:
    before = [*steps("build"), *steps("testpypi")]
    text = "\n".join(str(step.get("run", "")) for step in before)
    assert "gate_summary.py twine" in text
    assert "gate_summary.py install" in text
    titled = [
        step
        for step in steps("testpypi")
        if isinstance(env := step.get("env"), dict) and "SUMMARY_TITLE" in env
    ]
    assert len(titled) == 2


@pytest.mark.parametrize("job", ["build", "testpypi"])
def test_no_step_that_feeds_the_summary_pipes_a_command(job: str) -> None:
    """A `run:` with no `shell:` is `bash -e` without `pipefail`, so `cmd | tee`
    would let a failed check through with a green step. The outputs go to
    files instead."""
    for step in steps(job):
        body = str(step.get("run", ""))
        if "gate_summary.py" not in body:
            continue
        without_or = body.replace("||", "")
        assert not re.search(r"(?<![<>])\|(?!\|)", without_or), step.get("name")
