"""`digline view` that reads its suite again, and starts without one.

Found on a user pass with a Node application: the server loaded the suite
once, at launch, and then described that suite, so a `[capture]` written
while it ran read as *no suite yet* and a case imported from its own page
as none; and `digline view` with no `--suite` exited 64, though `record.md`
told a person who did not know what to do next to open it.

Every server here is a real `digline view`, in a process of its own, over a
store written by digline's own writers.
"""

from __future__ import annotations

import subprocess
import sys
import urllib.error
import urllib.request
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

import pytest
from tests.test_view_policy import WANTED, inline_in

from digline.cli import EXIT_USAGE
from digline.core.recording import Recording, setup_digest_of
from digline.core.run import RecordedResponse
from digline.host import import_elect, import_listing, load_suite
from digline.host.importing import answer_id
from digline.recorder import UNASSIGNED
from digline.store.file_store import FileResultStore, RecordingWriter

TENANT = "dev"
SETUP: dict[str, object] = {"model": "m", "system": "Say whether the CV fits."}

SUITE_TOML = """\
[suite]
tenant = "dev"
environment = "dev"
name = "screening"
cases = {cases}
samples = 2
min_agreement = "2/2"

[target]
type = "http"
url = "http://127.0.0.1:9/screen"
output_path = "answer"

  [target.body]
  cv = "case.vars.cv"

[[assertions]]
type = "llm_rubric"
rubric = "Right?"
judge = "openai/gpt-4o-mini"
threshold = 0.7
tolerance = 0.05
{capture}"""

CAPTURE = """
[capture]
cases_file = "captured.json"
repository = "private"
check = "llm_rubric"
"""


def write_suite(root: Path, *, capture: bool) -> None:
    (root / "eval").mkdir(exist_ok=True)
    (root / "eval" / "cases.json").write_text(
        '[{"id": "by-hand", "vars": {"cv": "CV"}}]', encoding="utf-8"
    )
    cases = '["cases.json", "captured.json"]' if capture else '"cases.json"'
    (root / "eval" / "suite.toml").write_text(
        SUITE_TOML.format(cases=cases, capture=CAPTURE if capture else ""),
        encoding="utf-8",
    )


def asked(text: str) -> dict[str, object]:
    return {"messages": [{"role": "user", "content": text}]}


def record(root: Path, *questions: str, suite: str = "screening") -> None:
    writer = RecordingWriter(FileResultStore(root))
    for minute, question in enumerate(questions, start=1):
        writer.write(
            Recording(
                source_tenant=TENANT,
                app="node",
                suite=suite,
                case=asked(question),
                setup=SETUP,
                setup_digest=setup_digest_of(SETUP),
                response=RecordedResponse(output="FIT", kind="text", input="q"),
                recorded_at=f"2026-11-05T08:{minute:02d}:00+00:00",
            )
        )


@contextmanager
def viewing(root: Path, *flags: str) -> Generator[tuple[str, str]]:
    """A real `digline view`, yielding its address and its startup line."""
    process = subprocess.Popen(
        [sys.executable, "-u", "-m", "digline.cli", "view", "--port", "0", *flags],
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert process.stdout is not None
        line = process.stdout.readline()
        assert "http://" in line, (
            line,
            process.stderr.read() if process.stderr else "",
        )
        address = line.split()[3].split("?")[0]
        yield address, line
    finally:
        process.terminate()
        process.wait(timeout=10)


def get(url: str) -> tuple[int, str, str]:
    """Status, body and Content-Security-Policy of one GET."""
    try:
        with urllib.request.urlopen(url, timeout=10) as answer:
            return (
                answer.status,
                answer.read().decode("utf-8"),
                answer.headers.get("Content-Security-Policy", ""),
            )
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8"), ""


def heading(page: str) -> str:
    return page.split("<h1>")[1].split("</h1>")[0]


# --------------------------------------------------------------------------- #
# The suite read again
# --------------------------------------------------------------------------- #


def test_a_capture_and_a_case_written_while_it_runs_are_seen(tmp_path: Path) -> None:
    """The two lies of the user pass, each read before and after the write
    that makes it a lie, on one server that is never restarted."""
    write_suite(tmp_path, capture=False)
    record(tmp_path, "CV: Python", "CV: Java")
    with viewing(tmp_path, "--suite", "eval/suite.toml") as (base, _line):
        where = f"{base}where/dev/screening/?locale=en"
        assert heading(get(where)[1]) == "2 recording(s) in screening, no suite yet"

        write_suite(tmp_path, capture=True)
        assert heading(get(where)[1]) == "2 since the last import"

        suite, found = load_suite(str(tmp_path / "eval" / "suite.toml"), root=tmp_path)
        listing = import_listing(tmp_path, suite, found.module, TENANT)
        import_elect(listing, good=[answer_id(asked("CV: Python"), "FIT")], by="Pippo")
        page = get(where)[1]
        assert heading(page) == "The suite has never run"
        assert "holds 1 reviewed answer(s)" in page


def test_a_suite_that_no_longer_loads_is_said_and_never_served_stale(
    tmp_path: Path,
) -> None:
    write_suite(tmp_path, capture=True)
    with viewing(tmp_path, "--suite", "eval/suite.toml") as (base, _line):
        assert get(base)[0] == 200
        (tmp_path / "eval" / "suite.toml").write_text("[suite\n", encoding="utf-8")
        status, page, _ = get(base)
        assert status == 400
        assert "the suite no longer loads" in page
        write_suite(tmp_path, capture=True)
        assert get(base)[0] == 200


# --------------------------------------------------------------------------- #
# No suite: a tenant's pages
# --------------------------------------------------------------------------- #


def test_without_a_suite_where_you_are_is_the_first_page(tmp_path: Path) -> None:
    record(tmp_path, "CV: Python", suite=UNASSIGNED)
    with viewing(tmp_path) as (base, line):
        assert "tenant 'dev', no suite" in line
        status, page, policy = get(base)
        assert status == 200
        assert policy == WANTED
        assert inline_in(page) == []
        assert heading(page) == "1 call(s) named no suite"
        # The bar: where you are, then the recorder, and no runs.
        bar = page.split('<nav class="bar">')[1].split("</nav>")[0]
        assert bar.index(">Where you are</a>") < bar.index(">Recorder</a>")
        assert ">Runs</a>" not in bar
        recorder = get(f"{base}recorder/dev/?locale=en")
        assert recorder[0] == 200 and inline_in(recorder[1]) == []


def test_without_a_suite_the_pages_of_a_suite_are_no_page(tmp_path: Path) -> None:
    record(tmp_path, "CV: Python")
    with viewing(tmp_path) as (base, _line):
        status, page, _ = get(f"{base}compare?run=x")
        assert status == 404
        assert "started without --suite" in page


def test_without_a_suite_the_suites_the_store_holds_are_listed(tmp_path: Path) -> None:
    """From the fourth state on there is a suite to serve, and the page lists
    the ones the store holds, with the command that serves one."""
    record(tmp_path, "CV: Python", "CV: Java")
    record(tmp_path, "Summarise", suite="summary")
    with viewing(tmp_path) as (base, _line):
        page = get(base)[1]
        assert heading(page) == "2 recording(s) in screening, no suite yet"
        assert "screening: 2 recording(s), 0 run(s)" in page
        assert "summary: 1 recording(s), 0 run(s)" in page
        assert "digline view --suite &#x27;&lt;suite file&gt;&#x27;" in page


def test_without_a_suite_a_named_tenant_with_nothing_starts_at_the_start(
    tmp_path: Path,
) -> None:
    with viewing(tmp_path, "--tenant", "dev") as (base, _line):
        page = get(base)[1]
        assert heading(page) == "Nothing recorded yet"
        assert "digline holds no recording of tenant dev." in page
        assert "digline record on --tenant dev" in page


def refused(root: Path, *flags: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "digline.cli", "view", "--port", "0", *flags],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def test_without_a_suite_or_a_tenant_it_says_which_to_name(tmp_path: Path) -> None:
    done = refused(tmp_path)
    assert done.returncode == EXIT_USAGE
    assert "holds none: name one with --tenant" in done.stderr
    record(tmp_path, "CV: Python")
    writer = RecordingWriter(FileResultStore(tmp_path))
    writer.write(
        Recording(
            source_tenant="other",
            app="node",
            suite="x",
            case=asked("hi"),
            setup=SETUP,
            setup_digest=setup_digest_of(SETUP),
            response=RecordedResponse(output="hello", kind="text", input="q"),
            recorded_at="2026-11-05T08:00:00+00:00",
        )
    )
    done = refused(tmp_path)
    assert done.returncode == EXIT_USAGE
    assert "holds dev, other" in done.stderr


@pytest.mark.parametrize("flag", ["--allow-promote"])
def test_without_a_suite_there_is_nothing_to_promote(tmp_path: Path, flag: str) -> None:
    record(tmp_path, "CV: Python")
    done = refused(tmp_path, flag)
    assert done.returncode == EXIT_USAGE
    assert "--allow-promote promotes a suite's run" in done.stderr
