"""The journal, and the run that is finished rather than started again.

ADR 0017. A 720-call run killed mid-flight used to lose everything, because
`write_run` happens once, at the end. What is tested here is the record kept as
the run goes, the rules under which a second process may finish it, and — the
one that makes the rest legitimate — that the document a resumed run produces is
the document the killed run was going to produce, byte for byte.

The boundary half is not here. A journal never crosses one: it is not a document,
`digline.wire` does not know its name, and `tests/test_wire_boundary.py` is where
that kind of negative is proved about the surface that would carry it.
"""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from typing import Any

import pytest
from tests._helpers import cli

from digline.core import (
    Artifact,
    CaseProgress,
    CaseResult,
    Contains,
    Run,
    run_to_json,
)
from digline.core.run import SCHEMA_VERSION, run_to_dict
from digline.host import measure, prepare
from digline.host.measure import Prepared
from digline.run import Case, Response, Suite, execute, planned_calls
from digline.store import (
    JOURNAL_VERSION,
    PENDING_DIRNAME,
    ErroredRunError,
    FileJournal,
    FileResultStore,
    JournalBusyError,
    JournalRefusedError,
    journal_key,
)
from digline.targets import Completion, ObservedIdentity, Usage

CREATED = "2026-01-01T00:00:00+00:00"
LATER = "2026-01-02T09:30:00+00:00"
TENANT = "acme"
SUITE = "demo"


def a_suite(*, cases: int = 6, **extra: object) -> Suite:
    return Suite(
        tenant=TENANT,
        environment="staging",
        name=SUITE,
        assertions=[Contains(needle="yes", threshold=1.0)],
        cases=[Case(id=f"c{n}") for n in range(1, cases + 1)],
        **extra,  # pyright: ignore[reportArgumentType]
    )


class Counting:
    """A target that answers, counts, and can be killed at a chosen call.

    `SystemExit` rather than an ordinary exception on purpose: the driver
    contains `Exception` and errors the case, which is not what a supervisor
    does. This is the kill.
    """

    def __init__(self, *, die_at: int | None = None, model: str = "m-1") -> None:
        self.calls: list[str] = []
        self.die_at = die_at
        self.config = {"provider": "fake", "model": model}

    def __call__(self, case: Case) -> Response:
        self.calls.append(case.id)
        if self.die_at is not None and len(self.calls) == self.die_at:
            raise SystemExit(9)
        return Response(output="yes", input=f"ask {case.id}", cost_usd=0.01)


class Rolling:
    """A provider target whose alias resolves to one model and then another."""

    def __init__(self, ids: list[str]) -> None:
        self.observed = ObservedIdentity("alias")
        self.ids = ids
        self.calls = 0

    @property
    def config(self) -> dict[str, object]:
        return {
            "provider": "fake",
            "model": "alias",
            **{k: v for k, v in self.observed.values.items() if v is not None},
        }

    def __call__(self, case: Case) -> Response:
        model = self.ids[min(self.calls, len(self.ids) - 1)]
        self.calls += 1
        self.observed.see(Completion(text="yes", usage=Usage(1, 1), model=model))
        return Response(output="yes")


def launch(
    root: Path,
    suite: Suite,
    target: object,
    *,
    now: str = CREATED,
    resume_key: str | None = None,
    retry_errors: bool = True,
    commit: str | None = "deadbeef",
) -> tuple[FileResultStore, Prepared]:
    store = FileResultStore(root)
    pending = None
    if resume_key is not None:
        found = [p for p in store.pending(TENANT, SUITE) if p.key == resume_key]
        assert found, "no such pending journal"
        pending = found[0]
    prepared = prepare(
        suite,
        target,
        now=now,
        git_commit=commit,
        artifacts={},
        resume=pending,
        retry_errors=retry_errors,
    )
    return store, prepared


def killed(root: Path, suite: Suite, target: Counting, *, now: str = CREATED) -> str:
    """Run until the target kills the process, and return the journal's key."""
    store, prepared = launch(root, suite, target, now=now)
    with pytest.raises(SystemExit):
        measure(suite, target, store=store, prepared=prepared)  # pyright: ignore[reportArgumentType]
    return journal_key(prepared.header)


def legs(root: Path, key: str) -> list[Path]:
    directory = Path(root) / ".digline" / TENANT / "runs" / SUITE / PENDING_DIRNAME
    return sorted(directory.glob(f"{key}.*.jsonl"))


def records(path: Path) -> list[Any]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


# -- what a kill leaves ------------------------------------------------------ #


def test_a_killed_run_loses_one_case_and_not_the_others(tmp_path: Path) -> None:
    """The whole point, in one assertion: four cases were paid for and three
    are on disk. Before the journal there were none."""
    target = Counting(die_at=4)
    key = killed(tmp_path, a_suite(), target)

    assert target.calls == ["c1", "c2", "c3", "c4"]
    lines = records(legs(tmp_path, key)[0])
    assert lines[0]["kind"] == "header"
    assert [line["case"]["case_id"] for line in lines if line["kind"] == "case"] == [
        "c1",
        "c2",
        "c3",
    ]


def test_the_observation_is_written_once_and_before_the_crash(tmp_path: Path) -> None:
    """An identity learnt from the first reply has to be on disk before the
    kill, or the resume has nothing to seed and the roll is averaged away."""

    class Dying(Rolling):
        def __call__(self, case: Case) -> Response:
            if self.calls == 3:
                raise SystemExit(9)
            return super().__call__(case)

    key = killed(tmp_path, a_suite(cases=4), Dying(["m-1"]))  # pyright: ignore[reportArgumentType]
    observed = [
        line for line in records(legs(tmp_path, key)[0]) if line["kind"] == "observed"
    ]
    assert len(observed) == 1, "written when it changes, which is once"
    assert observed[0]["target_config"]["values"]["resolved_model"] == "m-1"


def test_the_journal_holds_what_the_run_file_would_hold_and_no_more(
    tmp_path: Path,
) -> None:
    """Per case, not per sample: the granularity *is* the payload rule. A suite
    that does not record its answers has none in its journal either."""
    key = killed(tmp_path, a_suite(), Counting(die_at=3))
    cases = [
        line["case"]
        for line in records(legs(tmp_path, key)[0])
        if line["kind"] == "case"
    ]
    assert all("responses" not in case for case in cases)

    key = killed(
        tmp_path / "recorded",
        a_suite(record_responses=True),
        Counting(die_at=3),
    )
    cases = [
        line["case"]
        for line in records(legs(tmp_path / "recorded", key)[0])
        if line["kind"] == "case"
    ]
    assert all(case["responses"] for case in cases)


# -- the resumed run --------------------------------------------------------- #


def test_the_resumed_run_is_the_document_the_kill_prevented(tmp_path: Path) -> None:
    """Byte for byte, key included. This is the assertion that makes ADR 0017
    §10 true rather than intended: a resumed run needs no marker because there
    is nothing about it to mark."""
    whole = tmp_path / "whole"
    store, prepared = launch(whole, a_suite(), Counting())
    uninterrupted = measure(a_suite(), Counting(), store=store, prepared=prepared)  # pyright: ignore[reportArgumentType]

    broken = tmp_path / "broken"
    key = killed(broken, a_suite(), Counting(die_at=4))
    store, prepared = launch(broken, a_suite(), Counting(), now=LATER, resume_key=key)
    resumed = measure(a_suite(), Counting(), store=store, prepared=prepared)  # pyright: ignore[reportArgumentType]

    assert resumed.ref.key == uninterrupted.ref.key
    assert run_to_json(resumed.run) == run_to_json(uninterrupted.run)
    assert resumed.run.created_at == CREATED, "the original, not the rescue"


def test_a_resume_can_itself_be_killed_and_resumed(tmp_path: Path) -> None:
    """Three legs. Every leg but the last ended in a kill, so every leg but the
    last may end in a torn line — and the run they add up to is still one run."""
    suite = a_suite(cases=6)
    key = killed(tmp_path, suite, Counting(die_at=3))

    store, prepared = launch(tmp_path, suite, Counting(die_at=2), resume_key=key)
    second = Counting(die_at=2)
    store, prepared = launch(tmp_path, suite, second, resume_key=key, now=LATER)
    with pytest.raises(SystemExit):
        measure(suite, second, store=store, prepared=prepared)  # pyright: ignore[reportArgumentType]
    assert len(legs(tmp_path, key)) == 2

    third = Counting()
    store, prepared = launch(tmp_path, suite, third, resume_key=key, now=LATER)
    measured = measure(suite, third, store=store, prepared=prepared)  # pyright: ignore[reportArgumentType]

    assert measured.ref.key == key, "still the run the first leg started"
    assert measured.run.created_at == CREATED
    assert [case.case_id for case in measured.run.results] == [
        f"c{n}" for n in range(1, 7)
    ]
    assert third.calls == ["c4", "c5", "c6"], "neither leg re-called what was done"
    assert legs(tmp_path, key) == []


def test_the_order_of_the_results_comes_from_the_suite(tmp_path: Path) -> None:
    key = killed(tmp_path, a_suite(), Counting(die_at=4))
    # Journalled c1..c3; the resume calls c4..c6 and must not append them.
    store, prepared = launch(tmp_path, a_suite(), Counting(), resume_key=key)
    run = measure(a_suite(), Counting(), store=store, prepared=prepared).run  # pyright: ignore[reportArgumentType]
    assert [case.case_id for case in run.results] == [
        "c1",
        "c2",
        "c3",
        "c4",
        "c5",
        "c6",
    ]


def test_a_resume_with_nothing_left_to_call_still_writes_the_run(
    tmp_path: Path,
) -> None:
    """A process killed between the last case and `write_run` is the cheapest
    resume there is."""
    suite = a_suite(cases=3)
    store = FileResultStore(tmp_path)
    _, prepared = launch(tmp_path, suite, Counting())
    journal = store.open_journal(prepared.header)
    run = execute(suite, Counting(), created_at=CREATED, on_case=journal.append)
    assert len(run.results) == 3

    target = Counting()
    store, prepared = launch(tmp_path, suite, target, resume_key=journal.key, now=LATER)
    assert prepared.plan.target_calls == 0
    measured = measure(suite, target, store=store, prepared=prepared)  # pyright: ignore[reportArgumentType]
    assert target.calls == []
    assert len(measured.run.results) == 3
    assert legs(tmp_path, journal.key) == []


def test_the_journal_is_deleted_only_once_the_run_exists(tmp_path: Path) -> None:
    key = killed(tmp_path, a_suite(), Counting(die_at=3))
    assert legs(tmp_path, key), "a killed run keeps its journal"
    store, prepared = launch(tmp_path, a_suite(), Counting(), resume_key=key)
    measured = measure(a_suite(), Counting(), store=store, prepared=prepared)  # pyright: ignore[reportArgumentType]
    assert store.run_path(measured.ref).exists()
    assert legs(tmp_path, key) == []


# -- the refusals ------------------------------------------------------------ #


def test_every_asserted_fact_refuses_and_costs_nothing(tmp_path: Path) -> None:
    """One case per row of ADR 0017 §6, and each one asserts that **no call was
    made**: a refused resume that had already paid for something would be the
    failure this feature exists to prevent."""
    key = killed(tmp_path, a_suite(), Counting(die_at=3))

    def refuse(suite: Suite, target: Counting, **kw: object) -> str:
        with pytest.raises(JournalRefusedError) as caught:
            launch(tmp_path, suite, target, resume_key=key, **kw)  # pyright: ignore[reportArgumentType]
        assert target.calls == []
        return str(caught.value)

    # the rules
    assert "config_hash" in refuse(a_suite(samples=3, min_agreement="2/3"), Counting())
    # the questions
    assert "cases_digest" in refuse(a_suite(cases=7), Counting())
    # the system under test
    assert "target_config" in refuse(a_suite(), Counting(model="m-2"))
    # the code around it
    assert "git_commit" in refuse(a_suite(), Counting(), commit="cafe")
    # what the document will record of the answers
    assert "record_responses" in refuse(a_suite(record_responses=True), Counting())


def test_the_prompt_that_moved_refuses(tmp_path: Path) -> None:
    """Artifacts are digested in the header for one reason: the prompt is the
    thing under test, and half a run under one of them is not a run."""
    suite = a_suite()
    store = FileResultStore(tmp_path)
    prepared = prepare(
        suite,
        Counting(),
        now=CREATED,
        git_commit=None,
        artifacts={"p.md": _artifact("one")},
    )
    journal = store.open_journal(prepared.header)
    journal.append(CaseProgress(result=CaseResult(case_id="c1")))

    pending = store.pending(TENANT, SUITE)[0]
    with pytest.raises(JournalRefusedError, match="artifacts"):
        prepare(
            suite,
            Counting(),
            now=LATER,
            git_commit=None,
            artifacts={"p.md": _artifact("two")},
            resume=pending,
        )


def _artifact(text: str) -> Artifact:
    return Artifact(sha=sha256(text.encode()).hexdigest(), text=text)


def test_a_finished_journal_is_not_resumable(tmp_path: Path) -> None:
    """Killed between `write_run` and the delete: the run exists, so there is
    nothing to finish."""
    key = killed(tmp_path, a_suite(), Counting(die_at=3))
    store, prepared = launch(tmp_path, a_suite(), Counting(), resume_key=key)
    journal = store.open_journal(prepared.header)
    run = execute(a_suite(), Counting(), created_at=CREATED, done=prepared.done)
    store.write_run(run)
    journal._handle.close()  # pyright: ignore[reportPrivateUsage]

    pending = [p for p in store.pending(TENANT, SUITE) if p.key == key]
    assert pending and pending[0].finished
    with pytest.raises(JournalRefusedError, match="already written"):
        prepare(
            a_suite(),
            Counting(),
            now=LATER,
            git_commit="deadbeef",
            artifacts={},
            resume=pending[0],
        )
    store.drop_pending(TENANT, SUITE, key)
    assert legs(tmp_path, key) == []


def test_two_processes_cannot_resume_one_run(tmp_path: Path) -> None:
    """The whole concurrency story, and it needs no lock file."""
    key = killed(tmp_path, a_suite(), Counting(die_at=3))
    store, prepared = launch(tmp_path, a_suite(), Counting(), resume_key=key)
    first = store.open_journal(prepared.header)
    with pytest.raises(JournalBusyError, match="another digline"):
        FileJournal(first.path, prepared.header)
    assert records(first.path)[0]["kind"] == "header", "untouched by the loser"


# -- the seam ---------------------------------------------------------------- #


def test_an_alias_that_rolled_across_the_seam_errors_instead_of_averaging(
    tmp_path: Path,
) -> None:
    """The in-process rule, unchanged by the crash: one case errors, the run is
    still written, it exits unjudged and it cannot be promoted."""
    suite = a_suite(cases=4)
    store = FileResultStore(tmp_path)

    class Dying(Rolling):
        def __call__(self, case: Case) -> Response:
            if self.calls == 2:
                raise SystemExit(9)
            return super().__call__(case)

    first = Dying(["m-1"])
    _, prepared = launch(tmp_path, suite, first)
    with pytest.raises(SystemExit):
        measure(suite, first, store=store, prepared=prepared)  # pyright: ignore[reportArgumentType]

    second = Rolling(["m-2"])
    pending = store.pending(TENANT, SUITE)[0]
    assert pending.observed_target.values["resolved_model"] == "m-1"
    prepared = prepare(
        suite, second, now=LATER, git_commit="deadbeef", artifacts={}, resume=pending
    )
    run = measure(suite, second, store=store, prepared=prepared).run  # pyright: ignore[reportArgumentType]

    errored = [
        case.case_id
        for case in run.results
        if any(verdict.status == "error" for verdict in case.verdicts)
    ]
    assert errored, "the roll has to error a case, not be averaged into one model"
    reason = run.results[2].verdicts[0].reason
    assert "m-1" in reason and "m-2" in reason and "pin the model id" in reason
    ref = FileResultStore(tmp_path).write_run(run)
    with pytest.raises(ErroredRunError):
        store.promote_baseline(ref, run.config_hash, promoted_at=LATER)


def test_a_target_that_observes_nothing_is_seeded_with_nothing(
    tmp_path: Path,
) -> None:
    """A plain function has no identity to average, so nothing has to happen."""
    key = killed(tmp_path, a_suite(), Counting(die_at=3))
    store, prepared = launch(tmp_path, a_suite(), Counting(), resume_key=key)
    run = measure(a_suite(), Counting(), store=store, prepared=prepared).run  # pyright: ignore[reportArgumentType]
    assert run.target_config.values["model"] == "m-1"


# -- errored cases ----------------------------------------------------------- #


class Weather:
    """Raises on a named case until told to stop."""

    def __init__(self, *, failing: set[str]) -> None:
        self.failing = failing
        self.calls: list[str] = []
        self.config = {"provider": "fake", "model": "m-1"}

    def __call__(self, case: Case) -> Response:
        self.calls.append(case.id)
        if case.id in self.failing:
            raise TimeoutError("the provider did not answer")
        return Response(output="yes")


def test_a_resume_retries_an_errored_case_by_default(tmp_path: Path) -> None:
    """An errored verdict exits 2 and cannot be promoted, so a resume that kept
    it would finish a run nobody can use."""
    suite = a_suite(cases=4)
    store = FileResultStore(tmp_path)
    flaky = Weather(failing={"c2"})
    _, prepared = launch(tmp_path, suite, flaky)
    journal = store.open_journal(prepared.header)
    execute(suite, flaky, created_at=CREATED, on_case=journal.append)
    journal._handle.close()  # pyright: ignore[reportPrivateUsage]

    pending = store.pending(TENANT, SUITE)[0]
    assert pending.errored == {"c2"}
    assert pending.causes == {"c2": "target"}

    better = Weather(failing=set())
    prepared = prepare(
        suite, better, now=LATER, git_commit="deadbeef", artifacts={}, resume=pending
    )
    assert prepared.plan.target_calls == 1
    assert prepared.plan.retried == 1
    run = measure(suite, better, store=store, prepared=prepared).run  # pyright: ignore[reportArgumentType]
    assert better.calls == ["c2"]
    assert all(
        verdict.status != "error" for case in run.results for verdict in case.verdicts
    )


def test_keep_errors_keeps_them(tmp_path: Path) -> None:
    suite = a_suite(cases=4)
    store = FileResultStore(tmp_path)
    flaky = Weather(failing={"c2"})
    _, prepared = launch(tmp_path, suite, flaky)
    journal = store.open_journal(prepared.header)
    execute(suite, flaky, created_at=CREATED, on_case=journal.append)
    journal._handle.close()  # pyright: ignore[reportPrivateUsage]

    better = Weather(failing=set())
    pending = store.pending(TENANT, SUITE)[0]
    prepared = prepare(
        suite,
        better,
        now=LATER,
        git_commit="deadbeef",
        artifacts={},
        resume=pending,
        retry_errors=False,
    )
    assert prepared.plan.target_calls == 0
    assert prepared.retrying == {}
    run = measure(suite, better, store=store, prepared=prepared).run  # pyright: ignore[reportArgumentType]
    assert better.calls == []
    assert run.results[1].verdicts[0].status == "error"


def test_the_cause_is_recorded_for_each_layer(tmp_path: Path) -> None:
    """Recorded so a reader can tell the target's weather from a bug of their
    own — and never acted on, which is what the retry default means."""
    suite = Suite(
        tenant=TENANT,
        environment="staging",
        name=SUITE,
        assertions=[Contains(needle="yes", threshold=1.0)],
        cases=[Case(id="c1"), Case(id="c2")],
    )
    store = FileResultStore(tmp_path)
    _, prepared = launch(tmp_path, suite, Counting())
    journal = store.open_journal(prepared.header)

    def mapper(response: Response, case: Case) -> object:
        raise RuntimeError("no")

    execute(
        suite,
        Counting(),
        created_at=CREATED,
        mapper=mapper,  # pyright: ignore[reportArgumentType]
        on_case=journal.append,
    )
    journal._handle.close()  # pyright: ignore[reportPrivateUsage]
    assert store.pending(TENANT, SUITE)[0].causes == {"c1": "mapper", "c2": "mapper"}


# -- the file ---------------------------------------------------------------- #


def test_a_torn_last_line_is_the_one_the_kill_interrupted(tmp_path: Path) -> None:
    key = killed(tmp_path, a_suite(), Counting(die_at=4))
    path = legs(tmp_path, key)[0]
    path.write_text(path.read_text() + '{"kind": "case", "ca', encoding="utf-8")
    pending = FileResultStore(tmp_path).pending(TENANT, SUITE)[0]
    assert not pending.refusal
    assert sorted(pending.done) == ["c1", "c2", "c3"]


def test_a_corrupt_line_in_the_middle_is_refused_by_name(tmp_path: Path) -> None:
    key = killed(tmp_path, a_suite(), Counting(die_at=4))
    path = legs(tmp_path, key)[0]
    lines = path.read_text(encoding="utf-8").splitlines()
    lines[2] = "{not json"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    pending = FileResultStore(tmp_path).pending(TENANT, SUITE)[0]
    assert "corrupt at line 3" in pending.refusal


def test_an_unknown_journal_format_is_named_and_left_on_disk(tmp_path: Path) -> None:
    """A work file has a version and no migration. What it does not have is a
    digline willing to delete it on a guess."""
    key = killed(tmp_path, a_suite(), Counting(die_at=3))
    path = legs(tmp_path, key)[0]
    lines = path.read_text(encoding="utf-8").splitlines()
    header = json.loads(lines[0])
    header["journal_version"] = JOURNAL_VERSION + 1
    lines[0] = json.dumps(header)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    pending = FileResultStore(tmp_path).pending(TENANT, SUITE)[0]
    assert "journal format" in pending.refusal
    assert path.exists()
    with pytest.raises(JournalRefusedError, match="journal format"):
        prepare(
            a_suite(),
            Counting(),
            now=LATER,
            git_commit="deadbeef",
            artifacts={},
            resume=pending,
        )


def test_the_journal_is_invisible_to_everything_that_reads_documents(
    tmp_path: Path,
) -> None:
    """A journal is not a run: nothing lists it, scans it or migrates it."""
    key = killed(tmp_path, a_suite(), Counting(die_at=3))
    store = FileResultStore(tmp_path)
    assert legs(tmp_path, key), "the journal is there to be overlooked"
    assert store.list_runs(TENANT, SUITE) == ()
    assert store.scan_runs(TENANT, SUITE).runs == ()
    assert store.scan_runs(TENANT, SUITE).unreadable == ()
    assert store.run_paths(TENANT, SUITE) == ()


def test_the_generated_gitignore_already_covers_the_journal(tmp_path: Path) -> None:
    """`*/runs/` ignores the directory and everything beneath it, so a journal
    cannot reach a commit and no new rule was needed."""
    killed(tmp_path, a_suite(), Counting(die_at=3))
    ignore = (tmp_path / ".digline" / ".gitignore").read_text(encoding="utf-8")
    assert "*/runs/" in ignore
    assert PENDING_DIRNAME not in ignore


# -- what did not move ------------------------------------------------------- #


def test_the_schema_did_not_move(tmp_path: Path) -> None:
    """ADR 0017's own condition. A resumed run carries no marker, so the
    document has exactly the keys it had — asserted as a set, so a field added
    by accident fails here rather than in somebody's baseline."""
    assert SCHEMA_VERSION == 10
    key = killed(tmp_path, a_suite(), Counting(die_at=3))
    store, prepared = launch(tmp_path, a_suite(), Counting(), resume_key=key)
    resumed = measure(a_suite(), Counting(), store=store, prepared=prepared).run  # pyright: ignore[reportArgumentType]
    plain = Run(
        tenant=TENANT,
        environment="staging",
        suite=SUITE,
        config_hash=a_suite().config_hash(),
        created_at=CREATED,
    )
    assert set(run_to_dict(resumed)) - set(run_to_dict(plain)) == {"digline_version"}
    assert "resumed" not in json.dumps(run_to_dict(resumed))


def test_planned_calls_subtracts_what_it_will_not_call() -> None:
    suite = a_suite()
    assert planned_calls(suite).sentence().startswith("6 cases × 1 sample = 6 calls")
    plan = planned_calls(suite, done={"c1", "c2"}, retried=1)
    assert plan.target_calls == 4
    assert plan.reused == 2
    assert "4 of 6 cases" in plan.sentence()
    assert "2 cases already judged" in plan.sentence()
    assert "1 case retried after an error" in plan.sentence()


# -- the command line -------------------------------------------------------- #


JOURNALLED_SUITE = """\
from pathlib import Path

from digline.core import Contains
from digline.run import Case, Response, Suite

STATE = Path(__file__).parent / "calls.txt"

suite = Suite(
    tenant="acme",
    environment="staging",
    name="demo",
    assertions=[Contains(needle="yes", threshold=1.0)],
    cases=[Case(id="c1"), Case(id="c2"), Case(id="c3")],
)


def target(case):
    seen = STATE.read_text().split()
    STATE.write_text(" ".join([*seen, case.id]))
    if len(seen) + 1 == int((Path(__file__).parent / "die.txt").read_text()):
        raise SystemExit(9)
    return Response(output="yes")
"""


@pytest.fixture
def project(tmp_path: Path) -> Path:
    (tmp_path / "suite.py").write_text(JOURNALLED_SUITE, encoding="utf-8")
    (tmp_path / "calls.txt").write_text("", encoding="utf-8")
    (tmp_path / "die.txt").write_text("2", encoding="utf-8")
    return tmp_path


def test_the_cli_finishes_a_killed_run(project: Path) -> None:
    first = cli(project, "run", "--suite", "suite.py")
    assert first.returncode == 9

    (project / "die.txt").write_text("99", encoding="utf-8")
    done = cli(project, "run", "--suite", "suite.py", "--resume")
    assert done.returncode == 0, done.stderr
    assert "2 of 3 cases" in done.stderr
    assert "1 case already judged" in done.stderr
    key = done.stdout.strip()
    stored = json.loads(
        (project / ".digline" / "acme" / "runs" / "demo" / f"{key}.json").read_text()
    )
    assert [case["case_id"] for case in stored["results"]] == ["c1", "c2", "c3"]
    assert (project / "calls.txt").read_text().split() == ["c1", "c2", "c2", "c3"]


def test_resume_with_nothing_pending_refuses_rather_than_starting_a_run(
    project: Path,
) -> None:
    """Somebody who typed `--resume` believed there was something to finish,
    and starting the whole suite instead is the surprise this flag must not
    spring."""
    (project / "die.txt").write_text("99", encoding="utf-8")
    done = cli(project, "run", "--suite", "suite.py", "--resume")
    assert done.returncode == 64
    assert "does not start one" in done.stderr
    assert (project / "calls.txt").read_text().strip() == ""


def test_a_plain_run_names_the_journal_it_is_leaving_behind(project: Path) -> None:
    """Silently abandoning paid calls is the same surprise pointed the other
    way, so the note says what would finish them."""
    assert cli(project, "run", "--suite", "suite.py").returncode == 9
    (project / "die.txt").write_text("99", encoding="utf-8")
    done = cli(project, "run", "--suite", "suite.py")
    assert done.returncode == 0, done.stderr
    assert "was started and never written" in done.stderr
    assert "--resume" in done.stderr


def test_run_json_says_what_this_launch_did(project: Path) -> None:
    assert cli(project, "run", "--suite", "suite.py").returncode == 9
    (project / "die.txt").write_text("99", encoding="utf-8")
    done = cli(project, "run", "--suite", "suite.py", "--json", "--resume")
    payload = json.loads(done.stdout)
    assert payload["resumed"] is True
    assert payload["reused"] == 1
    assert (
        json.loads(cli(project, "run", "--suite", "suite.py", "--json").stdout)[
            "resumed"
        ]
        is False
    )
