"""No credential is written by the recorder or printed by the proxy.
(ADR 0004 §5: a credential is the one payload no `Disclosure` releases)

The defects this holds shut, one class:

- `digline-anthropic`'s map put the whole request body but the messages into
  the setup, so an MCP server's `authorization_token`, passed as a keyword or
  through `extra_body`, was written in clear into every recording, shown by
  `record compare --show-setup`, and folded into the setup digest;
- `digline record proxy` wrote the call site as the User-Agent and the path
  *with its query*, so a key sent as `?api-key=...` was written into the
  recording and the import's listing;
- `--upstream ROUTE=URL` kept a user name and password in the address,
  printed the address on the start line, and quoted it in its refusals, to
  standard error and a CI log (GHSA-xrvr-5x82-w7g7's class).

Each test is a probe of the delta-pass over 1.1.1 (`recorder/probe2`,
`proxy/probe.py` P3 and P9), made to fail on 1.1.1 and pass here; the header
keys, which were never written, are the controls.
"""

from __future__ import annotations

import importlib
import json
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from tests.test_record_proxy import Upstream, an_openai, proxying

from digline import recorder
from digline.host.errors import UsageError
from digline.host.proxy import Proxy, load_wires, upstreams_of
from digline.recorder import wrap

REPLY: dict[str, object] = {
    "id": "msg_1",
    "type": "message",
    "role": "assistant",
    "model": "claude-test",
    "content": [{"type": "text", "text": "Paris"}],
    "stop_reason": "end_turn",
    "usage": {"input_tokens": 12, "output_tokens": 3},
}
TOKEN = "MCP-TOKEN-SECRET"
SERVER = {"type": "url", "url": "https://mcp.example/sse", "name": "tickets"}


def an_anthropic() -> Any:
    httpx2 = importlib.import_module("httpx2")
    http = httpx2.Client(
        transport=httpx2.MockTransport(lambda request: httpx2.Response(200, json=REPLY))
    )
    return importlib.import_module("anthropic").Anthropic(
        api_key="sk-ant-HEADER-KEY", http_client=http, max_retries=0
    )


def written(root: Path) -> list[str]:
    return [
        path.read_text(encoding="utf-8")
        for path in sorted((root / ".digline").glob("*/recordings/*/*.json"))
        if not path.name.startswith(".")
    ]


# -- the anthropic map ------------------------------------------------------ #


def test_an_mcp_servers_token_is_not_recorded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(recorder.ENVIRONMENT_VARIABLE, "1")
    client = wrap(an_anthropic(), app="support", tenant="acme", root=tmp_path)
    servers = [{**SERVER, "authorization_token": TOKEN}]
    client.messages.create(
        model="claude-test",
        max_tokens=10,
        messages=[{"role": "user", "content": "q"}],
        suite="triage",
        extra_headers={"x-api-key": "sk-ant-EXTRA-HEADER"},
        extra_body={"mcp_servers": servers},
    )
    recorder._flush_shared(client._digline_state.shared)  # pyright: ignore[reportPrivateUsage, reportAttributeAccessIssue]
    [text] = written(tmp_path)
    assert TOKEN not in text
    recording = json.loads(text)
    # What the server is stays in the setup: only its credential is left out.
    assert recording["setup"]["mcp_servers"] == [SERVER]
    # The controls: the keys in headers were never written.
    assert "sk-ant-HEADER-KEY" not in text
    assert "sk-ant-EXTRA-HEADER" not in text


def test_a_rotated_token_is_the_same_setup() -> None:
    """A credential in the digest would make every rotation a new setup."""
    from digline_anthropic.recording import MAP

    def setup(token: str) -> dict[str, object]:
        request = {
            "model": "claude-test",
            "max_tokens": 10,
            "messages": [],
            "extra_body": {"mcp_servers": [{**SERVER, "authorization_token": token}]},
        }
        return MAP.split(request)[1]

    assert setup("first") == setup("second")
    assert "authorization_token" not in json.dumps(setup("first"))


# -- the proxy --------------------------------------------------------------- #


@pytest.fixture
def upstream() -> Iterator[Upstream]:
    fake = Upstream()
    yield fake
    fake.server.shutdown()
    fake.server.server_close()


@pytest.fixture
def proxy(
    tmp_path: Path, upstream: Upstream, monkeypatch: pytest.MonkeyPatch
) -> Iterator[Proxy]:
    monkeypatch.setenv(recorder.ENVIRONMENT_VARIABLE, "1")
    running = proxying(tmp_path, upstream)
    yield running
    running.stop()


def test_a_key_in_the_query_is_not_recorded(
    proxy: Proxy, upstream: Upstream, tmp_path: Path
) -> None:
    client = an_openai(f"{proxy.address}/v1")
    client.chat.completions.create(
        model="gpt-test",
        messages=[{"role": "user", "content": "q"}],
        extra_query={"api-key": "sk-FAKEQUERYKEY0000"},
    )
    deadline = time.monotonic() + 5
    while not written(tmp_path) and time.monotonic() < deadline:
        time.sleep(0.02)
    [text] = written(tmp_path)
    assert "sk-FAKEQUERYKEY0000" not in text
    # The path is still there, so the call site still says where it came from.
    assert "/v1/chat/completions" in json.loads(text)["call_site"]
    # The control: the key in the header was never written.
    assert "sk-test" not in text


@pytest.mark.parametrize(
    "given",
    [
        "openai=http://gwuser:FAKEGATEWAYPASSWORD@127.0.0.1:9/v1",
        "openai=http://FAKEGATEWAYPASSWORD@127.0.0.1:9/v1",
        "openai=ftp://gwuser:FAKEGATEWAYPASSWORD@h/",
        "openai=http://gwuser:FAKEGATEWAYPASSWORD@h:notaport/",
        "http://gwuser:FAKEGATEWAYPASSWORD@h/",
        "nosuchroute=http://gwuser:FAKEGATEWAYPASSWORD@h/",
    ],
)
def test_an_upstream_with_a_credential_is_refused_without_quoting_it(
    given: str,
) -> None:
    with pytest.raises(UsageError) as refused:
        upstreams_of([given], load_wires())
    assert "FAKEGATEWAYPASSWORD" not in str(refused.value)


def test_an_upstream_without_a_credential_is_kept() -> None:
    """The control."""
    assert upstreams_of(["openai=http://127.0.0.1:9/v1/"], load_wires()) == {
        "openai": "http://127.0.0.1:9/v1"
    }


def test_the_command_never_prints_the_credential(tmp_path: Path) -> None:
    done = subprocess.run(
        [
            sys.executable,
            "-m",
            "digline.cli",
            "record",
            "proxy",
            "--root",
            str(tmp_path),
            "--tenant",
            "acme",
            "--port",
            "0",
            "--upstream",
            "openai=http://gwuser:FAKEGATEWAYPASSWORD@127.0.0.1:9/v1",
        ],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert done.returncode == 64
    assert "FAKEGATEWAYPASSWORD" not in done.stdout + done.stderr
