"""The suite the operator watches.

Four cases, six checks, and nothing clever. The suite is not the point of this
example — the loop is — so it is deliberately the quickstart's shape: a support
desk, three questions it can answer and one set aside with a reason.

What it does carry that the quickstart does not is a `Repeated` rubric. That is
not decoration either: a check judged once has no measured interval, and
without an interval the operator's whole vocabulary — "the drop repeated beyond
the measured floor" — is a phrase with nothing behind it.

    digline run     --suite suite.py
    digline compare --suite suite.py --run latest

`loop.py` is what runs those on a schedule and decides what they mean.
"""

from __future__ import annotations

import json
from pathlib import Path

from digline.core import (
    Contains,
    CostBudget,
    LatencyBudget,
    Length,
    LlmRubric,
    Regex,
    Repeated,
)
from digline.run import Case, Suite

import fake

CASES = json.loads((Path(__file__).parent / "cases.json").read_text(encoding="utf-8"))

suite = Suite(
    # The tenant is the perimeter and it is a directory: everything lands in
    # .digline/northwind/. `environment` says where inside it this ran — and
    # `production` is the honest word for a suite pointed at a live endpoint on
    # a schedule, which is what this example is a model of.
    tenant="northwind",
    environment="production",
    name="support",
    assertions=[
        Contains(needle="Northwind Support"),
        Regex(pattern=r"^[A-Z]", name="starts_capitalised"),
        Length(maximum=400, unit="characters"),
        # Judged three times, and the three votes are recorded. `min_agreement`
        # is mandatory once a check is repeated: below it the verdict is an
        # *error* rather than a failure — a judgement that could not be given —
        # and a run carrying one cannot become a baseline.
        Repeated(
            inner=LlmRubric(
                rubric=(
                    "Does the reply answer the customer in at most three "
                    "sentences, and sign off as Northwind Support?"
                ),
                judge=fake.judge,
                threshold=0.7,
                tolerance=0.05,
            ),
            samples=3,
            min_agreement="2/3",
        ),
        # Always, both of them: a cost creeping up *within* budget is visible
        # before it is a problem.
        CostBudget(max_usd=0.02, tolerance=0.05),
        LatencyBudget(max_ms=800.0, tolerance=0.10),
    ],
    cases=[
        Case(
            id=case["id"],
            vars=case["vars"],
            suspended=case.get("suspended"),
        )
        for case in CASES
    ],
)

#: What is under test. `fake.py` explains why it is an object and not a
#: function; point it at your own endpoint — an `HttpTarget`, an SDK call —
#: and nothing else in this directory changes.
target = fake.target
