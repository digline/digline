"""The command line, driven in a real subprocess against a real git repository.

In-process tests would not prove the two things this layer exists for: that the
clock and git are read *here* and nowhere else, and that a pipeline can act on
the exit code.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
from tests._helpers import SUITE_SOURCE, cli, run_key, write_suite

from digline.cli import (
    EXIT_OK,
    EXIT_UNJUDGED,
    EXIT_USAGE,
    EXIT_WORSE,
    OUTPUT_VERSION,
    build_parser,
    exit_code,
)
from digline.core.run import SCHEMA_VERSION
from digline.report import Headline

ROOT = Path(__file__).resolve().parents[1]

# --------------------------------------------------------------------------- #
# exit codes
# --------------------------------------------------------------------------- #


def head(*, worse: bool, unjudged: int) -> Headline:
    return Headline(
        worse=worse,
        unjudged=unjudged,
        suspended=0,
        config_changed=False,
        counts={},
        reasons_available=True,
        sentence="",
    )


def test_a_regression_outranks_an_unjudged_case() -> None:
    """Both need attention, but a regression is a statement about behaviour and
    an unjudged case is one about the harness. If the harness won, a real
    regression would hide behind a flaky provider."""
    assert exit_code(head(worse=True, unjudged=3)) == EXIT_WORSE
    assert exit_code(head(worse=True, unjudged=0)) == EXIT_WORSE
    assert exit_code(head(worse=False, unjudged=3)) == EXIT_UNJUDGED
    assert exit_code(head(worse=False, unjudged=0)) == EXIT_OK


def test_a_suspension_alone_never_fails() -> None:
    quiet = Headline(
        worse=False,
        unjudged=0,
        suspended=7,
        config_changed=True,
        counts={},
        reasons_available=True,
        sentence="",
    )
    assert exit_code(quiet) == EXIT_OK


# --------------------------------------------------------------------------- #
# the cycle, through the process boundary
# --------------------------------------------------------------------------- #


def test_run_prints_a_key_that_promote_accepts(repo: Path) -> None:
    key = run_key(repo)
    assert key and ":" not in key

    promoted = cli(repo, "promote", "--suite", "suite_qa.py", "--run", key)
    assert promoted.returncode == EXIT_OK, promoted.stderr
    assert (repo / ".digline" / "acme-bank" / "baselines" / "qa.json").is_file()

    compared = cli(
        repo, "compare", "--suite", "suite_qa.py", "--run", key, "--locale", "en"
    )
    assert compared.returncode == EXIT_OK
    assert "Nothing got worse" in compared.stdout


def test_compare_exits_worse_when_the_suite_regresses(repo: Path) -> None:
    baseline_key = run_key(repo)
    cli(repo, "promote", "--suite", "suite_qa.py", "--run", baseline_key)

    write_suite(repo, fr_score="0.2")  # the judge now scores one case badly
    key = run_key(repo)
    compared = cli(
        repo, "compare", "--suite", "suite_qa.py", "--run", key, "--locale", "it"
    )
    assert compared.returncode == EXIT_WORSE
    assert "peggiorato" in compared.stdout


def test_compare_exits_unjudged_when_a_case_cannot_run(repo: Path) -> None:
    baseline_key = run_key(repo)
    cli(repo, "promote", "--suite", "suite_qa.py", "--run", baseline_key)

    write_suite(repo, extra=', Case(id="flaky")')
    key = run_key(repo)
    compared = cli(
        repo, "compare", "--suite", "suite_qa.py", "--run", key, "--locale", "en"
    )
    assert compared.returncode == EXIT_UNJUDGED
    assert "1 case could not be judged" in compared.stdout


def test_compare_json_emits_the_headline_not_the_document(repo: Path) -> None:
    key = run_key(repo)
    cli(repo, "promote", "--suite", "suite_qa.py", "--run", key)
    done = cli(
        repo,
        "compare",
        "--suite",
        "suite_qa.py",
        "--run",
        key,
        "--locale",
        "en",
        "--json",
    )
    payload = json.loads(done.stdout)
    assert set(payload) == COMPARE_KEYS
    assert payload["output_version"] == OUTPUT_VERSION
    assert "<html" not in done.stdout


#: The whole of what `digline compare --json` prints, at `OUTPUT_VERSION` 1.
#:
#: A golden set, and the point is that it is tedious to change: adding a key
#: here without bumping `OUTPUT_VERSION` is the mistake this guards, because a
#: pipeline that parses stdout has no other way to learn that the shape moved.
#: `SCHEMA_VERSION` does not cover it — that one is about documents on disk.
COMPARE_KEYS = {
    "output_version",
    "worse",
    "unjudged",
    "suspended",
    "config_changed",
    # Joined the contract with ADR 0003: same rules, different prompt is a thing
    # a pipeline has to be able to ask about.
    "artifacts_changed",
    "counts",
    "reasons_available",
    "sentence",
}


def test_the_json_output_declares_its_own_contract_version(repo: Path) -> None:
    """Storage and output are two contracts with two lifetimes, so they carry
    two numbers. A run file must stay *readable* years later, which is why
    `SCHEMA_VERSION` has migrations; a pipeline only needs to know what it is
    being handed today."""
    key = run_key(repo)
    cli(repo, "promote", "--suite", "suite_qa.py", "--run", key)

    compared = json.loads(
        cli(repo, "compare", "--suite", "suite_qa.py", "--run", key, "--json").stdout
    )
    ran = json.loads(cli(repo, "run", "--suite", "suite_qa.py", "--json").stdout)
    assert compared["output_version"] == ran["output_version"] == OUTPUT_VERSION
    # The two numbers are independent, and nothing may quietly tie them.
    assert OUTPUT_VERSION != SCHEMA_VERSION


def test_json_full_adds_the_deltas_and_nothing_else(repo: Path) -> None:
    key = run_key(repo)
    cli(repo, "promote", "--suite", "suite_qa.py", "--run", key)
    full = json.loads(
        cli(
            repo, "compare", "--suite", "suite_qa.py", "--run", key, "--json", "full"
        ).stdout
    )
    assert set(full) == COMPARE_KEYS | {"deltas"}


def regressed_repo(repo: Path) -> str:
    """A promoted baseline, then a run where `capital-fr` scores badly."""
    cli(repo, "promote", "--suite", "suite_qa.py", "--run", run_key(repo))
    write_suite(repo, fr_score="0.2")
    return run_key(repo)


def test_compare_names_the_checks_that_got_worse(repo: Path) -> None:
    """ "1 check got worse" without saying which sends the reader to open an HTML
    file to learn a fact that fits on one line."""
    key = regressed_repo(repo)
    done = cli(repo, "compare", "--suite", "suite_qa.py", "--run", key)
    assert done.returncode == EXIT_WORSE

    lines = [ln for ln in done.stdout.splitlines() if " · " in ln]
    assert len(lines) == 1
    case, assertion, detail = lines[0].split(" · ")
    assert case == "capital-fr"
    assert assertion == "llm_rubric"
    assert "1.000000" in detail and "0.200000" in detail


def test_the_terminal_detail_is_the_one_in_the_report(repo: Path) -> None:
    """End to end through two commands: if the two ever stop sharing the
    string, this says so."""
    key = regressed_repo(repo)
    terminal = cli(
        repo, "compare", "--suite", "suite_qa.py", "--run", key, "--locale", "it"
    ).stdout
    document = cli(
        repo, "report", "--suite", "suite_qa.py", "--run", key, "--locale", "it"
    ).stdout

    detail = next(ln for ln in terminal.splitlines() if " · " in ln).split(" · ")[2]
    assert detail in document


def test_a_clean_comparison_prints_only_the_sentence(repo: Path) -> None:
    key = run_key(repo)
    cli(repo, "promote", "--suite", "suite_qa.py", "--run", key)
    done = cli(repo, "compare", "--suite", "suite_qa.py", "--run", key)
    assert done.returncode == EXIT_OK
    assert " · " not in done.stdout


def test_compare_json_full_adds_the_deltas(repo: Path) -> None:
    key = regressed_repo(repo)

    plain = json.loads(
        cli(repo, "compare", "--suite", "suite_qa.py", "--run", key, "--json").stdout
    )
    assert "deltas" not in plain  # unchanged, as promised

    full = json.loads(
        cli(
            repo, "compare", "--suite", "suite_qa.py", "--run", key, "--json", "full"
        ).stdout
    )
    assert full["sentence"] == plain["sentence"]
    worse = [d for d in full["deltas"] if d["outcome"] == "regressed"]
    assert len(worse) == 1
    assert worse[0]["case_id"] == "capital-fr"
    assert worse[0]["before"] == 1.0
    assert worse[0]["after"] == 0.2
    assert worse[0]["scope"] == "case"


def test_every_delta_says_what_it_is_about(repo: Path) -> None:
    """A run-scoped delta carries `case_id == ""`, and without `scope` the only
    way to tell an aggregate from a case was to read that empty string as a
    convention — which is also what a malformed `case_id` would look like."""
    key = regressed_repo(repo)
    full = json.loads(
        cli(
            repo, "compare", "--suite", "suite_qa.py", "--run", key, "--json", "full"
        ).stdout
    )
    assert all(d["scope"] in ("case", "run") for d in full["deltas"])
    assert all(d["case_id"] != "" for d in full["deltas"] if d["scope"] == "case")


def test_json_full_does_not_carry_the_judge_words(repo: Path) -> None:
    """A reason is payload, and the stdout of a CI job is where logs go and
    stay. A pipeline that needs it can read the run file from inside the
    perimeter."""
    key = regressed_repo(repo)
    out = cli(
        repo, "compare", "--suite", "suite_qa.py", "--run", key, "--json", "full"
    ).stdout
    assert "judged:" not in out
    assert all("reason" not in d for d in json.loads(out)["deltas"])


def test_report_writes_a_document_and_keeps_the_exit_code(repo: Path) -> None:
    baseline_key = run_key(repo)
    cli(repo, "promote", "--suite", "suite_qa.py", "--run", baseline_key)
    write_suite(repo, fr_score="0.2")
    key = run_key(repo)

    out = repo / "report.html"
    done = cli(
        repo,
        "report",
        "--suite",
        "suite_qa.py",
        "--run",
        key,
        "--locale",
        "it",
        "--out",
        str(out),
    )
    assert done.returncode == EXIT_WORSE
    document = out.read_text(encoding="utf-8")
    assert document.startswith("<!DOCTYPE html>")
    assert "È peggiorato? Sì" in document


def test_report_redacted_removes_the_judge_words(repo: Path) -> None:
    key = run_key(repo)
    cli(repo, "promote", "--suite", "suite_qa.py", "--run", key)

    complete = cli(
        repo, "report", "--suite", "suite_qa.py", "--run", key, "--locale", "en"
    ).stdout
    hidden = cli(
        repo,
        "report",
        "--suite",
        "suite_qa.py",
        "--run",
        key,
        "--locale",
        "en",
        "--redacted",
    ).stdout

    assert "judged:" in complete
    assert "judged:" not in hidden
    assert "produced from redacted data" in hidden


# --------------------------------------------------------------------------- #
# list
# --------------------------------------------------------------------------- #


def test_list_shows_runs_newest_first_and_marks_the_baseline(repo: Path) -> None:
    """Without this a developer coming back the next day had no way to name
    yesterday's run: `--run KEY` is mandatory everywhere and only `run` prints
    a key."""
    first = run_key(repo)
    cli(repo, "promote", "--suite", "suite_qa.py", "--run", first)
    write_suite(repo, fr_score="0.5")
    second = run_key(repo)
    assert second != first

    done = cli(repo, "list", "--suite", "suite_qa.py")
    assert done.returncode == EXIT_OK, done.stderr
    body = [line for line in done.stdout.splitlines() if line.strip()]

    header, rows = body[0], body[1:3]
    assert "KEY" in header and "CASES" in header
    # Newest first. Checked by membership, not by column index: a marked row
    # starts with "*" and an unmarked one with a space, so `split()` shifts.
    assert second in rows[0] and first not in rows[0]
    assert first in rows[1] and second not in rows[1]
    # The promoted one, and only it, is marked.
    assert rows[1].startswith("*")
    assert not rows[0].startswith("*")
    assert "* = current baseline" in done.stdout


def test_list_reports_the_recorded_facts(repo: Path) -> None:
    key = run_key(repo)
    done = cli(repo, "list", "--suite", "suite_qa.py")
    row = next(line for line in done.stdout.splitlines() if key in line)
    assert "staging" in row  # environment
    assert row.rstrip().endswith("2")  # two cases
    sha = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert sha[:7] in row


def test_list_marks_nothing_when_there_is_no_baseline(repo: Path) -> None:
    run_key(repo)
    done = cli(repo, "list", "--suite", "suite_qa.py")
    assert "* = current baseline" not in done.stdout


def test_list_on_an_empty_store_says_so(repo: Path) -> None:
    done = cli(repo, "list", "--suite", "suite_qa.py")
    assert done.returncode == EXIT_OK
    assert "no runs for suite 'qa'" in done.stdout


def test_list_needs_no_locale(repo: Path) -> None:
    """Terminal output for the developer, not a document for a recipient."""
    run_key(repo)
    assert cli(repo, "list", "--suite", "suite_qa.py").returncode == EXIT_OK


def test_list_shows_a_dirty_commit_as_such(repo: Path) -> None:
    (repo / "scratch.txt").write_text("uncommitted", encoding="utf-8")
    key = run_key(repo)
    done = cli(repo, "list", "--suite", "suite_qa.py")
    row = next(line for line in done.stdout.splitlines() if key in line)
    assert "-dirty" in row


# --------------------------------------------------------------------------- #
# git and the clock live here
# --------------------------------------------------------------------------- #


def test_a_clean_tree_records_the_commit(repo: Path) -> None:
    key = run_key(repo)
    stored = json.loads(
        (repo / ".digline" / "acme-bank" / "runs" / "qa" / f"{key}.json").read_text(
            encoding="utf-8"
        )
    )
    sha = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert stored["git_commit"] == sha
    assert not stored["git_commit"].endswith("-dirty")


def test_a_dirty_tree_is_marked_and_warned_about_in_the_report(repo: Path) -> None:
    """Such a run cannot be reproduced from the repository, and a reader
    deciding whether to act on it must be told before the numbers."""
    (repo / "untracked_change.txt").write_text("uncommitted", encoding="utf-8")

    key = run_key(repo)
    cli(repo, "promote", "--suite", "suite_qa.py", "--run", key)
    stored = json.loads(
        (repo / ".digline" / "acme-bank" / "runs" / "qa" / f"{key}.json").read_text(
            encoding="utf-8"
        )
    )
    assert stored["git_commit"].endswith("-dirty")

    document = cli(
        repo, "report", "--suite", "suite_qa.py", "--run", key, "--locale", "en"
    ).stdout
    assert "-dirty" in document
    assert "cannot be reproduced from the repository" in document


def test_outside_a_repository_there_is_no_commit_and_no_error(
    tmp_path: Path,
) -> None:
    """A run produced from a notebook or a container legitimately has none, and
    refusing to work there would break the tool where people try things first."""
    write_suite(tmp_path)
    key = run_key(tmp_path)
    stored = json.loads(
        (tmp_path / ".digline" / "acme-bank" / "runs" / "qa" / f"{key}.json").read_text(
            encoding="utf-8"
        )
    )
    assert stored["git_commit"] is None


def test_the_created_at_comes_from_the_clock(repo: Path) -> None:
    first = run_key(repo)
    stored = json.loads(
        (repo / ".digline" / "acme-bank" / "runs" / "qa" / f"{first}.json").read_text(
            encoding="utf-8"
        )
    )
    assert stored["created_at"].startswith("20")
    assert stored["created_at"].endswith("+00:00")


# --------------------------------------------------------------------------- #
# loading, and what the CLI refuses
# --------------------------------------------------------------------------- #


def test_a_missing_suite_attribute_names_what_is_missing(repo: Path) -> None:
    (repo / "empty.py").write_text("x = 1\n", encoding="utf-8")
    done = cli(repo, "run", "--suite", "empty.py")
    assert done.returncode == EXIT_USAGE
    assert "has no attribute 'suite'" in done.stderr
    assert "Module defines: x" in done.stderr


def test_a_missing_target_attribute_names_what_is_missing(repo: Path) -> None:
    source = SUITE_SOURCE % {"fr": "1.0", "extra": ""}
    (repo / "no_target.py").write_text(
        source.replace("def target(case):", "def _hidden(case):"), encoding="utf-8"
    )
    done = cli(repo, "run", "--suite", "no_target.py")
    assert done.returncode == EXIT_USAGE
    assert "no attribute 'target'" in done.stderr


def test_an_explicit_attribute_after_a_colon_is_used(repo: Path) -> None:
    done = cli(repo, "run", "--suite", "suite_qa.py:suite")
    assert done.returncode == EXIT_OK, done.stderr


def test_a_nonexistent_file_says_so(repo: Path) -> None:
    done = cli(repo, "run", "--suite", "nowhere.py")
    assert done.returncode == EXIT_USAGE
    assert "no such file" in done.stderr


def test_tenant_and_env_verify_and_never_override(repo: Path) -> None:
    ok = cli(
        repo,
        "run",
        "--suite",
        "suite_qa.py",
        "--tenant",
        "acme-bank",
        "--env",
        "staging",
    )
    assert ok.returncode == EXIT_OK, ok.stderr

    wrong = cli(repo, "run", "--suite", "suite_qa.py", "--tenant", "globex")
    assert wrong.returncode == EXIT_USAGE
    assert "The suite decides" in wrong.stderr
    # And nothing was filed under the wrong perimeter.
    assert not (repo / ".digline" / "globex").exists()


def test_compare_does_not_demand_a_locale(repo: Path) -> None:
    """Terminal output for a developer, same category as `list`: English unless
    asked otherwise. The sentence matches the report's anyway, because both come
    from `headline()` — there is no need to make the user restate it."""
    key = run_key(repo)
    cli(repo, "promote", "--suite", "suite_qa.py", "--run", key)

    plain = cli(repo, "compare", "--suite", "suite_qa.py", "--run", key)
    assert plain.returncode == EXIT_OK, plain.stderr
    assert "Nothing got worse" in plain.stdout

    italian = cli(
        repo, "compare", "--suite", "suite_qa.py", "--run", key, "--locale", "it"
    )
    assert "Nulla è peggiorato" in italian.stdout


def test_report_does_demand_a_locale(repo: Path) -> None:
    """A document has a recipient, and their language is not settled by
    omission."""
    key = run_key(repo)
    cli(repo, "promote", "--suite", "suite_qa.py", "--run", key)
    done = cli(repo, "report", "--suite", "suite_qa.py", "--run", key)
    assert done.returncode != EXIT_OK
    assert "--locale" in done.stderr


# --------------------------------------------------------------------------- #
# --run latest
# --------------------------------------------------------------------------- #


def test_latest_resolves_to_the_most_recent_run(repo: Path) -> None:
    """The friction of minute three: copying by hand the key `run` just printed."""
    first = run_key(repo)
    cli(repo, "promote", "--suite", "suite_qa.py", "--run", first)
    write_suite(repo, fr_score="0.2")
    second = run_key(repo)
    assert second != first

    compared = cli(repo, "compare", "--suite", "suite_qa.py", "--run", "latest")
    assert compared.returncode == EXIT_WORSE  # the second run is the worse one
    assert "1 check got worse" in compared.stdout


def test_latest_works_for_promote_and_reports_the_real_key(repo: Path) -> None:
    key = run_key(repo)
    done = cli(repo, "promote", "--suite", "suite_qa.py", "--run", "latest")
    assert done.returncode == EXIT_OK, done.stderr
    # Never the literal "latest": what was promoted must be nameable afterwards.
    assert key in done.stdout
    assert "latest" not in done.stdout


def test_latest_works_for_report(repo: Path) -> None:
    key = run_key(repo)
    cli(repo, "promote", "--suite", "suite_qa.py", "--run", key)
    done = cli(
        repo, "report", "--suite", "suite_qa.py", "--run", "latest", "--locale", "en"
    )
    assert done.returncode == EXIT_OK, done.stderr
    assert done.stdout.startswith("<!DOCTYPE html>")


def test_latest_on_an_empty_store_says_so(repo: Path) -> None:
    done = cli(repo, "compare", "--suite", "suite_qa.py", "--run", "latest")
    assert done.returncode == EXIT_USAGE
    assert "no runs stored" in done.stderr
    assert "Run it first" in done.stderr


def test_run_is_still_mandatory(repo: Path) -> None:
    """`latest` is a value the caller types, not a default that guesses."""
    run_key(repo)
    done = cli(repo, "compare", "--suite", "suite_qa.py")
    assert done.returncode != EXIT_OK
    assert "--run" in done.stderr


# --------------------------------------------------------------------------- #
# A suite imports the application it evaluates
# --------------------------------------------------------------------------- #


def test_a_suite_can_import_a_module_beside_it(tmp_path: Path) -> None:
    """A suite imports the application under test — that is what a suite *is*.
    Without its directory on the path, the first real suite fails on its first
    line with ModuleNotFoundError and the tool looks broken because it is."""
    (tmp_path / "brief.py").write_text(
        "def judge_score(case_id):\n    return 0.9\n", encoding="utf-8"
    )
    (tmp_path / "suite_app.py").write_text(
        "from brief import judge_score\n"
        "from digline.core import Contains, JudgeReply, LlmRubric\n"
        "from digline.run import Case, Response, Suite\n"
        "\n"
        "suite = Suite(\n"
        "    tenant='acme', environment='dev', name='qa',\n"
        "    assertions=[\n"
        "        Contains(needle='Rome'),\n"
        "        LlmRubric(\n"
        "            rubric='ok?',\n"
        "            judge=lambda p: JudgeReply(score=judge_score('x'), reason='r'),\n"
        "            threshold=0.7,\n"
        "            tolerance=0.05,\n"
        "        ),\n"
        "    ],\n"
        "    cases=[Case(id='one')],\n"
        ")\n"
        "\n"
        "def target(case):\n"
        "    return Response(output='Rome', cost_usd=0.01)\n",
        encoding="utf-8",
    )

    done = cli(tmp_path, "run", "--suite", "suite_app.py")
    assert done.returncode == EXIT_OK, done.stderr
    assert done.stdout.strip()


APP_SUITE = """\
import brief
from digline.core import JudgeReply, LlmRubric
from digline.run import Case, Response, Suite

suite = Suite(
    tenant="acme", environment="dev", name="qa",
    assertions=[
        LlmRubric(
            rubric="ok?",
            judge=lambda p: JudgeReply(score=brief.SCORE, reason="r"),
            threshold=0.7,
            tolerance=0.05,
        )
    ],
    cases=[Case(id="one")],
)


def target(case):
    return Response(output="Rome", cost_usd=0.01)
"""


def test_the_application_beside_the_suite_is_never_read_from_stale_bytecode(
    repo: Path,
) -> None:
    """The defect this finder exists for, reproduced exactly.

    `brief.py` is edited to the same length, and its mtime is forced back so the
    pre-existing `.pyc` looks fresh — the same condition an edit within one
    second produces, made deterministic. Without the source-only finder the run
    scores 0.95 again and the comparison reports that nothing got worse, which
    is the only kind of defect that can hide a regression.
    """
    brief = repo / "brief.py"
    brief.write_text("SCORE = 0.95\n", encoding="utf-8")
    (repo / "suite_app.py").write_text(APP_SUITE, encoding="utf-8")

    # Someone already ran the application the ordinary way, so a cache exists.
    subprocess.run(
        [sys.executable, "-c", "import brief"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    assert (repo / "__pycache__").is_dir()
    stamp = brief.stat().st_mtime

    first = cli(repo, "run", "--suite", "suite_app.py")
    assert first.returncode == EXIT_OK, first.stderr
    cli(repo, "promote", "--suite", "suite_app.py", "--run", "latest")

    # Same length, and the timestamp put back: to Python's freshness check
    # (mtime, size) the stale cache is indistinguishable from a current one.
    brief.write_text("SCORE = 0.20\n", encoding="utf-8")
    os.utime(brief, (stamp, stamp))

    second = cli(repo, "run", "--suite", "suite_app.py")
    assert second.returncode == EXIT_OK, second.stderr
    compared = cli(repo, "compare", "--suite", "suite_app.py", "--run", "latest")
    assert compared.returncode == EXIT_WORSE, compared.stdout
    assert "1 check got worse" in compared.stdout


def test_running_leaves_no_bytecode_behind(repo: Path) -> None:
    """New untracked files make a repository dirty, and digline would then
    report every run of its own making as unreproducible."""
    (repo / "brief.py").write_text("SCORE = 0.95\n", encoding="utf-8")
    (repo / "suite_app.py").write_text(APP_SUITE, encoding="utf-8")

    done = cli(repo, "run", "--suite", "suite_app.py")
    assert done.returncode == EXIT_OK, done.stderr
    assert not list(repo.rglob("__pycache__"))
    assert not list(repo.rglob("*.pyc"))


def test_only_the_suite_directory_gets_the_source_only_loader(
    tmp_path: Path,
) -> None:
    """Scoped on purpose: a loader for every module would slow every import to
    protect files that do not change during an evaluation."""
    from digline.cli.loader import SourceOnlyLoader
    from digline.cli.loader import load_suite as _load_suite

    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "faraway.py").write_text("VALUE = 1\n", encoding="utf-8")

    beside = tmp_path / "beside"
    beside.mkdir()
    (beside / "nearby.py").write_text("VALUE = 2\n", encoding="utf-8")
    (beside / "suite_two.py").write_text(
        "import faraway\n"
        "import nearby\n"
        "from digline.core import Contains\n"
        "from digline.run import Case, Suite\n"
        "\n"
        "suite = Suite(\n"
        "    tenant='acme', environment='dev', name='qa',\n"
        "    assertions=[Contains(needle='x')],\n"
        "    cases=[Case(id='one')],\n"
        ")\n",
        encoding="utf-8",
    )

    before = list(sys.path)
    sys.path.insert(0, str(elsewhere))
    try:
        _load_suite(str(beside / "suite_two.py"))
        # Beside the suite: read from disk, always.
        assert isinstance(sys.modules["nearby"].__loader__, SourceOnlyLoader)
        # Anywhere else: the normal machinery, cache and all.
        assert not isinstance(sys.modules["faraway"].__loader__, SourceOnlyLoader)
    finally:
        sys.path[:] = before
        for name in ("nearby", "faraway"):
            sys.modules.pop(name, None)


def test_a_suite_given_as_a_module_path_leaves_sys_path_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only a file path needs the treatment: `package.module:attr` is already
    importable, and widening the path for it would be reaching into the
    caller's environment for no reason."""
    from digline.cli.loader import UsageError as _UsageError
    from digline.cli.loader import load_suite as _load_suite

    before = list(sys.path)
    with pytest.raises(_UsageError):
        _load_suite("a_module_that_does_not_exist:suite")
    assert sys.path == before


def test_loading_twice_does_not_grow_sys_path(tmp_path: Path) -> None:
    """Several suites in one directory, or one loaded twice, must not make
    `sys.path` accumulate copies of the same entry."""
    from digline.cli.loader import load_suite as _load_suite

    write_suite(tmp_path)
    path = str(tmp_path.resolve())
    # Measured as a delta, not against global uniqueness: pytest's own sys.path
    # already carries a duplicate, and asserting on it would be testing pytest.
    before = list(sys.path)
    try:
        for _ in range(3):
            _load_suite(str(tmp_path / "suite_qa.py"))

        assert sys.path.count(path) == 1
        assert len(sys.path) == len(before) + 1
        assert sys.path[0] == path  # inserted at the front, like `python file.py`
    finally:
        sys.path[:] = before


def test_comparing_without_a_baseline_explains_the_next_step(repo: Path) -> None:
    key = run_key(repo)
    done = cli(
        repo, "compare", "--suite", "suite_qa.py", "--run", key, "--locale", "en"
    )
    assert done.returncode == EXIT_USAGE
    assert "has no baseline" in done.stderr
    assert "promote" in done.stderr


def test_promoting_a_run_that_could_not_judge_is_refused(repo: Path) -> None:
    write_suite(repo, extra=', Case(id="flaky")')
    key = run_key(repo)
    done = cli(repo, "promote", "--suite", "suite_qa.py", "--run", key)
    assert done.returncode == EXIT_USAGE
    assert "flaky" in done.stderr


# --------------------------------------------------------------------------- #
# --meta
# --------------------------------------------------------------------------- #


def test_meta_is_recorded_and_stays_payload_unless_disclosed(repo: Path) -> None:
    # The value carries a decimal point on purpose. An earlier version asserted
    # that the bare digits "1499" were absent from the report, and failed about
    # one run in a hundred: `created_at` carries microseconds, so a timestamp
    # like `…:01.149917+00:00` contains them. A flaky test is worse than no
    # test — it teaches the reader to rerun instead of to look.
    key = run_key(
        repo, "--meta", "model=claude-opus-5", "--meta", "account_balance=1499.55"
    )
    stored = json.loads(
        (repo / ".digline" / "acme-bank" / "runs" / "qa" / f"{key}.json").read_text(
            encoding="utf-8"
        )
    )
    assert stored["metadata"] == {
        "model": "claude-opus-5",
        "account_balance": "1499.55",
    }

    cli(repo, "promote", "--suite", "suite_qa.py", "--run", key)
    hidden = cli(
        repo,
        "report",
        "--suite",
        "suite_qa.py",
        "--run",
        key,
        "--locale",
        "en",
        "--redacted",
    ).stdout
    # The suite discloses `model` and nothing else.
    assert "account_balance" not in hidden
    assert "1499.55" not in hidden


def test_malformed_meta_is_refused(repo: Path) -> None:
    done = cli(repo, "run", "--suite", "suite_qa.py", "--meta", "nonsense")
    assert done.returncode == EXIT_USAGE
    assert "key=value" in done.stderr


# --------------------------------------------------------------------------- #
# Old schemas do not block a scan (friction 19)
# --------------------------------------------------------------------------- #


def runs_dir(root: Path) -> Path:
    return root / ".digline" / "acme-bank" / "runs" / "qa"


def downgrade(path: Path, to_version: int) -> None:
    """Turn a current document back into an older one, by removing exactly what
    that version added. The inverse of the migration, so the fixture and the
    code under test cannot both be wrong in the same direction."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    if to_version <= 5:
        raw.pop("aggregate", None)
    if to_version <= 4:
        for case in raw["results"]:
            case.pop("suspended", None)
            case.pop("suspended_reason", None)
    raw["schema_version"] = to_version
    path.write_text(json.dumps(raw, sort_keys=True, indent=2), encoding="utf-8")


def mixed_store(repo: Path) -> tuple[str, Path, Path]:
    """Three runs at three schemas: one current, one at 5, one at 4."""
    current = run_key(repo)
    older = run_key(repo)
    oldest = run_key(repo)
    assert len({current, older, oldest}) == 3, "keys must differ to file three runs"

    older_path = runs_dir(repo) / f"{older}.json"
    oldest_path = runs_dir(repo) / f"{oldest}.json"
    downgrade(older_path, 5)
    downgrade(oldest_path, 4)
    return current, older_path, oldest_path


def test_list_survives_a_store_with_three_schemas(repo: Path) -> None:
    """The scan is a survey. It steps over what it cannot read, and says so."""
    current, _older, _oldest = mixed_store(repo)
    done = cli(repo, "list", "--suite", "suite_qa.py")

    assert done.returncode == EXIT_OK, done.stderr
    assert current in done.stdout
    assert "ignored:" in done.stdout
    assert "schema 5" in done.stdout and "schema 4" in done.stdout
    assert "migrate" in done.stdout


def test_latest_resolves_over_the_readable_runs(repo: Path) -> None:
    """This is the failure that started the entry: `--run latest` died on
    yesterday's files, refusing a run nobody had asked for."""
    current, _older, _oldest = mixed_store(repo)
    cli(repo, "promote", "--suite", "suite_qa.py", "--run", current)

    done = cli(repo, "compare", "--suite", "suite_qa.py", "--run", "latest")
    assert done.returncode == EXIT_OK, done.stderr
    assert "ignored:" in done.stderr  # noted, and kept off stdout


def test_naming_an_old_run_explicitly_is_still_refused(repo: Path) -> None:
    """A scan steps over what it does not recognise; an explicitly named key
    does not. The caller asked for that file and must be told."""
    _current, older_path, _oldest = mixed_store(repo)
    done = cli(repo, "compare", "--suite", "suite_qa.py", "--run", older_path.stem)
    assert done.returncode != EXIT_OK
    assert "schema_version 5 is not supported" in done.stderr


def test_migrate_brings_them_all_forward_and_the_scan_stops_ignoring(
    repo: Path,
) -> None:
    current, older_path, oldest_path = mixed_store(repo)

    before = cli(repo, "list", "--suite", "suite_qa.py")
    assert "ignored:" in before.stdout
    assert older_path.stem not in before.stdout  # skipped, so not a row

    migrated = cli(repo, "migrate", "--suite", "suite_qa.py")
    assert migrated.returncode == EXIT_OK, migrated.stderr
    assert "from schema 5" in migrated.stdout
    assert "from schema 4" in migrated.stdout
    assert "0 refused" in migrated.stdout

    after = cli(repo, "list", "--suite", "suite_qa.py")
    assert after.returncode == EXIT_OK
    assert "ignored:" not in after.stdout
    # All three readable now, so all three are rows — named, not counted.
    for key in (current, older_path.stem, oldest_path.stem):
        assert key in after.stdout


def test_a_dry_run_writes_nothing(repo: Path) -> None:
    _current, older_path, _oldest = mixed_store(repo)
    before = older_path.read_text(encoding="utf-8")

    done = cli(repo, "migrate", "--suite", "suite_qa.py", "--dry-run")
    assert done.returncode == EXIT_OK
    assert "would migrate" in done.stdout
    assert older_path.read_text(encoding="utf-8") == before


def test_a_non_additive_bump_is_refused_with_what_is_missing(repo: Path) -> None:
    """Schema 3 predates `environment`. There is no value to invent, and
    inventing one would place a run in a perimeter it may not belong to."""
    key = run_key(repo)
    path = runs_dir(repo) / f"{key}.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw.pop("environment")
    raw["schema_version"] = 3
    path.write_text(json.dumps(raw, sort_keys=True), encoding="utf-8")

    done = cli(repo, "migrate", "--suite", "suite_qa.py")
    assert done.returncode == EXIT_USAGE
    assert "environment" in done.stderr
    assert "1 refused" in done.stdout
    # Refused, therefore untouched: still readable as the old document it was.
    assert json.loads(path.read_text(encoding="utf-8"))["schema_version"] == 3


def test_one_refusal_does_not_block_the_others(repo: Path) -> None:
    _current, older_path, oldest_path = mixed_store(repo)
    broken = runs_dir(repo) / "not-a-run.json"
    broken.write_text("{ this is not json", encoding="utf-8")

    done = cli(repo, "migrate", "--suite", "suite_qa.py")
    assert done.returncode == EXIT_USAGE
    assert "1 refused" in done.stdout
    for path in (older_path, oldest_path):
        # The current version, not a literal: every additive bump would
        # otherwise fail this test for a reason that has nothing to do with it.
        version = json.loads(path.read_text(encoding="utf-8"))["schema_version"]
        assert version == SCHEMA_VERSION


def test_the_baseline_is_migrated_too(repo: Path) -> None:
    """A baseline left behind would be unreadable the moment anything compared
    against it, which is every command that matters."""
    key = run_key(repo)
    cli(repo, "promote", "--suite", "suite_qa.py", "--run", key)
    baseline = repo / ".digline" / "acme-bank" / "baselines" / "qa.json"
    downgrade(baseline, 5)

    assert cli(repo, "compare", "--suite", "suite_qa.py", "--run", key).returncode != 0
    assert cli(repo, "migrate", "--suite", "suite_qa.py").returncode == EXIT_OK
    assert cli(repo, "compare", "--suite", "suite_qa.py", "--run", key).returncode == 0


def test_the_help_is_written_for_whoever_typed_it() -> None:
    """`--help` used to print the module's docstring.

    An architecture note — "the last layer, and the only one that touches the
    world" — rewrapped by argparse into a paragraph, and announcing four
    commands while listing seven. Whoever types `-h` wants to know what to type;
    whoever opens the file wants to know why the layer exists. Two audiences,
    two texts, and the reasons stay in the docstring and in `docs/adr/`.
    """
    # Through `sys.modules`: `digline.cli` re-exports the `main` *function*,
    # which shadows the `main` submodule on the package.
    import digline.cli.main  # noqa: F401  # pyright: ignore[reportUnusedImport]

    module = sys.modules["digline.cli.main"]
    helped = build_parser().format_help()

    assert "the last layer" not in helped
    assert "Four commands" not in helped
    assert module.__doc__ is not None
    # Not a paraphrase of the docstring either: nothing of it is reused.
    assert module.__doc__.strip().splitlines()[0] not in helped

    # What it does, and where to go next.
    assert "not got worse" in helped
    assert "digline <command> -h" in helped


def test_the_help_and_the_package_summary_say_the_same_thing() -> None:
    """A PyPI page and a terminal describing one tool two ways is one of them
    being out of date, and no way to tell which."""
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    summary = pyproject["project"]["description"]
    assert "baseline" in summary and "repo" in summary
    assert "worse" in build_parser().format_help()
