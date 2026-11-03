"""The recorder on asynchronous clients: `anthropic.AsyncAnthropic` and
`openai.AsyncOpenAI`, on the SDKs' own clients with no network. (ADR 0058 §5,
§13, the second piece)

The fakes are the ones `tests/test_recorder_streaming.py` builds, over an
`httpx2.AsyncClient` with a `MockTransport`. Each test runs its own event loop
with `asyncio.run`.

What is held here:

- the same request through the synchronous and the asynchronous client gives
  the same recording, and a streamed asynchronous reply the same as a whole
  one;
- what the application awaits is what the SDK returns: a stream comes back
  unread, and nothing is recorded before the application reads it to its end;
- an asynchronous stream closed or dropped before its end is abandoned, and an
  exception inside it propagates and is counted;
- `async with episode(...)`: calls gathered inside it are its children; a call
  in a task started before it is an orphan, and a child with `async with
  attach(...)`.
"""

from __future__ import annotations

import asyncio
import gc
import json
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from tests.test_recorder_streaming import (
    ANTHROPIC_WHOLE,
    OPENAI_WHOLE,
    QUESTION,
    an_anthropic,
    an_openai,
    anthropic_events,
    openai_chunk,
    same,
    sse,
)

from digline import recorder
from digline.recorder import RecordedClient, attach, episode, wrap

SDKS = ("anthropic", "openai", "httpx2")


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
    import importlib

    return importlib.import_module(name)


def recordings(root: Path) -> list[dict[str, Any]]:
    return [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted((root / ".digline").glob("*/recordings/*/*.json"))
    ]


def counts(client: RecordedClient) -> dict[str, Any]:
    return dict(client.digline_counts)


def an_async_anthropic(*, error: bool = False) -> Any:
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

    return sdk("anthropic").AsyncAnthropic(
        api_key="test",
        http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handle)),
        max_retries=0,
    )


def an_async_openai() -> Any:
    httpx2 = sdk("httpx2")

    def handle(request: Any) -> Any:
        body = json.loads(request.content)
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

    return sdk("openai").AsyncOpenAI(
        api_key="test",
        base_url="http://openai.test/v1",
        http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handle)),
    )


async def ask(client: Any, **extra: Any) -> Any:
    return await client.messages.create(
        model="claude-test", max_tokens=10, messages=QUESTION, suite="triage", **extra
    )


# -- sync and async, whole and streamed --------------------------------------- #


def test_anthropic_async_is_recorded_as_the_sync_client_records(tmp_path: Path) -> None:
    client = wrap(an_anthropic(), app="a", tenant="acme", root=tmp_path)
    client.messages.create(
        model="claude-test", max_tokens=10, messages=QUESTION, suite="triage"
    )
    async_client = wrap(an_async_anthropic(), app="a", tenant="acme", root=tmp_path)
    reply = asyncio.run(ask(async_client))
    assert reply.content[0].text == "Paris"
    sync, asynchronous = recordings(tmp_path)
    same(sync, asynchronous)


def test_openai_async_is_recorded_as_the_sync_client_records(tmp_path: Path) -> None:
    client = wrap(an_openai(), app="a", tenant="acme", root=tmp_path)
    client.chat.completions.create(model="gpt-test", messages=QUESTION, suite="triage")
    async_client = wrap(an_async_openai(), app="a", tenant="acme", root=tmp_path)

    async def call() -> Any:
        return await async_client.chat.completions.create(
            model="gpt-test", messages=QUESTION, suite="triage"
        )

    asyncio.run(call())
    sync, asynchronous = recordings(tmp_path)
    same(sync, asynchronous)


def test_anthropic_async_stream_is_recorded_as_the_whole_reply(
    tmp_path: Path,
) -> None:
    client = wrap(an_async_anthropic(), app="a", tenant="acme", root=tmp_path)

    async def run() -> list[str]:
        await ask(client)
        stream = await ask(client, stream=True)
        assert isinstance(stream, sdk("anthropic").AsyncStream)
        # Back unread: nothing is recorded until the application reads it.
        assert len(recordings(tmp_path)) == 1
        return [event.type async for event in stream]

    kinds = asyncio.run(run())
    assert kinds[0] == "message_start" and kinds[-1] == "message_stop"
    whole, streamed = recordings(tmp_path)
    same(whole, streamed)


def test_anthropic_async_messages_stream_is_recorded(tmp_path: Path) -> None:
    client = wrap(an_async_anthropic(), app="a", tenant="acme", root=tmp_path)

    async def run() -> str:
        await ask(client)
        async with client.messages.stream(
            model="claude-test", max_tokens=10, messages=QUESTION, suite="triage"
        ) as stream:
            return "".join([text async for text in stream.text_stream])

    assert asyncio.run(run()) == "Paris"
    whole, streamed = recordings(tmp_path)
    same(whole, streamed)


def test_openai_async_streams_are_recorded(tmp_path: Path) -> None:
    client = wrap(an_async_openai(), app="a", tenant="acme", root=tmp_path)

    async def run() -> None:
        await client.chat.completions.create(
            model="gpt-test", messages=QUESTION, suite="triage"
        )
        stream = await client.chat.completions.create(
            model="gpt-test",
            messages=QUESTION,
            stream=True,
            stream_options={"include_usage": True},
            suite="triage",
        )
        assert isinstance(stream, sdk("openai").AsyncStream)
        async for _ in stream:
            pass
        async with client.chat.completions.stream(
            model="gpt-test",
            messages=QUESTION,
            stream_options={"include_usage": True},
            suite="triage",
        ) as managed:
            async for _ in managed:
                pass

    asyncio.run(run())
    whole, streamed, managed = recordings(tmp_path)
    same(whole, streamed)
    same(whole, managed)


# -- abandoned, failed -------------------------------------------------------- #


def test_an_async_stream_closed_before_its_end_is_abandoned(tmp_path: Path) -> None:
    client = wrap(an_async_anthropic(), app="a", tenant="acme", root=tmp_path)

    async def run() -> None:
        stream = await ask(client, stream=True)
        await stream.__anext__()
        await stream.close()

    asyncio.run(run())
    assert recordings(tmp_path) == []
    assert counts(client)["not_recorded"] == {"stream abandoned": 1}


def test_an_async_stream_dropped_unread_is_abandoned(tmp_path: Path) -> None:
    client = wrap(an_async_anthropic(), app="a", tenant="acme", root=tmp_path)

    async def run() -> None:
        stream = await ask(client, stream=True)
        await stream.__anext__()
        del stream
        gc.collect()

    asyncio.run(run())
    assert recordings(tmp_path) == []
    assert counts(client)["not_recorded"] == {"stream abandoned": 1}


def test_an_exception_inside_an_async_stream_propagates(tmp_path: Path) -> None:
    client = wrap(an_async_anthropic(error=True), app="a", tenant="acme", root=tmp_path)

    async def run() -> None:
        async for _ in await ask(client, stream=True):
            pass

    with pytest.raises(sdk("anthropic").APIStatusError) as raised:
        asyncio.run(run())
    assert recordings(tmp_path) == []
    assert counts(client)["not_recorded"] == {type(raised.value).__name__: 1}


# -- episodes in asyncio ------------------------------------------------------ #


def test_calls_gathered_inside_an_async_episode_are_its_children(
    tmp_path: Path,
) -> None:
    client = wrap(an_async_anthropic(), app="a", tenant="acme", root=tmp_path)

    async def run() -> str | None:
        async with episode(client, suite="agent", case={"m": "q"}) as ep:
            await asyncio.gather(ask(client), ask(client), ask(client))
        return ep.id

    episode_id = asyncio.run(run())
    found = recordings(tmp_path)
    [turn] = [r for r in found if "steps" in r]
    children = [r for r in found if "steps" not in r]
    assert [child["episode"] for child in children] == [episode_id] * 3
    assert [step["actor"] for step in turn["steps"]] == ["model"] * 3


def run_in_a_task_started_before(
    client: Any, *, attached: bool
) -> tuple[str | None, list[dict[str, Any]]]:
    """A task created before the episode, so its context has no episode; it
    makes its call once the episode is open, attached by id or not."""

    async def run() -> str | None:
        go = asyncio.Event()
        held: list[str | None] = []

        async def late() -> None:
            await go.wait()
            if attached:
                async with attach(held[0]):
                    await ask(client)
            else:
                await ask(client)

        task = asyncio.create_task(late())
        async with episode(client, suite="agent", case={"m": "q"}) as ep:
            held.append(ep.id)
            go.set()
            await task
            ep.output("done")
        return ep.id

    episode_id = asyncio.run(run())
    return episode_id, recordings(client._digline_state.root)  # pyright: ignore[reportPrivateUsage]


def test_a_call_in_a_task_started_before_the_episode_is_an_orphan(
    tmp_path: Path,
) -> None:
    client = wrap(an_async_anthropic(), app="a", tenant="acme", root=tmp_path)
    _, found = run_in_a_task_started_before(client, attached=False)
    [child] = [r for r in found if "steps" not in r]
    assert "episode" not in child
    assert child["orphan"] is True
    assert counts(client)["orphan"] == 1


def test_attach_makes_it_a_child(tmp_path: Path) -> None:
    client = wrap(an_async_anthropic(), app="a", tenant="acme", root=tmp_path)
    episode_id, found = run_in_a_task_started_before(client, attached=True)
    [child] = [r for r in found if "steps" not in r]
    assert child["episode"] == episode_id
    assert "orphan" not in child
    assert counts(client)["orphan"] == 0


# -- what is wrapped ---------------------------------------------------------- #


def test_the_async_clients_are_wrapped_and_off_passes_through(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(recorder.ENVIRONMENT_VARIABLE)
    client = wrap(an_async_anthropic(), app="a", tenant="acme", root=tmp_path)

    async def run() -> Any:
        return await ask(client)

    assert asyncio.run(run()).content[0].text == "Paris"
    assert not (tmp_path / ".digline").exists()
