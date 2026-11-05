"""The recorder's episode, on Anthropic's own SDK, with no network.
(ADR 0058 §5, §7, §8, §9)

What is held here:

- an episode with three calls is one recording whose response's steps are
  the calls' trajectory (ADR 0060 §6), and three recordings that carry its
  id;
- a tool's result, which the wrapper never sees, is absent from its step and
  says `not_reported`, never filled in;
- two levels of nesting, each recording carrying its parent's id;
- the setup by hand against the derived one, and the derived digest moving
  with `git_commit` and with nothing that is the same;
- the id reaches a call through `attach`, in a pool thread, a plain thread and
  a spawned process; without it a call in a pool thread is an orphan, counted
  and attached to nothing; `asyncio.to_thread` inherits it;
- an exception inside the block propagates, and the episode is still written,
  interrupted;
- off, an episode is an empty context and imports nothing of digline's core.

The SDK is imported inside a test and taken out of `sys.modules` when the
module is done, for the reason `tests/test_recorder.py` gives.
"""

from __future__ import annotations

import asyncio
import datetime
import importlib
import json
import multiprocessing
import subprocess
import sys
import threading
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest

from digline import recorder
from digline.core.recording import setup_digest_of
from digline.core.run import MAX_RECORDED_CHARS
from digline.recorder import (
    UNASSIGNED,
    RecordedClient,
    RecorderStartError,
    attach,
    episode,
    wrap,
)

SDKS = ("anthropic", "httpx2")

#: Three replies, in the order a turn of a support agent gets them: a lookup,
#: a refund, then the answer.
LOOKUP: dict[str, object] = {
    "id": "msg_1",
    "type": "message",
    "role": "assistant",
    "model": "claude-test",
    "content": [
        {
            "type": "tool_use",
            "id": "toolu_1",
            "name": "lookup",
            "input": {"order": "A1"},
        }
    ],
    "stop_reason": "tool_use",
    "usage": {"input_tokens": 20, "output_tokens": 5},
}
REFUND: dict[str, object] = {
    **LOOKUP,
    "id": "msg_2",
    "content": [
        {"type": "text", "text": "Refunding."},
        {
            "type": "tool_use",
            "id": "toolu_2",
            "name": "refund",
            "input": {"order": "A1"},
        },
    ],
}
ANSWER: dict[str, object] = {
    **LOOKUP,
    "id": "msg_3",
    "content": [{"type": "text", "text": "Your refund is on its way."}],
    "stop_reason": "end_turn",
}
QUESTION = [{"role": "user", "content": "Where is my refund for A1?"}]
CASE: dict[str, object] = {"message": "Where is my refund for A1?"}


@pytest.fixture(autouse=True, scope="module")
def the_sdks_leave_with_this_module() -> Iterator[None]:
    before = set(sys.modules)
    yield
    for name in set(sys.modules) - before:
        if name.split(".", 1)[0] in SDKS:
            del sys.modules[name]


def an_anthropic(*replies: dict[str, object]) -> Any:
    """A client that answers with `replies` in turn, then with the last."""
    httpx2 = importlib.import_module("httpx2")
    queue = list(replies)

    def handle(request: object) -> Any:
        body = queue.pop(0) if len(queue) > 1 else queue[0]
        return httpx2.Response(200, json=body)

    return importlib.import_module("anthropic").Anthropic(
        api_key="test",
        http_client=httpx2.Client(transport=httpx2.MockTransport(handle)),
        max_retries=0,
    )


def wrapped(root: Path, *replies: dict[str, object]) -> RecordedClient:
    return wrap(an_anthropic(*replies), app="support", tenant="acme", root=root)


def ask(client: RecordedClient, suite: str | None = "triage") -> Any:
    keywords: dict[str, Any] = {} if suite is None else {"suite": suite}
    return client.messages.create(
        model="claude-test", max_tokens=50, messages=QUESTION, **keywords
    )


@pytest.fixture
def on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(recorder.ENVIRONMENT_VARIABLE, "1")


@pytest.fixture
def off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(recorder.ENVIRONMENT_VARIABLE, raising=False)


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """The recorder's clock, moved by hand: `clock[0] += 60` is a minute."""
    now = [1000.0]
    monkeypatch.setattr(recorder, "_clock", lambda: now[0])
    return now


@pytest.fixture
def commit(monkeypatch: pytest.MonkeyPatch) -> list[str | None]:
    """The commit `git_commit` answers, settable by a test: the reading the
    episode does, replaced where it is looked up."""
    answer: list[str | None] = ["a" * 40]
    environment = importlib.import_module("digline.host.environment")

    def git_commit(root: Path) -> str | None:
        return answer[0]

    monkeypatch.setattr(environment, "git_commit", git_commit)
    return answer


def recordings(root: Path) -> list[dict[str, Any]]:
    return [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted((root / ".digline").glob("*/recordings/*/*.json"))
    ]


def episodes(root: Path) -> list[dict[str, Any]]:
    return [found for found in recordings(root) if "id" in found]


def calls(root: Path) -> list[dict[str, Any]]:
    return [found for found in recordings(root) if "id" not in found]


def counts(client: RecordedClient) -> dict[str, Any]:
    return dict(client.digline_counts)


# -- one episode, three calls ------------------------------------------------- #


@pytest.mark.usefixtures("on", "commit")
def test_an_episode_of_three_calls_is_one_recording_and_three_children(
    tmp_path: Path,
) -> None:
    client = wrapped(tmp_path, LOOKUP, REFUND, ANSWER)
    with episode(client, suite="support-agent", case=CASE) as ep:
        for _ in range(3):
            ask(client)
        ep.output("Refund sent for A1.")
    assert ep.id is not None and len(ep.id) == 32
    int(ep.id, 16)  # hexadecimal
    [turn] = episodes(tmp_path)
    children = calls(tmp_path)
    assert [child["episode"] for child in children] == [ep.id] * 3
    assert "episode" not in turn
    # Its own id, the one its children carry: the files alone join them.
    assert turn["id"] == ep.id
    assert all("id" not in child for child in children)
    # Written with the system time, read by the host's clock.
    for found in (turn, *children):
        datetime.datetime.fromisoformat(found["recorded_at"])
    assert turn["suite"] == "support-agent"
    assert turn["case"] == CASE
    assert turn["app"] == "support"
    assert turn["source_tenant"] == "acme"
    assert turn["response"]["output"] == "Refund sent for A1."
    assert [call["tool"] for call in turn["response"]["tool_calls"]] == [
        "lookup",
        "refund",
    ]
    assert [
        (step["index"], step["actor"], step.get("finish"), step.get("tool"))
        for step in turn["response"]["steps"]
    ] == [
        (0, "model", "tool_use", None),
        (1, "tool", None, "lookup"),
        (2, "model", "tool_use", None),
        (3, "tool", None, "refund"),
        (4, "model", "stop", None),
    ]
    assert turn["response"]["steps"][1]["arguments"] == '{"order":"A1"}'
    # Read off the steps, as a run reads them live: the last model step's
    # finish, and the tool steps' names, one per call, in order.
    assert turn["response"]["finish"] == "stop"
    assert turn["response"]["tools"] == ["lookup", "refund"]
    assert "interrupted" not in turn
    assert "unrecorded_children" not in turn
    assert counts(client) == {
        "recorded": 4,
        "not_recorded": {},
        "orphan": 0,
        "noted": {},
    }


@pytest.mark.usefixtures("on", "commit")
def test_a_tools_result_is_absent_from_its_step_never_invented(
    tmp_path: Path,
) -> None:
    client = wrapped(tmp_path, LOOKUP, ANSWER)
    with episode(client, suite="support-agent", case=CASE):
        ask(client)
        ask(client)
    [turn] = episodes(tmp_path)
    [tool] = [step for step in turn["response"]["steps"] if step["actor"] == "tool"]
    assert "result" not in tool
    assert tool["result_absence"] == "not_reported"
    assert tool["status"] == "not_reported"
    [call] = turn["response"]["tool_calls"]
    assert "result" not in call
    assert call["result_absence"] == "not_reported"


@pytest.mark.usefixtures("on", "commit")
def test_without_an_output_the_last_models_text_is_the_episodes(
    tmp_path: Path,
) -> None:
    client = wrapped(tmp_path, LOOKUP, ANSWER)
    with episode(client, suite="support-agent", case=CASE):
        ask(client)
        ask(client)
    [turn] = episodes(tmp_path)
    assert turn["response"]["output"] == "Your refund is on its way."
    assert turn["response"]["kind"] == "text"


@pytest.mark.usefixtures("on", "commit")
def test_an_episode_with_no_call_and_no_output_is_counted_not_written(
    tmp_path: Path,
) -> None:
    client = wrapped(tmp_path, ANSWER)
    with episode(client, suite="support-agent", case=CASE):
        pass
    assert recordings(tmp_path) == []
    assert counts(client) == {
        "recorded": 0,
        "not_recorded": {"no output": 1},
        "orphan": 0,
        "noted": {},
    }


@pytest.mark.usefixtures("on", "commit")
def test_an_episode_with_an_output_and_no_call_has_no_steps(tmp_path: Path) -> None:
    client = wrapped(tmp_path, ANSWER)
    with episode(client, suite="support-agent", case=CASE) as ep:
        ep.output({"route": "human"})
    [turn] = episodes(tmp_path)
    assert "steps" not in turn["response"]
    assert turn["response"]["output"] == '{"route":"human"}'
    assert turn["response"]["kind"] == "structured"
    assert turn["response"]["tool_calls"] == []
    # No call, so no reply ended: no finish, and no tool named, as
    # `tool_calls` says.
    assert "finish" not in turn["response"]
    assert turn["response"]["tools"] == []
    assert turn["setup"] == {"child_setups": [], "git_commit": "a" * 40}


@pytest.mark.usefixtures("on", "commit")
def test_an_episode_that_names_no_suite_is_unassigned_with_its_call_site(
    tmp_path: Path,
) -> None:
    client = wrapped(tmp_path, ANSWER)
    with episode(client, case=CASE):
        ask(client)
    [turn] = episodes(tmp_path)
    assert turn["suite"] == UNASSIGNED
    assert turn["call_site"].endswith(
        "test_recorder_episode:"
        "test_an_episode_that_names_no_suite_is_unassigned_with_its_call_site"
    )


# -- nesting ------------------------------------------------------------------ #


@pytest.mark.usefixtures("on", "commit")
def test_two_levels_of_nesting_carry_their_parents_id(tmp_path: Path) -> None:
    client = wrapped(tmp_path, LOOKUP, REFUND, ANSWER)
    with episode(client, suite="support-agent", case=CASE) as outer:
        ask(client)
        with episode(client, suite="refunds", case={"order": "A1"}) as inner:
            ask(client)
        ask(client)
    assert outer.id is not None and inner.id is not None and outer.id != inner.id
    by_suite = {found["suite"]: found for found in episodes(tmp_path)}
    assert "episode" not in by_suite["support-agent"]
    assert by_suite["refunds"]["episode"] == outer.id
    assert [child["episode"] for child in calls(tmp_path)] == [
        outer.id,
        inner.id,
        outer.id,
    ]
    # The inner episode's steps are the outer's, where it closed.
    assert [step["actor"] for step in by_suite["refunds"]["response"]["steps"]] == [
        "model",
        "tool",
    ]
    assert [
        (step["actor"], step.get("tool"))
        for step in by_suite["support-agent"]["response"]["steps"]
    ] == [
        ("model", None),
        ("tool", "lookup"),
        ("model", None),
        ("tool", "refund"),
        ("model", None),
    ]
    # The outer setup names its direct children: one call's setup, and the
    # inner episode's own digest.
    call_digest = calls(tmp_path)[0]["setup_digest"]
    assert by_suite["support-agent"]["setup"]["child_setups"] == sorted(
        {call_digest, by_suite["refunds"]["setup_digest"]}
    )


# -- the setup ---------------------------------------------------------------- #


@pytest.mark.usefixtures("on", "commit")
def test_a_setup_given_by_hand_is_the_one_digested(tmp_path: Path) -> None:
    client = wrapped(tmp_path, ANSWER)
    by_hand = {"graph": "support-v3", "nodes": ["route", "answer"]}
    with episode(client, suite="by-hand", case=CASE, setup=by_hand):
        ask(client)
    with episode(client, suite="derived", case=CASE):
        ask(client)
    by_suite = {found["suite"]: found for found in episodes(tmp_path)}
    assert by_suite["by-hand"]["setup"] == by_hand
    assert by_suite["by-hand"]["setup_digest"] == setup_digest_of(by_hand)
    derived = by_suite["derived"]
    assert derived["setup"] == {
        "child_setups": [calls(tmp_path)[0]["setup_digest"]],
        "git_commit": "a" * 40,
    }
    assert derived["setup_digest"] == setup_digest_of(derived["setup"])
    assert derived["setup_digest"] != by_suite["by-hand"]["setup_digest"]


@pytest.mark.usefixtures("on")
def test_the_same_setup_and_children_digest_alike_and_a_commit_moves_it(
    tmp_path: Path, commit: list[str | None], clock: list[float]
) -> None:
    client = wrapped(tmp_path, LOOKUP, ANSWER, LOOKUP, ANSWER, LOOKUP, ANSWER)
    for suite in ("first", "second"):
        with episode(client, suite=suite, case=CASE):
            ask(client)
            ask(client)
    commit[0] = "b" * 40
    # The commit is read once until the next look at the switch; past the
    # interval, it is read again.
    clock[0] += recorder.DEFAULT_INTERVAL + 1
    with episode(client, suite="third", case=CASE):
        ask(client)
        ask(client)
    digest = {found["suite"]: found["setup_digest"] for found in episodes(tmp_path)}
    assert digest["first"] == digest["second"]
    assert digest["third"] != digest["first"]


@pytest.mark.usefixtures("on")
def test_the_commit_is_read_from_the_repository_as_a_run_reads_it(
    tmp_path: Path,
) -> None:
    git = ["git", "-C", str(tmp_path), "-c", "user.name=t", "-c", "user.email=t@t"]
    subprocess.run([*git, "init", "-q"], check=True)
    (tmp_path / ".gitignore").write_text(".digline/\n", encoding="utf-8")
    subprocess.run([*git, "add", ".gitignore"], check=True)
    subprocess.run([*git, "commit", "-q", "-m", "init"], check=True)
    head = subprocess.run(
        [*git, "rev-parse", "HEAD"], check=True, capture_output=True, text=True
    ).stdout.strip()
    client = wrapped(tmp_path, ANSWER)
    with episode(client, suite="support-agent", case=CASE):
        ask(client)
    [turn] = episodes(tmp_path)
    assert turn["setup"]["git_commit"] == head


# -- propagation: threads and processes --------------------------------------- #


@pytest.mark.usefixtures("on", "commit")
def test_a_call_in_a_pool_thread_without_attach_is_an_orphan(tmp_path: Path) -> None:
    client = wrapped(tmp_path, LOOKUP, ANSWER)
    with (
        episode(client, suite="support-agent", case=CASE) as ep,
        ThreadPoolExecutor(1) as pool,
    ):
        ask(client)
        pool.submit(ask, client).result()
    [turn] = episodes(tmp_path)
    first, orphan = calls(tmp_path)
    assert first["episode"] == ep.id
    assert "episode" not in orphan
    assert orphan["orphan"] is True
    assert "orphan" not in first
    # Attached to nothing: the episode's trajectory is its one child.
    assert [step["actor"] for step in turn["response"]["steps"]] == ["model", "tool"]
    assert counts(client)["orphan"] == 1


@pytest.mark.usefixtures("on", "commit")
def test_a_call_in_a_pool_thread_with_attach_is_a_child(tmp_path: Path) -> None:
    client = wrapped(tmp_path, LOOKUP, ANSWER)

    def attached(id: str | None) -> Any:  # noqa: A002
        with attach(id):
            return ask(client)

    with (
        episode(client, suite="support-agent", case=CASE) as ep,
        ThreadPoolExecutor(1) as pool,
    ):
        ask(client)
        pool.submit(attached, ep.id).result()
    [turn] = episodes(tmp_path)
    assert [child["episode"] for child in calls(tmp_path)] == [ep.id, ep.id]
    assert not any("orphan" in child for child in calls(tmp_path))
    assert [step["actor"] for step in turn["response"]["steps"]] == [
        "model",
        "tool",
        "model",
    ]
    assert counts(client)["orphan"] == 0


@pytest.mark.usefixtures("on", "commit")
def test_a_plain_thread_needs_attach_too(tmp_path: Path) -> None:
    client = wrapped(tmp_path, ANSWER)
    with episode(client, suite="support-agent", case=CASE) as ep:
        bare = threading.Thread(target=ask, args=(client,))
        bare.start()
        bare.join()

        def attached() -> None:
            with attach(ep.id):
                ask(client)

        joined = threading.Thread(target=attached)
        joined.start()
        joined.join()
    orphan, child = calls(tmp_path)
    assert "episode" not in orphan
    assert child["episode"] == ep.id
    assert counts(client)["orphan"] == 1


@pytest.mark.usefixtures("on", "commit")
def test_asyncio_to_thread_inherits_the_episode(tmp_path: Path) -> None:
    client = wrapped(tmp_path, ANSWER)

    async def turn() -> None:
        await asyncio.to_thread(ask, client)

    with episode(client, suite="support-agent", case=CASE) as ep:
        asyncio.run(turn())
    [child] = calls(tmp_path)
    assert child["episode"] == ep.id
    assert counts(client)["orphan"] == 0


def _in_a_spawned_process(root: str, id: str) -> None:  # noqa: A002
    """Run in a process started with `spawn`: a client of its own, attached
    to an episode opened in the parent by its id."""
    client = wrapped(Path(root), ANSWER)
    with attach(id):
        ask(client)


@pytest.mark.usefixtures("on", "commit")
def test_a_spawned_process_attaches_by_id(tmp_path: Path) -> None:
    client = wrapped(tmp_path, ANSWER)
    with episode(client, suite="support-agent", case=CASE) as ep:
        assert ep.id is not None
        ask(client)
        process = multiprocessing.get_context("spawn").Process(
            target=_in_a_spawned_process, args=(str(tmp_path), ep.id)
        )
        process.start()
        process.join(timeout=120)
    assert process.exitcode == 0
    children = calls(tmp_path)
    assert [child["episode"] for child in children] == [ep.id, ep.id]
    # Two processes, two subdirectories, joined by the id at the import.
    folders = {
        path.parent.name
        for path in (tmp_path / ".digline").glob("acme/recordings/*/*.json")
    }
    assert len(folders) == 2
    # The parent's trajectory holds what this process saw.
    [turn] = episodes(tmp_path)
    assert [step["actor"] for step in turn["response"]["steps"]] == ["model"]


# -- the episode never fails the application ---------------------------------- #


@pytest.mark.usefixtures("on", "commit")
def test_an_exception_inside_propagates_and_the_episode_is_written_interrupted(
    tmp_path: Path,
) -> None:
    client = wrapped(tmp_path, LOOKUP, ANSWER)
    raised = LookupError("order A1 not found")
    with (
        pytest.raises(LookupError) as caught,
        episode(client, suite="support-agent", case=CASE),
    ):
        ask(client)
        raise raised
    assert caught.value is raised
    [turn] = episodes(tmp_path)
    assert turn["interrupted"] is True
    assert [step["actor"] for step in turn["response"]["steps"]] == ["model", "tool"]
    assert recorder._CURRENT.get() is None  # pyright: ignore[reportPrivateUsage]
    assert recorder._OPEN == {}  # pyright: ignore[reportPrivateUsage]


@pytest.mark.usefixtures("on", "commit")
def test_a_case_json_cannot_carry_is_counted_and_the_block_runs(
    tmp_path: Path,
) -> None:
    client = wrapped(tmp_path, ANSWER)
    with episode(client, suite="support-agent", case={"when": object()}):
        ask(client)
    assert episodes(tmp_path) == []
    assert counts(client) == {
        "recorded": 1,
        "not_recorded": {"not JSON": 1},
        "orphan": 0,
        "noted": {},
    }


@pytest.mark.usefixtures("on", "commit")
def test_an_output_that_is_not_an_output_is_counted(tmp_path: Path) -> None:
    client = wrapped(tmp_path, ANSWER)
    with episode(client, suite="support-agent", case=CASE) as ep:
        ask(client)
        ep.output(42)
    assert episodes(tmp_path) == []
    assert counts(client)["not_recorded"] == {"output": 1}


@pytest.mark.usefixtures("on", "commit")
def test_a_call_inside_that_is_not_recorded_is_counted_on_the_episode(
    tmp_path: Path,
) -> None:
    httpx2 = importlib.import_module("httpx2")

    def handle(request: object) -> Any:
        return httpx2.Response(
            200, headers={"content-type": "text/event-stream"}, content=b""
        )

    streaming = wrap(
        importlib.import_module("anthropic").Anthropic(
            api_key="test",
            http_client=httpx2.Client(transport=httpx2.MockTransport(handle)),
        ),
        app="support",
        tenant="acme",
        root=tmp_path,
    )
    client = wrapped(tmp_path, ANSWER)
    with episode(client, suite="support-agent", case=CASE):
        ask(client)
        streaming.messages.create(
            model="claude-test", max_tokens=10, messages=QUESTION, stream=True
        )
    [turn] = episodes(tmp_path)
    assert turn["unrecorded_children"] == 1


@pytest.mark.usefixtures("on", "commit")
def test_over_the_ceiling_the_episode_keeps_no_text_and_no_steps(
    tmp_path: Path,
) -> None:
    client = wrapped(tmp_path, LOOKUP, ANSWER)
    with episode(client, suite="support-agent", case=CASE) as ep:
        ask(client)
        ep.output("x" * (MAX_RECORDED_CHARS + 1))
    [turn] = episodes(tmp_path)
    assert turn["response"]["oversize"] is True
    assert "output" not in turn["response"]
    assert "tool_calls" not in turn["response"]
    assert "steps" not in turn["response"]


@pytest.mark.usefixtures("on", "commit")
def test_a_call_outside_every_episode_is_no_orphan(tmp_path: Path) -> None:
    client = wrapped(tmp_path, ANSWER)
    ask(client)
    with episode(client, suite="support-agent", case=CASE):
        ask(client)
    ask(client)
    before, inside, after = calls(tmp_path)
    assert "orphan" not in before and "orphan" not in after
    assert "orphan" not in inside
    assert counts(client)["orphan"] == 0


def test_an_episode_needs_a_wrapped_client() -> None:
    with pytest.raises(RecorderStartError, match="wrap"):
        episode(object(), case=CASE)


# -- off ---------------------------------------------------------------------- #


@pytest.mark.usefixtures("off")
def test_off_an_episode_is_an_empty_context(tmp_path: Path) -> None:
    client = wrapped(tmp_path, ANSWER)
    with episode(client, suite="support-agent", case=CASE) as ep:
        with attach(ep.id):
            ask(client)
        ep.output("ignored")
    assert ep.id is None
    assert not (tmp_path / ".digline").exists()
    assert counts(client) == {
        "recorded": 0,
        "not_recorded": {},
        "orphan": 0,
        "noted": {},
    }


def test_off_an_episode_imports_nothing_of_digline_core() -> None:
    program = (
        "import sys, anthropic, httpx2\n"
        "import digline.recorder as r\n"
        "body = " + repr(ANSWER) + "\n"
        "http = httpx2.Client(transport=httpx2.MockTransport("
        "lambda q: httpx2.Response(200, json=body)))\n"
        "c = r.wrap(anthropic.Anthropic(api_key='t', http_client=http), "
        "app='a', tenant='acme')\n"
        "with r.episode(c, suite='s', case={'m': 'q'}) as ep:\n"
        "    with r.attach(ep.id):\n"
        "        c.messages.create(model='m', max_tokens=5, messages=[], suite='s')\n"
        "    ep.output('done')\n"
        "print(sorted(m for m in sys.modules if m.startswith('digline')))\n"
    )
    done = subprocess.run(
        [sys.executable, "-I", "-c", program],
        capture_output=True,
        text=True,
        check=False,
        env={"PATH": "/usr/bin:/bin"},
    )
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == "['digline', 'digline.recorder']"
