"""`digline record proxy`: the recorder for an application in any language,
which points its SDK at it. (ADR 0062 §3)

The proxy listens on `127.0.0.1` alone, forwards each call to its provider,
passes the reply on as it arrives, and records the call once the reply has
ended, with the recorder an application in Python wraps its client with:
the same switch, the same writer, the same digest and the same counts
(`digline.recorder.WireRecorder`).

**Which map reads a call is its route**, the path, as each plugin's entry in
`digline.recording_wire` says (`/chat/completions` is OpenAI's, `/v1/messages`
Anthropic's). **Where it goes** is `--upstream ROUTE=URL` where that names the
route; otherwise the provider whose SDK the request's headers show, the
route's own first (`anthropic-version` or `x-api-key` Anthropic's, a bearer
key without them OpenAI's: both SDKs send their key as a bearer), at that
provider's own address; otherwise the route's. A call over a path no plugin
reads is forwarded the same way and not recorded.

**The suite, the app and the episode** come from `X-Digline-Suite`,
`X-Digline-App` and `X-Digline-Episode`, or the suite from a `/suite/<name>/`
prefix of the path, and none of them is forwarded. `X-Digline-Case` gives an
episode its case. A call that names no suite is `_unassigned`, and its call
site is the SDK's `User-Agent` and the path.

**What it never does**: read, log or write the application's key, which
travels in the application's own headers; change a reply's body or headers,
beyond the hop-by-hop ones a connection owns; record a reply that is not a
200, which passes on as it came; or hold a call silently: an upstream that
does not answer within `TIMEOUT` seconds is a 504 to the application.
"""

from __future__ import annotations

import gzip
import http.client
import json
import threading
import time
import zlib
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.metadata import entry_points
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlsplit

from digline.host.errors import UsageError
from digline.recorder import WIRE_GROUP, RecordingWire, WireRecorder

__all__ = [
    "DEFAULT_PORT",
    "EPISODE_IDLE",
    "PACKAGES",
    "TIMEOUT",
    "Proxy",
    "load_wires",
    "start_proxy",
]

#: Where the proxy listens when `--port` is not given.
DEFAULT_PORT = 8787

#: Seconds an upstream has to answer, and between two pieces of a stream:
#: what the SDKs wait by default.
TIMEOUT = 600.0

#: Seconds without a call after which an episode off the wire is closed and
#: written, when `--episode-idle` is not given.
EPISODE_IDLE = 30.0

#: The plugin that reads each route, for the sentence that says which to
#: install.
PACKAGES: Mapping[str, str] = {
    "openai": "digline-openai",
    "anthropic": "digline-anthropic",
    "bedrock": "digline-bedrock",
}

#: Owned by the connection, never passed on in either direction (RFC 9110's
#: hop-by-hop fields), with `host`, which names the proxy, and the length,
#: which `http.client` writes for the body it sends.
_HOP = frozenset(
    {
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
        "host",
        "content-length",
    }
)

_OURS = "x-digline-"


def load_wires() -> dict[str, RecordingWire]:
    """Every route a plugin reads, loaded now, its SDK with it. A plugin that
    cannot be loaded leaves its route out, and the start says so."""
    found: dict[str, RecordingWire] = {}
    for entry in sorted(entry_points(group=WIRE_GROUP), key=lambda e: e.name):
        wire = cast(RecordingWire, entry.load())
        wire.load()
        found[entry.name] = wire
    return found


@dataclass(frozen=True, slots=True)
class Proxy:
    """A running proxy: its address, its server and what it records with."""

    address: str
    port: int
    server: ThreadingHTTPServer
    recorder: WireRecorder
    wires: Mapping[str, RecordingWire]
    upstreams: Mapping[str, str]

    def stop(self) -> None:
        """Stop listening, then write every open episode and the counts."""
        self.server.shutdown()
        self.server.server_close()
        self.recorder.close()


def upstreams_of(
    given: Sequence[str], wires: Mapping[str, RecordingWire]
) -> dict[str, str]:
    """`--upstream ROUTE=URL`, each, checked: a route a plugin reads, and an
    http or https address."""
    found: dict[str, str] = {}
    for item in given:
        route, sep, url = item.partition("=")
        if not sep or not route or not url:
            raise UsageError(f"--upstream {item}: write it as ROUTE=URL")
        if route not in wires:
            known = ", ".join(sorted(wires)) or "none"
            raise UsageError(
                f"--upstream {item}: no plugin reads the route {route!r}; the "
                f"routes read here are {known}"
            )
        if urlsplit(url).scheme not in ("http", "https") or not urlsplit(url).hostname:
            raise UsageError(f"--upstream {item}: the address is not http or https")
        found[route] = url.rstrip("/")
    return found


def start_proxy(
    *,
    root: Path,
    tenant: str,
    app: str,
    port: int,
    upstream: Sequence[str] = (),
    episode_idle: float = EPISODE_IDLE,
    timeout: float = TIMEOUT,
    wires: Mapping[str, RecordingWire] | None = None,
) -> Proxy:
    """Load the plugins, read the switch, and listen on `127.0.0.1:port`, in
    threads of its own. `port=0` takes a free one."""
    loaded = dict(wires) if wires is not None else load_wires()
    upstreams = upstreams_of(upstream, loaded)
    recorder = WireRecorder(
        tenant=tenant, app=app, root=root, episode_idle=episode_idle
    )

    class Handler(_Handler):
        pass

    Handler.recorder = recorder
    Handler.wires = loaded
    Handler.upstreams = upstreams
    Handler.timeout_s = timeout
    try:
        server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    except OSError as exc:
        raise UsageError(
            f"digline record proxy cannot listen on 127.0.0.1:{port}: {exc.strerror}"
        ) from None
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    threading.Thread(
        target=_closing, args=(server, recorder, episode_idle), daemon=True
    ).start()
    bound = server.server_address[1]
    return Proxy(
        address=f"http://127.0.0.1:{bound}",
        port=bound,
        server=server,
        recorder=recorder,
        wires=loaded,
        upstreams=upstreams,
    )


def _closing(server: ThreadingHTTPServer, recorder: WireRecorder, idle: float) -> None:
    """Write the episodes gone idle, a few times in each idle interval."""
    step = max(min(idle / 4, 1.0), 0.01)
    while server.socket.fileno() != -1:
        time.sleep(step)
        recorder.close_idle()


class _Handler(BaseHTTPRequestHandler):
    """One connection from the application: every method forwarded."""

    protocol_version = "HTTP/1.1"
    recorder: WireRecorder
    wires: Mapping[str, RecordingWire]
    upstreams: Mapping[str, str]
    timeout_s: float

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        """Nothing logged: a request line names a path, and a header could
        carry a key."""

    def do_GET(self) -> None:  # noqa: N802
        self._forward()

    def do_POST(self) -> None:  # noqa: N802
        self._forward()

    def do_PUT(self) -> None:  # noqa: N802
        self._forward()

    def do_PATCH(self) -> None:  # noqa: N802
        self._forward()

    def do_DELETE(self) -> None:  # noqa: N802
        self._forward()

    def _forward(self) -> None:
        started = time.perf_counter()
        body = self._body()
        headers = {key.lower(): value for key, value in self.headers.items()}
        ours = {k: _text(v) for k, v in headers.items() if k.startswith(_OURS)}
        path = self.path
        if path.startswith("/suite/"):
            # `/suite/<name>/v1/...` is `/v1/...` for the suite `<name>`, for
            # an application that can set a base URL and no header.
            name, _, rest = path[len("/suite/") :].partition("/")
            ours.setdefault(_OURS + "suite", name)
            path = "/" + rest
        route = next(
            (name for name, wire in self.wires.items() if wire.matches(path)), None
        )
        where = self._upstream(route, headers)
        if where is None:
            self._refuse(
                502,
                "no upstream for this call: no plugin reads its path, and its "
                "key is no provider's a plugin knows. Installed: "
                + (", ".join(sorted(self.wires)) or "none")
                + ". The others come with "
                + ", ".join(
                    package
                    for name, package in sorted(PACKAGES.items())
                    if name not in self.wires
                ),
            )
            return
        url, owner = where
        target = urlsplit(url)
        own = self.wires[owner].base
        rest = path[len(own) :] if own and path.startswith(own) else path
        sent = {
            key: value
            for key, value in self.headers.items()
            if key.lower() not in _HOP and not key.lower().startswith(_OURS)
        }
        suite = ours.get(_OURS + "suite") or None
        app = ours.get(_OURS + "app") or None
        episode = ours.get(_OURS + "episode") or None
        records = route is not None and self.command == "POST"
        if records:
            self.recorder.begin(episode)
        connection = (
            http.client.HTTPSConnection
            if target.scheme == "https"
            else http.client.HTTPConnection
        )(target.hostname or "", target.port, timeout=self.timeout_s)
        try:
            try:
                connection.request(
                    self.command,
                    target.path.rstrip("/") + rest,
                    body=body or None,
                    headers=sent,
                )
                reply = connection.getresponse()
            except TimeoutError:
                self._refuse(
                    504,
                    f"the upstream did not answer within {self.timeout_s:g} seconds",
                )
                self._missed(records, "upstream timeout", suite, app, episode)
                return
            except OSError as exc:
                self._refuse(
                    502,
                    "the upstream cannot be reached: "
                    + (exc.strerror or type(exc).__name__),
                )
                self._missed(records, "upstream unreachable", suite, app, episode)
                return
            kept = self._pass_on(reply)
        finally:
            connection.close()
        if kept is None:
            self._missed(records, "stream abandoned", suite, app, episode)
            return
        if not records:
            if route is None and self.command == "POST":
                # A call the proxy passed on and no plugin reads: said, so a
                # route nobody maps shows in the status rather than nowhere.
                self.recorder.missed(
                    "route not read", suite=suite, app=app, episode=None
                )
            return
        if reply.status != 200:
            # An error passes on as it came and is neither recorded nor
            # counted, as an SDK's exception is not in process.
            self.recorder.end(episode)
            return
        self._record(
            cast(str, route),
            body,
            kept,
            reply,
            (time.perf_counter() - started) * 1000.0,
            suite,
            app,
            episode,
            ours.get(_OURS + "case"),
            headers.get("user-agent"),
            path,
        )

    def _missed(
        self,
        records: bool,
        reason: str,
        suite: str | None,
        app: str | None,
        episode: str | None,
    ) -> None:
        if records:
            self.recorder.missed(reason, suite=suite, app=app, episode=episode)

    def _upstream(
        self, route: str | None, headers: Mapping[str, str]
    ) -> tuple[str, str] | None:
        """Where the call goes, and whose route's base the path is read
        against: `--upstream` for the route; else the provider whose key the
        request carries; else the route's own provider."""
        if route is not None and route in self.upstreams:
            return self.upstreams[route], route
        # The route's own provider first: a key two providers' SDKs send alike
        # goes where the path already says.
        order = sorted(self.wires, key=lambda name: name != route)
        for name in order:
            wire = self.wires[name]
            if wire.claims(headers):
                return self.upstreams.get(name, wire.upstream), name
        if route is not None:
            return self.wires[route].upstream, route
        return None

    def _body(self) -> bytes:
        length = self.headers.get("Content-Length")
        if length is not None:
            return self.rfile.read(int(length))
        if "chunked" in (self.headers.get("Transfer-Encoding") or "").lower():
            return b"".join(_chunks(self.rfile))
        return b""

    def _pass_on(self, reply: http.client.HTTPResponse) -> bytes | None:
        """The reply, to the application, as it arrives: headers as they came
        but the connection's own, and the body unchanged. What was passed on
        is kept for the recording; `None` where the application closed first."""
        streamed = reply.getheader("Content-Length") is None
        kept = bytearray()
        try:
            self.send_response_only(reply.status, reply.reason)
            for key, value in reply.getheaders():
                if key.lower() not in _HOP:
                    self.send_header(key, value)
            if not streamed:
                data = reply.read()
                kept += data
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                self.wfile.flush()
                return bytes(kept)
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            self.wfile.flush()
            while chunk := reply.read1(65536):
                kept += chunk
                self.wfile.write(b"%x\r\n%s\r\n" % (len(chunk), chunk))
                self.wfile.flush()
            self.wfile.write(b"0\r\n\r\n")
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            self.close_connection = True
            return None
        return bytes(kept)

    def _refuse(self, status: int, message: str) -> None:
        """digline's own answer, where the upstream gave none: JSON in the
        shape both SDKs read an error from, so the application's exception
        says what happened."""
        data = json.dumps(
            {
                "type": "error",
                "error": {
                    "type": "digline_record_proxy",
                    "message": f"digline record proxy: {message}",
                },
            }
        ).encode("utf-8")
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True

    def _record(
        self,
        route: str,
        body: bytes,
        kept: bytes,
        reply: http.client.HTTPResponse,
        elapsed_ms: float,
        suite: str | None,
        app: str | None,
        episode: str | None,
        case: str | None,
        agent: str | None,
        path: str,
    ) -> None:
        wire = self.wires[route]
        try:
            parsed: object = json.loads(body)
            if not isinstance(parsed, dict):
                raise ValueError
        except ValueError:
            self.recorder.missed("not JSON", suite=suite, app=app, episode=episode)
            return
        try:
            text = _decoded(kept, reply.getheader("Content-Encoding"))
        except ValueError:
            self.recorder.missed(
                "content encoding", suite=suite, app=app, episode=episode
            )
            return
        request = cast(dict[str, Any], parsed)
        streamed = "text/event-stream" in (reply.getheader("Content-Type") or "")
        try:
            mapped = wire.map
            if streamed:
                reading = cast(Any, mapped).reading(request)
                for event in _events(text):
                    reading.add(wire.event(event))
                completion = reading.completion(None)
                reply_object = None
            else:
                completion = None
                reply_object = wire.reply(json.loads(text))
        except Exception:  # noqa: BLE001 — a reply the map cannot read is its reason
            self.recorder.missed("map", suite=suite, app=app, episode=episode)
            return
        self.recorder.record(
            mapped,
            request,
            reply=reply_object,
            completion=completion,
            elapsed_ms=elapsed_ms,
            suite=suite,
            app=app,
            site=None if suite is not None else f"{agent or 'no User-Agent'} {path}",
            episode=episode,
            case=_case(case),
        )


def _text(value: str) -> str:
    """A header's value as the application wrote it: `http.server` reads
    headers as Latin-1, and an application that sent UTF-8 meant UTF-8."""
    try:
        return value.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return value


def _case(value: str | None) -> Mapping[str, object] | None:
    """`X-Digline-Case`: a JSON object is the case; any other value, JSON or
    text, is the case's `text`."""
    if value is None:
        return None
    try:
        parsed = json.loads(value)
    except ValueError:
        return {"text": value}
    if isinstance(parsed, dict):
        return cast(dict[str, object], parsed)
    return {"text": value}


def _decoded(data: bytes, encoding: str | None) -> str:
    """The reply's text, for reading it: what was passed on is unchanged."""
    kind = (encoding or "identity").strip().lower()
    if kind == "identity":
        raw = data
    elif kind == "gzip":
        raw = gzip.decompress(data)
    elif kind == "deflate":
        raw = zlib.decompress(data)
    else:
        raise ValueError(kind)
    return raw.decode("utf-8")


def _events(text: str) -> Iterator[object]:
    """The JSON of each server-sent event, in order: its `data:` lines joined.
    OpenAI's closing `[DONE]` is not an event."""
    for block in text.replace("\r\n", "\n").split("\n\n"):
        data = "\n".join(
            line[len("data:") :].lstrip(" ")
            for line in block.split("\n")
            if line.startswith("data:")
        )
        if data and data != "[DONE]":
            yield json.loads(data)


def _chunks(stream: Any) -> Iterator[bytes]:
    """A request body sent chunked, read whole."""
    while True:
        size = int(stream.readline().split(b";")[0].strip() or b"0", 16)
        if size == 0:
            stream.readline()
            return
        yield stream.read(size)
        stream.readline()
