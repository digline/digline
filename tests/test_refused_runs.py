"""One run the store refuses leaves the rest of the list standing. (#314)

`scan_runs` reads only a file's `schema_version`, so a file at the current
schema that `read_run` refuses gets through the scan. Every place that built a
suite's run list as the scan plus a bare `read_run` then failed whole: `digline
list` and `digline log` exited 64, and `digline view` answered 400 on its first
screen and on every case page. They read through `suite_runs` now, which leaves
the run out and names it.

Each test here plants that file beside a real run and fails on the tree before
#314. MCP's `list_runs` and `log` are tested in `digline-mcp`'s own suite.
"""

from __future__ import annotations

import json
from pathlib import Path

from tests._helpers import baseline_in, cli, run_key
from tests.test_view import get, server

from digline.core.run import SCHEMA_VERSION
from digline.store import FileResultStore, Listing
from digline.wire import EXIT_OK, runs_json

#: What `read_run` refuses and the scan keeps: the current schema, and nothing
#: else a run has.
NOT_A_RUN = json.dumps({"schema_version": SCHEMA_VERSION})


def plant(repo: Path, name: str = "not-a-run") -> None:
    runs = FileResultStore(repo).runs_dir("acme-bank") / "qa"
    runs.mkdir(parents=True, exist_ok=True)
    (runs / f"{name}.json").write_text(NOT_A_RUN, encoding="utf-8")


def promoted(repo: Path) -> str:
    key = run_key(repo)
    done = cli(
        repo,
        "promote",
        "--replacing",
        baseline_in(repo),
        "--suite",
        "suite_qa.py",
        "--run",
        key,
    )
    assert done.returncode == EXIT_OK, done.stderr
    return key


# --------------------------------------------------------------------------- #
# digline list
# --------------------------------------------------------------------------- #


def test_list_shows_the_readable_runs_and_names_the_refused_one(repo: Path) -> None:
    key = promoted(repo)
    plant(repo)

    listed = cli(repo, "list", "--suite", "suite_qa.py")

    assert listed.returncode == EXIT_OK, listed.stderr
    assert f"* {key}" in listed.stdout
    assert "refused: 1 run(s): not-a-run (" in listed.stdout
    assert "mandatory field" in listed.stdout


def test_list_with_every_run_refused_does_not_say_there_are_none_to_read(
    repo: Path,
) -> None:
    """The empty branch used to speak only for what the scan skipped, so a
    store holding nothing but refused runs would have read as an empty one."""
    plant(repo)

    listed = cli(repo, "list", "--suite", "suite_qa.py")

    assert listed.returncode == EXIT_OK, listed.stderr
    assert "no runs for suite 'qa'" in listed.stdout
    assert "refused: 1 run(s): not-a-run (" in listed.stdout


def test_list_names_a_baseline_it_cannot_read_rather_than_failing(
    repo: Path,
) -> None:
    key = promoted(repo)
    baseline = FileResultStore(repo).root / "acme-bank" / "baselines" / "qa.json"
    baseline.write_text(NOT_A_RUN, encoding="utf-8")

    listed = cli(repo, "list", "--suite", "suite_qa.py")

    assert listed.returncode == EXIT_OK, listed.stderr
    assert key in listed.stdout
    # Not marked: the baseline it was promoted from could not be read, and a
    # `*` would claim it had been.
    assert f"* {key}" not in listed.stdout
    assert "the baseline could not be read" in listed.stdout


# --------------------------------------------------------------------------- #
# digline log
# --------------------------------------------------------------------------- #


def test_log_reads_past_a_refused_run_and_counts_it(repo: Path) -> None:
    promoted(repo)
    plant(repo)

    shown = cli(repo, "log", "--suite", "suite_qa.py")
    as_json = cli(repo, "log", "--suite", "suite_qa.py", "--json")

    assert shown.returncode == EXIT_OK, shown.stderr
    assert "1 run(s) were refused by the store and not read" in shown.stdout
    assert as_json.returncode == EXIT_OK, as_json.stderr
    reading = json.loads(as_json.stdout)
    assert reading["runs"] == 1
    assert reading["refused"] == 1
    assert reading["unreadable"] == 0


def test_log_with_nothing_refused_says_nothing_about_it(repo: Path) -> None:
    promoted(repo)

    shown = cli(repo, "log", "--suite", "suite_qa.py")
    reading = json.loads(cli(repo, "log", "--suite", "suite_qa.py", "--json").stdout)

    assert "refused" not in shown.stdout
    assert reading["refused"] == 0


# --------------------------------------------------------------------------- #
# digline view
# --------------------------------------------------------------------------- #


def test_view_serves_the_list_and_the_case_page_past_a_refused_run(
    repo: Path,
) -> None:
    key = promoted(repo)
    plant(repo)

    with server(repo) as (base, _line):
        status, page = get(base + "/")
        case_status, _case = get(base + "/case/q1")

    assert status == 200, page
    assert key in page
    assert "not-a-run" in page
    assert case_status == 200


def test_view_names_the_refused_run_beside_a_cases_history(repo: Path) -> None:
    """A run left out of a history is no row at all, so the rows around it
    close up. `docs/api.md` says whoever shows a history shows the note beside
    it, and `view`'s own case page did not. (#339)"""
    promoted(repo)
    plant(repo)

    with server(repo) as (base, _line):
        status, page = get(base + "/case/q1")

    assert status == 200, page
    # A list item, so it starts with a capital: a sentence on a page. (#440)
    assert "<li>Refused: 1 run(s): not-a-run (" in page


def test_view_says_what_was_left_out_in_the_pages_language(repo: Path) -> None:
    promoted(repo)
    plant(repo)

    with server(repo) as (base, _line):
        _status, runs = get(base + "/?locale=it")
        _status, case = get(base + "/case/q1?locale=it")

    for page in (runs, case):
        assert "<li>Rifiutate: 1 run: not-a-run (" in page
        assert "refused:" not in page.lower()


def test_view_does_not_advise_a_migration_for_a_refused_run(repo: Path) -> None:
    """No migration reads a document that has nothing of a run in it."""
    promoted(repo)
    plant(repo)

    with server(repo) as (base, _line):
        _status, page = get(base + "/")

    assert "not-a-run" in page
    assert "migrate" not in page


# --------------------------------------------------------------------------- #
# The wire, for a caller that predates #314
# --------------------------------------------------------------------------- #


def test_runs_json_keeps_its_old_call_working() -> None:
    """A `digline-mcp` already published calls `runs_json` without the three
    new arguments. Against this core it must still get an answer, and the
    defaults must be true for it: such a caller raised on every refusal, so
    for it nothing was refused and the note is the scan's."""
    listing = Listing(runs=(), skipped={3: 1}, unreadable=())

    answered = runs_json(
        [], tenant="acme-bank", suite="qa", baseline_key=None, listing=listing
    )

    assert answered["note"] == listing.note()
    assert answered["refused"] == 0
    assert answered["baseline_unreadable"] is False


# --------------------------------------------------------------------------- #
# `latest`, which does not move
# --------------------------------------------------------------------------- #


def test_latest_still_refuses_past_a_refused_run(repo: Path) -> None:
    """Ruled, not overlooked: a document that cannot be read has no
    `created_at` to trust, so nothing can say whether it was newer than the run
    `latest` would pick. Picking past it could compare or promote the wrong run
    in silence. `docs/migrate.md` says so, and this holds it."""
    promoted(repo)
    plant(repo)

    done = cli(
        repo, "report", "--suite", "suite_qa.py", "--run", "latest", "--locale", "en"
    )

    assert done.returncode != EXIT_OK
    assert "mandatory field" in done.stderr
