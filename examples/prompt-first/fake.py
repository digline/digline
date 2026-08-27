"""The provider, faked, so this runs with no key and no network.

Deterministic and *sensitive to the prompt*: change `prompts/system.txt` and the
answers change, which is the whole point of the example. A fake that ignored the
prompt would make every prompt look equally good.

`DIGLINE_LIVE=1` swaps it for the real SDK — see `suite.py`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

ANSWERS = {
    "Are you open on Sunday?": (
        "We are closed on Sundays, but you are very welcome Monday to Saturday."
    ),
    "Can you order a book you do not have?": (
        "Yes, we can order almost any title for you and it usually arrives "
        "within a week."
    ),
    "Do you gift wrap?": "We do, and it is free at the till whenever you ask.",
    "Do you have signed copies?": (
        "Sometimes we do after an author event, so it is worth asking at the counter."
    ),
    "How much is the new Rooney?": (
        "I would rather check that at the till than guess the price for you."
    ),
}

#: What the model does when the system prompt asks for it. One line in a prompt,
#: five answers changed — which is what the report is for.
RETURNS_LINE = " You can return any book within 30 days."


@dataclass
class _Block:
    text: str
    type: str = "text"


@dataclass
class _Usage:
    input_tokens: int = 180
    output_tokens: int = 40
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0


@dataclass
class _Reply:
    content: list[_Block]
    usage: _Usage = field(default_factory=_Usage)


class _Messages:
    def create(self, **request: Any) -> _Reply:
        prompt: str = request["messages"][0]["content"]
        system: str = request.get("system", "")
        question = prompt.split("Customer asks:", 1)[1].strip()
        answer = ANSWERS.get(question, "I am not sure, let me find out for you.")
        if "returns policy" in system:
            answer += RETURNS_LINE
        return _Reply(content=[_Block(answer)])


class FakeAnthropic:
    """Whatever `AnthropicTarget` calls, and nothing else."""

    def __init__(self) -> None:
        self.messages = _Messages()
