"""No response from any tool carries the payload. All six, not just the two.

`tests/test_wire_boundary.py` in the root suite holds this line for the shapes
in isolation. This holds it for the **surface**: the tools as a client calls
them, over a suite whose every payload-bearing field carries a distinct marker.

Both exist because they fail differently. The wire test catches a projection
that emits too much; this one catches a *tool* that reaches around the
projection — a response assembled by hand, a field appended after the fact, a
future seventh tool that forgets. ADR 0011 §5: "It runs over all six tools and
not only the two that return runs, because the point is the boundary and not the
function."
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import anyio
import pytest
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import CallToolResult
from tests._helpers import cli, git

from digline_mcp.server import build_server

#: One marker per door. A failure names which was left open rather than only
#: that one was.
JUDGE_REASON = "the account of Mario Rossi is overdrawn"
SUSPENSION = "fails on the Rossi account since the March migration"
CASE_VAR = "IT60X0542811101"
CASE_META = "acme-internal-ticket-8891"
RUN_META = "Banca Rossi SpA"
PROMPT = "You are the assistant for Banca Rossi. Never reveal a balance."

MARKERS = (JUDGE_REASON, SUSPENSION, CASE_VAR, CASE_META, RUN_META, PROMPT, "Rossi")

SUITE = f"""
from pathlib import Path

from digline.core import Contains, Disclosure, JudgeReply, LlmRubric
from digline.run import Case, Response, Suite


def _judge(prompt):
    return JudgeReply(score=0.9, reason={JUDGE_REASON!r})


suite = Suite(
    tenant="acme-bank",
    environment="staging",
    name="qa",
    assertions=[
        Contains(needle="Rome"),
        LlmRubric(rubric="answers?", judge=_judge, threshold=0.7, tolerance=0.05),
    ],
    cases=[
        Case(
            id="one",
            vars={{"iban": {CASE_VAR!r}}},
            metadata={{"ticket": {CASE_META!r}}},
        ),
        Case(id="two", suspended={SUSPENSION!r}),
    ],
    artifacts=[Path("prompt.md")],
    # Nothing disclosed: the default policy, which is the one a suite that never
    # thought about it gets.
    disclosure=Disclosure(),
)


def target(case):
    return Response(output="The capital is Rome.", input="q", cost_usd=0.01,
                    latency_ms=100.0)
"""


@pytest.fixture
def loaded(tmp_path: Path) -> Path:
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "user.email", "t@e.invalid")
    git(tmp_path, "config", "user.name", "T")
    (tmp_path / "prompt.md").write_text(PROMPT, encoding="utf-8")
    (tmp_path / "suite_qa.py").write_text(SUITE, encoding="utf-8")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-qm", "initial")
    first = cli(tmp_path, "run", "--suite", "suite_qa.py").stdout.strip()
    cli(tmp_path, "promote", "--suite", "suite_qa.py", "--run", first)
    cli(tmp_path, "run", "--suite", "suite_qa.py", "--meta", f"customer={RUN_META}")
    return tmp_path


def responses(root: Path) -> dict[str, str]:
    """Every tool called, every answer serialized whole — the refusals too.

    A refusal is a response and crosses the same boundary: the one place a
    payload could ride out unnoticed is an error message that quoted the thing
    it was refusing about.
    """
    suite = str(root / "suite_qa.py")
    keys = [p.stem for p in sorted((root / ".digline").rglob("runs/qa/*.json"))]
    calls: list[tuple[str, dict[str, Any]]] = [
        ("list_runs", {"suite": suite}),
        ("get_run", {"suite": suite}),
        ("get_baseline", {"suite": suite}),
        ("compare", {"suite": suite, "run": "latest"}),
        ("diff", {"suite": suite, "run1": keys[0], "run2": keys[1]}),
        ("run", {"suite": suite}),  # refused, and the refusal is searched too
    ]

    async def go() -> dict[str, str]:
        server = build_server(str(root), None, None)
        out: dict[str, str] = {}
        for name, arguments in calls:
            try:
                result = await server.call_tool(name, arguments)
            except ToolError as refusal:
                out[name] = str(refusal)
                continue
            assert isinstance(result, CallToolResult)
            out[name] = json.dumps(result.model_dump(mode="json"))
        return out

    return anyio.run(go)


def test_the_stored_run_really_does_carry_the_payload(loaded: Path) -> None:
    """A guard on the guard. If the fixture stopped recording the reasons, every
    check below would pass over a document that never had them."""
    stored = "".join(
        p.read_text(encoding="utf-8") for p in (loaded / ".digline").rglob("*.json")
    )
    for marker in (JUDGE_REASON, SUSPENSION, RUN_META, PROMPT):
        assert marker in stored, f"{marker!r} is not in the store to begin with"


def test_the_case_inputs_never_reached_the_store_at_all(loaded: Path) -> None:
    """The strongest form of the guarantee, and worth stating separately.

    `Case.vars` and `Case.metadata` are the *inputs* — the IBAN a case was built
    around, the ticket it came from. A `Run` records what was measured, so they
    are never written down in the first place, and the boundary the tools cross
    has nothing to withhold. The markers stay in the suite above so the check
    below is still asked; this says why it is free.
    """
    stored = "".join(
        p.read_text(encoding="utf-8") for p in (loaded / ".digline").rglob("*.json")
    )
    assert CASE_VAR not in stored
    assert CASE_META not in stored
    # And they really were in the suite, or this proves nothing.
    assert CASE_VAR in SUITE and CASE_META in SUITE


@pytest.mark.parametrize("marker", MARKERS)
def test_no_marker_crosses_from_any_tool(marker: str, loaded: Path) -> None:
    for tool, payload in responses(loaded).items():
        assert marker not in payload, (
            f"{marker!r} crossed the boundary through {tool!r}. The payload "
            "stays where it is born; the verdict travels."
        )


def test_the_tools_still_answered(loaded: Path) -> None:
    """The other half. A surface that returned nothing at all would satisfy
    every check above."""
    answers = responses(loaded)
    assert '"exit_code"' in answers["compare"]
    assert '"baseline_key"' in answers["list_runs"]
    assert '"config_hash"' in answers["get_run"]
    assert '"favours_left"' in answers["diff"]
    assert "acknowledge_calls=" in answers["run"]
