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
import subprocess
import sys
import warnings
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
from digline.host import recorder_status
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


# -- the corrections of the user pass of 2026-11-03 --------------------------- #


def test_an_async_stream_left_half_read_when_the_loop_closes_is_abandoned(
    tmp_path: Path,
) -> None:
    """The loop closes the generator the application broke out of, and what
    it throws in, `CancelledError` or `GeneratorExit`, is not the SDK's: the
    stream is abandoned, never counted by that class's name."""
    client = wrap(an_async_anthropic(), app="a", tenant="acme", root=tmp_path)

    async def run() -> None:
        stream = await ask(client, stream=True)
        async for _ in stream:
            break

    asyncio.run(run())
    assert recordings(tmp_path) == []
    assert counts(client)["not_recorded"] == {"stream abandoned": 1}


def test_a_call_attached_after_its_episode_closed_is_an_orphan_noted(
    tmp_path: Path,
) -> None:
    """A task attached to the episode whose call ends after the episode
    closed: recorded with the episode's id, marked an orphan and noted, as a
    stream that ends late is. The episode is written without it."""
    client = wrap(an_async_anthropic(), app="a", tenant="acme", root=tmp_path)

    async def run() -> str | None:
        go, closed = asyncio.Event(), asyncio.Event()
        held: list[str | None] = []

        async def late() -> None:
            await go.wait()
            async with attach(held[0]):
                await closed.wait()
                await ask(client)

        task = asyncio.create_task(late())
        async with episode(client, suite="agent", case={"m": "q"}) as ep:
            held.append(ep.id)
            go.set()
            await ask(client)
            ep.output("done")
        closed.set()
        await task
        return ep.id

    episode_id = asyncio.run(run())
    child, turn, after = recordings(tmp_path)
    assert child["episode"] == episode_id and "orphan" not in child
    assert turn["id"] == episode_id and len(turn["steps"]) == 1
    assert after["episode"] == episode_id and after["orphan"] is True
    assert counts(client)["noted"] == {"ended after its episode": 1}
    [triage] = [
        s for s in recorder_status(tmp_path, "acme")[0].suites if s.suite == "triage"
    ]
    assert (triage.calls, triage.inside_episodes, triage.orphans) == (2, 1, 1)


def test_a_call_attached_to_an_episode_this_process_never_opened_is_a_child(
    tmp_path: Path,
) -> None:
    """An id from another process, whole or streamed: the episode was never
    open here, so the call is not late. It carries the id unmarked, for the
    import to join."""
    client = wrap(an_async_anthropic(), app="a", tenant="acme", root=tmp_path)
    elsewhere = "0" * 32

    async def run() -> None:
        async with attach(elsewhere):
            await ask(client)
            async for _ in await ask(client, stream=True):
                pass

    asyncio.run(run())
    whole, streamed = recordings(tmp_path)
    for child in (whole, streamed):
        assert child["episode"] == elsewhere
        assert "orphan" not in child
    assert counts(client)["noted"] == {}


def test_one_process_writes_one_directory_whatever_the_clients_it_wraps(
    tmp_path: Path,
) -> None:
    """A synchronous and an asynchronous client in one process: one
    subdirectory for the tenant, one counts file, the two clients' counts in
    it (ADR 0058 §4, §10)."""
    synchronous = wrap(an_anthropic(), app="a", tenant="acme", root=tmp_path)
    asynchronous = wrap(an_async_anthropic(), app="a", tenant="acme", root=tmp_path)
    synchronous.messages.create(
        model="claude-test", max_tokens=10, messages=QUESTION, suite="triage"
    )
    asyncio.run(ask(asynchronous))
    recorder._flush(asynchronous._digline_state)  # pyright: ignore[reportPrivateUsage]
    [folder] = (tmp_path / ".digline" / "acme" / "recordings").iterdir()
    assert sorted(p.name for p in folder.iterdir()) == [
        ".counts",
        "000001.json",
        "000002.json",
    ]
    written = json.loads((folder / ".counts").read_text(encoding="utf-8"))
    assert written["suites"]["triage"]["recorded"] == 2


#: The longest the event loop may stall on the first recorded call, with the
#: recorder on when the client is wrapped. Measured with this program on
#: 2026-11-03 on a laptop (macOS, CPython 3.14.5), five runs each: 9.7 to
#: 11.9 ms with the imports in `wrap()`, 88.1 to 91.9 ms with them at the
#: first recording. Between the two, with room for a slower machine.
FIRST_CALL_STALL_MS = 50.0

#: A fresh interpreter, so that nothing of digline's is imported before
#: `wrap()`: a ticker task sleeps 1 ms at a time and records the longest gap
#: while the first call, and then a second, are awaited.
#:
#: Diagnostic, for now: the first call is also cut into phases, each a
#: function of the recorder timed with `perf_counter` while that call runs,
#: and the modules it imports are listed. Nested phases: `record` holds
#: `now` and `write`; `write` holds `layout` and `link`; `layout` holds
#: `ensure_layout`. `rest` is the call's wall time less `look`, `map`,
#: `record` and `tally`: the SDK and the loop.
STALL_PROGRAM = """\
import asyncio, json, os, sys, time
import anthropic, httpx2
import digline.recorder as recorder
cold = "digline.core" not in sys.modules
body = __BODY__
http = httpx2.AsyncClient(transport=httpx2.MockTransport(
    lambda request: httpx2.Response(200, json=body)))
client = recorder.wrap(anthropic.AsyncAnthropic(api_key="t", http_client=http),
                       app="a", tenant="acme")
ready = "digline.core" in sys.modules

from digline.store import file_store

spent = {}
timing = [False]

def timed(owner, name, phase):
    original = getattr(owner, name)
    def wrapper(*args, **kwargs):
        started = time.perf_counter()
        try:
            return original(*args, **kwargs)
        finally:
            if timing[0]:
                took = (time.perf_counter() - started) * 1000.0
                spent[phase] = spent.get(phase, 0.0) + took
    setattr(owner, name, wrapper)

timed(recorder, "_look", "look")
timed(recorder, "_map_or_none", "map")
timed(recorder, "_record", "record")
timed(recorder, "_now", "now")
timed(recorder, "_write", "write")
timed(file_store.RecordingWriter, "_choose", "layout")
timed(file_store.FileResultStore, "ensure_layout", "ensure_layout")
timed(os, "link", "link")
timed(recorder, "_tally", "tally")

async def main():
    gaps, stop = [], [False]
    async def ticker():
        last = time.perf_counter()
        while not stop[0]:
            await asyncio.sleep(0.001)
            now = time.perf_counter()
            gaps.append((now - last) * 1000.0)
            last = now
    task = asyncio.create_task(ticker())
    await asyncio.sleep(0.01)
    stalls, phases, imported = [], {}, []
    for n in range(2):
        gaps.clear()
        before = set(sys.modules)
        timing[0] = n == 0
        started = time.perf_counter()
        await client.messages.create(model="claude-test", max_tokens=10,
            messages=[{"role": "user", "content": str(n)}], suite="triage")
        wall = (time.perf_counter() - started) * 1000.0
        timing[0] = False
        if n == 0:
            imported = sorted(set(sys.modules) - before)
            phases = {k: round(v, 2) for k, v in sorted(spent.items())}
            phases["wall"] = round(wall, 2)
            phases["rest"] = round(wall - sum(spent.get(k, 0.0)
                for k in ("look", "map", "record", "tally")), 2)
        await asyncio.sleep(0.005)
        stalls.append(max(gaps))
    stop[0] = True
    await task
    return stalls, phases, imported

(first, second), phases, imported = asyncio.run(main())
print(json.dumps({"cold": cold, "ready": ready, "first": first, "second": second,
                  "recorded": client.digline_counts["recorded"],
                  "phases": phases, "imported": imported}))
"""


class FirstCallBreakdown(UserWarning):
    """The first call's phases and new modules, said on every run: pytest's
    warnings summary shows it in a CI log whether the test passed or not."""


def test_the_first_recorded_call_does_not_hold_the_loop_for_the_imports(
    tmp_path: Path,
) -> None:
    """On when the client is wrapped: `wrap()` imports what the first
    recording would, at the application's start, and the first call holds the
    loop no longer than `FIRST_CALL_STALL_MS`."""
    done = subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            STALL_PROGRAM.replace("__BODY__", repr(ANTHROPIC_WHOLE)),
        ],
        capture_output=True,
        text=True,
        check=False,
        cwd=tmp_path,
        env={"PATH": "/usr/bin:/bin", recorder.ENVIRONMENT_VARIABLE: "1"},
    )
    assert done.returncode == 0, done.stderr
    measured = json.loads(done.stdout)
    breakdown = (
        f"first-call stall {measured['first']:.2f} ms, second "
        f"{measured['second']:.2f} ms; phases in ms {measured['phases']}; "
        f"{len(measured['imported'])} modules imported by the first call: "
        f"{measured['imported']}"
    )
    warnings.warn(breakdown, FirstCallBreakdown, stacklevel=1)
    # The control: the interpreter was cold before `wrap()`, and both calls
    # were recorded, so the stall measured is a recording's.
    assert measured["cold"] is True
    assert measured["recorded"] == 2
    assert measured["first"] < FIRST_CALL_STALL_MS, breakdown
    # And why: the core was imported by `wrap()`, before any call.
    assert measured["ready"] is True
