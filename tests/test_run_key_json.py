"""The run a `--json` was read from, named in it: `run_key` (#448).

`compare --json` named its reference, `baseline_key`, and not the run it held
against it, so `compare --run latest` answered whether a run got worse without
saying which run. `explain --json` named neither, even in its `"comparison"`
scope, where it holds the run against the same reference `compare` does.

Both keys are derived from the documents that were read, never copied from
what the caller typed: a key typed by hand comes back as a confirmation of the
run digline used, which is worth having where the store is not the file store
that checks a name against its run.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from tests._helpers import baseline_in, cli, run_key


@pytest.fixture
def two_runs(repo: Path) -> tuple[Path, str, str]:
    """An older run promoted, then a newer one, so `latest` is not the
    reference and a `run_key` equal to `baseline_key` would be caught."""
    older = run_key(repo)
    done = cli(
        repo,
        "promote",
        *("--replacing", baseline_in(repo), "--suite", "suite_qa.py"),
        *("--run", older),
    )
    assert done.returncode == 0, done.stderr
    return repo, older, run_key(repo)


@pytest.mark.parametrize("shape", ["--json", "--json=full"])
def test_compare_names_the_run_latest_picked(
    two_runs: tuple[Path, str, str], shape: str
) -> None:
    root, older, newer = two_runs
    done = cli(root, "compare", "--suite", "suite_qa.py", "--run", "latest", shape)

    payload = json.loads(done.stdout)
    assert (payload["run_key"], payload["baseline_key"]) == (newer, older)


def test_compare_confirms_a_key_typed_by_hand(two_runs: tuple[Path, str, str]) -> None:
    root, older, _newer = two_runs
    done = cli(root, "compare", "--suite", "suite_qa.py", "--run", older, "--json")

    assert json.loads(done.stdout)["run_key"] == older


def test_explain_names_both_documents_of_a_comparison(
    two_runs: tuple[Path, str, str],
) -> None:
    root, older, newer = two_runs
    done = cli(root, "explain", "--suite", "suite_qa.py", "--run", "latest", "--json")

    payload = json.loads(done.stdout)
    assert payload["scope"] == "comparison"
    assert (payload["run_key"], payload["baseline_key"]) == (newer, older)


def test_explain_without_a_reference_names_only_the_run(repo: Path) -> None:
    """No reference was read, so there is no key to give it, and an absent
    `baseline_key` is the scope saying so rather than a `null` to interpret."""
    key = run_key(repo)
    done = cli(repo, "explain", "--suite", "suite_qa.py", "--run", "latest", "--json")

    payload = json.loads(done.stdout)
    assert payload["scope"] == "run"
    assert payload["run_key"] == key
    assert "baseline_key" not in payload
