"""`steps` on a recorded response: schema 23's third passenger. (ADR 0060 §5)

What is held here:

- the steps a target reports are recorded under `record_responses`, written
  by the run document's serializer, a tool step's call inline, and read back
  to the same value;
- absent is *not recorded*, never `[]`;
- the reader that records them is strict, as `record_trajectory` is, and
  refuses steps whose calls are not the response's `tool_calls`;
- whole or nothing with the text: an oversize answer keeps no steps, a
  withheld one may carry none;
- a document read back refuses a malformed step by name.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

import pytest

from digline.core import (
    MAX_RECORDED_CHARS,
    Contains,
    RecordedResponse,
    RecordedToolCall,
    RefusedError,
    run_from_json,
    run_to_json,
)
from digline.core.run import (
    RecordedStep,
    record_steps,
    recorded_response_from_dict,
    recorded_response_to_dict,
    steps_as_reported,
)
from digline.run import Case, Response, Suite, execute
from digline.run.driver import recorded

CREATED = "2026-11-04T00:00:00.000000Z"

LOOKUP: dict[str, object] = {"tool": "lookup", "arguments": {"order": 42}}
REFUND: dict[str, object] = {"tool": "refund", "arguments": {"amount": 10}}


def reported(*turns: tuple[str | None, list[Any]]) -> dict[str, object]:
    calls = [call for _, made in turns for call in made]
    return {
        "tools": [call["tool"] for call in calls],
        "tool_calls": calls,
        "steps": steps_as_reported(list(turns)),
    }


TWO_TURNS = reported(("tool_use", [LOOKUP]), ("tool_use", [REFUND]))


def test_the_steps_a_target_reports_are_recorded_in_order() -> None:
    answer = recorded(Response(output="ok", metadata=TWO_TURNS))
    assert answer.steps is not None
    assert [(s.index, s.actor, s.finish) for s in answer.steps] == [
        (0, "model", "tool_use"),
        (1, "tool", None),
        (2, "model", "tool_use"),
        (3, "tool", None),
    ]
    assert [s.call.tool for s in answer.steps if s.call is not None] == [
        "lookup",
        "refund",
    ]


def test_steps_are_written_inline_and_read_back_to_the_same_value() -> None:
    answer = recorded(Response(output="ok", metadata=TWO_TURNS))
    written = recorded_response_to_dict(answer)
    assert written["steps"] == [
        {"index": 0, "actor": "model", "finish": "tool_use"},
        {"index": 1, "actor": "tool", "tool": "lookup", "arguments": '{"order":42}'},
        {"index": 2, "actor": "model", "finish": "tool_use"},
        {"index": 3, "actor": "tool", "tool": "refund", "arguments": '{"amount":10}'},
    ]
    back = recorded_response_from_dict(json.loads(json.dumps(written)))
    assert back == answer


def test_a_response_with_no_steps_records_none_never_an_empty_list() -> None:
    answer = recorded(Response(output="ok", metadata={"tools": [], "tool_calls": []}))
    assert answer.steps is None
    assert "steps" not in recorded_response_to_dict(answer)


def test_a_run_document_round_trips_its_steps() -> None:
    suite = Suite(
        tenant="acme",
        environment="test",
        name="agent",
        assertions=[Contains(needle="ok")],
        cases=[Case(id="refund")],
        record_responses=True,
    )

    def target(case: Case) -> Response:
        return Response(output="ok", metadata=TWO_TURNS)

    run = execute(suite, target, created_at=CREATED)
    back = run_from_json(run_to_json(run))
    [answer] = back.results[0].responses
    assert answer.steps is not None
    assert len(answer.steps) == 4
    assert back == run


# -- strict, as record_trajectory is ---------------------------------------------- #


MALFORMED: list[tuple[object, str]] = [
    ("lookup", "not a sequence of steps"),
    (["lookup"], "not a mapping"),
    ([{"index": 1, "actor": "model"}], "indexed from 0"),
    ([{"index": True, "actor": "model"}], "indexed from 0"),
    ([{"index": 0, "actor": "engine"}], "'model' or 'tool'"),
    ([{"index": 0, "actor": "model", "tool": "x"}], "only its 'finish'"),
    ([{"index": 0, "actor": "model", "finish": 3}], "only its 'finish'"),
    ([{"index": 0, "actor": "tool", "arguments": {}}], "no 'tool' in it"),
    ([{"index": 0, "actor": "model", "finish": ""}], "non-empty"),
]


@pytest.mark.parametrize(
    ("steps", "said"),
    MALFORMED,
    ids=[
        "text",
        "not-a-mapping",
        "index-out-of-order",
        "index-bool",
        "actor",
        "model-with-a-call",
        "model-finish-not-text",
        "tool-without-a-tool",
        "empty-finish",
    ],
)
def test_record_steps_refuses_a_malformed_step(steps: object, said: str) -> None:
    with pytest.raises(RefusedError, match=said):
        record_steps({"steps": steps})


def test_steps_that_name_other_calls_than_tool_calls_are_refused() -> None:
    disagreeing = {**TWO_TURNS, "tool_calls": [REFUND, LOOKUP]}
    with pytest.raises(RefusedError, match="not its `tool_calls`"):
        recorded(Response(output="ok", metadata=disagreeing))


def test_steps_alone_are_recorded_without_tool_calls() -> None:
    alone: Mapping[str, object] = {"steps": TWO_TURNS["steps"]}
    answer = recorded(Response(output="ok", metadata=alone))
    assert answer.steps is not None
    assert answer.tool_calls is None


# -- whole or nothing ---------------------------------------------------------------- #


def test_an_oversize_answer_keeps_no_steps() -> None:
    big: dict[str, object] = {
        "tool": "lookup",
        "arguments": {"q": "x" * MAX_RECORDED_CHARS},
    }
    answer = recorded(Response(output="ok", metadata=reported(("tool_use", [big]))))
    assert answer.oversize
    assert answer.steps is None


def test_the_ceiling_counts_the_trajectory_once() -> None:
    """Steps and calls carry the same calls: counted twice, an answer just
    over half the ceiling would be refused as oversize."""
    half: dict[str, object] = {
        "tool": "lookup",
        "arguments": "x" * (MAX_RECORDED_CHARS // 2 + 10),
    }
    answer = recorded(Response(output="ok", metadata=reported(("tool_use", [half]))))
    assert not answer.oversize
    assert answer.steps is not None


@pytest.mark.parametrize("flag", ["withheld", "oversize"])
def test_a_response_that_keeps_no_text_carries_no_steps(flag: str) -> None:
    step = RecordedStep(index=0, actor="model")
    with pytest.raises(ValueError, match=flag):
        RecordedResponse(**{flag: True}, steps=(step,))  # pyright: ignore[reportArgumentType]


# -- a document read back ------------------------------------------------------ #


def document(steps: object) -> dict[str, Any]:
    return {"output": "ok", "kind": "text", "steps": steps}


@pytest.mark.parametrize(
    ("steps", "said"),
    [
        (None, "not a list of steps"),
        ([{"index": 1, "actor": "model"}], "in order from 0"),
        ([{"index": 0, "actor": "model", "tool": "x"}], "carries a tool call's keys"),
        ([{"index": 0, "actor": "tool"}], "tool"),
    ],
    ids=["null", "out-of-order", "model-with-call-keys", "tool-without-a-tool"],
)
def test_a_document_refuses_a_malformed_step(steps: object, said: str) -> None:
    with pytest.raises(ValueError, match=said):
        recorded_response_from_dict(document(steps))


def test_a_document_reads_a_tool_steps_call_as_tool_calls_does() -> None:
    back = recorded_response_from_dict(
        document([{"index": 0, "actor": "tool", "tool": "lookup", "status": "error"}])
    )
    assert back.steps == (
        RecordedStep(
            index=0,
            actor="tool",
            call=RecordedToolCall(tool="lookup", status="error"),
        ),
    )
