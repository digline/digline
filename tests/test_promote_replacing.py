"""A promotion names the reference it replaces, and is refused when that
reference moved. (ADR 0031)

Found by kantorcodes1, reading `promote`'s code from a post about something
else: `promote_baseline` rewrote the baseline without looking at the one it
replaced, so two people who compared two runs against one reference and both
promoted lost the first promotion without either of them being told.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest
from tests._helpers import baseline_in, cli, run_key

from digline.core import (
    NO_BASELINE,
    CaseResult,
    Run,
    Score,
    Verdict,
    key_of,
)
from digline.store import (
    BaselineMovedError,
    ErroredRunError,
    FileResultStore,
    RunRef,
)

CFG = "hash-a"
SIGNED = "2026-01-02T09:00:00+00:00"


def run(created_at: str, *, status: str = "pass") -> Run:
    return Run(
        tenant="acme",
        environment="test",
        suite="qa",
        config_hash=CFG,
        created_at=created_at,
        results=(
            CaseResult(
                "case-1",
                (
                    Verdict(
                        score=Score(
                            name="contains", score=None if status == "error" else 1.0
                        ),
                        threshold=1.0,
                        tolerance=0.0,
                        status=status,  # type: ignore[arg-type]
                        reason="found",
                    ),
                ),
            ),
        ),
    )


def stored(store: FileResultStore, created_at: str, *, status: str = "pass") -> RunRef:
    return store.write_run(run(created_at, status=status))


def promote(
    store: FileResultStore, ref: RunRef, expected: str | None, *, at: str = SIGNED
) -> Run:
    return store.promote_baseline(ref, CFG, expected_baseline=expected, promoted_at=at)


# --------------------------------------------------------------------------- #
# The lost update, and the three shapes of the refusal
# --------------------------------------------------------------------------- #


def test_the_second_of_two_promotions_against_one_reference_is_refused(
    tmp_path: Path,
) -> None:
    """The reader's scenario, whole. Both people compared against the first
    reference; the first to promote wins, and the second is told rather than
    silently replacing a reference nobody compared their run against."""
    store = FileResultStore(tmp_path)
    first = stored(store, "2026-01-01T10:00:00+00:00")
    promote(store, first, None)

    theirs = stored(store, "2026-01-01T11:00:00+00:00")
    mine = stored(store, "2026-01-01T12:00:00+00:00")
    promote(store, theirs, first.key)

    with pytest.raises(BaselineMovedError) as refused:
        promote(store, mine, first.key)

    message = str(refused.value)
    assert f"compared against baseline {first.key}" in message
    assert f"is now {theirs.key} (promoted {SIGNED})" in message
    assert f"--replacing {theirs.key}" in message
    # The refusal is real, not cosmetic: the reference is still theirs.
    current = store.read_baseline("acme", "qa")
    assert current is not None and store.key_for(current) == theirs.key


def test_none_is_refused_when_a_baseline_exists(tmp_path: Path) -> None:
    """`none` is not a wildcard: it states that nothing is there."""
    store = FileResultStore(tmp_path)
    theirs = stored(store, "2026-01-01T10:00:00+00:00")
    promote(store, theirs, None)
    mine = stored(store, "2026-01-01T11:00:00+00:00")

    with pytest.raises(BaselineMovedError) as refused:
        promote(store, mine, None)
    message = str(refused.value)
    assert "--replacing none says suite 'qa' has no baseline yet" in message
    assert f"it has one: {theirs.key} (promoted {SIGNED})" in message


def test_a_baseline_that_vanished_is_refused_and_sent_to_git(tmp_path: Path) -> None:
    store = FileResultStore(tmp_path)
    first = stored(store, "2026-01-01T10:00:00+00:00")
    promote(store, first, None)
    store.baseline_path("acme", "qa").unlink()
    mine = stored(store, "2026-01-01T11:00:00+00:00")

    with pytest.raises(BaselineMovedError) as refused:
        promote(store, mine, first.key)
    message = str(refused.value)
    assert f"compared against baseline {first.key}" in message
    assert "is no longer there" in message
    assert "git log -- " in message
    assert not store.baseline_path("acme", "qa").exists()


def test_an_unrecorded_signature_is_left_out_rather_than_guessed(
    tmp_path: Path,
) -> None:
    """A baseline promoted before `promoted_at` existed was signed at a time
    nobody wrote down; the refusal says nothing about when. (ADR 0014 §3)"""
    store = FileResultStore(tmp_path)
    old = stored(store, "2026-01-01T10:00:00+00:00")
    promote(store, old, None, at="")
    mine = stored(store, "2026-01-01T11:00:00+00:00")

    with pytest.raises(BaselineMovedError) as refused:
        promote(store, mine, None)
    assert f"it has one: {old.key}. " in str(refused.value)
    assert "(promoted" not in str(refused.value)


# --------------------------------------------------------------------------- #
# What goes through
# --------------------------------------------------------------------------- #


def test_the_first_promotion_says_none_and_goes_through(tmp_path: Path) -> None:
    store = FileResultStore(tmp_path)
    first = stored(store, "2026-01-01T10:00:00+00:00")
    promote(store, first, None)
    assert baseline_in(tmp_path) == first.key


def test_naming_the_reference_that_is_there_goes_through(tmp_path: Path) -> None:
    store = FileResultStore(tmp_path)
    first = stored(store, "2026-01-01T10:00:00+00:00")
    promote(store, first, None)
    second = stored(store, "2026-01-01T11:00:00+00:00")
    promote(store, second, first.key)
    assert baseline_in(tmp_path) == second.key


def test_a_migrated_baseline_is_the_same_reference(tmp_path: Path) -> None:
    """New bytes, same key. `digline migrate` rewrites every committed baseline
    when the schema moves, and a comparison made before an upgrade still names
    the same reference after it. This is the control that fails if the check
    ever moves onto a digest of the file."""
    store = FileResultStore(tmp_path)
    first = stored(store, "2026-01-01T10:00:00+00:00")
    promote(store, first, None)
    path = store.baseline_path("acme", "qa")
    document = json.loads(path.read_text(encoding="utf-8"))
    rewritten = json.dumps(document, indent=4, sort_keys=False)
    assert rewritten != path.read_text(encoding="utf-8")
    path.write_text(rewritten, encoding="utf-8")

    second = stored(store, "2026-01-01T11:00:00+00:00")
    promote(store, second, first.key)
    assert baseline_in(tmp_path) == second.key


def test_the_check_runs_after_the_refusals_about_the_run(tmp_path: Path) -> None:
    """A run that would be refused whatever the reference is refused for
    itself: sending that person to compare again first would send them round
    twice. (ADR 0031 §2)"""
    store = FileResultStore(tmp_path)
    theirs = stored(store, "2026-01-01T10:00:00+00:00")
    promote(store, theirs, None)
    broken = stored(store, "2026-01-01T11:00:00+00:00", status="error")

    with pytest.raises(ErroredRunError):
        promote(store, broken, NO_BASELINE)


# --------------------------------------------------------------------------- #
# The key, printed where a person reads a comparison
# --------------------------------------------------------------------------- #


def test_the_key_is_the_one_every_other_surface_uses() -> None:
    document = run("2026-01-01T10:00:00.123456+00:00")
    assert key_of(document.created_at, document.config_hash) == FileResultStore.key_for(
        document
    )
    assert key_of(document.created_at, document.config_hash) != NO_BASELINE


def test_compare_names_the_baseline_it_compared_against(repo: Path) -> None:
    first = run_key(repo)
    promoted = cli(
        repo, "promote", "--suite", "suite_qa.py", "--run", first, "--replacing", "none"
    )
    assert promoted.returncode == 0, promoted.stderr
    second = run_key(repo)

    text = cli(repo, "compare", "--suite", "suite_qa.py", "--run", second)
    assert f"against baseline {first}" in text.stdout.splitlines()

    as_json = cli(repo, "compare", "--suite", "suite_qa.py", "--run", second, "--json")
    assert json.loads(as_json.stdout)["baseline_key"] == first

    # And it is the key `promote --replacing` accepts: the loop a person runs.
    again = cli(
        repo,
        "promote",
        "--suite",
        "suite_qa.py",
        "--run",
        second,
        "--replacing",
        json.loads(as_json.stdout)["baseline_key"],
    )
    assert again.returncode == 0, again.stderr


def test_replacing_is_mandatory_on_the_command_line(repo: Path) -> None:
    """Absent would mean unchecked, and unchecked in the ordinary case is where
    the lost update happens. argparse refuses it and names the flag."""
    key = run_key(repo)
    done = cli(repo, "promote", "--suite", "suite_qa.py", "--run", key)
    assert done.returncode != 0
    assert "--replacing" in done.stderr
    assert not list((repo / ".digline").glob("*/baselines/*.json"))


def test_the_help_states_the_guarantee_and_its_limit(repo: Path) -> None:
    """Both halves, because a reader who meets only the first trusts the check
    for more than it does. (ADR 0031 §3)"""
    helped = " ".join(cli(repo, "promote", "--help").stdout.split())
    assert "never silent" in helped
    assert "without comparing again, still does it" in helped


def test_the_view_form_carries_the_baseline_the_page_was_drawn_against() -> None:
    from digline.report import runs_page

    baseline = replace(run("2026-01-01T10:00:00+00:00"), promoted_at=SIGNED)
    other = run("2026-01-01T11:00:00+00:00")
    reference = key_of(baseline.created_at, baseline.config_hash)
    page = runs_page(
        [
            (reference, baseline),
            (key_of(other.created_at, other.config_hash), other),
        ],
        baseline_key=reference,
        config_hash=CFG,
        locale="en",
        suite="qa",
        allow_promote=True,
    )
    assert f'name="replacing" value="{reference}"' in page
