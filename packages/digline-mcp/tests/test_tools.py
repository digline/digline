"""The six tools against a real repository, and the CLI beside them.

The anti-drift test is the one this package exists for: the tool's response and
the CLI's `--json` are the same object, because they are built by the same
function. If that ever stops being true, ADR 0011 §6 was a wasted afternoon.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import anyio
import pytest
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import CallToolResult
from tests._helpers import cli, run_key, write_suite

from digline_mcp.server import build_server


def call(root: Path, tool: str, **arguments: Any) -> dict[str, Any]:
    async def go() -> dict[str, Any]:
        server = build_server(str(root), None, None)
        result = await server.call_tool(tool, arguments)
        # `call_tool` can also return `InputRequiredResult` — the SDK's
        # elicitation path, which nothing here uses. Narrowed rather than cast,
        # so a tool that ever started asking the caller a question fails here.
        assert isinstance(result, CallToolResult)
        assert result.structured_content is not None
        return dict(result.structured_content)

    return anyio.run(go)


def refusal(root: Path, tool: str, **arguments: Any) -> str:
    async def go() -> str:
        server = build_server(str(root), None, None)
        with pytest.raises(ToolError) as caught:
            await server.call_tool(tool, arguments)
        return str(caught.value)

    return anyio.run(go)


# --------------------------------------------------------------------------- #
# The acknowledged count (ADR 0011 §2)
# --------------------------------------------------------------------------- #


def test_run_without_the_count_is_refused_and_told_the_number(repo: Path) -> None:
    """The first call is the probe, and the refusal carries its own answer.

    Two cases, one sample each, so the number is 2 — and the sentence names the
    judge's own repeat factor, which the integer deliberately does not cover.
    """
    message = refusal(repo, "run", suite=str(repo / "suite_qa.py"))
    assert "2 calls to the target" in message
    assert "acknowledge_calls=2" in message
    assert "2 cases × 1 sample = 2 calls to the target" in message
    # Nothing was written: a refused run is a run that did not happen.
    assert not list((repo / ".digline").rglob("*.json"))


def test_a_wrong_count_is_refused_too(repo: Path) -> None:
    message = refusal(
        repo, "run", suite=str(repo / "suite_qa.py"), acknowledge_calls=99
    )
    assert "acknowledge_calls=99 does not match" in message
    assert "plans 2 calls" in message
    assert not list((repo / ".digline").rglob("*.json"))


def test_the_right_count_runs_it_once(repo: Path) -> None:
    written = call(repo, "run", suite=str(repo / "suite_qa.py"), acknowledge_calls=2)
    assert written["tenant"] == "acme-bank"
    assert written["suite"] == "qa"
    assert written["key"]
    assert "2 calls to the target" in str(written["sentence"])
    stored = (repo / ".digline" / "acme-bank" / "runs" / "qa").glob("*.json")
    assert len(list(stored)) == 1


def test_a_suspended_case_is_not_counted(repo: Path) -> None:
    """It is never called, so announcing a figure that included it would be a
    figure nobody could reconcile with the invoice."""
    write_suite(repo, extra=', Case(id="parked", suspended="waiting on legal")')
    message = refusal(repo, "run", suite=str(repo / "suite_qa.py"))
    assert "2 calls to the target" in message


# --------------------------------------------------------------------------- #
# The shapes, against the CLI (ADR 0011 §4, §6)
# --------------------------------------------------------------------------- #


def test_compare_matches_the_cli_field_for_field(promoted: Path) -> None:
    """The anti-drift test, and the reason `digline.wire` exists."""
    key = run_key(promoted)
    done = cli(
        promoted,
        "compare",
        "--suite",
        "suite_qa.py",
        "--run",
        key,
        "--locale",
        "en",
        "--json",
        "full",
    )
    assert call(promoted, "compare", suite=str(promoted / "suite_qa.py"), run=key) == (
        json.loads(done.stdout)
    )


def test_diff_matches_the_cli_field_for_field(repo: Path) -> None:
    first, second = run_key(repo), run_key(repo)
    done = cli(
        repo,
        "diff",
        "--suite",
        "suite_qa.py",
        first,
        second,
        "--locale",
        "en",
        "--json",
        "full",
    )
    assert call(
        repo, "diff", suite=str(repo / "suite_qa.py"), run1=first, run2=second
    ) == json.loads(done.stdout)


def test_the_diff_carries_no_verdict(repo: Path) -> None:
    """Neither side was approved by anybody, so there is nothing to gate on."""
    first, second = run_key(repo), run_key(repo)
    payload = json.dumps(
        call(repo, "diff", suite=str(repo / "suite_qa.py"), run1=first, run2=second)
    )
    assert "worse" not in payload
    assert "exit_code" not in payload


def test_compare_carries_the_exit_code_the_cli_would_have_returned(
    promoted: Path,
) -> None:
    """There is no process to exit here, which is why it has to be a field."""
    write_suite(promoted, fr_score="0.2")
    key = run_key(promoted)
    done = cli(
        promoted, "compare", "--suite", "suite_qa.py", "--run", key, "--locale", "en"
    )
    payload = call(promoted, "compare", suite=str(promoted / "suite_qa.py"), run=key)
    assert payload["worse"] is True
    assert payload["exit_code"] == done.returncode == 1


def test_a_self_diff_is_refused(repo: Path) -> None:
    key = run_key(repo)
    message = refusal(
        repo, "diff", suite=str(repo / "suite_qa.py"), run1=key, run2="latest"
    )
    assert "tautology" in message


# --------------------------------------------------------------------------- #
# Reading (ADR 0011 §4, §5)
# --------------------------------------------------------------------------- #


def test_list_runs_is_newest_first_and_marks_the_baseline(promoted: Path) -> None:
    newest = run_key(promoted)
    listing = call(promoted, "list_runs", suite=str(promoted / "suite_qa.py"))
    runs = listing["runs"]
    assert isinstance(runs, list)
    assert runs[0]["key"] == newest
    assert listing["baseline_key"] not in (None, newest)
    assert listing["note"] == ""
    assert listing["unreadable"] == 0


def test_get_run_resolves_latest_and_names_the_key(repo: Path) -> None:
    key = run_key(repo)
    document = call(repo, "get_run", suite=str(repo / "suite_qa.py"))
    assert document["key"] == key
    assert document["tenant"] == "acme-bank"


def test_get_baseline_refuses_before_there_is_one(repo: Path) -> None:
    """Not an error: the first round has no reference, and what it needs is a
    person. The one place `promote` appears on this surface is here, as
    instructions for one."""
    message = refusal(repo, "get_baseline", suite=str(repo / "suite_qa.py"))
    assert "has no baseline" in message
    assert "digline promote" in message


def test_the_judges_reason_never_crosses(repo: Path) -> None:
    """The fixture's judge writes its reason as "judged: <the prompt>", so a
    reason that survived would carry the input with it."""
    run_key(repo)
    document = json.dumps(call(repo, "get_run", suite=str(repo / "suite_qa.py")))
    assert "judged:" not in document
    assert '"reason"' not in document


def test_a_disclosed_metadata_key_still_travels(repo: Path) -> None:
    """The positive half: the fixture discloses `model`, so it must arrive."""
    cli(repo, "run", "--suite", "suite_qa.py", "--meta", "model=claude-opus-5")
    document = call(repo, "get_run", suite=str(repo / "suite_qa.py"))
    assert document["metadata"] == {"model": "claude-opus-5"}


def test_an_undisclosed_metadata_key_does_not(repo: Path) -> None:
    cli(
        repo,
        "run",
        "--suite",
        "suite_qa.py",
        "--meta",
        "model=claude-opus-5",
        "--meta",
        "customer=Banca Rossi",
    )
    document = call(repo, "get_run", suite=str(repo / "suite_qa.py"))
    assert "Rossi" not in json.dumps(document)


# --------------------------------------------------------------------------- #
# The perimeter (ADR 0011 §8)
# --------------------------------------------------------------------------- #


def test_the_tenant_verifies_and_never_overrides(repo: Path) -> None:
    run_key(repo)

    async def go() -> str:
        server = build_server(str(repo), "somebody-else", None)
        with pytest.raises(ToolError) as caught:
            await server.call_tool("get_run", {"suite": str(repo / "suite_qa.py")})
        return str(caught.value)

    message = anyio.run(go)
    assert "does not match the suite" in message
    assert "The suite decides" in message


def test_run_matches_the_cli_field_for_field(repo: Path) -> None:
    """The third of the three reused shapes, and the one that is easiest to
    forget: it is four keys, so it looks too small to drift."""
    suite = str(repo / "suite_qa.py")
    through_the_tool = call(repo, "run", suite=suite, acknowledge_calls=2)
    done = cli(repo, "run", "--suite", "suite_qa.py", "--json")
    through_the_cli = json.loads(done.stdout)
    # The keys are the contract; the run key itself differs because these are
    # two different runs, which is the only honest way to compare two writes.
    assert set(through_the_tool) == set(through_the_cli)
    assert through_the_tool["tenant"] == through_the_cli["tenant"]
    assert through_the_tool["suite"] == through_the_cli["suite"]
    assert through_the_tool["sentence"] == through_the_cli["sentence"]
    assert through_the_tool["output_version"] == through_the_cli["output_version"]


def test_list_runs_reports_what_it_could_not_read(repo: Path) -> None:
    """A stored history outlives the schema that wrote it. Over MCP there is no
    stderr, so a listing that quietly dropped half a suite would read exactly
    like a suite with a shorter history — and `AGENTS.md` §8 tells a reader to
    propose a migration, which needs a field to propose from."""
    run_key(repo)
    stored = next((repo / ".digline").rglob("runs/qa/*.json"))
    document = json.loads(stored.read_text(encoding="utf-8"))
    document["schema_version"] = 2  # a schema this version cannot read
    stored.write_text(json.dumps(document), encoding="utf-8")

    listing = call(repo, "list_runs", suite=str(repo / "suite_qa.py"))
    assert listing["runs"] == []
    assert listing["skipped"] == {"2": 1}
    assert "1 run(s) at schema 2" in str(listing["note"])
    assert listing["unreadable"] == 0
