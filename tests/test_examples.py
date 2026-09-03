"""The documented example, executed.

An example that rots is worse than no example: it is the first thing a new user
copies, and the only artifact whose failure they will blame on themselves. So
the quickstart is run here for real, and `docs/api.md` is checked to contain the
same file that runs — the document cannot drift from the code it shows.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
from collections.abc import Generator, Iterator
from contextlib import contextmanager
from pathlib import Path

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
    "quickstart-toml",
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
