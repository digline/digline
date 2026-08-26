"""The application under test — the part you would replace with your own.

Deterministic on purpose: a quickstart that needs an API key is a quickstart
nobody runs. Where this returns a canned answer, yours would call a model.
"""

from __future__ import annotations

from dataclasses import dataclass

SYSTEM_PROMPT = (
    "You are Northwind Support. Answer the customer's question in at most "
    "three sentences, and sign off as Northwind Support."
)

_ANSWERS = {
    "where-is-my-order": (
        "Your order 4821 left our warehouse on Tuesday and arrives Thursday. "
        "You will get a tracking link by email. — Northwind Support"
    ),
    "how-do-i-return": (
        "You can return any item within 30 days, unused and in its box. "
        "Start the return from your account page. — Northwind Support"
    ),
    "is-it-waterproof": (
        "The case is rated IPX4, so it handles splashes but not immersion. "
        "We do not recommend swimming with it. — Northwind Support"
    ),
}


@dataclass(frozen=True)
class Reply:
    """What the application gives back. Yours probably has these three too."""

    text: str
    cost_usd: float
    latency_ms: float


def render_prompt(question_id: str) -> str:
    """The prompt actually sent. digline records it so a judge can see the
    question, not only the answer."""
    return f"{SYSTEM_PROMPT}\n\nCustomer question: {question_id}"


def reply(question_id: str) -> Reply:
    """Replace the body with a call to your model."""
    text = _ANSWERS[question_id]
    return Reply(text=text, cost_usd=0.004 + 0.001 * len(text) / 100, latency_ms=180.0)
