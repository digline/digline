"""A LangGraph agent, evaluated in process.

No server and no HTTP: the target is a plain function that invokes the graph the
application already has. What is under test is the **trajectory** — which tools
the agent called, in what order, and with what arguments — because that is where
this agent's behaviour lives. The answer text is a sentence about money that has
already moved.

Two paths, one switch. By default the graph runs on a scripted stand-in, so this
needs no key and answers the same way every time; that is what CI runs.
`DIGLINE_LIVE=1` puts a real model in the same seat, with the same graph and the
same tools around it. They are different systems and each keeps its own baseline.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from time import perf_counter

from digline.core import Contains, ToolCalledWith, ToolsCalled
from digline.run import Case, Response, Suite
from langchain_core.language_models import BaseChatModel

import app
import fake

HERE = Path(__file__).parent
CASES = json.loads((HERE / "cases.json").read_text(encoding="utf-8"))

#: EDIT: the one line that points this example at a real model.
LIVE = os.environ.get("DIGLINE_LIVE") == "1"
MODEL = "claude-haiku-4-5"

#: The order every case is about, and what the lookup says its shipping was.
#: One order and four phrasings, because the thing under test is whether the
#: agent reads the request correctly — not whether it can hold two orders apart.
ORDER = "4711"
SHIPPING_EUR = 4.90


def _model(request: str) -> BaseChatModel:
    if LIVE:  # pragma: no cover - needs a key
        from langchain.chat_models import init_chat_model

        return init_chat_model(f"anthropic:{MODEL}", temperature=0)
    return fake.model_for(request)


def target(case: Case) -> Response:
    """The target: a function that runs the graph. No HTTP, no subprocess.

    **The output is the projection, not the message list.** LangGraph mints
    `ToolMessage.id` as a uuid4 with no public hook to pin it, so the raw list
    is not stable across processes and a baseline built on it would churn on
    every run for a reason that has nothing to do with the agent. The ordered
    `(tool, arguments, result, status)` was measured byte-identical across
    separate processes, and the id it drops carries no evaluative meaning —
    which is fixed decision 9 behaving correctly rather than a workaround.

    The trajectory rides in `Response.metadata`, where the trajectory assertions
    read it. That bag is not persisted; what reaches the run file is what an
    assertion measured out of it.
    """
    request = str(case.vars["request"])
    started = perf_counter()
    final, calls = app.answer(request, _model(request))
    # A duration is not a clock, so measuring one here is allowed. No
    # `LatencyBudget` on this path all the same: a ceiling a scripted model can
    # never touch is a check that is green by construction.
    return Response(
        output=final,
        input=request,
        latency_ms=(perf_counter() - started) * 1000,
        metadata={
            "tools": [call["tool"] for call in calls],
            "tool_calls": calls,
        },
    )


suite = Suite(
    tenant="northwind",
    environment="staging",
    name="dispatch",
    assertions=[
        # The policy, and the one check that is about *how* the answer was
        # produced. Look it up, then refund it: an agent that refunds first has
        # moved money against a figure nobody verified, and every check below
        # would still be green.
        ToolsCalled(expected=["lookup", "refund"]),
        # The id came out of the request. The `decoy-number` case puts a second
        # number in the sentence, and an agent that passes 12.50 as an order id
        # fails here and nowhere else.
        ToolCalledWith(tool="lookup", arguments={"order_id": ORDER}),
        # And the amount came out of the *lookup*, not out of the customer. The
        # `amount-asserted-by-the-customer` case states 9.90 confidently; the
        # shipping was 4.90. `subset` because the call may carry keys this
        # example did not declare, and a framework adding one is not a
        # regression.
        ToolCalledWith(
            tool="refund",
            arguments={"order_id": ORDER, "amount_eur": SHIPPING_EUR},
            match="subset",
        ),
        # The sentence the customer reads names the figure that actually moved.
        Contains(needle=f"{SHIPPING_EUR:.2f}"),
    ],
    cases=[Case(id=case["id"], vars={"request": case["request"]}) for case in CASES],
    # The system prompt is the thing under test (ADR 0003), so every run records
    # it and the report shows what changed above the scores it moved.
    artifacts=[Path("prompts/system.txt")],
    # Keep the answers, so a changed policy can be re-judged against the calls
    # this run actually made rather than by paying the agent again. They stay in
    # this repository: `promote` strips them, and no boundary ever sees them.
    record_responses=True,
)
