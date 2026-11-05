"""`extra_body`, recorded in process, has the setup the same call has off the
wire. (ADR 0062 §2)

In process the maps read the SDK call's keyword arguments, where `extra_body`
is a keyword of its own. On the wire the SDK has already merged its keys into
the body, at the top level, and that body is what `digline record proxy` and
a recorder in another language read. So the maps merge it the same way, and
the same call records one setup digest whichever door it went through.

Each SDK is the real one, with a transport that keeps the body it sends: the
wire's side is what the SDK put on the wire, not what this test thinks it
would.
"""

from __future__ import annotations

import importlib
import json
import sys
from collections.abc import Iterator
from typing import Any

import pytest

from digline.core.recording import setup_digest_of
from digline.recorder import RecordingMap

EXTRA = {"reasoning_effort": "low", "top_k": 5}
QUESTION = [{"role": "user", "content": "Capital?"}]


SDKS = ("anthropic", "openai", "httpx2")


@pytest.fixture(autouse=True, scope="module")
def the_sdks_leave_with_this_module() -> Iterator[None]:
    """The SDKs imported here, gone after: the plugins' own tests hold that
    nothing imports them before a call."""
    before = set(sys.modules)
    yield
    for name in set(sys.modules) - before:
        if name.split(".", 1)[0] in SDKS:
            del sys.modules[name]


def sent(reply: dict[str, object]) -> tuple[list[dict[str, Any]], Any]:
    """A client of the SDKs' own HTTP library that answers `reply` and keeps
    each body it was sent."""
    httpx2 = importlib.import_module("httpx2")
    bodies: list[dict[str, Any]] = []

    def handle(request: Any) -> Any:
        bodies.append(json.loads(request.content))
        return httpx2.Response(200, json=reply)

    return bodies, httpx2.Client(transport=httpx2.MockTransport(handle))


def digest(
    mapped: RecordingMap, request: dict[str, Any]
) -> tuple[str, dict[str, object]]:
    _, setup = mapped.split(request)
    return setup_digest_of(setup), setup


@pytest.mark.parametrize("provider", ["openai", "anthropic"])
def test_a_call_with_extra_body_has_one_setup_in_process_and_off_the_wire(
    provider: str,
) -> None:
    if provider == "openai":
        openai: Any = importlib.import_module("openai")

        from digline_openai.recording import MAP

        bodies, http = sent(
            {
                "id": "c",
                "object": "chat.completion",
                "created": 1,
                "model": "gpt-test",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": "Paris"},
                    }
                ],
            }
        )
        kwargs: dict[str, Any] = {
            "model": "gpt-test",
            "messages": QUESTION,
            "max_tokens": 16,
            "extra_body": EXTRA,
        }
        openai.OpenAI(api_key="k", http_client=http).chat.completions.create(**kwargs)
    else:
        anthropic: Any = importlib.import_module("anthropic")

        from digline_anthropic.recording import MAP

        bodies, http = sent(
            {
                "id": "m",
                "type": "message",
                "role": "assistant",
                "model": "claude-test",
                "content": [{"type": "text", "text": "Paris"}],
                "stop_reason": "end_turn",
                "stop_sequence": None,
                "usage": {"input_tokens": 1, "output_tokens": 1},
            }
        )
        kwargs = {
            "model": "claude-test",
            "messages": QUESTION,
            "max_tokens": 16,
            "extra_body": EXTRA,
        }
        anthropic.Anthropic(api_key="k", http_client=http).messages.create(**kwargs)

    [wire] = bodies
    # What the SDK sent: the keys merged at the top level, no `extra_body`.
    assert "extra_body" not in wire and wire["top_k"] == 5
    in_process, setup = digest(MAP, kwargs)
    off_the_wire, _ = digest(MAP, wire)
    assert in_process == off_the_wire
    assert "extra_body" not in setup
    assert setup["reasoning_effort"] == "low"
    # And the case is the same from either side.
    assert MAP.split(kwargs)[0] == MAP.split(wire)[0]


def test_extra_body_takes_the_place_of_a_key_it_names() -> None:
    """A key in both the keywords and `extra_body` is the extra one on the
    wire, measured with OpenAI's SDK, and so in the setup."""
    openai: Any = importlib.import_module("openai")

    from digline_openai.recording import MAP

    bodies, http = sent(
        {
            "id": "c",
            "object": "chat.completion",
            "created": 1,
            "model": "b",
            "choices": [],
        }
    )
    kwargs: dict[str, Any] = {
        "model": "a",
        "messages": QUESTION,
        "extra_body": {"model": "b"},
    }
    openai.OpenAI(api_key="k", http_client=http).chat.completions.create(**kwargs)
    [wire] = bodies
    assert wire["model"] == "b"
    assert MAP.split(kwargs)[1]["model"] == "b"
    assert MAP.split({**kwargs, "extra_body": None})[1]["model"] == "a"
