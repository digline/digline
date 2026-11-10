"""`digline record proxy` answers programs, never a web page. (ADR 0062 §3)

The defect this holds shut: the proxy read neither `Host` nor `Origin`, so a
page open in the developer's browser could send what a browser sends without
asking, a CORS-simple POST with `Content-Type: text/plain`, to
`127.0.0.1:<port>/suite/<any>/v1/...`, directly or through a name it rebinds to
the loopback. Against an upstream that needs no key, a local gateway, the page
spent through it and planted recordings under a suite it named, which
`digline record import` then shows a person. A request with `Origin` is now
refused, and `Host` is held to the address the proxy bound, as `digline view`
holds its own (GHSA-qjqq-hrq4-rfgh).

Each test is the delta-pass's probe over 1.1.1 (`proxy/probe.py`, P2), made
to fail on 1.1.1 and pass here; the SDK tests are the controls.
"""

from __future__ import annotations

import http.client
import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from tests.test_record_proxy import Upstream, an_openai, proxying

from digline import recorder
from digline.host.proxy import Proxy

BODY = json.dumps(
    {"model": "gpt-fake", "messages": [{"role": "user", "content": "q"}]}
).encode()


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


def send(proxy: Proxy, headers: dict[str, str]) -> int:
    """One POST as the given headers say, with no key: what a page can send."""
    connection = http.client.HTTPConnection("127.0.0.1", proxy.port, timeout=5)
    try:
        connection.putrequest(
            "POST", "/suite/from-a-web-page/v1/chat/completions", skip_host=True
        )
        for name, value in headers.items():
            connection.putheader(name, value)
        connection.putheader("Content-Length", str(len(BODY)))
        connection.endheaders(BODY)
        return connection.getresponse().status
    finally:
        connection.close()


def written(root: Path) -> list[Path]:
    return sorted((root / ".digline").glob("*/recordings/*/*.json"))


def test_a_page_with_an_origin_is_refused(
    proxy: Proxy, upstream: Upstream, tmp_path: Path
) -> None:
    status = send(
        proxy,
        {
            "Host": f"127.0.0.1:{proxy.port}",
            "Origin": "http://evil.example",
            "Content-Type": "text/plain;charset=UTF-8",
        },
    )
    assert status == 403
    assert upstream.seen == []
    assert written(tmp_path) == []


def test_a_rebound_host_is_refused_with_no_origin(
    proxy: Proxy, upstream: Upstream, tmp_path: Path
) -> None:
    status = send(proxy, {"Host": f"rebound.example:{proxy.port}"})
    assert status == 403
    assert upstream.seen == []
    assert written(tmp_path) == []


def test_a_host_on_another_port_is_refused(proxy: Proxy, upstream: Upstream) -> None:
    assert send(proxy, {"Host": f"127.0.0.1:{proxy.port + 1}"}) == 403
    assert upstream.seen == []


@pytest.mark.parametrize("name", ["127.0.0.1", "localhost", "LOCALHOST"])
def test_the_proxys_own_names_are_answered(
    proxy: Proxy, upstream: Upstream, name: str
) -> None:
    assert send(proxy, {"Host": f"{name}:{proxy.port}"}) == 200
    assert len(upstream.seen) == 1


def test_an_sdk_is_answered_and_recorded(
    proxy: Proxy, upstream: Upstream, tmp_path: Path
) -> None:
    """The control: what the proxy is for still works."""
    reply = an_openai(f"{proxy.address}/v1").chat.completions.create(
        model="gpt-test",
        messages=[{"role": "user", "content": "Capital of France?"}],
        extra_headers={"X-Digline-Suite": "triage"},
    )
    assert reply.choices[0].message.content
    assert len(upstream.seen) == 1
