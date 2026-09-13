"""The agent under test: two tools, and a policy about the order it uses them in.

A dispatch desk that can look an order up and refund its shipping. The rule the
business cares about is not in the answer text at all — it is that the agent
**looks the order up before it refunds it**, and refunds the figure the lookup
returned rather than the one the customer asserted. An agent that skips the
lookup writes a plausible sentence and moves real money against a number it
invented.

`answer()` returns the final text **and the trajectory**, as a projection:
`(tool, arguments, result, status)` per call, in order. That shape is chosen and
not incidental — see `suite.py` for why the raw message list is not what the
baseline records.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

# `create_agent` is an overload set whose generics langgraph leaves open, so
# pyright strict reads it as partially unknown here and at the call below. An
# upstream limitation rather than one of this call site, and narrowed to the two
# lines that meet it rather than relaxed for the file.
from langchain.agents import create_agent  # pyright: ignore[reportUnknownVariableType]
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langchain_core.tools import tool

HERE = Path(__file__).parent

#: The orders this desk knows about, and what shipping was actually charged.
#: A dict rather than a database, because the example is about the agent.
ORDERS: dict[str, dict[str, object]] = {
    "4711": {"status": "delivered 4 days late", "shipping_eur": 4.90},
    "5120": {"status": "in transit", "shipping_eur": 0.00},
}


@tool
def lookup(order_id: str) -> str:
    """Look up an order: its delivery status and what shipping was charged."""
    found = ORDERS.get(order_id)
    if found is None:
        return f"order {order_id} is not in the system"
    return (
        f"order {order_id}: {found['status']}, "
        f"shipping charged {found['shipping_eur']:.2f} EUR"
    )


@tool
def refund(order_id: str, amount_eur: float) -> str:
    """Refund an amount in euro against an order. Only after looking it up."""
    if order_id not in ORDERS:
        raise ValueError(f"refusing to refund unknown order {order_id}")
    return f"refunded {amount_eur:.2f} EUR against order {order_id}"


#: Read from the file, never inlined here. `suite.py` declares that same path as
#: the thing under test (ADR 0003), and a prompt hardcoded beside a declaration
#: pointing at a file is a run recording an artifact nothing used.
SYSTEM = (HERE / "prompts" / "system.txt").read_text(encoding="utf-8")


def build(model: BaseChatModel) -> Any:
    """The graph. `create_agent`, and **not** `create_react_agent`: that one
    moved to `langchain.agents` in v1, still imports, warns, and goes away in
    v2."""
    return create_agent(  # pyright: ignore[reportUnknownVariableType]
        model=model, tools=[lookup, refund], system_prompt=SYSTEM
    )


def trajectory(messages: list[BaseMessage]) -> list[dict[str, object]]:
    """The ordered `(tool, arguments, result, status)` the agent produced.

    Paired on `tool_call_id` rather than by position. One `AIMessage` carries
    every call of a turn, so two parallel calls arrive as one message and two
    `ToolMessage`s, and position alone would mis-pair them the moment the model
    asks for two things at once.

    `status` is read and not inferred — it is a real field on `ToolMessage`, and
    an agent that carried on after a call the framework marked failed is visible
    here and nowhere in the text.

    What it does **not** cover, measured rather than assumed: a tool that raises
    propagates the exception out of `invoke()` in langgraph 1.2.11 rather than
    coming back as a `ToolMessage`. Nothing here catches it, deliberately —
    digline then records the case as one that could not be judged, which is the
    honest third outcome and is not the same statement as a check that failed.
    """
    asked: dict[str, dict[str, object]] = {}
    ordered: list[dict[str, object]] = []
    for message in messages:
        if isinstance(message, AIMessage):
            for call in message.tool_calls:
                identifier = call.get("id")
                if identifier is not None:
                    asked[identifier] = {
                        "tool": call["name"],
                        "arguments": call["args"],
                    }
        elif isinstance(message, ToolMessage):
            call = asked.get(str(message.tool_call_id), {})
            ordered.append(
                {
                    "tool": call.get("tool", message.name or ""),
                    "arguments": call.get("arguments", {}),
                    "result": str(message.content),
                    "status": message.status,
                }
            )
    return ordered


def answer(request: str, model: BaseChatModel) -> tuple[str, list[dict[str, object]]]:
    """Run the agent once. The final text, and how it got there."""
    state = build(model).invoke({"messages": [("user", request)]})
    messages = cast("list[BaseMessage]", state["messages"])
    final = next(
        (
            str(message.content)
            for message in reversed(messages)
            if isinstance(message, AIMessage) and not message.tool_calls
        ),
        "",
    )
    return final, trajectory(messages)
