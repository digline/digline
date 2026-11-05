"""Bedrock's InvokeModel and InvokeModelWithResponseStream, recorded where the
body is Anthropic's Messages and counted, by name, where it is not. (P-1541,
P-1543; ADR 0062 §2, noted 2026-11-05)

Measured before this: through the recorder in process both calls passed with
nothing recorded and nothing counted, through the proxy they were counted
`route not read`, and through the Java hook nothing at all. Here, with boto3
against a fake Bedrock on 127.0.0.1 that answers with the wire fixtures:

- in process and through the proxy, the call is the file the fixture holds:
  the same case, setup digest, answer and tool calls the Java hook is held to;
- the application reads the reply it would have read without the recorder;
- another family, an embedding model, a cross-region prefix: counted with
  their reason, which the status shows, said once a family on standard error,
  and nothing written.
"""

from __future__ import annotations

import base64
import json
import sys
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest
from tests.test_record_proxy import SDKS, recordings

# `aws` is an autouse fixture: the proxy's credentials and region, and the
# recorder switched on. Imported for pytest to find it, never called.
from tests.test_record_proxy_bedrock import (  # noqa: F401
    a_bedrock,
    aws,  # pyright: ignore[reportUnusedImport]
    frame,
)

from digline import recorder
from digline.host import recorder_status
from digline.host.proxy import Proxy, start_proxy
from digline.recorder import wrap
from digline_bedrock.recording import REGION_PREFIXES, family_of

FIXTURES = Path(__file__).resolve().parent.parent / "recorders" / "fixtures" / "wire"


def fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / f"{name}.json").read_text("utf-8"))


def expected(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / f"{name}.expected.json").read_text("utf-8"))


WHOLE, STREAM = fixture("bedrock-invoke"), fixture("bedrock-invoke-stream")

#: What Titan's InvokeModel answers, in its own shape.
TITAN = {
    "inputTextTokenCount": 5,
    "results": [{"tokenCount": 3, "outputText": "Paris", "completionReason": "FINISH"}],
}
TITAN_CHUNKS = [
    {"outputText": "Par", "index": 0},
    {"outputText": "is", "index": 0, "completionReason": "FINISH"},
]


class Bedrock:
    """Bedrock, faked: InvokeModel answered with the fixture's reply, its
    stream with the fixture's chunks, as event-stream frames."""

    def __init__(self) -> None:
        self.paths: list[str] = []
        owner = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
                pass

            def do_POST(self) -> None:  # noqa: N802
                self.rfile.read(int(self.headers["Content-Length"]))
                owner.paths.append(self.path)
                if "anthropic" not in self.path and self.path.endswith("-stream"):
                    # Another family's stream, its chunks in its own shape.
                    self.send_response(200)
                    self.send_header(
                        "Content-Type", "application/vnd.amazon.eventstream"
                    )
                    self.send_header("Transfer-Encoding", "chunked")
                    self.end_headers()
                    for piece in TITAN_CHUNKS:
                        payload = {
                            "bytes": base64.b64encode(
                                json.dumps(piece).encode()
                            ).decode()
                        }
                        data = frame("chunk", payload)
                        self.wfile.write(b"%x\r\n%s\r\n" % (len(data), data))
                    self.wfile.write(b"0\r\n\r\n")
                    self.wfile.flush()
                    return
                if "anthropic" not in self.path:
                    # Another family answers in its own shape, which no
                    # Messages reading can read: Titan's, here, for all of them.
                    data = json.dumps(TITAN).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                    return
                if self.path.endswith("/invoke-with-response-stream"):
                    self.send_response(200)
                    self.send_header(
                        "Content-Type", "application/vnd.amazon.eventstream"
                    )
                    self.send_header("Transfer-Encoding", "chunked")
                    self.end_headers()
                    for event in STREAM["events"]:
                        data = frame("chunk", event["chunk"])
                        self.wfile.write(b"%x\r\n%s\r\n" % (len(data), data))
                    self.wfile.write(b"0\r\n\r\n")
                    self.wfile.flush()
                    return
                data = json.dumps(WHOLE["reply"]).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.address = f"http://127.0.0.1:{self.server.server_address[1]}"


@pytest.fixture(autouse=True, scope="module")
def the_sdks_leave_with_this_module() -> Iterator[None]:
    """Anthropic's SDK, which the Messages reading imports, gone after this
    module: the plugins' own tests hold that nothing imports it before a
    call, as `tests/test_record_proxy_bedrock.py` does."""
    before = set(sys.modules)
    yield
    for name in set(sys.modules) - before:
        if name.split(".", 1)[0] in SDKS:
            del sys.modules[name]


@pytest.fixture
def bedrock() -> Iterator[Bedrock]:
    fake = Bedrock()
    yield fake
    fake.server.shutdown()
    fake.server.server_close()


@pytest.fixture(autouse=True)
def nothing_said_yet(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each test its own process, as far as what was said once goes."""
    said: set[str] = set()
    monkeypatch.setattr(recorder, "_SAID", said)


@pytest.fixture
def proxy(tmp_path: Path, bedrock: Bedrock) -> Iterator[Proxy]:
    running = start_proxy(
        root=tmp_path / "wire",
        tenant="acme",
        app="support",
        port=0,
        upstream=[f"bedrock={bedrock.address}"],
        episode_idle=0.5,
        timeout=5.0,
    )
    yield running
    running.stop()


def invoke(client: Any, call: dict[str, Any], model: str | None = None) -> object:
    """The call as an application makes it, and what it reads back: the
    reply's JSON, or the types of the events it read."""
    body = json.dumps(call["request"])
    model_id = model or call["model_id"]
    if "events" not in call:
        reply = client.invoke_model(modelId=model_id, body=body)
        return json.loads(reply["body"].read())
    reply = client.invoke_model_with_response_stream(modelId=model_id, body=body)
    return [json.loads(e["chunk"]["bytes"]).get("type") for e in reply["body"]]


def held_to_the_fixture(written: dict[str, Any], name: str) -> None:
    """The file the fixture holds, but for what a call of its own differs in:
    when it was written, how long it took and the suite it named."""
    made = expected(name)
    for key in ("case", "setup", "setup_digest"):
        assert written[key] == made[key], key
    for key in ("output", "tool_calls", "finish", "usage", "input"):
        assert written["response"].get(key) == made["response"].get(key), key


@pytest.mark.parametrize("name", ["bedrock-invoke", "bedrock-invoke-stream"])
def test_in_process_the_call_is_the_fixtures_file(
    tmp_path: Path, bedrock: Bedrock, name: str
) -> None:
    call = fixture(name)
    client = wrap(
        a_bedrock(bedrock.address), app="support", tenant="acme", root=tmp_path
    )
    read = invoke(client, call)
    if name == "bedrock-invoke":
        # The application reads the reply the server sent, whole: the body the
        # recorder read is put back.
        assert read == WHOLE["reply"]
    else:
        assert read == [
            json.loads(base64.b64decode(e["chunk"]["bytes"]))["type"]
            for e in call["events"]
        ]
    [written] = recordings(tmp_path)
    held_to_the_fixture(written, name)


@pytest.mark.parametrize("name", ["bedrock-invoke", "bedrock-invoke-stream"])
def test_through_the_proxy_the_call_is_the_fixtures_file(
    tmp_path: Path, proxy: Proxy, bedrock: Bedrock, name: str
) -> None:
    call = fixture(name)
    invoke(a_bedrock(f"{proxy.address}/suite/triage"), call)
    assert bedrock.paths[-1] == call["path"]
    [written] = recordings(tmp_path / "wire", 1)
    assert written["suite"] == "triage"
    held_to_the_fixture(written, name)


#: Model ids not read, each with the reason it is counted as.
DECLINED = {
    "amazon.titan-text-express-v1": "model family not recorded",
    "amazon.titan-text-lite-v1": "model family not recorded",
    "us.meta.llama3-1-8b-instruct-v1:0": "model family not recorded",
    "mistral.mistral-large-2402-v1:0": "model family not recorded",
    "cohere.embed-english-v3": "embeddings not recorded",
    "amazon.titan-embed-text-v2:0": "embeddings not recorded",
}


def test_in_process_another_family_is_counted_said_once_and_not_written(
    tmp_path: Path, bedrock: Bedrock, capfd: pytest.CaptureFixture[str]
) -> None:
    client = wrap(
        a_bedrock(bedrock.address), app="support", tenant="acme", root=tmp_path
    )
    for model in DECLINED:
        invoke(client, WHOLE, model)
    # The stream of a family not read is declined too, before its chunks.
    invoke(client, STREAM, "amazon.titan-text-express-v1")
    assert recordings_or_none(tmp_path) == []
    assert client.digline_counts["not_recorded"] == {
        "model family not recorded": 5,
        "embeddings not recorded": 2,
    }
    said = capfd.readouterr().err
    assert said.count("this model family is not recorded") == 3, said
    assert (
        "digline recorder: invoke_model on amazon.titan-text-express-v1: this "
        "model family is not recorded" in said
    )
    assert "amazon.titan-text-lite-v1" not in said
    assert "invoke_model on us.meta.llama3-1-8b-instruct-v1:0" in said
    assert said.count("embeddings are not recorded") == 2, said
    # The counts reach the status at the recorder's next look, or when the
    # process ends: written here as the exit writes them.
    recorder._flush(client._digline_state)  # pyright: ignore[reportPrivateUsage]
    [tenant] = recorder_status(tmp_path)
    [suite] = tenant.suites
    assert dict(suite.not_recorded) == {
        "embeddings not recorded": 2,
        "model family not recorded": 5,
    }


def recordings_or_none(root: Path) -> list[Path]:
    place = root / ".digline" / "acme" / "recordings"
    return sorted(p for p in place.glob("*/*.json") if not p.name.startswith("."))


def test_through_the_proxy_another_family_is_counted_and_not_written(
    tmp_path: Path,
    proxy: Proxy,
    bedrock: Bedrock,
    capfd: pytest.CaptureFixture[str],
) -> None:
    client = a_bedrock(f"{proxy.address}/suite/triage")
    invoke(client, WHOLE, "amazon.titan-text-express-v1")
    invoke(client, STREAM, "cohere.embed-english-v3")
    proxy.stop()
    assert recordings_or_none(tmp_path / "wire") == []
    [tenant] = recorder_status(tmp_path / "wire")
    [suite] = tenant.suites
    assert dict(suite.not_recorded) == {
        "embeddings not recorded": 1,
        "model family not recorded": 1,
    }
    said = capfd.readouterr().err
    assert (
        "invoke_model on amazon.titan-text-express-v1: this model family is not "
        "recorded" in said
    )
    assert (
        "invoke_model_with_response_stream on cohere.embed-english-v3: embeddings "
        "are not recorded" in said
    )


@pytest.mark.parametrize("prefix", ["", *REGION_PREFIXES])
def test_the_region_prefix_is_taken_off_before_the_vendor_is_read(prefix: str) -> None:
    assert family_of(f"{prefix}anthropic.claude-3-5-haiku-20241022-v1:0") == (
        "anthropic",
        "messages",
    )
    assert family_of(f"{prefix}amazon.titan-text-express-v1") == ("amazon", "other")
    assert family_of(f"{prefix}cohere.embed-english-v3") == ("cohere", "embeddings")


def test_an_arn_is_read_by_its_last_segment() -> None:
    assert family_of(
        "arn:aws:bedrock:us-east-1:123:inference-profile/us.anthropic.claude-3-haiku"
    ) == ("anthropic", "messages")
