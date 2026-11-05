"""`digline.host.where`: one state per store, the first that holds.

Every store here is written by the writers digline uses: `RecordingWriter`
for recordings, `switch_on` and `switch_off` for the switch, `import_elect`
for the reviewed answers a person names, and `digline run` in a subprocess
for the runs. No document is written by hand, so a state is read off the
files the product writes and not off a shape this file assumed.

Each state has a test and, beside it, the control that keeps it from passing
on a store where something else holds.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from tests._helpers import cli

from digline.cli import EXIT_OK
from digline.core.recording import Recording, setup_digest_of
from digline.core.run import RecordedResponse
from digline.host import import_elect, import_listing, load_suite, where
from digline.host.importing import Shape, answer_id
from digline.host.recording import switch_off, switch_on
from digline.host.where import STATES, Where
from digline.recorder import UNASSIGNED
from digline.store.file_store import FileResultStore, RecordingWriter

TENANT = "acme"
SETUP_1: dict[str, object] = {"model": "m", "system": "Be brief."}
SETUP_2: dict[str, object] = {"model": "m", "system": "Be brief, and kind."}

SUITE = """\
from pathlib import Path
from digline.core import JudgeReply, LlmRubric
from digline.host import read_cases
from digline.run import Case, CaptureSource, Response, Suite
HERE = Path(__file__).parent

#: What the judge scores an answer that carries each text; None raises.
SCORES = {scores!r}


def judge(prompt):
    for text, score in SCORES.items():
        if text in prompt:
            if score is None:
                raise RuntimeError("the judge did not answer")
            return JudgeReply(score=score, reason="table")
    return JudgeReply(score=1.0, reason="default")


def target(case):
    return Response(output=str(case.vars["say"]), input="q")


suite = Suite(
    tenant='acme', environment='dev', name='triage',
    assertions=[LlmRubric(rubric='right?', judge=judge, threshold=0.7, tolerance=0.05)],
    cases=[
        Case(id='by-hand', vars={{'say': {say!r}}}),
        *read_cases(HERE / 'captured.json'),
    ],
    samples=2,
    min_agreement='2/2',
    {capture}
)
"""

CAPTURE = (
    "capture=CaptureSource(cases_file='captured.json', repository='private', "
    "check='llm_rubric'),"
)


def write_suite(
    root: Path,
    *,
    capture: bool = True,
    say: str = "fine",
    scores: dict[str, float | None] | None = None,
) -> None:
    (root / "suites").mkdir(exist_ok=True)
    (root / "suites" / "suite.py").write_text(
        SUITE.format(scores=scores or {}, say=say, capture=CAPTURE if capture else ""),
        encoding="utf-8",
    )


def asked(text: str) -> dict[str, object]:
    return {"messages": [{"role": "user", "content": text}]}


def record(
    root: Path,
    *items: tuple[str, str, dict[str, object], str],
    suite: str = "triage",
) -> None:
    """Each item is a question, an answer, a setup and an instant, written by
    the recorder's own writer."""
    writer = RecordingWriter(FileResultStore(root))
    for question, answer, setup, at in items:
        writer.write(
            Recording(
                source_tenant=TENANT,
                app="support",
                suite=suite,
                case=asked(question),
                setup=setup,
                setup_digest=setup_digest_of(setup),
                response=RecordedResponse(output=answer, kind="text", input="q"),
                recorded_at=at,
            )
        )


def read(root: Path, *, with_suite: bool = True) -> Where:
    if not with_suite:
        return where(root, TENANT, suite=None, module=None)
    suite, found = load_suite(str(root / "suites" / "suite.py"), root=root)
    return where(root, TENANT, suite=suite, module=found.module)


def elect(root: Path, **names: Any) -> None:
    """A person's yes or no, written by the import."""
    suite, found = load_suite(str(root / "suites" / "suite.py"), root=root)
    listing = import_listing(root, suite, found.module, TENANT)
    import_elect(listing, by="Ada", **names)


def run(root: Path, *, exits: int = EXIT_OK) -> None:
    done = cli(root, "run", "--suite", "suites/suite.py")
    assert done.returncode == exits, done.stderr


#: Two answers to one question, under the first setup, before any run.
EARLY = (
    ("refund?", "in 14 days", SETUP_1, "2026-11-03T08:01:00+00:00"),
    ("hours?", "nine to five", SETUP_1, "2026-11-03T08:02:00+00:00"),
)
REFUND_ID = answer_id(asked("refund?"), "in 14 days")
HOURS_ID = answer_id(asked("hours?"), "nine to five")


@pytest.fixture
def root(tmp_path: Path) -> Path:
    write_suite(tmp_path)
    return tmp_path


def test_the_states_are_eleven_in_order() -> None:
    assert STATES[0] == "nothing_recorded" and STATES[-1] == "last_run_red"
    assert len(STATES) == len(set(STATES)) == 11


# 1 ------------------------------------------------------------------------ #


def test_nothing_recorded_and_never_run(root: Path) -> None:
    assert read(root).state == "nothing_recorded"
    assert read(root, with_suite=False).state == "nothing_recorded"


def test_a_suite_that_has_run_is_past_nothing_recorded(root: Path) -> None:
    """Cases written by hand, a run, and no recorder: not the first state."""
    run(root)
    assert read(root).state != "nothing_recorded"


# 2 ------------------------------------------------------------------------ #


def test_recording_off_with_everything_imported_and_no_run(root: Path) -> None:
    record(root, *EARLY)
    elect(root, good=[REFUND_ID])
    switch_off(root, TENANT)
    found = read(root)
    assert found.state == "recording_off"
    assert found.count == 2


def test_the_same_store_switched_on_has_not_run(root: Path) -> None:
    record(root, *EARLY)
    elect(root, good=[REFUND_ID])
    switch_on(root, TENANT, production=False)
    assert read(root).state == "never_run"


def test_an_absent_switch_is_not_off(root: Path) -> None:
    """`DIGLINE_RECORD=1` records with no file: no file is not *off*."""
    record(root, *EARLY)
    elect(root, good=[REFUND_ID])
    assert read(root).state == "never_run"


# 3 ------------------------------------------------------------------------ #


def test_calls_that_named_no_suite(root: Path) -> None:
    record(root, *EARLY, suite=UNASSIGNED)
    found = read(root)
    assert found.state == "unassigned"
    assert found.count == 2


def test_one_call_that_named_a_suite_is_past_unassigned(root: Path) -> None:
    record(root, *EARLY, suite=UNASSIGNED)
    record(root, EARLY[0])
    assert read(root).state != "unassigned"


# 4 ------------------------------------------------------------------------ #


def test_recordings_no_suite_reads_yet_with_their_shapes(root: Path) -> None:
    write_suite(root, capture=False)
    record(root, *EARLY)
    found = read(root)
    assert found.state == "no_suite_yet"
    assert (found.suite, found.count) == ("triage", 2)
    assert found.shapes == ((Shape(episode=False, kind="text"), 2),)


def test_without_a_suite_the_recordings_name_one(root: Path) -> None:
    record(root, *EARLY)
    found = read(root, with_suite=False)
    assert (found.state, found.suite, found.count) == ("no_suite_yet", "triage", 2)


def test_a_capture_declaration_is_past_no_suite_yet(root: Path) -> None:
    record(root, *EARLY)
    assert read(root).state != "no_suite_yet"


# 5 ------------------------------------------------------------------------ #


def test_recordings_never_imported(root: Path) -> None:
    record(root, *EARLY)
    found = read(root)
    assert (found.state, found.count) == ("to_import", 2)


def test_recordings_after_the_last_import(root: Path) -> None:
    record(root, *EARLY)
    elect(root, good=[REFUND_ID])
    record(root, ("parcel?", "found it", SETUP_1, "2026-11-03T09:00:00+00:00"))
    found = read(root)
    assert (found.state, found.count) == ("to_import", 1)


# 6 ------------------------------------------------------------------------ #


def test_reviewed_and_never_run(root: Path) -> None:
    record(root, *EARLY)
    elect(root, good=[REFUND_ID], bad=[HOURS_ID])
    found = read(root)
    assert (found.state, found.count) == ("never_run", 2)


# 7 ------------------------------------------------------------------------ #


def test_the_judge_contradicts_a_person(root: Path) -> None:
    record(root, *EARLY)
    elect(root, good=[REFUND_ID], bad=[HOURS_ID])
    run(root)  # the judge passes everything, the no included
    found = read(root)
    assert (found.state, found.count) == ("judge_disagrees", 1)
    assert found.exit_code == 1


def test_a_judge_that_agrees_is_past_disagreement(root: Path) -> None:
    write_suite(root, scores={"nine to five": 0.0})
    record(root, *EARLY)
    elect(root, good=[REFUND_ID], bad=[HOURS_ID])
    run(root)
    assert read(root).state != "judge_disagrees"


# 8 ------------------------------------------------------------------------ #


def test_green_without_a_red(root: Path) -> None:
    record(root, *EARLY)
    elect(root, good=[REFUND_ID])
    run(root)
    found = read(root)
    assert found.state == "green_without_red"
    assert found.exit_code == 0 and found.run_key is not None


def test_one_failed_check_in_an_older_run_is_past_green_without_red(
    root: Path,
) -> None:
    """The newest run fails nothing, and the one before it failed a check:
    the suite has shown it can fail."""
    write_suite(root, scores={"fine": 0.0})
    record(root, *EARLY)
    elect(root, good=[REFUND_ID])
    run(root)
    write_suite(root)
    run(root)
    assert read(root).state == "nothing_to_do"


# 9 ------------------------------------------------------------------------ #


def test_answers_from_a_setup_that_came_after_the_newest_run(root: Path) -> None:
    write_suite(root, scores={"nine to five": 0.0})
    record(root, *EARLY)
    elect(root, good=[REFUND_ID], bad=[HOURS_ID])
    run(root)
    record(
        root,
        ("refund?", "in fourteen days", SETUP_2, "2099-01-01T08:00:00+00:00"),
        ("hours?", "nine to six", SETUP_2, "2099-01-01T08:01:00+00:00"),
    )
    elect(root, good=[answer_id(asked("refund?"), "in fourteen days")])
    found = read(root)
    assert (found.state, found.count) == ("new_setup", 2)


def test_a_new_setup_before_the_newest_run_is_past_it(root: Path) -> None:
    """The same answers under a new setup, recorded before the newest run: the
    run has read that setup, and the state is the next one. A failed check
    in the run keeps it past `green_without_red`, so this one is asked."""
    write_suite(root, scores={"fine": 0.0})
    record(
        root,
        *EARLY,
        ("refund?", "in fourteen days", SETUP_2, "2026-11-03T09:00:00+00:00"),
    )
    elect(root, good=[answer_id(asked("refund?"), "in fourteen days")])
    run(root)
    assert read(root).state == "nothing_to_do"


# 10 ----------------------------------------------------------------------- #


def test_nothing_to_do(root: Path) -> None:
    write_suite(root, scores={"nine to five": 0.0})
    record(root, *EARLY)
    elect(root, good=[REFUND_ID], bad=[HOURS_ID])
    run(root)
    found = read(root)
    assert found.state == "nothing_to_do"
    assert found.count == 3  # the case by hand and the two reviewed
    assert found.last_import == "2026-11-03T08:02:00+00:00"


# 11 ----------------------------------------------------------------------- #


def test_a_red_run_no_state_above_names(root: Path) -> None:
    write_suite(root, scores={"nine to five": 0.0, "fine": None})
    record(root, *EARLY)
    elect(root, good=[REFUND_ID], bad=[HOURS_ID])
    run(root, exits=2)  # the one measured case could not be judged
    found = read(root)
    assert (found.state, found.exit_code) == ("last_run_red", 2)
