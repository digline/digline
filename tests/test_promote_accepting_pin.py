"""A promotion is refused while a pin is a cause of 2, unless it names the paths.

Before this, accepting a drifted pin was done by promoting: the drifted run
became the reference and the next comparison was green, and nothing recorded
that anybody had looked at the file. A pin never blocked a promotion (ADR 0051,
*Context*). Now the write step refuses a run that would exit 2 for a pin —
drifted or lost — and lets it through only when `--accepting-pin` names exactly
the paths the comparison implicates. (#483)

It is any cause of 2 and not *the exit code is 2*: a regression outranks every
cause of 2, so a run that drifted and got worse exits 1, and its pin is no less
unaccepted for that.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from tests._helpers import baseline_in, cli, hand_over, run_key

from digline.core import (
    Artifact,
    CaseResult,
    Run,
    Score,
    Verdict,
    compare,
    key_of,
)
from digline.host import REFUSALS
from digline.report import headline
from digline.store import FileResultStore, RunRef
from digline.wire import exit_code

CFG = "hash-a"
SIGNED = "2026-01-02T09:00:00+00:00"

#: Paths carry `underwriting`, the token `tests/test_artifacts.py` uses: no
#: tenant, suite or boilerplate string shares it, so finding it in a message
#: means the message named the path.
OLD = "eval/d1/underwriting-tools.json"
NEW = "eval/d2/underwriting-tools.json"
OTHER = "eval/d3/underwriting-rules.json"

PASSED = CaseResult(
    "judged",
    (
        Verdict(
            score=Score(name="contains", score=1.0),
            threshold=1.0,
            status="pass",
            reason="found",
            assertion_id="contains-1",
        ),
    ),
)

#: The same case judged worse: with a reference that passed it, `worse`.
FAILED = CaseResult(
    "judged",
    (
        Verdict(
            score=Score(name="contains", score=0.0),
            threshold=1.0,
            status="fail",
            reason="missing",
            assertion_id="contains-1",
        ),
    ),
)


def a_run(
    created_at: str,
    pinned: tuple[str, ...],
    *,
    results: tuple[CaseResult, ...] = (PASSED,),
    **artifacts: Artifact,
) -> Run:
    return Run(
        tenant="acme",
        environment="test",
        suite="qa",
        config_hash=CFG,
        created_at=created_at,
        results=results,
        artifacts=dict(artifacts),
        pinned=pinned,
    )


def v(text: str) -> Artifact:
    """An artifact whose digest follows its text, so two texts are two files."""
    return Artifact(sha=(text.encode().hex() * 64)[:64], text=text)


def promote(
    store: FileResultStore,
    ref: RunRef,
    expected: str | None,
    *,
    accepting: frozenset[str] = frozenset(),
) -> Run:
    return store.promote_baseline(
        ref,
        CFG,
        expected_baseline=expected,
        declared=None,
        promoted_at=SIGNED,
        accepting_pins=accepting,
    )


def with_a_reference(store: FileResultStore, reference: Run) -> RunRef:
    """`reference` promoted as the first baseline of the suite."""
    ref = store.write_run(reference)
    promote(store, ref, None)
    return ref


def current_key(store: FileResultStore) -> str:
    current = store.read_baseline("acme", "qa")
    assert current is not None
    return key_of(current.created_at, current.config_hash)


# Two reference/run pairs, one per pin cause. Built fresh in each test so a
# store is never shared.


def drifted(store: FileResultStore) -> tuple[RunRef, RunRef]:
    """OLD pinned on both sides, and its text moved: `pinned_drifted`."""
    reference = with_a_reference(
        store, a_run("2026-01-01T10:00:00+00:00", (OLD,), **{OLD: v("v1")})
    )
    run = store.write_run(a_run("2026-01-01T11:00:00+00:00", (OLD,), **{OLD: v("v2")}))
    return reference, run


def lost(store: FileResultStore) -> tuple[RunRef, RunRef]:
    """OLD pinned and gone, NEW pinned with no reference: `pinned_lost`, and
    the paths it implicates are both of them. (ADR 0051 §3)"""
    reference = with_a_reference(
        store, a_run("2026-01-01T10:00:00+00:00", (OLD,), **{OLD: v("v1")})
    )
    run = store.write_run(a_run("2026-01-01T11:00:00+00:00", (NEW,), **{NEW: v("v2")}))
    return reference, run


def refusal_of(
    store: FileResultStore, run: RunRef, reference: RunRef, **kw: object
) -> str:
    """The refusal's sentence, after checking it is a refusal a front end shows
    and that the reference did not move."""
    with pytest.raises(REFUSALS) as refused:
        promote(store, run, reference.key, **kw)  # type: ignore[arg-type]
    assert type(refused.value).__name__ == "UnacceptedPinsError", (
        f"refused with {type(refused.value).__name__}: {refused.value}"
    )
    assert current_key(store) == reference.key, "the refusal was cosmetic"
    return str(refused.value)


# --------------------------------------------------------------------------- #
# 1. The refusal, on each pin cause
# --------------------------------------------------------------------------- #


def test_a_drifted_pin_refuses_the_promotion_and_names_the_path(
    tmp_path: Path,
) -> None:
    store = FileResultStore(tmp_path)
    reference, run = drifted(store)
    message = refusal_of(store, run, reference)
    assert message.startswith(f"run {run.key} was not promoted: "), message
    assert OLD in message
    assert f"--accepting-pin {OLD}" in message


def test_a_lost_pin_refuses_the_promotion_and_names_both_paths(
    tmp_path: Path,
) -> None:
    store = FileResultStore(tmp_path)
    reference, run = lost(store)
    message = refusal_of(store, run, reference)
    assert message.startswith(f"run {run.key} was not promoted: "), message
    for path in (OLD, NEW):
        assert f"--accepting-pin {path}" in message, message


# --------------------------------------------------------------------------- #
# 2. The authorisation, with the set the comparison implicates
# --------------------------------------------------------------------------- #


def test_accepting_the_drifted_path_promotes(tmp_path: Path) -> None:
    store = FileResultStore(tmp_path)
    reference, run = drifted(store)
    promote(store, run, reference.key, accepting=frozenset({OLD}))
    assert current_key(store) == run.key


def test_accepting_both_paths_of_a_lost_pin_promotes(tmp_path: Path) -> None:
    store = FileResultStore(tmp_path)
    reference, run = lost(store)
    promote(store, run, reference.key, accepting=frozenset({OLD, NEW}))
    assert current_key(store) == run.key


# --------------------------------------------------------------------------- #
# 3. Anything but the exact set is refused, and the refusal names the set
# --------------------------------------------------------------------------- #


def test_one_path_more_than_the_comparison_implicates_is_refused(
    tmp_path: Path,
) -> None:
    """Accepting a file that did not drift is accepting nothing anybody looked
    at: the authorisation says what was read, so it must be what moved."""
    store = FileResultStore(tmp_path)
    reference, run = drifted(store)
    message = refusal_of(store, run, reference, accepting=frozenset({OLD, OTHER}))
    assert f"--accepting-pin {OLD}" in message, message
    assert OTHER in message, f"the extra path is not named: {message}"


def test_one_path_fewer_than_the_comparison_implicates_is_refused(
    tmp_path: Path,
) -> None:
    """Half of a lost pin is not the lost pin: the two paths are one fact."""
    store = FileResultStore(tmp_path)
    reference, run = lost(store)
    message = refusal_of(store, run, reference, accepting=frozenset({OLD}))
    for path in (OLD, NEW):
        assert f"--accepting-pin {path}" in message, message


def test_a_wrong_path_in_place_of_the_right_one_is_refused(tmp_path: Path) -> None:
    store = FileResultStore(tmp_path)
    reference, run = drifted(store)
    message = refusal_of(store, run, reference, accepting=frozenset({OTHER}))
    assert f"--accepting-pin {OLD}" in message, message
    assert OTHER in message, f"the wrong path is not named: {message}"


# --------------------------------------------------------------------------- #
# 4. The first promotion has nothing to compare against, so nothing changes
# --------------------------------------------------------------------------- #


def test_the_first_promotion_of_a_pinning_run_is_unchanged(tmp_path: Path) -> None:
    """`--replacing none`: no reference, no comparison, no pin cause."""
    store = FileResultStore(tmp_path)
    first = store.write_run(
        a_run("2026-01-01T10:00:00+00:00", (OLD,), **{OLD: v("v1")})
    )
    promote(store, first, None)
    assert current_key(store) == first.key


# --------------------------------------------------------------------------- #
# 5. Any cause of 2, not the exit code 2
# --------------------------------------------------------------------------- #


def test_a_drift_beside_a_regression_is_refused_though_it_exits_one(
    tmp_path: Path,
) -> None:
    """The case the ruling names. A regression outranks every cause of 2, so
    this comparison exits 1; a refusal that read `exit_code == 2` would let
    the drift through with the regression."""
    store = FileResultStore(tmp_path)
    reference = with_a_reference(
        store, a_run("2026-01-01T10:00:00+00:00", (OLD,), **{OLD: v("v1")})
    )
    worse = a_run(
        "2026-01-01T11:00:00+00:00", (OLD,), results=(FAILED,), **{OLD: v("v2")}
    )
    run = store.write_run(worse)

    baseline = store.read_baseline("acme", "qa")
    assert baseline is not None
    comparison = compare(worse, baseline)
    head = headline(comparison, worse, baseline, locale="en", declared=None)
    assert exit_code(head) == 1, "the fixture must exit 1, or it tests nothing"
    assert comparison.pinned_drifted

    message = refusal_of(store, run, reference)
    assert f"--accepting-pin {OLD}" in message, message


# --------------------------------------------------------------------------- #
# Where it sits: after condition 8
# --------------------------------------------------------------------------- #


def test_a_moved_baseline_is_refused_before_the_pin_is_read(tmp_path: Path) -> None:
    """In the write step after 8, by the ruling: a pin read against a reference
    that is no longer the one compared against would name paths nobody saw."""
    store = FileResultStore(tmp_path)
    reference, run = drifted(store)
    theirs = store.write_run(
        a_run("2026-01-01T12:00:00+00:00", (OLD,), **{OLD: v("v1")})
    )
    promote(store, theirs, reference.key)
    with pytest.raises(REFUSALS) as refused:
        promote(store, run, reference.key)
    assert type(refused.value).__name__ == "BaselineMovedError", refused.value


# --------------------------------------------------------------------------- #
# The command line and the view, over a real repository
# --------------------------------------------------------------------------- #

PROMPT = "prompts/underwriting-system.md"


def planted(repo: Path) -> tuple[str, str]:
    """A reference pinning PROMPT, promoted, and a run where PROMPT moved.

    Planted from a real run of the standard suite, so the configuration in
    force is the one both carry; only the artifacts are added. Returns the two
    keys."""
    real = run_key(repo)
    store = FileResultStore(repo)
    measured = store.read_run(RunRef(tenant="acme-bank", suite="qa", key=real))
    reference = store.write_run(
        replace(measured, artifacts={PROMPT: v("v1")}, pinned=(PROMPT,))
    )
    done = cli(
        repo,
        "promote",
        "--suite",
        "suite_qa.py",
        "--run",
        reference.key,
        "--replacing",
        baseline_in(repo),
    )
    assert done.returncode == 0, done.stderr
    moved = store.write_run(
        replace(
            measured,
            created_at=measured.created_at.replace("+00:00", "1+00:00"),
            artifacts={PROMPT: v("v2")},
            pinned=(PROMPT,),
        )
    )
    return reference.key, moved.key


def test_the_command_line_refuses_and_then_accepts_and_says_so(repo: Path) -> None:
    reference, moved = planted(repo)

    refused = cli(
        repo,
        "promote",
        "--suite",
        "suite_qa.py",
        "--run",
        moved,
        "--replacing",
        reference,
    )
    assert refused.returncode == 64, refused.stdout
    assert "UnacceptedPinsError" in refused.stderr
    assert f"--accepting-pin {PROMPT}" in refused.stderr
    assert baseline_in(repo) == reference

    accepted = cli(
        repo,
        "promote",
        "--suite",
        "suite_qa.py",
        "--run",
        moved,
        "--replacing",
        reference,
        "--accepting-pin",
        PROMPT,
    )
    assert accepted.returncode == 0, accepted.stderr
    assert baseline_in(repo) == moved
    # Announced where the promotion is announced, and not written into the
    # baseline: the authorisation is in what promote prints. (the ruling)
    assert PROMPT in accepted.stdout, accepted.stdout
    document = (repo / ".digline" / "acme-bank" / "baselines" / "qa.json").read_text(
        encoding="utf-8"
    )
    assert "accepting" not in document


def test_the_view_button_refuses_a_drift_and_sends_to_the_command_line(
    repo: Path,
) -> None:
    """The form carries no authorisation, so a run with a pin cause is refused
    there, and the page says how to promote it: the command, the flag, the
    path. A consequence the ruling chose."""
    from tests.test_view import launch_of, port_of, post_page, server

    reference, moved = planted(repo)
    with server(repo, "--allow-promote") as (base, line):
        cookie = hand_over(port_of(base), launch_of(line))
        status, page = post_page(
            base, f"run={moved}&replacing={reference}&locale=en", cookie=cookie
        )
    assert status == 200, page
    assert "digline promote" in page, page
    assert f"--accepting-pin {PROMPT}" in page, page
    assert baseline_in(repo) == reference
