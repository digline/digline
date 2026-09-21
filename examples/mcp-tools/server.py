"""The MCP server under test, standing in for a real one.

A real `tools/list` comes back over the wire from a server you did not write
and do not pin. Here it is a dict, so the example needs no network and no
server process — what matters is the shape of the reply and the fact that a
**description** is a field in it, sitting beside the name.

`CAUTIOUS` is the switch this example turns. Both settings offer the same two
tools under the same two names with the same schemas; the only difference is
the wording of one description. Turn it on and watch a tool stop being called.
"""

from __future__ import annotations

from typing import Any

#: Shipped off, so the committed baseline is the permissive wording and
#: `digline compare` shows the point when you turn it on.
CAUTIOUS = False

_LOOKUP_PERMISSIVE = (
    "Look up a customer record by id. Use this whenever the user mentions a "
    "customer, an account or an order."
)

#: One clause added, no name changed, no schema changed. This is the shape
#: EvalSeal measured across published servers: the instruction moves and every
#: name-based check reads no change at all.
_LOOKUP_CAUTIOUS = (
    "Look up a customer record by id. Use this whenever the user mentions a "
    "customer, an account or an order. Do not call this tool unless the user "
    "has supplied an explicit customer id; ask for one instead."
)


def list_tools() -> list[dict[str, Any]]:
    """What a `tools/list` round trip would hand you."""
    return [
        {
            "name": "search_docs",
            "description": (
                "Search the product documentation for a phrase and return the "
                "matching passages."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
        {
            "name": "lookup_customer",
            "description": _LOOKUP_CAUTIOUS if CAUTIOUS else _LOOKUP_PERMISSIVE,
            "inputSchema": {
                "type": "object",
                "properties": {"customer_id": {"type": "string"}},
                "required": ["customer_id"],
            },
        },
    ]
