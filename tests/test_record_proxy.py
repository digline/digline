"""`digline record proxy`: the providers' own SDKs pointed at it, a fake
upstream in this process behind it, and what it records read by `digline
record import`. (ADR 0062 §3)

Nothing leaves `127.0.0.1`. The SDKs are the real ones, so a header or a path
the proxy passed on wrong is refused, or read wrong, by the SDK itself.

What is held here:

- OpenAI and Anthropic, whole and streamed, recorded as the recorder in
  process records them, and electable at the import;
- the suite from `X-Digline-Suite` or from `/suite/<name>/`, neither passed
  on; no suite is `_unassigned`, with the SDK's `User-Agent` and the path;
- an episode from `X-Digline-Episode`, written once it is idle, with the case
  `X-Digline-Case` gives or its first call's, and the import says which;
- a stream the application closes before its end is `stream abandoned`;
- off, nothing is written; a 500 passes on as it came and is not recorded; an
  upstream that does not answer is a 504 that says so; a route no plugin is
  installed for is a 502 that names the package;
- an endpoint that answers in OpenAI's shape, at another path, as Gemini's
  OpenAI-compatible one does, is read by OpenAI's map;
- the latency the proxy adds, measured and printed.
"""

from __future__ import annotations

import hashlib
import http.client
import json
import os
import signal
import statistics
import subprocess
import sys
import threading
import time
from collections.abc import Iterator, Mapping
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest
from tests.test_recorder_import import argv, suite_file
from tests.test_recorder_streaming import (
    ANTHROPIC_WHOLE,
    OPENAI_WHOLE,
    QUESTION,
    anthropic_events,
    openai_chunk,
    sse,
)

from digline import recorder
from digline.cli.main import main
from digline.core.recording import input_of
from digline.host import answer_id, recorder_status
from digline.host.proxy import Proxy, start_proxy
from digline.recorder import RecordingMap, RecordingWire

SDKS = ("anthropic", "openai", "httpx2")

#: What Gemini's OpenAI-compatible endpoint answers, in its shape: no `id`,
#: no `system_fingerprint`. Not read from the service: the shape a compatible
#: endpoint may answer in, fewer fields than OpenAI's.
GEMINI_WHOLE: dict[str, object] = {
    "choices": [
        {
            "finish_reason": "stop",
            "index": 0,
            "message": {"content": "Paris", "role": "assistant"},
        }
    ],
    "created": 1730000000,
    "model": "gemini-2.0-flash",
    "object": "chat.completion",
    "usage": {"completion_tokens": 1, "prompt_tokens": 5, "total_tokens": 6},
}


@pytest.fixture(autouse=True)
def no_sdk_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """What would point an SDK elsewhere, or give it another key."""
    for name in (
        "ANTHROPIC_AUTH_TOKEN",
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_BASE_URL",
        "OPENAI_API_KEY",
        "OPENAI_BASE_URL",
    ):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture(autouse=True, scope="module")
def the_sdks_leave_with_this_module() -> Iterator[None]:
    before = set(sys.modules)
    yield
    for name in set(sys.modules) - before:
        if name.split(".", 1)[0] in SDKS:
            del sys.modules[name]


class Upstream:
    """OpenAI and Anthropic, faked: each request kept, each reply by the
    request's `model`: `error` a 500, `sleep` too late, `slow` a stream that
    takes its time."""

    def __init__(self) -> None:
        self.seen: list[tuple[str, dict[str, str]]] = []
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
                pass

            def do_GET(self) -> None:  # noqa: N802
                owner.seen.append((self.path, dict(self.headers.items())))
                self._json(200, {"object": "list", "data": []})

            def do_POST(self) -> None:  # noqa: N802
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                owner.seen.append(
                    (self.path, {k.lower(): v for k, v in self.headers.items()})
                )
                model = body.get("model")
                if model == "error":
                    self._json(500, {"type": "error", "error": {"message": "boom"}})
                    return
                if model == "sleep":
                    time.sleep(1.5)
                anthropic = self.path.endswith("/v1/messages")
                gemini = "/v1beta/openai/" in self.path
                if not body.get("stream"):
                    whole = (
                        ANTHROPIC_WHOLE
                        if anthropic
                        else GEMINI_WHOLE
                        if gemini
                        else OPENAI_WHOLE
                    )
                    self._json(200, whole)
                    return
                if anthropic:
                    events = anthropic_events()
                else:
                    chunks: list[tuple[str | None, object]] = [
                        (
                            None,
                            openai_chunk({"role": "assistant", "content": "Par"}, None),
                        ),
                        *[(None, openai_chunk({"content": ""}, None))]
                        * (20 if model == "slow" else 0),
                        (None, openai_chunk({"content": "is"}, None)),
                        (None, openai_chunk({}, "stop")),
                    ]
                    if body.get("stream_options", {}).get("include_usage"):
                        usage: dict[str, object] = {
                            **openai_chunk({}, None),
                            "choices": [],
                        }
                        usage["usage"] = OPENAI_WHOLE["usage"]
                        chunks.append((None, usage))
                    chunks.append((None, "[DONE]"))
                    events = sse(chunks)
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                for line in events.splitlines(keepends=True):
                    self.wfile.write(line)
                    self.wfile.flush()
                    if model == "slow":
                        time.sleep(0.05)

            def _json(self, status: int, payload: object) -> None:
                data = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    @property
    def address(self) -> str:
        return f"http://127.0.0.1:{self.port}"


@pytest.fixture
def upstream() -> Iterator[Upstream]:
    fake = Upstream()
    yield fake
    fake.server.shutdown()
    fake.server.server_close()


def proxying(root: Path, upstream: Upstream, **extra: Any) -> Proxy:
    return start_proxy(
        root=root,
        tenant="acme",
        app="support",
        port=0,
        upstream=extra.pop(
            "routes",
            [f"openai={upstream.address}/v1", f"anthropic={upstream.address}"],
        ),
        episode_idle=extra.pop("episode_idle", 0.2),
        timeout=extra.pop("timeout", 5.0),
        **extra,
    )


@pytest.fixture
def proxy(
    tmp_path: Path, upstream: Upstream, monkeypatch: pytest.MonkeyPatch
) -> Iterator[Proxy]:
    monkeypatch.setenv(recorder.ENVIRONMENT_VARIABLE, "1")
    running = proxying(tmp_path, upstream)
    yield running
    running.stop()


def an_openai(base: str, **headers: str) -> Any:
    import openai

    return openai.OpenAI(
        api_key="sk-test", base_url=base, default_headers=headers, max_retries=0
    )


def an_anthropic(base: str, **headers: str) -> Any:
    import anthropic

    return anthropic.Anthropic(
        api_key="test", base_url=base, default_headers=headers, max_retries=0
    )


def recordings(root: Path, at_least: int = 1) -> list[dict[str, Any]]:
    """The recordings, once there are `at_least`: each is written once its
    reply has been passed on, so after the call has returned."""
    deadline = time.monotonic() + 5
    while True:
        found = [
            json.loads(path.read_text(encoding="utf-8"))
            for path in sorted((root / ".digline").glob("*/recordings/*/*.json"))
        ]
        if len(found) >= at_least or time.monotonic() > deadline:
            return found
        time.sleep(0.02)


def counted(root: Path) -> dict[str, Any]:
    [tenant] = recorder_status(root, "acme")
    return {suite.suite: dict(suite.not_recorded) for suite in tenant.suites}


SUITE = {"X-Digline-Suite": "triage"}


# -- OpenAI and Anthropic, whole and streamed ---------------------------------- #


def test_openai_is_recorded_and_the_import_can_write_it(
    proxy: Proxy, upstream: Upstream, tmp_path: Path
) -> None:
    client = an_openai(f"{proxy.address}/v1", **SUITE)
    reply = client.chat.completions.create(model="gpt-test", messages=QUESTION)
    assert reply.choices[0].message.content == "Paris"
    [written] = recordings(tmp_path)
    assert written["suite"] == "triage" and written["app"] == "support"
    assert written["case"] == {"messages": QUESTION}
    assert written["response"]["output"] == "Paris"
    assert written["response"]["input"] == input_of(QUESTION)
    [(path, headers)] = upstream.seen
    assert path == "/v1/chat/completions"
    assert not [key for key in headers if key.startswith("x-digline-")]
    assert headers["authorization"] == "Bearer sk-test"
    suite_file(tmp_path)
    good = answer_id({"messages": QUESTION}, "Paris")
    assert main(argv(tmp_path, "--good", good, "--by", "Ada")) == 0


def test_openai_streamed_is_recorded_as_the_whole_reply(
    proxy: Proxy, tmp_path: Path
) -> None:
    client = an_openai(f"{proxy.address}/v1", **SUITE)
    stream = client.chat.completions.create(
        model="gpt-test",
        messages=QUESTION,
        stream=True,
        stream_options={"include_usage": True},
    )
    text = "".join(c.choices[0].delta.content or "" for c in stream if c.choices)
    assert text == "Paris"
    [written] = recordings(tmp_path)
    assert written["response"]["output"] == "Paris"
    assert written["response"]["usage"] == {"input_tokens": 12, "output_tokens": 3}


def test_anthropic_whole_and_streamed_are_recorded(
    proxy: Proxy, upstream: Upstream, tmp_path: Path
) -> None:
    client = an_anthropic(proxy.address, **SUITE)
    reply = client.messages.create(
        model="claude-test", max_tokens=10, messages=QUESTION
    )
    assert reply.content[0].text == "Paris"
    events = list(
        client.messages.create(
            model="claude-test", max_tokens=10, messages=QUESTION, stream=True
        )
    )
    assert events[-1].type == "message_stop"
    whole, streamed = recordings(tmp_path, 2)
    assert whole["response"]["output"] == streamed["response"]["output"] == "Paris"
    assert whole["setup_digest"] == streamed["setup_digest"]
    assert [path for path, _ in upstream.seen] == ["/v1/messages", "/v1/messages"]
    # Anthropic's SDK sends its key as a bearer, as OpenAI's does: the route
    # is what told the two apart, and the key went on as it was sent.
    assert upstream.seen[0][1]["authorization"] == "Bearer test"
    assert "anthropic-version" in upstream.seen[0][1]
    suite_file(tmp_path)
    good = answer_id({"messages": QUESTION}, "Paris")
    assert main(argv(tmp_path, "--good", good, "--by", "Ada")) == 0


# -- the suite --------------------------------------------------------------- #


def test_the_suite_in_the_path_is_taken_off_before_the_call_goes_on(
    proxy: Proxy, upstream: Upstream, tmp_path: Path
) -> None:
    an_openai(f"{proxy.address}/suite/triage/v1").chat.completions.create(
        model="gpt-test", messages=QUESTION
    )
    [written] = recordings(tmp_path)
    assert written["suite"] == "triage"
    assert upstream.seen[0][0] == "/v1/chat/completions"


def test_no_suite_is_unassigned_with_the_sdk_and_the_path(
    proxy: Proxy, tmp_path: Path
) -> None:
    an_openai(f"{proxy.address}/v1").chat.completions.create(
        model="gpt-test", messages=QUESTION
    )
    [written] = recordings(tmp_path)
    assert written["suite"] == recorder.UNASSIGNED
    assert written["call_site"].startswith("OpenAI/Python ")
    assert written["call_site"].endswith(" /v1/chat/completions")


# -- an episode off the wire ------------------------------------------------- #


def a_turn(proxy: Proxy, **headers: str) -> None:
    client = an_openai(f"{proxy.address}/v1", **SUITE, **headers)
    for _ in range(2):
        client.chat.completions.create(model="gpt-test", messages=QUESTION)


def the_episode(root: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    found = recordings(root, 3)
    [episode] = [r for r in found if "id" in r]
    return episode, [r for r in found if "id" not in r]


def test_an_episode_is_written_once_idle_with_the_case_it_was_given(
    proxy: Proxy, tmp_path: Path
) -> None:
    a_turn(
        proxy, **{"X-Digline-Episode": "turn-1", "X-Digline-Case": '{"order": "A1"}'}
    )
    episode, calls = the_episode(tmp_path)
    expected = hashlib.sha256(b"turn-1").hexdigest()[:32]
    assert episode["id"] == expected
    assert {call["episode"] for call in calls} == {expected}
    assert episode["case"] == {"order": "A1"}
    assert "case_from_first_call" not in episode
    assert "interrupted" not in episode
    assert episode["response"]["output"] == "Paris"
    assert [s["actor"] for s in episode["response"]["steps"]] == ["model", "model"]


def test_an_episode_with_no_case_takes_its_first_calls_and_the_import_says_so(
    proxy: Proxy, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    a_turn(proxy, **{"X-Digline-Episode": "turn-2"})
    episode, _ = the_episode(tmp_path)
    assert episode["case"] == {"messages": QUESTION}
    assert episode["case_from_first_call"] is True
    suite_file(tmp_path)
    assert main(argv(tmp_path)) == 0
    assert "(case from the first call)" in capsys.readouterr().out


def test_a_stream_closed_before_its_end_is_abandoned_and_not_recorded(
    tmp_path: Path, upstream: Upstream, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(recorder.ENVIRONMENT_VARIABLE, "1")
    running = proxying(tmp_path, upstream)
    try:
        stream = an_openai(f"{running.address}/v1", **SUITE).chat.completions.create(
            model="slow", messages=QUESTION, stream=True
        )
        next(iter(stream))
        stream.close()
        time.sleep(0.5)
    finally:
        running.stop()
    assert recordings(tmp_path, 0) == []
    assert counted(tmp_path) == {"triage": {"stream abandoned": 1}}


# -- what passes on, and what is refused ------------------------------------- #


def test_off_the_call_passes_and_nothing_is_written(
    tmp_path: Path, upstream: Upstream, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(recorder.ENVIRONMENT_VARIABLE, raising=False)
    running = proxying(tmp_path, upstream)
    try:
        assert not running.recorder.on()
        reply = an_openai(f"{running.address}/v1", **SUITE).chat.completions.create(
            model="gpt-test", messages=QUESTION
        )
        assert reply.choices[0].message.content == "Paris"
    finally:
        running.stop()
    assert not (tmp_path / ".digline").exists()


def test_an_upstream_error_passes_on_as_it_came_and_is_not_recorded(
    proxy: Proxy, tmp_path: Path
) -> None:
    import openai

    with pytest.raises(openai.InternalServerError) as raised:
        an_openai(f"{proxy.address}/v1", **SUITE).chat.completions.create(
            model="error", messages=QUESTION
        )
    assert raised.value.status_code == 500
    assert raised.value.body == {"message": "boom"}
    proxy.stop()
    assert recordings(tmp_path, 0) == []
    # Not read either: an error is not a call that ended, so it is not
    # counted as one the map could not read.
    assert counted(tmp_path) == {}


def test_an_upstream_that_does_not_answer_is_a_504_that_says_so(
    tmp_path: Path, upstream: Upstream, monkeypatch: pytest.MonkeyPatch
) -> None:
    import openai

    monkeypatch.setenv(recorder.ENVIRONMENT_VARIABLE, "1")
    running = proxying(tmp_path, upstream, timeout=0.3)
    try:
        with pytest.raises(openai.APIStatusError) as raised:
            an_openai(f"{running.address}/v1", **SUITE).chat.completions.create(
                model="sleep", messages=QUESTION
            )
    finally:
        running.stop()
    assert raised.value.status_code == 504
    assert "did not answer within 0.3 seconds" in str(raised.value)


def test_a_route_with_no_plugin_is_a_502_that_names_the_package(
    tmp_path: Path, upstream: Upstream
) -> None:
    running = start_proxy(root=tmp_path, tenant="acme", app="support", port=0, wires={})
    try:
        connection = http.client.HTTPConnection("127.0.0.1", running.port)
        connection.request("POST", "/v1/chat/completions", body=b"{}")
        reply = connection.getresponse()
        message = json.loads(reply.read())["error"]["message"]
    finally:
        running.stop()
    assert reply.status == 502
    assert "digline-openai" in message and "digline-anthropic" in message


def test_a_route_no_plugin_reads_is_forwarded_and_not_recorded(
    proxy: Proxy, upstream: Upstream, tmp_path: Path
) -> None:
    models = an_openai(f"{proxy.address}/v1", **SUITE).models.list()
    assert list(models) == []
    assert upstream.seen[0][0] == "/v1/models"
    assert recordings(tmp_path, 0) == []


class Elsewhere:
    """A plugin's reader whose own address is the fake upstream's, under a
    path of its own, so a test can see where a call went with no
    `--upstream`."""

    def __init__(self, wire: RecordingWire, upstream: str) -> None:
        self._wire = wire
        self.upstream = upstream
        self.map: RecordingMap = wire.map
        self.base = wire.base

    def matches(self, path: str) -> bool:
        return self._wire.matches(path)

    def claims(self, headers: Mapping[str, str]) -> bool:
        return self._wire.claims(headers)

    def reply(self, raw: object) -> Any:
        return self._wire.reply(raw)

    def event(self, raw: object) -> Any:
        return self._wire.event(raw)

    def load(self) -> None:
        self._wire.load()


def test_with_no_upstream_a_call_goes_where_its_sdks_headers_say(
    tmp_path: Path, upstream: Upstream
) -> None:
    """Both SDKs send their key as a bearer: Anthropic's call is told by its
    `anthropic-version`, and never sent to OpenAI's address."""
    from digline_anthropic.recording import WIRE as ANTHROPIC
    from digline_openai.recording import WIRE as OPENAI

    running = start_proxy(
        root=tmp_path,
        tenant="acme",
        app="support",
        port=0,
        wires={
            "anthropic": Elsewhere(ANTHROPIC, f"{upstream.address}/a"),
            "openai": Elsewhere(OPENAI, f"{upstream.address}/o/v1"),
        },
    )
    try:
        an_anthropic(running.address).messages.create(
            model="claude-test", max_tokens=10, messages=QUESTION
        )
        an_openai(f"{running.address}/v1").chat.completions.create(
            model="gpt-test", messages=QUESTION
        )
    finally:
        running.stop()
    assert [path for path, _ in upstream.seen] == [
        "/a/v1/messages",
        "/o/v1/chat/completions",
    ]


# -- a compatible endpoint ------------------------------------------------------ #


def test_an_endpoint_in_openais_shape_at_another_path_is_read(
    tmp_path: Path, upstream: Upstream, monkeypatch: pytest.MonkeyPatch
) -> None:
    """As Gemini's OpenAI-compatible endpoint is reached: its own base URL,
    `/v1beta/openai`, and a reply with fewer fields than OpenAI's. The shape
    is a fake one; the service itself was not called."""
    monkeypatch.setenv(recorder.ENVIRONMENT_VARIABLE, "1")
    running = proxying(
        tmp_path, upstream, routes=[f"openai={upstream.address}/v1beta/openai"]
    )
    try:
        an_openai(f"{running.address}/v1", **SUITE).chat.completions.create(
            model="gemini-2.0-flash", messages=QUESTION
        )
        [written] = recordings(tmp_path)
    finally:
        running.stop()
    assert upstream.seen[0][0] == "/v1beta/openai/chat/completions"
    assert written["response"]["output"] == "Paris"
    assert written["response"]["usage"] == {"input_tokens": 5, "output_tokens": 1}


# -- the latency ------------------------------------------------------------- #


def test_the_latency_the_proxy_adds_is_measured(
    proxy: Proxy, upstream: Upstream
) -> None:
    body = json.dumps({"model": "gpt-test", "messages": QUESTION}).encode()
    headers = {"Content-Type": "application/json", "Authorization": "Bearer sk"}

    def once(port: int, extra: dict[str, str]) -> float:
        connection = http.client.HTTPConnection("127.0.0.1", port)
        started = time.perf_counter()
        connection.request("POST", "/v1/chat/completions", body, {**headers, **extra})
        connection.getresponse().read()
        elapsed = time.perf_counter() - started
        connection.close()
        return elapsed * 1000.0

    direct: list[float] = []
    through: list[float] = []
    for _ in range(100):
        direct.append(once(upstream.port, {}))
        through.append(once(proxy.port, SUITE))
    added = statistics.median(through) - statistics.median(direct)
    print(f"\nthe proxy adds {added:.3f} ms, median of 100 single calls")
    assert added < 5.0


# -- the command ------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("on", "stop"),
    [(False, signal.SIGINT), (True, signal.SIGTERM)],
    ids=["off-interrupted", "on-terminated"],
)
def test_the_command_says_where_it_listens_and_how_to_point_an_sdk(
    tmp_path: Path, on: bool, stop: signal.Signals
) -> None:
    environment = {
        key: value
        for key, value in os.environ.items()
        if key != recorder.ENVIRONMENT_VARIABLE
    }
    if on:
        environment[recorder.ENVIRONMENT_VARIABLE] = "1"
    started = subprocess.Popen(
        [
            sys.executable,
            "-u",
            "-m",
            "digline.cli",
            "record",
            "proxy",
            "--tenant",
            "acme",
            "--root",
            str(tmp_path),
            "--port",
            "0",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=environment,
    )
    assert started.stdout is not None
    lines = [started.stdout.readline().rstrip("\n") for _ in range(9)]
    started.send_signal(stop)
    out, _ = started.communicate(timeout=10)
    assert lines[0].startswith("digline record proxy: listening on http://127.0.0.1:")
    address = lines[0].rsplit(" ", 1)[1]
    assert lines[1] == "  tenant:     acme, app proxy"
    if on:
        assert lines[3].startswith(
            "  recording:  on, from DIGLINE_RECORD=1: sample 1, ceiling "
        )
    else:
        assert lines[3] == (
            "  recording:  off for this tenant: calls are forwarded, none is written"
        )
    assert f"    ANTHROPIC_BASE_URL={address}" in lines
    assert f"    OPENAI_BASE_URL={address}/v1" in lines
    assert out.rstrip("\n").endswith(
        "digline record proxy: stopped; open episodes and the counts are written"
    )
    assert started.returncode == 0


@pytest.mark.parametrize(
    ("extra", "said"),
    [
        ((), "needs --tenant"),
        (("--tenant", "acme", "--upstream", "nowhere=http://x"), "no plugin reads"),
        (("--tenant", "acme", "--upstream", "openai"), "write it as ROUTE=URL"),
        (("--app", "a"), "belongs to `digline record proxy`"),
    ],
)
def test_the_command_refuses_what_it_cannot_do(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    extra: tuple[str, ...],
    said: str,
) -> None:
    action = "status" if extra[:1] == ("--app",) else "proxy"
    assert main(["record", action, "--root", str(tmp_path), *extra]) == 64
    assert said in capsys.readouterr().err
