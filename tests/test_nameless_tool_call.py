"""The tool call nobody named (ADR 0018 §1, amended 2026-09-17).

A provider can hand over a call without the name of its tool — none of the
three SDKs validates a reply — and every reader before schema 13 turned that
into a tool named `"None"`, or errored the whole case. The document now omits
`tool` and says `"tool_absence": "not_reported"`; `ToolsCalled` never passes over
such a call, fails where the mismatch is settled without it, and errors
otherwise.

The cross-version tests at the bottom run 0.14.1's own source, taken from its
tag, and are skipped where the tags are absent, as `test_recorded_output.py`
skips its own.
"""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tarfile
from pathlib import Path
from typing import Any

import pytest
from tests._helpers import stamp_journal_format
from tests.test_recorded_output import CREATED, LATER, suite

from digline.core import (
    EvaluatorInputs,
    RecordedToolCall,
    ToolCalledWith,
    ToolsCalled,
    record_trajectory,
    redact,
    run_from_json,
    run_to_json,
    without_responses,
)
from digline.core.run import SCHEMA_VERSION, run_to_dict
from digline.host import measure, prepare
from digline.run import Case, Response, Suite, Target, execute, rejudge
from digline.store import FileResultStore, journal_key
from digline.store.migrate import upgrade_document
from digline.targets import Completion, ToolCall, Usage

# --------------------------------------------------------------------------- #
# A target shaped like a plugin meeting a non-conforming server
# --------------------------------------------------------------------------- #


def unnamed_then_lookup() -> Target:
    """What every plugin now reports for a reply whose first call has no name."""

    def target(case: Case) -> Response:
        completion = Completion(
            text="Let me look that up.",
            usage=Usage(1, 1),
            tools=(None, "lookup"),
            tool_calls=(
                ToolCall(tool=None, arguments={"q": "x"}, status="not_reported"),
                ToolCall(
                    tool="lookup", arguments={"order_id": "4711"}, status="not_reported"
                ),
            ),
        )
        return Response(
            output=completion.text,
            input=f"refund {case.id}?",
            metadata=dict(completion.as_metadata()),
        )

    return target


def nameless_suite(**extra: object) -> Suite:
    declared: dict[str, object] = {
        "record_responses": True,
        "assertions": [
            ToolsCalled(expected=["search", "lookup"]),
            ToolCalledWith(tool="lookup", arguments={"order_id": "4711"}),
        ],
    }
    declared.update(extra)
    return suite(**declared)


def recorded_calls(document: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        call
        for case in document["results"]
        for response in case["responses"]
        for call in response["tool_calls"]
    ]


# --------------------------------------------------------------------------- #
# The value and the document
# --------------------------------------------------------------------------- #


def test_the_document_omits_tool_and_declares_why() -> None:
    """Never `"tool": null`: that is the shape every earlier reader turns into a
    tool named "None". The named call beside it is written as it always was."""
    run = execute(nameless_suite(), unnamed_then_lookup(), created_at=CREATED)
    calls = recorded_calls(json.loads(run_to_json(run)))
    unnamed, named = calls[0], calls[1]
    assert "tool" not in unnamed
    assert unnamed["tool_absence"] == "not_reported"
    assert named["tool"] == "lookup" and "tool_absence" not in named


def test_it_reads_back_as_the_absence_it_was() -> None:
    run = execute(nameless_suite(), unnamed_then_lookup(), created_at=CREATED)
    again = run_from_json(run_to_json(run))
    tools = [
        call.tool
        for case in again.results
        for response in case.responses
        for call in response.tool_calls or ()
    ]
    assert tools == [None, "lookup"] * 2


@pytest.mark.parametrize(
    ("entry", "named"),
    [
        ({"tool": None}, "'tool' is null"),
        ({"tool": 5}, "'tool' is int"),
        ({"tool": "lookup", "tool_absence": "not_reported"}, "both 'tool' and"),
        ({"tool_absence": "not_recorded"}, "'tool_absence' must be"),
        ({"tool_absence": None}, "'tool_absence' must be"),
        ({}, "missing the mandatory field 'tool'"),
    ],
    ids=["null", "not-a-string", "both", "not-recorded", "absence-null", "neither"],
)
def test_a_document_that_says_it_badly_is_refused_by_name(
    entry: dict[str, object], named: str
) -> None:
    run = execute(nameless_suite(), unnamed_then_lookup(), created_at=CREATED)
    document = json.loads(run_to_json(run))
    call = document["results"][0]["responses"][0]["tool_calls"][0]
    call.pop("tool", None)
    call.pop("tool_absence", None)
    call.update(entry)
    with pytest.raises(ValueError, match=named):
        run_from_json(json.dumps(document))


def test_an_empty_name_is_still_refused_and_none_is_not() -> None:
    """A writer that does not know says `None`; `""` is not a name either."""
    assert RecordedToolCall(tool=None).tool is None
    assert ToolCall(tool=None, arguments=None, status="not_reported").tool is None
    with pytest.raises(ValueError, match="must not be empty"):
        RecordedToolCall(tool="")
    with pytest.raises(ValueError, match="must not be empty"):
        ToolCall(tool="", arguments=None, status="not_reported")


def test_a_plain_target_that_says_none_records_the_absence_not_a_name() -> None:
    """`record_trajectory` did `str(item.get("tool", ""))`, so a mapper's
    `"tool": None` became a tool named "None"."""
    entries: list[dict[str, object]] = [{"tool": None, "arguments": {}}]
    calls = record_trajectory({"tool_calls": entries})
    assert calls is not None
    (call,) = calls
    assert call.tool is None


@pytest.mark.parametrize(
    ("entry", "named"),
    [
        ({"arguments": {}}, "no 'tool' in it"),
        ({"tool": 5}, "whose 'tool' is int"),
        ({"tool": ""}, "must not be empty"),
    ],
    ids=["no-key", "not-a-string", "empty"],
)
def test_a_target_that_reports_it_badly_raises(
    entry: dict[str, object], named: str
) -> None:
    """Strict about shape: a mapping with no `tool` key is a malformed entry,
    not the statement that nobody named it."""
    with pytest.raises(ValueError, match=named):
        record_trajectory({"tool_calls": [entry]})


def test_the_live_record_agrees_with_itself_on_the_absence() -> None:
    call = ToolCall(tool=None, arguments=None, status="not_reported")
    assert Completion(text="", usage=Usage(1, 1), tools=(None,), tool_calls=(call,))
    with pytest.raises(ValueError, match="same tools"):
        Completion(text="", usage=Usage(1, 1), tools=("None",), tool_calls=(call,))


# --------------------------------------------------------------------------- #
# ToolsCalled: never passes, fails where settled, errors where it turns on it
# --------------------------------------------------------------------------- #


def reported(*tools: object) -> EvaluatorInputs:
    return EvaluatorInputs(output="", metadata={"response": {"tools": list(tools)}})


@pytest.mark.parametrize(
    ("tools", "expected"),
    [
        ((None, "cite"), ["search", "cite"]),
        (("search", None), ["search", "cite"]),
        ((None, None), ["search", "cite"]),
    ],
    ids=["first", "last", "both"],
)
def test_it_errors_where_every_named_call_matches(
    tools: tuple[str | None, ...], expected: list[str]
) -> None:
    """The missing name is what decides, so neither pass nor fail is known."""
    verdict = ToolsCalled(expected=expected)(reported(*tools))
    assert verdict.status == "error"
    unnamed = ", ".join(str(i + 1) for i, name in enumerate(tools) if name is None)
    assert f"position(s) {unnamed}" in verdict.reason
    assert "without the name of its tool" in verdict.reason


@pytest.mark.parametrize(
    ("tools", "expected"),
    [
        ((None,), ["search", "cite"]),
        ((None, "cite", "extra"), ["search", "cite"]),
        ((None, "refund"), ["search", "cite"]),
        (("refund", None), ["search", "cite"]),
    ],
    ids=["fewer", "more", "named-mismatch-after", "named-mismatch-before"],
)
def test_it_fails_where_the_reply_settles_the_mismatch_without_it(
    tools: tuple[str | None, ...], expected: list[str]
) -> None:
    """Erroring these would hide a real regression behind a reporter's gap."""
    verdict = ToolsCalled(expected=expected)(reported(*tools))
    assert verdict.status == "fail"
    assert "an unnamed call" in verdict.reason
    assert "'None'" not in verdict.reason


def test_null_keeps_its_position_in_called() -> None:
    """Dropping the hole would shift every later name into a place it did not
    hold — falsifying the order this check judges."""
    verdict = ToolsCalled(expected=["search", "cite"])(reported(None, "refund"))
    assert verdict.score.metadata == {"tool_calls": 2, "called": [None, "refund"]}
    document = json.loads(json.dumps(dict(verdict.score.metadata)))
    assert document["called"] == [None, "refund"]


@pytest.mark.parametrize("entry", [5, "", ["lookup"]], ids=["int", "empty", "list"])
def test_anything_that_is_neither_a_name_nor_its_absence_is_unreadable(
    entry: object,
) -> None:
    """`str()` is what once read `None` as a name; it reads nothing now."""
    verdict = ToolsCalled(expected=["lookup"])(reported(entry))
    assert verdict.status == "error"
    assert "not by a name" in verdict.reason


def test_a_live_none_is_not_a_call_to_a_tool_named_none() -> None:
    """The live half of the defect: `str(name)` over `tools` passed this."""
    assert ToolsCalled(expected=["None"])(reported(None)).status == "error"


# --------------------------------------------------------------------------- #
# The replay judges what the live run judged
# --------------------------------------------------------------------------- #


def test_a_replay_judges_the_unnamed_call_exactly_as_the_run_did() -> None:
    """`ToolsCalled` errors — every named call matches — and `ToolCalledWith`
    passes on the named call, stepping over the one it cannot read. Both
    readings survive the document."""
    declared = nameless_suite()
    source = execute(declared, unnamed_then_lookup(), created_at=CREATED)
    live = [(v.name, v.status) for c in source.results for v in c.verdicts]
    assert live == [("tools_called", "error"), ("tool_called_with", "pass")] * 2
    again = rejudge(declared, source, key="src-key", created_at=LATER)
    assert [(v.name, v.status) for c in again.results for v in c.verdicts] == live


# --------------------------------------------------------------------------- #
# The passenger rule (ADR 0014 §1)
# --------------------------------------------------------------------------- #


def test_it_leaves_config_hash_alone() -> None:
    """Payload, not configuration: the suite that records it hashes as before."""
    declared = nameless_suite()
    run = execute(declared, unnamed_then_lookup(), created_at=CREATED)
    assert run.config_hash == declared.config_hash()


def test_it_does_not_cross_a_boundary_or_reach_a_baseline() -> None:
    run = execute(nameless_suite(), unnamed_then_lookup(), created_at=CREATED)
    assert "tool_absence" in run_to_json(run)
    assert "tool_absence" not in run_to_json(redact(run))
    assert "tool_absence" not in run_to_json(without_responses(run))


def test_the_step_to_thirteen_writes_nothing() -> None:
    """No schema-12 writer could omit `tool`, so there is nothing to add.

    Read from 12 all the way to the current version, so the claim survives every
    later bump: 13 -> 14 writes nothing either, because `usage` has no honest
    value in a document that recorded none (ADR 0025 §7).
    """
    run = execute(nameless_suite(), unnamed_then_lookup(), created_at=CREATED)
    current = run_to_dict(run)
    assert SCHEMA_VERSION == 16
    assert upgrade_document({**current, "schema_version": 12}) == current


def test_a_none_already_recorded_is_neither_rewritten_nor_refused() -> None:
    """The residue, left alone: `"tool": "None"` at 12 may have been a call
    nobody named, and may be a tool really named `None`. Rewriting would guess;
    refusing would break a valid document."""
    run = execute(nameless_suite(), unnamed_then_lookup(), created_at=CREATED)
    document = run_to_dict(run)
    for call in recorded_calls(document):
        call.pop("tool_absence", None)
        call.setdefault("tool", "None")
    at_twelve = {**document, "schema_version": 12}
    upgraded = upgrade_document(at_twelve)
    assert recorded_calls(upgraded)[0] == {**recorded_calls(at_twelve)[0]}
    assert recorded_calls(upgraded)[0]["tool"] == "None"
    read = run_from_json(json.dumps(upgraded))
    assert read.results[0].responses[0].tool_calls[0].tool == "None"  # type: ignore[index]


# --------------------------------------------------------------------------- #
# The old reader, from its tag: two locks, and the journal has only one
# --------------------------------------------------------------------------- #


def old_source(tmp_path: Path) -> Path:
    root = Path(__file__).resolve().parents[1]
    archive = subprocess.run(  # noqa: S603
        ["git", "archive", "v0.14.1", "src"],  # noqa: S607
        cwd=root,
        capture_output=True,
        check=False,
    )
    if archive.returncode != 0:
        pytest.skip("v0.14.1 is not in this checkout (shallow clone, no tags)")
    with tarfile.open(fileobj=io.BytesIO(archive.stdout)) as tar:
        tar.extractall(tmp_path / "old", filter="data")
    return tmp_path / "old" / "src"


def run_old(source: Path, code: str, *args: str) -> subprocess.CompletedProcess[str]:
    read = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-c",
            "import digline; print(digline.__file__); " + code,
            *args,
        ],
        env={**os.environ, "PYTHONPATH": str(source)},
        capture_output=True,
        text=True,
        check=False,
    )
    # Proof the old source is what ran, not this checkout's editable install.
    assert read.stdout.startswith(str(source)), read.stdout + read.stderr
    return read


READ_RUN = (
    "import sys, digline.core as c; "
    "c.run_from_json(open(sys.argv[1], encoding='utf-8').read())"
)


def test_0_14_1_refuses_a_newer_document_on_its_version(tmp_path: Path) -> None:
    """The outer lock, and the bump's: *a newer schema*, not a damaged file.

    The expected number is read off `SCHEMA_VERSION` rather than written in, so
    this keeps asserting the lock instead of the day's constant — it was pinned
    to 13 and went stale the moment ADR 0025 opened 14.
    """
    source = old_source(tmp_path)
    document = tmp_path / "run.json"
    document.write_text(
        run_to_json(
            execute(nameless_suite(), unnamed_then_lookup(), created_at=CREATED)
        ),
        encoding="utf-8",
    )
    read = run_old(source, READ_RUN, str(document))
    assert read.returncode != 0
    assert f"schema_version {SCHEMA_VERSION} is not supported (expected 12)" in (
        read.stderr
    ), read.stderr


def test_0_14_1_refuses_the_omitted_tool_by_name_at_any_schema(tmp_path: Path) -> None:
    """The inner lock, which holds without the bump: stamped 12, so the version
    does not refuse it first. It ignores `tool_absence` as an unknown key, and
    still cannot build the call — by name, never as a tool named "None"."""
    source = old_source(tmp_path)
    written = json.loads(
        run_to_json(
            execute(nameless_suite(), unnamed_then_lookup(), created_at=CREATED)
        )
    )
    written["schema_version"] = 12
    document = tmp_path / "run.json"
    document.write_text(json.dumps(written), encoding="utf-8")
    read = run_old(source, READ_RUN, str(document))
    assert read.returncode != 0
    assert "missing the mandatory field 'tool'" in read.stderr, read.stderr


def test_this_reader_reads_what_0_14_1_wrote(tmp_path: Path) -> None:
    """The other direction: a schema-12 run with a named trajectory, written by
    0.14.1 itself, migrates and reads here unchanged."""
    source = old_source(tmp_path)
    write = (
        "import sys; from digline.core import *; from digline.run import *; "
        "t = lambda case: Response(output='ok', metadata={'tools': ['lookup'], "
        "'tool_calls': [{'tool': 'lookup', 'arguments': {'id': 1}}]}); "
        "s = Suite(tenant='acme', environment='staging', name='qa', "
        "assertions=[ToolsCalled(expected=['lookup'])], cases=[Case(id='one')], "
        "record_responses=True); "
        "open(sys.argv[1], 'w', encoding='utf-8').write("
        "run_to_json(execute(s, t, created_at='2026-01-01T00:00:00+00:00')))"
    )
    document = tmp_path / "old-run.json"
    written = run_old(source, write, str(document))
    assert written.returncode == 0, written.stderr
    old = json.loads(document.read_text(encoding="utf-8"))
    assert old["schema_version"] == 12
    upgraded = upgrade_document(old)
    assert {k: v for k, v in upgraded.items() if k != "schema_version"} == {
        k: v for k, v in old.items() if k != "schema_version"
    }
    run = run_from_json(json.dumps(upgraded))
    calls = run.results[0].responses[0].tool_calls
    assert calls is not None
    (call,) = calls
    assert call.tool == "lookup"
    assert [v.status for v in run.results[0].verdicts] == ["pass"]


class Dying:
    """Reports a call nobody named, and is killed at the chosen call."""

    def __init__(self, die_at: int) -> None:
        self.calls = 0
        self.die_at = die_at
        self.config = {"provider": "fake", "model": "m-1"}

    def __call__(self, case: Case) -> Response:
        self.calls += 1
        if self.calls == self.die_at:
            raise SystemExit(9)
        return unnamed_then_lookup()(case)


def test_0_14_1_refuses_a_journal_leg_carrying_one_by_name(tmp_path: Path) -> None:
    """The journals' only protection, for every journal that has only it.

    **Rewritten 2026-09-18.** This test used to open by saying `JOURNAL_VERSION`
    does not move with `SCHEMA_VERSION`, so a journal of ours meets no version
    refusal. That is still true of the *constant* — the two are independent by
    design — but it is no longer true of this file: ADR 0025 §11 moved the
    journal to format 2 for its bill line, so a current leg is refused on its
    format before a call is read.

    What that does **not** do is retire the inner refusal, and this is the test
    that says so. Every journal written at format 1 — every 0.15.x journal in
    existence, and they hold nameless calls — still meets no outer lock, so the
    omitted `tool` refused by name is all that stands between an older digline
    and resuming a call as a tool named "None". The leg here is stamped back to
    format 1 to be exactly that file. Asserted as the sentence, not as a
    non-empty refusal.
    """
    source = old_source(tmp_path)
    declared = nameless_suite(cases=[Case(id="one"), Case(id="two")])
    target = Dying(die_at=2)
    store = FileResultStore(tmp_path)
    prepared = prepare(
        declared, target, now=CREATED, git_commit="deadbeef", artifacts={}
    )
    with pytest.raises(SystemExit):
        measure(declared, target, store=store, prepared=prepared)  # pyright: ignore[reportArgumentType]
    key = journal_key(prepared.header)
    (here,) = store.pending("acme", "qa")
    assert here.key == key and not here.refusal, here.refusal
    stamp_journal_format(tmp_path, "acme", "qa", key, 1)

    read = run_old(
        source,
        "import sys; from digline.store import FileResultStore; "
        "(p,) = FileResultStore(sys.argv[1]).pending('acme', 'qa'); "
        "print('REFUSAL:', p.refusal)",
        str(tmp_path),
    )
    assert read.returncode == 0, read.stderr
    assert "missing the mandatory field 'tool'" in read.stdout, read.stdout
