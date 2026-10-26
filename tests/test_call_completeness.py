"""Whether a line of the bill saw every call, and knew the cost of each (#563).

Two markers on `CallTotals`, each `True`, `False` or `None`:

- `every_call_seen`: `False` only where digline **knows** a call was made and is
  not on the line, which is a call that raised, the target's or a judge's.
  `None` where digline does not know whether there was a call at all, which is
  a judge that is not `Billable` and so keeps no count digline can read.
- `every_cost_known`: `False` where a call was seen and its cost was not, which
  is a reply with `cost_usd=None` and a reply of the wrong shape.

In a sum `False` wins over `None`, and `None` over `True`: one call missing
makes the whole line incomplete, and one line nobody recorded makes the whole
line unrecorded unless something already says it is incomplete. The sum is
tested at the three places it is taken: the per-case lines of a run, the
judges in `judge_totals`, and the legs of a resumed journal.

The 20 -> 21 step writes nothing, and absent is `None`.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar, cast

import pytest

from digline.core import (
    NO_CALLS,
    TEXT_ONLY,
    AssertionBase,
    CallTotals,
    CheckKind,
    Contains,
    Disclosure,
    EvaluatorInputs,
    JudgeReply,
    LlmRubric,
    OutputKind,
    Run,
    RunUsage,
    Verdict,
)
from digline.core.run import (
    SCHEMA_VERSION,
    run_from_dict,
    run_from_json,
    run_to_dict,
)
from digline.host import measure, prepare
from digline.run import Case, Response, Suite, execute
from digline.run.driver import judge_totals
from digline.store import FileResultStore
from digline.store.migrate import upgrade_document
from digline.targets.judge import ScoreJudge
from digline.targets.pricing import ModelPrice, Pricing, Usage
from digline.wire import run_document, usage_lines

CREATED = "2026-01-01T00:00:00+00:00"
PRICING = Pricing(
    per_model={"j-1": ModelPrice(input_per_mtok=1.0, output_per_mtok=2.0)}
)
KNOWN = CallTotals(every_call_seen=True, every_cost_known=True)


def suite(*assertions: object, cases: int = 2) -> Suite:
    return Suite(
        tenant="acme",
        environment="staging",
        name="qa",
        assertions=list(assertions) or [Contains(needle="yes", threshold=1.0)],  # pyright: ignore[reportArgumentType]
        cases=[Case(id=f"c{n}") for n in range(1, cases + 1)],
    )


class Answering:
    """A target that answers every call, priced unless told otherwise."""

    def __init__(self, *, cost_usd: float | None = 0.01) -> None:
        self.cost_usd = cost_usd
        self.config = {"provider": "fake", "model": "m-1"}

    def __call__(self, case: Case) -> Response:
        return Response(output="yes", cost_usd=self.cost_usd, usage=Usage(10, 5))


class RaisingOn:
    """A target whose call on the named cases raises."""

    def __init__(self, *case_ids: str) -> None:
        self.case_ids = set(case_ids)
        self.config = {"provider": "fake", "model": "m-1"}

    def __call__(self, case: Case) -> Response:
        if case.id in self.case_ids:
            raise RuntimeError("the endpoint went away")
        return Response(output="yes", cost_usd=0.01, usage=Usage(10, 5))


class Shapeless:
    """A target whose code returns something that is not a `Response`."""

    config = {"provider": "fake", "model": "m-1"}

    def __call__(self, case: Case) -> Response:
        return "yes"  # pyright: ignore[reportReturnType]


def plain_judge(prompt: str) -> JudgeReply:
    """A judge written as a function: it keeps no count digline can read."""
    return JudgeReply(score=1.0, reason="fine")


def rubric(judge: object) -> LlmRubric:
    return LlmRubric(
        rubric="Is it polite?",
        judge=judge,  # pyright: ignore[reportArgumentType]
        threshold=0.5,
        tolerance=0.0,
    )


class FlakyJudge(ScoreJudge):
    """A `JudgeBase` whose provider raises on the calls named, and answers on
    the rest. Subclassed rather than faked, because what is under test is the
    count `_ask` keeps."""

    provider = "fake"
    system = "unused"

    def __init__(self, *, raise_on: frozenset[int] = frozenset()) -> None:
        super().__init__(model="j-1", max_tokens=16, pricing=PRICING)
        self.raise_on = raise_on
        self.asked = 0

    def _complete(self, system: str, prompt: str) -> tuple[str, Usage]:
        self.asked += 1
        if self.asked in self.raise_on:
            raise RuntimeError("the judge's endpoint went away")
        return json.dumps({"score": 1.0, "reason": "fine"}), Usage(10, 5)


def lines(document: Mapping[str, object]) -> dict[str, dict[str, object]]:
    """The two lines of a document's bill, typed for a test that edits them."""
    return cast(dict[str, dict[str, object]], document["usage"])


def usage_of(run: Run) -> RunUsage:
    assert run.usage is not None
    return run.usage


# --------------------------------------------------------------------------- #
# The sum: False over None over True
# --------------------------------------------------------------------------- #

_LINES = {
    True: CallTotals(every_call_seen=True, every_cost_known=True),
    False: CallTotals(every_call_seen=False, every_cost_known=False),
    None: CallTotals(),
}


@pytest.mark.parametrize(
    ("left", "right", "expected"),
    [
        (True, True, True),
        (True, None, None),
        (None, True, None),
        (None, None, None),
        (False, None, False),
        (None, False, False),
        (False, True, False),
        (True, False, False),
        (False, False, False),
    ],
)
def test_a_sum_is_as_complete_as_its_least_complete_side(
    left: bool | None, right: bool | None, expected: bool | None
) -> None:
    total = _LINES[left] + _LINES[right]
    assert total.every_call_seen is expected
    assert total.every_cost_known is expected


def test_a_line_built_without_markers_is_not_recorded() -> None:
    """The default is the absence, not a claim: `CallTotals(calls=n)` is how a
    caller that kept no figures says so, and it must not read as complete."""
    line = CallTotals(calls=3)
    assert line.every_call_seen is None
    assert line.every_cost_known is None


def test_no_calls_is_complete_and_neutral_in_a_sum() -> None:
    assert CallTotals(every_call_seen=True, every_cost_known=True) == NO_CALLS
    for line in _LINES.values():
        assert NO_CALLS + line == line


def test_a_priced_call_keeps_the_cost_known_and_an_unpriced_one_does_not() -> None:
    priced = NO_CALLS.plus(tokens=Usage(1, 1), spent_usd=0.5)
    assert (priced.every_call_seen, priced.every_cost_known) == (True, True)
    unpriced = priced.plus(tokens=Usage(1, 1), spent_usd=None)
    assert (unpriced.every_call_seen, unpriced.every_cost_known) == (True, False)
    assert unpriced.spent_usd == 0.5, "an unknown cost adds nothing it does not know"
    assert unpriced.calls == 2, "the call was seen, so it is on the line"


# --------------------------------------------------------------------------- #
# Passenger 1: every_call_seen
# --------------------------------------------------------------------------- #


def test_a_target_call_that_raised_is_a_call_not_seen() -> None:
    run = execute(suite(), RaisingOn("c1"), created_at=CREATED)
    target = usage_of(run).target
    assert target.every_call_seen is False
    assert target.calls == 1, "the call that raised is still on no line"


def test_a_judged_check_whose_judge_is_not_billable_is_not_recorded() -> None:
    """digline cannot know whether a judge it cannot read made a call, so
    `False` would claim a miss that nothing established."""
    run = execute(suite(rubric(plain_judge)), Answering(), created_at=CREATED)
    judge = usage_of(run).judge
    assert judge.every_call_seen is None
    assert judge.every_cost_known is None
    assert usage_of(run).target.every_call_seen is True


def test_a_billable_judge_call_that_raised_is_a_call_not_seen() -> None:
    judge = FlakyJudge(raise_on=frozenset({1}))
    run = execute(suite(rubric(judge)), Answering(), created_at=CREATED)
    line = usage_of(run).judge
    assert line.every_call_seen is False
    assert line.calls == 1, "the raised call stays off the count"
    assert judge.raised_calls == 1


def test_a_billable_judge_that_answered_every_call_saw_them_all() -> None:
    run = execute(suite(rubric(FlakyJudge())), Answering(), created_at=CREATED)
    line = usage_of(run).judge
    assert (line.every_call_seen, line.every_cost_known) == (True, True)
    assert line.calls == 2


def test_a_run_with_no_judge_saw_every_judge_call() -> None:
    """Zero calls, and none missing: a measurement, not an absence."""
    run = execute(suite(), Answering(), created_at=CREATED)
    assert usage_of(run).judge == NO_CALLS
    assert usage_of(run).target.every_call_seen is True


def test_a_raised_judge_call_before_this_run_is_not_this_runs_miss() -> None:
    """A judge reused across runs: its count of raised calls is monotone, so
    this run cannot tell its own misses from the earlier run's, and says it
    does not know rather than repeating the earlier one's `False`."""
    judge = FlakyJudge(raise_on=frozenset({1}))
    declared = suite(rubric(judge))
    first = execute(declared, Answering(), created_at=CREATED)
    assert usage_of(first).judge.every_call_seen is False
    second = execute(declared, Answering(), created_at=CREATED)
    assert usage_of(second).judge.every_call_seen is None


# --------------------------------------------------------------------------- #
# Passenger 2: every_cost_known
# --------------------------------------------------------------------------- #


def test_a_reply_with_no_cost_leaves_the_cost_unknown() -> None:
    run = execute(suite(), Answering(cost_usd=None), created_at=CREATED)
    target = usage_of(run).target
    assert target.every_cost_known is False
    assert target.every_call_seen is True
    assert target.spent_usd == 0.0


def test_a_reply_of_the_wrong_shape_was_seen_and_not_priced() -> None:
    run = execute(suite(cases=1), Shapeless(), created_at=CREATED)
    target = usage_of(run).target
    assert (target.every_call_seen, target.every_cost_known) == (True, False)
    assert target.calls == 1


def test_calls_seen_and_priced_are_complete_on_both_markers() -> None:
    run = execute(suite(), Answering(), created_at=CREATED)
    target = usage_of(run).target
    assert (target.every_call_seen, target.every_cost_known) == (True, True)


# --------------------------------------------------------------------------- #
# The three places the sum is taken
# --------------------------------------------------------------------------- #


def test_the_per_case_lines_sum_false_over_unknown_cost() -> None:
    """Case c1 raised and the others answered unpriced: the run's line is
    incomplete on calls and on cost, each marker on its own."""

    class Mixed:
        config = {"provider": "fake", "model": "m-1"}

        def __call__(self, case: Case) -> Response:
            if case.id == "c1":
                raise RuntimeError("no")
            return Response(output="yes", cost_usd=None, usage=Usage(10, 5))

    run = execute(suite(cases=3), Mixed(), created_at=CREATED)
    target = usage_of(run).target
    assert (target.every_call_seen, target.every_cost_known) == (False, False)


def test_judge_totals_sums_false_over_none_over_true() -> None:
    """Three judges: one billable that missed a call, one billable that saw
    every call, one that is not billable. The miss wins; without it the
    unreadable one does."""
    missed = FlakyJudge(raise_on=frozenset({1}))
    with pytest.raises(RuntimeError):
        missed._ask("x")  # pyright: ignore[reportPrivateUsage]
    clean = FlakyJudge()
    every = judge_totals(suite(rubric(missed), rubric(clean), rubric(plain_judge)))
    assert every.every_call_seen is False
    without_miss = judge_totals(suite(rubric(clean), rubric(plain_judge)))
    assert without_miss.every_call_seen is None
    only_clean = judge_totals(suite(rubric(clean)))
    assert only_clean.every_call_seen is True


@dataclass(frozen=True)
class HoldsHandWritten(AssertionBase):
    """A judged check holding a `Billable` judge that keeps no count of the
    calls that raised, which is any judge not built on `JudgeBase`."""

    judge: object
    name: str = "holds"
    threshold: float = 1.0
    tolerance: float = 0.0
    accepts: frozenset[OutputKind] = TEXT_ONLY
    KIND: ClassVar[CheckKind] = "judged"

    def __call__(self, inputs: EvaluatorInputs) -> Verdict:
        return self._binary(True, "held")


class HandWritten:
    def __init__(self) -> None:
        self.calls = 0
        self.spent_usd = 0.0
        self.tokens = Usage(0, 0)
        self.config = {"provider": "fake", "model": "j-1"}


def test_a_billable_judge_that_counts_no_raised_call_is_not_recorded() -> None:
    every = judge_totals(suite(HoldsHandWritten(judge=HandWritten())))
    assert every.every_call_seen is None


class DyingAfter:
    """Raises on c1, answers c2, and kills the process on c3."""

    def __init__(self) -> None:
        self.config = {"provider": "fake", "model": "m-1"}

    def __call__(self, case: Case) -> Response:
        if case.id == "c1":
            raise RuntimeError("no")
        if case.id == "c3":
            raise SystemExit(9)
        return Response(output="yes", cost_usd=0.01, usage=Usage(10, 5))


def _killed(root: Path, target: object, declared: Suite) -> FileResultStore:
    store = FileResultStore(root)
    prepared = prepare(
        declared,
        target,  # pyright: ignore[reportArgumentType]
        now=CREATED,
        git_commit="deadbeef",
        artifacts={},
    )
    with pytest.raises(SystemExit):
        measure(declared, target, store=store, prepared=prepared)  # pyright: ignore[reportArgumentType]
    return store


def _strip_markers(root: Path, case_id: str) -> None:
    """Rewrite the journal as a digline before 21 wrote it, for one case: its
    usage line carries no marker."""
    (journal,) = [p for p in root.rglob("*.jsonl")]
    rewritten: list[str] = []
    for line in journal.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        if record.get("kind") == "case" and record["case"]["case_id"] == case_id:
            record["usage"].pop("every_call_seen")
            record["usage"].pop("every_cost_known")
        rewritten.append(json.dumps(record))
    journal.write_text("\n".join(rewritten) + "\n", encoding="utf-8")


def test_a_journal_sums_its_legs_false_over_none(tmp_path: Path) -> None:
    store = _killed(tmp_path, DyingAfter(), suite(cases=4))
    (pending,) = store.pending("acme", "qa")
    assert pending.spent.every_call_seen is False, "c1 raised"
    _strip_markers(tmp_path, "c2")
    (pending,) = store.pending("acme", "qa")
    assert pending.spent.every_call_seen is False, "False wins over the absent"


def test_a_journal_line_before_21_makes_the_legs_not_recorded(
    tmp_path: Path,
) -> None:
    store = _killed(tmp_path, DyingAfter(), suite(cases=4))
    (pending,) = store.pending("acme", "qa")
    assert pending.spent.every_cost_known is True
    _strip_markers(tmp_path, "c2")
    (pending,) = store.pending("acme", "qa")
    assert pending.spent.every_cost_known is None, "None wins over True"


# --------------------------------------------------------------------------- #
# The document, the wire and the terminal
# --------------------------------------------------------------------------- #


def test_the_markers_round_trip_and_absent_is_not_recorded() -> None:
    run = execute(suite(), RaisingOn("c1"), created_at=CREATED)
    raw = run_to_dict(run)
    target = lines(raw)["target"]
    assert target["every_call_seen"] is False
    assert target["every_cost_known"] is True
    assert run_from_dict(raw).usage == run.usage

    for line in lines(raw).values():
        line.pop("every_call_seen")
        line.pop("every_cost_known")
    read = run_from_dict(raw).usage
    assert read is not None
    assert read.target.every_call_seen is None
    assert read.judge.every_cost_known is None


def test_a_marker_not_recorded_is_written_absent_never_null() -> None:
    run = execute(suite(rubric(plain_judge)), Answering(), created_at=CREATED)
    judge = lines(run_to_dict(run))["judge"]
    assert "every_call_seen" not in judge
    assert "every_cost_known" not in judge


def test_an_explicit_null_marker_is_refused() -> None:
    raw = run_to_dict(execute(suite(), Answering(), created_at=CREATED))
    lines(raw)["target"]["every_call_seen"] = None
    with pytest.raises(ValueError, match="every_call_seen"):
        run_from_dict(raw)


def test_the_wire_carries_both_markers_on_each_line() -> None:
    run = execute(suite(rubric(plain_judge)), RaisingOn("c1"), created_at=CREATED)
    usage = lines(run_document(run, Disclosure()))
    assert usage["target"]["every_call_seen"] is False
    assert usage["target"]["every_cost_known"] is True
    assert usage["judge"]["every_call_seen"] is None
    assert usage["judge"]["every_cost_known"] is None


def test_the_terminal_says_a_call_was_not_seen() -> None:
    run = execute(suite(), RaisingOn("c1"), created_at=CREATED)
    (line,) = usage_lines(run.usage)
    assert "not every call seen" in line
    assert "cost not known for every call" not in line


def test_the_terminal_says_a_cost_was_not_known() -> None:
    run = execute(suite(), Answering(cost_usd=None), created_at=CREATED)
    (line,) = usage_lines(run.usage)
    assert "cost not known for every call" in line
    assert "not every call seen" not in line


def test_the_terminal_says_nothing_of_a_complete_line() -> None:
    run = execute(suite(), Answering(), created_at=CREATED)
    (line,) = usage_lines(run.usage)
    assert "not every call seen" not in line
    assert "cost not known" not in line


def test_the_terminal_says_a_judge_it_cannot_read_is_not_recorded() -> None:
    """#569, the judge's half. A judge written as a function made its calls,
    and none of them is on the line: the line is *not recorded*, and saying
    nothing, or `0.000000 USD`, would read as a judge that cost nothing."""
    run = execute(suite(rubric(plain_judge)), Answering(), created_at=CREATED)
    assert usage_of(run).judge.every_call_seen is None
    target_line, judge_line = usage_lines(run.usage)
    assert target_line.startswith("target:")
    assert judge_line == "judge: not recorded"


def test_a_judge_that_spends_still_prints_its_cost() -> None:
    """The control: a `Billable` judge whose every call was seen keeps its
    bill, and is not called unrecorded."""
    run = execute(suite(rubric(FlakyJudge())), Answering(), created_at=CREATED)
    spent = usage_of(run).judge.spent_usd
    assert spent > 0
    _, judge_line = usage_lines(run.usage)
    assert f"{spent:.6f} USD" in judge_line
    assert "not recorded" not in judge_line


def test_a_bill_with_an_unread_judge_beside_it_says_it_is_not_whole() -> None:
    """A readable judge beside one written as a function: the figure is what
    the readable one spent, and the line says that it is not the whole."""
    run = execute(
        suite(rubric(FlakyJudge()), rubric(plain_judge)),
        Answering(),
        created_at=CREATED,
    )
    _, judge_line = usage_lines(run.usage)
    assert "USD" in judge_line
    assert judge_line.endswith("; not recorded in full")


# --------------------------------------------------------------------------- #
# Schema 21, and the step that writes nothing
# --------------------------------------------------------------------------- #


def test_migrating_a_schema_20_line_writes_no_marker() -> None:
    assert SCHEMA_VERSION == 21
    current = run_to_dict(execute(suite(), Answering(), created_at=CREATED))
    for line in lines(current).values():
        line.pop("every_call_seen")
        line.pop("every_cost_known")
    upgraded = upgrade_document({**current, "schema_version": 20})
    assert upgraded == current
    usage = run_from_json(json.dumps(upgraded)).usage
    assert usage is not None
    assert usage.target.every_call_seen is None
    assert usage.target.every_cost_known is None


def test_the_terminal_says_it_when_every_call_raised() -> None:
    """Nothing is on the line, and that is when the clause matters most."""
    run = execute(suite(), RaisingOn("c1", "c2"), created_at=CREATED)
    (line,) = usage_lines(run.usage)
    assert line.startswith("target: 0 calls")
    assert "not every call seen" in line
