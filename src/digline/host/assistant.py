"""The assistant `digline suggest` asks, where one is declared. (ADR 0063 §4)

**Declared, or never called.** `[suggest] model` in a `suite.toml`, or
`--model`, which wins; with neither, no call is made and the proposal is the
one the rules alone write (fixed decision 5).

**Built as a judge is built**, from its coordinates through the provider
plugin's judge, and asked through the judge's own call, `_ask_as`: priced,
counted and read by the same code, with an instruction of its own and a reply
allowance of `MAX_TOKENS`. It is never the suite's judge and gives no verdict.

**What it is given follows the capture's regime.** Under `"private"`, the
suite's recordings and the reviewed answers, whole. Under `"public"`, the
shape alone: kinds, finishes, the tools declared and called, the checks
already proposed, which carry the keys and the regularities of the steps, and
counts. No input, no answer and no step's arguments. The calls no suite named
are never given, under either regime.

**At most `MAX_RECORDINGS` recordings and `MAX_CHARS` characters**, the newest
of the setups in force first, each whole and never cut. Without a bound, 50
recordings at the recorder's ceiling of 65,536 characters for the input, the
answer and the trajectory are about 9.8 million characters.

**What it costs is said before the call**, as `digline run` says its plan:
one call, the material, the input tokens estimated, the output allowance and
the most it can cost. A model the plugin's list does not know is refused
before the call, because the judge's call raises on a reply it cannot price
once that reply is paid for.
"""

from __future__ import annotations

import json
import math
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from digline.core import EvaluatorInputs, Verdict
from digline.core.recording import Recording, instant_of
from digline.core.refused import RefusedError
from digline.core.suggest import Proposed, handle
from digline.host.toml_suite import assistant_of, check_of
from digline.run.suite import Case
from digline.targets import JudgeBase
from digline.targets.pricing import Usage

__all__ = [
    "MAX_CHARS",
    "MAX_RECORDINGS",
    "MAX_TOKENS",
    "Material",
    "announcement",
    "ask",
    "assistant",
    "material",
    "refused_by",
]

#: The reply's allowance: a rubric, a sentence for each check, the limits and
#: a counterexample.
MAX_TOKENS = 4000

#: The most recordings the assistant is given.
MAX_RECORDINGS = 50

#: The most characters of material it is given, recordings and reviewed
#: answers together, each whole.
MAX_CHARS = 200_000

#: Characters per token where no recording of the suite reports its tokens: a
#: convention, not a measurement, and said as one.
CONVENTION = 4

#: The assistant's instruction. Its reply is one JSON object, read by
#: `digline.core.suggest.merged`, which keeps what this allows and discards the
#: rest.
SYSTEM = """\
You help a developer write a first evaluation suite for an application that \
calls a language model. digline has already proposed the suite's checks from \
rules every recording holds. You may not add a check, remove one, or name a \
case: you write text into the checks that are there.

You are given the proposed checks, each with an id such as "check-1", its \
type and parameters, which parameters are placeholders, and why digline \
proposes it; and the material the regime allows: under "private" the \
recordings and the reviewed answers, under "public" their shape alone.

Reply with one JSON object and nothing else, with any of these four keys:

- "rubric": {"<id>": "<one question a good answer says yes to>"}, only for a \
check whose parameters hold an "inner" llm_rubric;
- "why": {"<id>": "<one sentence on why this check is there>"};
- "limits": {"<id>.<parameter>": <number>}, for "maximum", "limit", \
"max_usd", "max_ms" or "inner.threshold": a ceiling no higher and a \
threshold no lower than the one written, unless it is a placeholder;
- "counterexample": {"vars": {<the case's input, keyed as the recordings' \
case>}, "answer": "<an answer the suite must refuse>"}.
"""


@dataclass(frozen=True, slots=True)
class Material:
    """What the assistant is given, as the prompt, and the counts said of it."""

    prompt: str
    regime: str
    recordings: int
    #: Left out at the bound of `MAX_RECORDINGS` and `MAX_CHARS`.
    recordings_left: int
    reviewed: int
    reviewed_left: int
    #: Left out because they were recorded under a setup no longer in force:
    #: a reason of its own, counted apart from the bound. (P-1588)
    recordings_earlier: int = 0


def assistant(coordinate: str, where: str) -> JudgeBase:
    """The assistant, from its coordinates. A plugin's judge that is not a
    `JudgeBase` has no call to ask it through, and is refused by name."""
    built = assistant_of(coordinate, where=where, max_tokens=MAX_TOKENS)
    if not isinstance(built, JudgeBase):
        raise RefusedError(
            f"{where}: the judge of {coordinate.split('/')[0]!r} is not a "
            "digline JudgeBase, so digline suggest has no call to ask it "
            "through (ADR 0063 §4)"
        )
    if not built.pricing.knows(built.model):
        # Refused before the call, not after it: the judge's call prices
        # every reply it reads and raises on a model its list does not know,
        # once the call is paid for (ADR 0004 §8.6).
        raise RefusedError(
            f"{where}: {coordinate.split('/')[0]}'s price list has no price "
            f"for {built.model!r}, and the judge's call the assistant is asked "
            "through refuses a reply it cannot price, after paying for it. No "
            "call was made: name a model the list knows"
        )
    return built


def _newest_first(eligible: Sequence[Recording]) -> list[Recording]:
    """The recordings of the setups in force, the newest first: by
    `recorded_at` where they carry it, then by the files' order, later
    first."""
    in_force: dict[bool, str] = {}
    for form in (True, False):
        own = [r for r in eligible if r.is_episode == form]
        if own:
            in_force[form] = _ordered(own)[0].setup_digest
    return _ordered(
        [r for r in eligible if in_force.get(r.is_episode) == r.setup_digest]
    )


def _ordered(recordings: Sequence[Recording]) -> list[Recording]:
    keyed = [
        (instant_of(r.recorded_at) if r.recorded_at is not None else "", index, r)
        for index, r in enumerate(recordings)
    ]
    return [r for _, _, r in sorted(keyed, key=lambda t: (t[0], t[1]), reverse=True)]


def _steps(recording: Recording) -> list[dict[str, object]] | None:
    steps = recording.response.steps
    if steps is None:
        return None
    return [
        {
            "actor": step.actor,
            **({"finish": step.finish} if step.finish is not None else {}),
            **(
                {"tool": step.call.tool, "arguments": step.call.arguments}
                if step.call is not None
                else {}
            ),
        }
        for step in steps
    ]


def _recorded(recording: Recording) -> dict[str, object]:
    return {
        "input": recording.response.input,
        "answer": recording.response.output,
        "kind": recording.response.kind,
        "steps": _steps(recording),
    }


def _reviewed(case: Case) -> dict[str, object]:
    answer = case.reviewed_answer
    assert answer is not None
    return {
        "input": answer.input,
        "answer": answer.output,
        "check": answer.check,
        "good": answer.good,
    }


def _text(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _checks(checks: Sequence[Proposed]) -> list[dict[str, object]]:
    return [
        {
            "id": handle(number),
            "type": check.type,
            "params": check.params,
            "placeholders": list(check.placeholders),
            "why": check.why,
        }
        for number, check in enumerate(checks, start=1)
    ]


def _shape(eligible: Sequence[Recording], declared: Sequence[str]) -> dict[str, object]:
    """What a recording's shape says, and no text of it: kinds, finishes,
    the tools declared and the tools called, and how many steps."""
    kinds = Counter(str(r.response.kind) for r in eligible)
    finishes = Counter(
        str(step.finish)
        for r in eligible
        for step in r.response.steps or ()
        if step.actor == "model"
    )
    called = sorted(
        {
            str(step.call.tool)
            for r in eligible
            for step in r.response.steps or ()
            if step.call is not None and step.call.tool is not None
        }
    )
    steps = [len(r.response.steps) for r in eligible if r.response.steps is not None]
    return {
        "kinds": dict(kinds),
        "finishes": dict(finishes),
        "tools_declared": list(declared),
        "tools_called": called,
        "steps": {"fewest": min(steps), "most": max(steps)} if steps else None,
    }


def material(
    *,
    suite: str,
    regime: str,
    eligible: Sequence[Recording],
    reviewed: Sequence[Case],
    checks: Sequence[Proposed],
    declared: Sequence[str],
) -> Material:
    """The prompt, under the capture's regime. Never an `_unassigned` call:
    `eligible` holds the suite's recordings alone."""
    yes = sum(1 for c in reviewed if c.reviewed_answer and c.reviewed_answer.good)
    document: dict[str, object] = {
        "suite": suite,
        "regime": regime,
        "checks": _checks(checks),
        "counts": {
            "recordings": len(eligible),
            "reviewed_yes": yes,
            "reviewed_no": len(reviewed) - yes,
        },
    }
    if regime != "private":
        # The shape, not the text (ADR 0063 §6, as ruled on 2026-11-06).
        document["shape"] = _shape(eligible, declared)
        return Material(
            prompt=_text(document),
            regime=regime,
            recordings=0,
            recordings_left=len(eligible),
            reviewed=0,
            reviewed_left=len(reviewed),
        )
    chosen: list[dict[str, object]] = []
    spent = len(_text(document))
    newest = _newest_first(eligible)
    earlier = len(eligible) - len(newest)
    for recording in newest:
        entry = _recorded(recording)
        size = len(_text(entry))
        if len(chosen) == MAX_RECORDINGS or spent + size > MAX_CHARS:
            break
        chosen.append(entry)
        spent += size
    answers: list[dict[str, object]] = []
    for case in reviewed:
        entry = _reviewed(case)
        size = len(_text(entry))
        if spent + size > MAX_CHARS:
            break
        answers.append(entry)
        spent += size
    document["recordings"] = chosen
    document["reviewed"] = answers
    return Material(
        prompt=_text(document),
        regime=regime,
        recordings=len(chosen),
        recordings_left=len(newest) - len(chosen),
        reviewed=len(answers),
        reviewed_left=len(reviewed) - len(answers),
        recordings_earlier=earlier,
    )


def _ratio(recordings: Sequence[Recording]) -> float | None:
    """Tokens per character of a request, read off the suite's recordings
    that report their input tokens: the input and the setup, as sent."""
    tokens = chars = 0
    for recording in recordings:
        usage = recording.response.usage
        if usage is None or not recording.response.input:
            continue
        tokens += usage.input_tokens
        chars += len(recording.response.input) + len(_text(recording.setup))
    return tokens / chars if tokens and chars else None


def _many(count: int, noun: str) -> str:
    return f"{count} {noun}{'' if count == 1 else 's'}"


def announcement(
    coordinate: str,
    judge: JudgeBase,
    given: Material,
    recordings: Sequence[Recording],
) -> str:
    """What the call will cost, said before it is made, and not asked."""
    ratio = _ratio(recordings)
    chars = len(SYSTEM) + len(given.prompt)
    if ratio is None:
        estimated = math.ceil(chars / CONVENTION)
        how = (
            f"at {CONVENTION} characters a token, a convention: no recording "
            "reports its tokens"
        )
    else:
        estimated = math.ceil(chars * ratio)
        how = "at the ratio the suite's recordings report"
    if given.regime == "private":
        what = (
            f"{_many(given.recordings, 'recording')} and "
            f"{_many(given.reviewed, 'reviewed answer')}"
        )
    else:
        what = "the shape of the recordings and the counts"
    usage = Usage(input_tokens=estimated, output_tokens=judge.max_tokens)
    price = judge.pricing.cost(judge.model, usage)
    return (
        f"assistant: 1 call to {coordinate}, {what}, about "
        f"{estimated:,} input tokens ({how}) and at most "
        f"{judge.max_tokens:,} output; at most ${price:.2f}"
    )


def ask(judge: JudgeBase, prompt: str) -> Mapping[str, Any] | None:
    """The one call, through the judge's own. `None` where the reply is no
    JSON object: none of it is used, and the proposal is the rules' alone."""
    try:
        # The judge's call with this command's instruction: one body that
        # times, prices and counts, not a second path (ADR 0063 §4).
        return judge._ask_as(SYSTEM, prompt)  # pyright: ignore[reportPrivateUsage]
    except ValueError:
        return None


def refused_by(checks: Sequence[Proposed], answer: str) -> list[str]:
    """The checks of the proposal that refuse `answer` on their own, without
    a judge: built as the loader builds them, each asked once. A check that
    reads what an answer alone does not carry, the steps, errors and is not
    counted."""
    refusing: list[str] = []
    for check in checks:
        if "inner" in check.params or check.type == "repeated":
            continue
        built = check_of({"type": check.type, **check.params}, "the proposal")
        verdict: Verdict = built(EvaluatorInputs(output=answer))
        if verdict.status == "fail":
            refusing.append(check.type)
    return refusing
