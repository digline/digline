"""Stands in for your application, so this example runs with no key and no JVM.

It answers the shape a real service answers — `data`, `usage`, `config` — with
fixed text, so the cycle is deterministic and free. Point `url` in `suite.toml`
at your own service and delete this file; nothing else changes, which is the
claim this example exists to make.

Run it in one terminal:

    python stub.py

and the cycle in another. It has to be started from outside, and that is not an
oversight: a suite that is data cannot import anything, so the application under
test is genuinely somebody else's process. In CI that is two lines, and
`.github/workflows/check.yml` has them.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

#: Fixed, because `suite.toml` names it. A data file has nowhere to put an
#: ephemeral port, and that is the trade: the URL is written down, once, where
#: a reader can see it.
PORT = 8730

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
}

#: What the service says about the model that answered — the same keys, the same
#: types a real one reports. digline records this per run and tells you when it
#: moves, because a score that changed under a model that also changed is two
#: facts, not one (ADR 0005 §8).
CONFIG = {
    "provider": "openai",
    "model": "gpt-4o-mini",
    "temperature": 0.0,
    "max_tokens": 512,
}


class Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802 - the name http.server dispatches on
        length = int(self.headers.get("Content-Length") or 0)
        asked = json.loads(self.rfile.read(length).decode("utf-8"))
        question = str(asked.get("question", ""))
        body = json.dumps(
            {
                "data": {
                    "answer": ANSWERS.get(
                        question, "I am not sure. — Northwind Support"
                    )
                },
                "usage": {"cost_usd": 0.00021, "elapsed_ms": 380.0},
                "config": CONFIG,
            }
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_HEAD(self) -> None:  # noqa: N802 - the name http.server dispatches on
        """digline asks before the first case whether anything is listening, so
        that a service that is down fails once rather than once per case."""
        self.send_response(200)
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        """Quiet: the suite's output is what the reader is here for."""


def main() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"stub listening on http://127.0.0.1:{PORT}/answer")
    server.serve_forever()


if __name__ == "__main__":
    main()
