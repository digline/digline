"""The client half: building the SDK client, and reading a reply.

Shared by the target and the two judges, so how a reply is read is decided once
per provider rather than once per class.

**No key in the code.** The SDK reads `ANTHROPIC_API_KEY` from the environment,
and this file never names it: a key that a suite could set is a key that ends up
in a repository. The client is built on first use, which is what lets the tests
run with no SDK installed and no network at all.
"""

from __future__ import annotations

from typing import Any

from digline.targets import Usage

__all__ = ["build_client", "text_of", "usage_of"]


def build_client() -> Any:
    """Imported here rather than at module scope.

    A suite that only wants to be *loaded* — `digline list`, a preflight, a
    test — should not need the SDK present, and importing it lazily is what
    makes that true.
    """
    import anthropic

    return anthropic.Anthropic()


def text_of(reply: Any) -> str:
    """Only the text blocks.

    A tool-use or a thinking block has no `.text` at all, and joining one in
    would put a repr in the output the assertions read.
    """
    return "".join(
        block.text for block in reply.content if getattr(block, "type", "") == "text"
    )


def usage_of(reply: Any) -> Usage:
    """Tokens out of a message.

    `cache_creation_input_tokens` is **not** part of `input_tokens`. Measured
    against the API on 2026-08-27: a call that wrote a 9202-token cache
    reported `input_tokens=10`. Reading only `input_tokens` there prices the
    call at a thousandth of what it cost. (friction 25)
    """
    usage = reply.usage
    return Usage(
        input_tokens=int(getattr(usage, "input_tokens", 0)),
        output_tokens=int(getattr(usage, "output_tokens", 0)),
        cache_read_tokens=int(getattr(usage, "cache_read_input_tokens", 0) or 0),
        cache_write_tokens=int(getattr(usage, "cache_creation_input_tokens", 0) or 0),
    )
