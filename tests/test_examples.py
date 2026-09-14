"""The documented example, executed.

An example that rots is worse than no example: it is the first thing a new user
copies, and the only artifact whose failure they will blame on themselves. So
the quickstart is run here for real, and `docs/api.md` is checked to contain the
same file that runs — the document cannot drift from the code it shows.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import tomllib
from collections.abc import Generator, Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import pytest
from tests._site import nav_lists, require_site_config

from digline.cli import EXIT_OK

ROOT = Path(__file__).resolve().parents[1]
QUICKSTART = ROOT / "examples" / "quickstart"
API_DOC = ROOT / "docs" / "api.md"


def cli(
    root: Path, *args: str, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "digline.cli", *args],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


@pytest.fixture
def quickstart(tmp_path: Path) -> Path:
    """Copied out of the repository so running it writes nothing into ours."""
    workdir = tmp_path / "quickstart"
    shutil.copytree(QUICKSTART, workdir)
    return workdir


def test_the_quickstart_runs(quickstart: Path) -> None:
    done = cli(quickstart, "run", "--suite", "suite.py")
    assert done.returncode == EXIT_OK, done.stderr
    assert done.stdout.strip()


def test_the_quickstart_completes_the_whole_cycle(quickstart: Path) -> None:
    """run -> promote -> compare -> report, exactly as the README claims."""
    assert cli(quickstart, "run", "--suite", "suite.py").returncode == EXIT_OK

    promoted = cli(quickstart, "promote", "--suite", "suite.py", "--run", "latest")
    assert promoted.returncode == EXIT_OK, promoted.stderr

    compared = cli(quickstart, "compare", "--suite", "suite.py", "--run", "latest")
    assert compared.returncode == EXIT_OK, compared.stderr
    assert "Nothing got worse" in compared.stdout
    # The suspended case is visible in the answer, not silently absent.
    assert "1 case is suspended" in compared.stdout

    out = quickstart / "report.html"
    rendered = cli(
        quickstart,
        "report",
        "--suite",
        "suite.py",
        "--run",
        "latest",
        "--locale",
        "it",
        "--out",
        str(out),
    )
    assert rendered.returncode == EXIT_OK, rendered.stderr
    document = out.read_text(encoding="utf-8")
    assert document.startswith("<!DOCTYPE html>")
    assert "È peggiorato? No" in document
    assert "ticket 412" in document  # the suspension reason reaches the reader


def test_the_quickstart_judges_every_case_with_every_assertion(
    quickstart: Path,
) -> None:
    key = cli(quickstart, "run", "--suite", "suite.py").stdout.strip()
    stored = json.loads(
        (
            quickstart / ".digline" / "northwind" / "runs" / "support" / f"{key}.json"
        ).read_text(encoding="utf-8")
    )
    by_case = {case["case_id"]: case for case in stored["results"]}
    assert set(by_case) == {
        "where-is-my-order",
        "how-do-i-return",
        "is-it-waterproof",
        "refund-status",
    }
    for case_id in ("where-is-my-order", "how-do-i-return", "is-it-waterproof"):
        verdicts = by_case[case_id]["verdicts"]
        assert len(verdicts) == 5
        assert all(v["status"] == "pass" for v in verdicts), case_id
    # The suspended one is recorded, judged by nothing.
    assert by_case["refund-status"]["verdicts"] == []
    assert by_case["refund-status"]["suspended"] is True


def test_the_quickstart_imports_the_application_beside_it(quickstart: Path) -> None:
    """`import app` is the whole point: a suite evaluates something."""
    assert "import app" in (quickstart / "suite.py").read_text(encoding="utf-8")
    assert (quickstart / "app.py").is_file()
    assert cli(quickstart, "run", "--suite", "suite.py").returncode == EXIT_OK


def test_the_documented_example_is_the_one_that_runs() -> None:
    """The anti-rot rule. If the doc drifts from the file, this fails — which is
    the only way a code sample stays true six months later."""
    source = (QUICKSTART / "suite.py").read_text(encoding="utf-8")
    doc = API_DOC.read_text(encoding="utf-8")
    assert source.strip() in doc, (
        "docs/api.md no longer contains examples/quickstart/suite.py verbatim"
    )


def test_the_api_doc_covers_every_public_assertion() -> None:
    """A reference that silently omits a type is a reference that sends the
    reader to read the source, which is where they started.

    Derived from `__all__` rather than from a list written here: a hand-kept
    list has to be remembered, and the failure mode of forgetting it is a
    *passing* test. Anything exported that is an assertion or an aggregate has
    to appear in the document, so the next one cannot be added quietly.
    """
    import digline.core as core

    doc = API_DOC.read_text(encoding="utf-8")
    bases = (core.AssertionBase, core.RunAssertionBase)
    exported = [
        name
        for name in core.__all__
        if isinstance(obj := getattr(core, name), type) and issubclass(obj, bases)
    ]
    # A guard on the guard: if the derivation ever stops finding anything, the
    # loop below would pass over an empty list and prove nothing.
    assert len(exported) >= 12, exported
    for name in (*exported, "Repeated", "combine_samples"):
        assert name in doc, f"{name} is exported but undocumented"


# --------------------------------------------------------------------------- #
# The standalone examples: whole cycle, every build, against the source
# --------------------------------------------------------------------------- #

#: Each is a project that is meant to leave: its own `pyproject.toml`, its own
#: dependency on the *published* package, no reference to this workspace. Run
#: here against the source so a change that breaks one is caught the day it is
#: made, rather than the day somebody copies the directory out.
STANDALONE = (
    "classifier",
    "prompt-first",
    "rag",
    "external-app",
    "langchain4j",
    "langchain",
    "langgraph",
    "llamaindex",
    "quickstart-toml",
    "operator",
)

#: The examples whose application has to be started from **outside** the suite,
#: with the port it listens on. There is exactly one, and the reason is the
#: point of it: a suite that is data cannot import a module, so it cannot start
#: a server the way `external-app/suite.py` does. The application under test is
#: somebody else's process — which is what is true in production anyway.
NEEDS_A_SERVICE = {"quickstart-toml": 8730}


def suite_file(workdir: Path) -> str:
    """Which form this example is written in. The extension is what chooses the
    format (ADR 0007 §6), here as on the command line."""
    return "suite.toml" if (workdir / "suite.toml").is_file() else "suite.py"


@contextmanager
def application(workdir: Path, name: str) -> Generator[None]:
    """Run `stub.py` for as long as the block lasts, if this example needs it."""
    port = NEEDS_A_SERVICE.get(name)
    if port is None:
        yield
        return
    process = subprocess.Popen(  # noqa: S603 - our own stub, in our own tree
        [sys.executable, "stub.py"],
        cwd=workdir,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        for _ in range(100):
            with socket.socket() as probe:
                if probe.connect_ex(("127.0.0.1", port)) == 0:
                    break
            time.sleep(0.05)
        else:  # pragma: no cover - only on a machine that cannot bind
            pytest.fail(f"{name}: stub.py never listened on {port}")
        yield
    finally:
        process.terminate()
        process.wait(timeout=10)


@pytest.fixture(params=STANDALONE)
def standalone(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[Path]:
    """A copy, without its baseline: the cycle has to work from nothing."""
    name = str(request.param)
    workdir = tmp_path / name
    shutil.copytree(ROOT / "examples" / name, workdir)
    shutil.rmtree(workdir / ".digline", ignore_errors=True)
    with application(workdir, name):
        yield workdir


def test_each_example_completes_the_cycle(standalone: Path) -> None:
    """run -> promote -> compare, exactly what its README tells a reader."""
    suite = suite_file(standalone)
    ran = cli(standalone, "run", "--suite", suite)
    assert ran.returncode == EXIT_OK, ran.stderr
    key = ran.stdout.strip()
    assert key

    promoted = cli(standalone, "promote", "--suite", suite, "--run", key)
    assert promoted.returncode == EXIT_OK, promoted.stderr

    compared = cli(standalone, "compare", "--suite", suite, "--run", key)
    assert compared.returncode == EXIT_OK, compared.stderr
    assert "Nothing got worse" in compared.stdout


def test_each_example_renders_its_report(standalone: Path) -> None:
    suite = suite_file(standalone)
    cli(standalone, "run", "--suite", suite)
    cli(standalone, "promote", "--suite", suite, "--run", "latest")
    out = standalone / "fresh.html"
    rendered = cli(
        standalone,
        "report",
        "--suite",
        suite,
        "--run",
        "latest",
        "--locale",
        "en",
        "--out",
        str(out),
    )
    assert rendered.returncode == EXIT_OK, rendered.stderr
    assert out.read_text(encoding="utf-8").startswith("<!DOCTYPE html>")


@pytest.mark.parametrize("name", STANDALONE)
def test_each_example_is_a_project_that_can_leave(name: str) -> None:
    """No workspace, no path dependency, no import from this source tree.

    The promise is `cp -r examples/rag ~/elsewhere && uv sync`. What breaks it
    is a convenience someone adds here, so it is checked here.
    """
    directory = ROOT / "examples" / name
    pyproject = (directory / "pyproject.toml").read_text(encoding="utf-8")

    assert "digline" in pyproject
    assert "workspace" not in pyproject, "a workspace reference does not travel"
    assert "path =" not in pyproject, "a path dependency does not travel"
    assert (directory / "README.md").exists()
    assert (directory / "report.html").exists()
    assert (directory / ".github" / "workflows" / "check.yml").exists()


@pytest.mark.parametrize("name", STANDALONE)
def test_each_readme_opens_with_the_question_it_answers(name: str) -> None:
    """The reader is looking for their own situation, not for a product name.

    First person, because that is what makes it findable: somebody arrives with
    "I have a RAG and I don't trust it", not with "expense triage evaluation".
    Not every one ends in a question mark — "I'm writing a prompt and have no
    application yet" is a predicament, and predicaments are why people open
    an examples directory.
    """
    first = (
        (ROOT / "examples" / name / "README.md")
        .read_text(encoding="utf-8")
        .splitlines()[0]
    )
    assert first.startswith("# ")
    assert first.split()[1] in ("I", "I'm", "My"), first
    assert len(first.split()) >= 6, first


# --------------------------------------------------------------------------- #
# The LangChain path: in process, and free
# --------------------------------------------------------------------------- #

# --------------------------------------------------------------------------- #
# The classifier: the per-class table is the baseline, or it is decoration
# --------------------------------------------------------------------------- #

CLASSIFIER = ROOT / "examples" / "classifier"


def classifier_baseline() -> dict[str, Any]:
    return json.loads(
        (
            CLASSIFIER / ".digline" / "northwind" / "baselines" / "expense-triage.json"
        ).read_text(encoding="utf-8")
    )


def readme_table() -> list[list[str]]:
    """The one table in the classifier's README whose first column is a class.

    Found by its header rather than by position, so inserting a paragraph
    above it does not silently make this test read nothing.
    """
    lines = (CLASSIFIER / "README.md").read_text(encoding="utf-8").splitlines()
    start = next(
        i for i, line in enumerate(lines) if line.startswith("| Class | Cases |")
    )
    rows: list[list[str]] = []
    for line in lines[start + 2 :]:
        if not line.startswith("|"):
            break
        rows.append([cell.strip().strip("`") for cell in line.strip("|").split("|")])
    return rows


def test_the_classifier_readme_table_is_the_promoted_baseline() -> None:
    """A hand-written table beside a committed measurement rots, quietly and in
    the direction that flatters. This is the third act of the example — the two
    red rows are the whole point of it — so every figure in it is held to the
    baseline the repository ships, number for number.
    """
    by_name = {a["assertion"]: a for a in classifier_baseline()["aggregate"]}
    rows = readme_table()
    assert len(rows) == 6, rows  # the whole run, then five classes

    for label, cases, precision, accuracy in rows:
        where = "" if label == "whole run" else f"[group={label}]"
        for measure, written in (("precision", precision), ("accuracy", accuracy)):
            recorded = by_name[measure + where]
            assert f"{recorded['score']:.3f}" == written, f"{measure}{where}"
            assert str(recorded["metadata"]["considered"]) == cases, f"{measure}{where}"


def test_the_classifier_table_covers_every_class_its_cases_declare() -> None:
    """A guard on the guard: a row quietly dropped from the README would leave
    the test above passing over five figures instead of six."""
    cases = json.loads((CLASSIFIER / "cases.json").read_text(encoding="utf-8"))
    declared = {case["group"] for case in cases}
    written = {row[0] for row in readme_table()} - {"whole run"}
    assert written == declared


def test_the_classifier_ships_the_red_rows_it_narrates() -> None:
    """The example is only worth its README if the failure is really there. If
    a change ever makes these green, the third act has to be rewritten rather
    than the assertion relaxed — a demo that cannot fail is fixed decision 3
    broken in the place people copy from.
    """
    by_name = {a["assertion"]: a for a in classifier_baseline()["aggregate"]}
    failing = {name for name, a in by_name.items() if a["status"] == "fail"}
    assert failing == {
        "precision[group=tools]",
        "precision[group=travel]",
        "accuracy[group=tools]",
        "accuracy[group=travel]",
    }
    # And the gate is green anyway, which is the combination the README and the
    # rendered document both have to explain (ADR 0010 §10).
    assert by_name["precision"]["status"] == "pass"
    assert by_name["accuracy"]["status"] == "pass"


LANGCHAIN = ROOT / "examples" / "langchain"


def test_the_langchain_example_runs_with_no_key_anywhere(tmp_path: Path) -> None:
    """The claim its README opens with, checked rather than asserted.

    An example about a framework is only an example if somebody without an
    account can run it, and the way that promise rots is quiet: a provider key
    happens to be exported on the machine where it was last tried, the default
    path silently reaches a real model, and the failure surfaces on a stranger's
    laptop. So the environment is stripped of every key here, and of the switch
    that would ask for one.
    """
    workdir = tmp_path / "langchain"
    shutil.copytree(LANGCHAIN, workdir)
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.endswith("_API_KEY") and k != "DIGLINE_LIVE"
    }
    ran = cli(workdir, "run", "--suite", "suite.py", env=env)
    assert ran.returncode == EXIT_OK, ran.stderr
    assert ran.stdout.strip()


def test_the_langchain_example_states_the_version_it_was_tested_against() -> None:
    """A reader reproduces a run from the version in the README, so it has to be
    the version the project actually resolves. The failure mode of a hand-typed
    one is a reader debugging a difference that is only in the prose."""
    floor = re.search(
        r'"langchain>=([\d.]+),<2"',
        (LANGCHAIN / "pyproject.toml").read_text(encoding="utf-8"),
    )
    assert floor is not None, "examples/langchain no longer pins a langchain floor"
    readme = (LANGCHAIN / "README.md").read_text(encoding="utf-8")
    assert f"langchain {floor.group(1)}" in readme, (
        f"the README does not say it was tested against langchain "
        f"{floor.group(1)}, which is what pyproject.toml resolves"
    )


LANGGRAPH = ROOT / "examples" / "langgraph"


def test_the_langgraph_example_runs_with_no_key_anywhere(tmp_path: Path) -> None:
    """The same promise as the other two framework examples, with one more
    switch to strip.

    `DISPATCH_NAIVE` is the example's own: it puts a careless reader in the
    model's seat so the README can show what the checks catch. Left set in the
    environment it would quietly change what the default path measures, which is
    the same class of escape as a provider key happening to be exported.
    """
    workdir = tmp_path / "langgraph"
    shutil.copytree(LANGGRAPH, workdir)
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.endswith("_API_KEY") and k not in ("DIGLINE_LIVE", "DISPATCH_NAIVE")
    }
    ran = cli(workdir, "run", "--suite", "suite.py", env=env)
    assert ran.returncode == EXIT_OK, ran.stderr
    assert ran.stdout.strip()


@pytest.mark.parametrize("package", ["langgraph", "langchain"])
def test_the_langgraph_example_states_the_versions_it_was_tested_against(
    package: str,
) -> None:
    """A reader reproduces a run from the versions in the README, so they have to
    be the versions the project actually resolves.

    Both of them, because this example depends on both and they moved apart:
    `create_agent` lives in `langchain` while the graph lives in `langgraph`, so
    a reader who has the right one of the two still cannot reproduce the run.
    """
    floor = re.search(
        rf'"{package}>=([\d.]+),<2"',
        (LANGGRAPH / "pyproject.toml").read_text(encoding="utf-8"),
    )
    assert floor is not None, f"examples/langgraph no longer pins a {package} floor"
    readme = (LANGGRAPH / "README.md").read_text(encoding="utf-8")
    assert f"{package} {floor.group(1)}" in readme, (
        f"the README does not say it was tested against {package} "
        f"{floor.group(1)}, which is what pyproject.toml resolves"
    )


#: **All four**, in the order the lookup reads them: first non-empty wins, so
#: the highest-precedence name decides and a pinned subset decides nothing.
#: 0.12.0 pinned two of these and left `LANGSMITH_TRACING_V2` — the first one
#: consulted — free to turn tracing back on. (0.12.1, from the release
#: delta-pass)
TRACING_PINS = (
    "LANGSMITH_TRACING_V2",
    "LANGCHAIN_TRACING_V2",
    "LANGSMITH_TRACING",
    "LANGCHAIN_TRACING",
)


@pytest.mark.parametrize("name", TRACING_PINS)
def test_the_langgraph_example_pins_tracing_off_where_it_runs(name: str) -> None:
    """Fixed decision 5, gated rather than claimed.

    `langsmith` is a hard, non-optional dependency of `langchain-core`. It opens
    no socket with a clean environment — that was measured — but the README says
    this example pins it shut anyway, and a promise about telemetry is the last
    one that should rest on prose.

    **Both places, because they are different runs.** The example's own
    `check.yml` is what a reader gets when they copy the directory out; the
    root `ci.yml` is what runs here, where that file is inert. A pin in one and
    not the other is a pin that holds only where nobody was worried.
    """
    example = (LANGGRAPH / ".github" / "workflows" / "check.yml").read_text(
        encoding="utf-8"
    )
    monorepo = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert f'{name}: "false"' in example, f"{name} is not pinned in the example"
    assert f'{name}: "false"' in monorepo, f"{name} is not pinned in ci.yml"


def test_the_langgraph_baseline_records_the_trajectory_checks() -> None:
    """The example's whole claim, held to its own committed artifact.

    This is the one example that gates on *how* the answer was produced, so a
    baseline carrying only text checks would be the example quietly ceasing to
    be about anything. Named checks rather than a count: a suite that swapped
    `tool_called_with` for a second `contains` would keep the count and lose the
    point.
    """
    baseline = json.loads(
        (
            LANGGRAPH / ".digline" / "northwind" / "baselines" / "dispatch.json"
        ).read_text(encoding="utf-8")
    )
    named = {v["assertion"] for case in baseline["results"] for v in case["verdicts"]}
    assert {"tools_called", "tool_called_with"} <= named, named
    # And the prompt is the thing under test (ADR 0003): the agent reads it from
    # the file the suite declares, so a run that recorded no artifact would mean
    # the policy under test was inlined somewhere nothing diffs.
    assert "prompts/system.txt" in baseline["artifacts"]


LLAMAINDEX = ROOT / "examples" / "llamaindex"


def test_the_llamaindex_example_runs_with_no_key_anywhere(tmp_path: Path) -> None:
    """The same promise as the LangChain example, and the same way it rots: a
    provider key happens to be exported on the machine where it was last tried,
    the default path silently reaches a real model, and the failure surfaces on
    a stranger's laptop.

    Worth its own test rather than a parametrization, because this example fakes
    two things and not one — the model *and* the embedding. An embedding that
    quietly reached a real endpoint would be the subtler of the two escapes.
    """
    workdir = tmp_path / "llamaindex"
    shutil.copytree(LLAMAINDEX, workdir)
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.endswith("_API_KEY") and k != "DIGLINE_LIVE"
    }
    ran = cli(workdir, "run", "--suite", "suite.py", env=env)
    assert ran.returncode == EXIT_OK, ran.stderr
    assert ran.stdout.strip()


def test_the_llamaindex_example_states_the_version_it_was_tested_against() -> None:
    """The LangChain lesson, applied from day one: a reader reproduces a run
    from the version in the README, so it has to be the version the project
    actually resolves. LlamaIndex moves faster than most, which is why the floor
    is written down and gated rather than remembered."""
    floor = re.search(
        r'"llama-index-core>=([\d.]+),<[\d.]+"',
        (LLAMAINDEX / "pyproject.toml").read_text(encoding="utf-8"),
    )
    assert floor is not None, (
        "examples/llamaindex no longer pins a llama-index-core floor"
    )
    readme = (LLAMAINDEX / "README.md").read_text(encoding="utf-8")
    assert f"llama-index-core {floor.group(1)}" in readme, (
        f"the README does not say it was tested against llama-index-core "
        f"{floor.group(1)}, which is what pyproject.toml resolves"
    )


def test_the_llamaindex_example_depends_on_the_core_not_the_meta_package() -> None:
    """`llama-index` pulls the OpenAI LLM and embedding bindings and the reader
    collection. None of them is called here, and one of them would make the
    default path ask for a key — which is the promise the test above defends
    from the other side. The minimal set was measured, not assumed."""
    dependencies = (LLAMAINDEX / "pyproject.toml").read_text(encoding="utf-8")
    assert '"llama-index-core>=' in dependencies
    assert '"llama-index>=' not in dependencies, (
        "the meta-package brings bindings this example does not call, one of "
        "which reaches a provider on import"
    )


def test_the_llamaindex_cases_declare_a_page_that_exists() -> None:
    """Retrieval runs live here, so a case's context is the page that *ought*
    to answer it rather than the one that did. A `source` naming no file would
    make `faithfulness` grade against nothing — which is an error, not a pass,
    but the reason would point at the wrong thing."""
    pages = {f"handbook/{path.stem}" for path in (LLAMAINDEX / "handbook").glob("*.md")}
    assert pages, "examples/llamaindex has no handbook to retrieve from"
    cases = json.loads((LLAMAINDEX / "cases.json").read_text(encoding="utf-8"))
    declared = {str(case["source"]) for case in cases}
    assert declared <= pages, f"cases name pages that do not exist: {declared - pages}"


def test_the_langchain_suite_declares_both_prompt_files() -> None:
    """The prompt is the thing under test (ADR 0003), and this chain builds its
    messages from two files. One of them declared and the other not would leave
    a run that records half of what produced it."""
    baseline = json.loads(
        (
            LANGCHAIN / ".digline" / "riverbend" / "baselines" / "handbook.json"
        ).read_text(encoding="utf-8")
    )
    assert set(baseline["artifacts"]) == {
        "prompts/extract.txt",
        "prompts/request.txt",
    }


# --------------------------------------------------------------------------- #
# The Java path (ADR 0005 §8)
# --------------------------------------------------------------------------- #

LANGCHAIN4J = ROOT / "examples" / "langchain4j"


def test_the_java_example_records_the_model_that_answered() -> None:
    """The point of the example, and of ADR 0005 §8: a service digline cannot
    import still says which model answered, so a run is as complete a document
    as one produced by a plugin."""
    baseline = json.loads(
        (
            LANGCHAIN4J / ".digline" / "northwind" / "baselines" / "support.json"
        ).read_text(encoding="utf-8")
    )
    assert baseline["target_config"]["values"]["provider"] == "openai"
    assert baseline["target_config"]["values"]["model"]
    # And the prompt (ADR 0003). It sits beside the two services rather than
    # inside either, so the suite names the thing under test without naming a
    # framework — and there is one copy for both of them to package.
    assert "prompts/system.txt" in baseline["artifacts"]


def test_the_java_readme_lists_the_configuration_contract() -> None:
    """A reader implements their endpoint from this list, so it cannot drift
    from the set the code enforces — and the failure mode of a hand-kept list
    is a reader whose field is silently refused."""
    from digline.targets import CONTRACT_FIELDS

    readme = (LANGCHAIN4J / "README.md").read_text(encoding="utf-8")
    for field in CONTRACT_FIELDS:
        assert f"`{field}`" in readme, f"{field} is accepted but undocumented"


#: The two services, and the class that exposes the endpoint in each. The pair
#: is the example's whole argument — the framework is not the contract, the
#: endpoint is — so it is only true while both answer the same shape.
JAVA_ENDPOINTS = {
    "app-spring": "EvaluationController.java",
    "app-quarkus": "EvaluationResource.java",
}

#: Every key `stub.py` puts in an answer, which is what a reader takes the
#: contract to be.
CONTRACT_KEYS = ("data", "usage", "cost_usd", "elapsed_ms", "config", "provider")


def endpoint_source(app: str) -> str:
    return (
        LANGCHAIN4J / app / "src/main/java/dev/digline/example" / JAVA_ENDPOINTS[app]
    ).read_text(encoding="utf-8")


@pytest.mark.parametrize("app", sorted(JAVA_ENDPOINTS))
def test_each_java_service_reports_every_field_the_stub_does(app: str) -> None:
    """`stub.py` is what the example actually runs, so it is what a reader
    believes the contract to be. If a service and the stub disagree, one of them
    is lying about the shape — and the suite would not notice, because it only
    ever talks to one of them at a time."""
    source = endpoint_source(app)
    for key in CONTRACT_KEYS:
        assert f'"{key}"' in source, f"{app} does not report {key}"


def test_the_two_java_services_answer_the_same_shape() -> None:
    """Neither service is the reference: they are peers, and the example's claim
    is false the moment they diverge. Nothing else checks this — `mvn verify`
    compiles each in isolation, and the suite runs against the stub."""
    spring, quarkus = endpoint_source("app-spring"), endpoint_source("app-quarkus")
    import re as _re

    def reported(source: str) -> set[str]:
        return set(_re.findall(r'\.put\("([a-z_]+)"', source))

    assert reported(spring) == reported(quarkus), (
        "app-spring and app-quarkus put different keys in their answers: "
        f"{sorted(reported(spring) ^ reported(quarkus))}. One prompt, one "
        "model, one contract — that is what the pair is for"
    )


def test_the_prompt_is_shared_by_both_services_and_owned_by_neither() -> None:
    """One file, packaged by both builds. Two copies would drift, and the suite
    can only name one of them as the thing under test."""
    assert (LANGCHAIN4J / "prompts" / "system.txt").is_file()
    for app in JAVA_ENDPOINTS:
        pom = (LANGCHAIN4J / app / "pom.xml").read_text(encoding="utf-8")
        assert "../prompts" in pom, f"{app} does not package the shared prompt"
        assert not list((LANGCHAIN4J / app).rglob("system.txt")), (
            f"{app} carries its own copy of the prompt"
        )


# --------------------------------------------------------------------------- #
# The operator loop: the alert is the deliverable, so the alert is what is gated
# --------------------------------------------------------------------------- #

OPERATOR = ROOT / "examples" / "operator"

#: Each scenario `fake.py` can be put in, and what the loop must conclude about
#: it: the verdict, how many runs it took, and whether it wakes anybody.
#:
#: This is the example's whole claim, so it is the example's whole test. A loop
#: that classified everything as drift would escalate every week and be ignored
#: by the third; one that classified everything as a draw would be a monitor
#: that never monitors. Both failures are silent, and both are caught here.
SCENARIOS = {
    "steady": ("clean", 1, False),
    "wobble": ("draw", 2, False),
    "drift": ("drift", 3, True),
    "structural": ("structural", 1, True),
}

#: The alerts committed under `examples/operator/alerts/`, each with the cycle
#: it was built from and the decision, where one was recorded.
#:
#: `held` is deliberately the **same cycle** as `drift`: one document where no
#: policy ran and one where a declared clause held what the classification
#: would have escalated. Rebuilding both from one cycle is what makes the pair
#: a comparison rather than two anecdotes — every number in them is identical
#: and only the decision differs.
CAPTURED: dict[str, tuple[str, str | None]] = {
    "draw": ("draw-cycle.json", None),
    "drift": ("drift-cycle.json", None),
    "held": ("drift-cycle.json", "held-decision.json"),
}


def operator_script(
    workdir: Path, script: str, *args: str
) -> subprocess.CompletedProcess[str]:
    """One of the example's own scripts, run the way its workflow runs it."""
    return subprocess.run(
        [sys.executable, script, *args],
        cwd=workdir,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.fixture
def operator(tmp_path: Path) -> Path:
    """A copy with its baseline kept: the loop compares against an approved
    reference, and a cycle with nothing to compare against is not a cycle."""
    workdir = tmp_path / "operator"
    shutil.copytree(OPERATOR, workdir)
    shutil.rmtree(workdir / ".digline" / "northwind" / "runs", ignore_errors=True)
    return workdir


@pytest.mark.parametrize("scenario", sorted(SCENARIOS))
def test_the_operator_classifies_each_scenario(operator: Path, scenario: str) -> None:
    """The four events `AGENTS.md` separates, told apart by the loop.

    Structural is the one worth reading twice: it escalates on **one** run.
    Several cases flipping together is investigated and never retried, because
    retrying destroys the evidence either way — so a loop that re-ran it would
    be breaking §4 while looking diligent.
    """
    want_verdict, want_runs, want_escalate = SCENARIOS[scenario]
    done = subprocess.run(
        [sys.executable, "loop.py", "--config", "operator.toml", "--out", "cycle.json"],
        cwd=operator,
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "OPERATOR_SCENARIO": scenario},
    )
    assert done.returncode == EXIT_OK, done.stderr

    cycle = json.loads((operator / "cycle.json").read_text(encoding="utf-8"))
    assert cycle["verdict"] == want_verdict, done.stdout
    assert len(cycle["runs"]) == want_runs, (
        f"{scenario} took {len(cycle['runs'])} run(s), not {want_runs}: the "
        "stopping rule is declared in operator.toml and the loop has to obey it"
    )
    assert cycle["escalate"] is want_escalate
    assert cycle["budget"]["spent"] <= cycle["budget"]["max_target_calls"]
    # Against the real server, every scenario: the wall is a fact about the
    # surface and not about how the system under test is doing this week.
    assert cycle["probe"] == {
        "wall": "intact",
        "negative": "refused",
        "positive": True,
        "rolled_back": False,
        # The second wall, reported for what it is on a checkout rather than
        # dressed up: `operator.toml` is writable here, which measured against
        # this identity is a latch and not a constraint. A probe that called
        # that a collapse would cry wolf on every machine it ran on.
        "policy_wall": "unenforced",
        # The fourth check: the digest this cycle reports is the digest of the
        # policy on disk, so it was ruled by the policy it names.
        "digest_matches": True,
    }, cycle["probe"]


@pytest.mark.parametrize("name", CAPTURED)
def test_the_captured_alert_is_what_the_dossier_writes_today(
    operator: Path, name: str
) -> None:
    """The README tells a story about an alert this loop produced. A captured
    document beside a script that has since moved on is a screenshot, and
    screenshots rot in the direction that flatters — so the committed alert is
    rebuilt from the committed cycle, byte for byte, on every build.

    `dossier.py` is pure for exactly this reason: a cycle in, a document out,
    no clock and no filesystem of its own. Rebuilding it needs no run, no
    target and no key.
    """
    source, decision = CAPTURED[name]
    built = operator / "rebuilt.md"
    args = ["--cycle", f"alerts/{source}"]
    if decision is not None:
        args += ["--decision", f"alerts/{decision}"]
    done = operator_script(operator, "dossier.py", *args, "--out", str(built))
    assert done.returncode == EXIT_OK, done.stderr
    assert built.read_text(encoding="utf-8") == (
        OPERATOR / "alerts" / f"{name}.md"
    ).read_text(encoding="utf-8"), (
        f"examples/operator/alerts/{name}.md is not what dossier.py writes "
        f"from alerts/{source} any more. Rebuild it and commit the "
        "new one — the alert is the example's deliverable, not an illustration"
    )


@pytest.mark.parametrize("name", CAPTURED)
def test_every_captured_alert_says_the_judgment_layer_did_not_run(name: str) -> None:
    """Layer 3 is the only one a model writes, and no key was configured when
    these were captured. The heading is still there, saying so: an absence is
    stated, never faked — a document that quietly dropped the section would
    read as though a judgment had been made."""
    text = (OPERATOR / "alerts" / f"{name}.md").read_text(encoding="utf-8")
    assert "## 3. The judgment" in text
    assert "**This layer was not run.**" in text


def captured(name: str) -> dict[str, Any]:
    return cast(
        "dict[str, Any]",
        json.loads((OPERATOR / "alerts" / name).read_text(encoding="utf-8")),
    )


def test_the_captured_alerts_cover_both_answers() -> None:
    """One that wakes somebody and one that deliberately does not.

    The second is the half that is easy to leave out and is worth more: a loop
    that only ever escalates has not demonstrated absorbing anything, which is
    the job it exists to do.
    """
    assert captured("draw-cycle.json")["escalate"] is False
    assert captured("drift-cycle.json")["escalate"] is True


def test_the_held_alert_is_the_drift_a_declared_policy_absorbed() -> None:
    """The pair that is the whole point of the seat.

    The classification wakes somebody and the decision does not, from the
    **same cycle** — so the two committed documents differ in nothing except
    what a declared policy did about an identical measurement. And the hold
    cites its clause, because a reason that cites no clause is an opinion.
    """
    decision = captured("held-decision.json")
    assert decision["verdict_escalates"] is True, (
        "the held alert has to be built from a cycle the classification would "
        "have escalated, or it demonstrates nothing about the policy"
    )
    assert decision["escalate"] is False
    assert decision["clause"], "a hold with no clause is an opinion"
    assert decision["floor"] is None
    # The same cycle, so the comparison between the two documents is exact.
    assert CAPTURED["held"][0] == CAPTURED["drift"][0]


def test_the_operator_config_agrees_with_the_workflow_about_the_cadence() -> None:
    """`operator.toml` states the cadence and GitHub reads it from the YAML, so
    the file's most editable field is the one that could silently do nothing.
    `loop.py` refuses to start when they disagree; this is that refusal, checked
    against the pair the example actually ships."""
    config = tomllib.loads((OPERATOR / "operator.toml").read_text(encoding="utf-8"))
    cadence = config["operator"]["cadence"]
    workflow = (OPERATOR / ".github" / "workflows" / "operator.yml").read_text(
        encoding="utf-8"
    )
    assert re.search(rf'-\s*cron:\s*"{re.escape(str(cadence))}"', workflow), (
        f"operator.toml declares the cadence {cadence!r} and operator.yml does "
        "not schedule it. loop.py fails loudly on this at run time; it is here "
        "so it fails in a pull request instead"
    )


def test_the_operator_cannot_reach_promote() -> None:
    """`AGENTS.md` §1 as a property of the assembly rather than a rule in it.

    The MCP surface has no `promote` tool by construction, and the loop shells
    out to the CLI, where the command does exist. So the absence has to hold
    here too — and the way it stops holding is somebody adding a helpful line
    to a workflow at two in the morning.
    """
    # The word itself is all over these files, and has to be: they explain why
    # they do not do it. What is looked for is the *call* — `promote` as a
    # quoted argument, which is the only shape it could reach the CLI in.
    called = re.compile(r"""['"]promote['"]""")
    # One exception, and it is the opposite of a call: the probe names the tool
    # to the MCP server expecting to be told there is no such thing. It may be
    # written exactly once, as that constant — and the constant may never reach
    # `digline(...)`, the helper that shells out to the CLI, where it exists.
    probe = 'ABSENT_TOOL = "promote"'
    # Every module in the directory, and the list grows with the directory:
    # the gate is about what the assembly can reach, so a file added to it
    # without being added here would be the one place the absence stopped
    # being checked — which is exactly how it would stop being true.
    for name in (
        "loop.py",
        "dossier.py",
        "judgment.py",
        "decide.py",
        "policy.py",
        "journal.py",
        "answer.py",
    ):
        source = (OPERATOR / name).read_text(encoding="utf-8")
        if name == "loop.py":
            assert source.count(probe) == 1, "the probe names the tool once"
            source = source.replace(probe, "")
            assert not re.search(r"digline\([^)]*ABSENT_TOOL", source), (
                "the probe's tool name reaches the CLI: the probe asks the MCP "
                "surface, where `promote` is absent, and never the CLI"
            )
        assert not called.search(source), (
            f"examples/operator/{name} passes 'promote' to something: a "
            "baseline is an approved reference and the approval is a person's"
        )
    for workflow in sorted((OPERATOR / ".github" / "workflows").glob("*.yml")):
        assert "digline promote" not in workflow.read_text(encoding="utf-8"), workflow


def operator_loop() -> ModuleType:
    """`loop.py`, imported, for the probe's two outcomes a real run never shows.

    Through the same loader every other module here goes through, and that is
    the whole of the change: `loop.py` imports `policy` by name now, so a
    module executed from a path with nothing beside it on `sys.path` resolves
    its own siblings nowhere. That is a `ModuleNotFoundError` in a test and
    never in the directory a fork actually runs it from — the kind of failure
    that says more about the loader than about the code under it.
    """
    return operator_module("loop")


#: A deployment whose surface grew the tool it must not have — the thing the
#: probe exists to catch. It lives here, in a test, and never in `digline-mcp`:
#: the server's `promote` is absent, and a disabled one added "to test it" would
#: be the very policy the absence replaces.
STAND_IN = """
import sys
from pathlib import Path

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

mode, root = sys.argv[1], Path(sys.argv[2])
baselines = root / ".digline" / "northwind" / "baselines"


def promote() -> str:
    if mode == "refusing":
        raise ToolError("a baseline is approved by a person")
    (baselines / "support.json").write_text("{}", encoding="utf-8")
    (baselines / "smuggled.json").write_text("{}", encoding="utf-8")
    return "promoted"


server = MCPServer(name="stand-in")
server.add_tool(promote, name="promote")
server.run(transport="stdio")
"""


@pytest.mark.parametrize("mode", ["allowing", "refusing"])
def test_the_probe_calls_a_wall_that_answered_collapsed(
    operator: Path, mode: str
) -> None:
    """Any answer but "unknown tool" is a collapse — a refusal included.

    On this surface the wall *is* the absence. A `promote` that says no is a
    policy where the design put nothing to ask, and a policy is what a future
    release can relax. So the probe fails toward a false alarm and never toward
    a false all-clear: a server that learnt to word "unknown" differently would
    read as collapsed, loudly, rather than as intact.
    """
    loop = operator_loop()
    before = {
        path.name: path.read_bytes()
        for path in (operator / ".digline" / "northwind" / "baselines").iterdir()
    }
    (operator / "stand_in.py").write_text(STAND_IN, encoding="utf-8")
    server = (sys.executable, str(operator / "stand_in.py"), mode, str(operator))

    found = loop.probe(operator, operator / "cycle.json", server)

    assert found.wall == "collapsed"
    assert found.negative == "reached"
    assert found.rolled_back is (mode == "allowing")
    # Before the comparison could read it: the approved reference is the one a
    # person signed, byte for byte, and nothing the collapse wrote survives.
    after = {
        path.name: path.read_bytes()
        for path in (operator / ".digline" / "northwind" / "baselines").iterdir()
    }
    assert after == before


def test_the_probe_is_inconclusive_when_nothing_answers(operator: Path) -> None:
    """No server, no answer — and no answer is not a refusal. A probe that read
    silence as a wall standing would stay green the day its instrument died."""
    loop = operator_loop()
    silent = (sys.executable, "-c", "raise SystemExit(0)")

    found = loop.probe(operator, operator / "cycle.json", silent)

    assert (found.negative, found.positive, found.wall) == (
        "unobserved",
        True,
        "inconclusive",
    )


def test_the_probe_is_inconclusive_when_the_positive_fails(operator: Path) -> None:
    """Refused, and unable to write its own cycle file: the refusal proves
    nothing. An identity that is refused everything is refused `promote` too,
    and that is the instrument down, not the wall standing."""
    loop = operator_loop()
    unwritable = operator / "cycle.json"
    unwritable.mkdir()

    found = loop.probe(operator, unwritable, loop.surface(operator))

    assert (found.negative, found.positive, found.wall) == (
        "refused",
        False,
        "inconclusive",
    )


def operator_module(name: str) -> ModuleType:
    """One of the example's own modules, imported from its directory.

    The directory goes on `sys.path` because these modules import each other by
    name — `decide.py` reads `policy` and `journal` — which is exactly how they
    resolve when a fork runs them from inside the directory.
    """
    if str(OPERATOR) not in sys.path:
        sys.path.insert(0, str(OPERATOR))
    spec = importlib.util.spec_from_file_location(name, OPERATOR / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def a_cycle(
    verdict: str,
    *,
    escalate: bool,
    regressed: Sequence[tuple[str, str]] = (),
    run_facts: Sequence[dict[str, Any]] = (),
    digest: str = "abc123",
    exit_code: int = 1,
) -> dict[str, Any]:
    """The smallest cycle the seat will read. Hand-built on purpose: the floors
    are about cycles a real scenario cannot produce here — this suite declares
    no canary and its target never fails — and a floor that could only be
    reached by a scenario nobody can run is a floor nothing tests."""
    checks = [
        {
            "about": "check",
            "kind": "regressed",
            "case_id": case,
            "assertion": assertion,
            "assertion_id": f"id-{assertion}",
        }
        for case, assertion in regressed
    ]
    return {
        "cycle_format": 4,
        "tenant": "northwind",
        "suite": "suite.py",
        "verdict": verdict,
        "escalate": escalate,
        "reproduced": [list(pair) for pair in regressed],
        "policy": {"name": "northwind-weekly", "digest": digest},
        "runs": [
            {
                "key": "2026-09-14T00-00-00-000000-00-00-deadbeef",
                "seed": 0,
                "exit_code": exit_code,
                "spend": "",
                "explain": {"facts": [*run_facts, *checks]},
            }
        ],
    }


def test_the_policy_digest_is_taken_over_the_parsed_table() -> None:
    """Reflowing a comment must not move an identity; changing a number must.

    Both halves, because only the pair says what the digest is *of*. A digest
    over the file's bytes would churn on every edit that changed nothing, and a
    cycle would report a policy change nobody made.
    """
    policy = operator_module("policy")
    text = (OPERATOR / "operator.toml").read_text(encoding="utf-8")
    table = cast("dict[str, Any]", tomllib.loads(text)["policy"])
    first = cast("str", policy.digest_of(table))

    commented = tomllib.loads(text + "\n# a comment changes nothing\n")["policy"]
    assert policy.digest_of(commented) == first

    moved = cast("dict[str, Any]", json.loads(json.dumps(table)))
    moved["hold"][0]["max_cycles"] = 99
    assert policy.digest_of(moved) != first, (
        "a clause that allows a different number of cycles is a different "
        "policy, and a cycle has to be able to say which one ruled it"
    )


@pytest.mark.parametrize("key", ["vars", "output", "reason", "artifact"])
def test_a_clause_may_not_name_the_contents_of_a_case(key: str) -> None:
    """Identifiers yes, contents no — refused at load, not at use.

    Whatever a clause may name is written into the decision journal on every
    cycle, so the boundary has to hold on the file a person writes rather than
    on the code that reads it.
    """
    policy = operator_module("policy")
    document = {
        "policy": {
            "name": "p",
            "hold": [{"name": "c", "because": "b", "case": "x", key: "v"}],
        }
    }
    with pytest.raises(cast("type[Exception]", policy.PolicyError)) as caught:
        policy.load_policy(document)
    assert key in str(caught.value)
    assert "identifiers" in str(caught.value), caught.value


@pytest.mark.parametrize(
    "key", ["max_reruns", "structural_flip_cases", "max_target_calls"]
)
def test_a_clause_may_not_reach_the_stopping_rule(key: str) -> None:
    """The policy narrows and never widens, so the keys that would widen it are
    refused by name rather than quietly ignored."""
    policy = operator_module("policy")
    document = {
        "policy": {
            "name": "p",
            "hold": [{"name": "c", "because": "b", "case": "x", key: 9}],
        }
    }
    with pytest.raises(cast("type[Exception]", policy.PolicyError)) as caught:
        policy.load_policy(document)
    assert "narrow" in str(caught.value), caught.value


def test_a_cycle_with_no_policy_escalates_exactly_as_the_verdict_says() -> None:
    """The seat added a decision; it did not move the classifier. A fork with
    no `[policy]` table behaves as the loop behaved before any of this."""
    decide = operator_module("decide")
    for verdict, escalate in (("drift", True), ("draw", False)):
        found = cast(
            "dict[str, Any]",
            decide.decide(
                a_cycle(verdict, escalate=escalate, regressed=[("c", "llm_rubric")]),
                None,
                on_disk="",
                records=[],
                now=datetime(2026, 9, 14, 12, 0, tzinfo=UTC),
            ),
        )
        assert found["escalate"] is escalate
        assert found["clause"] is None


@pytest.mark.parametrize(
    ("name", "cycle_kwargs", "floor"),
    [
        (
            "a canary that moved",
            {"run_facts": [{"about": "run", "kind": "canary", "state": True}]},
            "canary",
        ),
        ("a run that could not be judged", {"exit_code": 2}, "unjudged"),
    ],
)
def test_no_clause_may_lower_a_floor(
    name: str, cycle_kwargs: dict[str, Any], floor: str
) -> None:
    """The two floors a cycle can carry, each refusing a clause that covers
    everything else about it.

    The clause below matches the regression exactly, so the only reason the
    cycle escalates is the floor — which is what makes this a test of the floor
    rather than of the matching.
    """
    decide = operator_module("decide")
    policy = operator_module("policy")
    verdict = "system-error" if floor == "unjudged" else "drift"
    loaded = policy.load_policy(
        {
            "policy": {
                "name": "p",
                "hold": [{"name": "covers-it", "because": "b", "case": "c"}],
            }
        }
    )
    found = cast(
        "dict[str, Any]",
        decide.decide(
            a_cycle(
                verdict,
                escalate=True,
                regressed=[("c", "llm_rubric")],
                digest=loaded.digest,
                **cycle_kwargs,
            ),
            loaded,
            on_disk=loaded.digest,
            records=[],
            now=datetime(2026, 9, 14, 12, 0, tzinfo=UTC),
        ),
    )
    assert found["escalate"] is True, f"{name} was held, and it may never be"
    assert found["floor"] == floor
    assert found["clause"] is None


def test_a_policy_that_moved_under_the_cycle_cannot_hold_it() -> None:
    """The fourth check, from the decision's side.

    A hold taken under a policy nobody can produce is not a hold, so a digest
    that disagrees with the file on disk refuses before any clause is read.
    """
    decide = operator_module("decide")
    policy = operator_module("policy")
    loaded = policy.load_policy(
        {
            "policy": {
                "name": "p",
                "hold": [{"name": "covers-it", "because": "b", "case": "c"}],
            }
        }
    )
    found = cast(
        "dict[str, Any]",
        decide.decide(
            a_cycle(
                "drift", escalate=True, regressed=[("c", "llm_rubric")], digest="x"
            ),
            loaded,
            on_disk="a-different-digest",
            records=[],
            now=datetime(2026, 9, 14, 12, 0, tzinfo=UTC),
        ),
    )
    assert found["escalate"] is True
    assert found["floor"] == "policy-moved"


def test_a_hold_is_one_clauses_responsibility() -> None:
    """A clause naming one case does not absorb a run in which three flipped.

    The strict reading, and the one that keeps a narrow clause from covering a
    regression nobody looked at. It is why the `structural` scenario still
    wakes somebody with the shipped policy in force.
    """
    decide = operator_module("decide")
    policy = operator_module("policy")
    loaded = policy.load_policy(
        {
            "policy": {
                "name": "p",
                "hold": [{"name": "one-case", "because": "b", "case": "a"}],
            }
        }
    )
    found = cast(
        "dict[str, Any]",
        decide.decide(
            a_cycle(
                "structural",
                escalate=True,
                regressed=[("a", "llm_rubric"), ("b", "llm_rubric")],
                digest=loaded.digest,
            ),
            loaded,
            on_disk=loaded.digest,
            records=[],
            now=datetime(2026, 9, 14, 12, 0, tzinfo=UTC),
        ),
    )
    assert found["escalate"] is True
    assert found["clause"] is None


@pytest.mark.parametrize(("max_cycles", "holds"), [(2, False), (None, True)])
def test_an_unknown_streak_is_not_a_streak_of_zero(
    max_cycles: int | None, holds: bool
) -> None:
    """A journal that could not be restored is not an empty history.

    Read as zero, a clause with `max_cycles` would hold every cycle on a hosted
    runner whose journal is lost, which is the stopping rule switched off in
    silence. A clause that counts nothing needs no streak and still holds —
    the case that proves the refusal is scoped to counting, not to the policy.
    """
    decide = operator_module("decide")
    policy = operator_module("policy")
    clause: dict[str, Any] = {"name": "counts", "because": "b", "case": "c"}
    if max_cycles is not None:
        clause["max_cycles"] = max_cycles
    loaded = policy.load_policy({"policy": {"name": "p", "hold": [clause]}})
    cycle = a_cycle(
        "drift", escalate=True, regressed=[("c", "llm_rubric")], digest=loaded.digest
    )

    def decided(*, streak_known: bool) -> dict[str, Any]:
        return cast(
            "dict[str, Any]",
            decide.decide(
                cycle,
                loaded,
                on_disk=loaded.digest,
                records=[],
                now=datetime(2026, 9, 14, 12, 0, tzinfo=UTC),
                streak_known=streak_known,
            ),
        )

    unknown = decided(streak_known=False)
    assert unknown["escalate"] is not holds
    if not holds:
        assert unknown["clause"] is None
        assert "streak is unknown" in unknown["reason"], unknown["reason"]
    # The same cycle with a known, empty journal holds: the pair is what shows
    # the unknown streak, and nothing else, decided it.
    assert decided(streak_known=True)["escalate"] is False


def test_the_operator_workflow_carries_the_journal_between_cycles() -> None:
    """Upload, restore, and say so when the restore fails.

    The ignored journal does not survive a hosted job. A workflow that forgot
    either half would count every streak from zero, and one that swallowed a
    failed restore (`|| echo`) would do the same while printing that it had
    noticed.
    """
    workflow = (OPERATOR / ".github" / "workflows" / "operator.yml").read_text(
        encoding="utf-8"
    )
    assert workflow.count("name: decision-journal") == 1, "the upload"
    assert "--name decision-journal" in workflow, "the restore"
    assert "--streak-unknown" in workflow
    assert "|| echo" not in workflow


def test_the_operator_mcp_config_points_at_this_example() -> None:
    """The interactive path: somebody opens a coding agent in this directory
    and the operator's surface is already there. A server pointed one directory
    up would read another project's `.digline/`, which is the perimeter
    mistake the tenant exists to prevent."""
    config = json.loads((OPERATOR / ".mcp.json").read_text(encoding="utf-8"))
    servers = cast("dict[str, Any]", config)["mcpServers"]
    assert list(servers) == ["digline-northwind"], servers
    server = cast("dict[str, Any]", servers["digline-northwind"])
    # `uv run` and not the bare script: the server is a dependency of *this*
    # project, so it lives in this directory's environment and not on anybody's
    # PATH. `--tenant` verifies and never overrides — the suite decides.
    assert server["command"] == "uv"
    assert server["args"] == [
        "run",
        "digline-mcp",
        "--root",
        ".",
        "--tenant",
        "northwind",
    ]


@pytest.mark.parametrize("name", STANDALONE)
def test_no_example_workflow_promotes_before_it_compares(name: str) -> None:
    """A job that promotes and then compares is comparing a run with itself and
    passes whatever happened. Every example shipped that shape once, and it hid
    four baselines that had stopped being readable at all."""
    workflow = (
        ROOT / "examples" / name / ".github" / "workflows" / "check.yml"
    ).read_text(encoding="utf-8")
    assert "digline compare" in workflow
    assert "digline promote" not in workflow, (
        "promoting in CI makes the comparison vacuous: the baseline is a human "
        "decision, committed by whoever read the report"
    )


@pytest.mark.parametrize("name", STANDALONE)
def test_no_example_readme_carries_a_markdown_link(name: str) -> None:
    """These files are the site's example pages, built by mkdocs in **strict
    mode**, so a link that resolves on GitHub aborts the build.

    Every relative form fails there and passes here: a path into the example's
    own directory (`report.html`, a `.java` file) is not copied into the docs
    tree, `../../docs/guide.md` escapes it, and `../langchain4j/` is not a page
    name. The whole release goes out, PyPI takes the version, and then the last
    job fails and the site keeps describing the version before it.

    That happened on v0.3.0. The four examples that predate it carry no links at
    all, which is why nobody had met the rule — so it is written down here
    rather than learned again. Backtick the path: a reader is already in the
    directory.
    """
    text = (ROOT / "examples" / name / "README.md").read_text(encoding="utf-8")
    links = re.findall(r"\[[^\]]+\]\(([^)]+)\)", text)
    relative = [t for t in links if not t.startswith(("http://", "https://", "#"))]
    assert not relative, (
        f"examples/{name}/README.md links to {relative}, which mkdocs --strict "
        "refuses when it renders this file as a site page. Use a backticked "
        "path, or an absolute https:// URL"
    )


# --------------------------------------------------------------------------- #
# The other repository: digline.dev renders these examples as pages
# --------------------------------------------------------------------------- #


def examples_with_a_readme() -> list[str]:
    """The directories `sync-docs.sh` turns into pages: one per README.

    `quickstart` has none — it is the guide's first chapter rather than a case
    of its own — so the glob excludes it exactly as the script's does.
    """
    return sorted(p.parent.name for p in (ROOT / "examples").glob("*/README.md"))


def test_the_readme_glob_still_finds_the_examples() -> None:
    """A guard on the guard: an empty list would make the check below pass
    over nothing and prove nothing."""
    found = examples_with_a_readme()
    assert len(found) >= 5, found
    assert "quickstart" not in found, "quickstart has no README and is not a page"


def test_every_example_has_a_page_in_the_site_nav() -> None:
    """An example added here needs one line in another repository.

    `sync-docs.sh` copies `examples/<name>/README.md` to
    `docs/product/examples/<name>.md`, and mkdocs builds `--strict`: a page that
    is in the docs tree and not in `nav` is a warning, and a warning is a failed
    build. That build runs after PyPI, so the first time anyone sees the mistake
    the version is already spent — which is exactly what happened to
    `langchain4j` on v0.3.0.

    The `docs` job in `ci.yml` catches it too, by running the real build. This
    exists beside it because it names the example and the line to add, in a
    second, instead of leaving a reader to read mkdocs' warning about a path
    they did not write.

    Read with a regex rather than a YAML parser, like `test_releasing.py` reads
    the workflow: this repository has one runtime dependency and a test is not
    where a second one arrives.
    """
    config = require_site_config()
    nav = config.read_text(encoding="utf-8")
    missing = [
        name
        for name in examples_with_a_readme()
        if not nav_lists(nav, f"product/examples/{name}.md")
    ]
    assert not missing, (
        f"examples/{missing[0]}/README.md becomes the page "
        f"product/examples/{missing[0]}.md, which {config} does not list in "
        f"its nav — so `mkdocs build --strict` fails and the site is not "
        f"rebuilt. Add, under `- Examples:`:\n"
        f"          - <a label for the reader's situation>: "
        f"product/examples/{missing[0]}.md\n"
        f"Missing: {', '.join(missing)}. "
        "If that path is a checkout of your own, it may simply be behind "
        "origin — the entry is added in digline/digline.dev, not here."
    )


# --------------------------------------------------------------------------- #
# The examples run against the release, not against the one before it
# --------------------------------------------------------------------------- #


def workspace_versions() -> dict[str, tuple[int, ...]]:
    """Every package this repository publishes, and the version it declares.

    The core and the three plugins, read where each one states it. `tomllib`
    returns an untyped document, so the shape is cast at the two points that
    read it rather than trusted throughout.
    """
    paths = [
        ROOT / "pyproject.toml",
        *sorted((ROOT / "packages").glob("*/pyproject.toml")),
    ]
    versions: dict[str, tuple[int, ...]] = {}
    for path in paths:
        with path.open("rb") as handle:
            project = cast("dict[str, str]", tomllib.load(handle)["project"])
        versions[project["name"]] = tuple(
            int(part) for part in project["version"].split(".")
        )
    return versions


def example_pins() -> list[tuple[str, str, str]]:
    """Every example pin on a workspace package, as (example, package, specifier).

    A dependency on anything this repository does not publish is not ours to
    have an opinion about: `langchain` moves on its own schedule.
    """
    published = workspace_versions()
    pins: list[tuple[str, str, str]] = []
    for path in sorted((ROOT / "examples").glob("*/pyproject.toml")):
        with path.open("rb") as handle:
            document = tomllib.load(handle)
        dependencies = cast("list[str]", document["project"].get("dependencies", []))
        for dependency in dependencies:
            match = re.match(r"^([A-Za-z0-9][A-Za-z0-9._-]*)", dependency)
            if match is not None and match.group(1) in published:
                pins.append((path.parent.name, match.group(1), dependency))
    return pins


def bounds(specifier: str) -> list[tuple[str, tuple[int, ...]]]:
    """`digline>=0.5,<0.6` -> [(">=", (0, 5)), ("<", (0, 6))]."""
    return [
        (operator, tuple(int(part) for part in version.split(".")))
        for operator, version in re.findall(
            r"(>=|<=|==|<|>)\s*([0-9][0-9.]*)", specifier
        )
    ]


def admits(version: tuple[int, ...], operator: str, bound: tuple[int, ...]) -> bool:
    """Does `version` satisfy this one clause?

    Compared at the bound's own precision: a pin of `>=0.5` is a statement
    about two components, and 0.5.0 satisfies it.
    """
    padded = version[: len(bound)]
    return {
        ">=": padded >= bound,
        "<=": padded <= bound,
        "==": padded == bound,
        "<": padded < bound,
        ">": padded > bound,
    }[operator]


def test_every_example_admits_the_versions_this_workspace_declares() -> None:
    """An example capped below the release is tested against the release before it.

    `examples-from-pypi` resolves each example from the real index, so a cap of
    `<0.5` on a workspace at 0.5.0 does not fail: it installs 0.4.0 and passes,
    green against the version nobody is shipping. That is what happened on the
    0.5.0 release — six examples reported green having never seen it — and the
    green is what made it invisible.

    Every published package, not only the core: the plugin pins were raised by
    hand in the same pass and nothing held them there, which is the same trap
    one name over. The ritual in RELEASING.md raises the caps with the release;
    this is what notices when it was not done.
    """
    published = workspace_versions()
    for example, package, specifier in example_pins():
        version = published[package]
        for operator, bound in bounds(specifier):
            assert admits(version, operator, bound), (
                f"examples/{example}/pyproject.toml pins `{specifier}`, which "
                f"excludes {package} {'.'.join(str(p) for p in version)} — the "
                f"version {package} declares in this workspace. Raise the cap "
                f"with the release, as RELEASING.md says, or the example is "
                f"tested against the release before this one."
            )


#: Spelt out, because the front page spells them out. Only as far as the number
#: of examples could plausibly reach — a longer table would be inventing a
#: problem nobody has.
NUMBER_WORDS = {
    5: "Five",
    6: "Six",
    7: "Seven",
    8: "Eight",
    9: "Nine",
    10: "Ten",
}


def test_the_front_page_counts_the_examples_it_lists() -> None:
    """One source of truth for how many examples there are: the directories.

    `README.md` said "Six projects in `examples/`" and listed six for the whole
    of 0.5.0 and 0.6.0, while `quickstart-toml` was the seventh — present in the
    site's nav, in `sync-docs.sh`'s glob and in `test_example_caps.STANDALONE`,
    and missing only from the page a reader arrives on. Nothing counted, so
    nothing noticed. The example that went missing was the one for a reader who
    writes no Python, which is the one least able to find itself by browsing a
    directory of Python projects.
    """
    names = examples_with_a_readme()
    text = (ROOT / "README.md").read_text(encoding="utf-8")

    word = NUMBER_WORDS.get(len(names))
    assert word is not None, (
        f"{len(names)} examples, which NUMBER_WORDS above does not spell. Add "
        "the word rather than changing the sentence to a digit: the page is "
        "prose."
    )
    assert f"{word} projects in [`examples/`](examples/)" in text, (
        f"README.md does not say “{word} projects in `examples/`”, and there "
        f"are {len(names)}: {names}. If the sentence moved, move this pattern "
        "with it — the number in it is written by hand."
    )

    # Bullets only. The page links `examples/quickstart/` further down as the
    # guide's first chapter, and that directory is deliberately not one of the
    # projects — it has no README, which is the same rule the glob follows.
    linked = {
        found.group(1)
        for line in text.splitlines()
        if line.startswith("- [")
        for found in [re.search(r"\]\(examples/([\w-]+)/\)", line)]
        if found is not None
    }
    assert linked == set(names), (
        "the bullets under that sentence do not match the directories.\n"
        f"  listed but not an example: {sorted(linked - set(names))}\n"
        f"  an example but not listed:  {sorted(set(names) - linked)}"
    )
