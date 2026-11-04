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
    verdict = judged(MaxSteps(limit=2, count="tool"), steps=GOOD)
    assert verdict.status == "fail"
    assert verdict.score.metadata == {"steps": 3, "limit": 2}


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
        (Never(tool="issue_refund"), LOOKUP_BEFORE_REFUND),
        (Never(tool="lookup_order"), LOOKUP_BEFORE_REFUND),
        (
            LOOKUP_BEFORE_REFUND,
            Before(first="issue_refund", then="lookup_order", name="refund_first"),
        ),
        (MaxSteps(limit=1, count="tool"), LOOKUP_THEN_REFUND),
    ],
    ids=[
        "never-subsequence",
        "never-tools_called",
        "never-tool_called_with",
        "never-before-then",
        "never-before-first",
        "before-before",
        "max_steps-subsequence",
    ],
)
def test_a_suite_refuses_two_checks_that_cannot_both_pass(one: Any, other: Any) -> None:
    with pytest.raises(RefusedError, match="cannot both pass") as refused:
        suite(one, other)
    assert repr(one.name) in str(refused.value)
    assert repr(other.name) in str(refused.value)


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


def test_a_replay_refuses_a_check_that_counts_steps() -> None:
    with pytest.raises(
        ReplayError, match="steps are not in the run document before schema 23"
    ):
        rejudge(
            suite(MaxSteps(limit=6, count="model")),
            recorded(),
            key="src",
            created_at=LATER,
        )


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
