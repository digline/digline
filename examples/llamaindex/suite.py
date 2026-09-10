"""A LlamaIndex query engine, evaluated in process.

No server and no HTTP: the target is a plain function that calls the engine the
application already has. What is under test is the whole pipeline — retrieval,
prompt, synthesis — which is what makes this different from `examples/rag`.
There the retrieved passages are frozen into the cases and only the generator
is measured; here the index is rebuilt and queried on every run, so a change to
the corpus, the chunking or the retriever moves the numbers.

Each case declares **the page that ought to answer it**, and that page is the
case's context. So `faithfulness` asks a question retrieval cannot dodge: the
answer has to be supported by the page this question belongs to. Answer it
beautifully from the wrong page and the check goes red.

Two paths, one switch. By default the engine runs on a local embedding
stand-in and a scripted model, so this needs no key and answers the same way
every time; that is what CI runs. `DIGLINE_LIVE=1` puts a real model under the
synthesizer and a real judge behind `faithfulness`. They are different systems
and each keeps its own baseline.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from time import perf_counter

from digline.core import (
    JUDGE_OUTPUT_LABEL,
    ClaimJudge,
    ClaimReply,
    Faithfulness,
    Length,
    NotContains,
    Regex,
)
from digline.run import Case, Response, Suite
from digline_anthropic import AnthropicClaimJudge
from llama_index.core.llms import LLM

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

#: The citation the prompt asks for, and the closed set of pages it may name.
#: One check rather than two: a missing citation, an invented page and the
#: `"Empty Response"` LlamaIndex returns when the retriever finds nothing all
#: arrive here, and a second assertion saying the same thing would make every
#: diff twice as long and no more informative.
CITES_A_PAGE = r"\nSource: (?:{})$".format("|".join(sorted(app.PAGES)))

#: The prompt's own label for the rider's question. It has no business in an
#: answer: if it is there, the model is continuing the prompt instead of
#: answering it. See `README.md` §3 — swap in LlamaIndex's own `MockLLM` and
#: this is the check that goes red.
PROMPT_FURNITURE = "Question:"


def _fake_claim_judge(prompt: str) -> ClaimReply:
    """Counts claims and how many the page supports. Never divides.

    digline does the arithmetic: a model asked for a ratio returns a number
    nobody can check, one asked for two counts returns something arithmetic can
    contradict. Faked here, and deliberately not generous — a stand-in that
    always answered "all supported" would leave `faithfulness` measuring
    nothing, which is the one thing digline refuses.
    """
    # Every judged assertion sends one shape, and the output is last, behind
    # this label. Imported rather than typed: it is the interface.
    context, _, said = prompt.partition(JUDGE_OUTPUT_LABEL)
    page = context.lower()
    claims = [
        sentence.strip()
        for sentence in said.split(".")
        # The citation line is not a claim about the world — it is a pointer,
        # and `regex` above is what holds it. Counting it as a claim would let
        # a wrong answer buy back a fifth of its score by citing correctly.
        if sentence.strip() and not sentence.strip().startswith("Source:")
    ]
    supported = sum(1 for claim in claims if _covered(claim, page))
    return ClaimReply(
        supported=supported,
        total=len(claims),
        reason=f"{supported} of {len(claims)} claims appear in the page",
    )


def _covered(claim: str, page: str) -> bool:
    """A claim is supported when every content word of it is on the page."""
    words = [word.strip(",;:()").lower() for word in claim.split() if len(word) > 4]
    return bool(words) and all(word in page for word in words)


#: A plugin is a target *and* a judge (ADR 0004): on the live path the twenty
#: lines of SDK-and-JSON leave this file, and the run records which model graded.
JUDGE: ClaimJudge = (
    AnthropicClaimJudge(model=JUDGE_MODEL) if LIVE else _fake_claim_judge
)


def _llm() -> LLM:
    if LIVE:  # pragma: no cover - needs a key
        from llama_index.llms.anthropic import Anthropic

        return Anthropic(model=MODEL, temperature=0.0)
    return fake.HandbookLLM()


def target(case: Case) -> Response:
    """The target: a function that queries the engine. No HTTP, no subprocess."""
    question = str(case.vars["question"])
    started = perf_counter()
    said = app.answer(question, _llm())
    # A duration is not a clock, so measuring one here is allowed. No
    # `LatencyBudget` on this path all the same: a ceiling a scripted model can
    # never touch is a check that is green by construction.
    return Response(
        output=said,
        input=question,
        latency_ms=(perf_counter() - started) * 1000,
    )


suite = Suite(
    tenant="kestrel",
    environment="staging",
    name="hire",
    assertions=[
        # Grounding, as a string: the answer names the page it came from, and
        # names one that exists. First, because it is the check that notices
        # retrieval returning nothing at all.
        Regex(pattern=CITES_A_PAGE, name="cites_a_page"),
        # The model answering rather than continuing. A synthesizer that hands
        # the prompt back reads plausibly in a log and breaks everything after
        # it — the failure this example was built around.
        NotContains(needle=PROMPT_FURNITURE, name="does_not_echo_the_prompt"),
        # A floor under the answer. The degenerate reply — a stub, an apology,
        # the fallback the model reaches for when the passage is empty — is
        # short, and nothing else here would see it.
        Length(minimum=60, name="says_something"),
        # The part no string comparison reaches: is the answer supported by the
        # page this question belongs to. Retrieval is inside this check, not
        # beside it.
        Faithfulness(judge=JUDGE, threshold=0.8, tolerance=0.1),
    ],
    cases=[
        Case(
            id=case["id"],
            vars={"question": case["question"]},
            # The page that *ought* to answer this question — declared, not
            # retrieved. Retrieval runs live in the target, so freezing what it
            # found would be grading the run against itself.
            context=[app.page(case["source"])],
        )
        for case in CASES
    ],
    # The prompt is the thing under test, so every run records it and the report
    # shows what changed above the scores it moved.
    artifacts=[Path("prompts/qa_template.txt")],
)
