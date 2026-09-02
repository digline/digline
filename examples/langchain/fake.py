"""The model, faked, so this runs with no key and no network.

`FakeListChatModel` is LangChain's own stand-in: it returns the replies it was
handed, in order, and never looks at the prompt. That is a real limit and worth
saying plainly — on this path the prompt is *not* under test, the chain around
it is. What is measured is that the template still renders, the parser still
returns a string, and the shape the caller depends on still arrives.

So the replies are keyed on the passage step one selected rather than on the
case: change the retrieval and the answer this example sees changes with it.
Point the suite at a real model (`DIGLINE_LIVE=1`) and the prompt is under test
again, with a baseline of its own.
"""

from __future__ import annotations

import json

from langchain_core.language_models import FakeListChatModel

import app

#: One answer per handbook page, quoting it — a stand-in that invented freely
#: would make the rubric below measure nothing.
RECORDS: dict[str, dict[str, object]] = {
    "handbook/accounts": {
        "category": "accounts",
        "answer": (
            "An account locked after five failed attempts unlocks itself after "
            "fifteen minutes, or you can use the reset link on the sign in page."
        ),
        "source": "handbook/accounts",
        "needs_human": False,
    },
    "handbook/contact": {
        "category": "contact",
        "answer": (
            "The handbook does not cover this, so the support desk will answer "
            "within one working day."
        ),
        "source": "handbook/contact",
        "needs_human": True,
    },
    "handbook/payments": {
        "category": "payments",
        "answer": (
            "We cannot split one order across two cards, though a gift card can "
            "be combined with a card payment."
        ),
        "source": "handbook/payments",
        "needs_human": False,
    },
    "handbook/returns": {
        "category": "returns",
        "answer": (
            "Boots count as unworn only if they were tried on indoors, so a "
            "returned pair worn outdoors is not refunded."
        ),
        "source": "handbook/returns",
        "needs_human": False,
    },
    "handbook/shipping": {
        "category": "shipping",
        "answer": (
            "Standard delivery reaches the islands in four working days, and an "
            "island address costs the same as the mainland."
        ),
        "source": "handbook/shipping",
        "needs_human": False,
    },
    "handbook/sizing": {
        "category": "sizing",
        "answer": (
            "Between two sizes, take the larger one if you wear a fleece "
            "underneath, and read the size chart rather than guessing."
        ),
        "source": "handbook/sizing",
        "needs_human": False,
    },
    "handbook/warranty": {
        "category": "warranty",
        "answer": (
            "Jackets carry a two year warranty against faulty zips, so send "
            "photographs of the damage with your order number and we arrange a "
            "repair."
        ),
        "source": "handbook/warranty",
        "needs_human": False,
    },
}


def model_for(request: str) -> FakeListChatModel:
    """The stand-in that answers for the page step one selected."""
    return FakeListChatModel(responses=[json.dumps(RECORDS[app.select(request)])])
