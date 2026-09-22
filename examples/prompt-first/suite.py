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
from digline.run import Calibration, Case, Suite
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

#: The case that watches the judge instead of the model, and it is **behind
#: `DIGLINE_LIVE` like the judge it watches**. A calibration case asks where a
#: judge places an answer known to be half right; the real judge is already
#: behind that door, so the control belongs on the same side of it. Cases are
#: outside `config_hash` (`run/suite.py`), so its presence moves no fingerprint.
#:
#: The answer is **truthful and deficient**: three clipped sentences, cold, and
#: unhelpfully vague — it fails the rubric's *one sentence* and *warm* clauses
#: and satisfies the third, inventing no price and no date. A judge with a scale
#: puts that inside its working range. A judge that has collapsed onto the
#: extremes scores it 0 or 1 and is caught, which no amount of repetition would
#: catch: a collapsed judge is *more* repeatable, not less.
#:
#: **The first answer written here was disqualifying, not partial**, and that
#: is the correction worth keeping rather than hiding. It invented a price,
#: which the rubric forbids outright, and the live judge scored it 0.000 twice
#: — a hard, repeatable refusal. The band then read that as a lost scale, which
#: it was not: in the same run the judge graded the five real answers across
#: 0.266 to 0.650. ADR 0024 §4 says whether an answer makes a good calibration
#: is the author's craft and nothing here checks it. This is that sentence
#: arriving: the band had been authored against a judge nobody had ever
#: watched, and the first thing watching it revealed was the author's error,
#: not the instrument's.
#:
#: The band is authored against what the judge's scale *is*, measured: on real
#: answers through this prompt it works between roughly 0.27 and 0.65, never
#: near either extreme. 0.20–0.70 contains that working range and excludes both
#: ends, so it catches a collapse without being fitted to any single reading.
#:
#: The band is wide on purpose. It is a control on the instrument, not a second
#: threshold on the prompt, and a narrow one would fail on the judge's ordinary
#: noise.
#:
#: **On its first outing it caught a judge with no scale, and the judge was
#: ours.** The stand-in below scores this answer 1.0 — it checks sentence count
#: and warmth, and cannot see the invented price at all — so it lands outside
#: the band and the run exits 2. That is the instrument working, not a defect
#: in it: the stand-in is honest about what it is, and nothing until now could
#: *say* so. The calibration case said it in one run.
#:
#: **Do not fix this by teaching the stand-in to see the price.** A stand-in
#: that can read the rubric is no longer standing in, and a calibration case it
#: passes by construction is a gate that cannot fail — the vacuously green
#: assertion fixed decision 3 forbids, pointed at the instrument instead of at
#: the system. The control belongs behind the same door as the judge it
#: controls, which is where it is.
CALIBRATION = (
    [
        Case(
            id="calibration-half-right",
            # The target is never called for this case, but every case is still
            # preflighted against the prompt template, so the variable has to
            # be here. It is the question the calibration shows the judge.
            vars={"question": "How much is a signed copy?"},
            calibration=Calibration(
                check="llm_rubric",
                input="How much is a signed copy?",
                output=(
                    "Signed copies. Sometimes there are some. You could ask "
                    "at the counter I suppose."
                ),
                low=0.20,
                high=0.70,
            ),
        )
    ]
    if LIVE
    else []
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
                threshold=0.7,
                tolerance=0.1,
            ),
            samples=3,
            min_agreement="2/3",
        ),
    ],
    # Two, because a suite that declares a calibration case has to repeat: one
    # judgement of a known answer is one draw of a noisy instrument, and every
    # wobble outside the band would stop a release. Declared for both modes
    # rather than only the live one, so that `config_hash` is the same
    # question on both sides of the door — a suite that fingerprinted
    # differently depending on an environment variable would report
    # `config_changed` against its own baseline.
    samples=2,
    min_agreement="2/2",
    cases=[
        Case(id=c["id"], vars=c["vars"], expected=c["expected"])
        for c in json.loads((HERE / "cases.json").read_text(encoding="utf-8"))
    ]
    + CALIBRATION,
    record_responses=True,
)
