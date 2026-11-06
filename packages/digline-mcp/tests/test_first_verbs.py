"""The five tools of the first verbs: facts, never a recorded word; the
command line's reading; no model, and nothing written. (ADR 0011 §1, as
noted 2026-11-06)

Every store here is written by the writers digline uses, through the helpers
of `tests/test_where.py`, so what a tool reads is what the product files.

- **No recorded word.** A marker in an input, an answer, a step's arguments,
  a setup's value, a case's vars and a call site reaches no answer of the five,
  in clear or under `project`.
- **No digest of an answer or an input.** The command line's `record compare
  --json` carries them, and is the control; the tools carry none.
- **The command line's reading.** `where` is `digline where --json` in each of
  the eleven states and without a suite; `record_listing` is `digline record
  import --json`; `record_status` is `digline record status --json`; and
  `record_compare` is `digline record compare --json` with the two declared
  differences.
- **No model, and nothing written.** Loading a provider plugin raises here,
  and the repository's files are byte for byte what they were after all five.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import anyio
import pytest
from _names import RecordingTable
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import CallToolResult
from tests._helpers import cli
from tests.test_where import (
    EARLY,
    HOURS_ID,
    REFUND_ID,
    SETUP_1,
    SETUP_2,
    TENANT,
    asked,
    elect,
    record,
    run,
    write_suite,
)

from digline.core.capture import capture_id
from digline.core.recording import Recording, setup_digest_of
from digline.core.run import RecordedResponse, RecordedStep, RecordedToolCall
from digline.host.importing import answer_id
from digline.host.recording import switch_off, switch_on
from digline.recorder import UNASSIGNED
from digline.store.file_store import FileResultStore, RecordingWriter
from digline_mcp.server import build_server

SUITE = "suites/suite.py"

#: Text only a recording holds.
MARKERS = {
    "input": "MARK-INPUT-7f1",
    "answer": "MARK-ANSWER-7f1",
    "arguments": "MARK-ARGUMENTS-7f1",
    "setup": "MARK-SETUP-7f1",
    "vars": "MARK-VARS-7f1",
    "call_site": "MARK-CALL-SITE-7f1",
}


def server_call(
    root: Path, tool: str, *, table: RecordingTable | None = None, **arguments: Any
) -> dict[str, Any]:
    async def go() -> dict[str, Any]:
        server = build_server(
            str(root),
            None,
            None,
            names="clear" if table is None else "project",
            table=table,
        )
        result = await server.call_tool(tool, arguments)
        assert isinstance(result, CallToolResult)
        assert result.structured_content is not None
        return dict(result.structured_content)

    return anyio.run(go)


def server_refusal(root: Path, tool: str, **arguments: Any) -> str:
    async def go() -> str:
        server = build_server(str(root), None, None, names="clear", table=None)
        with pytest.raises(ToolError) as caught:
            await server.call_tool(tool, arguments)
        return str(caught.value)

    return anyio.run(go)


def cli_json(root: Path, *args: str) -> dict[str, Any]:
    done = cli(root, *args)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def marked(root: Path) -> None:
    """Recordings that carry a marker in every place a recording holds text:
    a single call under each of two setups, and an episode whose step called
    a tool with marked arguments."""
    writer = RecordingWriter(FileResultStore(root))
    for number, setup in enumerate(
        ({**SETUP_1, "system": MARKERS["setup"]}, SETUP_2), start=1
    ):
        writer.write(
            Recording(
                source_tenant=TENANT,
                app="support",
                suite="triage",
                case={"question": f"{MARKERS['vars']} {number}"},
                setup=setup,
                setup_digest=setup_digest_of(setup),
                response=RecordedResponse(
                    output=MARKERS["answer"],
                    kind="text",
                    input=MARKERS["input"],
                ),
                call_site=MARKERS["call_site"],
                recorded_at=f"2026-11-03T08:0{number}:00+00:00",
            )
        )
    own = "a" * 32
    writer.write(
        Recording(
            source_tenant=TENANT,
            app="support",
            suite="triage",
            case={"question": MARKERS["vars"]},
            setup={"child_setups": ["c" * 16]},
            setup_digest="d" * 16,
            response=RecordedResponse(
                output=f"{MARKERS['answer']} episode",
                kind="text",
                input=MARKERS["input"],
                steps=(
                    RecordedStep(index=0, actor="model", finish="tool_use"),
                    RecordedStep(
                        index=1,
                        actor="tool",
                        call=RecordedToolCall(
                            tool="lookup", arguments=MARKERS["arguments"]
                        ),
                    ),
                    RecordedStep(index=2, actor="model", finish="end_turn"),
                ),
            ),
            id=own,
            recorded_at="2026-11-03T08:03:00+00:00",
        )
    )


#: Each tool, called once, as an agent would over the marked store.
CALLS: dict[str, dict[str, Any]] = {
    "where": {"tenant": TENANT, "suite": SUITE},
    "record_status": {"tenant": TENANT},
    "record_listing": {"suite": SUITE},
    "record_compare": {"suite": SUITE},
    "suggest": {"suite": SUITE},
}


@pytest.fixture
def root(tmp_path: Path) -> Path:
    write_suite(tmp_path)
    marked(tmp_path)
    return tmp_path


@pytest.mark.parametrize("names", ["clear", "project"])
def test_no_recorded_word_reaches_any_answer(root: Path, names: str) -> None:
    table = RecordingTable() if names == "project" else None
    for tool, arguments in CALLS.items():
        said = json.dumps(server_call(root, tool, table=table, **arguments))
        for where_, marker in MARKERS.items():
            assert marker not in said, f"{tool} lets the {where_} out"


def test_the_markers_are_in_the_store_this_reads(root: Path) -> None:
    """The control: the markers are where the tools read, so their absence
    above is the tools' and not the fixture's."""
    held = "".join(
        p.read_text(encoding="utf-8")
        for p in (root / ".digline").rglob("*.json")
        if p.is_file()
    )
    assert all(marker in held for marker in MARKERS.values())


def test_a_refusal_quotes_no_recorded_word(root: Path) -> None:
    write_suite(root, capture=False)
    said = server_refusal(root, "record_listing", suite=SUITE)
    assert "capture" in said
    assert not any(marker in said for marker in MARKERS.values())


def test_no_digest_of_an_answer_or_an_input_leaves(root: Path) -> None:
    digests = {hashlib.sha256(MARKERS["answer"].encode()).hexdigest()[:8]}
    inputs = {capture_id({"question": f"{MARKERS['vars']} {n}"}) for n in (1, 2)}
    # The control: the command line carries them, to the person who ran it.
    printed = json.dumps(
        cli_json(
            root, "record", "compare", "--tenant", TENANT, "--suite", SUITE, "--json"
        )
    )
    assert all(d in printed for d in digests)
    assert all(i in printed for i in inputs)
    for tool, arguments in CALLS.items():
        said = json.dumps(server_call(root, tool, **arguments))
        assert not any(d in said for d in digests), tool
        assert not any(i in said for i in inputs), tool
        assert "cap-" not in said, tool


def test_an_answer_and_a_case_are_numbered_in_the_answer(root: Path) -> None:
    found = server_call(root, "record_compare", suite=SUITE)
    ids = [case["id"] for case in found["cases"]]
    assert ids == [f"case {n}" for n in range(1, len(ids) + 1)]
    answers = [
        answer["answer"]
        for case in found["cases"]
        for setup in case["setups"]
        for answer in setup["answers"]
    ]
    # The two single calls gave the same text under two setups: one number.
    assert answers.count("answer 1") == 2
    assert all("digest" not in str(answer) for answer in answers)


def test_record_compare_is_the_command_line_s_but_for_the_numbers(root: Path) -> None:
    printed = cli_json(
        root, "record", "compare", "--tenant", TENANT, "--suite", SUITE, "--json"
    )
    found = server_call(root, "record_compare", suite=SUITE)
    numbered: dict[str, str] = {}
    for number, case in enumerate(printed["cases"], start=1):
        case["id"] = f"case {number}"
        for setup in case["setups"]:
            for answer in setup["answers"]:
                digest = answer.pop("digest")
                numbered.setdefault(digest, f"answer {len(numbered) + 1}")
                answer["answer"] = numbered[digest]
    assert found == printed


def test_the_episode_s_shape_crosses_with_its_calls(root: Path) -> None:
    found = server_call(root, "record_compare", suite=SUITE)
    shapes = [
        (setup["calls"], setup["models"])
        for case in found["cases"]
        for setup in case["setups"]
        if setup["setup"] == "d" * 8
    ]
    assert shapes and all(isinstance(calls, list) for calls, _ in shapes)


def test_record_listing_is_the_command_line_s(root: Path) -> None:
    printed = cli_json(
        root, "record", "import", "--tenant", TENANT, "--suite", SUITE, "--json"
    )
    assert server_call(root, "record_listing", suite=SUITE) == printed


def test_the_listing_says_where_a_person_gives_a_yes(root: Path) -> None:
    review = server_call(root, "record_listing", suite=SUITE)["review"]
    assert review["sentence"].startswith("to review an answer, open digline view")
    assert "default port, 7373" in review["sentence"]
    assert review["command"] == f"digline view --suite {SUITE}"
    assert review["address"] == "http://127.0.0.1:7373/recordings/acme/triage/"


def test_record_status_is_the_command_line_s_with_its_paths_relative(
    root: Path,
) -> None:
    switch_on(root, TENANT, production=False)
    printed = cli_json(root, "record", "status", "--tenant", TENANT, "--json")
    # The one difference this surface declares: the paths, relative to the
    # repository's root, which the command line prints whole.
    for each in printed["tenants"]:
        for part in ("switch", "recordings"):
            whole = Path(each[part]["path"])
            each[part]["path"] = str(whole.relative_to(root.resolve()))
        for refusal in ("refusal", "production_refusal"):
            said = each["switch"][refusal]
            if said is not None:
                each["switch"][refusal] = said.replace(f"{root.resolve()}/", "")
    found = server_call(root, "record_status", tenant=TENANT)
    assert found == printed
    [tenant] = found["tenants"]
    assert not Path(tenant["switch"]["path"]).is_absolute()
    assert not Path(tenant["recordings"]["path"]).is_absolute()
    assert str(root) not in json.dumps(found)


# Where, in each of the eleven states and without a suite.


def _recording_off(root: Path) -> None:
    record(root, *EARLY)
    elect(root, good=[REFUND_ID])
    switch_off(root, TENANT)


def _no_suite_yet(root: Path) -> None:
    write_suite(root, capture=False)
    record(root, *EARLY)


def _nothing_recorded(root: Path) -> None:
    """The store as `write_suite` leaves it: no recording and no run."""


def _unassigned(root: Path) -> None:
    record(root, *EARLY, suite=UNASSIGNED)


def _to_import(root: Path) -> None:
    record(root, *EARLY)


def _never_run(root: Path) -> None:
    record(root, *EARLY)
    elect(root, good=[REFUND_ID], bad=[HOURS_ID])


def _judge_disagrees(root: Path) -> None:
    record(root, *EARLY)
    elect(root, good=[REFUND_ID], bad=[HOURS_ID])
    run(root)


def _green_without_red(root: Path) -> None:
    record(root, *EARLY)
    elect(root, good=[REFUND_ID])
    run(root)


def _new_setup(root: Path) -> None:
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


def _nothing_to_do(root: Path) -> None:
    write_suite(root, scores={"nine to five": 0.0})
    record(root, *EARLY)
    elect(root, good=[REFUND_ID], bad=[HOURS_ID])
    run(root)


def _last_run_red(root: Path) -> None:
    write_suite(root, scores={"nine to five": 0.0, "fine": None})
    record(root, *EARLY)
    elect(root, good=[REFUND_ID], bad=[HOURS_ID])
    run(root, exits=2)


#: Each state, and the store that puts the project in it, as
#: `tests/test_where.py` writes it.
STATES: dict[str, Callable[[Path], None]] = {
    "nothing_recorded": _nothing_recorded,
    "recording_off": _recording_off,
    "unassigned": _unassigned,
    "no_suite_yet": _no_suite_yet,
    "to_import": _to_import,
    "never_run": _never_run,
    "judge_disagrees": _judge_disagrees,
    "green_without_red": _green_without_red,
    "new_setup": _new_setup,
    "nothing_to_do": _nothing_to_do,
    "last_run_red": _last_run_red,
}


@pytest.mark.parametrize("state", list(STATES))
def test_where_over_this_server_is_where_on_the_command_line(
    tmp_path: Path, state: str
) -> None:
    write_suite(tmp_path)
    STATES[state](tmp_path)
    printed = cli_json(
        tmp_path, "where", "--tenant", TENANT, "--suite", SUITE, "--json"
    )
    found = server_call(tmp_path, "where", tenant=TENANT, suite=SUITE)
    assert found["state"] == state
    assert found == printed


def test_where_without_a_suite_is_the_command_line_s(tmp_path: Path) -> None:
    write_suite(tmp_path)
    record(tmp_path, *EARLY)
    printed = cli_json(tmp_path, "where", "--tenant", TENANT, "--json")
    found = server_call(tmp_path, "where", tenant=TENANT)
    assert found["state"] == "no_suite_yet"
    assert found == printed


def test_where_refuses_a_tenant_the_suite_does_not_declare(root: Path) -> None:
    said = server_refusal(root, "where", tenant="other", suite=SUITE)
    assert "does not match the suite" in said


# No model, and nothing written.


def _files(root: Path) -> dict[str, bytes]:
    return {
        str(p.relative_to(root)): p.read_bytes()
        for p in sorted(root.rglob("*"))
        if p.is_file() and "__pycache__" not in p.parts
    }


def test_no_tool_loads_a_provider_and_none_writes(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def loaded(*_: object) -> object:
        raise AssertionError("a provider plugin was loaded")

    monkeypatch.setattr("importlib.metadata.EntryPoint.load", loaded)
    monkeypatch.setattr("digline.targets.registry.resolve", loaded)
    before = _files(root)
    for tool, arguments in CALLS.items():
        server_call(root, tool, **arguments)
    server_call(root, "suggest", name="newsuite", tenant=TENANT, repository="private")
    assert _files(root) == before


def test_suggest_says_the_command_that_writes_and_the_one_that_asks(
    root: Path,
) -> None:
    found = server_call(root, "suggest", suite=SUITE)
    assert found["written"] is False
    assert found["proposal"] == "suites/suite.proposed.toml"
    assert found["command"] == f"digline suggest --suite {SUITE}"
    assistant = found["assistant"]
    assert assistant["asked"] is False
    assert "a tool has no before" in assistant["sentence"]
    assert assistant["command"] == (
        f"digline suggest --suite {SUITE} --model provider/model"
    )
    # The command it says writes the proposal those facts describe.
    done = cli(root, *found["command"].split()[1:])
    assert done.returncode == 0, done.stderr
    written = (root / found["proposal"]).read_text(encoding="utf-8")
    assert written.count("[[assertions]]") == len(found["checks"])


def test_suggest_for_a_suite_that_does_not_exist_yet(root: Path) -> None:
    found = server_call(
        root, "suggest", name="newsuite", tenant=TENANT, repository="private"
    )
    assert found["form"] is None
    assert found["nothing"] is True
    assert found["command"] == (
        "digline suggest --suite newsuite --tenant acme --repository private"
    )


@pytest.mark.parametrize(
    "arguments",
    [{}, {"suite": SUITE, "name": "x"}, {"suite": SUITE, "tenant": TENANT}],
    ids=["neither", "both", "a tenant beside a suite"],
)
def test_suggest_takes_a_suite_or_a_name(root: Path, arguments: dict[str, Any]) -> None:
    said = server_refusal(root, "suggest", **arguments)
    assert "suite" in said


def test_under_project_the_plugins_installed_are_withheld(root: Path) -> None:
    """A suite that does not exist yet has its judge as a placeholder, and the
    answer names the plugins installed beside it: in clear, the control, and
    under `project` none, since no kind holds a plugin's name."""
    arguments: dict[str, Any] = {
        "name": "triage",
        "tenant": TENANT,
        "repository": "private",
    }
    clear = server_call(root, "suggest", **arguments)
    assert clear["judge"]["declared"] is False
    assert clear["judge"]["plugins"]
    projected = server_call(root, "suggest", table=RecordingTable(), **arguments)
    assert projected["judge"]["plugins"] == []
    assert projected["judge"]["check"] != "llm_rubric"
