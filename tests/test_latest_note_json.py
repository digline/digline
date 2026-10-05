"""`latest`'s note in the `--json` of `compare`, `diff` and `explain` (#433).

The CLI said it on stderr only, and MCP's tools of the same names return the
same object as these `--json`s, so the note goes into the object. stderr keeps
it too: a person at a terminal reads that, not the JSON.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from tests._helpers import baseline_in, cli, run_key


@pytest.fixture
def outrun(repo: Path) -> tuple[Path, str, str, str]:
    """Three runs, the newest promoted and then removed, so `latest` is the
    middle one and the baseline names a run nobody can read."""
    oldest, older, newer = run_key(repo), run_key(repo), run_key(repo)
    done = cli(
        repo,
        "promote",
        *("--replacing", baseline_in(repo), "--suite", "suite_qa.py"),
        *("--run", newer),
    )
    assert done.returncode == 0, done.stderr
    (found,) = (repo / ".digline").glob(f"*/runs/**/{newer}.json")
    found.unlink()
    return repo, oldest, older, newer


def newer_than(older: str, newer: str) -> str:
    return (
        f"the baseline was promoted from run {newer}, newer than {older}, "
        "and that run was not read here"
    )


@pytest.mark.parametrize("shape", ["--json", "--json=full"])
def test_compare_json_carries_it_in_both_shapes(
    outrun: tuple[Path, str, str, str], shape: str
) -> None:
    root, _oldest, older, newer = outrun
    done = cli(root, "compare", "--suite", "suite_qa.py", "--run", "latest", shape)

    assert json.loads(done.stdout)["note"] == newer_than(older, newer)
    assert f"note: {newer_than(older, newer)}" in done.stderr


def test_explain_json_carries_it(outrun: tuple[Path, str, str, str]) -> None:
    root, _oldest, older, newer = outrun
    done = cli(root, "explain", "--suite", "suite_qa.py", "--run", "latest", "--json")

    assert json.loads(done.stdout)["note"] == newer_than(older, newer)


def test_diff_json_puts_each_note_beside_its_key(
    outrun: tuple[Path, str, str, str],
) -> None:
    root, oldest, older, newer = outrun
    done = cli(
        root, "diff", "--suite", "suite_qa.py", "latest", oldest, "--json", "counts"
    )

    runs = json.loads(done.stdout)["runs"]
    assert (runs["left"]["key"], runs["left"]["note"]) == (
        older,
        newer_than(older, newer),
    )
    assert (runs["right"]["key"], runs["right"]["note"]) == (oldest, "")


def test_a_key_typed_by_hand_steps_over_nothing(
    outrun: tuple[Path, str, str, str],
) -> None:
    root, _oldest, older, _newer = outrun
    done = cli(root, "compare", "--suite", "suite_qa.py", "--run", older, "--json")

    assert json.loads(done.stdout)["note"] == ""
    assert "note:" not in done.stderr
