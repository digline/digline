"""The file-based store: `.digline/<tenant>/`, baseline versioned, runs not.

The tenant is a directory rather than a field, so addressing is something the
filesystem enforces rather than something a document merely describes. Not
access: one OS user reads every tenant (fixed decision 8).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from digline.core import (
    CaseResult,
    Contains,
    CostBudget,
    EvaluatorInputs,
    Run,
    Score,
    Verdict,
    compare,
    config_hash,
    key_of,
)
from digline.core.run import SCHEMA_VERSION, DocumentRefusedError
from digline.store import (
    ConfigMismatchError,
    ErroredRunError,
    FileResultStore,
    RunRef,
    TenantMismatchError,
)

CREATED = "2026-01-01T12:30:45+00:00"


def run(cfg: str = "hash-a", suite: str = "test-suite", tenant: str = "acme") -> Run:
    return Run(
        tenant=tenant,
        environment="test",
        suite=suite,
        config_hash=cfg,
        created_at=CREATED,
        git_commit="0f1e2d3",
        results=(
            CaseResult(
                "case-1",
                (
                    Verdict(
                        score=Score(name="contains", score=1.0),
                        threshold=1.0,
                        tolerance=0.0,
                        status="pass",
                        reason="found",
                        assertion_id="contains",
                    ),
                ),
            ),
        ),
    )


# --------------------------------------------------------------------------- #
# Layout
# --------------------------------------------------------------------------- #


def test_it_creates_the_layout_and_the_gitignore(tmp_path: Path) -> None:
    store = FileResultStore(tmp_path)
    store.ensure_layout("acme")
    assert (tmp_path / ".digline" / "acme" / "baselines").is_dir()
    assert (tmp_path / ".digline" / "acme" / "runs").is_dir()
    ignored = (tmp_path / ".digline" / ".gitignore").read_text(encoding="utf-8")
    # Rules only, not comments: run artifacts are ephemeral, baselines are meant
    # to be committed, and the name table never is — for every tenant.
    rules = [
        r.strip() for r in ignored.splitlines() if r.strip() and not r.startswith("#")
    ]
    assert rules == ["*/runs/", "*/name-table/"]


def test_it_does_not_overwrite_an_edited_gitignore(tmp_path: Path) -> None:
    store = FileResultStore(tmp_path)
    store.ensure_layout("acme")
    gitignore = tmp_path / ".digline" / ".gitignore"
    gitignore.write_text("*/runs/\nmy-own-entry\n", encoding="utf-8")
    store.ensure_layout("beta")
    assert "my-own-entry" in gitignore.read_text(encoding="utf-8")


def test_it_writes_and_reads_back_a_run(tmp_path: Path) -> None:
    store = FileResultStore(tmp_path)
    ref = store.write_run(run())
    assert store.read_run(ref).config_hash == "hash-a"
    assert store.run_path(ref).is_file()


def test_a_run_lands_under_runs_and_not_among_the_baselines(tmp_path: Path) -> None:
    store = FileResultStore(tmp_path)
    ref = store.write_run(run())
    assert "runs" in store.run_path(ref).parts
    assert not store.baseline_path("acme", "test-suite").exists()


def test_the_baseline_file_is_readable_by_eye(tmp_path: Path) -> None:
    store = FileResultStore(tmp_path)
    store.promote_baseline(
        store.write_run(run()),
        "hash-a",
        expected_baseline=None,
        promoted_at="2026-01-02T09:00:00+00:00",
        declared=None,
    )
    text = store.baseline_path("acme", "test-suite").read_text(encoding="utf-8")
    assert text.startswith("{\n")  # indented, not minified
    assert text.endswith("\n")  # trailing newline: no "\ No newline" in diffs
    assert '"config_hash": "hash-a"' in text
    assert '"tenant": "acme"' in text


def test_the_timestamp_becomes_a_portable_filename(tmp_path: Path) -> None:
    """ISO colons are legal on macOS and Linux but not on Windows."""
    ref = FileResultStore(tmp_path).write_run(run())
    assert ":" not in ref.key
    assert ref.key.endswith("hash-a")


# --------------------------------------------------------------------------- #
# Promotion
# --------------------------------------------------------------------------- #


def test_a_suite_without_a_baseline_is_not_an_error(tmp_path: Path) -> None:
    """The first round has no baseline to compare against."""
    assert FileResultStore(tmp_path).read_baseline("acme", "test-suite") is None


def test_it_promotes_a_run_with_the_matching_configuration(tmp_path: Path) -> None:
    store = FileResultStore(tmp_path)
    promoted = store.promote_baseline(
        store.write_run(run()),
        "hash-a",
        expected_baseline=None,
        promoted_at="2026-01-02T09:00:00+00:00",
        declared=None,
    )
    assert promoted.config_hash == "hash-a"
    stored = store.read_baseline("acme", "test-suite")
    assert stored is not None and stored.git_commit == "0f1e2d3"


def test_it_refuses_to_promote_a_run_from_another_configuration(tmp_path: Path) -> None:
    """Without this check the baseline would record scores obtained under a
    configuration other than the one in force: every later comparison would be
    meaningless while remaining syntactically valid."""
    store = FileResultStore(tmp_path)
    ref = store.write_run(run(cfg="old-hash"))
    with pytest.raises(ConfigMismatchError, match="other than the one in force"):
        store.promote_baseline(
            ref,
            expected_config_hash="new-hash",
            expected_baseline=None,
            promoted_at="2026-01-02T09:00:00+00:00",
            declared=None,
        )
    assert store.read_baseline("acme", "test-suite") is None


def test_promotion_is_explicit_writing_a_run_does_not_promote_it(
    tmp_path: Path,
) -> None:
    store = FileResultStore(tmp_path)
    store.write_run(run())
    assert store.read_baseline("acme", "test-suite") is None


def test_it_refuses_to_promote_a_run_that_could_not_judge(tmp_path: Path) -> None:
    """A baseline is an approved reference; an error is not one. Promoting it
    would freeze a permanent red line no reader could tell apart from a new
    failure — the remedy for a flaky case is to fix it or remove it."""
    store = FileResultStore(tmp_path)
    suite = [Contains(needle="Rome"), CostBudget(max_usd=0.10, tolerance=0.02)]
    cfg = config_hash(suite)
    # `cost_usd` is absent, so the budget cannot be verified: an error, not a fail.
    verdicts = tuple(a(EvaluatorInputs(output="Rome")) for a in suite)
    flaky = Run(
        tenant="acme",
        environment="test",
        suite="qa",
        config_hash=cfg,
        created_at=CREATED,
        results=(
            CaseResult("healthy", (suite[0](EvaluatorInputs(output="Rome")),)),
            CaseResult("cannot-judge", verdicts),
        ),
    )
    ref = store.write_run(flaky)

    with pytest.raises(ErroredRunError, match="cannot-judge"):
        store.promote_baseline(
            ref,
            cfg,
            expected_baseline=None,
            promoted_at="2026-01-02T09:00:00+00:00",
            declared=None,
        )
    assert store.read_baseline("acme", "qa") is None


def test_it_names_every_case_it_could_not_judge(tmp_path: Path) -> None:
    store = FileResultStore(tmp_path)
    budget = CostBudget(max_usd=0.10, tolerance=0.02)
    cfg = config_hash([budget])
    broken = budget(EvaluatorInputs(output="x"))  # no cost_usd -> error
    run_with_errors = Run(
        tenant="acme",
        environment="test",
        suite="qa",
        config_hash=cfg,
        created_at=CREATED,
        results=(
            # Judged, so condition 3 is the refusal under test and not condition
            # 10, which a run whose every case errored meets first.
            # (ADR 0049 §3, §5)
            CaseResult("judged", (budget(EvaluatorInputs(output="x", cost_usd=0.01)),)),
            CaseResult("alpha", (broken,)),
            CaseResult("beta", (broken,)),
        ),
    )
    ref = store.write_run(run_with_errors)
    with pytest.raises(ErroredRunError) as raised:
        store.promote_baseline(
            ref,
            cfg,
            expected_baseline=None,
            promoted_at="2026-01-02T09:00:00+00:00",
            declared=None,
        )
    assert "alpha" in str(raised.value) and "beta" in str(raised.value)


def test_a_clean_run_is_still_promotable(tmp_path: Path) -> None:
    """The other direction: the new condition must not block the normal path."""
    store = FileResultStore(tmp_path)
    assert (
        store.promote_baseline(
            store.write_run(run()),
            "hash-a",
            expected_baseline=None,
            promoted_at="2026-01-02T09:00:00+00:00",
            declared=None,
        )
        is not None
    )


def test_a_nonexistent_run_cannot_be_promoted(tmp_path: Path) -> None:
    store = FileResultStore(tmp_path)
    with pytest.raises(FileNotFoundError):
        store.promote_baseline(
            RunRef("acme", "test-suite", "made-up"),
            "hash-a",
            expected_baseline=None,
            promoted_at="2026-01-02T09:00:00+00:00",
            declared=None,
        )


# --------------------------------------------------------------------------- #
# The perimeter
# --------------------------------------------------------------------------- #


def test_two_tenants_do_not_see_each_other(tmp_path: Path) -> None:
    """The point of the layout: a software house holding N customers must not be
    one typo away from reading one customer's history as another's."""
    store = FileResultStore(tmp_path)
    store.promote_baseline(
        store.write_run(run(tenant="acme")),
        "hash-a",
        expected_baseline=None,
        promoted_at="2026-01-02T09:00:00+00:00",
        declared=None,
    )

    assert store.read_baseline("acme", "test-suite") is not None
    assert store.read_baseline("globex", "test-suite") is None


def test_a_run_addressed_through_the_wrong_tenant_is_refused(tmp_path: Path) -> None:
    """Reading is checked as well as writing: the directory says one thing, the
    document says another, and guessing which is right is how perimeters leak."""
    store = FileResultStore(tmp_path)
    ref = store.write_run(run(tenant="acme"))
    forged = RunRef(tenant="globex", suite=ref.suite, key=ref.key)
    # Place the acme document under globex by hand, as a mistaken copy would.
    target = store.run_path(forged)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(store.run_path(ref).read_text(encoding="utf-8"), encoding="utf-8")

    with pytest.raises(TenantMismatchError, match="acme"):
        store.read_run(forged)


def test_each_tenant_keeps_its_own_baseline_for_the_same_suite(tmp_path: Path) -> None:
    store = FileResultStore(tmp_path)
    store.promote_baseline(
        store.write_run(run(tenant="acme", cfg="hash-a")),
        "hash-a",
        expected_baseline=None,
        promoted_at="2026-01-02T09:00:00+00:00",
        declared=None,
    )
    store.promote_baseline(
        store.write_run(run(tenant="globex", cfg="hash-b")),
        "hash-b",
        expected_baseline=None,
        promoted_at="2026-01-02T09:00:00+00:00",
        declared=None,
    )
    acme = store.read_baseline("acme", "test-suite")
    globex = store.read_baseline("globex", "test-suite")
    assert acme is not None and globex is not None
    assert acme.config_hash == "hash-a"
    assert globex.config_hash == "hash-b"


def test_comparing_across_tenants_is_refused(tmp_path: Path) -> None:
    store = FileResultStore(tmp_path)
    store.promote_baseline(
        store.write_run(run(tenant="acme")),
        "hash-a",
        expected_baseline=None,
        promoted_at="2026-01-02T09:00:00+00:00",
        declared=None,
    )
    baseline = store.read_baseline("acme", "test-suite")
    assert baseline is not None
    with pytest.raises(ValueError, match="across tenants"):
        compare(run(tenant="globex"), baseline)


def test_dangerous_names_are_rejected(tmp_path: Path) -> None:
    """`..` and `/` are the interesting ones: a name that could climb out of its
    tenant directory would defeat the addressing the layout exists to give."""
    store = FileResultStore(tmp_path)
    for bad in ("../escape", "with/slash", "", "with space"):
        with pytest.raises(ValueError, match="invalid suite name"):
            store.baseline_path("acme", bad)
        with pytest.raises(ValueError, match="invalid tenant name"):
            store.baseline_path(bad, "test-suite")
        # The run key too, and it is the one that matters most: tenant and
        # suite are read from a suite the developer wrote, while the key
        # arrives from `--run` or from `?run=` in the view's query string.
        with pytest.raises(ValueError, match="invalid run name"):
            store.run_path(RunRef(tenant="acme", suite="test-suite", key=bad))


def test_a_real_run_key_is_still_a_legal_name(tmp_path: Path) -> None:
    """The check above has to admit what `key_of` produces, or it refuses every
    run there has ever been. `latest` too: `resolve_key` normally spends it
    before the store sees it, but nothing stops a caller passing it through."""
    store = FileResultStore(tmp_path)
    document = run()
    key = key_of(document.created_at, document.config_hash)
    assert (
        store.run_path(RunRef(tenant="acme", suite="qa", key=key)).name == f"{key}.json"
    )
    store.run_path(RunRef(tenant="acme", suite="qa", key="latest"))


# --------------------------------------------------------------------------- #
# End to end
# --------------------------------------------------------------------------- #


def test_rerunning_an_unchanged_suite_shows_no_regression(tmp_path: Path) -> None:
    """End to end, through the real filesystem: promote a baseline, run the same
    suite again on the same input, expect nothing to have moved.

    This is the test that would have caught the phantom regression — a score of
    0.909090... written to disk as 0.909091 and compared against the unrounded
    live value produced a spurious `regressed` on every run."""
    suite = [Contains(needle="Rome"), CostBudget(max_usd=0.10, tolerance=0.02)]
    cfg = config_hash(suite)
    store = FileResultStore(tmp_path)

    def execute(when: str) -> Run:
        verdicts = tuple(
            a(EvaluatorInputs(output="The capital is Rome.", cost_usd=0.01))
            for a in suite
        )
        return Run(
            tenant="acme",
            environment="test",
            suite="qa",
            config_hash=cfg,
            created_at=when,
            results=(CaseResult("capital", verdicts),),
        )

    store.promote_baseline(
        store.write_run(execute(CREATED)),
        cfg,
        expected_baseline=None,
        promoted_at="2026-01-02T09:00:00+00:00",
        declared=None,
    )
    baseline = store.read_baseline("acme", "qa")
    assert baseline is not None

    result = compare(execute("2026-01-02T09:00:00+00:00"), baseline)
    assert result.counts == {"unchanged": 2}, [d.reason for d in result.deltas]
    assert not result.has_regressions


def test_reordering_the_suite_does_not_invent_regressions(tmp_path: Path) -> None:
    """Identity-based pairing, verified against a baseline read from disk."""
    rome, milan = Contains(needle="Rome"), Contains(needle="Milan")
    cfg = config_hash([rome, milan])
    store = FileResultStore(tmp_path)

    def execute(order: list[Contains], when: str) -> Run:
        verdicts = tuple(a(EvaluatorInputs(output="Rome and Milan")) for a in order)
        return Run(
            tenant="acme",
            environment="test",
            suite="qa",
            config_hash=cfg,
            created_at=when,
            results=(CaseResult("cities", verdicts),),
        )

    store.promote_baseline(
        store.write_run(execute([rome, milan], CREATED)),
        cfg,
        expected_baseline=None,
        promoted_at="2026-01-02T09:00:00+00:00",
        declared=None,
    )
    baseline = store.read_baseline("acme", "qa")
    assert baseline is not None

    swapped = execute([milan, rome], "2026-01-02T09:00:00+00:00")
    assert compare(swapped, baseline).counts == {"unchanged": 2}


def test_storage_is_local_to_the_project(tmp_path: Path) -> None:
    """Fixed decision 2: never a database in the home directory, never global
    state."""
    one, two = tmp_path / "project-a", tmp_path / "project-b"
    one.mkdir()
    two.mkdir()
    store_one = FileResultStore(one)
    store_one.promote_baseline(
        store_one.write_run(run()),
        "hash-a",
        expected_baseline=None,
        promoted_at="2026-01-02T09:00:00+00:00",
        declared=None,
    )
    assert FileResultStore(two).read_baseline("acme", "test-suite") is None


# --------------------------------------------------------------------------- #
# A refused document says which file, and whether it is the run or the
# baseline (#672)
# --------------------------------------------------------------------------- #


def _promoted(root: Path) -> tuple[FileResultStore, Path, Path]:
    """A store holding one run promoted to baseline: the run's file and the
    baseline's, to break one of them."""
    store = FileResultStore(root)
    ref = store.write_run(run())
    store.promote_baseline(
        ref,
        "hash-a",
        expected_baseline=None,
        promoted_at="2026-01-02T09:00:00+00:00",
        declared=None,
    )
    return store, store.run_path(ref), store.baseline_path("acme", "test-suite")


def _restamp(path: Path, schema: int) -> None:
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["schema_version"] = schema
    path.write_text(json.dumps(raw), encoding="utf-8")


def test_a_newer_baseline_is_named_as_the_baseline_with_its_path(
    tmp_path: Path,
) -> None:
    """`compare`, `explain`, `register` and `report` printed *"schema_version
    21 is not supported (expected 20)"*, naming neither the file nor its role.
    It names both, and the advice in the direction the schema differs."""
    store, _run, baseline = _promoted(tmp_path)
    _restamp(baseline, SCHEMA_VERSION + 1)
    with pytest.raises(DocumentRefusedError) as refused:
        store.read_baseline("acme", "test-suite")
    message = str(refused.value)
    assert f"the baseline at {baseline}" in message
    assert "upgrade digline" in message.lower()
    assert "digline migrate" not in message
    assert refused.value.role == "baseline"
    assert refused.value.declared_schema == SCHEMA_VERSION + 1


def test_a_broken_run_is_named_as_the_run_with_its_path(tmp_path: Path) -> None:
    store, path, _baseline = _promoted(tmp_path)
    path.write_text("{ not json", encoding="utf-8")
    ref = RunRef("acme", "test-suite", path.stem)
    with pytest.raises(DocumentRefusedError) as refused:
        store.read_run(ref)
    assert f"the run at {path}" in str(refused.value)
    assert refused.value.role == "run"
    assert refused.value.declared_schema is None


def test_a_broken_baseline_stays_apart_from_a_newer_one_and_from_a_run(
    tmp_path: Path,
) -> None:
    """The control: the same exception, told apart by its fields. A broken
    baseline declares no schema, unlike a newer one, and says `baseline`,
    unlike a broken run."""
    store, _run, baseline = _promoted(tmp_path)
    baseline.write_text("{ not json", encoding="utf-8")
    with pytest.raises(DocumentRefusedError) as refused:
        store.read_baseline("acme", "test-suite")
    assert refused.value.role == "baseline"
    assert refused.value.declared_schema is None
    assert f"the baseline at {baseline}" in str(refused.value)
