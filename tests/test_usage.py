"""What a run consumed: the two lines, the two grains, and the two refusals.

ADR 0025's test plan. The failing case for every rule here is the same shape as
the defect the record was written about — a number that reads as good news
because nobody counted what it was made of — so most of these assert what is
*absent* or *partial* rather than what is present.

The old-reader halves live where their neighbours already do:
`test_nameless_tool_call.py` holds the schema refusal and the journal's inner
one, and `test_sample_means.py` holds a 0.14.1 resume meeting both journal
formats. What is here is this reader's own direction.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar, cast

import pytest
from tests._helpers import stamp_journal_format

from digline.core import (
    NO_USAGE,
    TEXT_ONLY,
    AssertionBase,
    CallTotals,
    CaseResult,
    CheckKind,
    Contains,
    Disclosure,
    EvaluatorInputs,
    OutputKind,
    RecordedResponse,
    Run,
    RunUsage,
    Usage,
    Verdict,
    redact,
    without_responses,
)
from digline.core.run import (
    SCHEMA_VERSION,
    run_from_json,
    run_to_dict,
    run_to_json,
)
from digline.host import measure, prepare
from digline.run import Case, Response, Suite, execute
from digline.store import FileResultStore, journal_key
from digline.store.migrate import upgrade_document
from digline.wire import run_document, usage_lines

CREATED = "2026-01-01T00:00:00+00:00"


def suite(*, cases: int = 3, **extra: object) -> Suite:
    return Suite(
        tenant="acme",
        environment="staging",
        name="qa",
        assertions=[Contains(needle="yes", threshold=1.0)],
        cases=[Case(id=f"c{n}") for n in range(1, cases + 1)],
        **extra,  # pyright: ignore[reportArgumentType]
    )


class Counting:
    """A target that answers and reports what it consumed — or does not.

    `quiet_after` is the whole point of `counted`: a target may report counts
    for some calls and none for others, which is what an aggregator behind one
    endpoint does.
    """

    def __init__(self, *, quiet_after: int | None = None) -> None:
        self.calls = 0
        self.quiet_after = quiet_after
        self.config = {"provider": "fake", "model": "m-1"}

    def __call__(self, case: Case) -> Response:
        self.calls += 1
        quiet = self.quiet_after is not None and self.calls > self.quiet_after
        return Response(
            output="yes",
            cost_usd=0.01,
            usage=None if quiet else Usage(input_tokens=10, output_tokens=5),
        )


# --------------------------------------------------------------------------- #
# The totals
# --------------------------------------------------------------------------- #


def test_a_run_states_its_own_bill() -> None:
    run = execute(suite(), Counting(), created_at=CREATED)
    assert run.usage is not None
    assert run.usage.target == CallTotals(
        calls=3, counted=3, tokens=Usage(30, 15), spent_usd=0.03
    )
    # No judge was asked, and a zero is what that is — not an absence.
    assert run.usage.judge == CallTotals()


def test_counted_says_how_much_of_the_bill_was_counted() -> None:
    """A target that reports counts on one call of three. The money is known
    for all three; the counts are not, and the line says so rather than summing
    the silent ones as zeros."""
    run = execute(suite(), Counting(quiet_after=1), created_at=CREATED)
    assert run.usage is not None
    line = run.usage.target
    assert (line.calls, line.counted) == (3, 1)
    assert line.tokens == Usage(10, 5)
    assert line.spent_usd == pytest.approx(0.03)
    assert line.partial


def test_a_line_that_counted_everything_is_not_partial() -> None:
    run = execute(suite(), Counting(), created_at=CREATED)
    assert run.usage is not None
    assert not run.usage.target.partial


def test_a_call_that_raised_is_on_no_line() -> None:
    """`JudgeBase._ask`'s rule, applied to the target: an unknown cost counted
    at zero is the undercount that reads as good news."""

    class Raising:
        config = {"provider": "fake", "model": "m-1"}

        def __call__(self, case: Case) -> Response:
            raise RuntimeError("no")

    run = execute(suite(cases=1), Raising(), created_at=CREATED)
    assert run.usage is not None
    assert run.usage.target == CallTotals()
    assert [v.status for v in run.results[0].verdicts] == ["error"]


def test_the_totals_do_not_enter_the_hash() -> None:
    """ADR 0014 §1's first condition, as a test rather than an intention: what a
    run consumed cannot change what the suite was asked to do."""
    declared = suite()
    cheap = execute(declared, Counting(), created_at=CREATED)
    dear = execute(declared, Counting(quiet_after=0), created_at=CREATED)
    assert cheap.usage != dear.usage
    assert cheap.config_hash == dear.config_hash == declared.config_hash()


# --------------------------------------------------------------------------- #
# The detail
# --------------------------------------------------------------------------- #


def test_the_detail_rides_the_recorded_answer() -> None:
    run = execute(suite(record_responses=True), Counting(), created_at=CREATED)
    assert [r.responses[0].usage for r in run.results] == [Usage(10, 5)] * 3


def test_without_recording_there_is_no_detail_and_still_a_bill() -> None:
    """The ordinary run, and the reason the totals are not conditional on
    recording: it is the configuration least free to keep the answers."""
    run = execute(suite(), Counting(), created_at=CREATED)
    assert all(not r.responses for r in run.results)
    assert run.usage is not None and run.usage.target.counted == 3


def test_a_target_that_reports_nothing_records_no_detail_and_no_zero() -> None:
    run = execute(
        suite(cases=1, record_responses=True),
        Counting(quiet_after=0),
        created_at=CREATED,
    )
    assert run.results[0].responses[0].usage is None


# --------------------------------------------------------------------------- #
# The boundary, both halves
# --------------------------------------------------------------------------- #


def test_redaction_keeps_the_bill_and_drops_the_detail() -> None:
    run = execute(suite(record_responses=True), Counting(), created_at=CREATED)
    hidden = redact(run)
    assert hidden.usage == run.usage
    assert all(r.usage is None for case in hidden.results for r in case.responses)


def test_promotion_keeps_the_bill_and_strips_the_detail() -> None:
    run = execute(suite(record_responses=True), Counting(), created_at=CREATED)
    promoted = without_responses(run)
    assert promoted.usage == run.usage
    assert all(not case.responses for case in promoted.results)


def test_the_wire_carries_the_totals_and_never_a_per_call_count() -> None:
    run = execute(suite(record_responses=True), Counting(), created_at=CREATED)
    document = run_document(run, Disclosure())
    usage = cast("dict[str, dict[str, object]]", document["usage"])
    assert usage["target"]["calls"] == 3
    # By key, not by eye: every recorded response is gone from this projection,
    # so its counts cannot be in it under any name.
    cases = cast("list[dict[str, object]]", document["results"])
    assert cases and all("responses" not in case for case in cases)


def test_a_withheld_response_may_not_carry_what_it_consumed() -> None:
    """The flag announces a guarantee, so it is checked against the contents —
    the rule `RecordedResponse` already applies to the cost and the latency."""
    with pytest.raises(ValueError, match="withheld"):
        RecordedResponse(withheld=True, usage=Usage(1, 1))


# --------------------------------------------------------------------------- #
# The judge's line
# --------------------------------------------------------------------------- #


class OneJudge:
    """The smallest thing `Billable` accepts, so the driver's reading is tested
    without a provider SDK in the room."""

    def __init__(self) -> None:
        self.calls = 0
        self.spent_usd = 0.0
        self.tokens = NO_USAGE
        self.config = {"provider": "fake", "model": "j-1", "max_tokens": 10}

    def spend(self, calls: int = 1) -> None:
        self.calls += calls
        self.spent_usd += 0.5 * calls
        self.tokens = self.tokens + Usage(input_tokens=100 * calls, output_tokens=calls)


class Spending:
    """A target that makes its judge spend, so a run has a judge line at all."""

    def __init__(self, judge: OneJudge) -> None:
        self.judge = judge
        self.config = {"provider": "fake", "model": "m-1"}

    def __call__(self, case: Case) -> Response:
        self.judge.spend()
        return Response(output="yes", cost_usd=0.01, usage=Usage(10, 5))


@dataclass(frozen=True)
class Asks(AssertionBase):
    """A check that holds a judge, as a dataclass field.

    `judges()` walks dataclass *fields* rather than an attribute called
    `judge`, deliberately — so a fixture that bolted one on with `setattr`
    would be found by nothing and this file would assert a judge line that no
    real suite produces.
    """

    judge: OneJudge
    name: str = "asks"
    threshold: float = 1.0
    tolerance: float = 0.0
    accepts: frozenset[OutputKind] = TEXT_ONLY
    KIND: ClassVar[CheckKind] = "judged"

    def __call__(self, inputs: EvaluatorInputs) -> Verdict:
        return self._binary(True, "asked")


def judged_suite(judge: OneJudge, *, cases: int = 2) -> Suite:
    return Suite(
        tenant="acme",
        environment="staging",
        name="qa",
        assertions=[Asks(judge=judge)],
        cases=[Case(id=f"c{n}") for n in range(1, cases + 1)],
    )


def test_the_judge_line_is_a_difference_and_not_a_reading() -> None:
    """The failing case a single reading of a monotone counter would pass: one
    judge object, two runs, and the second must not carry the first's calls."""
    judge = OneJudge()
    declared = judged_suite(judge)
    first = execute(declared, Spending(judge), created_at=CREATED)
    second = execute(declared, Spending(judge), created_at=CREATED)

    assert first.usage is not None and second.usage is not None
    assert first.usage.judge.calls == 2
    assert second.usage.judge.calls == 2, "the first run's calls leaked into it"
    assert second.usage.judge.tokens == Usage(input_tokens=200, output_tokens=2)


def test_a_shared_judge_is_billed_once() -> None:
    judge = OneJudge()
    declared = Suite(
        tenant="acme",
        environment="staging",
        name="qa",
        assertions=[Asks(judge=judge), Asks(judge=judge, name="asks-again")],
        cases=[Case(id="c1")],
    )
    run = execute(declared, Spending(judge), created_at=CREATED)
    assert run.usage is not None
    assert run.usage.judge.calls == 1, "one instance, one bill"


def test_two_instances_of_the_same_judge_are_two_bills() -> None:
    """Correct, and stated in ADR 0025 §4 because it looks wrong: the two are
    one identity in `judge_config` and two lines of spending."""
    first, second = OneJudge(), OneJudge()
    declared = Suite(
        tenant="acme",
        environment="staging",
        name="qa",
        assertions=[Asks(judge=first), Asks(judge=second, name="asks-again")],
        cases=[Case(id="c1")],
    )

    class Both:
        config = {"provider": "fake", "model": "m-1"}

        def __call__(self, case: Case) -> Response:
            first.spend()
            second.spend()
            return Response(output="yes", cost_usd=0.01, usage=Usage(10, 5))

    run = execute(declared, Both(), created_at=CREATED)
    assert run.usage is not None
    assert run.usage.judge.calls == 2
    assert len(run.judge_config.identities) <= 1, "one identity, two bills"


# --------------------------------------------------------------------------- #
# The document
# --------------------------------------------------------------------------- #


def test_the_step_to_fourteen_writes_nothing() -> None:
    run = execute(suite(), Counting(), created_at=CREATED)
    current = run_to_dict(run)
    # 14 -> 15 writes nothing either (ADR 0026 §6), so a schema-13 document
    # still arrives here unchanged but for its version.
    # 16 -> 17 writes only onto a calibration band, and this run has none.
    assert SCHEMA_VERSION == 17
    assert upgrade_document({**current, "schema_version": 13}) == current


def test_a_migrated_document_records_no_bill_and_is_not_a_zero() -> None:
    """Absent is *not recorded*; `counted: 0` is *nothing was counted*. A
    reader must be able to tell them apart, which is the whole of §7's second
    condition."""
    run = execute(suite(), Counting(), created_at=CREATED)
    without = {k: v for k, v in run_to_dict(run).items() if k != "usage"}
    migrated = run_from_json(json.dumps({**without, "schema_version": SCHEMA_VERSION}))
    assert migrated.usage is None

    quiet = execute(suite(), Counting(quiet_after=0), created_at=CREATED)
    assert quiet.usage is not None and quiet.usage.target.counted == 0


def test_the_hash_survives_the_migration() -> None:
    """A schema-13 baseline migrated to 14 promotes against the current
    configuration without re-promotion."""
    declared = suite()
    run = execute(declared, Counting(), created_at=CREATED)
    at_thirteen = {**run_to_dict(run), "schema_version": 13}
    upgraded = upgrade_document(at_thirteen)
    assert upgraded["config_hash"] == declared.config_hash()


def test_the_document_round_trips() -> None:
    run = execute(suite(record_responses=True), Counting(), created_at=CREATED)
    assert run_from_json(run_to_json(run)) == run


def test_a_null_bill_is_refused_rather_than_read_as_nothing() -> None:
    """The asymmetry the 0.15.x delta-pass found on `status`, closed here before
    it exists: an explicit null is a malformed file, not an absence."""
    run = execute(suite(), Counting(), created_at=CREATED)
    document = run_to_dict(run)
    document["usage"] = None
    with pytest.raises(ValueError, match="usage"):
        run_from_json(json.dumps(document))


@pytest.mark.parametrize("amount", [float("inf"), float("-inf"), float("nan")])
def test_a_spend_that_is_not_a_number_is_refused(amount: float) -> None:
    """B-1 of the 0.16.0 delta-pass, and the guard beside it was written for the
    wrong half of the problem.

    `spent_usd < 0` catches a negative bill and lets through the two values that
    are not bills at all. Since 0.16.0 that matters more than it did: the figure
    flows into a run-level total, and two forged journal lines at `1e308` summed
    to `inf` — which `run_to_json` then wrote into the document as a bare
    `Infinity`. CPython's `json` accepts that as an extension; **no strict
    parser does**, so the run file round-tripped locally and was refused by the
    first conforming reader.
    """
    with pytest.raises(ValueError, match="not a finite number"):
        CallTotals(calls=1, counted=1, spent_usd=amount)


def test_a_fold_cannot_overflow_into_one_either() -> None:
    """The path the forgery actually took. `__add__` builds a new `CallTotals`,
    so the refusal covers the sum and not only the literal — which is what makes
    this a fix rather than a check at one call site."""
    huge = CallTotals(calls=1, counted=1, spent_usd=1e308)

    assert huge.spent_usd == 1e308, "a large but finite bill is still a bill"
    with pytest.raises(ValueError, match="not a finite number"):
        _ = huge + huge


def test_the_document_carries_no_json_extension() -> None:
    """The consequence, asserted where a reader meets it: whatever a run
    records, the bytes are JSON a strict parser reads."""
    run = execute(suite(), Counting(), created_at=CREATED)
    written = run_to_json(run)

    assert "Infinity" not in written
    assert "NaN" not in written
    json.loads(written, parse_constant=_refuse_constant)


def _refuse_constant(name: str) -> float:
    raise AssertionError(f"the document carries the JSON extension {name!r}")


def test_a_line_that_counted_more_than_it_covered_is_refused() -> None:
    with pytest.raises(ValueError, match="cannot count more calls"):
        CallTotals(calls=1, counted=2)


# --------------------------------------------------------------------------- #
# Where the counts come from
# --------------------------------------------------------------------------- #


def test_the_document_reads_the_typed_field_and_not_the_metadata() -> None:
    """The test that keeps the four string keys from becoming a second source of
    truth: a fact whose source is a string key is one typo away from absent."""

    class ByMetadata:
        config = {"provider": "fake", "model": "m-1"}

        def __call__(self, case: Case) -> Response:
            return Response(
                output="yes",
                cost_usd=0.01,
                metadata={"input_tokens": 10, "output_tokens": 5},
            )

    run = execute(suite(cases=1), ByMetadata(), created_at=CREATED)
    assert run.usage is not None
    assert (run.usage.target.calls, run.usage.target.counted) == (1, 0)
    assert run.usage.target.tokens == NO_USAGE


def test_usage_is_one_class_under_both_names() -> None:
    """The re-export may not quietly become a copy: a plugin's `isinstance` and
    this document's field have to mean the same type. (ADR 0025 §5)"""
    from digline.targets.pricing import Usage as FromTargets

    assert FromTargets is Usage


def test_usage_adds_field_by_field() -> None:
    assert Usage(1, 2, 3, 4) + Usage(10, 20, 30, 40) == Usage(11, 22, 33, 44)
    assert NO_USAGE + Usage(1, 2) == Usage(1, 2)


def test_a_negative_count_is_refused() -> None:
    with pytest.raises(ValueError, match="must not be negative"):
        Usage(input_tokens=-1, output_tokens=0)


# --------------------------------------------------------------------------- #
# The reading
# --------------------------------------------------------------------------- #


def test_the_parenthesis_appears_only_when_the_total_is_partial() -> None:
    whole = usage_lines(
        RunUsage(target=CallTotals(calls=2, counted=2, tokens=Usage(10, 5)))
    )
    assert whole == ["target: 2 calls, 10 in / 5 out, 0.000000 USD"]

    partial = usage_lines(
        RunUsage(target=CallTotals(calls=2, counted=1, tokens=Usage(10, 5)))
    )
    assert partial == ["target: 2 calls, 10 in / 5 out, 0.000000 USD (counted 1 of 2)"]


def test_a_document_with_no_bill_prints_no_line() -> None:
    assert usage_lines(None) == []


def test_a_side_that_made_no_calls_prints_no_line() -> None:
    lines = usage_lines(RunUsage(target=CallTotals(calls=1, counted=1)))
    assert len(lines) == 1 and lines[0].startswith("target:")


# --------------------------------------------------------------------------- #
# The journal: the bill survives a kill, and the format refuses by name
# --------------------------------------------------------------------------- #


class Dying:
    def __init__(self, die_at: int) -> None:
        self.calls = 0
        self.die_at = die_at
        self.config = {"provider": "fake", "model": "m-1"}

    def __call__(self, case: Case) -> Response:
        self.calls += 1
        if self.calls == self.die_at:
            raise SystemExit(9)
        return Response(output="yes", cost_usd=0.01, usage=Usage(10, 5))


def killed(root: Path, declared: Suite) -> tuple[FileResultStore, str]:
    store = FileResultStore(root)
    target = Dying(die_at=3)
    prepared = prepare(
        declared, target, now=CREATED, git_commit="deadbeef", artifacts={}
    )
    with pytest.raises(SystemExit):
        measure(declared, target, store=store, prepared=prepared)  # pyright: ignore[reportArgumentType]
    return store, journal_key(prepared.header)


def test_the_journal_keeps_the_bill_without_recording_any_answer(
    tmp_path: Path,
) -> None:
    """Requirement of ADR 0025 §11: the bill line does not ride
    `record_responses`. The suite here records nothing, and the legs still add
    up."""
    declared = suite(cases=4)
    store, _ = killed(tmp_path, declared)
    (pending,) = store.pending("acme", "qa")

    assert not pending.refusal, pending.refusal
    assert not any(case.responses for case in pending.done.values())
    assert pending.spent == CallTotals(
        calls=2, counted=2, tokens=Usage(20, 10), spent_usd=0.02
    )


def test_a_resumed_run_bills_every_leg(tmp_path: Path) -> None:
    declared = suite(cases=4)
    store, _ = killed(tmp_path, declared)
    prepared = prepare(
        declared,
        Counting(),
        now=CREATED,
        git_commit="deadbeef",
        artifacts={},
        resume=store.pending("acme", "qa")[0],
    )
    resumed = measure(declared, Counting(), store=store, prepared=prepared).run  # pyright: ignore[reportArgumentType]

    assert resumed.usage is not None
    assert resumed.usage.target.calls == 4, "two legs, four calls"
    assert resumed.usage.target.spent_usd == pytest.approx(0.04)


def test_this_reader_refuses_a_format_one_journal_by_name(tmp_path: Path) -> None:
    """The other direction of ADR 0025 §11's refusal. A journal written by a
    0.15.x digline carries no bill, so resuming it would produce a document
    under-billing its first leg — and the version is what makes that a refusal
    instead of a silence."""
    declared = suite(cases=4)
    store, key = killed(tmp_path, declared)
    stamp_journal_format(tmp_path, "acme", "qa", key, 1)

    (pending,) = store.pending("acme", "qa")
    assert "journal format 1" in pending.refusal, pending.refusal
    assert not pending.done, "a refused journal hands over no cases"


def test_a_resume_by_hand_must_say_what_it_spent() -> None:
    """A library caller gets the refusal rather than a zero: the default would
    be a silent undercount in the one direction this record is about."""
    declared = suite()
    done = {"c1": CaseResult(case_id="c1", verdicts=())}
    with pytest.raises(ValueError, match="no `spent` beside them"):
        execute(declared, Counting(), created_at=CREATED, done=done)

    run = execute(
        declared,
        Counting(),
        created_at=CREATED,
        done=done,
        spent=CallTotals(calls=1),
    )
    assert run.usage is not None
    assert (run.usage.target.calls, run.usage.target.counted) == (3, 2)
    assert run.usage.target.partial, "a declared leg with no counts stays partial"


def test_a_hand_built_run_records_no_bill() -> None:
    plain = Run(
        tenant="acme",
        environment="staging",
        suite="qa",
        config_hash="h",
        created_at=CREATED,
    )
    assert plain.usage is None
    assert "usage" not in run_to_json(plain)


# --------------------------------------------------------------------------- #
# The same guard, one class over: F-3 of the second 0.17.0 delta-pass
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "name",
    [
        "input_tokens",
        "output_tokens",
        "cache_read_tokens",
        "cache_write_tokens",
        "thinking_tokens",
    ],
)
def test_a_count_that_is_not_a_number_is_refused_by_name(name: str) -> None:
    """B-1's guard was written for `spent_usd` and the counts beside it kept the
    hole it closed.

    `NaN` is not negative and no ordering comparison against it is true, so it
    passed `< 0` here exactly as it passed `< 0` on the bill — and it passed
    `thinking > output` too, which is why the one field added in 0.17.0 was the
    one that could carry it furthest.
    """
    counts: dict[str, float] = {"input_tokens": 10, "output_tokens": 100}
    counts[name] = float("nan")

    with pytest.raises(ValueError, match=f"Usage.{name} is nan"):
        Usage(**counts)  # pyright: ignore[reportArgumentType]


@pytest.mark.parametrize("amount", [float("inf"), float("-inf"), float("nan")])
def test_every_non_finite_count_is_refused_and_not_only_nan(amount: float) -> None:
    """`inf` was refused before this, and for the wrong reason: it is *more
    thinking than output*, which is the right answer to a different question and
    no answer at all on `input_tokens`."""
    with pytest.raises(ValueError, match="not a finite number"):
        Usage(input_tokens=amount, output_tokens=1)  # pyright: ignore[reportArgumentType]


def test_a_non_finite_split_never_reaches_a_document() -> None:
    """The consequence this is really about, and it is worse than the bill's.

    A `NaN` written into a run file is read back through `int()`, so the
    document is refused by **its own reader**: written, listed, and unreadable
    for good. The refusal is at the value, so no sink has to defend itself.
    """
    with pytest.raises(ValueError, match="not a finite number"):
        Usage(input_tokens=10, output_tokens=5, thinking_tokens=float("nan"))  # pyright: ignore[reportArgumentType]


def test_the_fold_raises_rather_than_asserting() -> None:
    """It was an `assert`, on the argument that only our own arithmetic could
    fire it. Two things were wrong with that: `NaN` reached it from a reply, and
    `python -O` strips an assert — so the one release that needed the check had
    none, and the `NaN` total went through in silence.

    Constructed past `__post_init__` with `object.__setattr__`, because the
    guard now closes the honest door in: this asserts the fold's own behaviour,
    not that the value is reachable.
    """
    over = Usage(input_tokens=1, output_tokens=5, thinking_tokens=5)
    object.__setattr__(over, "thinking_tokens", 9)

    # `match` on the fold's **own** wording, not on "more thinking than
    # output": the mutation control caught that. Remove the check from `__add__`
    # and the `Usage` it returns refuses the same arithmetic at construction, so
    # a test matching the shared phrase passes with the fix deleted — and the
    # message a user then sees is the constructor's, which blames their
    # provider. The fold's check earns its place by *whose fault it says it is*,
    # so that is what is asserted.
    with pytest.raises(ValueError, match="folding 9 and 1 thinking tokens"):
        _ = over + Usage(input_tokens=1, output_tokens=1, thinking_tokens=1)


def test_the_fold_blames_neither_side() -> None:
    """The old message said "this fold is wrong, not the replies it added" — to
    a user whose provider had just sent a malformed count. The new one states
    the arithmetic and accuses nobody."""
    over = Usage(input_tokens=1, output_tokens=5, thinking_tokens=5)
    object.__setattr__(over, "thinking_tokens", 9)

    with pytest.raises(ValueError) as caught:
        _ = over + Usage(input_tokens=1, output_tokens=1, thinking_tokens=1)

    message = str(caught.value)
    assert "fold is wrong" not in message
    assert "not the replies" not in message
    # And it is not the constructor's message either, which says a provider sent
    # a malformed reply — true of a single bad reply, false of a bad fold.
    assert "malformed reply" not in message


def test_an_honest_fold_still_folds() -> None:
    """The guard is not a ceiling: two legal splits sum and stay legal."""
    assert Usage(10, 100, thinking_tokens=60) + Usage(1, 5, thinking_tokens=3) == Usage(
        11, 105, thinking_tokens=63
    )


def test_a_whole_float_and_a_bool_still_pass() -> None:
    """F-1 is **not** closed here, and the line is drawn deliberately: a value
    that is not a number is refused, and what a third-party target may hand us
    is a separate decision about the type's contract."""
    assert Usage(10, 100, thinking_tokens=True).thinking_tokens is True
    assert Usage(10, 100, thinking_tokens=2.0).thinking_tokens == 2.0  # pyright: ignore[reportArgumentType]
