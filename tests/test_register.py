"""The register, held to ADR 0021.

The machine's memory is the operator's journal; the human's is this file. What is
tested is that a line of it is a person's decision beside the verdict it was
taken against, that nothing but counts and keys can be in it, that it is only
ever appended to, and that two branches can each add a line and still merge.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import fields
from pathlib import Path
from typing import Any

import pytest
from tests._helpers import cli, git, run_key, write_suite

from digline.cli import EXIT_OK, EXIT_USAGE
from digline.core import RegisterEntry
from digline.store import FileResultStore, RegisterRefusedError

SUITE = "suite_qa.py"


def promote_first(repo: Path) -> str:
    key = run_key(repo)
    done = cli(repo, "promote", "--suite", SUITE, "--run", key)
    assert done.returncode == EXIT_OK, done.stderr
    return key


def register_file(repo: Path) -> Path:
    return repo / ".digline" / "acme-bank" / "register" / "qa.jsonl"


def record(repo: Path, key: str, disposition: str) -> subprocess.CompletedProcess[str]:
    return cli(
        repo, "register", "--suite", SUITE, "--run", key, "--disposition", disposition
    )


def entries(repo: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in register_file(repo).read_text(encoding="utf-8").splitlines()
    ]


# --------------------------------------------------------------------------- #
# §2 — a command of its own, and the disposition is mandatory
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("arguments", [(), ("--disposition", "maybe")])
def test_the_disposition_is_mandatory(repo: Path, arguments: tuple[str, ...]) -> None:
    """Refused by the parser, and nothing is written. The exit code is argparse's
    own, as for every missing flag in the CLI — ADR 0021's test plan records why
    it is not 64."""
    promote_first(repo)
    key = run_key(repo)
    done = cli(repo, "register", "--suite", SUITE, "--run", key, *arguments)
    assert done.returncode != EXIT_OK
    assert "--disposition" in done.stderr
    assert not register_file(repo).exists()


@pytest.mark.parametrize("disposition", ["accepted", "rejected", "unsure"])
def test_each_disposition_writes_one_line(repo: Path, disposition: str) -> None:
    promote_first(repo)
    key = run_key(repo)
    done = record(repo, key, disposition)
    assert done.returncode == EXIT_OK, done.stderr
    (entry,) = entries(repo)
    assert entry["disposition"] == disposition
    assert entry["run"]["key"] == key
    assert "commit" in done.stdout


def test_no_baseline_means_nothing_to_have_decided_about(repo: Path) -> None:
    key = run_key(repo)
    done = record(repo, key, "rejected")
    assert done.returncode == EXIT_USAGE
    assert "no baseline" in done.stderr
    assert not register_file(repo).exists()


def test_an_unjudged_run_may_be_recorded(repo: Path) -> None:
    """Rejecting a run that could not be judged is a real act."""
    promote_first(repo)
    write_suite(repo, extra=', Case(id="flaky")')
    key = run_key(repo)
    done = record(repo, key, "rejected")
    assert done.returncode == EXIT_OK, done.stderr
    (entry,) = entries(repo)
    assert entry["exit_code"] == 2
    assert entry["outcome"]["unjudged"] >= 1


# --------------------------------------------------------------------------- #
# §3 — counts and keys, by type
# --------------------------------------------------------------------------- #


def test_the_entry_is_a_set_of_counts_and_keys(repo: Path) -> None:
    promote_first(repo)
    key = run_key(repo)
    record(repo, key, "accepted")
    (entry,) = entries(repo)
    assert set(entry) == {
        "register_version",
        "recorded_at",
        "digline_version",
        "disposition",
        "run",
        "baseline",
        "outcome",
        "exit_code",
    }
    assert set(entry["run"]) == {
        "key",
        "created_at",
        "config_hash",
        "environment",
        "digline_version",
        "rejudged",
    }
    assert set(entry["baseline"]) == {"key", "config_hash", "promoted_at"}
    assert set(entry["outcome"]) == {
        "regressed",
        "improved",
        "unchanged",
        "new",
        "missing",
        "errored",
        "unjudged",
        "suspended",
        "within_noise",
        "on_the_line",
        "worse",
        "canary_moved",
        "config_changed",
        "artifacts_changed",
        "target_config_changed",
        "judge_config_changed",
        "rejudged",
    }
    text = register_file(repo).read_text(encoding="utf-8")
    # A case id, and the judge's words, are in the run and never in the entry.
    for marker in ("capital-it", "capital-fr", "judged:"):
        assert marker not in text


def test_the_value_has_no_field_payload_could_occupy() -> None:
    names = {f.name for f in fields(RegisterEntry)}
    for forbidden in ("case_id", "cases", "reason", "note", "sentence", "author"):
        assert forbidden not in names


def test_the_verdict_is_the_gates(repo: Path) -> None:
    promote_first(repo)
    write_suite(repo, fr_score="0.2")
    key = run_key(repo)
    gate = cli(repo, "compare", "--suite", SUITE, "--run", key)
    record(repo, key, "rejected")
    (entry,) = entries(repo)
    assert entry["exit_code"] == gate.returncode == 1
    assert entry["outcome"]["worse"] is True
    assert entry["outcome"]["regressed"] >= 1


# --------------------------------------------------------------------------- #
# §5 — append, never rewrite
# --------------------------------------------------------------------------- #


def test_a_changed_mind_is_a_second_line_and_the_first_is_untouched(
    repo: Path,
) -> None:
    promote_first(repo)
    key = run_key(repo)
    record(repo, key, "rejected")
    before = register_file(repo).read_bytes()
    record(repo, key, "accepted")
    after = register_file(repo).read_bytes()
    assert after.startswith(before)
    read = FileResultStore(repo).read_register("acme-bank", "qa")
    assert [e.disposition for e in read.entries] == ["rejected", "accepted"]


def test_a_torn_tail_is_stated_and_nothing_is_appended_after_it(repo: Path) -> None:
    promote_first(repo)
    key = run_key(repo)
    record(repo, key, "rejected")
    with register_file(repo).open("a", encoding="utf-8") as handle:
        handle.write('{"register_version": 1, "rec')
    read = FileResultStore(repo).read_register("acme-bank", "qa")
    assert (len(read.entries), read.torn) == (1, True)

    before = register_file(repo).read_bytes()
    refused = record(repo, key, "accepted")
    assert refused.returncode == EXIT_USAGE
    assert "incomplete" in refused.stderr
    assert register_file(repo).read_bytes() == before


def test_a_hole_in_the_middle_is_refused_and_left(repo: Path) -> None:
    promote_first(repo)
    key = run_key(repo)
    record(repo, key, "rejected")
    record(repo, key, "accepted")
    first, second = register_file(repo).read_text(encoding="utf-8").splitlines()
    register_file(repo).write_text(f"{first}\n{{broken\n{second}\n", encoding="utf-8")
    before = register_file(repo).read_bytes()

    with pytest.raises(RegisterRefusedError, match="corrupt at line 2"):
        FileResultStore(repo).read_register("acme-bank", "qa")
    refused = record(repo, key, "unsure")
    assert refused.returncode == EXIT_USAGE
    assert register_file(repo).read_bytes() == before


def test_an_unknown_format_is_refused_and_left(repo: Path) -> None:
    promote_first(repo)
    key = run_key(repo)
    record(repo, key, "rejected")
    (entry,) = entries(repo)
    entry["register_version"] = 99
    register_file(repo).write_text(json.dumps(entry) + "\n", encoding="utf-8")
    before = register_file(repo).read_bytes()
    with pytest.raises(RegisterRefusedError, match="format 99"):
        FileResultStore(repo).read_register("acme-bank", "qa")
    assert record(repo, key, "accepted").returncode == EXIT_USAGE
    assert register_file(repo).read_bytes() == before


# --------------------------------------------------------------------------- #
# §4 — committed, and two branches merge
# --------------------------------------------------------------------------- #


def test_the_gitattributes_is_generated_and_never_overwritten(tmp_path: Path) -> None:
    fresh = FileResultStore(tmp_path / "fresh")
    fresh.ensure_layout("acme")
    generated = (tmp_path / "fresh" / ".digline" / ".gitattributes").read_text(
        encoding="utf-8"
    )
    assert "*/register/*.jsonl merge=union" in generated

    mine = tmp_path / "mine" / ".digline"
    mine.mkdir(parents=True)
    (mine / ".gitattributes").write_text("# mine\n", encoding="utf-8")
    FileResultStore(tmp_path / "mine").ensure_layout("acme")
    assert (mine / ".gitattributes").read_text(encoding="utf-8") == "# mine\n"


def test_two_branches_that_each_record_merge_without_a_conflict(repo: Path) -> None:
    promote_first(repo)
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "baseline")
    home = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--abbrev-ref", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    key = run_key(repo)

    git(repo, "checkout", "-q", "-b", "other")
    assert record(repo, key, "rejected").returncode == EXIT_OK
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "rejected on other")

    git(repo, "checkout", "-q", home)
    assert record(repo, key, "unsure").returncode == EXIT_OK
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "unsure at home")

    merged = subprocess.run(
        ["git", "-C", str(repo), "merge", "-q", "--no-edit", "other"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert merged.returncode == 0, merged.stdout + merged.stderr
    read = FileResultStore(repo).read_register("acme-bank", "qa")
    assert sorted(e.disposition for e in read.entries) == ["rejected", "unsure"]


# --------------------------------------------------------------------------- #
# §8 — the register reaches a reader through `log`
# --------------------------------------------------------------------------- #


def test_log_reads_the_register_and_carries_no_payload(repo: Path) -> None:
    baseline_key = promote_first(repo)
    key = run_key(repo)
    record(repo, key, "rejected")
    shown = cli(repo, "log", "--suite", SUITE, "--json")
    assert shown.returncode == EXIT_OK, shown.stderr
    document = json.loads(shown.stdout)
    (entry,) = document["register"]
    assert entry["disposition"] == "rejected"
    assert entry["baseline"]["key"] == baseline_key
    assert "register_version" not in entry
    for marker in ("capital-it", "capital-fr", "judged:"):
        assert marker not in shown.stdout
    text = cli(repo, "log", "--suite", SUITE)
    assert "rejected" in text.stdout


def test_the_register_is_read_where_no_run_is(repo: Path) -> None:
    """The runs are ignored and the register is committed: on a fresh clone the
    story of the alias is empty and the story of the reference is not."""
    promote_first(repo)
    key = run_key(repo)
    record(repo, key, "accepted")
    shutil.rmtree(repo / ".digline" / "acme-bank" / "runs")
    document = json.loads(cli(repo, "log", "--suite", SUITE, "--json").stdout)
    assert document["runs"] == 0
    assert len(document["register"]) == 1


def test_an_unreadable_register_is_stated_and_the_runs_are_still_read(
    repo: Path,
) -> None:
    promote_first(repo)
    key = run_key(repo)
    record(repo, key, "rejected")
    record(repo, key, "accepted")
    first, second = register_file(repo).read_text(encoding="utf-8").splitlines()
    register_file(repo).write_text(f"{first}\n{{broken\n{second}\n", encoding="utf-8")
    shown = cli(repo, "log", "--suite", SUITE, "--json")
    assert shown.returncode == EXIT_OK, shown.stderr
    document = json.loads(shown.stdout)
    assert document["register_unreadable"] is True
    assert document["register"] == []
    assert document["runs"] == 2
