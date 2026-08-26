"""A complete, working suite.

Run it from this directory:

    digline run     --suite suite.py
    digline promote --suite suite.py --run latest
    digline compare --suite suite.py --run latest
    digline report  --suite suite.py --run latest --locale it --out report.html
"""

from __future__ import annotations

import app  # the application under test, sitting next to this file
from digline.core import (
    Contains,
    CostBudget,
    JudgeReply,
    LatencyBudget,
    LlmRubric,
    Regex,
)
from digline.run import Case, Response, Suite


def judge(prompt: str) -> JudgeReply:
    """Stand-in for a real model call.

    digline composes `prompt` from the rubric, the question and the answer,
    and asks for two things back: a score in [0, 1] and a reason. Replace the
    body with your own call; the protocol is all that is required.

    Note it is a plain function. That is why a suite is Python and not YAML.
    """
    concise = len(prompt.split()) <= 90
    signed = "Northwind Support" in prompt
    score = 0.4 + 0.3 * signed + 0.3 * concise
    return JudgeReply(
        score=score,
        reason=f"signed={signed}, concise={concise}",
    )


suite = Suite(
    tenant="northwind",
    environment="staging",
    name="support",
    assertions=[
        # Every assertion runs on every case, so each one states something that
        # must hold for all of them.
        Contains(needle="Northwind Support"),
        Regex(pattern=r"^[A-Z]"),
        LlmRubric(
            rubric="Does the reply answer the question in at most three sentences?",
            judge=judge,
            threshold=0.7,
            # Mandatory and without a default: a judge is not reproducible, and
            # an implicit tolerance over a noisy value is a green light nobody
            # decided to give.
            tolerance=0.05,
        ),
        CostBudget(max_usd=0.02, tolerance=0.05),
        LatencyBudget(max_ms=800.0, tolerance=0.10),
    ],
    cases=[
        Case(id="where-is-my-order"),
        Case(id="how-do-i-return"),
        Case(id="is-it-waterproof"),
        # Set aside with a stated reason, which the report shows. The driver
        # does not run it; the run still records that coverage is smaller.
        Case(id="refund-status", suspended="the refund API is down, ticket 412"),
    ],
)


def target(case: Case) -> Response:
    """Called once per case. It calls the application and reports what it cost."""
    result = app.reply(case.id)
    return Response(
        output=result.text,
        input=app.render_prompt(case.id),
        cost_usd=result.cost_usd,
        latency_ms=result.latency_ms,
    )
