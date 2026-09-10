"""A chat completion, faked at the lowest level there is.

Not in `conftest.py`: several `conftest` modules with the same name live in
this repository, and `from conftest import ...` resolves to whichever of them
got onto `sys.path` first. A name of its own is the fix — and it has to be
unique across the whole workspace, not just within this package: pyright
resolves it through `extraPaths` and would otherwise pick another plugin's.
The fixtures stay in `conftest.py`, where pytest finds them without an import.

The fake stands where the SDK's `client.chat.completions.create` stands, so
everything above it — the request this package builds, the tokens it reads back,
the retry when a provider refuses `response_format` — is the real code. No
`openai` import, no socket, and the whole file runs with the SDK uninstalled.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class FakeFunction:
    name: str = "search"
    #: A **string** on this API, not an object, and the SDK's own docstring
    #: warns the model does not always generate valid JSON in it. That
    #: disagreement with the other two providers is why the record carries tool
    #: names and not arguments (ADR 0004 §6).
    arguments: str = '{"q": "rome"}'


@dataclass
class FakeToolCall:
    function: FakeFunction = field(default_factory=FakeFunction)
    id: str = "call_1"
    type: str = "function"


@dataclass
class FakeMessage:
    #: `None` is what the API returns when the model produced nothing — a
    #: refusal, or a cap hit before the first token.
    content: str | None = "Rome."
    #: A refusal arrives **here**, and `finish_reason` stays `stop`. The one
    #: place a plugin composes an answer rather than translating one.
    refusal: str | None = None
    #: Absent on a reply that called nothing *and* on a server with no tool
    #: support at all — two different facts this API cannot tell apart.
    tool_calls: list[FakeToolCall] | None = None


@dataclass
class FakeChoice:
    message: FakeMessage = field(default_factory=FakeMessage)
    finish_reason: str | None = "stop"


@dataclass
class FakeDetails:
    cached_tokens: int = 0


@dataclass
class FakeUsage:
    """Shaped from the real reply.

    `prompt_tokens_details.cached_tokens` is **inside** `prompt_tokens` here —
    the opposite of Anthropic, where a cache write is not in `input_tokens` at
    all. The fake carries the real convention so the subtraction in
    `usage_of` is tested against the shape it will actually meet.
    """

    prompt_tokens: int = 1200
    completion_tokens: int = 300
    prompt_tokens_details: FakeDetails = field(default_factory=FakeDetails)


@dataclass
class FakeReply:
    choices: list[FakeChoice] = field(default_factory=lambda: [FakeChoice()])
    usage: FakeUsage | None = field(default_factory=FakeUsage)
    #: What answered, and the backend it answered on. The first is the strong
    #: signal of ADR 0005 §9 — the request carried an alias, this is what it
    #: resolved to — and the second is this provider's half alone.
    model: str = "gpt-fake-1-2026-01-01"
    system_fingerprint: str | None = "fp_abc123"


class FakeCompletions:
    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []
        self.reply = FakeReply()
        #: Parameter names this provider refuses, as a real one refuses
        #: `response_format`: present in the request, raise.
        self.refuses: set[str] = set()
        #: Raised on every call, whatever the request, for the paths where the
        #: provider is simply down or the key is wrong.
        self.raises: Exception | None = None

    def create(self, **kwargs: Any) -> FakeReply:
        self.requests.append(kwargs)
        if self.raises is not None:
            raise self.raises
        refused = self.refuses & set(kwargs)
        if refused:
            raise ValueError(f"unsupported parameter: {sorted(refused)}")
        return self.reply


class FakeChat:
    def __init__(self) -> None:
        self.completions = FakeCompletions()


class FakeClient:
    """`client.chat.completions.create(...)`, and nothing else."""

    def __init__(self) -> None:
        self.chat = FakeChat()

    @property
    def completions(self) -> FakeCompletions:
        return self.chat.completions
