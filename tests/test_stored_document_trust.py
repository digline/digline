"""What a stored document may claim, and what it may not do by claiming it.

A run document is written by whoever holds the repository — a CI bundle, a
colleague's artifacts, a hand edit — so the reader treats it as input, not as
something digline wrote. Two findings of the standing-code security pass of
2026-09-23 are the two halves of that:

- **Finding 6, its shape.** A document of the wrong shape crashed the reader
  with a traceback and **exit 1**, which is `EXIT_WORSE`: to a gate, a
  corrupted file and a real regression were the same answer. It is now a
  refusal, exit 64, with the reason in the message.
- **Finding 7, its suite.** `promote_baseline` writes the baseline of the suite
  the *document* names. A run filed under `qa` that declared `"suite": "other"`
  overwrote `other`'s baseline, exit 0, silent. The tenant was already checked;
  the suite now is too.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from tests._helpers import cli, run_key

from digline.core.run import run_from_dict
from digline.store import FileResultStore, RunRef, SuiteMismatchError
from digline.wire.contract import EXIT_USAGE, EXIT_WORSE

STORE = Path(".digline") / "acme-bank"


def stored(repo: Path, key: str) -> Path:
    return repo / STORE / "runs" / "qa" / f"{key}.json"


def rewrite(path: Path, **fields: Any) -> None:
    document = json.loads(path.read_text(encoding="utf-8"))
    document.update(fields)
    path.write_text(json.dumps(document), encoding="utf-8")


#: Each one crashed the reader with `TypeError` or `AttributeError` before the
#: fix — measured, not imagined: thirteen shapes were tried and these nine are
#: the ones that reached a traceback. The other four were already refusals.
#:
#: **Each is one field away from a valid document**, and that is what makes
#: the test evidence: `rewrite` edits a real stored run, which the control at
#: the bottom of this file shows is accepted. A shape written from scratch can
#: stop at the first missing mandatory field and never reach the one it is
#: named after — a test of `results` that is really a test of `redacted`.
CRASHED: list[tuple[str, object]] = [
    ("results", 5),
    ("results", [5]),
    ("aggregate", 5),
    ("metadata", [1]),
    ("artifacts", [1]),
    ("artifacts", {"a": 5}),
    ("target_config", 5),
    ("resumed_at", 5),
    ("schema_version", None),
]


@pytest.mark.parametrize(("field", "value"), CRASHED)
def test_a_malformed_field_is_refused_and_never_reads_as_a_regression(
    repo: Path, field: str, value: object
) -> None:
    key = run_key(repo)
    rewrite(stored(repo, key), **{field: value})

    done = cli(repo, "compare", "--suite", "suite_qa.py", "--run", key)

    assert done.returncode == EXIT_USAGE, done.stderr
    assert done.returncode != EXIT_WORSE
    assert "Traceback" not in done.stderr
    assert "ValueError" in done.stderr


@pytest.mark.parametrize("command", ["compare", "explain"])
def test_a_document_that_is_not_an_object_is_refused_by_name(
    repo: Path, command: str
) -> None:
    key = run_key(repo)
    stored(repo, key).write_text("[]\n", encoding="utf-8")

    done = cli(repo, command, "--suite", "suite_qa.py", "--run", key)

    assert done.returncode == EXIT_USAGE, done.stderr
    assert "Traceback" not in done.stderr
    assert "is a JSON list, not an object" in done.stderr


def test_the_reader_refuses_without_a_front_end_too() -> None:
    """The rule lives in the core, where Plumbline and every driver meet it."""
    with pytest.raises(ValueError, match="not an object"):
        run_from_dict([])
    with pytest.raises(ValueError, match="does not have the shape of a run") as caught:
        run_from_dict({"schema_version": None})
    assert isinstance(caught.value.__cause__, TypeError)


def test_migrate_lists_a_malformed_document_as_refused_and_carries_on(
    repo: Path,
) -> None:
    """`migrate_paths` collects refusals so one bad file does not stop the rest;
    a malformed document crashed it instead, before the list was ever printed."""
    good = run_key(repo)
    bad = run_key(repo)
    stored(repo, bad).write_text("[]\n", encoding="utf-8")
    rewrite(stored(repo, good), schema_version=15)

    done = cli(repo, "migrate", "--suite", "suite_qa.py")

    assert done.returncode == EXIT_USAGE
    assert "Traceback" not in done.stderr
    assert (
        f"refused {bad}.json: the document is a JSON list, not an object" in done.stderr
    )
    assert f"migrated {good}.json from schema 15" in done.stdout


def test_a_run_declaring_another_suite_is_refused_and_promotes_nothing(
    repo: Path,
) -> None:
    key = run_key(repo)
    rewrite(stored(repo, key), suite="other")

    done = cli(repo, "promote", "--suite", "suite_qa.py", "--run", key)

    assert done.returncode == EXIT_USAGE, done.stdout
    assert "SuiteMismatchError" in done.stderr
    assert "declares suite 'other'" in done.stderr
    assert not (repo / STORE / "baselines").exists() or not list(
        (repo / STORE / "baselines").glob("*")
    )


def test_a_baseline_declaring_another_suite_is_refused(repo: Path) -> None:
    key = run_key(repo)
    promoted = cli(repo, "promote", "--suite", "suite_qa.py", "--run", key)
    assert promoted.returncode == 0, promoted.stderr
    rewrite(repo / STORE / "baselines" / "qa.json", suite="other")

    with pytest.raises(SuiteMismatchError, match="declares suite 'other'"):
        FileResultStore(repo).read_baseline("acme-bank", "qa")


def test_a_run_filed_where_it_says_it_belongs_is_untouched(repo: Path) -> None:
    """The control: every refusal above is worthless if the ordinary run and the
    ordinary promotion stopped working beside it."""
    key = run_key(repo)
    run = FileResultStore(repo).read_run(
        RunRef(tenant="acme-bank", suite="qa", key=key)
    )
    assert run.suite == "qa"
    done = cli(repo, "promote", "--suite", "suite_qa.py", "--run", key)
    assert done.returncode == 0, done.stderr
    assert (repo / STORE / "baselines" / "qa.json").is_file()
