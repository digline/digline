"""The stand-in for Anthropic that `docs/stories/from-the-ide-with-mcp.md` ran
against: the application's categories and the judge's scores, from tables.

It speaks the Messages API on 127.0.0.1, so the real `anthropic` client reaches
it through `ANTHROPIC_BASE_URL`, in the application and in the judge the MCP
server runs. Every answer, score and token count the story prints is this
file's. No call leaves the machine.

    python tests/_story_ide_stand_in.py 18791
"""

from __future__ import annotations

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

__all__ = ["ANSWERS", "serve"]

#: What the application answers, by the ticket. The shoes are answered wrong.
ANSWERS = {
    "Where is my refund for the blue jacket?": "refund",
    "The parcel never arrived.": "delivery",
    "How do I change my password?": "account",
    "I want my money back for the shoes.": "other",
    "Can I return a gift without the receipt?": "refund",
}

#: The category the judge takes for right, by the ticket. It is wrong about the
#: gift, which a person reads as a refund: that is day two's contradiction.
RIGHT = {
    "Where is my refund for the blue jacket?": "refund",
    "The parcel never arrived.": "delivery",
    "How do I change my password?": "account",
    "I want my money back for the shoes.": "refund",
    "Can I return a gift without the receipt?": "other",
}


def _text(content: Any) -> str:
    """A message's text: a string, or the text of its text blocks."""
    if isinstance(content, str):
        return content
    return "".join(str(block["text"]) for block in content if block["type"] == "text")


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        return

    def do_POST(self) -> None:  # noqa: N802 - the stdlib's name
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        messages = body["messages"]
        prompt = _text(messages[0]["content"])
        # The judge sends a prefill, `{`, as the last message: an assistant's.
        if messages[-1]["role"] == "assistant":
            ticket = next((t for t in RIGHT if t in prompt), None)
            right = ticket is not None and ANSWERS[ticket] == RIGHT[ticket]
            text = (
                f'"score": {1 if right else 0}, "reason": "The category is '
                f'{"right" if right else "wrong"} for the ticket."}}'
            )
            usage = {"input_tokens": 21, "output_tokens": 6}
        else:
            text = ANSWERS.get(prompt, "other")
            usage = {"input_tokens": 18, "output_tokens": 2}
        reply = {
            "id": "msg_standin",
            "type": "message",
            "role": "assistant",
            "model": body["model"],
            "content": [{"type": "text", "text": text}],
            "stop_reason": "end_turn",
            "stop_sequence": None,
            "usage": usage,
        }
        data = json.dumps(reply).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def serve(port: int = 0) -> ThreadingHTTPServer:
    """The stand-in, answering on a thread; `shutdown()` stops it."""
    server = ThreadingHTTPServer(("127.0.0.1", port), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1])), _Handler).serve_forever()
