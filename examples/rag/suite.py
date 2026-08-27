"""Does the answer stay inside what was retrieved?

That is the whole question for a RAG, and it is not the same as "is the answer
good". An answer can be well written, on topic, and about something no passage
said — which is the failure your users report and your tests do not catch.

The retrieval is frozen into the cases on purpose. A case carries the passages
that were retrieved for it, so what is being measured here is the *generator*:
if retrieval changes, that is a different experiment with a different baseline.
"""

from __future__ import annotations

import json
from pathlib import Path

from digline.core import (
    JUDGE_OUTPUT_LABEL,
    ClaimReply,
    CostBudget,
    Faithfulness,
    PiiAbsent,
)
from digline.run import Case, Response, Suite

import app

HERE = Path(__file__).parent
QUESTIONS = json.loads((HERE / "cases.json").read_text(encoding="utf-8"))


def claim_judge(prompt: str) -> ClaimReply:
    """Counts claims and how many the context supports. Never divides.

    digline does the arithmetic: a model asked for a ratio returns a number
    nobody can check, one asked for two counts returns something arithmetic can
    contradict. Faked here, and deliberately not generous — a stand-in that
    always answers "all supported" would measure nothing at all.
    """
    # Every judged assertion sends one shape, and the output is last, behind
    # this label. Imported rather than typed: it is the interface.
    context_part, _, answer_part = prompt.partition(JUDGE_OUTPUT_LABEL)
    context = context_part.lower()
    claims = [s.strip() for s in answer_part.split(".") if s.strip()]
    supported = sum(1 for claim in claims if _covered(claim, context))
    return ClaimReply(
        supported=supported,
        total=len(claims),
        reason=f"{supported} of {len(claims)} claims appear in the passages",
    )


def _covered(claim: str, context: str) -> bool:
    """A claim is supported when its content words are all in the passages."""
    words = [w.strip(",;:()").lower() for w in claim.split() if len(w) > 4]
    return bool(words) and all(word in context for word in words)


def target(case: Case) -> Response:
    question = str(case.vars["question"])
    context = list(case.context)
    said, cost = app.answer(question, context)
    return Response(output=said, input=question, cost_usd=cost)


suite = Suite(
    tenant="biblioteca",
    environment="staging",
    name="rag",
    assertions=[
        # The one that matters. Threshold below where the system measurably is
        # with an honest generator, so the gate protects against getting worse.
        Faithfulness(judge=claim_judge, threshold=0.9, tolerance=0.05),
        # The answer leaves the building. Binary on purpose: "a bit of PII" is
        # not a degree of quality.
        PiiAbsent(),
        # Graded, so a cost creeping up inside the budget is visible long
        # before it breaches.
        CostBudget(max_usd=0.002, tolerance=0.05),
    ],
    cases=[
        Case(
            id=item["id"],
            vars={"question": item["question"]},
            # Frozen retrieval: what the retriever returned when this case was
            # written. `Faithfulness` reads exactly this.
            context=app.retrieve(item["question"]),
        )
        for item in QUESTIONS
    ],
)
