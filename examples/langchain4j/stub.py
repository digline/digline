"""Stands in for the Java service, so this example runs with no JVM.

It answers the shape both services answer — `data`, `usage`, `config` — with
fixed text, so the cycle below is deterministic and free. It exists for the same
reason `app-spring/` and `app-quarkus/` do: one of them is the thing you
replace, and this is the other one.

Point `URL` in `suite.py` at your own service and delete this file. Nothing
else changes — which is the claim the example is here to make.
"""

from __future__ import annotations

import itertools
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

#: What the assistant replies. Deterministic, so the example is too.
ANSWERS = {
    "I ordered a kettle on Monday, order 4821. Where is it?": (
        "Order 4821 left our warehouse on Tuesday and is due Thursday. "
        "You will get a tracking link by email as soon as it is scanned. "
        "— Northwind Support"
    ),
    "The jacket does not fit. How do I send it back?": (
        "You can return any unworn item within 30 days. Print a label from "
        "your order page and drop the parcel at any pickup point. "
        "— Northwind Support"
    ),
    "Is the trail backpack waterproof or only water resistant?": (
        "The trail backpack is water resistant, not waterproof: it handles "
        "rain but should not be submerged. — Northwind Support"
    ),
    "Do you deliver to Palermo, and does it cost extra?": (
        "Yes, we deliver to Palermo. Standard delivery is free over 40 euro "
        "and takes one extra day for the islands. — Northwind Support"
    ),
    "I want to cancel my Northwind Plus subscription today.": (
        "You can cancel Northwind Plus from your account page and it stops at "
        "the end of the current period. — Northwind Support"
    ),
}

#: The four values the Java service reports about itself. Same keys, same
#: types: this is the contract, not a simplification of it.
CONFIG = {
    "provider": "openai",
    "model": "gpt-4o-mini",
    "temperature": 0.0,
    "max_tokens": 512,
}

#: The counts behind the price, under their own key so `usage_path` can read
#: them without meeting `cost_usd`: digline closes that object to its own count
#: names. Fixed, because the stub is deterministic. A real service reports what
#: the provider told it — and leaves the key out where it was told nothing,
#: rather than reporting a zero it did not measure.
TOKENS = {"input_tokens": 190, "output_tokens": 38}


#: The second witness. One line on standard error for every call this stub
#: receives, and nothing when it receives none, so a sentence such as
#: "Nothing was called" can be checked against more than digline's word. The
#: same format in every example's stub; the liveness `HEAD` is not a call.
_CALLS = itertools.count(1)
_COUNTING = threading.Lock()


def _witness(path: str, field: str, value: str) -> None:
    with _COUNTING:
        number = next(_CALLS)
    sys.stderr.write(f"stub: call {number} POST {path} {field}={value!r}\n")
    sys.stderr.flush()


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802 - the name http.server dispatches on
        length = int(self.headers.get("Content-Length") or 0)
        asked = json.loads(self.rfile.read(length).decode("utf-8"))
        question = str(asked.get("question", ""))
        _witness(self.path, "question", question)
        body = json.dumps(
            {
                "data": ANSWERS.get(question, "I am not sure. — Northwind Support"),
                "usage": {
                    "cost_usd": 0.00021,
                    "elapsed_ms": 380.0,
                    "tokens": TOKENS,
                },
                "config": CONFIG,
            }
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        """`http.server`'s own access log stays off: `_witness` writes the one
        line per call, in the format every example's stub shares."""


def start() -> str:
    """Serve on an ephemeral port in a background thread, and return the URL."""
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{httpd.server_address[1]}/evaluate"
