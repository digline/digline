"""The stand-in for Anthropic that `docs/walkthroughs/an-agent.md` ran against: the
agent's model and the judge, answered from tables.

It speaks the Messages API on 127.0.0.1, so the real `anthropic` client reaches
it through `ANTHROPIC_BASE_URL` and nothing else changes. For the agent it
answers by the ticket and by how many tool results the conversation already
holds: first the tool calls the table names, one reply each, then the final
text. Every answer, tool call, score and token count the story prints is this
file's. No call leaves the machine.

    python tests/_story_agent_stand_in.py 18797
"""

from __future__ import annotations

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, cast

#: By ticket: the tool calls the model asks for, one reply each, in order,
#: and the text it ends the turn with.
TURNS: dict[str, tuple[list[tuple[str, dict[str, Any]]], str]] = {
    "Where is my order 42?": (
        [("lookup_order", {"order": "42"})],
        "Order 42 shipped on 3 November and arrives on Friday.",
    ),
    "Where is my order 17?": (
        [("lookup_order", {"order": "17"})],
        "Order 17 is being packed and ships tomorrow.",
    ),
    "How long do I have to return a jacket?": (
        [],
        "You can return it within 14 days of delivery.",
    ),
    "Where is my order 99?": (
        [("lookup_order", {"order": "99"})],
        "I could not find order 99.",
    ),
    "Order 42 arrived torn. I want my money back.": (
        [("issue_refund", {"order": "42"})],
        "I have refunded order 42. The money is back on your card in 5 days.",
    ),
}

#: The answers the judge scores 0. Everything else it scores 1.
WRONG = ("within 14 days",)

JUDGE_MARK = "You are grading the output of another system against a rubric."


def _text(content: Any) -> str:
    if isinstance(content, str):
        return content
    parts = [cast(dict[str, Any], part) for part in content if isinstance(part, dict)]
    return "".join(str(part.get("text", "")) for part in parts)


def _results(messages: list[dict[str, Any]]) -> int:
    """How many tool results the conversation already sent back."""
    return sum(
        1
        for message in messages
        if message["role"] == "user" and not isinstance(message["content"], str)
        for part in message["content"]
        if part.get("type") == "tool_result"
    )


def answer(body: dict[str, Any]) -> tuple[list[dict[str, Any]], str, int, int]:
    """The content blocks, the stop reason, and the token counts."""
    system = _text(body.get("system", ""))
    messages = body["messages"]
    asked = _text(messages[0]["content"])
    if JUDGE_MARK in system:
        score = 0 if any(wrong in asked for wrong in WRONG) else 1
        reason = "the policy is 30 days" if score == 0 else "it answers the ticket"
        # The judge's reply is the continuation of its prefill, "{".
        text = f'"score": {score}, "reason": "{reason}"}}'
        return [{"type": "text", "text": text}], "end_turn", 180, 14
    calls, final = TURNS.get(asked, ([], "I do not know."))
    done = _results(messages)
    if done < len(calls):
        name, arguments = calls[done]
        block = {
            "type": "tool_use",
            "id": f"toolu_{done}",
            "name": name,
            "input": arguments,
        }
        return [block], "tool_use", 120, 30
    return [{"type": "text", "text": final}], "end_turn", 160, 25


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802 — the name http.server calls
        length = int(self.headers.get("content-length", "0"))
        body = json.loads(self.rfile.read(length))
        content, stop, tokens_in, tokens_out = answer(body)
        payload = json.dumps(
            {
                "id": "msg_stand_in",
                "type": "message",
                "role": "assistant",
                "model": body.get("model", "claude-haiku-4-5"),
                "content": content,
                "stop_reason": stop,
                "stop_sequence": None,
                "usage": {"input_tokens": tokens_in, "output_tokens": tokens_out},
            }
        ).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        return


def serve(port: int = 0) -> ThreadingHTTPServer:
    """The stand-in, started on a thread of its own; `server_port` says where."""
    server = ThreadingHTTPServer(("127.0.0.1", port), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1])), _Handler)
    server.serve_forever()
