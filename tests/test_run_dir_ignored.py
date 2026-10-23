"""A run directory git would commit is said, and never refused. (#523)

`ensure_layout` writes `.digline/.gitignore` only where none exists. One the
user already had, without `*/runs/`, lets `git add` commit every run file —
written unredacted — and every journal of a run in flight, which names the
host it ran on (#478). Without `*/name-table/` it would commit the
re-identification key. Neither is refused: the user's file is theirs, and the
run is not wrong. The front end that wrote the run says so on stderr.

**Git decides, not a reading of the file.** `git check-ignore` answers for
every rule that applies — the `.gitignore` at the root, a pattern written
another way, a global excludes file — so a rule kept anywhere git reads is a
rule kept. Where git cannot answer (no repository, no git), nothing is said:
a warning about a commit nobody can make is noise.

**Asked after the run is written**, so the generated file exists by then: the
first run in a fresh repository writes the rules and says nothing.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from tests._helpers import cli, git, write_suite

from digline.host import unignored, unignored_notes

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git is needed")

TENANT = "acme"
GENERATED = "*/runs/\n*/name-table/\n"


def repository(tmp_path: Path) -> Path:
    git(tmp_path, "init", "-q")
    return tmp_path


def own_gitignore(root: Path, text: str) -> None:
    (root / ".digline").mkdir(exist_ok=True)
    (root / ".digline" / ".gitignore").write_text(text, encoding="utf-8")


def test_the_generated_rules_leave_nothing_to_say(tmp_path: Path) -> None:
    root = repository(tmp_path)
    own_gitignore(root, GENERATED)
    assert unignored(root, TENANT) == ()


def test_a_file_with_neither_rule_is_said_for_both(tmp_path: Path) -> None:
    root = repository(tmp_path)
    own_gitignore(root, "my-own-entry\n")
    assert unignored(root, TENANT) == ("*/runs/", "*/name-table/")


def test_the_name_table_is_said_when_only_runs_is_ignored(tmp_path: Path) -> None:
    """The file `test_store.py` keeps as the user wrote it: `*/runs/` and an
    entry of their own. The name table is the re-identification key."""
    root = repository(tmp_path)
    own_gitignore(root, "*/runs/\nmy-own-entry\n")
    assert unignored(root, TENANT) == ("*/name-table/",)


def test_a_rule_kept_elsewhere_in_another_form_is_a_rule_kept(tmp_path: Path) -> None:
    """Git is asked, not the file read: a rule at the repository's root, written
    another way, ignores the directories, and nothing is said."""
    root = repository(tmp_path)
    own_gitignore(root, "my-own-entry\n")
    (root / ".gitignore").write_text(
        ".digline/**/runs/\n.digline/**/name-table/\n", encoding="utf-8"
    )
    assert unignored(root, TENANT) == ()


def test_outside_a_repository_nothing_is_said(tmp_path: Path) -> None:
    own_gitignore(tmp_path, "my-own-entry\n")
    assert unignored(tmp_path, TENANT) == ()


def test_with_no_git_nothing_is_said(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = repository(tmp_path)
    own_gitignore(root, "my-own-entry\n")
    monkeypatch.setenv("PATH", str(tmp_path / "nowhere"))
    assert unignored(root, TENANT) == ()


def test_each_sentence_names_the_directory_the_rule_and_the_file() -> None:
    runs, table = unignored_notes(TENANT, ("*/runs/", "*/name-table/"))
    assert runs.startswith("git does not ignore .digline/acme/runs/")
    assert "unredacted" in runs and "`*/runs/`" in runs
    assert table.startswith("git does not ignore .digline/acme/name-table/")
    assert "re-identification key" in table and "`*/name-table/`" in table
    assert ".digline/.gitignore" in runs and ".digline/.gitignore" in table


# --- the command line -----------------------------------------------------------


def test_run_says_it_on_stderr_and_exits_as_it_would(tmp_path: Path) -> None:
    root = repository(tmp_path)
    write_suite(root)
    own_gitignore(root, "my-own-entry\n")
    done = cli(root, "run", "--suite", "suite_qa.py")
    assert done.returncode == 0, done.stderr
    assert "digline: git does not ignore .digline/acme-bank/runs/" in done.stderr
    assert "digline: git does not ignore .digline/acme-bank/name-table/" in done.stderr
    assert "git does not ignore" not in done.stdout


def test_the_first_run_of_a_fresh_repository_says_nothing(tmp_path: Path) -> None:
    """The control: the generated file is written by that run, and a check
    asked before it would warn on every first run."""
    root = repository(tmp_path)
    write_suite(root)
    done = cli(root, "run", "--suite", "suite_qa.py")
    assert done.returncode == 0, done.stderr
    assert "git does not ignore" not in done.stderr


def test_rejudge_says_it_too(tmp_path: Path) -> None:
    """A re-judge writes a run of its own into `runs/`, unredacted like any
    other, so it says what `run` says."""
    from tests.test_suite_notes import SUITE_PY

    root = repository(tmp_path)
    (root / "suite_noted.py").write_text(SUITE_PY, encoding="utf-8")
    source = cli(root, "run", "--suite", "suite_noted.py")
    assert source.returncode == 0, source.stderr
    assert "git does not ignore" not in source.stderr
    own_gitignore(root, "my-own-entry\n")
    done = cli(
        root, "rejudge", "--suite", "suite_noted.py", "--run", source.stdout.strip()
    )
    assert done.returncode == 0, done.stderr
    assert "digline: git does not ignore .digline/acme-bank/runs/" in done.stderr
    assert "digline: git does not ignore .digline/acme-bank/name-table/" in done.stderr


def test_rejudge_with_the_generated_rules_says_nothing(tmp_path: Path) -> None:
    from tests.test_suite_notes import SUITE_PY

    root = repository(tmp_path)
    (root / "suite_noted.py").write_text(SUITE_PY, encoding="utf-8")
    source = cli(root, "run", "--suite", "suite_noted.py").stdout.strip()
    done = cli(root, "rejudge", "--suite", "suite_noted.py", "--run", source)
    assert done.returncode == 0, done.stderr
    assert "git does not ignore" not in done.stderr
