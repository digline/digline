"""The recorder on a streamed reply, on the three providers' own SDKs, with no
network. (ADR 0058 §13, the second piece)

The fakes answer as the providers do: Anthropic and OpenAI with server-sent
events from an `httpx2.MockTransport` when the request asks for a stream, and
Bedrock with the bytes of an AWS event stream handed to botocore's own parser
through its `before-send` hook. So what the application iterates is the SDK's
own stream, built by the SDK from those bytes.

What is held here:

- the application gets the stream the SDK built, the same class, with the
  same events, read as it reads them;
- a streamed reply is recorded at its end with the case, the setup digest and
  the text the same request would have had answered whole;
- a stream closed or dropped before its end is not recorded and is counted
  `stream abandoned`; an exception inside it propagates and is counted by its
  class's name;
- OpenAI's usage, which arrives only where the application asks for it, is
  never asked for in its place: without it the reply is recorded with no
  counts and `usage not reported` is noted;
- a streamed child of an episode joins it at the end of its stream, and one
  that ends after its episode closed is an orphan with the episode's id.
"""

from __future__ import annotations

import binascii
import gc
import importlib
import json
import struct
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from digline import recorder
from digline.host import recorder_status
from digline.recorder import RecordedClient, episode, wrap

SDKS = ("anthropic", "openai", "httpx2", "boto3", "botocore")
QUESTION = [{"role": "user", "content": "Capital of France?"}]


@pytest.fixture(autouse=True, scope="module")
def the_sdks_leave_with_this_module() -> Iterator[None]:
    before = set(sys.modules)
    yield
    for name in set(sys.modules) - before:
        if name.split(".", 1)[0] in SDKS:
            del sys.modules[name]


@pytest.fixture(autouse=True)
def on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(recorder.ENVIRONMENT_VARIABLE, "1")


def sdk(name: str) -> Any:
    return importlib.import_module(name)


def recordings(root: Path) -> list[dict[str, Any]]:
    return [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted((root / ".digline").glob("*/recordings/*/*.json"))
    ]


def counts(client: RecordedClient) -> dict[str, Any]:
    return dict(client.digline_counts)


def sse(events: list[tuple[str | None, object]]) -> bytes:
    """Server-sent events, as the providers send them."""
    lines: list[str] = []
    for name, data in events:
        if name is not None:
            lines.append(f"event: {name}")
        lines.append(f"data: {data if isinstance(data, str) else json.dumps(data)}")
        lines.append("")
    return ("\n".join(lines) + "\n").encode("utf-8")


# -- Anthropic ---------------------------------------------------------------- #

ANTHROPIC_WHOLE: dict[str, object] = {
    "id": "msg_1",
    "type": "message",
    "role": "assistant",
    "model": "claude-test",
    "content": [{"type": "text", "text": "Paris"}],
    "stop_reason": "end_turn",
    "stop_sequence": None,
    "usage": {"input_tokens": 12, "output_tokens": 3},
}


def anthropic_events(*, error: bool = False) -> bytes:
    start: dict[str, object] = {**ANTHROPIC_WHOLE, "content": [], "stop_reason": None}
    start["usage"] = {"input_tokens": 12, "output_tokens": 0}
    events: list[tuple[str | None, object]] = [
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
                "delta": {"type": "text_delta", "text": "Par"},
            },
        ),
    ]
    if error:
        events.append(
            (
                "error",
                {
                    "type": "error",
                    "error": {"type": "overloaded_error", "message": "Overloaded"},
                },
            )
        )
        return sse(events)
    events += [
        (
            "content_block_delta",
            {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "text_delta", "text": "is"},
            },
        ),
        ("content_block_stop", {"type": "content_block_stop", "index": 0}),
        (
            "message_delta",
            {
                "type": "message_delta",
                "delta": {"stop_reason": "end_turn", "stop_sequence": None},
                "usage": {"output_tokens": 3},
            },
        ),
        ("message_stop", {"type": "message_stop"}),
    ]
    return sse(events)


def an_anthropic(*, error: bool = False) -> Any:
    httpx2 = sdk("httpx2")

    def handle(request: Any) -> Any:
        body = json.loads(request.content)
        if body.get("stream"):
            return httpx2.Response(
                200,
                headers={"content-type": "text/event-stream"},
                content=anthropic_events(error=error),
            )
        return httpx2.Response(200, json=ANTHROPIC_WHOLE)

    return sdk("anthropic").Anthropic(
        api_key="test",
        http_client=httpx2.Client(transport=httpx2.MockTransport(handle)),
        max_retries=0,
    )


def ask_anthropic(client: Any, **extra: Any) -> Any:
    return client.messages.create(
        model="claude-test", max_tokens=10, messages=QUESTION, suite="triage", **extra
    )


# -- OpenAI ------------------------------------------------------------------- #

OPENAI_WHOLE: dict[str, object] = {
    "id": "c1",
    "object": "chat.completion",
    "created": 0,
    "model": "gpt-test",
    "choices": [
        {
            "index": 0,
            "message": {"role": "assistant", "content": "Paris"},
            "finish_reason": "stop",
        }
    ],
    "usage": {"prompt_tokens": 12, "completion_tokens": 3, "total_tokens": 15},
}


def openai_chunk(delta: dict[str, object], finish: str | None) -> dict[str, object]:
    return {
        "id": "c1",
        "object": "chat.completion.chunk",
        "created": 0,
        "model": "gpt-test",
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
    }


def an_openai(sent: list[dict[str, Any]] | None = None) -> Any:
    httpx2 = sdk("httpx2")

    def handle(request: Any) -> Any:
        body = json.loads(request.content)
        if sent is not None:
            sent.append(body)
        if not body.get("stream"):
            return httpx2.Response(200, json=OPENAI_WHOLE)
        events: list[tuple[str | None, object]] = [
            (None, openai_chunk({"role": "assistant", "content": "Par"}, None)),
            (None, openai_chunk({"content": "is"}, None)),
            (None, openai_chunk({}, "stop")),
        ]
        if body.get("stream_options", {}).get("include_usage"):
            usage: dict[str, object] = {**openai_chunk({}, None), "choices": []}
            usage["usage"] = OPENAI_WHOLE["usage"]
            events.append((None, usage))
        events.append((None, "[DONE]"))
        return httpx2.Response(
            200, headers={"content-type": "text/event-stream"}, content=sse(events)
        )

    return sdk("openai").OpenAI(
        api_key="test",
        base_url="http://openai.test/v1",
        http_client=httpx2.Client(transport=httpx2.MockTransport(handle)),
    )


def ask_openai(client: Any, **extra: Any) -> Any:
    return client.chat.completions.create(
        model="gpt-test", messages=QUESTION, suite="triage", **extra
    )


# -- Bedrock ------------------------------------------------------------------ #

BEDROCK_WHOLE: dict[str, object] = {
    "output": {"message": {"role": "assistant", "content": [{"text": "Paris"}]}},
    "stopReason": "end_turn",
    "usage": {"inputTokens": 12, "outputTokens": 3, "totalTokens": 15},
    "metrics": {"latencyMs": 5},
}


def frame(event_type: str, payload: object) -> bytes:
    """One AWS event-stream message: prelude, headers, payload, two CRCs."""
    headers = b""
    for name, value in (
        (":event-type", event_type),
        (":content-type", "application/json"),
        (":message-type", "event"),
    ):
        key, text = name.encode(), value.encode()
        headers += (
            bytes([len(key)]) + key + bytes([7]) + struct.pack(">H", len(text)) + text
        )
    body = json.dumps(payload).encode()
    prelude = struct.pack(">II", 12 + len(headers) + len(body) + 4, len(headers))
    head = prelude + struct.pack(">I", binascii.crc32(prelude) & 0xFFFFFFFF)
    message = head + headers + body
    return message + struct.pack(">I", binascii.crc32(message) & 0xFFFFFFFF)


BEDROCK_EVENTS = b"".join(
    (
        frame("messageStart", {"role": "assistant"}),
        frame("contentBlockDelta", {"delta": {"text": "Par"}, "contentBlockIndex": 0}),
        frame("contentBlockDelta", {"delta": {"text": "is"}, "contentBlockIndex": 0}),
        frame("contentBlockStop", {"contentBlockIndex": 0}),
        frame("messageStop", {"stopReason": "end_turn"}),
        frame(
            "metadata",
            {
                "usage": {"inputTokens": 12, "outputTokens": 3, "totalTokens": 15},
                "metrics": {"latencyMs": 5},
            },
        ),
    )
)


class _Raw:
    """What botocore reads an event stream's body from."""

    def __init__(self, data: bytes) -> None:
        self._data = data

    def stream(self, **_: object) -> Iterator[bytes]:
        yield from (self._data[i : i + 40] for i in range(0, len(self._data), 40))

    def close(self) -> None:
        return None


def a_bedrock() -> Any:
    client = sdk("boto3").client(
        "bedrock-runtime",
        region_name="us-east-1",
        aws_access_key_id="test",
        aws_secret_access_key="test",
    )
    awsrequest = sdk("botocore.awsrequest")

    def send(request: Any, **_: object) -> Any:
        if request.url.endswith("/converse-stream"):
            return awsrequest.AWSResponse(
                request.url,
                200,
                {"content-type": "application/vnd.amazon.eventstream"},
                _Raw(BEDROCK_EVENTS),
            )
        raw = _Raw(json.dumps(BEDROCK_WHOLE).encode())
        response = awsrequest.AWSResponse(
            request.url, 200, {"content-type": "application/json"}, raw
        )
        response._content = json.dumps(BEDROCK_WHOLE).encode()  # noqa: SLF001
        return response

    client.meta.events.register("before-send.bedrock-runtime.*", send)
    return client


BEDROCK_REQUEST: dict[str, Any] = {
    "modelId": "model-test",
    "messages": [{"role": "user", "content": [{"text": "Capital of France?"}]}],
    "inferenceConfig": {"maxTokens": 10},
}


# -- streamed = whole --------------------------------------------------------- #


def same(whole: dict[str, Any], streamed: dict[str, Any]) -> None:
    assert streamed["case"] == whole["case"]
    assert streamed["setup_digest"] == whole["setup_digest"]
    assert streamed["response"]["output"] == whole["response"]["output"] == "Paris"
    assert streamed["response"].get("usage") == whole["response"].get("usage")


def test_anthropic_streamed_is_recorded_as_the_whole_reply(tmp_path: Path) -> None:
    client = wrap(an_anthropic(), app="a", tenant="acme", root=tmp_path)
    ask_anthropic(client)
    stream = ask_anthropic(client, stream=True)
    assert isinstance(stream, sdk("anthropic").Stream)
    assert len(recordings(tmp_path)) == 1  # nothing until the stream is read
    kinds = [event.type for event in stream]
    assert kinds == [
        "message_start",
        "content_block_start",
        "content_block_delta",
        "content_block_delta",
        "content_block_stop",
        "message_delta",
        "message_stop",
    ]
    whole, streamed = recordings(tmp_path)
    same(whole, streamed)
    assert counts(client)["not_recorded"] == {}


def test_anthropic_messages_stream_is_recorded_as_the_whole_reply(
    tmp_path: Path,
) -> None:
    client = wrap(an_anthropic(), app="a", tenant="acme", root=tmp_path)
    ask_anthropic(client)
    with client.messages.stream(
        model="claude-test", max_tokens=10, messages=QUESTION, suite="triage"
    ) as stream:
        text = "".join(stream.text_stream)
    assert text == "Paris"
    whole, streamed = recordings(tmp_path)
    same(whole, streamed)


def test_openai_streamed_is_recorded_as_the_whole_reply(tmp_path: Path) -> None:
    client = wrap(an_openai(), app="a", tenant="acme", root=tmp_path)
    ask_openai(client)
    stream = ask_openai(client, stream=True, stream_options={"include_usage": True})
    assert isinstance(stream, sdk("openai").Stream)
    text = "".join(
        chunk.choices[0].delta.content or "" for chunk in stream if chunk.choices
    )
    assert text == "Paris"
    whole, streamed = recordings(tmp_path)
    same(whole, streamed)
    assert counts(client)["noted"] == {}


def test_openai_chat_completions_stream_is_recorded(tmp_path: Path) -> None:
    client = wrap(an_openai(), app="a", tenant="acme", root=tmp_path)
    ask_openai(client)
    with client.chat.completions.stream(
        model="gpt-test",
        messages=QUESTION,
        stream_options={"include_usage": True},
        suite="triage",
    ) as stream:
        for _ in stream:
            pass
    whole, streamed = recordings(tmp_path)
    same(whole, streamed)


def test_bedrock_converse_stream_is_recorded_as_the_whole_reply(
    tmp_path: Path,
) -> None:
    client = wrap(a_bedrock(), app="a", tenant="acme", root=tmp_path)
    client.converse(**BEDROCK_REQUEST, suite="triage")
    reply = client.converse_stream(**BEDROCK_REQUEST, suite="triage")
    stream = reply["stream"]
    assert isinstance(stream, sdk("botocore.eventstream").EventStream)
    kinds = [next(iter(event)) for event in stream]
    assert kinds == [
        "messageStart",
        "contentBlockDelta",
        "contentBlockDelta",
        "contentBlockStop",
        "messageStop",
        "metadata",
    ]
    whole, streamed = recordings(tmp_path)
    same(whole, streamed)


def test_the_events_are_the_ones_the_bare_sdk_gives(tmp_path: Path) -> None:
    bare = [
        event.to_dict()
        for event in an_anthropic().messages.create(
            model="claude-test", max_tokens=10, messages=QUESTION, stream=True
        )
    ]
    client = wrap(an_anthropic(), app="a", tenant="acme", root=tmp_path)
    watched = [event.to_dict() for event in ask_anthropic(client, stream=True)]
    assert watched == bare


# -- abandoned, failed -------------------------------------------------------- #


def test_a_stream_closed_before_its_end_is_not_recorded(tmp_path: Path) -> None:
    client = wrap(an_anthropic(), app="a", tenant="acme", root=tmp_path)
    stream = ask_anthropic(client, stream=True)
    next(stream)
    stream.close()
    assert recordings(tmp_path) == []
    assert counts(client)["not_recorded"] == {"stream abandoned": 1}


def test_a_stream_dropped_unread_is_abandoned(tmp_path: Path) -> None:
    client = wrap(an_openai(), app="a", tenant="acme", root=tmp_path)
    stream = ask_openai(client, stream=True)
    next(iter(stream))
    del stream
    gc.collect()
    assert recordings(tmp_path) == []
    assert counts(client)["not_recorded"] == {"stream abandoned": 1}


def test_an_exception_inside_the_stream_propagates_and_is_counted(
    tmp_path: Path,
) -> None:
    client = wrap(an_anthropic(error=True), app="a", tenant="acme", root=tmp_path)
    stream = ask_anthropic(client, stream=True)
    with pytest.raises(sdk("anthropic").APIStatusError) as raised:
        for _ in stream:
            pass
    assert recordings(tmp_path) == []
    assert counts(client)["not_recorded"] == {type(raised.value).__name__: 1}


# -- usage -------------------------------------------------------------------- #


def test_openai_usage_is_never_asked_for_in_the_applications_place(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    sent: list[dict[str, Any]] = []
    client = wrap(an_openai(sent), app="a", tenant="acme", root=tmp_path)
    for _ in ask_openai(client, stream=True):
        pass
    # What reached the provider is what the application asked, and no more.
    assert sent == [{"model": "gpt-test", "messages": QUESTION, "stream": True}]
    [written] = recordings(tmp_path)
    assert written["response"]["output"] == "Paris"
    assert "usage" not in written["response"]
    assert counts(client)["noted"] == {"usage not reported": 1}
    # The counts reach the file at the next tick; this is that tick.
    recorder._flush(client._digline_state)  # pyright: ignore[reportPrivateUsage]
    [status] = recorder_status(tmp_path, "acme")
    [triage] = status.suites
    assert dict(triage.noted) == {"usage not reported": 1}


# -- episodes ----------------------------------------------------------------- #


def test_a_streamed_child_joins_its_episode_at_the_end_of_its_stream(
    tmp_path: Path,
) -> None:
    client = wrap(an_anthropic(), app="a", tenant="acme", root=tmp_path)
    with episode(client, suite="agent", case={"m": "q"}) as ep:
        for _ in ask_anthropic(client, stream=True):
            pass
    found = recordings(tmp_path)
    [turn] = [r for r in found if "steps" in r]
    [child] = [r for r in found if "steps" not in r]
    assert child["episode"] == ep.id and "orphan" not in child
    assert [step["actor"] for step in turn["steps"]] == ["model"]
    assert turn["response"]["output"] == "Paris"


def test_a_stream_that_ends_after_its_episode_is_an_orphan_with_its_id(
    tmp_path: Path,
) -> None:
    client = wrap(an_anthropic(), app="a", tenant="acme", root=tmp_path)
    with episode(client, suite="agent", case={"m": "q"}) as ep:
        ep.output("done")
        stream = ask_anthropic(client, stream=True)
    for _ in stream:
        pass
    found = recordings(tmp_path)
    [turn] = [r for r in found if "steps" in r]
    [child] = [r for r in found if "steps" not in r]
    assert turn["steps"] == []
    assert turn["unrecorded_children"] == 1
    assert child["episode"] == ep.id
    assert child["orphan"] is True
    assert counts(client)["noted"] == {"ended after its episode": 1}
