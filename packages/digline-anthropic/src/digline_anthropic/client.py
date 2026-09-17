"""The client half: building the SDK client, and reading a reply.

Shared by the target and the two judges, so how a reply is read is decided once
per provider rather than once per class.

**No key in the code.** The SDK reads `ANTHROPIC_API_KEY` from the environment,
and this file never names it: a key that a suite could set is a key that ends up
in a repository. The client is built on first use, which is what lets the tests
run with no SDK installed and no network at all.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from digline.core import Finish
from digline.targets import Completion, ToolCall, Usage, finish_of

__all__ = [
    "FINISH",
    "completion_of",
    "build_client",
    "text_of",
    "tool_calls_of",
    "tools_of",
    "usage_of",
]

#: Anthropic's `stop_reason` in the vocabulary every plugin translates into
#: (ADR 0004 §6). Read off `anthropic.types.StopReason`, not recalled.
#:
#: Two of the mappings are lossy and deliberately so. `max_tokens` and
#: `model_context_window_exceeded` both become `length` — your cap and the
#: model's window, two different things to go and fix — and `refusal` becomes
#: `filtered`. The provider's own word survives beside it as `finish_raw`,
#: which is what an operator searches the provider's docs for.
#:
#: `pause_turn` is listed rather than left to fall through: it maps to `other`
#: either way, and listing it says it was considered. A word this table does not
#: know maps to `other` too, and never to `stop` — see `finish_of`.
FINISH: dict[str, Finish] = {
    "end_turn": "stop",
    "stop_sequence": "stop",
    "max_tokens": "length",
    "model_context_window_exceeded": "length",
    "tool_use": "tool_use",
    "refusal": "filtered",
    "pause_turn": "other",
}


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


def tools_of(reply: Any) -> tuple[str | None, ...]:
    """The tools the model called, in the order it called them.

    Both kinds count. A `tool_use` block is a tool the suite is asked to run; a
    `server_tool_use` block is one Anthropic ran on the model's behalf, and from
    where a trajectory assertion stands — *did it look the answer up or make it
    up* — the distinction is the provider's, not the question's.

    Never `None`: this API always says what the assistant turn contained, so an
    empty tuple here is the model calling nothing rather than nobody reporting.

    Read off `tool_calls_of`, so the two cannot disagree: a block that names no
    tool is `None` at its position in both.
    """
    return tuple(call.tool for call in tool_calls_of(reply))


def tool_calls_of(reply: Any) -> tuple[ToolCall, ...]:
    """The calls with their arguments, and what this API reports about each.

    **A `tool_use` block** is a tool the application runs after the reply, so
    the reply carries neither its result nor its status: both are
    `not_reported`, never an invented `success`.

    **A `server_tool_use` block** is one Anthropic ran, and its outcome arrives
    in the same reply as a `*_tool_result` block joined by `tool_use_id`. Its
    content is either a typed `*_error`, recorded as `status="error"` with the
    provider's own `error_code` as the result, or the payload, recorded as
    `status="success"` with `result_absence="not_recorded"`. Bulk is the
    criterion: search pages and encrypted code output would push the entry over
    `MAX_RECORDED_CHARS` and drop the model's own answer; an error code is the
    signal and is short. A server call with no result in the reply — a turn
    paused mid-search — reports neither. (ADR 0018 §1, amended 2026-09-15)

    Never `None`, for `tools_of`'s reason; the names are `tools_of`'s, in the
    same order.
    """
    outcomes = {
        str(getattr(block, "tool_use_id", "")): block
        for block in reply.content
        if str(getattr(block, "type", "")).endswith("_tool_result")
    }
    calls: list[ToolCall] = []
    for block in reply.content:
        kind = getattr(block, "type", "")
        if kind not in ("tool_use", "server_tool_use"):
            continue
        name = _name_of(block)
        raw_input: object = getattr(block, "input", None)
        arguments = (
            cast("Mapping[str, object]", raw_input)
            if isinstance(raw_input, Mapping)
            else None
        )
        outcome = (
            outcomes.get(str(getattr(block, "id", "")))
            if kind == "server_tool_use"
            else None
        )
        if outcome is None:
            calls.append(
                ToolCall(
                    tool=name,
                    arguments=arguments,
                    status="not_reported",
                    result_absence="not_reported",
                )
            )
            continue
        code = _error_code(outcome)
        if code is None:
            calls.append(
                ToolCall(
                    tool=name,
                    arguments=arguments,
                    status="success",
                    result_absence="not_recorded",
                )
            )
        else:
            calls.append(
                ToolCall(tool=name, arguments=arguments, status="error", result=code)
            )
    return tuple(calls)


def _name_of(block: Any) -> str | None:
    """The tool a block names, or `None` where it names none.

    The SDK declares `name: str` and does not validate a reply, so a server that
    does not honour the contract hands over `None`, whether it left the name out
    or sent `null`. `str()` of that was once a tool named `"None"`: a silent
    misread in `tools` and `tool_calls` alike. The next release errored the
    case instead;
    the document now records the call as one the provider did not name, and the
    named calls beside it are judged. `""` is not a name either. (ADR 0018 §1,
    amended 2026-09-17)
    """
    name: object = getattr(block, "name", None)
    return name if isinstance(name, str) and name else None


def _error_code(outcome: Any) -> str | None:
    """The provider's own code, where the result block's content is an error.

    Every error content in the SDK is typed `*_tool_result_error` (or
    `*_tool_result_error_block`) and carries `error_code`; a successful one is a
    result or a list of them. Read by the type word the SDK discriminates on.
    """
    content: Any = getattr(outcome, "content", None)
    word = getattr(content, "type", None)
    if not isinstance(word, str) or "_error" not in word:
        return None
    return str(getattr(content, "error_code", "") or word)


def completion_of(reply: Any) -> Completion:
    """One reply, as the record `_complete` returns (ADR 0004 §6).

    `model` is what the API said answered, which is the point of recording it:
    the target sent an alias, and an alias is a promise about a family rather
    than the name of a system. There is no fingerprint on this API — that is
    OpenAI's half — so the field stays absent, which is the honest reading of a
    provider that does not name a backend build.
    """
    finish, raw = finish_of(getattr(reply, "stop_reason", None), FINISH)
    return Completion(
        text=text_of(reply),
        usage=usage_of(reply),
        finish=finish,
        finish_raw=raw,
        tools=tools_of(reply),
        tool_calls=tool_calls_of(reply),
        model=str(reply.model) if getattr(reply, "model", None) else None,
    )
