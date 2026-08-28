"""A Converse call, faked at the lowest level there is.

Not in `conftest.py`: several `conftest` modules with the same name live in this
repository, and `from conftest import ...` resolves to whichever of them got
onto `sys.path` first — which depends on the order pytest was given its
arguments. A name of its own is the fix — and it has to be unique across the whole
workspace, not just within this package: pyright resolves `_fakes` through
`extraPaths` and would have picked another plugin's. The fixtures stay in
`conftest.py`, where pytest finds them without an import.

The fake stands where `client.converse(**request)` stands, so everything above
it — the request this package builds, the tokens it reads back, the scrubbing of
a failure — is the real code. No `boto3` import and no socket.

Converse answers with a **dict**, not with objects: that is the shape botocore
returns, and reading it with `getattr` (as the other two plugins read their
SDKs) would pass against a fake built the wrong way and fail against AWS.
"""

from __future__ import annotations

from typing import Any

__all__ = ["FakeClient", "FakeMeta", "converse_reply"]


def converse_reply(
    text: str = "Rome.",
    *,
    input_tokens: int = 1200,
    output_tokens: int = 300,
    cache_read: int = 0,
    cache_write: int = 0,
    usage: bool = True,
) -> dict[str, Any]:
    """One Converse reply, in the shape the API documents.

    `content` is a list of blocks and only some of them carry `text` — a
    `reasoningContent` or a `toolUse` block has no such key, which is what
    `text_of` has to survive.
    """
    reply: dict[str, Any] = {
        "output": {"message": {"role": "assistant", "content": [{"text": text}]}},
        "stopReason": "end_turn",
        "metrics": {"latencyMs": 42},
    }
    if usage:
        reply["usage"] = {
            "inputTokens": input_tokens,
            "outputTokens": output_tokens,
            "totalTokens": input_tokens + output_tokens,
            "cacheReadInputTokens": cache_read,
            "cacheWriteInputTokens": cache_write,
        }
    return reply


class FakeMeta:
    """`client.meta.region_name` — the only thing this package reads off a
    client besides the call itself."""

    def __init__(self, region_name: str | None) -> None:
        self.region_name = region_name


class FakeClient:
    """`client.converse(**request)`, and a region."""

    def __init__(self, region: str | None = "eu-west-1") -> None:
        self.meta = FakeMeta(region)
        self.requests: list[dict[str, Any]] = []
        self.reply: dict[str, Any] = converse_reply()
        #: Raised on every call: a throttle, a 403, an endpoint that is not
        #: there. The message is what the scrubbing is about.
        self.raises: Exception | None = None

    def converse(self, **kwargs: Any) -> dict[str, Any]:
        self.requests.append(kwargs)
        if self.raises is not None:
            raise self.raises
        return self.reply
