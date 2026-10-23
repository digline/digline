"""The core against the plugins PyPI serves — the parts that run without a tag.

`.github/plugins_against_core.py` runs in the `testpypi` job of `publish.yml`.
Two halves of it are pinned here:

- **each exercise, against this workspace**: the server's tools over stdio, a
  pytest session naming a suite, each provider built by the core from a suite
  file. The workspace holds the core and every plugin from the tree, which is
  the pair a tag would release together; green here says the exercise works,
  and the shadowed provider below says it can fail.
- **the reading of PyPI**: the three words, from a local index (fixed decision
  5, and because an exclusion cannot be produced on purpose against PyPI).

**What no test here proves**: which index wins when the job installs this core
from TestPyPI with PyPI as an extra index. That is read from the job's
configuration and was never observed; the first tag that runs the step is the
first observation.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from collections.abc import Generator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / ".github" / "plugins_against_core.py"
QUICKSTART = ROOT / "examples" / "quickstart"

sys.path.insert(0, str(ROOT / ".github"))
import plugins_against_core as script  # noqa: E402


def exercise(
    tmp_path: Path, kind: str, name: str, **env: str
) -> subprocess.CompletedProcess[str]:
    app = tmp_path / "app"
    shutil.copytree(QUICKSTART, app)
    return subprocess.run(
        [sys.executable, str(SCRIPT), "exercise", kind, name, str(app)],
        env={**os.environ, **env},
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )


# --- the exercises, against this workspace ---------------------------------------


def test_every_tool_the_server_lists_is_called_and_answers(tmp_path: Path) -> None:
    done = exercise(tmp_path, "mcp", "digline-mcp")
    assert done.returncode == 0, done.stdout + done.stderr
    listed = next(
        line for line in done.stdout.splitlines() if line.startswith("the server lists")
    )
    tools = listed.split(": ", 1)[1].split(", ")
    # The roster is the server's, so it is read back here rather than written:
    # every tool it listed has its own line.
    assert len(tools) >= 8
    for tool in tools:
        assert f"{tool}: answered" in done.stdout


def test_a_tool_the_script_has_no_arguments_for_is_red_rather_than_skipped() -> None:
    with pytest.raises(SystemExit, match="lists a tool `promote` this script has no"):
        script.tool_arguments("promote", ["a", "b"])


def test_a_session_names_the_suite_both_ways(tmp_path: Path) -> None:
    done = exercise(tmp_path, "pytest", "pytest-digline")
    assert done.returncode == 0, done.stdout + done.stderr
    assert "pytest --digline-suite suite.py : exit 0" in done.stdout
    assert "pytest --digline-suite suite.py --digline-run: exit 0" in done.stdout


@pytest.mark.parametrize("provider", sorted(script.MODELS))
def test_each_provider_is_built_by_the_core_with_no_key(
    tmp_path: Path, provider: str
) -> None:
    done = exercise(tmp_path, f"provider:{provider}", f"digline-{provider}")
    assert done.returncode == 0, done.stdout + done.stderr
    assert "target, judge and claim judge built by the core" in done.stdout


def test_a_provider_whose_factory_lost_a_parameter_is_red(tmp_path: Path) -> None:
    """The break this check is for: a signature. The shadow registers under the
    installed entry point's module name and drops `prompt_file`, which every
    published target takes and the core passes from the suite file."""
    shadow = tmp_path / "shadow" / "digline_anthropic"
    shadow.mkdir(parents=True)
    (shadow / "__init__.py").write_text(
        "from digline.targets import Provider\n"
        "from digline_anthropic_real import AnthropicJudge, AnthropicClaimJudge\n"
        "class AnthropicTarget:\n"
        "    def __init__(self, model: str, max_tokens: int) -> None:\n"
        "        self.model = model\n"
        "PROVIDER = Provider(name='anthropic', target=AnthropicTarget,\n"
        "    judge=AnthropicJudge, claim_judge=AnthropicClaimJudge)\n",
        encoding="utf-8",
    )
    real = Path(__import__("digline_anthropic").__file__).parent
    shutil.copytree(real, tmp_path / "shadow" / "digline_anthropic_real")
    # The copy imports itself by its old name; point those imports at the copy.
    for module in (tmp_path / "shadow" / "digline_anthropic_real").glob("*.py"):
        module.write_text(
            module.read_text(encoding="utf-8").replace(
                "digline_anthropic.", "digline_anthropic_real."
            ),
            encoding="utf-8",
        )
    done = exercise(
        tmp_path,
        "provider:anthropic",
        "digline-anthropic",
        PYTHONPATH=str(tmp_path / "shadow"),
    )
    assert done.returncode != 0
    assert "prompt_file" in done.stdout + done.stderr


def test_a_provider_with_no_model_declared_is_red_rather_than_skipped(
    tmp_path: Path,
) -> None:
    done = exercise(tmp_path, "provider:nobody", "digline-nobody")
    assert done.returncode != 0
    assert "no model is declared for the provider `nobody`" in done.stderr


def test_a_plugin_with_no_exercise_is_red_rather_than_skipped() -> None:
    """The core itself registers no provider and is no named plugin, so it
    stands in for a new package nobody said how to try."""
    with pytest.raises(script.Broken, match="no exercise is declared for digline"):
        script.kind_of(Path(sys.executable), "digline")


def test_a_provider_is_recognised_by_its_entry_point() -> None:
    assert script.kind_of(Path(sys.executable), "digline-bedrock") == "provider:bedrock"


# --- the reading of PyPI -----------------------------------------------------------


@contextmanager
def index(pages: dict[str, tuple[int, bytes]]) -> Generator[str]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            status, body = pages.get(self.path, (404, b""))
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


def page(version: str, *requires: str) -> tuple[int, bytes]:
    info = {"version": version, "requires_dist": list(requires)}
    return 200, json.dumps({"info": info}).encode()


def test_the_newest_version_and_its_range_on_the_core_are_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pages = {
        "/pypi/digline-mcp/json": page(
            "0.6.2", "mcp<3,>=2.2", "digline<0.34,>=0.32.0", 'pytest; extra == "dev"'
        )
    }
    with index(pages) as url:
        monkeypatch.setattr(script, "PYPI", url)
        found = script.served("digline-mcp")
    assert found == script.Served("digline-mcp", "0.6.2", "<0.34,>=0.32.0")


def test_a_cap_below_the_core_excludes_and_a_range_that_holds_it_admits() -> None:
    assert not script.admits("<0.34,>=0.32.0", "0.34.0")
    assert script.admits("<0.35,>=0.34.0", "0.34.0")
    assert script.admits(">=0.17.0", "0.34.0")
    assert script.admits("", "0.34.0")


def test_a_plugin_pypi_does_not_serve_is_not_a_plugin_anybody_runs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with index({}) as url:
        monkeypatch.setattr(script, "PYPI", url)
        assert script.served("digline-new") is None


def test_an_index_that_never_answers_is_not_judged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with index({"/pypi/digline-mcp/json": (503, b"")}) as url:
        monkeypatch.setattr(script, "PYPI", url)
        monkeypatch.setattr(script, "ATTEMPTS", 2)
        monkeypatch.setattr(script, "PAUSE", 0.0)
        with pytest.raises(script.NotJudged):
            script.served("digline-mcp")


def test_the_summary_names_the_debt_and_where_it_is_ruled() -> None:
    outcomes = [
        script.Outcome(
            "digline-anthropic", "works", "0.6.1", ">=0.17.0", "provider:anthropic"
        ),
        script.Outcome(
            "digline-mcp",
            "excluded",
            "0.6.2",
            "<0.34,>=0.32.0",
            f"excluded by its cap, so this release owes it a release ({script.OWED})",
        ),
        script.Outcome(
            "pytest-digline", "broken", "0.3.1", "<0.35", "failed its exercise"
        ),
    ]
    text = script.summary("0.34.0", outcomes)
    assert (
        "| `digline-mcp` | 0.6.2 | `<0.34,>=0.32.0` | **excluded**: "
        "excluded by its cap, so this release owes it a release" in text
    )
    assert '"The plugins, after this release"' in text
    assert "**works**" in text and "**broken**" in text


def test_a_dist_with_no_plugin_is_refused_rather_than_passed(tmp_path: Path) -> None:
    (tmp_path / "digline-0.34.0-py3-none-any.whl").write_bytes(b"")
    with pytest.raises(SystemExit, match="would pass by trying nothing"):
        script.roster(tmp_path)


def test_the_roster_is_dist_less_the_core(tmp_path: Path) -> None:
    for wheel in (
        "digline-0.34.0-py3-none-any.whl",
        "digline_mcp-0.7.0-py3-none-any.whl",
        "pytest_digline-0.4.0-py3-none-any.whl",
    ):
        (tmp_path / wheel).write_bytes(b"")
    assert script.roster(tmp_path) == ("0.34.0", ["digline-mcp", "pytest-digline"])
