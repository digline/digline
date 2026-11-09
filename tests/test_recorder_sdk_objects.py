"""An agent that hands the model's reply back as the SDK gave it. (P-1588)

The loop most agents on Anthropic's SDK write puts `reply.content`, a list of
the SDK's pydantic models, into the next call's messages. The SDK sends each
model as data; the recorder's map wrote it as it came, the recording could not
hold it, and the call was counted `not JSON` and not recorded. Inside an
episode the turn was then written with one model step where it took two.

What is held here, on Anthropic's own SDK with no network:

- the loop with `reply.content` as it is records both calls, and the turn's
  two model steps, with no `not JSON` among the counts or in the status;
- the case holds the messages as the SDK sends them, the same as the loop
  that dumps its blocks itself;
- a value that is still not data is declined, counted and said by the key it
  sits at and its type, and a model whose dump raises is named the same way.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from tests.test_recorder_episode import (
    ANSWER,
    LOOKUP,
    calls,
    counts,
    episodes,
    wrapped,
)

from digline.cli.main import main
from digline.recorder import RecordedClient, episode

SDKS = ("anthropic", "httpx2")
TICKET = "Where is my order A1?"


@pytest.fixture(autouse=True, scope="module")
def the_sdks_leave_with_this_module() -> Iterator[None]:
    before = set(sys.modules)
    yield
    for name in set(sys.modules) - before:
        if name.split(".", 1)[0] in SDKS:
            del sys.modules[name]


@pytest.fixture(autouse=True)
def on(monkeypatch: pytest.MonkeyPatch) -> None:
    from digline import recorder

    monkeypatch.setenv(recorder.ENVIRONMENT_VARIABLE, "1")


def turn(client: RecordedClient, *, dump: bool) -> str:
    """The story's loop: ask, run the tool, send its result back, ask again.
    With `dump`, the reply goes back as `block.to_dict()`; without, as the
    SDK gave it."""
    with episode(client, suite="support", case={"ticket": TICKET}) as ep:
        messages: list[dict[str, Any]] = [{"role": "user", "content": TICKET}]
        while True:
            reply = client.messages.create(
                model="claude-test",
                max_tokens=50,
                messages=messages,
                suite="support",
            )
            if reply.stop_reason != "tool_use":
                answer = reply.content[0].text
                ep.output(answer)
                return answer
            content = (
                [block.to_dict() for block in reply.content] if dump else reply.content
            )
            messages.append({"role": "assistant", "content": content})
            results = [
                {"type": "tool_result", "tool_use_id": block.id, "content": "shipped"}
                for block in reply.content
                if block.type == "tool_use"
            ]
            messages.append({"role": "user", "content": results})


def test_the_sdks_objects_are_recorded_as_the_sdk_sends_them(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    client = wrapped(tmp_path, LOOKUP, ANSWER)
    turn(client, dump=False)
    assert len(calls(tmp_path)) == 2
    [recorded] = episodes(tmp_path)
    assert [step["actor"] for step in recorded["response"]["steps"]] == [
        "model",
        "tool",
        "model",
    ]
    assert not any("not JSON" in str(key) for key in counts(client))
    capsys.readouterr()
    assert main(["record", "status", "--tenant", "acme", "--root", str(tmp_path)]) == 0
    status = capsys.readouterr().out
    assert "1 episode" in status
    assert "not JSON" not in status
    assert "not recorded" not in status


def test_the_case_is_the_same_as_the_loop_that_dumps_its_blocks(
    tmp_path: Path,
) -> None:
    turn(wrapped(tmp_path / "as-given", LOOKUP, ANSWER), dump=False)
    turn(wrapped(tmp_path / "dumped", LOOKUP, ANSWER), dump=True)
    given = [call["case"] for call in calls(tmp_path / "as-given")]
    dumped = [call["case"] for call in calls(tmp_path / "dumped")]
    assert given == dumped
    assert given[1]["messages"][1]["content"][0]["type"] == "tool_use"


class Opaque:
    """Something an application might put in a message by mistake. The SDK
    refuses to send it, so through a client the call fails before the
    recorder sees it: the map's refusal is held on its own."""


def test_a_value_that_is_not_data_is_named_by_its_key_and_type() -> None:
    from digline_anthropic.recording import MAP

    message = {"role": "user", "content": [{"type": "text", "text": Opaque()}]}
    found = MAP.refusal({"model": "claude-test", "messages": [message]})
    assert found is not None
    assert found.reason == "messages[0].content[0].text holds a Opaque"
    assert "not JSON" not in found.reason
    assert found.said == (
        "messages.create: messages[0].content[0].text holds a Opaque, which a "
        "recording cannot hold as data; the call was made, and not recorded"
    )


def test_a_model_whose_dump_raises_is_named_where_it_sits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from anthropic.types import TextBlock

    from digline_anthropic.recording import MAP

    block = TextBlock(type="text", text="hello", citations=None)

    def refuses(self: object, **_: object) -> object:
        raise ValueError("no dump")

    monkeypatch.setattr(TextBlock, "model_dump", refuses)
    found = MAP.refusal(
        {
            "model": "claude-test",
            "messages": [{"role": "assistant", "content": [block]}],
        }
    )
    assert found is not None
    assert found.reason == (
        "messages[0].content[0] holds a TextBlock whose dump raised ValueError"
    )


def test_a_request_of_data_is_not_declined() -> None:
    from digline_anthropic.recording import MAP

    request = {
        "model": "claude-test",
        "messages": [{"role": "user", "content": "hi"}],
        "stop_sequences": ("END",),
    }
    assert MAP.refusal(request) is None
    _, setup = MAP.split(request)
    assert setup["stop_sequences"] == ["END"]
