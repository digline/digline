"""The stand-in for Anthropic that `docs/walkthroughs/python-three-prompts.md` ran
against: the application's three prompts and the judge, answered from tables.

It speaks the Messages API on 127.0.0.1, so the real `anthropic` client reaches
it through `ANTHROPIC_BASE_URL` and nothing else changes. Every answer, score
and token count the story prints is this file's. No call leaves the machine.

    python tests/_story_python_stand_in.py 18791
"""

from __future__ import annotations

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

#: What the application's three prompts answer, by the user's message.
SCREENING = {
    "CV: five years of Python and Django, PostgreSQL.\nJob: backend developer": (
        '{"fit": "yes", "reason": "Python and Django are the job."}'
    ),
    "CV: graphic designer, Figma and Illustrator.\nJob: backend developer": (
        '{"fit": "no", "reason": "No backend work in the CV."}'
    ),
    "CV: two years of Java and Spring.\nJob: backend developer": (
        '{"fit": "yes", "reason": "Java is a backend language."}'
    ),
}

AD = {
    "Role: backend developer. City: Milan. Work: hybrid.": (
        "We are hiring a backend developer in Milan. The work is hybrid, "
        "three days in the office."
    ),
    "Role: data engineer. City: Rome. Work: remote.": (
        "Join us as a data engineer, from Rome or anywhere in Italy. The work "
        "is fully remote."
    ),
}

#: The ad prompt's second version asks for the salary band.
AD_WITH_SALARY = {
    "Role: backend developer. City: Milan. Work: hybrid.": (
        "We are hiring a backend developer in Milan, hybrid, three days in the "
        "office. The salary band is 45,000 to 55,000 euros."
    ),
    "Role: data engineer. City: Rome. Work: remote.": (
        "Join us as a data engineer, fully remote from Rome. The salary band "
        "is 50,000 to 60,000 euros."
    ),
}

REPLY = {
    "When will I hear back about the backend role?": (
        "Thank you for applying. We answer every candidate within ten working days."
    ),
    "Can I apply for two roles at once?": (
        "Yes. Apply to each role on its own page, and we read each application "
        "separately."
    ),
}

#: The answers the judge scores 0. Everything else it scores 1.
WRONG = ("Java is a backend language",)

JUDGE_MARK = "You are grading the output of another system against a rubric."


def _text(content: Any) -> str:
    if isinstance(content, str):
        return content
    return "".join(part.get("text", "") for part in content)


def answer(body: dict[str, Any]) -> tuple[str, int, int]:
    """The text, and the input and output token counts, for one request."""
    system = _text(body.get("system", ""))
    asked = _text(body["messages"][0]["content"])
    if JUDGE_MARK in system:
        score = 0 if any(wrong in asked for wrong in WRONG) else 1
        reason = "the fit is wrong" if score == 0 else "it answers the question"
        # The judge's reply is the continuation of its prefill, "{".
        return f'"score": {score}, "reason": "{reason}"}}', 180, 14
    if "salary band" in system:
        table = AD_WITH_SALARY
    elif asked in AD:
        table = AD
    elif asked in SCREENING:
        table = SCREENING
    else:
        table = REPLY
    return table.get(asked, "I do not know."), 40, 20


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802 — the name http.server calls
        length = int(self.headers.get("content-length", "0"))
        body = json.loads(self.rfile.read(length))
        text, tokens_in, tokens_out = answer(body)
        payload = json.dumps(
            {
                "id": "msg_stand_in",
                "type": "message",
                "role": "assistant",
                "model": body.get("model", "claude-haiku-4-5"),
                "content": [{"type": "text", "text": text}],
                "stop_reason": "end_turn",
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
