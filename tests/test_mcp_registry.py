"""digline-mcp's registry entry, published by the tag — driven locally.

`.github/mcp_registry.py` runs in the `mcp-registry` job of `publish.yml`.
What is pinned here is the part that is ours: **when it skips** (the registry
already holds the version), **when it refuses** (the manifest and `dist/`
disagree, PyPI never serves the version, the `mcp-name` line is missing), and
**what it retries** — the registry's 404 from PyPI, by its exact text, and
nothing else.

The registry and the index are a local server, for fixed decision 5 and because
none of the refusals can be produced on purpose against the real ones. The
publisher is a stand-in script that prints what it is told to.

**What no test here proves**: that the registry deployed today still words its
404 the way `pypi.go` does at the pinned tag. That is a read of the source at
each pin move, which `test_the_pin_is_the_version_the_texts_were_read_at`
forces and RELEASING.md, *digline-mcp's registry entry moves with its version*,
asks for.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from collections.abc import Generator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import pytest

from release_wiring import jobs

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / ".github" / "mcp_registry.py"
WORKFLOW = ROOT / ".github" / "workflows" / "publish.yml"
SERVER = "dev.digline/digline-mcp"
REGISTRY_PATH = "/v0.1/servers/dev.digline%2Fdigline-mcp/versions/"

sys.path.insert(0, str(ROOT / ".github"))
from mcp_registry import PUBLISHER_VERSION, retryable  # noqa: E402


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


def workspace(
    tmp_path: Path,
    *,
    version: str = "0.6.0",
    package: str | None = None,
    built: str | None = None,
) -> Path:
    manifest = tmp_path / "packages" / "digline-mcp" / "server.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        json.dumps(
            {
                "name": SERVER,
                "version": version,
                "packages": [
                    {
                        "registryType": "pypi",
                        "identifier": "digline-mcp",
                        "version": package or version,
                    }
                ],
            }
        )
    )
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / f"digline_mcp-{built or version}-py3-none-any.whl").write_bytes(b"")
    (dist / "digline-0.31.0-py3-none-any.whl").write_bytes(b"")
    return tmp_path


def run(cwd: Path, *args: str, **env: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=cwd,
        env={**os.environ, "GITHUB_OUTPUT": str(cwd / "out"), **env},
        capture_output=True,
        text=True,
        check=False,
    )


def outputs(cwd: Path) -> str:
    path = cwd / "out"
    return path.read_text() if path.exists() else ""


def entry(version: str) -> bytes:
    return json.dumps({"server": {"name": SERVER, "version": version}}).encode()


def pypi_page(description: str | None) -> bytes:
    return json.dumps({"info": {"description": description}}).encode()


# --- plan ------------------------------------------------------------------


def test_a_version_the_registry_holds_is_skipped(tmp_path: Path) -> None:
    cwd = workspace(tmp_path)
    with server({REGISTRY_PATH + "0.6.0": [(200, entry("0.6.0"))]}) as url:
        done = run(cwd, "plan", REGISTRY=url)
    assert done.returncode == 0, done.stderr
    assert "publish=false" in outputs(cwd)


def test_a_version_the_registry_lacks_is_published(tmp_path: Path) -> None:
    cwd = workspace(tmp_path)
    with server({}) as url:
        done = run(cwd, "plan", REGISTRY=url)
    assert done.returncode == 0, done.stderr
    assert "publish=true" in outputs(cwd)


def test_a_registry_that_errs_is_not_judged_as_absent(tmp_path: Path) -> None:
    cwd = workspace(tmp_path)
    with server({REGISTRY_PATH + "0.6.0": [(503, b"")]}) as url:
        done = run(cwd, "plan", REGISTRY=url)
    assert done.returncode == 2
    assert "publish=" not in outputs(cwd)


def test_a_manifest_ahead_of_dist_is_refused(tmp_path: Path) -> None:
    cwd = workspace(tmp_path, built="0.5.0")
    with server({}) as url:
        done = run(cwd, "plan", REGISTRY=url)
    assert done.returncode == 1
    assert "dist/ holds digline-mcp at ['0.5.0']" in done.stderr
    assert "publish=" not in outputs(cwd)


def test_a_manifest_that_disagrees_with_itself_is_refused(tmp_path: Path) -> None:
    cwd = workspace(tmp_path, package="0.5.0")
    with server({}) as url:
        done = run(cwd, "plan", REGISTRY=url)
    assert done.returncode == 1
    assert "its package says 0.5.0" in done.stderr


# --- await-pypi --------------------------------------------------------------


@pytest.mark.parametrize(
    "description",
    [
        f"# digline-mcp\n\n<!-- mcp-name: {SERVER} -->\n",
        f"mcp-name: {SERVER}",
        f"mcp-name: {SERVER}\nmore",
        f"mcp-name: {SERVER}-->",
    ],
)
def test_a_served_page_with_the_line_passes(tmp_path: Path, description: str) -> None:
    cwd = workspace(tmp_path)
    page = "/pypi/digline-mcp/0.6.0/json"
    with server({page: [(404, b""), (200, pypi_page(description))]}) as url:
        done = run(cwd, "await-pypi", INDEX=url, TIMEOUT="5", INTERVAL="0.1")
    assert done.returncode == 0, done.stderr


@pytest.mark.parametrize(
    "description",
    [
        None,
        "",
        f"mcp-name: {SERVER}-extra",
        f"mcp-name: {SERVER}x",
        "mcp-name: dev.digline/other",
    ],
)
def test_a_served_page_without_the_line_is_refused(
    tmp_path: Path, description: str | None
) -> None:
    cwd = workspace(tmp_path)
    page = "/pypi/digline-mcp/0.6.0/json"
    with server({page: [(200, pypi_page(description))]}) as url:
        done = run(cwd, "await-pypi", INDEX=url, TIMEOUT="0")
    assert done.returncode == 1
    assert "without 'mcp-name: dev.digline/digline-mcp'" in done.stderr


def test_a_version_never_served_is_refused_within_the_wait(tmp_path: Path) -> None:
    cwd = workspace(tmp_path)
    with server({}) as url:
        done = run(cwd, "await-pypi", INDEX=url, TIMEOUT="0.3", INTERVAL="0.1")
    assert done.returncode == 1
    assert "answered 404 for digline-mcp 0.6.0" in done.stderr


# --- publish -----------------------------------------------------------------


def publisher(tmp_path: Path, says: list[tuple[int, str]]) -> Path:
    """A stand-in `mcp-publisher` that answers each call from `says` in turn."""
    script = tmp_path / "mcp-publisher"
    counter = tmp_path / "calls"
    script.write_text(
        f"#!{sys.executable}\n"
        "import json, pathlib, sys\n"
        f"counter = pathlib.Path({str(counter)!r})\n"
        "n = int(counter.read_text()) if counter.exists() else 0\n"
        "counter.write_text(str(n + 1))\n"
        f"says = {json.dumps(says)}\n"
        "code, text = says[min(n, len(says) - 1)]\n"
        "print(text)\n"
        "sys.exit(code)\n"
    )
    script.chmod(0o755)
    return script


def calls(tmp_path: Path) -> int:
    return int((tmp_path / "calls").read_text())


def registry_said(text: str) -> str:
    """How the CLI prints a 400 from the registry: `publish.go` at v1.8.1."""
    body = json.dumps(
        {
            "title": "Bad Request",
            "status": 400,
            "detail": "Failed to publish server",
            "errors": [{"message": text}],
        }
    )
    return (
        "Publishing to https://registry.modelcontextprotocol.io...\n"
        f"Error: publish failed: server returned status 400: {body}"
    )


@pytest.mark.parametrize("text", retryable("digline-mcp", "0.6.0"))
def test_the_registrys_404_from_pypi_is_retried(tmp_path: Path, text: str) -> None:
    cwd = workspace(tmp_path)
    fake = publisher(
        tmp_path,
        [
            (1, registry_said(text + ". Wait and retry")),
            (0, "✓ Successfully published"),
        ],
    )
    done = run(cwd, "publish", str(fake), PAUSE="0")
    assert done.returncode == 0, done.stderr
    assert calls(tmp_path) == 2


def test_any_other_refusal_is_red_at_once(tmp_path: Path) -> None:
    cwd = workspace(tmp_path)
    other = "PyPI package 'digline-mcp' ownership validation failed."
    fake = publisher(
        tmp_path, [(1, registry_said(other)), (0, "✓ Successfully published")]
    )
    done = run(cwd, "publish", str(fake), PAUSE="0")
    assert done.returncode == 1
    assert calls(tmp_path) == 1


@pytest.mark.parametrize(
    "text",
    [
        # The two texts of `pypiVersion404Error` deliberately not retried.
        "PyPI package 'digline-mcp' not found (status: 404)",
        "PyPI package 'digline-mcp' version '0.6.0' not found (status: 404)",
        # The retried text, for another version: not this release's 404.
        "PyPI package 'digline-mcp' exists, but version '0.5.0' "
        "was not found (status: 404)",
    ],
)
def test_a_404_the_filter_does_not_name_is_red(tmp_path: Path, text: str) -> None:
    cwd = workspace(tmp_path)
    fake = publisher(tmp_path, [(1, registry_said(text))])
    done = run(cwd, "publish", str(fake), PAUSE="0")
    assert done.returncode == 1
    assert calls(tmp_path) == 1


def test_the_retries_are_bounded(tmp_path: Path) -> None:
    cwd = workspace(tmp_path)
    (text, _) = retryable("digline-mcp", "0.6.0")
    fake = publisher(tmp_path, [(1, registry_said(text))])
    done = run(cwd, "publish", str(fake), PAUSE="0", ATTEMPTS="3")
    assert done.returncode == 1
    assert calls(tmp_path) == 3
    assert "on all 3 tries" in done.stderr


# --- the job -----------------------------------------------------------------


def job() -> str:
    return jobs(WORKFLOW.read_text())["mcp-registry"].body


def test_the_pin_is_the_version_the_texts_were_read_at() -> None:
    """Moving the publisher pin without re-reading `pypiVersion404Error`
    would leave the retry filter quoting another release's words."""
    pinned = re.search(r'^\s+VERSION:\s*"([^"]+)"', job(), re.M)
    assert pinned is not None
    assert pinned.group(1) == PUBLISHER_VERSION
    assert re.search(r"^\s+SHA256:\s*[0-9a-f]{64}\s*$", job(), re.M)
    assert "releases/latest" not in job()


def test_the_job_follows_pypi_in_its_environment() -> None:
    body = job()
    assert re.search(r"^    needs:\s*pypi\s*$", body, re.M)
    assert re.search(r"^    environment:\s*mcp-registry\s*$", body, re.M)


def test_the_key_is_read_on_the_login_step_only() -> None:
    text = WORKFLOW.read_text()
    assert text.count("secrets.MCP_PRIVATE_KEY") == 1
    step = job().split("name: Log in on digline.dev", 1)[1].split("      - ", 1)[0]
    assert "secrets.MCP_PRIVATE_KEY" in step
