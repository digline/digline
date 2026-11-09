"""The four checks on a trajectory's steps. (ADR 0060 §4)

The case is an agent that handles a refund: it looks the order up, then
refunds it, and must never delete the account. Each check has a case that
passes, one that fails and one that errors; the shared reading has its own
errors; a suite that declares two checks that cannot both pass is refused,
one pair at a time; a replay refuses the check that counts steps; and the
TOML loader takes each one.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from digline.core import (
    Before,
    Contains,
    EvaluatorInputs,
    MaxSteps,
    Never,
    RefusedError,
    Subsequence,
    ToolCalledWith,
    ToolsCalled,
    Verdict,
)
from digline.core.run import steps_as_reported
from digline.host.toml_suite import load_toml_suite
from digline.run import Case, Response, Suite, execute
from digline.run.replay import ReplayError, rejudge

CREATED = "2026-11-04T00:00:00.000000Z"
NO_ARGUMENTS: dict[str, object] = {}
LATER = "2026-11-04T00:00:01.000000Z"


def model(finish: str | None = "tool_use") -> dict[str, object]:
    step: dict[str, object] = {"actor": "model"}
    if finish is not None:
        step["finish"] = finish
    return step


def tool(name: str | None) -> dict[str, object]:
    return {"actor": "tool", "tool": name, "arguments": {}}


def steps(*made: dict[str, object]) -> list[dict[str, object]]:
    return [{"index": at, **step} for at, step in enumerate(made)]


def inputs(**response: object) -> EvaluatorInputs:
    return EvaluatorInputs(output="done", metadata={"response": dict(response)})


#: The agent did what it should: looked up, checked the policy, refunded.
GOOD = steps(
    model(),
    tool("lookup_order"),
    model(),
    tool("check_policy"),
    tool("issue_refund"),
    model("stop"),
)
#: The agent refunded first and looked up afterwards, then deleted.
BAD = steps(
    model(),
    tool("issue_refund"),
    model(),
    tool("lookup_order"),
    tool("delete_account"),
    model("stop"),
)


def judged(check: Any, **response: object) -> Verdict:
    return check(inputs(**response))


def status(check: Any, **response: object) -> str:
    return judged(check, **response).status


# -- Subsequence --------------------------------------------------------------- #

LOOKUP_THEN_REFUND = Subsequence(tools=["lookup_order", "issue_refund"])


def test_subsequence_passes_with_anything_between() -> None:
    verdict = judged(LOOKUP_THEN_REFUND, steps=GOOD)
    assert verdict.status == "pass"
    assert verdict.score.metadata == {
        "matched": 2,
        "expected": 2,
        "tool_steps": 3,
        "called": ["lookup_order", "check_policy", "issue_refund"],
    }


def test_subsequence_fails_out_of_order() -> None:
    verdict = judged(LOOKUP_THEN_REFUND, steps=BAD)
    assert verdict.status == "fail"
    assert verdict.score.metadata["matched"] == 1


def test_subsequence_errors_where_an_unnamed_call_decides() -> None:
    unnamed = steps(model(), tool("lookup_order"), model(), tool(None))
    assert status(LOOKUP_THEN_REFUND, steps=unnamed) == "error"


def test_subsequence_fails_where_no_unnamed_call_could_save_it() -> None:
    unnamed = steps(model(), tool(None), model(), tool("lookup_order"))
    assert status(Subsequence(tools=["a", "b", "c"]), steps=unnamed) == "fail"


def test_subsequence_reads_tools_where_there_are_no_steps() -> None:
    assert status(LOOKUP_THEN_REFUND, tools=["lookup_order", "issue_refund"]) == "pass"
    assert status(LOOKUP_THEN_REFUND, tools=["issue_refund"]) == "fail"


def test_subsequence_refuses_what_cannot_be_checked() -> None:
    with pytest.raises(RefusedError, match="must not be empty"):
        Subsequence(tools=[])
    with pytest.raises(RefusedError, match="non-empty string"):
        Subsequence(tools=["lookup_order", ""])
    with pytest.raises(RefusedError, match="letter by letter"):
        Subsequence(tools="lookup_order")


# -- Before ------------------------------------------------------------------- #

LOOKUP_BEFORE_REFUND = Before(first="lookup_order", then="issue_refund")


def test_before_passes_where_then_follows_first() -> None:
    verdict = judged(LOOKUP_BEFORE_REFUND, steps=GOOD)
    assert verdict.status == "pass"
    assert verdict.score.metadata == {
        "violations": 0,
        "first_calls": 1,
        "then_calls": 1,
    }


def test_before_passes_where_then_was_never_called_and_says_so() -> None:
    verdict = judged(LOOKUP_BEFORE_REFUND, steps=steps(model(), tool("lookup_order")))
    assert verdict.status == "pass"
    assert verdict.score.metadata["then_calls"] == 0


def test_before_fails_on_a_then_with_no_first_before_it() -> None:
    verdict = judged(LOOKUP_BEFORE_REFUND, steps=BAD)
    assert verdict.status == "fail"
    assert verdict.score.metadata["violations"] == 1


def test_before_errors_where_an_unnamed_call_could_be_then() -> None:
    unnamed = steps(model(), tool(None), model(), tool("lookup_order"))
    assert status(LOOKUP_BEFORE_REFUND, steps=unnamed) == "error"


def test_before_refuses_a_call_before_itself_and_an_empty_name() -> None:
    with pytest.raises(RefusedError, match="cannot come before itself"):
        Before(first="lookup_order", then="lookup_order")
    with pytest.raises(RefusedError, match="non-empty string"):
        Before(first="", then="issue_refund")


# -- Never -------------------------------------------------------------------- #

NEVER_DELETE = Never(tool="delete_account")


def test_never_passes_where_the_tool_was_not_called() -> None:
    verdict = judged(NEVER_DELETE, steps=GOOD)
    assert verdict.status == "pass"
    assert verdict.score.metadata == {"occurrences": 0}


def test_never_fails_on_a_call_and_counts_them() -> None:
    verdict = judged(NEVER_DELETE, steps=BAD)
    assert verdict.status == "fail"
    assert verdict.score.metadata == {"occurrences": 1}


def test_never_errors_where_an_unnamed_call_may_be_the_one() -> None:
    assert status(NEVER_DELETE, steps=steps(model(), tool(None))) == "error"


def test_never_refuses_an_empty_name() -> None:
    with pytest.raises(RefusedError, match="non-empty string"):
        Never(tool="")


# -- MaxSteps ----------------------------------------------------------------- #


def test_max_steps_passes_within_the_limit() -> None:
    verdict = judged(MaxSteps(limit=3, count="model"), steps=GOOD)
    assert verdict.status == "pass"
    assert verdict.score.metadata == {"steps": 3, "limit": 3}


def test_max_steps_fails_over_the_limit_counting_the_actor_named() -> None:
    assert status(MaxSteps(limit=2, count="model"), steps=GOOD) == "fail"
    # Two turns and four calls: each count is read from its own actor.
    busy = steps(
        model(), tool("a"), tool("b"), tool("c"), model(), tool("d"), model("stop")
    )
    assert status(MaxSteps(limit=3, count="model"), steps=busy) == "pass"
    verdict = judged(MaxSteps(limit=3, count="tool"), steps=busy)
    assert verdict.status == "fail"
    assert verdict.score.metadata == {"steps": 4, "limit": 3}


def test_max_steps_errors_without_steps_and_names_wrap() -> None:
    verdict = judged(MaxSteps(limit=6, count="model"), tools=["lookup_order"])
    assert verdict.status == "error"
    assert "wrap()" in verdict.reason
    assert "`steps`" in verdict.reason


def test_max_steps_refuses_a_limit_below_one_and_another_actor() -> None:
    with pytest.raises(RefusedError, match="integer from 1"):
        MaxSteps(limit=0, count="model")
    with pytest.raises(RefusedError, match="integer from 1"):
        MaxSteps(limit=True, count="model")
    with pytest.raises(RefusedError, match="'model' or 'tool'"):
        MaxSteps(limit=6, count="engine")  # pyright: ignore[reportArgumentType]


def test_max_steps_cannot_be_built_without_count() -> None:
    with pytest.raises(TypeError, match="count"):
        MaxSteps(limit=6)  # pyright: ignore[reportCallIssue]


# -- the reading, shared ---------------------------------------------------------- #

ORDER_CHECKS = [LOOKUP_THEN_REFUND, LOOKUP_BEFORE_REFUND, NEVER_DELETE]


@pytest.mark.parametrize("check", ORDER_CHECKS, ids=lambda check: check.name)
def test_absent_steps_and_tools_is_an_error_naming_both(check: Any) -> None:
    verdict = judged(check)
    assert verdict.status == "error"
    assert "`steps`" in verdict.reason and "`tools`" in verdict.reason
    assert "wrap()" in verdict.reason


@pytest.mark.parametrize(
    "check",
    [*ORDER_CHECKS, MaxSteps(limit=6, count="model")],
    ids=lambda check: check.name,
)
def test_a_tool_use_finish_with_no_tool_step_after_it_is_an_error(check: Any) -> None:
    contradicted = steps(model(), tool("lookup_order"), model("tool_use"))
    verdict = judged(check, steps=contradicted)
    assert verdict.status == "error"
    assert "no tool step follows it" in verdict.reason


@pytest.mark.parametrize("check", ORDER_CHECKS, ids=lambda check: check.name)
def test_steps_that_disagree_with_tool_calls_are_an_error(check: Any) -> None:
    calls = [{"tool": "lookup_order"}, {"tool": "issue_refund"}]
    verdict = judged(check, steps=GOOD, tool_calls=calls)
    assert verdict.status == "error"
    assert "`tool_calls` name different calls" in verdict.reason


def test_steps_that_agree_with_tool_calls_and_tools_are_read() -> None:
    names = ["lookup_order", "check_policy", "issue_refund"]
    calls = [{"tool": name} for name in names]
    assert status(LOOKUP_THEN_REFUND, steps=GOOD, tool_calls=calls, tools=names) == (
        "pass"
    )


def test_a_tool_use_finish_with_no_tools_is_an_error_on_the_fallback() -> None:
    assert status(NEVER_DELETE, tools=[], finish="tool_use") == "error"


# -- the suite refuses two checks that cannot both pass --------------------------- #


def suite(*checks: Any) -> Suite:
    return Suite(
        tenant="acme",
        environment="test",
        name="refunds",
        assertions=list(checks),
        cases=[Case(id="refund")],
    )


@pytest.mark.parametrize(
    ("one", "other"),
    [
        (Never(tool="lookup_order"), LOOKUP_THEN_REFUND),
        (Never(tool="lookup_order"), ToolsCalled(expected=["lookup_order"])),
        (
            Never(tool="lookup_order"),
            ToolCalledWith(tool="lookup_order", arguments={"order": 42}),
        ),
        (MaxSteps(limit=1, count="tool"), LOOKUP_THEN_REFUND),
    ],
    ids=[
        "never-subsequence",
        "never-tools_called",
        "never-tool_called_with",
        "max_steps-subsequence",
    ],
)
def test_a_suite_refuses_two_checks_that_cannot_both_pass(one: Any, other: Any) -> None:
    with pytest.raises(RefusedError, match="cannot both pass") as refused:
        suite(one, other)
    said = str(refused.value)
    assert repr(one.name) in said
    assert repr(other.name) in said
    assert "so the suite would fail every case" in said


REFUND_FIRST = Before(first="issue_refund", then="lookup_order", name="refund_first")


@pytest.mark.parametrize(
    ("one", "other", "turn"),
    [
        (
            Never(tool="issue_refund"),
            LOOKUP_BEFORE_REFUND,
            "a turn that calls the tool the first forbids: the second allows it "
            "after another, and the first forbids it",
        ),
        (
            Never(tool="lookup_order"),
            LOOKUP_BEFORE_REFUND,
            "a turn that calls the second's later tool: the second needs the tool "
            "the first forbids before it, so that one is forbidden too, under "
            "another name",
        ),
        (
            LOOKUP_BEFORE_REFUND,
            REFUND_FIRST,
            "a turn that calls both tools: each asks for the other's tool first",
        ),
    ],
    ids=["never-before-then", "never-before-first", "before-before"],
)
def test_two_checks_that_contradict_on_some_turns_say_which(
    one: Any, other: Any, turn: str
) -> None:
    """`never` beside a `before` on its tool, and two reversed `before`s, are
    refused too, and the sentence says the truth about them: both pass on a
    turn that calls neither tool, and they disagree on the turn named, not on
    every case. (P-1588; it said *which cannot both pass … would fail every
    case*)"""
    with pytest.raises(RefusedError) as refused:
        suite(one, other)
    said = str(refused.value)
    assert said == (
        f"suite 'refunds' declares {one.name!r} and {other.name!r}, which "
        f"contradict each other on {turn}. Every case is asked every check, so "
        "the suite would fail every such turn. Remove one of the two"
    )
    assert "cannot both pass" not in said
    # What the sentence rests on: a turn that calls neither tool passes both.
    assert status(one, steps=[]) == status(other, steps=[]) == "pass"


def test_a_suite_takes_checks_that_can_both_pass() -> None:
    suite(
        NEVER_DELETE,
        LOOKUP_THEN_REFUND,
        LOOKUP_BEFORE_REFUND,
        MaxSteps(limit=2, count="tool"),
        MaxSteps(limit=1, count="model", name="one_turn"),
    )


# -- a replay ------------------------------------------------------------------- #


def agent(case: Case) -> Response:
    names = ["lookup_order", "issue_refund"]
    return Response(
        output="refunded",
        metadata={
            "tools": names,
            "tool_calls": [
                {"tool": name, "arguments": NO_ARGUMENTS, "status": "success"}
                for name in names
            ],
        },
    )


def recorded() -> Any:
    declared = Suite(
        tenant="acme",
        environment="test",
        name="refunds",
        assertions=[Contains(needle="refunded")],
        cases=[Case(id="refund")],
        record_responses=True,
    )
    return execute(declared, agent, created_at=CREATED)


def test_a_replay_judges_an_order_check_from_the_recorded_names() -> None:
    again = rejudge(suite(LOOKUP_THEN_REFUND), recorded(), key="src", created_at=LATER)
    [verdict] = again.results[0].verdicts
    assert verdict.status == "pass"


def test_a_replay_refuses_an_order_check_over_a_run_with_no_trajectory() -> None:
    declared = Suite(
        tenant="acme",
        environment="test",
        name="refunds",
        assertions=[Contains(needle="refunded")],
        cases=[Case(id="refund")],
        record_responses=True,
    )
    source = execute(
        declared, lambda case: Response(output="refunded"), created_at=CREATED
    )
    with pytest.raises(ReplayError, match="reported no trajectory"):
        rejudge(suite(NEVER_DELETE), source, key="src", created_at=LATER)


def test_a_replay_refuses_max_steps_where_no_steps_were_recorded() -> None:
    with pytest.raises(ReplayError, match="which counts them"):
        rejudge(
            suite(MaxSteps(limit=6, count="model")),
            recorded(),
            key="src",
            created_at=LATER,
        )


def stepping(case: Case) -> Response:
    """Two turns of an agent, reported as steps and as calls, which agree."""
    calls = [
        {"tool": "lookup_order", "arguments": NO_ARGUMENTS, "status": "success"},
        {"tool": "issue_refund", "arguments": NO_ARGUMENTS, "status": "success"},
    ]
    return Response(
        output="refunded",
        metadata={
            "tools": [call["tool"] for call in calls],
            "tool_calls": calls,
            "steps": steps_as_reported(
                [("tool_use", calls[:1]), ("tool_use", calls[1:])]
            ),
        },
    )


def recorded_with_steps() -> Any:
    declared = Suite(
        tenant="acme",
        environment="test",
        name="refunds",
        assertions=[Contains(needle="refunded")],
        cases=[Case(id="refund")],
        record_responses=True,
    )
    return execute(declared, stepping, created_at=CREATED)


@pytest.mark.parametrize(
    ("check", "status"),
    [
        (MaxSteps(limit=2, count="model"), "pass"),
        (MaxSteps(limit=1, count="model"), "fail"),
        (MaxSteps(limit=1, count="tool"), "fail"),
        (LOOKUP_THEN_REFUND, "pass"),
        (LOOKUP_BEFORE_REFUND, "pass"),
        (NEVER_DELETE, "pass"),
    ],
    ids=["max-model-2", "max-model-1", "max-tool-1", "subsequence", "before", "never"],
)
def test_a_replay_judges_the_recorded_steps(check: Any, status: str) -> None:
    again = rejudge(suite(check), recorded_with_steps(), key="src", created_at=LATER)
    [verdict] = again.results[0].verdicts
    assert verdict.status == status


# -- TOML --------------------------------------------------------------------------- #

TOML = """
[suite]
tenant = "acme"
environment = "test"
name = "refunds"
cases = "cases.json"

[target]
type = "http"
url = "http://localhost:8080/answer"
output_path = "data"

  [target.body]
  question = "case.vars.question"

[[assertions]]
{check}
"""


@pytest.mark.parametrize(
    ("declared", "expected"),
    [
        (
            'type = "subsequence"\ntools = ["lookup_order", "issue_refund"]',
            LOOKUP_THEN_REFUND,
        ),
        (
            'type = "before"\nfirst = "lookup_order"\nthen = "issue_refund"',
            LOOKUP_BEFORE_REFUND,
        ),
        ('type = "never"\ntool = "delete_account"', NEVER_DELETE),
        (
            'type = "max_steps"\nlimit = 6\ncount = "model"',
            MaxSteps(limit=6, count="model"),
        ),
    ],
    ids=["subsequence", "before", "never", "max_steps"],
)
def test_toml_declares_each_check(tmp_path: Path, declared: str, expected: Any) -> None:
    (tmp_path / "suite.toml").write_text(TOML.format(check=declared), encoding="utf-8")
    (tmp_path / "cases.json").write_text(
        '[{"id": "a", "vars": {"question": "?"}}]', encoding="utf-8"
    )
    loaded = load_toml_suite(tmp_path / "suite.toml")[0]
    [check] = loaded.assertions
    assert check == expected
    assert check.identity == expected.identity
