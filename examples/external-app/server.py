"""Stands in for the application under test — the one that is not Python.

A JVM service, a Go binary, something behind a gateway: digline cannot import
it and does not need to. It needs a body it can post and a field it can read.

Here that application is twenty lines of `http.server` so the example runs on
its own. Yours is already running somewhere; point `URL` at it and delete this
file.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

#: What the "Java" service replies. Deterministic, so the example is too.
ROUTING = {
    "card blocked": ("fraud", 0.94),
    "invoice wrong amount": ("billing", 0.88),
    "cannot log in": ("access", 0.91),
    "delivery late": ("logistics", 0.86),
    "want to close account": ("retention", 0.79),
}


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802 - the name http.server dispatches on
        length = int(self.headers.get("Content-Length") or 0)
        asked = json.loads(self.rfile.read(length).decode("utf-8"))
        text = str(asked.get("text", "")).lower()
        queue, confidence = ROUTING.get(text, ("general", 0.5))
        body = json.dumps(
            {
                "data": {"queue": queue, "confidence": confidence},
                "usage": {"cost_usd": 0.0009, "elapsed_ms": 41.0},
            }
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        """Quiet: the suite's output is what the reader is here for."""


def start() -> str:
    """Serve on an ephemeral port in a background thread, and return the URL."""
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{httpd.server_address[1]}/classify"
