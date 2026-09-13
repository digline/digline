"""The model, faked, so this runs with no key and no network.

**No stand-in in `langchain-core` can do this.** All five of them —
`FakeChatModel`, `FakeListChatModel`, `FakeMessagesListChatModel`,
`GenericFakeChatModel`, `ParrotFakeChatModel` — inherit `bind_tools` from
`BaseChatModel`, which raises `NotImplementedError`, and `create_agent` binds
its tools before it runs anything. So the example ships the three lines that
close the gap: a subclass that accepts the binding and replays a script.

What is faked is **only the model**. The tools are the real functions in
`app.py`: they execute, `refund` really refuses an unknown order, and the
results in the trajectory are computed rather than scripted. That is what keeps
the checks in `suite.py` from being green by construction.

The replies are keyed on the request, so each case scripts its own two turns —
the tool call, then the sentence — and `DIGLINE_LIVE=1` puts a real model in the
same seat with the same graph around it.
"""

from __future__ import annotations

import os
import re
from typing import Any

from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, BaseMessage


class FakeToolModel(FakeMessagesListChatModel):
    """Replays scripted messages, and accepts `.bind_tools()`.

    The binding is a no-op because the script already encodes which tools get
    called with what — there is no model here to be told what is available.
    """

    def bind_tools(self, tools: Any, **kwargs: Any) -> Any:  # noqa: ANN401, ARG002
        return self


def _call(name: str, arguments: dict[str, object], identifier: str) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[
            {"name": name, "args": arguments, "id": identifier, "type": "tool_call"}
        ],
    )


#: One script per case: look the order up, then refund what the lookup said.
#: The ids are literals rather than generated, which is what keeps two runs of
#: this example byte-identical — see the note in `suite.py`.
def _script(order_id: str, amount: float = 4.90) -> list[BaseMessage]:
    return [
        _call("lookup", {"order_id": order_id}, "call-lookup"),
        _call(
            "refund",
            {"order_id": order_id, "amount_eur": amount},
            "call-refund",
        ),
        AIMessage(
            content=(
                f"I have refunded the {amount:.2f} EUR shipping charge on order "
                f"{order_id}, which was delivered four days late."
            ),
            id="ai-final",
        ),
    ]


#: EDIT, or set it in the environment: makes the stand-in read the request the
#: way a careless agent does. See section 1 of the README — it is how this
#: example shows what its checks are for without committing a red baseline.
NAIVE = os.environ.get("DISPATCH_NAIVE") == "1"

#: A number in the request, with or without decimals.
_NUMBER = re.compile(r"\d+(?:\.\d+)?")


def _careless(request: str) -> tuple[str, float]:
    """What a badly-behaved agent extracts: the **first** number it sees as the
    order id, and any amount the customer stated as the figure to refund.

    Both are plausible mistakes rather than invented ones, which is the point.
    An agent that reads left to right takes `12.50` out of "I paid 12.50 for
    express on order 4711", and an agent that is agreeable takes `9.90` from a
    customer who is fairly sure — and both then write a sentence that reads
    perfectly.
    """
    numbers = _NUMBER.findall(request)
    order_id = numbers[0] if numbers else "unknown"
    stated = [float(n) for n in numbers if "." in n]
    return order_id, stated[-1] if stated else 4.90


def model_for(request: str) -> FakeToolModel:
    """The stand-in for one case. A fresh instance per call: the replay walks
    its list, and a shared one would answer the second case from the first
    case's place in the script."""
    if NAIVE:
        order_id, amount = _careless(request)
        return FakeToolModel(responses=_script(order_id, amount))
    order_id = "4711" if "4711" in request else "unknown"
    return FakeToolModel(responses=_script(order_id))
