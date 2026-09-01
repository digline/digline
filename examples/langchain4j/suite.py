"""My app is LangChain4j: what do I put in my repo?

This file. It is the whole Python side, and three lines of it are yours to
edit — they are marked EDIT below.

`app/` holds the Java service being evaluated; `stub.py` stands in for it so
this runs with no JVM and no API key. Point `URL` at your own service and
delete `stub.py`: nothing else in this file changes.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from digline.core import Contains, CostBudget, LatencyBudget, Length, NotContains
from digline.run import Case, Suite
from digline.targets import HttpTarget

import stub

HERE = Path(__file__).parent

# EDIT 1 — where your service listens. `http://localhost:8080/evaluate` once
# you have run `mvn spring-boot:run` in `app/`. The fallback starts the stub, so
# the example runs on its own; in CI you set the variable and delete the rest.
URL = os.environ.get("SUPPORT_URL") or stub.start()

target = HttpTarget(
    URL,
    # EDIT 2 — the body your endpoint expects, built from the case. A callable
    # rather than a template, because a real payload has shapes a template
    # cannot.
    request=lambda case: {"question": case.vars["question"]},
    # EDIT 3 — where the three things live in your answer, dotted.
    output_path="data",
    cost_path="usage.cost_usd",
    latency_from_response="usage.elapsed_ms",
    # The model that answered and how it was set up. Without this the run
    # records nothing about the system under test, and the day somebody bumps
    # the model the comparison reports the configuration as unchanged.
    config_path="config",
)

suite = Suite(
    tenant="northwind",
    environment="staging",
    name="support",
    assertions=[
        # Every assertion runs on every case, so each one states something that
        # must hold for all of them.
        Contains(needle="Northwind Support"),
        # The failure this catches is a model that starts hedging: "As an AI
        # language model, I cannot…" in front of an answer it then gives.
        NotContains(needle="As an AI"),
        # The prompt says "at most three sentences". This is the check that
        # notices when the model stops obeying it.
        Length(minimum=12, maximum=60, unit="words"),
        # Budgets, not metrics: a declared ceiling fails the run. Both are read
        # out of the answer, because the call happened on the Java side and only
        # the service can price it.
        CostBudget(max_usd=0.002, tolerance=0.05),
        LatencyBudget(max_ms=2000.0, tolerance=0.10),
    ],
    cases=[
        Case(id=item["id"], vars={"question": item["question"]})
        for item in json.loads((HERE / "cases.json").read_text(encoding="utf-8"))
    ],
    # The prompt is the thing under test, so the run records it and a report
    # shows when it moved (ADR 0003). It sits beside the two services rather
    # than inside either: both package it, and the suite names it without
    # naming a framework.
    artifacts=[Path("prompts/system.txt")],
)
