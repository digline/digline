"""The agent under test: it reads the tool descriptions and decides.

A stand-in, so the example needs no key — but it stands in for the one thing
that matters here. A real model receives the tool descriptions in its context
and calls or does not call on the strength of their wording. This one does the
same, crudely: it matches the request against each description, and it honours
a "do not call this tool unless" clause if one is present.

That is the whole mechanism the recipe exists for. Nothing about the tools'
*names* or *schemas* changes between the two settings of `server.CAUTIOUS`;
one description gains a clause, and `lookup_customer` stops being called.
"""

from __future__ import annotations

from typing import Any

import server

_REFUSAL = "do not call this tool unless"


def _wants(request: str, description: str) -> bool:
    """Does the request look like what this description is for?

    Content words from the **whole** description, because the sentence that
    tells a model when to reach for a tool is usually not the first one — in
    `server.py` it is the second, and the clause that withdraws the tool is the
    third. Crude on purpose: the point is that it reads the description at all,
    so rewording the description changes what gets called.
    """
    words = {word.strip(",.").lower() for word in description.split() if len(word) > 4}
    lowered = request.lower()
    return any(word in lowered for word in words)


def _blocked(request: str, description: str) -> bool:
    """A conditional clause that tells the model when *not* to call.

    The precondition here is an explicit id, which is what the cautious wording
    asks for. A request that does not carry one leaves the tool uncalled.
    """
    if _REFUSAL not in description.lower():
        return False
    return not any(token.isdigit() for token in request.split())


def answer(request: str) -> tuple[str, list[dict[str, Any]]]:
    """The reply, and the calls that produced it."""
    calls: list[dict[str, Any]] = []
    for tool in server.list_tools():
        name, description = str(tool["name"]), str(tool["description"])
        if not _wants(request, description) or _blocked(request, description):
            continue
        arguments = (
            {"customer_id": _id_in(request)}
            if name == "lookup_customer"
            else {"query": request}
        )
        calls.append({"tool": name, "arguments": arguments})

    if not calls:
        return "I could not find a tool for that.", calls
    named = ", ".join(str(call["tool"]) for call in calls)
    return f"Handled by {named}.", calls


def _id_in(request: str) -> str:
    """The first number in the request, or the empty string."""
    return next((tok for tok in request.split() if tok.isdigit()), "")
