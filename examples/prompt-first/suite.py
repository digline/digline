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
from digline_anthropic import AnthropicJudge, AnthropicTarget

import fake

HERE = Path(__file__).parent
LIVE = os.environ.get("DIGLINE_LIVE") == "1"
MODEL = "claude-haiku-4-5"


def _fake_judge(prompt: str) -> JudgeReply:
    """The rubric's judge on the keyless path.

    Faked by default, for the same reason the provider is: an example that needs
    a key is an example nobody runs. Deterministic, and it reads the answer
    rather than pretending to — a fake that always says 1.0 measures nothing.
    """
    answer = prompt.split("Output to judge:", 1)[-1].strip()
    one_sentence = answer.count(".") <= 1
    warm = any(word in answer.lower() for word in ("welcome", "we ", "you", "happy"))
    return JudgeReply(
        score=0.4 + 0.3 * one_sentence + 0.3 * warm,
        reason=f"one_sentence={one_sentence}, warm={warm}",
    )


#: A plugin is a target *and* a judge (ADR 0004): on the live path the twenty
#: lines of SDK-and-JSON leave this file, and the run records which model graded.
JUDGE = AnthropicJudge(model=MODEL) if LIVE else _fake_judge


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
#: **The band is derived from the purpose, not from a judge.** What it has to
#: catch is a lost scale: a judge collapsed onto an extreme gives this answer 0,
#: or 1, at every judging. The score the band reads is the folded mean of
#: **fifteen judgings**, `samples=5` times the three judgings of each sample, so
#: a collapse reads exactly 0.0 or 1.0, and one stray judging at the other
#: extreme moves that by 1/15, 0.067. **0.10–0.90** catches a collapse even with
#: one stray judging, and admits any judge that uses the inside of its scale.
#:
#: **The derivation depends on the configuration.** With `samples=3`, nine
#: judgings, one stray judging moves the mean by 0.111, which is beyond 0.10,
#: and a collapse with one stray judging would pass. Whoever changes `samples`,
#: the judgings per sample in `Repeated` below, or `min_agreement` changes this
#: derivation, and has to redo it here. It is a number derived from a
#: configuration, not an absolute.
#:
#: **What this control does not tell you.** It catches a collapse onto the
#: extremes and nothing else. It passes a compressed scale: a judge that gives
#: everything 0.35 or 0.5. It passes a judge that ranks this answer under the
#: real ones, and one that gives every answer the same score. On 2026-10-28 the
#: real answers' run means, 0.237 to 0.597, sat inside the band too. A narrower
#: band would catch more, and it would be bound to the judge it was measured on.
#: The band before this one, 0.70–0.95, was authored on the function judge this
#: example used until #651. On `AnthropicJudge` it held this answer by 0.015
#: over four live runs (samples 0.700 to 0.800, mean 0.725), and no longer
#: separated it from the real answers, whose samples reached 0.767.
#:
#: That the deficient answer outscores every real one is not a fault in the
#: band. It is what this rubric does, and it is recorded as its own finding:
#: the dominant clause forbids inventing, and silence invents nothing.
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
                low=0.10,
                high=0.90,
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
                judge=JUDGE,
                threshold=0.7,
                tolerance=0.1,
                # A movement inside two standard errors of the baseline's own
                # samples is noise, not a verdict: two live runs of one tree
                # moved this rubric by 0.133 on one case and 0.106 on another,
                # each inside the other run's spread. (#651)
                floor_standard_errors=2,
            ),
            samples=3,
            min_agreement="2/3",
        ),
    ],
    # Five, and the number matters more than the constraint that forced it.
    # A calibration case requires at least two — one judgement of a known
    # answer is one draw of a noisy instrument — but **two is a value that
    # cannot work against a real judge**: two samples are unanimous or split,
    # and there is no majority to take. Against a judge that legitimately
    # returns 0.33 and 0.95 on the same answer, `min_agreement="2/2"` errors
    # the case and `promote` then refuses the run. So the floor a calibration
    # case imposes is three. Five is what the rubric's noise floor asks: it is
    # measured from the baseline's samples, and with three a check's samples
    # came back all equal in one set of twelve, which leaves it no floor at
    # all. With five that is about one baseline in two hundred. A majority of
    # five is three. Declared for both modes rather than
    # only the live one, so that the sampling is not what tells them apart.
    # The judge is: the live path grades with `AnthropicJudge` and the keyless
    # one with a function, two identities, so `config_hash` differs on the two
    # sides of the door. The committed baseline is a live run, and
    # `tests/test_check_kind.py` reads it live, in `LIVE_BASELINES`. (#651)
    samples=5,
    min_agreement="3/5",
    cases=[
        Case(id=c["id"], vars=c["vars"], expected=c["expected"])
        for c in json.loads((HERE / "cases.json").read_text(encoding="utf-8"))
    ]
    + CALIBRATION,
    record_responses=True,
)
