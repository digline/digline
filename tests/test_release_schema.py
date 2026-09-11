"""Schema 10, and the rules ADR 0014 wrote for what may ride a bump.

Three passengers landed on one bump, so the thing worth testing is not any one
of them but the **conditions** they had to meet: the hash does not move, the
migration invents nothing, and the document says what wrote it without that
claim ever being manufactured.

The other half of this file is the sentence that only became possible with
schema 10: until then 9 was the ceiling of the world, so no released digline
had ever met a document written by a newer one.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from tests._helpers import cli, run_key

from digline import __version__
from digline.core import CaseResult, Contains, Score, Verdict, release_tuple
from digline.core.run import SCHEMA_VERSION, Run, run_from_json, run_to_json
from digline.store import FileResultStore
from digline.store.migrate import upgrade_document
from digline.store.protocol import Listing
from digline.wire import ahead_note, writer_ahead

CREATED = "2026-01-01T00:00:00+00:00"


def verdict(score: float = 0.9) -> Verdict:
    return Verdict(
        score=Score(name="contains", score=score),
        threshold=0.7,
        status="pass",
        reason="found it",
        assertion_id=Contains(needle="Rome").identity,
    )


def run(digline_version: str = "") -> Run:
    return Run(
        tenant="acme",
        environment="staging",
        suite="qa",
        config_hash="0123456789abcdef",
        created_at=CREATED,
        results=(CaseResult("one", (verdict(),)),),
        digline_version=digline_version,
    )


# --------------------------------------------------------------------------- #
# release_tuple — the comparison a string would have got wrong
# --------------------------------------------------------------------------- #


def test_ten_is_newer_than_nine() -> None:
    """The first case, because it is the whole reason the function exists: as
    strings, `"0.10.0" < "0.9.0"`, so a string comparison would have stopped
    warning at exactly the release after the one that introduced it."""
    assert release_tuple("0.10.0") > release_tuple("0.9.0")
    assert "0.10.0" < "0.9.0"  # noqa: PLR0133 — the trap, written out


@pytest.mark.parametrize("text", ["1.2.0", "1.2.0rc1", "1.2.0.post1", "1.2.0+local"])
def test_everything_after_the_release_segment_is_ignored(text: str) -> None:
    assert release_tuple(text) == (1, 2, 0)


@pytest.mark.parametrize("text", ["", "unknown", "dev"])
def test_an_unrecorded_version_is_never_ahead_of_anything(text: str) -> None:
    """`()` compares less than every real release, which is what keeps a
    document that records nothing from being read as a document from the
    future."""
    assert release_tuple(text) == ()
    assert not writer_ahead(text, "0.1.0")


# --------------------------------------------------------------------------- #
# the installed-behind warning
# --------------------------------------------------------------------------- #


def test_the_note_fires_only_upwards() -> None:
    assert ahead_note(["0.11.0"], "0.10.0")
    assert ahead_note(["0.10.0"], "0.10.0") == ""
    assert ahead_note(["0.9.0"], "0.10.0") == ""
    assert ahead_note([""], "0.10.0") == ""


def test_two_documents_produce_one_line_naming_the_newest() -> None:
    """A run and its baseline are two documents and one installation: the same
    sentence twice is a sentence that gets skimmed."""
    note = ahead_note(["0.11.0", "0.12.1", "0.9.0"], "0.10.0")
    assert note.count("written by digline") == 1
    assert "0.12.1" in note
    assert "0.11.0" not in note


def test_the_note_says_which_way_to_move() -> None:
    note = ahead_note(["0.11.0"], "0.10.0")
    assert "Upgrade digline" in note
    assert "never rewritten backwards" in note


# --------------------------------------------------------------------------- #
# the document says what wrote it — and only when it knows
# --------------------------------------------------------------------------- #


def test_the_version_round_trips() -> None:
    document = run(digline_version="0.10.0")
    assert run_from_json(run_to_json(document)).digline_version == "0.10.0"


def test_an_unrecorded_version_is_absent_rather_than_empty() -> None:
    """Absent, like every other unrecorded thing in this document: `""` would be
    a value where there is none, and a migrated file is exactly the case that
    has none."""
    raw = json.loads(run_to_json(run()))
    assert "digline_version" not in raw
    assert run_from_json(run_to_json(run())).digline_version == ""


def test_the_driver_stamps_it_and_a_hand_built_run_does_not(repo: Path) -> None:
    key = run_key(repo)
    stored = json.loads(
        (repo / ".digline" / "acme-bank" / "runs" / "qa" / f"{key}.json").read_text(
            encoding="utf-8"
        )
    )
    assert stored["digline_version"] == __version__
    assert stored["schema_version"] == SCHEMA_VERSION


def test_it_survives_redaction() -> None:
    """A fact about our own instrument, never about the end company: withholding
    it would buy no secrecy and would make a strange file unsupportable."""
    from digline.core import redact

    assert redact(run(digline_version="0.10.0")).digline_version == "0.10.0"


# --------------------------------------------------------------------------- #
# the migration invents nothing
# --------------------------------------------------------------------------- #


def nine() -> dict[str, object]:
    """A schema 9 document, as 0.9.0 wrote them."""
    raw = json.loads(run_to_json(run(digline_version="")))
    raw["schema_version"] = 9
    return raw


def test_the_step_leaves_the_version_absent() -> None:
    """Never the migrating version's own. A document rewritten by this release
    was not produced by it, and stamping it would be the invention
    `_add_configs` already refuses about the model that answered."""
    upgraded = upgrade_document(nine())
    assert upgraded["schema_version"] == SCHEMA_VERSION
    assert "digline_version" not in upgraded
    assert __version__ not in json.dumps(upgraded)
    assert run_from_json(json.dumps(upgraded)).digline_version == ""


def test_the_step_moves_no_hash_and_no_timestamp() -> None:
    """The condition the whole bump was checked against: a baseline promoted
    last month does not need promoting again, which is only true while the
    fingerprint of the suite is untouched by the upgrade."""
    before = nine()
    after = upgrade_document(before)
    assert after["config_hash"] == before["config_hash"]
    assert after["created_at"] == before["created_at"]


def test_a_migrated_run_still_promotes_under_the_hash_it_carries(
    tmp_path: Path,
) -> None:
    store = FileResultStore(tmp_path)
    document = run(digline_version="")
    ref = store.write_run(document)
    path = store.run_path(ref)
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["schema_version"] = 9
    raw.pop("digline_version", None)
    path.write_text(json.dumps(raw), encoding="utf-8")

    from digline.store.migrate import migrate_file

    assert migrate_file(path) == 9
    promoted = store.promote_baseline(ref, document.config_hash)
    assert promoted.config_hash == document.config_hash
    assert promoted.digline_version == ""


def test_a_newer_document_is_refused_rather_than_rewritten_backwards() -> None:
    from digline.store.migrate import NonAdditiveError

    ahead = nine()
    ahead["schema_version"] = SCHEMA_VERSION + 1
    with pytest.raises(NonAdditiveError, match="newer than this version"):
        upgrade_document(ahead)


# --------------------------------------------------------------------------- #
# the advice matches the direction — the sentence schema 10 made possible
# --------------------------------------------------------------------------- #


def test_older_documents_are_told_to_migrate() -> None:
    advice = Listing(runs=(), skipped={SCHEMA_VERSION - 1: 2}).advice()
    assert advice == ("run `digline migrate` to bring them up to date",)


def test_newer_documents_are_told_to_upgrade() -> None:
    """The line that was wrong for nine releases and could not be noticed:
    nothing rewrites a newer document backwards, so telling a reader to migrate
    tells them to do the one thing that cannot be done."""
    (line,) = Listing(runs=(), skipped={SCHEMA_VERSION + 1: 1}).advice()
    assert line.startswith("upgrade digline")
    assert "migrate" not in line


def test_a_store_can_owe_both_sentences() -> None:
    advice = Listing(
        runs=(), skipped={SCHEMA_VERSION - 1: 1, SCHEMA_VERSION + 1: 1}
    ).advice()
    assert len(advice) == 2


def test_the_listing_prints_the_direction_it_found(repo: Path) -> None:
    key = run_key(repo)
    path = repo / ".digline" / "acme-bank" / "runs" / "qa" / f"{key}.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["schema_version"] = SCHEMA_VERSION + 1
    path.write_text(json.dumps(raw), encoding="utf-8")

    done = cli(repo, "list", "--suite", "suite_qa.py")
    assert "upgrade digline" in done.stdout
    assert "digline migrate" not in done.stdout


def test_the_listing_still_says_migrate_for_an_older_one(repo: Path) -> None:
    key = run_key(repo)
    path = repo / ".digline" / "acme-bank" / "runs" / "qa" / f"{key}.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["schema_version"] = 5
    path.write_text(json.dumps(raw), encoding="utf-8")

    done = cli(repo, "list", "--suite", "suite_qa.py")
    assert "digline migrate" in done.stdout
    assert "upgrade digline" not in done.stdout


def test_the_warning_reaches_stderr_and_not_the_exit_code(repo: Path) -> None:
    """Never an exit code: the codes are a contract about the suite, and a
    tooling mismatch is not a verdict on a suite."""
    key = run_key(repo)
    promoted = cli(repo, "promote", "--suite", "suite_qa.py", "--run", key)
    assert promoted.returncode == 0, promoted.stderr

    for name in ("runs/qa/" + key, "baselines/qa"):
        path = repo / ".digline" / "acme-bank" / f"{name}.json"
        raw = json.loads(path.read_text(encoding="utf-8"))
        raw["digline_version"] = "99.0.0"
        path.write_text(json.dumps(raw), encoding="utf-8")

    done = cli(repo, "compare", "--suite", "suite_qa.py", "--run", key)
    assert done.returncode == 0, done.stderr
    assert done.stderr.count("written by digline 99.0.0") == 1
    assert "warning" not in done.stdout
