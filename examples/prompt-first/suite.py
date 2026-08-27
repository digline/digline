"""A prompt under test, with nothing else built yet.

There is no application here: a prompt, five questions, and the answers they
ought to get. That is enough to tell whether an edit to the prompt made things
better or only different — which is the question you actually have on day one,
and the one you cannot answer by reading the diff.

Both prompt files are recorded in every run, so the committed baseline carries
the prompt that produced it and the report shows what changed.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from digline.core import JudgeReply, Levenshtein, LlmRubric, Repeated
from digline.run import Case, Suite
from digline_anthropic import AnthropicTarget

import fake

HERE = Path(__file__).parent
LIVE = os.environ.get("DIGLINE_LIVE") == "1"
MODEL = "claude-haiku-4-5"


def judge(prompt: str) -> JudgeReply:
    """The rubric's judge.

    Faked by default, for the same reason the provider is: an example that needs
    a key is an example nobody runs. Deterministic, and it reads the answer
    rather than pretending to — a fake that always says 1.0 measures nothing.
    """
    if LIVE:  # pragma: no cover - exercised only with a key present
        return _live_judge(prompt)
    answer = prompt.split("Output to judge:", 1)[-1].strip()
    one_sentence = answer.count(".") <= 1
    warm = any(word in answer.lower() for word in ("welcome", "we ", "you", "happy"))
    return JudgeReply(
        score=0.4 + 0.3 * one_sentence + 0.3 * warm,
        reason=f"one_sentence={one_sentence}, warm={warm}",
    )


def _live_judge(prompt: str) -> JudgeReply:  # pragma: no cover - needs a key
    import anthropic

    reply = anthropic.Anthropic().messages.create(
        model=MODEL,
        max_tokens=200,
        system=(
            "Score the output against the rubric from 0 to 1. Reply with only "
            'a JSON object: {"score": <float>, "reason": "<one sentence>"}'
        ),
        messages=[
            {"role": "user", "content": prompt},
            {"role": "assistant", "content": "{"},
        ],
    )
    # Only the text blocks: the SDK's `content` is a union, and a thinking or
    # tool block has no `.text` at all — which a type checker says before a
    # traceback does.
    said = "".join(b.text for b in reply.content if b.type == "text")
    data = json.loads("{" + said)
    return JudgeReply(score=float(data["score"]), reason=str(data["reason"]))


target = AnthropicTarget(
    prompt_file=HERE / "prompts" / "user.txt",
    system_file=HERE / "prompts" / "system.txt",
    model=MODEL,
    max_tokens=200,
    client=None if LIVE else fake.FakeAnthropic(),
)

suite = Suite(
    tenant="bookshop",
    environment="dev",
    name="replies",
    assertions=[
        # How far the answer is from the one you would have written. Graded, so
        # "nearly right" is a number rather than a coin toss.
        Levenshtein(threshold=0.75, tolerance=0.05),
        # And the part no string comparison reaches. Wrapped, because a judge
        # asked twice does not answer twice the same way.
        Repeated(
            inner=LlmRubric(
                rubric="One sentence, warm, and invents no price or date.",
                judge=judge,
                # 0.65, not 0.70, and the reason is worth knowing: this judge
                # can return exactly 0.70, and a score that lands *on* its own
                # threshold is where digline 0.1.1 folds a passing check into an
                # `error` (friction 31, fixed after 0.1.1). Putting a bar on a
                # value the system produces exactly is a bad idea anyway — half
                # the runs land on either side of it.
                threshold=0.65,
                tolerance=0.1,
            ),
            samples=3,
            min_agreement="2/3",
        ),
    ],
    cases=[
        Case(id=c["id"], vars=c["vars"], expected=c["expected"])
        for c in json.loads((HERE / "cases.json").read_text(encoding="utf-8"))
    ],
)
