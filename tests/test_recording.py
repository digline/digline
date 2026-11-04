"""A recording: its document, its version, and where the store files it.
(ADR 0058 §3, §4, §5, §11)

What is held here:

- the response compartment is the run document's own serializer, by identity
  and by the bytes it writes, for every shape a recorded response takes;
- a recording at another version is refused by name, both versions in the
  sentence, and never read as this one;
- a recording is filed under `.digline/<source_tenant>/recordings/<process>/`,
  the subdirectory chosen at the first write and again after a fork, written
  whole or not at all, never over another;
- the generated `.gitignore` keeps `*/recordings/` and `*/recorder.toml` out of
  git;
- an episode's steps come back as written, a tool step's call by the run
  document's own serializer of a tool call, and a step that breaks §7 is
  refused: a finish on a tool step, a call on a model step, an index out of
  order.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from digline.core import RecordedResponse, RecordedToolCall, Usage
from digline.core.recording import (
    RECORDING_VERSION,
    Recording,
    RecordingRefusedError,
    recording_from_dict,
    recording_to_dict,
    setup_digest_of,
)
from digline.core.refused import RefusedError
from digline.core.run import (
    RecordedStep,
    _response_from_dict,  # pyright: ignore[reportPrivateUsage]
    _response_to_dict,  # pyright: ignore[reportPrivateUsage]
    _tool_call_from_dict,  # pyright: ignore[reportPrivateUsage]
    _tool_call_to_dict,  # pyright: ignore[reportPrivateUsage]
    recorded_response_from_dict,
    recorded_response_to_dict,
    recorded_tool_call_from_dict,
    recorded_tool_call_to_dict,
)
from digline.store.file_store import FileResultStore, RecordingWriter

SETUP: dict[str, object] = {"model": "a-model", "system": "Be brief.", "temperature": 0}

#: Every shape the response compartment takes: plain text, a trajectory with a
#: nameless call and a failed one, counts, a zero-call answer, withheld and
#: oversize. One serializer has to be the same on each of them.
RESPONSES: dict[str, RecordedResponse] = {
    "text": RecordedResponse(output="Paris", kind="text", input="Capital?"),
    "trajectory": RecordedResponse(
        output="{}",
        kind="structured",
        input="Look it up",
        cost_usd=0.0012,
        latency_ms=812.5,
        tool_calls=(
            RecordedToolCall(tool="lookup", arguments='{"id":7}', result="found"),
            RecordedToolCall(
                tool=None,
                status="not_reported",
                result_absence="not_reported",
            ),
            RecordedToolCall(tool="send", status="error", result="timeout"),
        ),
        usage=Usage(input_tokens=120, output_tokens=40, cache_read_tokens=8),
    ),
    "no-calls": RecordedResponse(output="no", kind="text", tool_calls=()),
    "withheld": RecordedResponse(withheld=True),
    "oversize": RecordedResponse(oversize=True, cost_usd=0.5),
}


def a_recording(
    response: RecordedResponse | None = None, /, **changes: object
) -> Recording:
    fields: dict[str, object] = {
        "source_tenant": "acme",
        "app": "support-bot",
        "suite": "triage",
        "case": {"messages": [{"role": "user", "content": "Capital?"}]},
        "setup": SETUP,
        "setup_digest": setup_digest_of(SETUP),
        "response": response or RESPONSES["text"],
    }
    fields.update(changes)
    return Recording(**fields)  # pyright: ignore[reportArgumentType]


# -- the document ------------------------------------------------------------- #


def test_the_public_names_are_the_run_documents_own_functions() -> None:
    assert recorded_response_to_dict is _response_to_dict
    assert recorded_response_from_dict is _response_from_dict
    assert recorded_tool_call_to_dict is _tool_call_to_dict
    assert recorded_tool_call_from_dict is _tool_call_from_dict


LOOKUP = RecordedToolCall(
    tool="lookup",
    arguments='{"order":"A1"}',
    status="not_reported",
    result_absence="not_reported",
)
STEPS = (
    RecordedStep(index=0, actor="model", finish="tool_use"),
    RecordedStep(index=1, actor="tool", call=LOOKUP),
    RecordedStep(index=2, actor="model"),
)


def an_episode(**changes: object) -> Recording:
    fields: dict[str, object] = {"steps": STEPS, "episode": "f" * 32}
    fields.update(changes)
    return a_recording(RESPONSES["text"], **fields)


@pytest.mark.parametrize(
    "changes",
    [{}, {"interrupted": True}, {"unrecorded_children": 2}, {"steps": ()}],
    ids=["plain", "interrupted", "unrecorded", "no-steps"],
)
def test_an_episode_comes_back_as_it_was_written(changes: dict[str, object]) -> None:
    recording = an_episode(**changes)
    document = json.loads(json.dumps(recording_to_dict(recording)))
    assert recording_from_dict(document) == recording


def test_a_recording_whose_step_breaks_the_steps_rules_is_refused_as_a_recording() -> (
    None
):
    """The step's rules are the run document's since schema 23, and a
    recording read with one says so as a recording, naming the step."""
    document = json.loads(json.dumps(recording_to_dict(an_episode())))
    document["steps"][2]["finish"] = ""
    with pytest.raises(
        RecordingRefusedError, match="a recording's step 2: .*non-empty"
    ):
        recording_from_dict(document)


def test_a_steps_tool_call_is_written_by_the_run_documents_serializer() -> None:
    written = recording_to_dict(an_episode())
    assert written["steps"] == [
        {"index": 0, "actor": "model", "finish": "tool_use"},
        {"index": 1, "actor": "tool", **_tool_call_to_dict(LOOKUP)},
        {"index": 2, "actor": "model"},
    ]
    assert "interrupted" not in written
    assert "unrecorded_children" not in written


def test_a_single_call_carries_none_of_an_episodes_keys() -> None:
    written = recording_to_dict(a_recording())
    assert not {"steps", "interrupted", "unrecorded_children", "orphan"} & set(written)


def test_an_episodes_id_and_the_time_come_back_as_written() -> None:
    recording = an_episode(id="a" * 32, recorded_at="2026-11-03T08:00:00+00:00")
    written = recording_to_dict(recording)
    assert (written["id"], written["recorded_at"]) == (
        "a" * 32,
        "2026-11-03T08:00:00+00:00",
    )
    assert recording_from_dict(json.loads(json.dumps(written))) == recording
    single = recording_to_dict(a_recording(recorded_at="2026-11-03T08:00:00+00:00"))
    assert "id" not in single


@pytest.mark.parametrize(
    ("changes", "match"),
    [
        ({"id": "a" * 32}, "only an episode carries an id"),
        ({"id": ""}, "Recording.id must be a non-empty string"),
        ({"recorded_at": ""}, "Recording.recorded_at must be a non-empty string"),
    ],
    ids=["id-on-a-call", "empty-id", "empty-time"],
)
def test_the_two_keys_refuse_what_no_writer_writes(
    changes: dict[str, object], match: str
) -> None:
    with pytest.raises(RecordingRefusedError, match=match):
        a_recording(**changes)


def test_an_orphan_comes_back_as_it_was_written() -> None:
    recording = a_recording(orphan=True)
    written = recording_to_dict(recording)
    assert written["orphan"] is True
    assert recording_from_dict(json.loads(json.dumps(written))) == recording


@pytest.mark.parametrize(
    ("step", "match"),
    [
        (
            lambda: RecordedStep(index=0, actor="tool", call=LOOKUP, finish="stop"),
            "no finish",
        ),
        (lambda: RecordedStep(index=0, actor="model", call=LOOKUP), "no tool call"),
        (lambda: RecordedStep(index=0, actor="tool"), "carries its call"),
        (lambda: RecordedStep(index=-1, actor="model"), "from 0"),
        (lambda: RecordedStep(index=True, actor="model"), "from 0"),  # pyright: ignore[reportArgumentType]
        (lambda: RecordedStep(index=0, actor="engine"), "'model' or 'tool'"),  # pyright: ignore[reportArgumentType]
        (lambda: RecordedStep(index=0, actor="model", finish=""), "non-empty"),
    ],
    ids=[
        "tool-finish",
        "model-call",
        "tool-no-call",
        "negative",
        "bool",
        "engine",
        "empty-finish",
    ],
)
def test_a_step_that_breaks_its_rules_is_refused(step: object, match: str) -> None:
    # A step's rules are the run document's since schema 23 (ADR 0060 §5), so
    # they raise the base refusal; a recording read with one re-raises it as
    # its own.
    with pytest.raises(RefusedError, match=match):
        step()  # pyright: ignore[reportCallIssue]


@pytest.mark.parametrize(
    ("changes", "match"),
    [
        ({"steps": (STEPS[1], STEPS[0])}, "in order"),
        ({"steps": None, "interrupted": True}, "single call"),
        ({"steps": None, "unrecorded_children": 1}, "single call"),
        ({"unrecorded_children": -1}, "from 0"),
        ({"orphan": True}, "only a single call"),
    ],
    ids=[
        "order",
        "interrupted-call",
        "unrecorded-call",
        "negative",
        "orphan-episode",
    ],
)
def test_an_episode_that_breaks_its_rules_is_refused(
    changes: dict[str, object], match: str
) -> None:
    with pytest.raises(RecordingRefusedError, match=match):
        an_episode(**changes)


@pytest.mark.parametrize(
    ("key", "value", "match"),
    [
        ("interrupted", False, "true or not at all"),
        ("interrupted", None, "true or not at all"),
        ("orphan", False, "true or not at all"),
        ("unrecorded_children", 0, "positive integer"),
        ("steps", {}, "not a list"),
    ],
)
def test_a_document_that_writes_what_no_writer_writes_is_refused(
    key: str, value: object, match: str
) -> None:
    document = recording_to_dict(an_episode())
    document[key] = value
    with pytest.raises(RecordingRefusedError, match=match):
        recording_from_dict(document)


def test_a_model_step_with_a_tool_calls_keys_is_refused() -> None:
    document = recording_to_dict(an_episode())
    document["steps"] = [{"index": 0, "actor": "model", "tool": "lookup"}]
    with pytest.raises(RecordingRefusedError, match="model step"):
        recording_from_dict(document)


@pytest.mark.parametrize("name", sorted(RESPONSES))
def test_the_response_compartment_is_what_a_run_document_writes(name: str) -> None:
    response = RESPONSES[name]
    written = recording_to_dict(a_recording(response))
    assert written["response"] == _response_to_dict(response)


@pytest.mark.parametrize("name", sorted(RESPONSES))
def test_a_recording_comes_back_as_it_was_written(name: str) -> None:
    recording = a_recording(
        RESPONSES[name], episode="ep-1", label="positive", call_site="app:answer"
    )
    document = json.loads(json.dumps(recording_to_dict(recording)))
    assert recording_from_dict(document) == recording


def test_what_is_not_given_is_absent_not_emptied() -> None:
    written = recording_to_dict(a_recording())
    assert "episode" not in written and "label" not in written
    assert written["recording_version"] == RECORDING_VERSION == 1
    assert set(written) == {
        "recording_version",
        "source_tenant",
        "app",
        "suite",
        "case",
        "setup",
        "setup_digest",
        "response",
    }


def test_the_setup_digest_reads_the_values_not_the_key_order() -> None:
    reordered = dict(reversed(list(SETUP.items())))
    assert setup_digest_of(reordered) == setup_digest_of(SETUP)
    assert setup_digest_of({**SETUP, "temperature": 1}) != setup_digest_of(SETUP)
    assert len(setup_digest_of(SETUP)) == 16


def test_a_value_json_cannot_carry_is_refused_not_collapsed() -> None:
    class Opaque:
        pass

    with pytest.raises(RecordingRefusedError, match="case holds a value JSON"):
        a_recording(case={"when": Opaque()})
    with pytest.raises(RecordingRefusedError, match="setup holds a value JSON"):
        a_recording(setup={"temperature": float("nan")})


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("source_tenant", ""),
        ("app", ""),
        ("suite", ""),
        ("setup_digest", ""),
        ("episode", ""),
        ("call_site", ""),
        ("label", "yes"),
    ],
)
def test_a_field_without_a_value_is_refused(field: str, value: object) -> None:
    with pytest.raises(RecordingRefusedError, match=field):
        a_recording(**{field: value})


# -- the version -------------------------------------------------------------- #


@pytest.mark.parametrize("version", [2, 0, True, "1", 1.0])
def test_a_recording_at_another_version_is_refused_by_name(version: object) -> None:
    document = recording_to_dict(a_recording())
    document["recording_version"] = version
    with pytest.raises(RecordingRefusedError) as refused:
        recording_from_dict(document)
    sentence = str(refused.value)
    assert f"at version {version!r}" in sentence
    assert f"reads version {RECORDING_VERSION}" in sentence


def test_a_recording_at_version_2_written_by_hand_is_not_read_as_1() -> None:
    # Written out in full, as a newer digline might: everything a version 1
    # reader knows is there, and it is still refused.
    document: dict[str, object] = {
        "recording_version": 2,
        "source_tenant": "acme",
        "app": "support-bot",
        "suite": "triage",
        "case": {"messages": []},
        "setup": {},
        "setup_digest": "0123456789abcdef",
        "response": {"output": "Paris", "kind": "text"},
        "steps": [{"actor": "model", "index": 0}],
    }
    with pytest.raises(
        RecordingRefusedError,
        match=r"at version 2 and this digline reads version 1",
    ):
        recording_from_dict(document)


def test_a_document_with_no_version_is_refused_by_name() -> None:
    document = recording_to_dict(a_recording())
    del document["recording_version"]
    with pytest.raises(RecordingRefusedError, match="carries no recording_version"):
        recording_from_dict(document)


# -- the layout and the writer ------------------------------------------------ #


def test_nothing_is_created_before_the_first_write(tmp_path: Path) -> None:
    store = FileResultStore(tmp_path)
    RecordingWriter(store)
    assert not store.recordings_dir("acme").exists()


def test_a_recording_is_filed_under_its_tenant_one_directory_per_process(
    tmp_path: Path,
) -> None:
    store = FileResultStore(tmp_path)
    writer = RecordingWriter(store)
    first = writer.write(a_recording())
    second = writer.write(a_recording(RESPONSES["withheld"]))
    other = writer.write(a_recording(source_tenant="globex"))

    assert first.parent == second.parent
    assert first.parent.parent == store.recordings_dir("acme")
    assert other.parent.parent == store.recordings_dir("globex")
    assert (first.name, second.name) == ("000001.json", "000002.json")
    assert first.parent.name.startswith("p")
    assert sorted(p.name for p in first.parent.iterdir()) == [
        "000001.json",
        "000002.json",
    ]
    assert store.read_recording(second) == a_recording(RESPONSES["withheld"])


def test_a_forked_process_writes_a_directory_of_its_own(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = FileResultStore(tmp_path)
    writer = RecordingWriter(store)
    parent = writer.write(a_recording())
    monkeypatch.setattr("os.getpid", lambda: 999_999_999)
    child = writer.write(a_recording())
    assert child.parent != parent.parent
    assert child.parent.name.startswith("p999999999-")
    assert child.name == "000001.json"


def test_a_recording_is_never_written_over_another(tmp_path: Path) -> None:
    store = FileResultStore(tmp_path)
    writer = RecordingWriter(store)
    first = writer.write(a_recording())
    planted = first.with_name("000002.json")
    planted.write_text("somebody else's\n", encoding="utf-8")
    with pytest.raises(RecordingRefusedError, match="never written over"):
        writer.write(a_recording())
    assert planted.read_text(encoding="utf-8") == "somebody else's\n"
    assert [p.name for p in sorted(first.parent.iterdir())] == [
        "000001.json",
        "000002.json",
    ]


def test_a_tenant_that_could_climb_out_is_refused(tmp_path: Path) -> None:
    writer = RecordingWriter(FileResultStore(tmp_path))
    with pytest.raises(ValueError, match="invalid tenant name"):
        writer.write(a_recording(source_tenant="../elsewhere"))


def test_a_misfiled_recording_is_refused_by_name(tmp_path: Path) -> None:
    store = FileResultStore(tmp_path)
    written = RecordingWriter(store).write(a_recording())
    moved = store.recordings_dir("globex") / "p1-00000000" / "000001.json"
    moved.parent.mkdir(parents=True)
    shutil.copy(written, moved)
    with pytest.raises(RecordingRefusedError, match="misfiled"):
        store.read_recording(moved)


def test_a_recording_at_another_version_on_disk_names_its_file(
    tmp_path: Path,
) -> None:
    store = FileResultStore(tmp_path)
    written = RecordingWriter(store).write(a_recording())
    document = json.loads(written.read_text(encoding="utf-8"))
    document["recording_version"] = 2
    written.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(RecordingRefusedError) as refused:
        store.read_recording(written)
    assert str(written) in str(refused.value)
    assert "at version 2 and this digline reads version 1" in str(refused.value)


def test_the_generated_gitignore_carries_the_two_lines(tmp_path: Path) -> None:
    store = FileResultStore(tmp_path)
    store.ensure_layout("acme")
    rules = (tmp_path / ".digline" / ".gitignore").read_text(encoding="utf-8")
    lines = [r.strip() for r in rules.splitlines()]
    assert "*/recordings/" in lines
    assert "*/recorder.toml" in lines


@pytest.mark.skipif(shutil.which("git") is None, reason="needs git")
def test_git_ignores_a_recording_and_the_switch(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    store = FileResultStore(tmp_path)
    store.ensure_layout("acme")
    recording = RecordingWriter(store).write(a_recording())
    switch = store.recorder_path("acme")
    switch.write_text("redact = 'none'\n", encoding="utf-8")
    for path in (recording, switch):
        checked = subprocess.run(
            ["git", "-C", str(tmp_path), "check-ignore", "-q", str(path)],
            check=False,
        )
        assert checked.returncode == 0, f"{path} is not ignored"


def test_a_broken_response_compartment_is_refused_with_its_file(
    tmp_path: Path,
) -> None:
    store = FileResultStore(tmp_path)
    written = RecordingWriter(store).write(a_recording())
    document = json.loads(written.read_text(encoding="utf-8"))
    document["response"]["kind"] = "not-a-kind"
    written.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(RecordingRefusedError) as refused:
        store.read_recording(written)
    sentence = str(refused.value)
    assert sentence.startswith(f"{written}, response: ")
    assert "'kind' is not one of" in sentence
