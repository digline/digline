"""The system under test, and the judge that grades it. Both fake, both honest.

An example that needs an API key is an example nobody runs, so the application
here is a dictionary and the judge is a function. They are also the **only**
two files in this directory that know what is being demonstrated: `loop.py`,
`dossier.py` and the workflow never learn which scenario they are watching,
which is the point — an operator that could see the answer would be proving
nothing.

Two environment variables steer them, read once at import:

    OPERATOR_SCENARIO      steady | wobble | drift | structural  (default steady)
    DIGLINE_OPERATOR_SEED  the run's index in the cycle, 0-based  (default 0)

`steady` at seed 0 is what the committed baseline was promoted from, which is
why `digline run` with no environment at all reproduces it exactly.
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Mapping

from digline.core import JUDGE_OUTPUT_LABEL, ConfigValue, JudgeReply
from digline.run import Case, Response

#: What the system does today. `steady` is the world the baseline was approved
#: in; the other three are the events the operator has to tell apart.
SCENARIO = os.environ.get("OPERATOR_SCENARIO", "steady")

#: Which run of the cycle this is: 0 for the first, 1 and 2 for the re-runs.
#: `loop.py` sets it; a real target would ignore it. It stands in for the
#: run-to-run variation a real system has on its own — and because it is
#: declared rather than sampled, the alert this example ships can be reproduced
#: byte for byte by a test.
SEED = int(os.environ.get("DIGLINE_OPERATOR_SEED", "0"))

SIGNOFF = "— Northwind Support"

SYSTEM_PROMPT = (
    "You are Northwind Support. Answer the customer's question in at most "
    "three sentences, commit to an answer rather than deferring it, and sign "
    "off as Northwind Support."
)

#: What the assistant replies when nothing is wrong.
ANSWERS: Mapping[str, str] = {
    "where-is-my-order": (
        "Order 4821 left our warehouse on Tuesday and is due Thursday. You "
        f"will get a tracking link by email as soon as it is scanned. {SIGNOFF}"
    ),
    "how-do-i-return": (
        "You can return any unworn item within 30 days. Print a label from "
        f"your order page and drop the parcel at any pickup point. {SIGNOFF}"
    ),
    "is-it-waterproof": (
        "The trail backpack is water resistant, not waterproof: it handles "
        f"rain but should not be submerged. {SIGNOFF}"
    ),
}

#: The one case that moves, and how. The model stops answering and starts
#: deferring — the failure mode a rubric is there to catch and a `contains`
#: check never would. One case, because one case moving is exactly what
#: `AGENTS.md` §3 calls a draw until it repeats.
DEFERRING_CASE = "is-it-waterproof"
DEFERRED = (
    "I do not have that detail to hand for the trail backpack, and it might "
    "be water resistant rather than waterproof. Have a look at the product "
    f"page, or write to us again and we will find out. {SIGNOFF}"
)


def _answer(case_id: str) -> str:
    """What the application replies, under the scenario in force."""
    if SCENARIO == "structural":
        # The sign-off is gone from every answer at once: three cases flip on
        # the same check in one run, which `AGENTS.md` §4 says is investigated
        # and never retried.
        return ANSWERS[case_id].replace(f" {SIGNOFF}", "")
    deferring = SCENARIO == "drift" or (SCENARIO == "wobble" and SEED == 0)
    if deferring and case_id == DEFERRING_CASE:
        return DEFERRED
    return ANSWERS[case_id]


class SupportDesk:
    """The application under test, and the configuration it ran under.

    A class rather than a plain function because `config` has to be an
    attribute: `HasConfig` is how a run records *which model answered*, and
    without it a comparison would report the system as unchanged on the day
    somebody swapped the model (ADR 0005). Everything else about it is a
    function — `__call__` is the whole interface a `Target` has.
    """

    #: Flat and scalar, and only what was actually sent. A real one reports
    #: what its SDK was configured with.
    config: Mapping[str, ConfigValue] = {
        "provider": "northwind-inhouse",
        "model": "support-desk-2",
        "temperature": 0.0,
    }

    def __call__(self, case: Case) -> Response:
        question = str(case.vars["question"])
        return Response(
            output=_answer(case.id),
            # The rendered prompt. Without it the rubric would judge an answer
            # without knowing the question.
            input=f"{SYSTEM_PROMPT}\n\nCustomer question: {question}",
            cost_usd=0.0042,
            latency_ms=180.0,
        )


target = SupportDesk()


# --------------------------------------------------------------------------- #
# The judge
# --------------------------------------------------------------------------- #

#: How many times each prompt has been graded, so a repeated judge can vary the
#: way a real one does. `Repeated` hands the judge the same prompt N times, so
#: counting is the only signal a deterministic fake has. Keyed on the prompt
#: rather than on one global counter, so the sequence does not depend on the
#: order the cases happen to be judged in.
_graded: dict[str, int] = {}

#: The phrases that mean "I am not going to answer this". Matched on the answer
#: alone, never on the whole prompt: the rubric and the question are our own
#: words, and a judge that read them would be grading itself.
DEFERRALS = ("do not have", "might be", "have a look", "write to us")


def _jitter(prompt: str, sample: int) -> float:
    """A spread of ±0.04, as a pure function of the prompt, the sample and the
    run's seed.

    This is what gives the check a *measured interval*. Without it every sample
    of a `Repeated` is the same number, the noise floor is a point, and "the
    drop repeated beyond the measured floor" — the sentence the operator
    classifies on — would be a sentence about nothing.

    `hashlib` and not `hash()`: Python salts the hash of a string per process,
    so a baseline committed on it would not reproduce on the next run.
    """
    digest = hashlib.sha256(f"{prompt}|{sample}|{SEED}".encode()).digest()
    return (digest[0] / 255.0 - 0.5) * 0.08


def judge(prompt: str) -> JudgeReply:
    """Stand-in for a model asked to grade the answer against the rubric.

    Three properties it genuinely reads, plus the jitter above. A fake that
    always returned 1.0 would measure nothing, and the operator would spend its
    week classifying noise this file had invented.
    """
    answer = prompt.split(JUDGE_OUTPUT_LABEL, 1)[-1].strip()
    lowered = answer.lower()
    signed = SIGNOFF in answer
    concise = len(answer.split()) <= 45
    committed = not any(phrase in lowered for phrase in DEFERRALS)

    seen = _graded.get(prompt, 0)
    _graded[prompt] = seen + 1

    base = 0.10 + 0.25 * signed + 0.20 * concise + 0.35 * committed
    return JudgeReply(
        score=round(base + _jitter(prompt, seen), 4),
        reason=f"signed={signed}, concise={concise}, committed={committed}",
    )
