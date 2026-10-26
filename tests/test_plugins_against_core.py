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

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Generator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from typing import cast

import pytest
import yaml

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
    """With an empty home, as on a runner: a developer's `~/.aws/config` once
    gave Bedrock a region the runner did not have, green here and red there."""
    home = tmp_path / "home"
    home.mkdir()
    done = exercise(
        tmp_path, f"provider:{provider}", f"digline-{provider}", HOME=str(home)
    )
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
    text = script.summary("Plugins", "0.34.0", outcomes)
    assert (
        "| `digline-mcp` | 0.6.2 | `<0.34,>=0.32.0` | **excluded**: "
        "excluded by its cap, so this release owes it a release" in text
    )
    assert '"The plugins, after this release"' in text
    assert "**works**" in text and "**broken**" in text
    assert text.startswith("### Plugins\n")


@pytest.mark.parametrize(("title", "written"), [("Plugins", True), ("", False)])
def test_the_table_reaches_the_summary_under_the_steps_title(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, title: str, written: bool
) -> None:
    """Under `SUMMARY_TITLE`, as `select_unpublished.py` does, and only then;
    `broken` is the one outcome that fails the step."""
    outcomes = [
        script.Outcome("digline-mcp", "excluded", "0.6.2", "<0.34", "excluded"),
        script.Outcome("pytest-digline", "broken", "0.3.1", "<0.35", "failed"),
    ]

    def roster(dist: Path) -> tuple[str, list[str]]:
        return "0.34.0", ["digline-mcp"]

    def check(dist: Path, work: Path) -> list[script.Outcome]:
        return outcomes

    monkeypatch.setattr(script, "roster", roster)
    monkeypatch.setattr(script, "check", check)
    page = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(page))
    monkeypatch.setenv("SUMMARY_TITLE", title)
    assert script.main_check() == 1
    assert page.exists() is written
    if written:
        assert page.read_text().startswith("### Plugins\n")


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


# --- where it runs: publish.yml -------------------------------------------------


def steps_of_testpypi() -> list[dict[str, object]]:
    workflow = yaml.safe_load(
        (ROOT / ".github" / "workflows" / "publish.yml").read_text()
    )
    return list(workflow["jobs"]["testpypi"]["steps"])


def position(steps: list[dict[str, object]], needle: str) -> int:
    (found,) = [i for i, s in enumerate(steps) if needle in str(s.get("run", ""))]
    return found


def test_the_step_runs_in_testpypi_after_the_install_and_before_the_gate() -> None:
    """In `testpypi`, which `pypi` waits on: a red here stops the upload, and
    its summary is on the page the reviewer clicks from. After the install,
    which is what put this core on TestPyPI for it to install."""
    steps = steps_of_testpypi()
    check = position(steps, "plugins_against_core.py check")
    assert check > position(steps, "gate_summary.py install TestPyPI")
    workflow = yaml.safe_load(
        (ROOT / ".github" / "workflows" / "publish.yml").read_text()
    )
    assert workflow["jobs"]["pypi"]["needs"] == "testpypi"
    assert "packaging==" in str(steps[check]["run"])
    uv = [i for i, s in enumerate(steps) if "setup-uv" in str(s.get("uses", ""))]
    assert uv and uv[0] < check


@pytest.mark.parametrize(
    ("tag", "runs"),
    [
        ("v0.34.0", True),
        ("pytest-digline-v0.4.0", False),
        ("digline-mcp-v0.7.0", False),
        ("digline-anthropic-v0.6.2", False),
    ],
)
def test_the_step_runs_on_workspace_tags_only(tag: str, runs: bool) -> None:
    """A tag of plugins alone puts no new core on TestPyPI. The condition is
    read as GitHub evaluates `startsWith`; the `False` rows are the control."""
    steps = steps_of_testpypi()
    condition = steps[position(steps, "plugins_against_core.py check")]["if"]
    assert condition == "startsWith(github.ref_name, 'v')"
    assert tag.startswith("v") is runs


# --- what the `pypi` job is handed: the classification, as a job output -------
#
# Made by a step of its own on every tag, and marked, so that an empty output
# cannot pass for "nothing to exclude" (#717, #731). `check` no longer writes it:
# it runs on `v*` tags only, and on a plugin tag the output it wrote was empty.


def jobs() -> dict[str, dict[str, object]]:
    workflow = yaml.safe_load(
        (ROOT / ".github" / "workflows" / "publish.yml").read_text()
    )
    return dict(workflow["jobs"])


def classifying_step() -> dict[str, object]:
    """The step whose output the `testpypi` job hands to `pypi`, found through
    the job's `outputs` rather than by its name."""
    outputs = cast("dict[str, str]", jobs()["testpypi"]["outputs"])
    exported = outputs["excluded"]
    found = re.fullmatch(r"\$\{\{ steps\.([a-z_-]+)\.outputs\.excluded \}\}", exported)
    assert found, exported
    (step,) = [s for s in steps_of_testpypi() if s.get("id") == found.group(1)]
    return step


def runs_on(condition: object, tag: str) -> bool:
    """Whether a step runs on `tag`, for the two conditions this workflow uses
    on a tag push. Anything else is a condition this test cannot read, which is
    a failure, not a guess."""
    if condition is None:
        return True
    if condition == "startsWith(github.ref_name, 'v')":
        return tag.startswith("v")
    raise AssertionError(f"a condition this test cannot read: {condition!r}")


def run_classifying_step(
    tmp_path: Path, printed: str, status: int
) -> tuple[subprocess.CompletedProcess[str], str, str]:
    """The step's own script, run the way Actions runs a `run:` block, with a
    `uv` on the path that stands for the classification: it records how it was
    called, prints `printed` and exits with `status`. Returns the step's
    outcome, what it wrote to `GITHUB_OUTPUT`, and the call."""
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    calls = tmp_path / "calls"
    uv = bin_ / "uv"
    uv.write_text(
        f'#!/bin/sh\necho "$*" > "{calls}"\necho "{printed}"\nexit {status}\n',
        encoding="utf-8",
    )
    uv.chmod(0o755)
    output = tmp_path / "output"
    output.write_text("", encoding="utf-8")
    # `bash -e -o pipefail` is the shell Actions runs a `run:` block in.
    done = subprocess.run(
        [
            "bash",
            "--noprofile",
            "--norc",
            "-e",
            "-o",
            "pipefail",
            "-c",
            str(classifying_step()["run"]),
        ],
        capture_output=True,
        text=True,
        check=False,
        env={
            "PATH": f"{bin_}{os.pathsep}{os.environ['PATH']}",
            "GITHUB_OUTPUT": str(output),
        },
    )
    return done, output.read_text(encoding="utf-8"), calls.read_text(encoding="utf-8")


def test_the_testpypi_job_exports_the_classification(tmp_path: Path) -> None:
    """The output both install checks read is written, under the name the job
    exports, with what the classification printed. A test that looked for the
    word `GITHUB_OUTPUT` in the step passed a write under another key and a
    write of nothing, and either reaches `pypi` as an output no step wrote.
    (#731)"""
    done, written, call = run_classifying_step(
        tmp_path, "classified digline-mcp==0.6.2", 0
    )
    assert done.returncode == 0, done.stderr
    assert call.split()[-3:] == [
        "python",
        ".github/plugins_against_core.py",
        "excluded",
    ]
    assert written == "excluded=classified digline-mcp==0.6.2\n"


def test_a_classification_that_fails_fails_its_step_and_writes_nothing(
    tmp_path: Path,
) -> None:
    """The assignment, not a substitution inside `echo`, carries the status
    out: a classification that failed stops the job before either install
    check, rather than handing on what it printed before failing."""
    done, written, _ = run_classifying_step(tmp_path, "classified", 1)
    assert done.returncode != 0
    assert written == ""


@pytest.mark.parametrize(
    "tag",
    [
        "v0.34.0",
        "pytest-digline-v0.4.0",
        "digline-mcp-v0.6.3",
        "digline-anthropic-v0.6.2",
    ],
)
def test_the_classification_the_pypi_job_reads_is_made_on_every_tag(tag: str) -> None:
    """A plugin tag installs the same manifest as a workspace tag, and needs
    the same exclusions. Made by `check`, it was made on `v*` tags only, and on
    `pytest-digline-v0.4.0` and `digline-mcp-v0.6.3` the `pypi` job was handed
    an empty output. (#731)"""
    assert runs_on(classifying_step().get("if"), tag)


def pypi_step(needle: str) -> dict[str, object]:
    steps = cast("list[dict[str, object]]", jobs()["pypi"]["steps"])
    return steps[position(steps, needle)]


def test_the_install_check_leaves_out_what_testpypi_classified() -> None:
    """And only the install check: the wait before it holds the index to
    every file this tag built, the excluded included."""
    install = pypi_step("dist_manifest.py /tmp/manifest --classification")
    assert install["env"] == {"EXCLUDED": "${{ needs.testpypi.outputs.excluded }}"}
    # Quoted, so an empty output reaches the script as one empty argument and
    # is refused there, rather than vanishing from the command line.
    assert 'dist_manifest.py /tmp/manifest --classification "$EXCLUDED"' in str(
        install["run"]
    )
    wait = pypi_step("await_index.py --manifest")
    assert "--classification" not in str(wait["run"])
    assert "EXCLUDED" not in str(wait["run"])


def test_pypi_keeps_a_version_this_tag_publishes_that_testpypi_saw_excluded(
    tmp_path: Path,
) -> None:
    """`testpypi` classifies against what PyPI served before this tag's upload,
    so the `pypi` job reads a classification one publication old: its own. The
    version this tag publishes is told apart from the excluded one by `dist/`,
    which `pypi` must still hold whole after choosing what to upload. This is
    `pytest-digline-v0.4.0`'s case: the classification excluded the served
    0.3.1, and the tag publishes 0.4.0. The `pypi` job's own selection and
    install lines are run, in order, against an index that serves what PyPI
    served before the upload."""
    dist = tmp_path / "dist"
    dist.mkdir()
    for stem in ("digline-0.34.0", "digline_mcp-0.6.2", "pytest_digline-0.4.0"):
        (dist / f"{stem}-py3-none-any.whl").write_bytes(b"")
        (dist / f"{stem}.tar.gz").write_bytes(b"")
    (tmp_path / ".github").symlink_to(ROOT / ".github")
    served = {
        f"/pypi/{n}/{v}/json": (200, b"{}")
        for n, v in (
            ("digline", "0.34.0"),
            ("digline-mcp", "0.6.2"),
            ("pytest-digline", "0.3.1"),
        )
    }
    steps = cast("list[dict[str, object]]", jobs()["pypi"]["steps"])
    (select,) = [s for s in steps if s.get("id") == "select"]
    (install,) = [
        line.strip()
        for line in str(
            pypi_step("dist_manifest.py /tmp/manifest --classification")["run"]
        ).splitlines()
        if line.strip().startswith("python .github/dist_manifest.py")
    ]
    install = install.replace("/tmp/manifest", str(tmp_path / "manifest"))
    with index(served) as url:
        chosen = subprocess.run(
            [
                "bash",
                "--noprofile",
                "--norc",
                "-e",
                "-o",
                "pipefail",
                "-c",
                str(select["run"]),
            ],
            cwd=tmp_path,
            env={**os.environ, "INDEX": url, "GITHUB_OUTPUT": str(tmp_path / "out")},
            capture_output=True,
            text=True,
            check=False,
        )
    assert chosen.returncode == 0, chosen.stderr
    assert sorted(p.name for p in (tmp_path / "to-publish").iterdir()) == [
        "pytest_digline-0.4.0-py3-none-any.whl",
        "pytest_digline-0.4.0.tar.gz",
    ]
    done = subprocess.run(
        ["bash", "--noprofile", "--norc", "-e", "-o", "pipefail", "-c", install],
        cwd=tmp_path,
        env={
            **os.environ,
            "EXCLUDED": "classified digline-mcp==0.6.2 pytest-digline==0.3.1",
        },
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    pins = (tmp_path / "manifest" / "pins.txt").read_text(encoding="utf-8")
    assert pins.splitlines() == ["digline==0.34.0", "pytest-digline==0.4.0"]
    assert (
        "kept pytest-digline 0.4.0: the classification excluded the served 0.3.1"
        in done.stdout
    )
    assert "left out digline-mcp 0.6.2" in done.stdout


def test_a_conflict_between_the_pins_is_not_told_to_re_run() -> None:
    """A conflict between declared requirements is the same on every read, so
    the step stops at the first one and says a re-run gives the same red. The
    advice to re-run stays where it can work: a version not yet served."""
    run = str(pypi_step("dist_manifest.py /tmp/manifest --classification")["run"])
    conflict = run.index("ResolutionImpossible")
    stop = run.index("exit 1", conflict)
    branch = run[conflict:stop]
    assert "re-run gives the same red" in branch
    assert "re-run this job" not in branch
    assert "re-run this job" in run[stop:]


# --- the testpypi install: pinned, less the same exclusion, said -----------------


def test_excluded_names_the_served_versions_whose_cap_stops_below_the_core(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The same classification the check makes, without installing anything:
    `served` and `admits`, asked of every plugin in `dist/`. What the install
    step before the check leaves out, so the two cannot disagree on a rule."""
    for wheel in (
        "digline-0.34.0-py3-none-any.whl",
        "digline_anthropic-0.6.1-py3-none-any.whl",
        "digline_mcp-0.6.2-py3-none-any.whl",
        "pytest_digline-0.3.1-py3-none-any.whl",
    ):
        (tmp_path / wheel).write_bytes(b"")
    ranges = {
        "digline-anthropic": script.Served("digline-anthropic", "0.6.1", ">=0.17.0"),
        "digline-mcp": script.Served("digline-mcp", "0.6.2", "<0.34,>=0.32.0"),
        "pytest-digline": script.Served("pytest-digline", "0.3.1", "<0.34,>=0.32.0"),
    }
    monkeypatch.setattr(script, "served", ranges.get)
    assert script.excluded(tmp_path) == [
        "digline-mcp==0.6.2",
        "pytest-digline==0.3.1",
    ]


def test_the_testpypi_install_is_pinned_and_leaves_out_the_same_exclusion() -> None:
    """It installed `names.txt`, unversioned, and on v0.34.0 pip went down to
    digline-mcp 0.5.0 in silence: the step proved the core beside a plugin two
    minors old. Now it installs the pins, less what the classification
    excludes, and the manifest script names each one it leaves out."""
    steps = steps_of_testpypi()
    at = position(steps, "gate_summary.py install TestPyPI")
    install = steps[at]
    run = str(install["run"])
    # The same classification the `pypi` job is handed, read from the step that
    # made it, not made again: one reading, in one place.
    assert install["env"] == {"CLASSIFIED": "${{ steps.classified.outputs.excluded }}"}
    assert 'dist_manifest.py /tmp/manifest --classification "$CLASSIFIED"' in run
    assert "plugins_against_core.py" not in run
    assert steps.index(classifying_step()) < at
    assert "-r /tmp/manifest/pins.txt" in run
    assert "names.txt" not in run


def test_the_classification_is_marked_so_an_empty_one_is_never_read_as_none(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`classification` is what the step writes: the marker, then the
    exclusions. With nothing excluded it is the marker alone, which is not the
    empty string GitHub gives for an output no step wrote. (#731)"""
    for wheel in (
        "digline-0.34.0-py3-none-any.whl",
        "digline_mcp-0.6.2-py3-none-any.whl",
        "pytest_digline-0.3.1-py3-none-any.whl",
    ):
        (tmp_path / wheel).write_bytes(b"")
    excluding = {
        "digline-mcp": script.Served("digline-mcp", "0.6.2", "<0.34,>=0.32.0"),
        "pytest-digline": script.Served("pytest-digline", "0.3.1", ">=0.32.0"),
    }
    monkeypatch.setattr(script, "served", excluding.get)
    assert script.classification(tmp_path) == "classified digline-mcp==0.6.2"

    def nothing(name: str) -> None:
        return None

    monkeypatch.setattr(script, "served", nothing)
    assert script.classification(tmp_path) == "classified"


def test_the_producer_and_the_consumer_read_one_marker() -> None:
    spec = importlib.util.spec_from_file_location(
        "dist_manifest", ROOT / ".github" / "dist_manifest.py"
    )
    assert spec and spec.loader
    manifest = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(manifest)
    assert script.CLASSIFIED == manifest.CLASSIFIED == "classified"


# --- owed: the reading release-followup's seventh question judges (#731) ---------


def _workspace(tmp_path: Path, *names: str) -> Path:
    packages = tmp_path / "packages"
    for name in names:
        (packages / name).mkdir(parents=True)
        (packages / name / "pyproject.toml").write_text(
            f'[project]\nname = "{name}"\nversion = "0.1.0"\n', encoding="utf-8"
        )
    return packages


def test_owed_reads_each_workspace_plugin_against_the_newest_core(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Every package under `packages/`, asked of PyPI the way `check` asks:
    `served`, then `admits` for the core and for a core no release carries,
    which the follow-up reads as its control. A plugin PyPI does not serve owes
    nothing and reads `None`."""
    packages = _workspace(tmp_path, "digline-mcp", "pytest-digline", "digline-new")
    ranges = {
        "digline-mcp": script.Served("digline-mcp", "0.6.2", "<0.34,>=0.32.0"),
        "pytest-digline": script.Served("pytest-digline", "0.4.0", "<0.35,>=0.34.0"),
    }
    monkeypatch.setattr(script, "served", ranges.get)
    assert script.owed("0.34.0", packages) == {
        "core": "0.34.0",
        "plugins": {
            "digline-mcp": {
                "version": "0.6.2",
                "requires": "<0.34,>=0.32.0",
                "admits": False,
                "admits_impossible": False,
            },
            "digline-new": None,
            "pytest-digline": {
                "version": "0.4.0",
                "requires": "<0.35,>=0.34.0",
                "admits": True,
                "admits_impossible": False,
            },
        },
    }


def test_owed_writes_unread_for_a_plugin_pypi_never_answered(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The third word, as everywhere in the follow-up: a read that never
    answered is not a plugin that owes nothing."""
    packages = _workspace(tmp_path, "digline-mcp")

    def silent(name: str) -> script.Served | None:
        raise script.NotJudged(f"{name} did not answer")

    monkeypatch.setattr(script, "served", silent)
    assert script.owed("0.34.0", packages)["plugins"] == {"digline-mcp": "unread"}


def test_owed_reads_the_real_workspace_names() -> None:
    """The real tree: the names `owed` would ask PyPI for are the five plugins'
    `[project].name`, read from their `pyproject.toml`, not a list kept here."""
    assert script.workspace_plugins(ROOT / "packages") == [
        "digline-anthropic",
        "digline-bedrock",
        "digline-mcp",
        "digline-openai",
        "pytest-digline",
    ]
