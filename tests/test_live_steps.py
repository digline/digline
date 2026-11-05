"""The steps of a trajectory, live, and the collection of a run's target.
(ADR 0060 §1, §2, §3)

The fakes are the real `anthropic.Anthropic` over an `httpx2.MockTransport`,
answering a sequence of replies, so the steps come out of the plugin's own
`completion_of`, as they do in a run.

What is held here:

- `steps_of` makes one model step per call, then a tool step per tool call,
  indexed across the trajectory; `steps_as_reported` lays the live calls on
  them, and is absent where a call's tools were not reported;
- `Completion.as_metadata()` writes `steps` beside `tools` and `tool_calls`;
- a function target that makes three calls through a wrapped client has the
  three calls' steps, its usage summed and its cost not known; unwrapped, it
  has what it reports, as before;
- an `episode()` opened with the recorder off delivers to the collection;
- a provider target whose client is wrapped is not counted twice, and the
  host prices each collected call at the model it reports;
- a stream the target returns before its end leaves no steps;
- a call made after the collection closed reaches nothing.
"""

from __future__ import annotations

import asyncio
import importlib
import json
import sys
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any, cast

import pytest

from digline import recorder
from digline.core import Contains, RefusedError
from digline.core.run import RecordedStep, RecordedToolCall, steps_as_reported, steps_of
from digline.host.measure import around_target
from digline.recorder import collecting, episode, wrap
from digline.run import Case, Response, Suite, default_mapper, execute
from digline.targets import Completion, ToolCall, Usage

SDKS = ("anthropic", "httpx2", "digline_anthropic")


@pytest.fixture(autouse=True, scope="module")
def the_sdks_leave_with_this_module() -> Iterator[None]:
    before = set(sys.modules)
    yield
    for name in set(sys.modules) - before:
        if name.split(".", 1)[0] in SDKS:
            del sys.modules[name]


@pytest.fixture(autouse=True)
def off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(recorder.ENVIRONMENT_VARIABLE, raising=False)


def sdk(name: str) -> Any:
    return importlib.import_module(name)


QUESTION = [{"role": "user", "content": "Refund order 42"}]


def tool_use(ident: str, name: str, arguments: dict[str, object]) -> dict[str, object]:
    return {"type": "tool_use", "id": ident, "name": name, "input": arguments}


def reply(
    content: list[dict[str, object]], *, model: str = "claude-test", output: int = 5
) -> dict[str, object]:
    return {
        "id": "msg_1",
        "type": "message",
        "role": "assistant",
        "model": model,
        "content": content,
        "stop_reason": "tool_use",
        "stop_sequence": None,
        "usage": {"input_tokens": 10, "output_tokens": output},
    }


#: Three calls an agent makes: one tool, then two in one reply, then one with
#: some text before it.
AGENT = [
    reply([tool_use("t1", "lookup_order", {"order": 42})], output=1),
    reply(
        [
            tool_use("t2", "check_refund_policy", {}),
            tool_use("t3", "lookup_customer", {"id": "c7"}),
        ],
        output=2,
    ),
    reply(
        [
            {"type": "text", "text": "Refunding."},
            tool_use("t4", "issue_refund", {"amount": 10}),
        ],
        output=3,
    ),
]
AGENT_TOOLS = ["lookup_order", "check_refund_policy", "lookup_customer", "issue_refund"]


def sse(events: list[tuple[str, object]]) -> bytes:
    lines: list[str] = []
    for name, data in events:
        lines += [f"event: {name}", f"data: {json.dumps(data)}", ""]
    return ("\n".join(lines) + "\n").encode("utf-8")


def streamed_text() -> bytes:
    start = {**reply([]), "stop_reason": None}
    return sse(
        [
            ("message_start", {"type": "message_start", "message": start}),
            (
                "content_block_start",
                {
                    "type": "content_block_start",
                    "index": 0,
                    "content_block": {"type": "text", "text": ""},
                },
            ),
            (
                "content_block_delta",
                {
                    "type": "content_block_delta",
                    "index": 0,
                    "delta": {"type": "text_delta", "text": "Done"},
                },
            ),
            ("content_block_stop", {"type": "content_block_stop", "index": 0}),
            (
                "message_delta",
                {
                    "type": "message_delta",
                    "delta": {"stop_reason": "end_turn", "stop_sequence": None},
                    "usage": {"output_tokens": 1},
                },
            ),
            ("message_stop", {"type": "message_stop"}),
        ]
    )


def anthropic(replies: list[dict[str, object]], *, asynchronous: bool = False) -> Any:
    """A real client answering `replies` in turn, and a text stream when a
    call asks for one."""
    httpx2 = sdk("httpx2")
    served = iter(replies * 10)

    def handle(request: Any) -> Any:
        if json.loads(request.content).get("stream"):
            return httpx2.Response(
                200,
                headers={"content-type": "text/event-stream"},
                content=streamed_text(),
            )
        return httpx2.Response(200, json=next(served))

    if asynchronous:
        return sdk("anthropic").AsyncAnthropic(
            api_key="test",
            http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handle)),
            max_retries=0,
        )
    return sdk("anthropic").Anthropic(
        api_key="test",
        http_client=httpx2.Client(transport=httpx2.MockTransport(handle)),
        max_retries=0,
    )


def ask(client: Any, **extra: Any) -> Any:
    return client.messages.create(
        model="claude-test", max_tokens=10, messages=QUESTION, **extra
    )


def agent(client: Any) -> Any:
    """A function target that makes three calls and answers with its text."""

    def target(case: Case) -> Response:
        for _ in range(3):
            ask(client)
        return Response(output="refunded")

    return target


def settled(target: Any, **collect: Any) -> Response:
    with collecting(**collect) as settle:
        return settle(target(Case(id="c", vars={})))


def steps_in(metadata: Mapping[str, object]) -> list[dict[str, Any]]:
    found = metadata["steps"]
    assert isinstance(found, list)
    return cast(list[dict[str, Any]], found)


def tools_of(metadata: Mapping[str, object]) -> list[object]:
    return [step["tool"] for step in steps_in(metadata) if step["actor"] == "tool"]


def collected(response: Response) -> dict[str, Any]:
    found = response.metadata["collected"]
    assert isinstance(found, dict)
    return cast(dict[str, Any], found)


# -- steps_of and steps_as_reported -------------------------------------------- #


def test_steps_of_makes_a_model_step_then_its_tool_steps_indexed_across() -> None:
    first = RecordedToolCall(tool="a")
    second = RecordedToolCall(tool="b")
    steps = steps_of([("tool_use", [first, second]), ("stop", [])])
    assert steps == (
        RecordedStep(index=0, actor="model", finish="tool_use"),
        RecordedStep(index=1, actor="tool", call=first),
        RecordedStep(index=2, actor="tool", call=second),
        RecordedStep(index=3, actor="model", finish="stop"),
    )


def test_steps_of_a_call_whose_tools_nobody_reported_is_its_model_step() -> None:
    assert steps_of([(None, None)]) == (RecordedStep(index=0, actor="model"),)


def test_steps_as_reported_carry_each_call_in_its_live_form() -> None:
    call = {
        "tool": "lookup",
        "arguments": {"order": 42},
        "result": None,
        "status": "not_reported",
        "result_absence": "not_reported",
    }
    assert steps_as_reported([("tool_use", [call]), (None, [])]) == [
        {"index": 0, "actor": "model", "finish": "tool_use"},
        {"index": 1, "actor": "tool", **call},
        {"index": 2, "actor": "model"},
    ]


def test_steps_as_reported_are_absent_where_one_call_said_nothing_of_tools() -> None:
    assert steps_as_reported([("tool_use", [{"tool": "a"}]), ("stop", None)]) is None


def test_steps_as_reported_refuse_a_call_with_no_tool_in_it() -> None:
    with pytest.raises(RefusedError, match="no 'tool' in it"):
        steps_as_reported([("tool_use", [{"arguments": {}}])])


# -- as_metadata ------------------------------------------------------------------ #


def test_a_completion_writes_its_steps_beside_tools_and_tool_calls() -> None:
    calls = (
        ToolCall("a", {"x": 1}, status="not_reported"),
        ToolCall("b", None, status="not_reported"),
    )
    found = Completion(
        "", Usage(1, 1), finish="tool_use", tools=("a", "b"), tool_calls=calls
    ).as_metadata()
    assert found["tools"] == ["a", "b"]
    assert found["tool_calls"] == [call.as_reported() for call in calls]
    assert found["steps"] == [
        {"index": 0, "actor": "model", "finish": "tool_use"},
        {"index": 1, "actor": "tool", **calls[0].as_reported()},
        {"index": 2, "actor": "tool", **calls[1].as_reported()},
    ]


def test_a_completion_that_reported_no_tool_calls_writes_no_steps() -> None:
    assert "steps" not in Completion("hi", Usage(1, 1), finish="stop").as_metadata()


# -- the collection ---------------------------------------------------------------- #


def test_a_function_target_through_a_wrapped_client_has_every_calls_steps(
    tmp_path: Path,
) -> None:
    client = wrap(anthropic(AGENT), app="support", tenant="acme", root=tmp_path)
    response = settled(agent(client))
    steps = steps_in(response.metadata)
    assert [step["actor"] for step in steps] == [
        "model",
        "tool",
        "model",
        "tool",
        "tool",
        "model",
        "tool",
    ]
    assert [step["index"] for step in steps] == list(range(7))
    assert tools_of(response.metadata) == AGENT_TOOLS
    assert response.metadata["tools"] == AGENT_TOOLS
    assert response.metadata["finish"] == "tool_use"
    assert response.usage == Usage(input_tokens=30, output_tokens=6)
    assert response.cost_usd is None
    assert response.unpriced is not None
    assert "no price list declared by the target" in response.unpriced
    assert response.latency_ms is not None
    assert response.metadata["collected"] == {
        "calls": 3,
        "latency": "model calls only, tool time excluded",
    }
    # Off: nothing was written.
    assert not (tmp_path / ".digline").exists()


def test_unwrapped_the_same_target_has_only_what_it_reports(tmp_path: Path) -> None:
    response = settled(agent(anthropic(AGENT)))
    assert "steps" not in response.metadata
    assert "collected" not in response.metadata
    assert response.usage is None


def test_unwrapped_a_provider_target_inside_an_agent_reports_its_last_call(
    tmp_path: Path,
) -> None:
    target = anthropic_target(tmp_path, anthropic(AGENT))

    def last(case: Case) -> Response:
        answered = target(case)
        for _ in range(2):
            answered = target(case)
        return answered

    response = settled(last)
    assert tools_of(response.metadata) == ["issue_refund"]


def test_an_episode_opened_off_inside_the_target_delivers_to_the_collection(
    tmp_path: Path,
) -> None:
    client = wrap(anthropic(AGENT), app="support", tenant="acme", root=tmp_path)

    def target(case: Case) -> Response:
        with episode(client, suite="agent", case={"q": "refund"}) as ep:
            assert ep.id is None
            for _ in range(3):
                ask(client)
        return Response(output="refunded")

    assert tools_of(settled(target).metadata) == AGENT_TOOLS


def test_an_asynchronous_client_is_collected(tmp_path: Path) -> None:
    client = wrap(
        anthropic(AGENT, asynchronous=True), app="support", tenant="acme", root=tmp_path
    )

    def target(case: Case) -> Response:
        async def run() -> None:
            for _ in range(3):
                await ask(client)

        asyncio.run(run())
        return Response(output="refunded")

    assert tools_of(settled(target).metadata) == AGENT_TOOLS


def test_a_stream_read_to_its_end_is_collected(tmp_path: Path) -> None:
    client = wrap(anthropic(AGENT), app="support", tenant="acme", root=tmp_path)

    def target(case: Case) -> Response:
        ask(client)
        for _ in ask(client, stream=True):
            pass
        return Response(output="done")

    response = settled(target)
    assert [step["actor"] for step in steps_in(response.metadata)] == [
        "model",
        "tool",
        "model",
    ]
    assert response.metadata["finish"] == "stop"


def test_a_stream_the_target_returns_before_its_end_leaves_no_steps(
    tmp_path: Path,
) -> None:
    client = wrap(anthropic(AGENT), app="support", tenant="acme", root=tmp_path)
    kept: list[Any] = []

    def target(case: Case) -> Response:
        ask(client)
        kept.append(ask(client, stream=True))
        return Response(output="streaming")

    response = settled(target)
    for key in ("steps", "tools", "tool_calls", "finish"):
        assert key not in response.metadata
    assert response.metadata["collected"] == {
        "calls": 2,
        "latency": "model calls only, tool time excluded",
        "unread": 1,
    }
    assert response.usage is None
    assert response.latency_ms is None
    # Read after the collection closed: it reaches nothing, and raises nothing.
    for _ in kept[0]:
        pass


def test_a_call_after_the_collection_closed_reaches_nothing(tmp_path: Path) -> None:
    client = wrap(anthropic(AGENT), app="support", tenant="acme", root=tmp_path)
    with collecting() as settle:
        ask(client)
    ask(client)
    response = settle(Response(output="x"))
    assert collected(response)["calls"] == 1


def test_a_stream_that_ends_after_the_collection_closed_reaches_nothing(
    tmp_path: Path,
) -> None:
    client = wrap(anthropic(AGENT), app="support", tenant="acme", root=tmp_path)
    with collecting() as settle:
        stream = ask(client, stream=True)
    for _ in stream:
        pass
    response = settle(Response(output="x"))
    assert "steps" not in response.metadata
    assert collected(response)["unread"] == 1


def test_an_empty_collection_leaves_the_response_as_it_came() -> None:
    answered = Response(output="x", metadata={"tools": ["a"]}, latency_ms=3.0)

    def target(case: Case) -> Response:
        return answered

    assert settled(target) is answered


# -- a provider target, wrapped, and its price -------------------------------------- #


def anthropic_target(tmp_path: Path, client: Any) -> Any:
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("Refund it.", encoding="utf-8")
    return sdk("digline_anthropic").AnthropicTarget(
        prompt, model="claude-haiku-4-5", max_tokens=64, client=client
    )


def test_a_provider_target_whose_client_is_wrapped_is_counted_once(
    tmp_path: Path,
) -> None:
    replies = [reply([tool_use("t1", "lookup_order", {})], model="claude-haiku-4-5")]
    client = wrap(anthropic(replies), app="support", tenant="acme", root=tmp_path)
    target = anthropic_target(tmp_path, client)
    alone = target(Case(id="c", vars={}))
    with around_target(target)() as settle:
        response = settle(target(Case(id="c", vars={})))
    assert response.usage == alone.usage
    assert response.metadata["input_tokens"] == 10
    assert response.cost_usd == alone.cost_usd
    assert response.cost_usd is not None
    assert response.metadata["steps"] == alone.metadata["steps"]
    assert collected(response)["calls"] == 1


def test_each_collected_call_is_priced_at_the_model_it_reports(
    tmp_path: Path,
) -> None:
    replies = [
        reply([tool_use("t1", "lookup_order", {})], model="claude-haiku-4-5"),
        reply([tool_use("t2", "issue_refund", {})], model="claude-unlisted"),
    ]
    client = wrap(anthropic(replies), app="support", tenant="acme", root=tmp_path)
    target = anthropic_target(tmp_path, client)

    def two(case: Case) -> Response:
        ask(client)
        ask(client)
        return target(case)

    with around_target(target)() as settle:
        response = settle(two(Case(id="c", vars={})))
    assert response.cost_usd is None
    assert response.unpriced is not None
    assert "'claude-unlisted'" in response.unpriced
    assert response.usage is not None


# -- through execute ---------------------------------------------------------------- #


def a_suite() -> Suite:
    return Suite(
        tenant="acme",
        environment="test",
        name="agent",
        assertions=[Contains(needle="refunded")],
        cases=[Case(id="c", vars={})],
    )


def test_execute_reads_the_collection_and_closes_it_before_the_assertions(
    tmp_path: Path,
) -> None:
    client = wrap(anthropic(AGENT), app="support", tenant="acme", root=tmp_path)
    seen: list[Any] = []

    def mapper(response: Response, case: Case) -> Any:
        seen.append(response.metadata)
        # Inside the mapper, after `settle`: a call here is the judge's side.
        ask(client)
        return default_mapper(response, case)

    suite = a_suite()
    run = execute(
        suite,
        agent(client),
        created_at="2026-11-04T00:00:00.000000Z",
        mapper=mapper,
        around_target=collecting,
    )
    assert run.results[0].error_kind is None
    assert [verdict.status for verdict in run.results[0].verdicts] == ["pass"]
    [metadata] = seen
    assert tools_of(metadata) == AGENT_TOOLS
    assert metadata["collected"]["calls"] == 3


def test_execute_without_the_hook_reads_what_the_target_reports(
    tmp_path: Path,
) -> None:
    client = wrap(anthropic(AGENT), app="support", tenant="acme", root=tmp_path)
    seen: list[Any] = []

    def mapper(response: Response, case: Case) -> Any:
        seen.append(response.metadata)
        return default_mapper(response, case)

    suite = a_suite()
    execute(
        suite, agent(client), created_at="2026-11-04T00:00:00.000000Z", mapper=mapper
    )
    assert seen == [{}]


# -- a run's calls are the gate's, not the application's traffic --------------- #


def recordings(root: Path) -> list[Path]:
    return sorted((root / ".digline").rglob("recordings/*/*.json"))


def counts_files(root: Path) -> dict[Path, str]:
    """Each process's `.counts`, as written: what `record status` sums."""
    return {
        path: path.read_text(encoding="utf-8")
        for path in sorted((root / ".digline").rglob("recordings/*/.counts"))
    }


def judged_through(client: Any) -> Any:
    """A judge that asks the same wrapped client, as a function judge may."""
    from digline.core import JudgeReply, LlmRubric

    def judge(prompt: str) -> JudgeReply:
        ask(client)
        return JudgeReply(score=1.0, reason="asked the client")

    return LlmRubric(rubric="ok?", judge=judge, threshold=0.5, tolerance=0.05)


def test_a_run_with_the_recorder_on_writes_no_recording(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Inside `running()`, the target's calls, an episode it opens and a
    judge's calls are collected or made and never written, and the counts do
    not move. The control first: the same client, outside a run, records."""
    monkeypatch.setenv(recorder.ENVIRONMENT_VARIABLE, "1")
    client = wrap(anthropic(AGENT), app="support", tenant="acme", root=tmp_path)
    ask(client, suite="support-step")
    written = recordings(tmp_path)
    assert len(written) == 1
    before = dict(client.digline_counts)
    on_disk = counts_files(tmp_path)
    assert on_disk  # the control's call left its counts on disk

    def target(case: Case) -> Response:
        with episode(client, suite="support-agent", case={"q": "refund"}) as ep:
            assert ep.id is None
            for _ in range(3):
                ask(client, suite="support-step")
        return Response(output="refunded")

    suite = Suite(
        tenant="acme",
        environment="test",
        name="agent",
        assertions=[judged_through(client)],
        cases=[Case(id="c")],
    )
    with recorder.running():
        run = execute(
            suite, target, created_at="2026-11-04T00:00:00Z", around_target=collecting
        )
    assert run.results[0].verdicts[0].status == "pass"
    assert recordings(tmp_path) == written
    assert dict(client.digline_counts) == before
    assert counts_files(tmp_path) == on_disk


def test_collecting_alone_writes_none_of_the_targets_calls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A library caller that passes `collecting` and opens no `running()`:
    the target's calls are still the run's, and are not written."""
    monkeypatch.setenv(recorder.ENVIRONMENT_VARIABLE, "1")
    client = wrap(anthropic(AGENT), app="support", tenant="acme", root=tmp_path)
    response = settled(agent(client))
    assert tools_of(response.metadata) == AGENT_TOOLS
    assert recordings(tmp_path) == []
    assert client.digline_counts["recorded"] == 0


def test_a_measured_run_records_none_of_its_judges_calls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """What `digline run` and the MCP server call: `measure` enters
    `running()` itself, so a judge's calls through a wrapped client, which
    no collection reads, are not written either."""
    from digline.host.measure import measure, prepare
    from digline.store import FileResultStore

    monkeypatch.setenv(recorder.ENVIRONMENT_VARIABLE, "1")
    client = wrap(anthropic(AGENT), app="support", tenant="acme", root=tmp_path)
    suite = Suite(
        tenant="acme",
        environment="test",
        name="agent",
        assertions=[judged_through(client)],
        cases=[Case(id="c")],
    )

    def target(case: Case) -> Response:
        return Response(output="refunded")

    prepared = prepare(
        suite, target, now="2026-11-04T00:00:00Z", git_commit=None, artifacts={}
    )
    measured = measure(
        suite, target, store=FileResultStore(tmp_path), prepared=prepared
    )
    assert measured.run.results[0].verdicts[0].status == "pass"
    assert recordings(tmp_path) == []
    assert client.digline_counts["recorded"] == 0
