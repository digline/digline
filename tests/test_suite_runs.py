"""`suite_runs`: the list a program shows, in clear or projected. (#276)

Written from the mistake each test prevents: one unreadable run taking the
whole list down, a run shown in clear on a projected page, a minter that pairs
rows that are not the same, and a baseline that could not be read reported as
no baseline at all.
"""

from __future__ import annotations

import inspect
import json
import secrets
from dataclasses import replace
from pathlib import Path

import pytest
from tests.test_projection import CHECK, FAMILY, NAMES, Table, promoted

from digline.core import (
    ProjectionRefusedError,
    Run,
    TokenKind,
    key_of,
    run_to_json,
)
from digline.core.run import SCHEMA_VERSION
from digline.host import REFUSALS, SuiteRuns, left_out, suite_runs
from digline.store import FileResultStore, Listing, PathRefusedError, RunRef

TENANT, SUITE = "acme", "support"
T1, T2, T3 = (
    "2026-09-28T10:00:00+00:00",
    "2026-09-29T10:00:00+00:00",
    "2026-09-30T10:00:00+00:00",
)


def current(created_at: str) -> Run:
    """A run as `execute` leaves it: nobody promoted it."""
    return promoted(created_at=created_at, promoted_at="")


def key(run: Run) -> str:
    return key_of(run.created_at, run.config_hash)


def stored(root: Path, *runs: Run) -> FileResultStore:
    store = FileResultStore(root)
    for run in runs:
        store.write_run(run)
    return store


def broken(store: FileResultStore, name: str) -> None:
    """A file the scan keeps, because its schema is current, and `read_run`
    refuses, because nothing else about it is a run."""
    path = store.runs_dir(TENANT) / SUITE / f"{name}.json"
    path.write_text(json.dumps({"schema_version": SCHEMA_VERSION}), encoding="utf-8")


def promote(store: FileResultStore, run: Run) -> None:
    store.promote_baseline(
        RunRef(tenant=TENANT, suite=SUITE, key=key(run)),
        run.config_hash,
        expected_baseline=None,
        promoted_at="2026-09-30T12:00:00+00:00",
    )


# --------------------------------------------------------------------------- #
# In clear
# --------------------------------------------------------------------------- #


def test_every_run_is_listed_by_key_with_the_baseline_marked(tmp_path: Path) -> None:
    older, newer = current(T1), current(T2)
    store = stored(tmp_path, older, newer)
    promote(store, older)

    listed = suite_runs(store, TENANT, SUITE, mint=None)

    assert [k for k, _ in listed.runs] == [key(older), key(newer)]
    assert [r for _, r in listed.runs] == [older, newer]
    assert listed.baseline_key == key(older)
    assert listed.note() == ""


def test_a_suite_with_no_runs_is_an_empty_list_not_a_refusal(tmp_path: Path) -> None:
    listed = suite_runs(FileResultStore(tmp_path), TENANT, SUITE, mint=None)
    assert listed.runs == ()
    assert listed.baseline_key is None
    assert listed.baseline_refused == ""


def test_one_run_the_store_refuses_does_not_take_the_others_down(
    tmp_path: Path,
) -> None:
    """The scan keeps a file at the current schema, and `read_run` can still
    refuse it. Every caller that read the scan by hand failed the whole list on
    it."""
    store = stored(tmp_path, current(T1), current(T2))
    broken(store, "2026-09-29T11-00-00-00-00-deadbeefdeadbeef")

    listed = suite_runs(store, TENANT, SUITE, mint=None)

    assert len(listed.runs) == 2
    [(refused_key, why)] = listed.refused
    assert refused_key == "2026-09-29T11-00-00-00-00-deadbeefdeadbeef"
    assert "redacted" in why  # the store's own sentence, in clear
    assert refused_key in listed.note()


def test_a_baseline_that_cannot_be_read_is_not_reported_as_none(
    tmp_path: Path,
) -> None:
    store = stored(tmp_path, current(T1))
    store.baseline_path(TENANT, SUITE).write_text(
        json.dumps({"schema_version": SCHEMA_VERSION}), encoding="utf-8"
    )

    listed = suite_runs(store, TENANT, SUITE, mint=None)

    assert listed.baseline_key is None
    assert listed.baseline_refused
    assert "the baseline could not be read" in listed.note()
    assert len(listed.runs) == 1


def test_a_baseline_whose_run_is_not_listed_is_said(tmp_path: Path) -> None:
    gone, kept = current(T1), current(T2)
    store = stored(tmp_path, gone, kept)
    promote(store, gone)
    store.run_path(RunRef(tenant=TENANT, suite=SUITE, key=key(gone))).unlink()

    listed = suite_runs(store, TENANT, SUITE, mint=None)

    assert listed.baseline_key == key(gone)
    assert f"promoted from, {key(gone)}, is not among the runs read" in listed.note()


def test_the_baseline_line_is_true_beside_one_cases_history(tmp_path: Path) -> None:
    """`docs/api.md` puts the note beside a case's history, which has no
    baseline and compares nothing. The line says only what holds there too:
    the run is missing. (#339)"""
    gone, kept = current(T1), current(T2)
    store = stored(tmp_path, gone, kept)
    promote(store, gone)
    store.run_path(RunRef(tenant=TENANT, suite=SUITE, key=key(gone))).unlink()

    note = suite_runs(store, TENANT, SUITE, mint=None).note()

    assert "this list" not in note
    assert "compared" not in note


# --------------------------------------------------------------------------- #
# The line's length, and its language (#339)
# --------------------------------------------------------------------------- #


def left(
    *,
    refused: tuple[tuple[str, str], ...] = (),
    skipped: dict[int, int] | None = None,
    unreadable: tuple[str, ...] = (),
    unnamed: int = 0,
    baseline_key: str | None = None,
    baseline_refused: str = "",
) -> SuiteRuns:
    return SuiteRuns(
        runs=(),
        baseline_key=baseline_key,
        baseline_refused=baseline_refused,
        listing=Listing(runs=(), skipped=skipped or {}, unreadable=unreadable),
        refused=refused,
        unnamed=unnamed,
    )


def test_the_note_names_three_refused_runs_and_counts_the_rest() -> None:
    refused = tuple((f"run-{n}", "Refused") for n in range(5))

    note = left(refused=refused).note()

    assert note == (
        "refused: 5 run(s): run-0 (Refused), run-1 (Refused), run-2 (Refused), "
        "and 2 more"
    )
    assert "run-3" not in note and "run-4" not in note


def test_three_refused_runs_are_all_named_with_nothing_counted() -> None:
    refused = tuple((f"run-{n}", "Refused") for n in range(3))

    note = left(refused=refused).note()

    assert "run-2 (Refused)" in note
    assert "more" not in note


def test_left_out_frames_every_part_in_the_documents_language() -> None:
    listed = left(
        refused=tuple((f"run-{n}", "Refused") for n in range(5)),
        skipped={SCHEMA_VERSION - 1: 2, SCHEMA_VERSION + 1: 1},
        unreadable=("x.json",),
        unnamed=1,
        baseline_key="gone-key",
    )

    line = left_out(listed, locale="it")

    assert "rifiutate: 5 run" in line and "e altre 2" in line
    assert "gone-key" in line
    for english in (
        "ignored",
        "refused",
        "unreadable",
        "left out",
        "baseline was",
        "among the runs",
        "more",
        "upgrade",
        "bring them",
    ):
        assert english not in line, english


def test_left_out_has_no_default_locale() -> None:
    assert inspect.signature(left_out).parameters["locale"].default is (
        inspect.Parameter.empty
    )


def test_left_out_advises_in_the_direction_the_schemas_say() -> None:
    older = left_out(left(skipped={SCHEMA_VERSION - 1: 2}), locale="en")
    newer = left_out(left(skipped={SCHEMA_VERSION + 1: 1}), locale="en")
    refused = left_out(left(refused=(("run-0", "Refused"),)), locale="en")

    assert "digline migrate" in older and "upgrade" not in older
    assert "upgrade digline" in newer and "migrate" not in newer
    assert "migrate" not in refused and "upgrade" not in refused


def test_the_note_keeps_its_advice_off_the_line() -> None:
    """A terminal prints `Listing.advice()` on lines of its own."""
    listed = left(skipped={SCHEMA_VERSION - 1: 2})

    assert listed.note() == f"ignored: 2 run(s) at schema {SCHEMA_VERSION - 1}"
    assert listed.note() == listed.listing.note()


def test_in_english_left_out_is_the_note_where_nothing_is_advised() -> None:
    listed = left(
        refused=(("run-0", "Refused"),), unnamed=2, baseline_refused="Refused"
    )

    assert left_out(listed, locale="en") == listed.note()


def test_a_name_that_is_not_one_segment_refuses_the_whole_call(
    tmp_path: Path,
) -> None:
    with pytest.raises(PathRefusedError):
        suite_runs(FileResultStore(tmp_path), TENANT, "../other", mint=None)


def test_the_minter_has_no_default() -> None:
    """A default would decide for a caller whether its page shows names."""
    parameter = inspect.signature(suite_runs).parameters["mint"]
    assert parameter.default is inspect.Parameter.empty


# --------------------------------------------------------------------------- #
# Projected
# --------------------------------------------------------------------------- #


def test_every_listed_run_is_projected_and_names_nothing(tmp_path: Path) -> None:
    store = stored(tmp_path, current(T1), current(T2), current(T3))

    listed = suite_runs(store, TENANT, SUITE, mint=Table())

    assert len(listed.runs) == 3
    for _, run in listed.runs:
        assert run.projected
        document = run_to_json(run)
        assert not [name for name in NAMES if name in document]


def test_rows_pair_by_name_across_the_list(tmp_path: Path) -> None:
    """What `runs_page` does with the list: hold each row's aggregates against
    the baseline's, by name. One token per name across the whole list."""
    store = stored(tmp_path, current(T1), current(T2))
    table = Table()

    listed = suite_runs(store, TENANT, SUITE, mint=table)

    names = [{v.score.name for v in run.aggregate} for _, run in listed.runs]
    assert names[0] == names[1]
    assert table.token("verdict_name", FAMILY) in names[0]


def test_a_key_is_the_same_projected_and_in_clear(tmp_path: Path) -> None:
    older, newer = current(T1), current(T2)
    store = stored(tmp_path, older, newer)
    promote(store, older)

    clear = suite_runs(store, TENANT, SUITE, mint=None)
    shown = suite_runs(store, TENANT, SUITE, mint=Table())

    assert [k for k, _ in shown.runs] == [k for k, _ in clear.runs]
    assert [key(r) for _, r in shown.runs] == [k for k, _ in shown.runs]
    assert shown.baseline_key == clear.baseline_key


def test_a_run_that_cannot_be_projected_is_left_out_not_shown_in_clear(
    tmp_path: Path,
) -> None:
    """A readable `assertion_id` is refused by the projection; its sentence
    quotes the id, so a projected page carries the refusal's type only."""
    readable = "leaks-account-data-for-rossi"
    bad = current(T2)
    bad = replace(
        bad,
        results=(
            replace(
                bad.results[0],
                verdicts=tuple(
                    replace(v, assertion_id=readable) for v in bad.results[0].verdicts
                ),
            ),
            *bad.results[1:],
        ),
    )
    store = stored(tmp_path, current(T1), bad)

    listed = suite_runs(store, TENANT, SUITE, mint=Table())

    assert [k for k, _ in listed.runs] == [key(current(T1))]
    assert listed.refused == ((key(bad), "ProjectionRefusedError"),)
    assert readable not in listed.note()
    assert CHECK not in listed.note()


def test_a_refusal_on_a_projected_list_carries_no_sentence(tmp_path: Path) -> None:
    store = stored(tmp_path, current(T1))
    broken(store, "2026-09-29T11-00-00-00-00-deadbeefdeadbeef")

    listed = suite_runs(store, TENANT, SUITE, mint=Table())

    assert listed.refused == (
        ("2026-09-29T11-00-00-00-00-deadbeefdeadbeef", "DocumentRefusedError"),
    )


class Forgetful(FileResultStore):
    """A store that wipes the minter's table before every read: each run is
    projected consistently on its own, and differently from the one before.
    `project_served` alone passes every run of it."""

    table: Table

    def read_run(self, ref: RunRef) -> Run:
        self.table.rows.clear()
        return super().read_run(ref)


def test_a_minter_that_answers_a_name_two_ways_across_the_list_is_refused(
    tmp_path: Path,
) -> None:
    store = Forgetful(tmp_path)
    store.table = Table()
    store.write_run(current(T1))
    store.write_run(current(T2))

    with pytest.raises(ProjectionRefusedError, match="two tokens in one list"):
        suite_runs(store, TENANT, SUITE, mint=store.table)


def test_a_minter_answering_without_a_tokens_form_refuses_the_whole_call(
    tmp_path: Path,
) -> None:
    """Not one run left out: every run would meet the same minter."""
    store = stored(tmp_path, current(T1), current(T2))

    def echo(kind: TokenKind, text: str) -> str:
        return text

    with pytest.raises(ProjectionRefusedError, match="token's form") as refused:
        suite_runs(store, TENANT, SUITE, mint=echo)
    assert not [name for name in NAMES if name in str(refused.value)]


def test_a_minter_giving_two_names_one_token_refuses_the_whole_call(
    tmp_path: Path,
) -> None:
    store = stored(tmp_path, current(T1))
    one = secrets.token_urlsafe(16)

    with pytest.raises(ProjectionRefusedError, match="two names would read as one"):
        suite_runs(store, TENANT, SUITE, mint=lambda kind, text: one)


def test_what_it_raises_is_a_refusal() -> None:
    assert ProjectionRefusedError in REFUSALS
    assert PathRefusedError in REFUSALS


# --------------------------------------------------------------------------- #
# A file name that is not a run key (delta-pass over 0.25.2, F-1)
# --------------------------------------------------------------------------- #

PERSON = "rossi-mario-IT60X0542811101"


def renamed(store: FileResultStore, run: Run, name: str) -> None:
    """File `run` under `name` instead of the key digline gives it."""
    directory = store.runs_dir(TENANT) / SUITE
    (directory / f"{key(run)}.json").rename(directory / f"{name}.json")


def test_a_run_filed_under_a_persons_name_is_not_named_on_a_projected_list(
    tmp_path: Path,
) -> None:
    kept, moved = current(T1), current(T2)
    store = stored(tmp_path, kept, moved)
    renamed(store, moved, PERSON)

    listed = suite_runs(store, TENANT, SUITE, mint=Table())

    assert [k for k, _ in listed.runs] == [key(kept)]
    assert listed.unnamed == 1
    assert listed.refused == ()
    assert PERSON not in listed.note()
    assert "left out without a name: 1" in listed.note()


def test_in_clear_the_same_run_is_listed_under_its_file_name(tmp_path: Path) -> None:
    """The owner's own list addresses the file as the store does."""
    kept, moved = current(T1), current(T2)
    store = stored(tmp_path, kept, moved)
    renamed(store, moved, PERSON)

    listed = suite_runs(store, TENANT, SUITE, mint=None)

    assert sorted(k for k, _ in listed.runs) == sorted([key(kept), PERSON])
    assert listed.unnamed == 0


def test_a_run_filed_under_another_runs_key_is_not_listed_projected(
    tmp_path: Path,
) -> None:
    """A run key's form is not enough: a readable run is listed only under its
    own `key_of`."""
    moved = current(T2)
    store = stored(tmp_path, moved)
    renamed(store, moved, key(current(T1)))

    listed = suite_runs(store, TENANT, SUITE, mint=Table())

    assert listed.runs == ()
    assert listed.unnamed == 1


def test_a_refused_file_named_after_a_person_is_counted_not_named(
    tmp_path: Path,
) -> None:
    store = stored(tmp_path, current(T1))
    broken(store, PERSON)

    listed = suite_runs(store, TENANT, SUITE, mint=Table())

    assert listed.refused == ()
    assert listed.unnamed == 1
    assert PERSON not in listed.note()


def test_control_characters_in_a_file_name_do_not_reach_a_projected_note(
    tmp_path: Path,
) -> None:
    hostile = "x\x1b[31mred\x9b"
    store = stored(tmp_path, current(T1))
    broken(store, hostile)

    listed = suite_runs(store, TENANT, SUITE, mint=Table())

    assert listed.unnamed == 1
    assert "\x1b" not in listed.note() and "\x9b" not in listed.note()


def test_a_refused_file_with_a_run_keys_form_is_still_named(tmp_path: Path) -> None:
    """A run key names nothing, so a refusal under one stays legible."""
    store = stored(tmp_path, current(T1))
    broken(store, "2026-09-29T11-00-00-00-00-deadbeefdeadbeef")

    listed = suite_runs(store, TENANT, SUITE, mint=Table())

    assert listed.unnamed == 0
    assert [k for k, _ in listed.refused] == [
        "2026-09-29T11-00-00-00-00-deadbeefdeadbeef"
    ]
