"""`digline record proxy`, PR-P2: Bedrock signed again, the steps of an agent
read off the wire, and the calls that named no suite imported. (ADR 0062 §3)

Nothing leaves `127.0.0.1`. The SDKs are the real ones, boto3 among them: a
signature, a path or an event stream the proxy passed on wrong is refused, or
read wrong, by the SDK itself.

What is held here:

- Bedrock's `converse` and `converse-stream`, sent by boto3 to the proxy,
  signed again with the proxy's own credentials and region, and recorded with
  the case and the setup digest the recorder in process gives the same call;
- the steps of an agent of three calls, on all three providers: a tool step is
  closed by the result the next call carries, with the status the provider
  carries; the places, tools and arguments are those the same agent recorded
  in process gives, whose results say `not_reported`;
- a result is never put on a step it may not answer;
- a call that named no suite, imported with `--from _unassigned`, shows the
  SDK and the path where it was made.
"""

from __future__ import annotations

import binascii
import json
import sys
import threading
import time
from collections.abc import Callable, Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, cast

import pytest
from tests.test_record_proxy import (
    QUESTION,
    SDKS,
    an_anthropic,
    an_openai,
    recordings,
)
from tests.test_recorder_import import argv, suite_file

from digline import recorder
from digline.cli.main import main
from digline.host.proxy import Proxy, start_proxy
from digline.recorder import episode, wrap

#: The model id, with the colon the SDK percent-encodes in the path.
MODEL = "anthropic.claude-test-v1:0"

#: What each tool answers in the fake agent, and which one fails.
RESULTS = {"lookup": "shipped", "refund": "refused: past the window"}
FAILS = "refund"

CASE = {"order": "A1"}


@pytest.fixture(autouse=True, scope="module")
def the_sdks_leave_with_this_module() -> Iterator[None]:
    """OpenAI's and Anthropic's SDKs, imported here, gone after: the plugins'
    own tests hold that nothing imports them before a call."""
    before = set(sys.modules)
    yield
    for name in set(sys.modules) - before:
        if name.split(".", 1)[0] in SDKS:
            del sys.modules[name]


@pytest.fixture(autouse=True)
def aws(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """The proxy's own credentials and region, and no file of this
    machine's: what boto3 would find here, set."""
    for name in (
        "AWS_PROFILE",
        "AWS_SESSION_TOKEN",
        "AWS_BEARER_TOKEN_BEDROCK",
        "AWS_ENDPOINT_URL",
        "AWS_ENDPOINT_URL_BEDROCK_RUNTIME",
        "OPENAI_BASE_URL",
        "ANTHROPIC_BASE_URL",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIDPROXY")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "proxy-secret")
    monkeypatch.setenv("AWS_REGION", "us-west-2")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-west-2")
    monkeypatch.setenv("AWS_CONFIG_FILE", str(tmp_path / "no-config"))
    monkeypatch.setenv("AWS_SHARED_CREDENTIALS_FILE", str(tmp_path / "no-credentials"))
    monkeypatch.setenv(recorder.ENVIRONMENT_VARIABLE, "1")


# -- the fake upstream: three providers, an agent of three calls ------------- #


def frame(kind: str, payload: object) -> bytes:
    """One message of an AWS event stream: the prelude and its CRC, three
    string headers, the JSON payload and the message's CRC."""
    headers = b"".join(
        bytes([len(name)]) + name + b"\x07" + len(value).to_bytes(2, "big") + value
        for name, value in (
            (b":event-type", kind.encode()),
            (b":content-type", b"application/json"),
            (b":message-type", b"event"),
        )
    )
    body = json.dumps(payload).encode()
    prelude = (16 + len(headers) + len(body)).to_bytes(4, "big") + len(
        headers
    ).to_bytes(4, "big")
    message = prelude + binascii.crc32(prelude).to_bytes(4, "big") + headers + body
    return message + binascii.crc32(message).to_bytes(4, "big")


def bedrock_reply(results: int) -> dict[str, object]:
    content: list[dict[str, object]]
    if results < 2:
        tool = ("lookup", "refund")[results]
        content = [
            {"toolUse": {"toolUseId": f"tu_{results}", "name": tool, "input": CASE}}
        ]
    else:
        content = [{"text": "Refused"}]
    return {
        "output": {"message": {"role": "assistant", "content": content}},
        "stopReason": "tool_use" if results < 2 else "end_turn",
        "usage": {"inputTokens": 12, "outputTokens": 3, "totalTokens": 15},
        "metrics": {"latencyMs": 1},
    }


def anthropic_reply(results: int) -> dict[str, object]:
    content: list[dict[str, object]]
    if results < 2:
        tool = ("lookup", "refund")[results]
        content = [
            {"type": "tool_use", "id": f"tu_{results}", "name": tool, "input": CASE}
        ]
    else:
        content = [{"type": "text", "text": "Refused"}]
    return {
        "id": f"msg_{results}",
        "type": "message",
        "role": "assistant",
        "model": "claude-test",
        "content": content,
        "stop_reason": "tool_use" if results < 2 else "end_turn",
        "stop_sequence": None,
        "usage": {"input_tokens": 12, "output_tokens": 3},
    }


def openai_reply(results: int) -> dict[str, object]:
    message: dict[str, object] = {"role": "assistant", "content": None}
    if results < 2:
        tool = ("lookup", "refund")[results]
        message["tool_calls"] = [
            {
                "id": f"call_{results}",
                "type": "function",
                "function": {"name": tool, "arguments": json.dumps(CASE)},
            }
        ]
    else:
        message["content"] = "Refused"
    return {
        "id": f"chat_{results}",
        "object": "chat.completion",
        "created": 1730000000,
        "model": "gpt-test",
        "choices": [
            {
                "index": 0,
                "finish_reason": "tool_calls" if results < 2 else "stop",
                "message": message,
            }
        ],
        "usage": {"completion_tokens": 3, "prompt_tokens": 12, "total_tokens": 15},
    }


def results_in(path: str, body: dict[str, Any]) -> int:
    """How many tool results the request carries: the agent's step."""
    messages: list[dict[str, Any]] = body.get("messages", [])
    if path.endswith("/chat/completions"):
        return sum(1 for m in messages if m.get("role") == "tool")
    blocks = [
        b for m in messages if isinstance(m.get("content"), list) for b in m["content"]
    ]
    if path.endswith("/v1/messages"):
        return sum(1 for b in blocks if b.get("type") == "tool_result")
    return sum(1 for b in blocks if "toolResult" in b)


class Upstream:
    """OpenAI, Anthropic and Bedrock, faked, each answering an agent of
    three calls by the tool results its request carries. Each request kept."""

    def __init__(self) -> None:
        self.seen: list[tuple[str, dict[str, str]]] = []
        owner = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
                pass

            def do_POST(self) -> None:  # noqa: N802
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                owner.seen.append(
                    (self.path, {k.lower(): v for k, v in self.headers.items()})
                )
                step = results_in(self.path, body)
                if self.path.endswith("/converse-stream"):
                    self._stream()
                elif self.path.endswith("/converse"):
                    self._json(bedrock_reply(step))
                elif self.path.endswith("/v1/messages"):
                    self._json(anthropic_reply(step))
                else:
                    self._json(openai_reply(step))

            def _json(self, payload: object) -> None:
                data = json.dumps(payload).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def _stream(self) -> None:
                self.send_response(200)
                self.send_header("Content-Type", "application/vnd.amazon.eventstream")
                self.send_header("Transfer-Encoding", "chunked")
                self.end_headers()
                for kind, payload in (
                    ("messageStart", {"role": "assistant"}),
                    (
                        "contentBlockDelta",
                        {"contentBlockIndex": 0, "delta": {"text": "Par"}},
                    ),
                    (
                        "contentBlockDelta",
                        {"contentBlockIndex": 0, "delta": {"text": "is"}},
                    ),
                    ("contentBlockStop", {"contentBlockIndex": 0}),
                    ("messageStop", {"stopReason": "end_turn"}),
                    (
                        "metadata",
                        {
                            "usage": {
                                "inputTokens": 12,
                                "outputTokens": 3,
                                "totalTokens": 15,
                            },
                            "metrics": {"latencyMs": 1},
                        },
                    ),
                ):
                    data = frame(kind, payload)
                    self.wfile.write(b"%x\r\n%s\r\n" % (len(data), data))
                    self.wfile.flush()
                self.wfile.write(b"0\r\n\r\n")
                self.wfile.flush()

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


@pytest.fixture
def proxy(tmp_path: Path, upstream: Upstream) -> Iterator[Proxy]:
    running = start_proxy(
        root=tmp_path / "wire",
        tenant="acme",
        app="support",
        port=0,
        upstream=[
            f"openai={upstream.address}/v1",
            f"anthropic={upstream.address}",
            f"bedrock={upstream.address}",
        ],
        episode_idle=0.5,
        timeout=5.0,
    )
    yield running
    running.stop()


def a_bedrock(endpoint: str, **headers: str) -> Any:
    """boto3's client, with the application's own key, and `headers` added
    before it signs: how a boto3 application sends `X-Digline-*`."""
    import boto3  # pyright: ignore[reportMissingTypeStubs]
    from botocore.config import Config  # pyright: ignore[reportMissingTypeStubs]

    client: Any = cast(Any, boto3).client(
        "bedrock-runtime",
        region_name="us-west-2",
        endpoint_url=endpoint,
        aws_access_key_id="AKIDAPP",
        aws_secret_access_key="app-secret",
        config=Config(retries={"max_attempts": 1}),
    )

    def add(request: Any, **_: Any) -> None:
        for key, value in headers.items():
            request.headers[key] = value

    client.meta.events.register("before-sign.bedrock-runtime.*", add)
    return client


def wired(root: Path, at_least: int) -> list[dict[str, Any]]:
    return recordings(root / "wire", at_least)


# -- Bedrock ----------------------------------------------------------------- #


def test_bedrock_is_signed_again_and_recorded_as_in_process(
    proxy: Proxy, upstream: Upstream, tmp_path: Path
) -> None:
    client = a_bedrock(f"{proxy.address}/suite/triage")
    reply = client.converse(
        modelId=MODEL, messages=[{"role": "user", "content": [{"text": "Capital?"}]}]
    )
    [(path, headers)] = upstream.seen
    # The model id as the SDK wrote it, and signed again with the proxy's own
    # key and region: the application's signature named the proxy.
    assert path == "/model/anthropic.claude-test-v1%3A0/converse"
    assert headers["authorization"].startswith("AWS4-HMAC-SHA256 Credential=AKIDPROXY/")
    assert "/us-west-2/bedrock/aws4_request" in headers["authorization"]
    assert not [key for key in headers if key.startswith("x-digline-")]
    assert reply["output"]["message"]["content"][0]["toolUse"]["name"] == "lookup"
    [written] = wired(tmp_path, 1)
    assert written["suite"] == "triage"
    # The same call recorded in process, against the same fake: the same case
    # and the same setup digest, `modelId` put back from the path.
    local = wrap(
        a_bedrock(upstream.address), app="support", tenant="acme", root=tmp_path / "in"
    )
    local.converse(
        modelId=MODEL,
        messages=[{"role": "user", "content": [{"text": "Capital?"}]}],
        suite="triage",
    )
    [made] = recordings(tmp_path / "in")
    assert written["case"] == made["case"]
    assert written["setup_digest"] == made["setup_digest"]
    assert written["response"]["output"] == made["response"]["output"]


def test_bedrock_streamed_is_read_from_its_event_stream(
    proxy: Proxy, tmp_path: Path
) -> None:
    client = a_bedrock(f"{proxy.address}/suite/triage")
    reply = client.converse_stream(
        modelId=MODEL, messages=[{"role": "user", "content": [{"text": "Capital?"}]}]
    )
    text = "".join(
        event["contentBlockDelta"]["delta"]["text"]
        for event in reply["stream"]
        if "contentBlockDelta" in event
    )
    assert text == "Paris"
    [written] = wired(tmp_path, 1)
    assert written["response"]["output"] == "Paris"
    assert written["response"]["usage"] == {"input_tokens": 12, "output_tokens": 3}


def test_bedrock_without_credentials_says_so_and_forwards_nothing(
    tmp_path: Path, upstream: Upstream, monkeypatch: pytest.MonkeyPatch
) -> None:
    from botocore.exceptions import ClientError  # pyright: ignore[reportMissingTypeStubs]

    monkeypatch.delenv("AWS_ACCESS_KEY_ID")
    monkeypatch.delenv("AWS_SECRET_ACCESS_KEY")
    running = start_proxy(
        root=tmp_path,
        tenant="acme",
        app="support",
        port=0,
        upstream=[f"bedrock={upstream.address}"],
    )
    try:
        assert getattr(running.wires["bedrock"], "problem", None) is not None
        with pytest.raises(ClientError) as raised:
            a_bedrock(running.address).converse(
                modelId=MODEL, messages=[{"role": "user", "content": [{"text": "?"}]}]
            )
    finally:
        running.stop()
    assert cast(Any, raised.value).response["ResponseMetadata"]["HTTPStatusCode"] == 502
    assert "no AWS credentials" in str(raised.value)
    assert upstream.seen == []


# -- the steps of an agent, off the wire ------------------------------------- #


def openai_agent(client: Any, **extra: Any) -> None:
    messages: list[dict[str, Any]] = list(QUESTION)
    for _ in range(3):
        reply = client.chat.completions.create(
            model="gpt-test", messages=messages, **extra
        )
        calls = reply.choices[0].message.tool_calls
        if not calls:
            return
        messages.append(
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": c.id,
                        "type": "function",
                        "function": {
                            "name": c.function.name,
                            "arguments": c.function.arguments,
                        },
                    }
                    for c in calls
                ],
            }
        )
        messages.extend(
            {"role": "tool", "tool_call_id": c.id, "content": RESULTS[c.function.name]}
            for c in calls
        )


def anthropic_agent(client: Any, **extra: Any) -> None:
    messages: list[dict[str, Any]] = list(QUESTION)
    for _ in range(3):
        reply = client.messages.create(
            model="claude-test", max_tokens=10, messages=messages, **extra
        )
        uses = [b for b in reply.content if b.type == "tool_use"]
        if not uses:
            return
        messages.append(
            {
                "role": "assistant",
                "content": [
                    {"type": "tool_use", "id": u.id, "name": u.name, "input": u.input}
                    for u in uses
                ],
            }
        )
        messages.append(
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": u.id,
                        "content": RESULTS[u.name],
                        "is_error": u.name == FAILS,
                    }
                    for u in uses
                ],
            }
        )


def bedrock_agent(client: Any, **extra: Any) -> None:
    messages: list[dict[str, Any]] = [
        {"role": "user", "content": [{"text": "Refund A1"}]}
    ]
    for _ in range(3):
        reply = client.converse(modelId=MODEL, messages=messages, **extra)
        uses = [
            b["toolUse"]
            for b in reply["output"]["message"]["content"]
            if "toolUse" in b
        ]
        if not uses:
            return
        messages.append(
            {"role": "assistant", "content": [{"toolUse": u} for u in uses]}
        )
        messages.append(
            {
                "role": "user",
                "content": [
                    {
                        "toolResult": {
                            "toolUseId": u["toolUseId"],
                            "content": [{"text": RESULTS[u["name"]]}],
                            "status": "error" if u["name"] == FAILS else "success",
                        }
                    }
                    for u in uses
                ],
            }
        )


EPISODE = {"X-Digline-Episode": "agent-1", "X-Digline-Suite": "agent"}

#: Each provider: its agent, its client through the proxy with the episode's
#: headers, its client straight to the fake, the keyword that names the suite
#: in process, and the status its results carry for the tool that worked and
#: the one that failed.
PROVIDERS: dict[
    str,
    tuple[
        Callable[..., None], Callable[[str], Any], Callable[[str], Any], tuple[str, str]
    ],
] = {
    "openai": (
        openai_agent,
        lambda proxy: an_openai(f"{proxy}/v1", **EPISODE),
        lambda fake: an_openai(f"{fake}/v1"),
        # Chat Completions has no word for a tool that failed.
        ("not_reported", "not_reported"),
    ),
    "anthropic": (
        anthropic_agent,
        lambda proxy: an_anthropic(proxy, **EPISODE),
        lambda fake: an_anthropic(fake),
        ("success", "error"),
    ),
    "bedrock": (
        bedrock_agent,
        lambda proxy: a_bedrock(proxy, **EPISODE),
        lambda fake: a_bedrock(fake),
        ("success", "error"),
    ),
}


def the_episode(root: Path) -> dict[str, Any]:
    deadline = time.monotonic() + 5
    while True:
        found = [r for r in recordings(root, 0) if "id" in r]
        if found or time.monotonic() > deadline:
            [written] = found
            return written
        time.sleep(0.05)


def shape(step: dict[str, Any]) -> tuple[object, ...]:
    """A step's place, actor, tool and arguments: what the wire and the
    process must agree on."""
    return (step["index"], step["actor"], step.get("tool"), step.get("arguments"))


@pytest.mark.parametrize("provider", sorted(PROVIDERS))
def test_an_agents_tool_steps_are_closed_by_the_next_calls_results(
    provider: str, proxy: Proxy, upstream: Upstream, tmp_path: Path
) -> None:
    agent, through, straight, (worked, failed) = PROVIDERS[provider]
    agent(through(proxy.address))
    wire = the_episode(tmp_path / "wire")
    steps = wire["response"]["steps"]
    assert [s["actor"] for s in steps] == ["model", "tool", "model", "tool", "model"]
    lookup, refund = steps[1], steps[3]
    # `success` is the default, and the format leaves it out, as the run
    # document does.
    assert (lookup["tool"], lookup["result"], lookup.get("status", "success")) == (
        "lookup",
        RESULTS["lookup"],
        worked,
    )
    assert (refund["tool"], refund["result"], refund.get("status", "success")) == (
        "refund",
        RESULTS["refund"],
        failed,
    )
    # The same agent recorded in process: the same places, tools and
    # arguments; its tool steps end where the call does, `not_reported`.
    local = wrap(
        straight(upstream.address), app="support", tenant="acme", root=tmp_path / "in"
    )
    with episode(local, suite="agent", case={"messages": "agent"}):
        agent(local)
    made = the_episode(tmp_path / "in")
    assert [shape(s) for s in made["response"]["steps"]] == [shape(s) for s in steps]
    assert [
        s.get("result_absence")
        for s in made["response"]["steps"]
        if s["actor"] == "tool"
    ] == [
        "not_reported",
        "not_reported",
    ]


def test_a_result_is_not_put_on_a_step_it_may_not_answer(
    proxy: Proxy, tmp_path: Path
) -> None:
    """The second call carries a result for a tool the first did not ask for:
    the first call's tool step stays as it ended."""
    client = an_anthropic(proxy.address, **EPISODE)
    client.messages.create(model="claude-test", max_tokens=10, messages=QUESTION)
    client.messages.create(
        model="claude-test",
        max_tokens=10,
        messages=[
            *QUESTION,
            {
                "role": "assistant",
                "content": [
                    {"type": "tool_use", "id": "tu_x", "name": "other", "input": {}}
                ],
            },
            {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": "tu_x", "content": "no"}
                ],
            },
        ],
    )
    steps = the_episode(tmp_path / "wire")["response"]["steps"]
    [lookup] = [s for s in steps if s.get("tool") == "lookup"]
    assert "result" not in lookup
    assert lookup["result_absence"] == "not_reported"


# -- the calls that named no suite ------------------------------------------- #


def test_a_call_that_named_no_suite_is_imported_from_unassigned(
    proxy: Proxy, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    an_openai(f"{proxy.address}/v1").chat.completions.create(
        model="gpt-test", messages=QUESTION
    )
    [written] = wired(tmp_path, 1)
    assert written["suite"] == recorder.UNASSIGNED
    root = tmp_path / "wire"
    suite_file(root)
    assert main([*argv(root), "--from", "_unassigned"]) == 0
    out = capsys.readouterr().out
    assert "read from _unassigned" in out
    # Where it was made: the SDK's `User-Agent` and the path, where a call in
    # process names its function.
    [made] = [line for line in out.splitlines() if line.startswith("    made at: ")]
    assert made.startswith("    made at: OpenAI/Python ")
    assert made.endswith(" /v1/chat/completions")


def test_a_bedrock_api_key_goes_to_bedrock_never_to_openai(
    tmp_path: Path, upstream: Upstream, monkeypatch: pytest.MonkeyPatch
) -> None:
    """boto3 sends a Bedrock API key as a bearer, which is OpenAI's claim
    (measured with botocore 1.43.123). Bedrock's path decides, and the key
    is signed over, not passed on."""
    running = start_proxy(
        root=tmp_path,
        tenant="acme",
        app="support",
        port=0,
        upstream=[
            f"openai={upstream.address}/openai/v1",
            f"bedrock={upstream.address}/bedrock",
        ],
    )
    try:
        import boto3  # pyright: ignore[reportMissingTypeStubs]

        monkeypatch.setenv("AWS_BEARER_TOKEN_BEDROCK", "bedrock-api-key")
        client: Any = cast(Any, boto3).client(
            "bedrock-runtime", region_name="us-west-2", endpoint_url=running.address
        )
        client.converse(
            modelId=MODEL, messages=[{"role": "user", "content": [{"text": "?"}]}]
        )
    finally:
        running.stop()
    [(path, headers)] = upstream.seen
    assert path.startswith("/bedrock/model/")
    assert headers["authorization"].startswith("AWS4-HMAC-SHA256 Credential=AKIDPROXY/")
    assert "bedrock-api-key" not in json.dumps(headers)


def test_the_applications_session_token_does_not_go_on(
    proxy: Proxy, upstream: Upstream
) -> None:
    """A token the application signed with is its own credentials': signed
    over with the proxy's, it would name a key that is not the one signing."""
    import boto3  # pyright: ignore[reportMissingTypeStubs]

    session: Any = boto3
    session.client(
        "bedrock-runtime",
        region_name="us-west-2",
        endpoint_url=proxy.address,
        aws_access_key_id="AKIDAPP",
        aws_secret_access_key="app-secret",
        aws_session_token="app-session-token",
    ).converse(modelId=MODEL, messages=[{"role": "user", "content": [{"text": "?"}]}])
    [(_, headers)] = upstream.seen
    assert "x-amz-security-token" not in headers
    assert "app-session-token" not in json.dumps(headers)


def test_bedrock_without_a_region_says_so_at_the_start_and_at_a_call(
    tmp_path: Path, upstream: Upstream, monkeypatch: pytest.MonkeyPatch
) -> None:
    from botocore.exceptions import ClientError  # pyright: ignore[reportMissingTypeStubs]

    monkeypatch.delenv("AWS_REGION")
    monkeypatch.delenv("AWS_DEFAULT_REGION")
    running = start_proxy(
        root=tmp_path,
        tenant="acme",
        app="support",
        port=0,
        upstream=[f"bedrock={upstream.address}"],
    )
    try:
        assert "no AWS region" in str(getattr(running.wires["bedrock"], "problem", ""))
        with pytest.raises(ClientError) as raised:
            a_bedrock(running.address).converse(
                modelId=MODEL, messages=[{"role": "user", "content": [{"text": "?"}]}]
            )
    finally:
        running.stop()
    assert "the route bedrock cannot forward: no AWS region" in str(raised.value)
    assert upstream.seen == []
