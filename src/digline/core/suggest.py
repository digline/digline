"""The rules a first suite is proposed by: checks read from regularities in a
suite's recorded answers, and limits read from its runs. (ADR 0063 §2, §3, §7)

Pure: each function takes the recorded responses or the runs and returns what
it would propose, and the host reads the files and writes the proposal.

**A check is proposed only from a regularity every recording holds**, never
one a single recording contradicts, because every case is asked every check
(ADR 0010 §5). One recording that breaks the rule takes the check out.

**A limit is read from the runs where they measured it, and is otherwise a
placeholder**: the strictest value the check accepts, so it fails until a
measured number replaces it. A placeholder is never a default that passes
(fixed decision 3).

**What a proposal says of itself is digline's words**: kinds, counts and the
names of checks. A tool's name or a key read from a recording goes into a
check's parameters, which is the rule, and into no sentence (ADR 0063 §6).

**What an assistant replies is merged, never obeyed** (§4): `merged` takes
from its reply a rubric for a judged check, a sentence of why beside a check,
a limit in place of a placeholder or stricter than the runs measured, and a
constructed counterexample. Anything else, a check of its own among them, is
discarded and counted.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import cast

from digline.core.run import RecordedResponse, Run, restore_output

__all__ = [
    "LIMITS",
    "PLACEHOLDER",
    "Counterexample",
    "Measured",
    "Merged",
    "Proposed",
    "declared_tools",
    "judged_check",
    "measured",
    "merged",
    "shape_checks",
    "step_checks",
]

#: Where no run measured a limit, the value written in its place: the
#: strictest the check accepts, at the six decimals every limit is compared at
#: (ADR 0009). It fails until a person writes a measured number. Tolerances are
#: placeholders too, at `0.0`, the strictest.
PLACEHOLDER: Mapping[str, float] = {
    "length.maximum": 0,
    "max_steps.limit": 1,
    "cost_budget.max_usd": 0.000001,
    "latency_budget.max_ms": 0.000001,
    "llm_rubric.threshold": 1.0,
    "tolerance": 0.0,
}


@dataclass(frozen=True, slots=True)
class Proposed:
    """One check the proposal writes: its TOML `type`, its parameters in the
    order written, why it is proposed, and which parameters are placeholders.

    `why` is digline's words alone: what was counted and what held, never a
    tool's name, a key or a quoted answer."""

    type: str
    params: Mapping[str, object]
    why: str
    placeholders: tuple[str, ...] = ()
    #: The assistant's sentence of why, where it wrote one, said beside
    #: digline's and never in place of it.
    said: str = ""
    #: The parameters the assistant wrote, each marked as its in the file.
    assisted: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Measured:
    """What the runs measured that a limit can be read from: the highest of
    each where the runs recorded the responses, and each check's lowest score.
    `None` is *not measured*, and the limit is then a placeholder."""

    runs: int = 0
    longest: int | None = None
    model_steps: int | None = None
    cost_usd: float | None = None
    latency_ms: float | None = None
    lowest: Mapping[str, float] = field(default_factory=dict[str, float])


def _many(count: int, noun: str) -> str:
    return f"{count} {noun}{'' if count == 1 else 's'}"


def _highest[T: (int, float)](values: Sequence[T]) -> T | None:
    return max(values) if values else None


def measured(runs: Sequence[Run]) -> Measured:
    """The limits the runs measured: the longest text answer in characters,
    the most model steps, the highest cost and latency among the responses
    they recorded, and each check's lowest score among its verdicts."""
    lengths: list[int] = []
    steps: list[int] = []
    costs: list[float] = []
    latencies: list[float] = []
    lowest: dict[str, float] = {}
    for run in runs:
        for result in run.results:
            for response in result.responses:
                if response.kind == "text" and response.output is not None:
                    lengths.append(len(response.output))
                if response.steps is not None:
                    steps.append(sum(1 for s in response.steps if s.actor == "model"))
                if response.cost_usd is not None:
                    costs.append(response.cost_usd)
                if response.latency_ms is not None:
                    latencies.append(response.latency_ms)
            for verdict in result.verdicts:
                score, name = verdict.score.score, verdict.score.name
                if score is None:
                    continue
                held = lowest.get(name)
                lowest[name] = score if held is None else min(held, score)
    return Measured(
        runs=len(runs),
        longest=_highest(lengths),
        model_steps=_highest(steps),
        cost_usd=_highest(costs),
        latency_ms=_highest(latencies),
        lowest=lowest,
    )


def _limit(
    value: float | None, key: str, runs: int, what: str
) -> tuple[float, str, bool]:
    """A limit, the sentence that says where it came from, and whether it is
    a placeholder."""
    if value is None:
        return (
            PLACEHOLDER[key],
            f"{key.split('.')[1]} is a placeholder, the strictest the check "
            "accepts: no run measured it",
            True,
        )
    return (
        value,
        f"{key.split('.')[1]} is the {what} seen in {_many(runs, 'run')}",
        False,
    )


def _json_type(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list | tuple):
        return "array"
    return "object"


def _draft_schema(values: Sequence[object]) -> dict[str, object]:
    """The keys every object carries, in the order first met, each with the
    type every one of them holds it as; an integer beside a number is a
    number. A key whose type varies is required and given no type."""
    if not all(isinstance(value, Mapping) for value in values):
        return {"type": "array"}
    objects = [cast(Mapping[str, object], value) for value in values]
    keys = list(dict.fromkeys(key for value in objects for key in value))
    required = [key for key in keys if all(key in value for value in objects)]
    properties: dict[str, object] = {}
    for key in required:
        types = {_json_type(value[key]) for value in objects}
        if types == {"integer", "number"}:
            types = {"number"}
        if len(types) == 1:
            properties[key] = {"type": types.pop()}
    schema: dict[str, object] = {"type": "object", "required": required}
    if properties:
        schema["properties"] = properties
    return schema


def shape_checks(
    responses: Sequence[RecordedResponse], found: Measured
) -> tuple[Proposed, ...]:
    """The checks the shape of every answer holds: `is_json` and a draft
    `json_schema` for answers that are JSON, `json_schema` alone for a
    structured output, which `is_json` does not read, and `length` for text.
    Answers of more than one kind hold no shape in common, and nothing is
    proposed from them."""
    count = len(responses)
    kinds = {response.kind for response in responses}
    if not responses or len(kinds) != 1:
        return ()
    (kind,) = kinds
    texts = [response.output for response in responses]
    if any(text is None for text in texts):
        return ()
    if kind == "structured":
        values = [restore_output(text, "structured") for text in texts if text]
        return (
            Proposed(
                type="json_schema",
                params={"schema": _draft_schema(values)},
                why=f"every one of {_many(count, 'recording')} answers a "
                "structure; the draft requires the keys every one carries",
            ),
        )
    if kind != "text":
        return ()
    parsed: list[object] = []
    for text in texts:
        try:
            parsed.append(json.loads(text or ""))
        except ValueError:
            break
    if len(parsed) == count and all(isinstance(v, dict | list) for v in parsed):
        top = (
            "object"
            if all(isinstance(v, dict) for v in parsed)
            else "array"
            if all(isinstance(v, list) for v in parsed)
            else "any"
        )
        return (
            Proposed(
                type="is_json",
                params={"top_level": top},
                why=f"every one of {_many(count, 'recording')} answers JSON, "
                f"top level {top}",
            ),
            Proposed(
                type="json_schema",
                params={"schema": _draft_schema(parsed)},
                why="the draft requires the keys every one of "
                f"{_many(count, 'recording')} carries",
            ),
        )
    maximum, said, placeholder = _limit(
        found.longest, "length.maximum", found.runs, "longest answer"
    )
    return (
        Proposed(
            type="length",
            params={"maximum": int(maximum), "unit": "characters"},
            why=f"every one of {_many(count, 'recording')} answers text; {said}",
            placeholders=("maximum",) if placeholder else (),
        ),
    )


def _tools(response: RecordedResponse) -> tuple[str | None, ...]:
    steps = response.steps or ()
    return tuple(step.call.tool for step in steps if step.actor == "tool" and step.call)


def _is_subsequence(wanted: Sequence[str], seen: Sequence[str]) -> bool:
    found = iter(seen)
    return all(any(tool == name for tool in found) for name in wanted)


def _common(first: Sequence[str], second: Sequence[str]) -> list[str]:
    """A longest common subsequence of two, by the textbook table."""
    rows, cols = len(first), len(second)
    table = [[0] * (cols + 1) for _ in range(rows + 1)]
    for i in range(rows - 1, -1, -1):
        for j in range(cols - 1, -1, -1):
            table[i][j] = (
                table[i + 1][j + 1] + 1
                if first[i] == second[j]
                else max(table[i + 1][j], table[i][j + 1])
            )
    common: list[str] = []
    i = j = 0
    while i < rows and j < cols:
        if first[i] == second[j]:
            common.append(first[i])
            i, j = i + 1, j + 1
        elif table[i + 1][j] >= table[i][j + 1]:
            i += 1
        else:
            j += 1
    return common


def _before(first: str, then: str, seen: Sequence[str]) -> bool:
    """`Before`'s rule on one trajectory: no `then` without a `first` before
    it. Where `then` is never called it holds."""
    if then not in seen:
        return True
    return first in seen[: seen.index(then)]


def _named(tools: object, *path: str) -> list[str]:
    """The names in a list of tool declarations, each read at `path`, or at
    `function.name` where `path` finds none."""
    names: list[str] = []
    if not isinstance(tools, list):
        return names
    for tool in cast(list[object], tools):
        name: object = tool
        for key in path:
            name = (
                cast(Mapping[str, object], name).get(key)
                if isinstance(name, Mapping)
                else None
            )
        if name is None and isinstance(tool, Mapping):
            function = cast(Mapping[str, object], tool).get("function")
            if isinstance(function, Mapping):
                name = cast(Mapping[str, object], function).get("name")
        if isinstance(name, str) and name:
            names.append(name)
    return names


def declared_tools(setups: Sequence[Mapping[str, object]]) -> tuple[str, ...]:
    """The tools a call declared to the model, in the order first met, in the
    shapes the provider maps record: under a setup's `tools`, by `name`, the
    Messages form, which an InvokeModel body on Bedrock carries too, or by
    `function.name`, OpenAI's; and under Bedrock Converse's `toolConfig`,
    `tools[].toolSpec.name`. A setup that declares none adds none."""
    names: list[str] = []
    for setup in setups:
        names += _named(setup.get("tools"), "name")
        config = setup.get("toolConfig")
        if isinstance(config, Mapping):
            tools = cast(Mapping[str, object], config).get("tools")
            names += _named(tools, "toolSpec", "name")
    return tuple(dict.fromkeys(names))


def step_checks(
    responses: Sequence[RecordedResponse],
    *,
    episodes: bool,
    declared: Sequence[str],
    found: Measured,
) -> tuple[Proposed, ...]:
    """The checks on the steps every recording holds. Nothing where a
    recording carries no steps, since a check on the steps errors on it.

    - `tools_called`, where every recording calls the same tools in the same
      order, and at least one;
    - otherwise `subsequence`, the longest run of tools common to every
      recording in order, where it holds two or more;
    - `before`, for each two tools where every call to the second has a call
      to the first before it, in every recording, and the second is called in
      at least one; not where the check above already says it;
    - `never`, for each tool declared to the model and called in none;
    - `max_steps` over the model's turns, where any recording is an episode.

    A recording with a tool call nobody named takes out every check that
    names tools: it may be any of them."""
    if not responses or any(response.steps is None for response in responses):
        return ()
    count = _many(len(responses), "recording")
    proposed: list[Proposed] = []
    sequences = [_tools(response) for response in responses]
    if all(None not in sequence for sequence in sequences):
        named = [[str(tool) for tool in sequence] for sequence in sequences]
        ordered: list[str] = []
        if named[0] and all(sequence == named[0] for sequence in named):
            ordered = named[0]
            proposed.append(
                Proposed(
                    type="tools_called",
                    params={"expected": list(ordered)},
                    why=f"every one of {count} calls the same "
                    f"{_many(len(ordered), 'tool')} in the same order",
                )
            )
        else:
            common = named[0]
            for sequence in named[1:]:
                common = _common(common, sequence)
            if len(common) >= 2 and all(_is_subsequence(common, s) for s in named):
                ordered = common
                proposed.append(
                    Proposed(
                        type="subsequence",
                        params={"tools": list(ordered)},
                        why=f"every one of {count} calls these "
                        f"{_many(len(ordered), 'tool')} in this order",
                    )
                )
        tools = list(dict.fromkeys(tool for sequence in named for tool in sequence))
        for then in tools:
            for first in tools:
                if first == then:
                    continue
                if (
                    first in ordered
                    and then in ordered
                    and ordered.index(first) < ordered.index(then)
                ):
                    continue
                if all(_before(first, then, sequence) for sequence in named):
                    calling = sum(1 for sequence in named if then in sequence)
                    proposed.append(
                        Proposed(
                            type="before",
                            params={"first": first, "then": then},
                            why=f"in every one of {count}, each call to the "
                            "second tool has a call to the first before it; "
                            f"{calling} of them call the second",
                        )
                    )
        for tool in declared:
            if not any(tool in sequence for sequence in named):
                proposed.append(
                    Proposed(
                        type="never",
                        params={"tool": tool},
                        why=f"declared to the model and called in none of {count}",
                    )
                )
    if episodes:
        limit, said, placeholder = _limit(
            found.model_steps, "max_steps.limit", found.runs, "most model turns"
        )
        proposed.append(
            Proposed(
                type="max_steps",
                params={"limit": int(limit), "count": "model"},
                why=f"the model's turns, in an agent's episode; {said}",
                placeholders=("limit",) if placeholder else (),
            )
        )
    return tuple(proposed)


def budget_checks(
    responses: Sequence[RecordedResponse], found: Measured
) -> tuple[Proposed, ...]:
    """`cost_budget` where every recording carries a cost, and
    `latency_budget` where every one carries a latency. The target the suite
    declares has to report them too, or the check errors on every case."""
    if not responses:
        return ()
    proposed: list[Proposed] = []
    count = _many(len(responses), "recording")
    for kind, key, value, carried in (
        (
            "cost_budget",
            "max_usd",
            found.cost_usd,
            all(r.cost_usd is not None for r in responses),
        ),
        (
            "latency_budget",
            "max_ms",
            found.latency_ms,
            all(r.latency_ms is not None for r in responses),
        ),
    ):
        if not carried:
            continue
        limit, said, placeholder = _limit(value, f"{kind}.{key}", found.runs, "highest")
        proposed.append(
            Proposed(
                type=kind,
                params={key: limit, "tolerance": PLACEHOLDER["tolerance"]},
                why=f"every one of {count} carries it, and the target has to "
                f"report it too; {said}; tolerance is a placeholder",
                placeholders=(key, "tolerance") if placeholder else ("tolerance",),
            )
        )
    return tuple(proposed)


def judged_check(name: str, found: Measured) -> Proposed:
    """The judged check a capture reviews answers for, wrapped in `repeated`
    at the starting point of the guide's chapter 3, three samples and
    `"2/3"`. The judge and the rubric are the person's to write, and the
    threshold is the lowest score the runs gave a check of that name."""
    threshold, said, placeholder = _limit(
        found.lowest.get(name),
        "llm_rubric.threshold",
        found.runs,
        "lowest score",
    )
    return Proposed(
        type="repeated",
        params={
            "samples": 3,
            "min_agreement": "2/3",
            "inner": {
                "type": "llm_rubric",
                "name": name,
                "rubric": "WRITE: one question a good answer says yes to",
                "judge": "provider/model",
                "threshold": threshold,
                "tolerance": PLACEHOLDER["tolerance"],
            },
        },
        why="the judged check the capture reviews answers for, asked three "
        f"times with two in three to agree; {said}; the rubric, the judge and "
        "the tolerance are placeholders",
        placeholders=(
            "inner.rubric",
            "inner.judge",
            "inner.tolerance",
            *(("inner.threshold",) if placeholder else ()),
        ),
    )


# What an assistant replies. (ADR 0063 §4)

#: The parameters an assistant may write a number for, and which way is
#: stricter: a ceiling down, a floor up. A tolerance stays the person's.
LIMITS: Mapping[str, str] = {
    "maximum": "ceiling",
    "limit": "ceiling",
    "max_usd": "ceiling",
    "max_ms": "ceiling",
    "inner.threshold": "floor",
}

#: The parts of a reply, and nothing else is read.
REPLY = ("rubric", "why", "limits", "counterexample")

FORM = "a part outside the reply's form"
NOT_HELD = "a check the proposal does not hold"
NOT_JUDGED = "a rubric for a check that is not judged"
NOT_TEXT = "a rubric or a sentence that is not text"
NOT_A_LIMIT = "a parameter that is not a limit of its check"
NOT_ACCEPTED = "a limit its check does not accept"
LAXER = "a limit less strict than the runs measured"
NO_COUNTEREXAMPLE = "a counterexample not of the form vars and answer"

#: A sentence of why longer than this is cut: a comment beside a check.
SAID_CHARS = 400


@dataclass(frozen=True, slots=True)
class Counterexample:
    """A case an assistant constructed: the input, and the answer the suite
    must refuse."""

    vars: Mapping[str, object]
    answer: str


@dataclass(frozen=True, slots=True)
class Merged:
    """The checks with what the assistant wrote merged in, the counterexample
    it constructed, and what was discarded, by reason."""

    checks: tuple[Proposed, ...]
    counterexample: Counterexample | None
    discarded: Mapping[str, int]
    rubrics: int = 0
    sentences: int = 0
    limits: int = 0


def handle(number: int) -> str:
    """How the reply names the `number`th check of the proposal."""
    return f"check-{number}"


def _plain(text: str) -> str:
    """One line, with no control character, as a comment can hold it."""
    return " ".join("".join(ch if ch.isprintable() else " " for ch in text).split())


def _param(check: Proposed, key: str) -> object:
    """The parameter at `key`, one level deep: `inner.threshold` is inside
    `repeated`'s inner check."""
    head, _, rest = key.partition(".")
    value = check.params.get(head)
    if not rest:
        return value
    if isinstance(value, Mapping):
        return cast(Mapping[str, object], value).get(rest)
    return None


def _with(check: Proposed, key: str, value: object) -> Proposed:
    """`check` with the parameter at `key` set, marked as the assistant's and
    no longer a placeholder."""
    params = dict(check.params)
    if key.startswith("inner."):
        inner = dict(cast(Mapping[str, object], params["inner"]))
        inner[key.removeprefix("inner.")] = value
        params["inner"] = inner
    else:
        params[key] = value
    return Proposed(
        type=check.type,
        params=params,
        why=check.why,
        placeholders=tuple(p for p in check.placeholders if p != key),
        said=check.said,
        assisted=(*check.assisted, key),
    )


def _accepted(check: Proposed, key: str, value: object) -> float | None:
    """The number as its check takes it, or `None` where the check refuses
    it: a count is whole, a threshold is in (0, 1], every other limit is
    above zero."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    number = float(value)
    if number != number or number in (float("inf"), float("-inf")):
        return None
    if key in ("maximum", "limit"):
        if number != int(number) or number < (1 if key == "limit" else 0):
            return None
        return int(number)
    if key == "inner.threshold":
        return number if 0 < number <= 1 else None
    return number if number > 0 else None


def merged(checks: Sequence[Proposed], reply: Mapping[str, object]) -> Merged:
    """What an assistant's reply may change in the proposal, changed, and the
    rest discarded and counted. The checks are named in the reply by
    `handle`, so a check the proposal does not hold has no name to be
    written under: the assistant adds none, removes none, and touches no
    `[capture]` and no case."""
    held = {handle(n): n - 1 for n in range(1, len(checks) + 1)}
    out = list(checks)
    discarded: dict[str, int] = {}
    rubrics = sentences = limits = 0

    def discard(reason: str) -> None:
        discarded[reason] = discarded.get(reason, 0) + 1

    def part(key: str) -> Mapping[str, object]:
        value = reply.get(key)
        if value is None:
            return {}
        if not isinstance(value, Mapping):
            discard(FORM)
            return {}
        return cast(Mapping[str, object], value)

    for key in reply:
        if key not in REPLY:
            discard(FORM)

    for name, text in part("rubric").items():
        index = held.get(name)
        if index is None:
            discard(NOT_HELD)
        elif not isinstance(text, str) or not text.strip():
            discard(NOT_TEXT)
        elif _param(out[index], "inner.rubric") is None:
            discard(NOT_JUDGED)
        else:
            out[index] = _with(out[index], "inner.rubric", text.strip())
            rubrics += 1

    for name, text in part("why").items():
        index = held.get(name)
        if index is None:
            discard(NOT_HELD)
        elif not isinstance(text, str) or not _plain(text):
            discard(NOT_TEXT)
        else:
            check = out[index]
            out[index] = Proposed(
                type=check.type,
                params=check.params,
                why=check.why,
                placeholders=check.placeholders,
                said=_plain(text)[:SAID_CHARS],
                assisted=check.assisted,
            )
            sentences += 1

    for name, value in part("limits").items():
        number, _, key = name.partition(".")
        index = held.get(number)
        if index is None:
            discard(NOT_HELD)
            continue
        check = out[index]
        current = _param(check, key)
        if key not in LIMITS or not isinstance(current, int | float):
            discard(NOT_A_LIMIT)
            continue
        accepted = _accepted(check, key, value)
        if accepted is None:
            discard(NOT_ACCEPTED)
            continue
        if key not in check.placeholders and (
            accepted > current if LIMITS[key] == "ceiling" else accepted < current
        ):
            discard(LAXER)
            continue
        out[index] = _with(check, key, accepted)
        limits += 1

    counterexample: Counterexample | None = None
    raw = reply.get("counterexample")
    if raw is not None:
        vars_ = (
            cast(Mapping[str, object], raw).get("vars")
            if isinstance(raw, Mapping)
            else None
        )
        answer = (
            cast(Mapping[str, object], raw).get("answer")
            if isinstance(raw, Mapping)
            else None
        )
        if (
            isinstance(vars_, Mapping)
            and vars_
            and all(isinstance(k, str) for k in cast(Mapping[object, object], vars_))
            and isinstance(answer, str)
        ):
            counterexample = Counterexample(
                vars=dict(cast(Mapping[str, object], vars_)), answer=answer
            )
        else:
            discard(NO_COUNTEREXAMPLE)

    return Merged(
        checks=tuple(out),
        counterexample=counterexample,
        discarded=discarded,
        rubrics=rubrics,
        sentences=sentences,
        limits=limits,
    )
