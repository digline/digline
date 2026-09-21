"""Did the tool descriptions move under me, and did the agent notice?

A tool description is not documentation. It is text in the model's context that
decides **when the model calls** — configuration, in other words, and an
upgrade can rewrite it while every name and every schema stays put. A check
that watches names reads that as no change at all.

So this suite does two things at once, and neither is enough alone:

1. It declares `tools.json` as an **artifact**, so the definitions the agent was
   offered are recorded, SHA and all, in every run and in the committed
   baseline. That is what makes a changed description *visible*.
2. It asserts the behaviour those definitions produce, so a change that matters
   shows up as a red check rather than only as a diff somebody might read.

Turn on `server.CAUTIOUS`, re-run `dump_tools.py`, and run the suite: one
description gains a conditional clause, `lookup_customer` stops being called
for the case with no explicit id, and the report shows the prompt diff above
the score that moved. Without the artifact you would see the score move and
have nothing in the document saying why.

`tools.json` is written by `dump_tools.py`, canonically, and digline never
fetches it — see that file, and `docs/tools.md`.
"""

from __future__ import annotations

import json
from pathlib import Path

from digline.core import Contains, ToolsCalled
from digline.run import Case, Response, Suite

import app

HERE = Path(__file__).parent
CASES = json.loads((HERE / "cases.json").read_text(encoding="utf-8"))


def target(case: Case) -> Response:
    request = str(case.vars["request"])
    said, calls = app.answer(request)
    return Response(
        output=said,
        input=request,
        metadata={
            "tools": [call["tool"] for call in calls],
            "tool_calls": calls,
        },
    )


suite = Suite(
    tenant="northwind",
    environment="staging",
    name="agent-tools",
    # The definitions the agent was offered, recorded with every run. Not in
    # `config_hash` by design: changing them is the experiment, and two runs
    # across the change must stay comparable.
    artifacts=[Path("tools.json")],
    assertions=[
        # Both cases mention a customer or an account, so under the shipped
        # wording both reach the tool. Flip `server.CAUTIOUS` and re-dump: the
        # `no-id` case stops calling it, and this is the check that says so.
        ToolsCalled(expected=["lookup_customer"]),
        # The same event read off what the user is shown, because a trajectory
        # check and a text check failing together is what tells you the
        # behaviour moved rather than the plumbing.
        Contains(needle="lookup_customer"),
    ],
    cases=[Case(id=item["id"], vars={"request": item["request"]}) for item in CASES],
)
