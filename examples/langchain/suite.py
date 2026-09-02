"""A LangChain pipeline, evaluated in process.

No server and no HTTP: the target is a plain function that invokes the chain the
application already has. What is under test is the whole pipeline — retrieval,
template, model, parser — and what the checks defend is the shape the caller
downstream depends on.

Two paths, one switch. By default the chain runs on `FakeListChatModel`, so this
needs no key and answers the same way every time; that is what CI runs.
`DIGLINE_LIVE=1` puts a real model under the chain and a real judge behind the
rubric. They are different systems and each keeps its own baseline.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path
from time import perf_counter
from typing import cast

from digline.core import (
    JUDGE_OUTPUT_LABEL,
    Contains,
    JsonSchema,
    Judge,
    JudgeReply,
    LlmRubric,
    NotContains,
)
from digline.run import Case, Response, Suite
from digline_anthropic import AnthropicJudge
from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel

import app
import fake

HERE = Path(__file__).parent
CASES = json.loads((HERE / "cases.json").read_text(encoding="utf-8"))

#: EDIT: the one line that points this example at a real model and a real judge.
LIVE = os.environ.get("DIGLINE_LIVE") == "1"
MODEL = "claude-haiku-4-5"
#: The instrument, not the subject. The same model by default because it is the
#: cheap answer, and a separate line because grading yourself is a choice
#: somebody should have to change rather than inherit.
JUDGE_MODEL = "claude-haiku-4-5"

#: The record the caller downstream unpacks. `source` is only `type: string`
#: here on purpose — that it names a handbook page is what `Contains` below
#: checks, and two assertions saying the same thing make a diff twice as long
#: and no more informative.
SCHEMA = {
    "type": "object",
    "required": ["category", "answer", "source", "needs_human"],
    "additionalProperties": False,
    "properties": {
        "category": {
            "type": "string",
            "enum": [
                "accounts",
                "contact",
                "payments",
                "returns",
                "shipping",
                "sizing",
                "warranty",
            ],
        },
        "answer": {"type": "string", "minLength": 1},
        "source": {"type": "string", "minLength": 1},
        "needs_human": {"type": "boolean"},
    },
}

RUBRIC = (
    "The answer resolves the request using only what the passage says, in at "
    "most two sentences, and states no price, date or rule the passage does "
    "not contain."
)


def _fake_judge(prompt: str) -> JudgeReply:
    """The rubric's judge on the default path: deterministic, and it reads.

    Graded rather than binary, and deliberately not generous — a stand-in that
    always answered 1.0 would leave the rubric vacuously green, which is the one
    thing digline refuses. It scores how much of the answer the passage actually
    supports, so an invented sentence costs score here exactly as it would with
    a real judge behind `DIGLINE_LIVE=1`.
    """
    context, _, said = prompt.partition(JUDGE_OUTPUT_LABEL)
    # Every judged assertion is sent one shape; the passage is the `Context`
    # section, which the suite froze into the case.
    passage = context.split("Context:\n", 1)[-1].split("\n\nInput:", 1)[0].lower()

    try:
        parsed: object = json.loads(said)
    except json.JSONDecodeError:
        parsed = None
    if not isinstance(parsed, Mapping):
        # Zero rather than an exception: `json_schema` above already reports an
        # undecodable output as an error, and a judge that raises would say the
        # same thing a second time in a worse way.
        return JudgeReply(score=0.0, reason="the reply was not one JSON object")
    record = cast(Mapping[str, object], parsed)

    answer = str(record.get("answer", ""))
    words = [
        w for w in (t.strip(",;:.()").lower() for t in answer.split()) if len(w) > 4
    ]
    grounded = sum(word in passage for word in words) / len(words) if words else 0.0
    short = answer.count(".") <= 2
    return JudgeReply(
        score=round(0.25 + 0.5 * grounded + 0.25 * short, 3),
        reason=(
            f"{grounded:.0%} of the answer's content words are in the passage, "
            f"at most two sentences={short}"
        ),
    )


#: A plugin is a target *and* a judge (ADR 0004): on the live path the twenty
#: lines of SDK-and-JSON leave this file, and the run records which model graded.
JUDGE: Judge = AnthropicJudge(model=JUDGE_MODEL) if LIVE else _fake_judge


def _model(request: str) -> BaseChatModel:
    if LIVE:  # pragma: no cover - needs a key
        return init_chat_model(f"anthropic:{MODEL}", temperature=0)
    # Keyed on the request, because the stand-in answers for whatever page step
    # one retrieved. See `fake.py`.
    return fake.model_for(request)


def target(case: Case) -> Response:
    """The target: a function that calls the chain. No HTTP, no subprocess."""
    request = str(case.vars["request"])
    started = perf_counter()
    said = app.answer(request, _model(request))
    # A duration is not a clock, so measuring one here is allowed. No
    # `LatencyBudget` on this path all the same: a ceiling a fake model can
    # never touch is a check that is green by construction.
    return Response(
        output=said,
        input=request,
        latency_ms=(perf_counter() - started) * 1000,
    )


suite = Suite(
    tenant="riverbend",
    environment="staging",
    name="handbook",
    assertions=[
        # The contract with whatever unpacks this record. First, because every
        # check below is meaningless if the shape went somewhere else.
        JsonSchema(schema=SCHEMA),
        # Grounding: the record names the page it came from. This is the one
        # that goes red when a model upgrade quietly drops the citation.
        Contains(needle="handbook/"),
        # And the regression a new model version brings more often than any
        # other: the JSON arrives wrapped in a code fence, and every consumer
        # downstream breaks on a string that still looks right in a report.
        NotContains(needle="```"),
        # The part no string comparison reaches.
        LlmRubric(rubric=RUBRIC, judge=JUDGE, threshold=0.8, tolerance=0.1),
    ],
    cases=[
        Case(
            id=case["id"],
            vars={"request": case["request"]},
            # The passage step one selected, frozen in so the judge reads what
            # the chain was given rather than retrieving a second time.
            context=[app.passage(case["request"])],
        )
        for case in CASES
    ],
    # The prompt is the thing under test, so every run records it and the report
    # shows what changed above the scores it moved.
    artifacts=[Path("prompts/extract.txt"), Path("prompts/request.txt")],
)
