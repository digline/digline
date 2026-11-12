"""`digline record proxy` behind a company proxy and a company CA.

Found in a first use outside the project, on a Java application with a judged
suite, behind a company proxy: the proxy went to the provider directly, so
where the network lets HTTPS out only through a company proxy, every call was
a 502. Measured on 2026-11-12 at `2aaae91d`, before this: with `HTTPS_PROXY`
naming a listener, nothing connected to it.

Here a fake company proxy counts the `CONNECT`s it is asked for and tunnels
them, and the upstream is HTTPS with a certificate a private CA signed, both on
127.0.0.1. The upstream answers in OpenAI's shape.
"""

from __future__ import annotations

import http.server
import json
import select
import socket
import ssl
import subprocess
import threading
import urllib.error
import urllib.request
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from digline import recorder
from digline.host.proxy import Proxy, start_proxy, upstream_proxy

REPLY = json.dumps(
    {
        "id": "c1",
        "object": "chat.completion",
        "created": 0,
        "model": "m",
        "choices": [
            {
                "index": 0,
                "finish_reason": "stop",
                "message": {"role": "assistant", "content": "hi"},
            }
        ],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }
).encode()

PROXY_VARIABLES = (
    "HTTPS_PROXY",
    "https_proxy",
    "HTTP_PROXY",
    "http_proxy",
    "NO_PROXY",
    "no_proxy",
    "SSL_CERT_FILE",
    "SSL_CERT_DIR",
    "REQUESTS_CA_BUNDLE",
)


@pytest.fixture(autouse=True)
def a_clean_network_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in PROXY_VARIABLES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv(recorder.ENVIRONMENT_VARIABLE, "1")


@pytest.fixture(scope="module")
def certificates(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A private CA, and a certificate for 127.0.0.1 it signed."""
    where = tmp_path_factory.mktemp("ca")
    (where / "x.cnf").write_text(
        "[req]\ndistinguished_name=dn\n[dn]\n"
        "[ca]\nbasicConstraints=critical,CA:TRUE\n"
        "keyUsage=critical,keyCertSign,cRLSign\nsubjectKeyIdentifier=hash\n"
        "[srv]\nsubjectAltName=IP:127.0.0.1\nbasicConstraints=CA:FALSE\n"
        "keyUsage=critical,digitalSignature,keyEncipherment\n"
        "extendedKeyUsage=serverAuth\nsubjectKeyIdentifier=hash\n"
        "authorityKeyIdentifier=keyid\n",
        encoding="utf-8",
    )

    def openssl(*args: str) -> None:
        subprocess.run(["openssl", *args], cwd=where, check=True, capture_output=True)

    openssl("req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", "ca.key",
            "-out", "ca.pem", "-days", "2", "-subj", "/CN=company CA",
            "-config", "x.cnf", "-extensions", "ca")  # fmt: skip
    openssl("req", "-newkey", "rsa:2048", "-nodes", "-keyout", "srv.key",
            "-out", "srv.csr", "-subj", "/CN=127.0.0.1")  # fmt: skip
    openssl("x509", "-req", "-in", "srv.csr", "-CA", "ca.pem", "-CAkey", "ca.key",
            "-CAcreateserial", "-out", "srv.pem", "-days", "2",
            "-extfile", "x.cnf", "-extensions", "srv")  # fmt: skip
    return where


class _Upstream(http.server.BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(REPLY)))
        self.end_headers()
        self.wfile.write(REPLY)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        pass


@pytest.fixture
def upstream(certificates: Path) -> Iterator[int]:
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Upstream)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certificates / "srv.pem", certificates / "srv.key")
    server.socket = context.wrap_socket(server.socket, server_side=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield server.server_address[1]
    server.shutdown()
    server.server_close()


@dataclass
class Company:
    """A company proxy: it answers `CONNECT host:port` and tunnels the bytes,
    and keeps each request line and its `Proxy-Authorization`."""

    port: int = 0
    asked: list[tuple[str, str | None]] = field(default_factory=list)


@pytest.fixture
def company() -> Iterator[Company]:
    seen = Company()
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    seen.port = listener.getsockname()[1]

    def tunnel(client: socket.socket) -> None:
        head = b""
        while b"\r\n\r\n" not in head:
            chunk = client.recv(4096)
            if not chunk:
                return
            head += chunk
        lines = head.split(b"\r\n\r\n", 1)[0].decode().split("\r\n")
        auth = next(
            (
                line.split(":", 1)[1].strip()
                for line in lines[1:]
                if line.lower().startswith("proxy-authorization:")
            ),
            None,
        )
        seen.asked.append((lines[0], auth))
        method, where, _ = lines[0].split(" ")
        if method != "CONNECT":
            client.sendall(b"HTTP/1.1 405 Not Allowed\r\n\r\n")
            client.close()
            return
        host, port = where.rsplit(":", 1)
        far = socket.create_connection((host, int(port)))
        client.sendall(b"HTTP/1.1 200 Connection established\r\n\r\n")
        ends = [client, far]
        while True:
            ready, _, _ = select.select(ends, [], [], 5)
            if not ready:
                break
            for end in ready:
                data = end.recv(65536)
                if not data:
                    far.close()
                    client.close()
                    return
                (far if end is client else client).sendall(data)

    def accept() -> None:
        while True:
            try:
                client, _ = listener.accept()
            except OSError:
                return
            threading.Thread(target=tunnel, args=(client,), daemon=True).start()

    threading.Thread(target=accept, daemon=True).start()
    yield seen
    listener.close()


def through(root: Path, upstream: int) -> tuple[int, str]:
    """One call of OpenAI's shape through a digline proxy started now, read
    with a client that itself uses no proxy."""
    running: Proxy = start_proxy(
        root=root,
        tenant="acme",
        app="support",
        port=0,
        upstream=[f"openai=https://127.0.0.1:{upstream}/v1"],
        episode_idle=0.5,
        timeout=5.0,
    )
    try:
        request = urllib.request.Request(
            f"{running.address}/v1/chat/completions",
            data=json.dumps(
                {"model": "m", "messages": [{"role": "user", "content": "q"}]}
            ).encode(),
            headers={"Content-Type": "application/json", "Authorization": "Bearer k"},
            method="POST",
        )
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with opener.open(request, timeout=10) as answer:
                return answer.status, answer.read().decode()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read().decode()
    finally:
        running.stop()


def test_https_proxy_carries_the_call_through_a_connect(
    tmp_path: Path,
    upstream: int,
    company: Company,
    certificates: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HTTPS_PROXY", f"http://ada:s%40cret@127.0.0.1:{company.port}")
    monkeypatch.setenv("SSL_CERT_FILE", str(certificates / "ca.pem"))
    status, body = through(tmp_path, upstream)
    assert status == 200, body
    assert json.loads(body)["choices"][0]["message"]["content"] == "hi"
    [(line, auth)] = company.asked
    assert line == f"CONNECT 127.0.0.1:{upstream} HTTP/1.1"
    # `ada:s@cret`, the password unquoted from the URL.
    assert auth == "Basic YWRhOnNAY3JldA=="


def test_no_proxy_sends_a_named_host_around_it(
    tmp_path: Path,
    upstream: int,
    company: Company,
    certificates: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HTTPS_PROXY", f"http://127.0.0.1:{company.port}")
    monkeypatch.setenv("NO_PROXY", "localhost,127.0.0.1")
    monkeypatch.setenv("SSL_CERT_FILE", str(certificates / "ca.pem"))
    status, body = through(tmp_path, upstream)
    assert status == 200, body
    assert company.asked == []


def test_requests_ca_bundle_names_the_company_ca(
    tmp_path: Path, upstream: int, certificates: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """botocore's convention, read beside Python's default store."""
    monkeypatch.setenv("REQUESTS_CA_BUNDLE", str(certificates / "ca.pem"))
    status, body = through(tmp_path, upstream)
    assert status == 200, body


def test_without_the_company_ca_the_certificate_is_refused(
    tmp_path: Path, upstream: int
) -> None:
    """The control for the two above: the CA is what made them pass."""
    status, body = through(tmp_path, upstream)
    assert status == 502
    assert "CERTIFICATE_VERIFY_FAILED" in body


@pytest.mark.parametrize(
    ("no_proxy", "host", "bypassed"),
    [
        ("", "api.openai.com", False),
        ("*", "api.openai.com", True),
        ("openai.com", "api.openai.com", True),
        (".openai.com", "api.openai.com", True),
        ("openai.com", "notopenai.com", False),
        ("internal:8080, api.anthropic.com", "api.anthropic.com", True),
    ],
)
def test_no_proxy_is_read_as_curl_reads_it(
    no_proxy: str, host: str, bypassed: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.example:3128")
    monkeypatch.setenv("NO_PROXY", no_proxy)
    found = upstream_proxy(host)
    assert (found is None) == bypassed
    if found is not None:
        assert (found.hostname, found.port) == ("proxy.example", 3128)
