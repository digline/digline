"""My application is Java: can I use this?

Yes, and nothing here is about Java. digline needs a body it can post and a
field it can read out of the answer; what produced the answer is not its
business. `HttpTarget` is the twenty lines every suite was writing by hand.

`server.py` stands in for the service. Point `URL` at yours and delete it — the
rest of this file does not change.
"""

from __future__ import annotations

import json
from pathlib import Path

from digline.core import CostBudget, Equals, JsonSchema, LatencyBudget
from digline.run import Case, Suite
from digline.targets import HttpTarget

import server

HERE = Path(__file__).parent
URL = server.start()

SCHEMA = {
    "type": "object",
    "required": ["queue", "confidence"],
    "properties": {
        "queue": {"type": "string", "minLength": 1},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    },
}

target = HttpTarget(
    URL,
    # The body your service expects, built from the case. A callable rather
    # than a template, because a real payload has shapes a template cannot.
    request=lambda case: {"text": case.vars["text"]},
    # Where the answer lives in the response, dotted.
    output_path="data",
    cost_path="usage.cost_usd",
    # The service reports its own time. Left out, digline measures the round
    # trip instead — which includes the network, and would be a different
    # number measuring a different thing.
    latency_from_response="usage.elapsed_ms",
)

suite = Suite(
    tenant="helpdesk",
    environment="staging",
    name="routing",
    assertions=[
        # The shape first: everything below is meaningless if the service
        # answered something else entirely.
        JsonSchema(schema=SCHEMA),
        # And the decision itself, against the one a human made. `Equals`
        # rather than `Contains`: this endpoint answers with an object, and
        # `Contains` is text-only — digline refuses to stringify a dict and
        # search inside it, which is the right refusal and says so plainly.
        Equals(),
        CostBudget(max_usd=0.002, tolerance=0.05),
        LatencyBudget(max_ms=250.0, tolerance=0.10),
    ],
    cases=[
        Case(
            id=item["id"],
            vars={"text": item["text"]},
            expected={"queue": item["queue"], "confidence": item["confidence"]},
        )
        for item in json.loads((HERE / "cases.json").read_text(encoding="utf-8"))
    ],
)
