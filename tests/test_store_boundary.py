"""Where a checked name leads.

0.7.1 checked the run **key** like the other two path segments, which closed
`?run=../../../../elsewhere`. It proved the name was one safe segment. It could
not prove where that name *led*, and nothing else did either: a symlink placed
inside `.digline/` under a perfectly legal key

    .digline/acme/runs/qa/planted-key.json -> ../../../../outside/evil.json

passed every check, and `digline view` answered 200 with the outside document
rendered, `digline compare --run planted-key` reported on it, and the MCP
`get_run` returned it to an agent. Found by the adversarial pass over the 0.7.1
fixes.

Writing that symlink needs write access inside the repository, which for the
developer sitting in it is no new power. It is not their threat: it is a run
directory whose contents came from somewhere else — a CI bundle, a colleague's
artifacts, the bridge — and `SECURITY.md` puts "a path escaping the working
directory" in scope without asking who put it there.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from tests._helpers import cli, run_key

from digline.store import FileResultStore, RunRef


@pytest.fixture
def planted(repo: Path) -> tuple[Path, str]:
    """A repository with a real run, a promoted baseline, and a run-shaped
    document outside the store that a link points at."""
    key = run_key(repo)
    cli(repo, "promote", "--suite", "suite_qa.py", "--run", key)
    stored = next((repo / ".digline").rglob(f"runs/qa/{key}.json"))

    outside = repo.parent / "outside.json"
    document = json.loads(stored.read_text(encoding="utf-8"))
    document["environment"] = "exfiltrated"
    outside.write_text(json.dumps(document), encoding="utf-8")

    link = stored.parent / "planted-key.json"
    link.symlink_to(outside)
    # The link really does reach the planted document: without this the
    # refusals below would also pass if the symlink were simply broken.
    assert link.is_file()
    assert json.loads(link.read_text(encoding="utf-8"))["environment"] == "exfiltrated"
    return repo, key


def test_the_store_refuses_a_run_that_links_out(planted: tuple[Path, str]) -> None:
    repo, _key = planted
    store = FileResultStore(repo)
    with pytest.raises(ValueError, match="outside") as caught:
        store.read_run(RunRef(tenant="acme-bank", suite="qa", key="planted-key"))
    assert "planted-key.json" in str(caught.value)


def test_the_store_refuses_a_baseline_that_links_out(planted: tuple[Path, str]) -> None:
    """The baseline is read by every comparison, so it is the same door."""
    repo, _key = planted
    baseline = repo / ".digline" / "acme-bank" / "baselines" / "qa.json"
    outside = repo.parent / "outside.json"
    baseline.unlink()
    baseline.symlink_to(outside)
    store = FileResultStore(repo)
    with pytest.raises(ValueError, match="outside"):
        store.read_baseline("acme-bank", "qa")


def test_the_scan_counts_a_linked_out_run_unreadable_rather_than_opening_it(
    planted: tuple[Path, str],
) -> None:
    """`scan_runs` opens each file to read its schema version, so it is a read
    of the same kind and gets the same rule."""
    repo, key = planted
    listing = FileResultStore(repo).scan_runs("acme-bank", "qa")
    assert [ref.key for ref in listing.runs] == [key]
    assert "planted-key.json" in listing.unreadable


def test_a_store_reached_through_a_symlink_still_works(repo: Path) -> None:
    """Both sides are resolved, so a `.digline` that is itself a link — a store
    kept on another volume — is not what this refuses."""
    key = run_key(repo)
    real = repo / ".digline"
    moved = repo.parent / "store-elsewhere"
    real.rename(moved)
    real.symlink_to(moved)
    run = FileResultStore(repo).read_run(
        RunRef(tenant="acme-bank", suite="qa", key=key)
    )
    assert run.tenant == "acme-bank"


def test_the_cli_refuses_it_too(planted: tuple[Path, str]) -> None:
    repo, _key = planted
    done = cli(
        repo,
        "compare",
        "--suite",
        "suite_qa.py",
        "--run",
        "planted-key",
        "--locale",
        "en",
    )
    assert done.returncode != 0
    assert "outside" in done.stderr
    assert "exfiltrated" not in done.stdout


def test_an_ordinary_run_is_untouched(planted: tuple[Path, str]) -> None:
    """The control. Every refusal above is worthless if the real key stopped
    working beside it."""
    repo, key = planted
    done = cli(
        repo, "compare", "--suite", "suite_qa.py", "--run", key, "--locale", "en"
    )
    assert done.returncode == 0, done.stderr


def _older(path: Path) -> bytes:
    """Make a run-shaped document one schema behind, so `migrate` would rewrite
    it, and return its bytes: the write-through needs an older schema to fire,
    and the assertion is that those bytes never change."""
    document = json.loads(path.read_text(encoding="utf-8"))
    document["schema_version"] = document["schema_version"] - 1
    path.write_text(json.dumps(document), encoding="utf-8")
    return path.read_bytes()


def test_migrate_refuses_a_run_that_links_out_and_writes_nothing(
    planted: tuple[Path, str],
) -> None:
    """`run_paths` was the one lister with no `_inside`, and its caller writes:
    `migrate` read the planted document through the link and wrote the upgraded
    one back through it, outside the repository, exit 0, reported as an
    ordinary "migrated planted-key.json". (Security pass of 2026-09-23,
    finding 3.)"""
    repo, _key = planted
    outside = repo.parent / "outside.json"
    before = _older(outside)

    done = cli(repo, "migrate", "--suite", "suite_qa.py")

    assert done.returncode == 64, done.stdout
    assert "planted-key.json" in done.stderr
    assert "outside" in done.stderr
    assert "migrated" not in done.stdout
    assert outside.read_bytes() == before


def test_migrate_refuses_a_baseline_that_links_out_and_writes_nothing(
    planted: tuple[Path, str],
) -> None:
    """The baseline had the same gap one line below: `migrate` appended it after
    only an `exists()`."""
    repo, _key = planted
    (repo / ".digline" / "acme-bank" / "runs" / "qa" / "planted-key.json").unlink()
    baseline = repo / ".digline" / "acme-bank" / "baselines" / "qa.json"
    outside = repo.parent / "outside.json"
    before = _older(outside)
    baseline.unlink()
    baseline.symlink_to(outside)

    done = cli(repo, "migrate", "--suite", "suite_qa.py")

    assert done.returncode == 64, done.stdout
    assert "qa.json" in done.stderr
    assert "outside" in done.stderr
    assert outside.read_bytes() == before


def test_migrate_still_migrates_an_ordinary_older_run(repo: Path) -> None:
    """The control: the refusal is of the link, not of migrating."""
    key = run_key(repo)
    stored = next((repo / ".digline").rglob(f"runs/qa/{key}.json"))
    _older(stored)

    done = cli(repo, "migrate", "--suite", "suite_qa.py")

    assert done.returncode == 0, done.stderr
    assert f"migrated {key}.json" in done.stdout
