"""The output tokens nobody reads, told apart from the ones they do.

ADR 0026's test plan. Most of what is asserted here is a **distinction** rather
than a value: `None`, `0` and `n` are three different sentences, and every
defect this field can have is one of them collapsing into another. A fold that
read an unreported split as zero, a codec that dropped a measured zero as a
default, and a migration that wrote `0` over a document that never said —
each is the same mistake, and each would look like a smaller number that
nobody would question.

The plugin halves live with their plugins: `digline-anthropic` and
`digline-openai` each read their own provider's field, and bedrock records
nothing and has a test saying so.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, cast

import pytest

from digline.core import (
    NO_USAGE,
    TEXT_ONLY,
    AssertionBase,
    CallTotals,
    CheckKind,
    Contains,
    Disclosure,
    EvaluatorInputs,
    OutputKind,
    RecordedResponse,
    Usage,
    Verdict,
    redact,
    without_responses,
)
from digline.core.run import (
    SCHEMA_VERSION,
    run_from_dict,
    run_to_dict,
    usage_from_dict,
    usage_to_dict,
)
from digline.run import Case, Response, Suite, execute
from digline.store.migrate import upgrade_document
from digline.wire import run_document

CREATED = "2026-01-01T00:00:00+00:00"


def suite(*, cases: int = 2, **extra: object) -> Suite:
    return Suite(
        tenant="acme",
        environment="staging",
        name="qa",
        assertions=[Contains(needle="yes", threshold=1.0)],
        cases=[Case(id=f"c{n}") for n in range(1, cases + 1)],
        **extra,  # pyright: ignore[reportArgumentType]
    )


class Thinking:
    """A target whose provider reports the split — or does not report it.

    `split=None` is the provider that says nothing, which is a different target
    from one that says zero, and the difference is what most of this file is
    about.
    """

    def __init__(self, *, split: int | None = 3) -> None:
        self.config = {"provider": "fake", "model": "m-1"}
        self.split = split

    def __call__(self, case: Case) -> Response:
        return Response(
            output="yes",
            cost_usd=0.01,
            usage=Usage(input_tokens=10, output_tokens=5, thinking_tokens=self.split),
        )


# --------------------------------------------------------------------------- #
# Three states, and they stay three
# --------------------------------------------------------------------------- #


def test_the_three_states_are_three() -> None:
    """`None`, `0` and `n` compare unequal. Stated first because every other
    test here is a way of losing one of them."""
    unreported = Usage(10, 5)
    measured_zero = Usage(10, 5, thinking_tokens=0)
    counted = Usage(10, 5, thinking_tokens=3)
    assert unreported.thinking_tokens is None
    assert unreported != measured_zero != counted
    assert measured_zero != counted


def test_a_reported_zero_is_written_and_read_back_as_a_zero() -> None:
    """The default-dropping bug, as a round trip: a `0` a provider gave is a
    measurement. Written, it is a key; read, it is still not `None`."""
    payload = usage_to_dict(Usage(10, 5, thinking_tokens=0))
    assert payload["thinking_tokens"] == 0
    assert usage_from_dict(payload, "where").thinking_tokens == 0


def test_an_unreported_split_leaves_the_key_out_rather_than_writing_zero() -> None:
    payload = usage_to_dict(Usage(10, 5))
    assert "thinking_tokens" not in payload
    assert usage_from_dict(payload, "where").thinking_tokens is None


def test_a_null_split_is_refused_rather_than_read_as_absence() -> None:
    """Absence already says *not reported*, so a null is a malformed document
    and not a second spelling of it — the rule `usage` itself follows."""
    with pytest.raises(ValueError, match="'thinking_tokens' is null"):
        usage_from_dict(
            {"input_tokens": 1, "output_tokens": 1, "thinking_tokens": None}, "where"
        )


def test_a_negative_split_is_refused() -> None:
    with pytest.raises(ValueError, match="thinking_tokens must not be negative"):
        Usage(10, 5, thinking_tokens=-1)


# --------------------------------------------------------------------------- #
# The invariant refuses rather than clamps
# --------------------------------------------------------------------------- #


def test_more_thinking_than_output_is_refused_by_name() -> None:
    """Refused, not clamped: the two failures a clamp hides — a provider whose
    accounting drifted and a plugin reading the wrong field into the right one
    — are both things somebody has to be told (ADR 0026 §3)."""
    with pytest.raises(ValueError) as raised:
        Usage(input_tokens=1, output_tokens=2, thinking_tokens=3)
    message = str(raised.value)
    assert "3" in message and "2" in message
    assert "more thinking than" in message


def test_the_refusal_is_not_a_repair() -> None:
    """The same malformed reply, asserted to produce **no** object: a clamped
    `thinking_tokens == output_tokens` would pass every other test in this
    file."""
    with pytest.raises(ValueError):
        Usage(input_tokens=1, output_tokens=2, thinking_tokens=3)
    # The boundary itself is legal — all of the output was thinking.
    assert Usage(1, 2, thinking_tokens=2).thinking_tokens == 2


def test_a_fold_of_legal_parts_cannot_break_the_invariant() -> None:
    """Stated as a property rather than a refusal, because it is one: both
    sides are bounded by their own output, so the sums are bounded too. The
    total is revalidated all the same — `+` builds a new `Usage` — and this
    asserts that the revalidation has nothing to catch here, which is why the
    refusal above is about a single malformed reply and not about arithmetic.
    """
    total = Usage(1, 2, thinking_tokens=2) + Usage(1, 5, thinking_tokens=4)
    assert (total.output_tokens, total.thinking_tokens) == (7, 6)


# --------------------------------------------------------------------------- #
# The fold keeps the state
# --------------------------------------------------------------------------- #


def test_two_reported_sides_add() -> None:
    total = Usage(10, 5, thinking_tokens=2) + Usage(10, 5, thinking_tokens=3)
    assert total.thinking_tokens == 5


@pytest.mark.parametrize(
    ("left", "right"),
    [(2, None), (None, 2), (None, None), (0, None)],
    ids=["known+unknown", "unknown+known", "neither", "zero+unknown"],
)
def test_any_unreported_side_makes_the_total_unreported(
    left: int | None, right: int | None
) -> None:
    """Both directions, because a fold that treated `None` as `0` would look
    identical from the total alone — and it would report **less** than the
    truth, which is the good-news direction this project has twice paid to stop
    reporting in (ADR 0026 §3)."""
    total = Usage(10, 5, thinking_tokens=left) + Usage(10, 5, thinking_tokens=right)
    assert total.thinking_tokens is None


def test_a_run_of_mixed_calls_reports_an_unknown_total() -> None:
    """The reachable shape of the rule: one target reports the split and the
    next call does not. The run's line says *not reported* rather than the
    smaller number it could have printed."""

    class Sometimes:
        config = {"provider": "fake", "model": "m-1"}

        def __init__(self) -> None:
            self.calls = 0

        def __call__(self, case: Case) -> Response:
            self.calls += 1
            split = 3 if self.calls == 1 else None
            return Response(
                output="yes",
                cost_usd=0.01,
                usage=Usage(10, 5, thinking_tokens=split),
            )

    run = execute(suite(), Sometimes(), created_at=CREATED)
    assert run.usage is not None
    assert run.usage.target.counted == 2
    assert run.usage.target.tokens.thinking_tokens is None


def test_a_run_whose_calls_all_report_carries_the_sum() -> None:
    run = execute(suite(), Thinking(split=3), created_at=CREATED)
    assert run.usage is not None
    assert run.usage.target.tokens == Usage(20, 10, thinking_tokens=6)


# --------------------------------------------------------------------------- #
# The migration invents nothing
# --------------------------------------------------------------------------- #


def test_the_step_to_fifteen_writes_nothing() -> None:
    run = execute(suite(record_responses=True), Thinking(), created_at=CREATED)
    current = run_to_dict(run)
    assert SCHEMA_VERSION == 15
    assert upgrade_document({**current, "schema_version": 14}) == current


def test_a_migrated_document_reports_no_split_anywhere() -> None:
    """A schema-14 document is one written before the field existed, so every
    place it could appear says *not reported* — not `0`, which would state that
    a reasoning model did none."""
    run = execute(
        suite(record_responses=True), Thinking(split=None), created_at=CREATED
    )
    at_fourteen = {**run_to_dict(run), "schema_version": 14}
    migrated = run_from_dict(upgrade_document(at_fourteen))
    assert migrated.usage is not None
    assert migrated.usage.target.tokens.thinking_tokens is None
    assert migrated.usage.judge.tokens.thinking_tokens is None
    assert all(
        response.usage is not None and response.usage.thinking_tokens is None
        for case in migrated.results
        for response in case.responses
    )


def test_a_migrated_absence_and_a_fresh_one_are_indistinguishable() -> None:
    """Both mean *not reported*, so a reader cannot be asked to tell them
    apart — and nothing in the document lets it."""
    fresh = execute(
        suite(record_responses=True), Thinking(split=None), created_at=CREATED
    )
    at_fourteen = {**run_to_dict(fresh), "schema_version": 14}
    migrated = run_from_dict(upgrade_document(at_fourteen))
    assert run_to_dict(migrated) == run_to_dict(fresh)


# --------------------------------------------------------------------------- #
# The boundary, both halves
# --------------------------------------------------------------------------- #


def test_redaction_keeps_the_total_and_drops_the_per_call_split() -> None:
    run = execute(suite(record_responses=True), Thinking(), created_at=CREATED)
    hidden = redact(run)
    assert hidden.usage is not None
    assert hidden.usage.target.tokens.thinking_tokens == 6
    assert all(r.usage is None for case in hidden.results for r in case.responses)


def test_promotion_keeps_the_total_and_strips_the_per_call_split() -> None:
    run = execute(suite(record_responses=True), Thinking(), created_at=CREATED)
    promoted = without_responses(run)
    assert promoted.usage is not None
    assert promoted.usage.target.tokens.thinking_tokens == 6
    assert all(not case.responses for case in promoted.results)


def test_the_wire_carries_the_total_split_and_no_per_call_one() -> None:
    run = execute(suite(record_responses=True), Thinking(), created_at=CREATED)
    document = run_document(run, Disclosure())
    usage = cast("dict[str, dict[str, object]]", document["usage"])
    assert usage["target"]["thinking_tokens"] == 6
    # By key, not by eye: the recorded responses are absent from this
    # projection altogether, so their splits cannot be in it under any name.
    cases = cast("list[dict[str, object]]", document["results"])
    assert cases and all("responses" not in case for case in cases)


def test_the_wire_reports_an_unknown_total_as_null_and_not_as_zero() -> None:
    """On the wire the absence has to be spelled, because a reader of JSON
    cannot tell a missing key from one it did not look for. `null` there is
    *not reported*; a `0` would be a measurement nobody made."""
    run = execute(suite(), Thinking(split=None), created_at=CREATED)
    document = run_document(run, Disclosure())
    usage = cast("dict[str, dict[str, object]]", document["usage"])
    assert usage["target"]["thinking_tokens"] is None
    assert "thinking_tokens" in usage["target"]


def test_a_withheld_response_may_not_carry_a_split_either() -> None:
    with pytest.raises(ValueError, match="withheld"):
        RecordedResponse(withheld=True, usage=Usage(1, 1, thinking_tokens=1))


# --------------------------------------------------------------------------- #
# What the field does not do
# --------------------------------------------------------------------------- #


def test_the_split_is_not_priced_a_second_time() -> None:
    """§2's whole point, as a number: the same run with and without a reported
    split costs the same. Thinking tokens are output tokens and are already in
    the total; adding them would bill every reasoning call twice, and the error
    would be in the direction that looks like diligence."""
    with_split = execute(suite(), Thinking(split=3), created_at=CREATED)
    without_split = execute(suite(), Thinking(split=None), created_at=CREATED)
    assert with_split.usage is not None and without_split.usage is not None
    assert with_split.usage.target.spent_usd == without_split.usage.target.spent_usd


def test_the_split_does_not_enter_the_hash() -> None:
    declared = suite()
    thought = execute(declared, Thinking(split=3), created_at=CREATED)
    quiet = execute(declared, Thinking(split=None), created_at=CREATED)
    assert thought.usage != quiet.usage
    assert thought.config_hash == quiet.config_hash == declared.config_hash()


def test_a_line_that_counted_nothing_reports_no_split() -> None:
    """`CallTotals()` is the empty line, and its `Usage` is the unreported
    one — not a zero that would read as *no thinking happened*."""
    assert CallTotals().tokens.thinking_tokens is None


# --------------------------------------------------------------------------- #
# The judge's line carries it too
# --------------------------------------------------------------------------- #


class ThinkingJudge:
    """The smallest `Billable` that reports a split.

    It accumulates the way `JudgeBase._ask` does — the first reply **replaces**
    the seed rather than folding into it — because `NO_USAGE` is not an
    unreported measurement and a fold against it would unreport every judge's
    split in the run (ADR 0026 §3).
    """

    def __init__(self, *, split: int | None = 2) -> None:
        self.calls = 0
        self.spent_usd = 0.0
        self.tokens = NO_USAGE
        self.split = split
        self.config = {"provider": "fake", "model": "j-1", "max_tokens": 10}

    def spend(self) -> None:
        self.calls += 1
        self.spent_usd += 0.5
        reply = Usage(input_tokens=100, output_tokens=4, thinking_tokens=self.split)
        self.tokens = reply if self.calls == 1 else self.tokens + reply


class Spending:
    """A target that makes its judge spend, so a run has a judge line at all."""

    def __init__(self, judge: ThinkingJudge) -> None:
        self.judge = judge
        self.config = {"provider": "fake", "model": "m-1"}

    def __call__(self, case: Case) -> Response:
        self.judge.spend()
        return Response(output="yes", cost_usd=0.01, usage=Usage(10, 5))


@dataclass(frozen=True)
class Asks(AssertionBase):
    judge: ThinkingJudge
    name: str = "asks"
    threshold: float = 1.0
    tolerance: float = 0.0
    accepts: frozenset[OutputKind] = TEXT_ONLY
    KIND: ClassVar[CheckKind] = "judged"

    def __call__(self, inputs: EvaluatorInputs) -> Verdict:
        return self._binary(True, "asked")


def judged_suite(judge: ThinkingJudge) -> Suite:
    return Suite(
        tenant="acme",
        environment="staging",
        name="qa",
        assertions=[Asks(judge=judge)],
        cases=[Case(id=f"c{n}") for n in range(1, 3)],
    )


def test_the_judges_split_reaches_the_judge_line() -> None:
    """Through `judge_totals` and the subtraction that makes it this run's
    share — two folds, each of which would have unreported the split if the
    empty line were treated as an unreported one."""
    judge = ThinkingJudge(split=2)
    run = execute(judged_suite(judge), Spending(judge), created_at=CREATED)
    assert run.usage is not None
    assert run.usage.judge.tokens.thinking_tokens == 4


def test_a_second_run_gets_its_own_share_of_the_split() -> None:
    """The subtraction's own failing case, on the field that can be `None`: a
    judge reused across two runs must not report the first run's thinking on
    the second's document."""
    judge = ThinkingJudge(split=2)
    declared = judged_suite(judge)
    first = execute(declared, Spending(judge), created_at=CREATED)
    second = execute(declared, Spending(judge), created_at=CREATED)
    assert first.usage is not None and second.usage is not None
    assert first.usage.judge.tokens.thinking_tokens == 4
    assert second.usage.judge.tokens.thinking_tokens == 4


def test_a_judge_that_reports_no_split_leaves_the_line_unreported() -> None:
    judge = ThinkingJudge(split=None)
    run = execute(judged_suite(judge), Spending(judge), created_at=CREATED)
    assert run.usage is not None
    assert run.usage.judge.tokens.thinking_tokens is None
    # And the target's own split is untouched by the judge's silence: the two
    # lines are two bills (ADR 0025 §2), so one saying nothing cannot unreport
    # the other.
    assert run.usage.target.tokens.thinking_tokens is None


def test_a_suite_with_no_judge_has_an_empty_line_and_not_a_zero_split() -> None:
    run = execute(suite(), Thinking(split=3), created_at=CREATED)
    assert run.usage is not None
    assert run.usage.judge == CallTotals()
    assert run.usage.judge.tokens.thinking_tokens is None
    assert run.usage.target.tokens.thinking_tokens == 6
