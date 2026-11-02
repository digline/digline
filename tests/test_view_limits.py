"""`digline view` bounds what one connection can cost it: the body it reads, and
the time it waits.

`do_POST` read `Content-Length` and then read that many bytes with no ceiling,
and `ThreadingHTTPServer` gave every connection a thread with no timeout. So a
caller that declared a large body, or sent half a request and went quiet, held
a thread for as long as it liked, and every such caller was one more.

**Each test asserts what the server decided, not that the connection ended.** A
connection ends for many reasons: the test client's own timeout, a handler that
raised, the server shutting down. So a refusal is read as its status and its
sentence. The one refusal with no response to read, a timeout while the headers
are still arriving, which the stdlib handles by closing, is read off the
server's own `log_error` and the time it took.

In-process rather than through `digline view` in a subprocess, because the
timeout under test is thirty seconds and a test has to be able to shorten it.
The handler class, the route and the checks are the ones `serve()` uses.
"""

from __future__ import annotations

import socket
import threading
import time
from collections.abc import Generator
from contextlib import contextmanager
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest
from tests._helpers import hand_over

from digline.cli.view import (
    MAX_FORM_BYTES,
    REQUEST_TIMEOUT_S,
    Launch,
    ViewHandler,
    self_netlocs,
)
from digline.host import load_suite
from digline.store import FileResultStore

#: The client's own patience, far above any timeout the server is given here,
#: so a client that gave up can never be mistaken for a server that did.
CLIENT_WAIT_S = 10.0
#: The server timeout the slow tests set, short enough to wait for.
SHORT_S = 0.5


@contextmanager
def promoting_view(repo: Path) -> Generator[tuple[int, str]]:
    """A promoting `ViewHandler` on an ephemeral port, and the `Cookie` of the
    browser that opened it: the state in which `/promote` reads a body."""
    suite, _loaded = load_suite(str(repo / "suite_qa.py"), root=repo)
    launch = Launch.minted()
    known: set[str] = set()
    handler = partial(
        ViewHandler,
        suite=suite,
        store=FileResultStore(str(repo)),
        known=known,
        launch=launch,
    )
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)  # pyright: ignore[reportArgumentType]
    port = int(httpd.server_address[1])
    known.update(self_netlocs("127.0.0.1", port))
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield port, hand_over(port, launch.key)
    finally:
        httpd.shutdown()
        httpd.server_close()


def head(port: int, cookie: str, length: bytes) -> bytes:
    """A same-origin `POST /promote` with a session, up to the blank line."""
    return (
        b"POST /promote HTTP/1.1\r\n"
        + f"Host: 127.0.0.1:{port}\r\n".encode()
        + f"Origin: http://127.0.0.1:{port}\r\n".encode()
        + f"Cookie: {cookie}\r\n".encode()
        + b"Content-Type: application/x-www-form-urlencoded\r\n"
        + b"Content-Length: "
        + length
        + b"\r\n\r\n"
    )


def exchange(
    port: int, sent: bytes, *, close_writing: bool = False
) -> tuple[bytes, float]:
    """Send `sent`, then read until the **server** closes; the answer and how
    long that took. A client timeout raises rather than returning, so every
    answer returned here is one the server chose to end."""
    # Before the connection, not after the send. A lower bound on wall time is
    # sound only if the window holds the whole of the server's wait: connecting,
    # sending, closing and delivering the close can only lengthen it. Started
    # after `sendall`, the window could open after the server's timer had
    # already started, and a merge-queue run on 2026-11-02 failed on exactly
    # that: `assert 0.5 <= 0.49933138500000496`.
    started = time.monotonic()
    with socket.create_connection(("127.0.0.1", port), timeout=CLIENT_WAIT_S) as sock:
        sock.sendall(sent)
        if close_writing:
            sock.shutdown(socket.SHUT_WR)
        chunks: list[bytes] = []
        while chunk := sock.recv(65536):
            chunks.append(chunk)
        return b"".join(chunks), time.monotonic() - started


def shorten(monkeypatch: pytest.MonkeyPatch) -> None:
    """Shorten the handler's own timeout, and refuse to give it one it lacks.

    **Setting it outright made the header test vacuous**: on `main`, where the
    handler has no timeout, the test supplied one and then measured the
    stdlib honouring it, and passed. Measured on 2026-09-28 by running this
    file against `main`'s `view.py`. What is under test is that the handler
    has a timeout, so a handler without one fails here.
    """
    assert ViewHandler.timeout is not None, "the handler has no timeout to shorten"
    monkeypatch.setattr(ViewHandler, "timeout", SHORT_S)


def status_of(answer: bytes) -> int:
    return int(answer.split(b" ", 2)[1])


# --------------------------------------------------------------------------- #
# The body: judged before it is read
# --------------------------------------------------------------------------- #


def test_a_declared_length_over_the_cap_is_refused_before_it_is_read(
    repo: Path,
) -> None:
    """**Fails on `main`**: there the server reads a gigabyte it will never get,
    and the client's own timeout is what ends the test."""
    with promoting_view(repo) as (port, cookie):
        answer, _ = exchange(port, head(port, cookie, b"1000000000") + b"run=x")
    assert status_of(answer) == 413
    assert f"at most {MAX_FORM_BYTES} bytes".encode() in answer
    assert b"declared 1000000000" in answer


def test_a_form_at_the_cap_is_read_and_judged_as_a_form(repo: Path) -> None:
    """The boundary, from the other side: exactly the cap is not refused for its
    size, and reaches the form's own refusal instead."""
    body = b"run=" + b"x" * (MAX_FORM_BYTES - len(b"run="))
    with promoting_view(repo) as (port, cookie):
        answer, _ = exchange(port, head(port, cookie, str(len(body)).encode()) + body)
    assert status_of(answer) == 400
    assert b"promote needs the baseline it replaces" in answer


@pytest.mark.parametrize(
    "length",
    [b"abc", b"-1", b"12x", "\N{SUPERSCRIPT TWO}".encode("latin-1")],
    ids=["letters", "negative", "trailing", "a-unicode-digit"],
)
def test_a_length_that_is_not_a_count_is_a_400_not_a_closed_connection(
    repo: Path, length: bytes
) -> None:
    """On `main`, `int()` raised on the first, third and fourth, and the
    browser saw the connection close; `-1` read until the caller hung up."""
    with promoting_view(repo) as (port, cookie):
        answer, _ = exchange(port, head(port, cookie, length) + b"run=x")
    assert status_of(answer) == 400
    assert b"no usable length" in answer


def test_a_body_shorter_than_it_declared_is_not_parsed(repo: Path) -> None:
    with promoting_view(repo) as (port, cookie):
        answer, _ = exchange(
            port, head(port, cookie, b"50") + b"run=x", close_writing=True
        )
    assert status_of(answer) == 400
    assert b"ended before its declared length" in answer


# --------------------------------------------------------------------------- #
# The time: a connection that goes quiet is let go
# --------------------------------------------------------------------------- #


def test_every_connection_has_a_finite_timeout() -> None:
    """The stdlib's default is `None`: no timeout at all."""
    assert ViewHandler.timeout == REQUEST_TIMEOUT_S
    assert 0 < REQUEST_TIMEOUT_S < float("inf")


def test_a_body_that_stops_arriving_is_answered_408(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """**Fails on `main`**: there the server waits for the other 45 bytes for
    ever, and the client gives up first.

    The elapsed time is asserted from below as well: an answer before the
    server's timeout would be something other than the timeout answering."""
    shorten(monkeypatch)
    with promoting_view(repo) as (port, cookie):
        answer, elapsed = exchange(port, head(port, cookie, b"50") + b"run=x")
    assert status_of(answer) == 408
    assert b"did not arrive in time" in answer
    assert SHORT_S <= elapsed < CLIENT_WAIT_S


def test_headers_that_stop_arriving_are_dropped_by_the_server(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """**Fails on `main`**: the thread waits for the rest of the headers for
    ever.

    Here the stdlib answers nothing: it catches the timeout, logs it and
    closes. So what is asserted is **the server's own record** that it timed
    out, beside the end of the connection. A handler that raised would log
    something else. A client that gave up would raise inside `exchange`."""
    logged: list[str] = []

    def record(self: ViewHandler, format: str, *args: object) -> None:
        logged.append(format % args)

    shorten(monkeypatch)
    monkeypatch.setattr(ViewHandler, "log_error", record)
    with promoting_view(repo) as (port, _cookie):
        answer, elapsed = exchange(
            port, b"POST /promote HTTP/1.1\r\nHost: 127.0.0.1\r\n"
        )
    assert answer == b""
    assert SHORT_S <= elapsed < CLIENT_WAIT_S
    assert len(logged) == 1
    assert logged[0].startswith("Request timed out")
