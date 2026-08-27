"""The documented example, executed.

An example that rots is worse than no example: it is the first thing a new user
copies, and the only artifact whose failure they will blame on themselves. So
the quickstart is run here for real, and `docs/api.md` is checked to contain the
same file that runs — the document cannot drift from the code it shows.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from digline.cli import EXIT_OK

ROOT = Path(__file__).resolve().parents[1]
QUICKSTART = ROOT / "examples" / "quickstart"
API_DOC = ROOT / "docs" / "api.md"


def cli(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "digline.cli", *args],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
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
STANDALONE = ("classifier", "prompt-first", "rag", "external-app")


@pytest.fixture(params=STANDALONE)
def standalone(request: pytest.FixtureRequest, tmp_path: Path) -> Path:
    """A copy, without its baseline: the cycle has to work from nothing."""
    name = str(request.param)
    workdir = tmp_path / name
    shutil.copytree(ROOT / "examples" / name, workdir)
    shutil.rmtree(workdir / ".digline", ignore_errors=True)
    return workdir


def test_each_example_completes_the_cycle(standalone: Path) -> None:
    """run -> promote -> compare, exactly what its README tells a reader."""
    ran = cli(standalone, "run", "--suite", "suite.py")
    assert ran.returncode == EXIT_OK, ran.stderr
    key = ran.stdout.strip()
    assert key

    promoted = cli(standalone, "promote", "--suite", "suite.py", "--run", key)
    assert promoted.returncode == EXIT_OK, promoted.stderr

    compared = cli(standalone, "compare", "--suite", "suite.py", "--run", key)
    assert compared.returncode == EXIT_OK, compared.stderr
    assert "Nothing got worse" in compared.stdout


def test_each_example_renders_its_report(standalone: Path) -> None:
    cli(standalone, "run", "--suite", "suite.py")
    cli(standalone, "promote", "--suite", "suite.py", "--run", "latest")
    out = standalone / "fresh.html"
    rendered = cli(
        standalone,
        "report",
        "--suite",
        "suite.py",
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
