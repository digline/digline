"""What an application reports about its trajectory and its counts.

Every refusal is tested beside the value it must let through: a reader that
refuses everything passes each "must fail" test, and one that refuses nothing
passes each "must pass" test, so only the pair says the reader discriminates.

The point of the whole file is the pair at the top. Before these paths existed,
`ToolsCalled` and `ToolCalledWith` loaded from a TOML suite against an HTTP
target and then **errored on every case** — the honest third outcome to a
question nothing could answer, which is worse than a check that refuses to load.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, cast

import pytest

from digline.core import EvaluatorInputs, ToolCalledWith, ToolsCalled, Usage
from digline.host import UsageError
from digline.host.toml_suite import load_toml_suite
from digline.run import Case
from digline.targets.http import (
    USAGE_FIELDS,
    HttpTarget,
    reported_tool_calls,
    reported_tools,
    reported_usage,
)

CASE = Case(id="c1", vars={"question": "where is order 4821?"})

#: One call, fully reported, as an application that knows everything says it.
CALL = {
    "tool": "activate_skill",
    "arguments": {"skill": "invoice"},
    "status": "success",
    "result": "ok",
}


def a_reply(**extra: object) -> dict[str, object]:
    return {"data": {"answer": "done"}, **extra}


@pytest.fixture
def endpoint() -> Iterator[Any]:
    """A real endpoint on localhost, because `_dig` reads a decoded body.

    A fake target would not exercise the one thing under test — that these
    values survive JSON and arrive as the assertions read them.
    """
    replies: dict[str, object] = {}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
            body = json.dumps(replies).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(  # pragma: no cover - quiet
            self, format: str, *args: object
        ) -> None:
            return

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    class Endpoint:
        url = f"http://127.0.0.1:{server.server_address[1]}/answer"

        def answers(self, reply: dict[str, object]) -> None:
            replies.clear()
            replies.update(reply)

    try:
        yield Endpoint()
    finally:
        server.shutdown()


def inputs_from(target: HttpTarget) -> EvaluatorInputs:
    """The mapper's own shape: `Response.metadata` under `"response"`."""
    response = target(CASE)
    return EvaluatorInputs(
        output=response.output,
        metadata={"case": {}, "response": dict(response.metadata)},
    )


# --------------------------------------------------------------------------- #
# The pair the file exists for


def test_a_trajectory_check_is_answerable_once_the_path_is_declared(
    endpoint: Any,
) -> None:
    endpoint.answers(a_reply(trajectory={"calls": [CALL]}))
    target = HttpTarget(
        endpoint.url,
        body={"q": "case.vars.question"},
        output_path="data.answer",
        tool_calls_path="trajectory.calls",
    )
    given = inputs_from(target)

    assert ToolsCalled(expected=["activate_skill"])(given).status == "pass"
    assert (
        ToolCalledWith(tool="activate_skill", arguments={"skill": "invoice"})(
            given
        ).status
        == "pass"
    )


def test_without_the_path_both_checks_error_rather_than_judge(endpoint: Any) -> None:
    """The defect, kept as a test so it cannot come back quietly.

    `error` and not `fail`: absent is not empty, and a target that reports no
    trajectory is not a model that called none.
    """
    endpoint.answers(a_reply(trajectory={"calls": [CALL]}))
    target = HttpTarget(
        endpoint.url, body={"q": "case.vars.question"}, output_path="data.answer"
    )
    given = inputs_from(target)

    called = ToolsCalled(expected=["activate_skill"])(given)
    assert called.status == "error"
    assert "reports no tool calls" in called.reason
    with_args = ToolCalledWith(tool="activate_skill", arguments={"skill": "invoice"})(
        given
    )
    assert with_args.status == "error"


def test_a_wrong_trajectory_fails_rather_than_passing(endpoint: Any) -> None:
    """The other half: the check discriminates once it can read anything."""
    endpoint.answers(a_reply(trajectory={"calls": [CALL]}))
    target = HttpTarget(
        endpoint.url,
        body={"q": "case.vars.question"},
        output_path="data.answer",
        tool_calls_path="trajectory.calls",
    )
    given = inputs_from(target)

    assert ToolsCalled(expected=["refund_order"])(given).status == "fail"
    assert (
        ToolCalledWith(tool="activate_skill", arguments={"skill": "refund"})(
            given
        ).status
        == "fail"
    )


# --------------------------------------------------------------------------- #
# The names, and the one the application did not give


def test_the_names_are_derived_from_the_calls_when_only_those_are_declared(
    endpoint: Any,
) -> None:
    """So the two readings of one answer cannot disagree."""
    endpoint.answers(a_reply(trajectory={"calls": [CALL]}))
    target = HttpTarget(
        endpoint.url,
        body={"q": "case.vars.question"},
        output_path="data.answer",
        tool_calls_path="trajectory.calls",
    )
    response = target(CASE)

    assert response.metadata["tools"] == ["activate_skill"]


def test_two_declared_paths_that_disagree_are_refused(endpoint: Any) -> None:
    endpoint.answers(a_reply(trajectory={"calls": [CALL], "names": ["something_else"]}))
    target = HttpTarget(
        endpoint.url,
        body={"q": "case.vars.question"},
        output_path="data.answer",
        tools_path="trajectory.names",
        tool_calls_path="trajectory.calls",
    )

    with pytest.raises(ValueError, match="different trajectories"):
        target(CASE)


def test_an_unnamed_call_keeps_its_position() -> None:
    """`null` is a call the application did not name, at its place. (ADR 0018 §1)"""
    assert reported_tools([None, "second"], "t") == (None, "second")

    calls = reported_tool_calls(
        [{"tool": None, "arguments": None, "status": "not_reported"}], "c"
    )
    assert calls[0].tool is None


def test_an_empty_name_is_refused_rather_than_read_as_the_absence() -> None:
    with pytest.raises(ValueError, match="not a tool name"):
        reported_tools([""], "t")
    with pytest.raises(ValueError, match="not a tool name"):
        reported_tool_calls([{"tool": "", "status": "success"}], "c")


def test_a_name_that_is_not_a_string_is_refused() -> None:
    with pytest.raises(ValueError, match=r"t\[0\] is 7"):
        reported_tools([7], "t")


def test_a_trajectory_that_is_not_a_list_is_refused() -> None:
    for wrong in ("activate_skill", {"tool": "activate_skill"}, 3):
        with pytest.raises(ValueError, match="not a list of"):
            reported_tools(wrong, "t")
        with pytest.raises(ValueError, match="not a list of"):
            reported_tool_calls(wrong, "c")


# --------------------------------------------------------------------------- #
# The vocabularies, closed here because the values arrive from outside


def test_a_call_with_no_status_is_refused_and_does_not_default_to_success() -> None:
    """A plain-function target defaults to `success` by its own history; an
    application has none, and writing *success* by omission is the vacuously
    green report fixed decision 3 refuses."""
    with pytest.raises(ValueError, match="no default"):
        reported_tool_calls(
            [{"tool": "activate_skill", "arguments": cast("dict[str, object]", {})}],
            "c",
        )


def test_an_unknown_status_is_refused_by_name() -> None:
    with pytest.raises(ValueError, match="c\\[0\\].status is 'ok'"):
        reported_tool_calls([{"tool": "activate_skill", "status": "ok"}], "c")


def test_every_status_the_vocabulary_has_is_accepted() -> None:
    for status in ("success", "error", "not_reported"):
        calls = reported_tool_calls([{"tool": "t", "status": status}], "c")
        assert calls[0].status == status


def test_an_unknown_result_absence_is_refused() -> None:
    with pytest.raises(ValueError, match="result_absence is 'dunno'"):
        reported_tool_calls(
            [{"tool": "t", "status": "not_reported", "result_absence": "dunno"}], "c"
        )


def test_a_result_beside_a_declared_absence_is_refused_by_ToolCall() -> None:
    """One rule, checked in the place that already owns it."""
    with pytest.raises(ValueError, match="declares its result"):
        reported_tool_calls(
            [
                {
                    "tool": "t",
                    "status": "not_reported",
                    "result": "ok",
                    "result_absence": "not_reported",
                }
            ],
            "c",
        )


def test_arguments_may_be_an_object_a_string_or_absent() -> None:
    for arguments in ({"skill": "invoice"}, '{"skill": "invoice"}', None):
        calls = reported_tool_calls(
            [{"tool": "t", "status": "success", "arguments": arguments}], "c"
        )
        assert calls[0].arguments == arguments


def test_arguments_that_are_neither_are_refused() -> None:
    with pytest.raises(ValueError, match="arguments is a int"):
        reported_tool_calls([{"tool": "t", "status": "success", "arguments": 7}], "c")


def test_a_call_with_no_tool_key_at_all_is_refused() -> None:
    """Missing is malformed; `"tool": null` is the statement."""
    with pytest.raises(ValueError, match="has no 'tool'"):
        reported_tool_calls([{"status": "success"}], "c")


# --------------------------------------------------------------------------- #
# The counts


def test_the_counts_arrive_by_their_own_names(endpoint: Any) -> None:
    endpoint.answers(
        a_reply(
            usage={"input_tokens": 120, "output_tokens": 44, "cache_read_tokens": 9}
        )
    )
    target = HttpTarget(
        endpoint.url,
        body={"q": "case.vars.question"},
        output_path="data.answer",
        usage_path="usage",
    )

    assert target(CASE).usage == Usage(
        input_tokens=120, output_tokens=44, cache_read_tokens=9
    )


def test_no_usage_path_reports_no_counts_rather_than_zero(endpoint: Any) -> None:
    endpoint.answers(a_reply(usage={"input_tokens": 1, "output_tokens": 2}))
    target = HttpTarget(
        endpoint.url, body={"q": "case.vars.question"}, output_path="data.answer"
    )

    assert target(CASE).usage is None


def test_a_count_under_another_name_is_refused_with_the_allowed_set() -> None:
    with pytest.raises(ValueError, match="promptTokens"):
        reported_usage({"promptTokens": 10, "output_tokens": 2}, "u")


def test_the_two_mandatory_counts_are_mandatory() -> None:
    for missing in ("input_tokens", "output_tokens"):
        counts = {"input_tokens": 10, "output_tokens": 2}
        del counts[missing]
        with pytest.raises(ValueError, match=f"gives no {missing}"):
            reported_usage(counts, "u")


def test_a_boolean_count_is_refused_here_because_Usage_accepts_it() -> None:
    """F-1, kept unreachable.

    `Usage(input_tokens=True)` is accepted — its guards are ordering
    comparisons, which a `bool` satisfies — and the second 0.17.0 delta-pass
    graded that LOW because nothing reachable could deliver one. An
    application's JSON is the first path that can.
    """
    with pytest.raises(ValueError, match="not a token count"):
        reported_usage({"input_tokens": True, "output_tokens": 2}, "u")

    # And the value it would have become, had this reader not been here.
    assert Usage(input_tokens=True, output_tokens=2).input_tokens is True


def test_a_fractional_count_is_refused() -> None:
    with pytest.raises(ValueError, match="not a token count"):
        reported_usage({"input_tokens": 2.7, "output_tokens": 2}, "u")


def test_thinking_tokens_absent_is_not_reported_and_never_a_zero() -> None:
    assert (
        reported_usage({"input_tokens": 1, "output_tokens": 2}, "u").thinking_tokens
        is None
    )
    assert (
        reported_usage(
            {"input_tokens": 1, "output_tokens": 2, "thinking_tokens": 0}, "u"
        ).thinking_tokens
        == 0
    )


def test_usage_that_is_not_an_object_is_refused() -> None:
    with pytest.raises(ValueError, match="not an object of counts"):
        reported_usage([1, 2], "u")


def test_usage_fields_are_exactly_the_fields_Usage_has() -> None:
    """So a count added to `Usage` cannot be silently unreadable over HTTP."""
    assert set(USAGE_FIELDS) == set(Usage.__dataclass_fields__)


# --------------------------------------------------------------------------- #
# The declarative form, which gets all three for free


def test_a_toml_suite_inherits_the_three_paths(tmp_path: Path) -> None:
    """`_http` splats the `[target]` table and its allow-list is derived from
    `HttpTarget.__init__` by `inspect.signature`, so a new keyword parameter
    reaches a data suite with no edit to the loader. Verified rather than
    assumed, because "it comes for free" is the kind of claim that is true until
    somebody names the parameters by hand."""
    suite = tmp_path / "suite.toml"
    (tmp_path / "cases.json").write_text('[{"id": "c1", "vars": {"q": "x"}}]')
    suite.write_text(
        """
[suite]
tenant = "acme"
environment = "dev"
name = "gate"
cases = "cases.json"

[target]
type = "http"
url = "http://127.0.0.1:8731/answer"
output_path = "data.answer"
tools_path = "trajectory.names"
tool_calls_path = "trajectory.calls"
usage_path = "usage"
[target.body]
q = "case.vars.q"

[[assertions]]
type = "tools_called"
expected = ["activate_skill"]
""",
        encoding="utf-8",
    )
    _, target = load_toml_suite(suite, root=tmp_path)

    assert isinstance(target, HttpTarget)
    assert target.tools_path == "trajectory.names"
    assert target.tool_calls_path == "trajectory.calls"
    assert target.usage_path == "usage"


def test_a_typo_in_one_of_them_is_refused_at_load(tmp_path: Path) -> None:
    """The other half: the allow-list is real, and names the near miss."""
    suite = tmp_path / "suite.toml"
    (tmp_path / "cases.json").write_text('[{"id": "c1", "vars": {"q": "x"}}]')
    suite.write_text(
        """
[suite]
tenant = "acme"
environment = "dev"
name = "gate"
cases = "cases.json"

[target]
type = "http"
url = "http://127.0.0.1:8731/answer"
output_path = "data.answer"
usage_paht = "usage"
[target.body]
q = "case.vars.q"

[[assertions]]
type = "contains"
needle = "x"
""",
        encoding="utf-8",
    )
    with pytest.raises(UsageError, match="has no parameter `usage_paht`"):
        load_toml_suite(suite, root=tmp_path)
