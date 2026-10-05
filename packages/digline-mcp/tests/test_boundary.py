"""No response from any tool carries the payload. All eight, not just the two.

`tests/test_wire_boundary.py` in the root suite holds this line for the shapes
in isolation. This holds it for the **surface**: the tools as a client calls
them, over a suite whose every payload-bearing field carries a distinct marker.

Both exist because they fail differently. The wire test catches a projection
that emits too much; this one catches a *tool* that reaches around the
projection — a response assembled by hand, a field appended after the fact, a
future ninth tool that forgets. ADR 0011 §5: "It runs over all six tools and
not only the two that return runs, because the point is the boundary and not the
function." Six became eight with ADR 0020, and the sentence holds for all of them.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import anyio
import pytest
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import CallToolResult
from tests._helpers import baseline_in, cli, git

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
    cli(
        tmp_path,
        "promote",
        "--replacing",
        baseline_in(tmp_path),
        "--suite",
        "suite_qa.py",
        "--run",
        first,
    )
    second = cli(
        tmp_path, "run", "--suite", "suite_qa.py", "--meta", f"customer={RUN_META}"
    ).stdout.strip()
    # A disposition in the register, so `log` crosses the boundary carrying one:
    # the register is the one ledger the wire learns the name of (ADR 0021 §8).
    cli(
        tmp_path,
        "register",
        "--suite",
        "suite_qa.py",
        "--run",
        second,
        "--disposition",
        "rejected",
    )
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
        ("log", {"suite": suite}),
        ("compare", {"suite": suite, "run": "latest"}),
        ("diff", {"suite": suite, "run1": keys[0], "run2": keys[1]}),
        ("explain", {"suite": suite, "run": "latest"}),
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
    assert '"facts"' in answers["explain"]
    assert '"spans"' in answers["log"]
    assert '"disposition"' in answers["log"]
    assert "acknowledge_calls=" in answers["run"]


# --------------------------------------------------------------------------- #
# The refusals: every path where code digline did not write can raise
# --------------------------------------------------------------------------- #

#: Where the marker sits in each suite below: a case's `vars`, the data. Shaped
#: like an identifier on purpose, so the one builtin path that can quote a name
#: (§6, amended) can quote this one.
ROW = f'{{"iban": "{CASE_VAR}"}}'

_HEAD = f"""
import sys

from digline.core import Contains, RefusedError
from digline.host import UsageError
from digline.run import Case, Response, Suite

ROW = {ROW}
suite = Suite(
    tenant="acme-bank",
    environment="staging",
    name="qa",
    assertions=[Contains(needle="Rome")],
    cases=[Case(id="one", vars=ROW)],
)
"""

_TARGET = """
def target(case):
    return Response(output="Rome", input="q", cost_usd=0.0, latency_ms=1.0)
"""

#: ADR 0043 §4's first table, a row at a time, plus the site §6's amendment
#: found. Each is a suite whose code, or code a tool runs, raises with the case
#: in reach, and the tool that reaches it. The dotted form of the loader's rule
#: 3 and of its `ImportError` is not here: `within_root` refuses a dotted spec,
#: so no tool can reach it, and the command line is its only recipient.
CLASS: dict[str, tuple[str, str]] = {
    "rule 3, the file form": (
        _HEAD + "raise ValueError(f'cannot parse {ROW}')\n",
        "list_runs",
    ),
    "a SystemExit code while loading": (
        _HEAD + "sys.exit(f'bad row {ROW}')\n",
        "list_runs",
    ),
    "refused_exit, during run": (
        _HEAD + "def target(case):\n    sys.exit(f'bad row {case.vars}')\n",
        "run",
    ),
    "an ImportError's text": (
        _HEAD + "raise ImportError(f'no adapter for {ROW}')\n",
        "list_runs",
    ),
    "a RefusedError the suite raises while loading": (
        _HEAD + "raise RefusedError(f'refused {ROW}')\n",
        "list_runs",
    ),
    "a UsageError the suite raises while loading": (
        _HEAD + "raise UsageError(f'refused {ROW}')\n",
        "list_runs",
    ),
    "a refusal raised by a preflight": (
        _HEAD
        + _TARGET
        + "def _preflight(cases):\n"
        + "    raise RefusedError(f'not up for {cases[-1].vars}')\n"
        + "target.preflight = _preflight\n",
        "run",
    ),
    "a refusal raised by a target's config": (
        _HEAD
        + "class Target:\n"
        + "    @property\n"
        + "    def config(self):\n"
        + "        raise RefusedError(f'no config for {ROW}')\n"
        + "    def __call__(self, case):\n"
        + "        return Response(output='Rome', input='q', cost_usd=0.0,\n"
        + "                        latency_ms=1.0)\n"
        + "target = Target()\n",
        "run",
    ),
    "a SyntaxError from compile(), a builtin (§6)": (
        _HEAD.replace("vars=ROW)", f"vars=dict({CASE_VAR}=1, {CASE_VAR}=2))"),
        "list_runs",
    ),
}


def _refused(root: Path, tool: str, suite: str) -> str:
    """The `ToolError`'s text, through the acknowledgement for `run`: the
    first call is refused with the count, and the second types it back."""

    async def go() -> str:
        server = build_server(str(root), None, None)
        arguments: dict[str, Any] = {"suite": suite}
        for _ in range(2):
            try:
                await server.call_tool(tool, arguments)
            except ToolError as refusal:
                said = str(refusal)
                if "acknowledge_calls=" in said and "acknowledge_calls" not in (
                    arguments
                ):
                    count = said.split("acknowledge_calls=")[1].split(" ")[0]
                    arguments["acknowledge_calls"] = int(count)
                    continue
                return said
            pytest.fail(f"{tool} answered over a suite that raises")
        pytest.fail(f"{tool} kept asking for the count")

    return anyio.run(go)


@pytest.fixture
def raising(tmp_path: Path, request: pytest.FixtureRequest) -> tuple[Path, str]:
    source, tool = CLASS[request.param]
    git(tmp_path, "init", "-q")
    (tmp_path / "suite_raises.py").write_text(source, encoding="utf-8")
    return tmp_path, tool


@pytest.mark.parametrize("raising", list(CLASS), indirect=True)
def test_no_refusal_carries_the_case_to_the_agent(raising: tuple[Path, str]) -> None:
    """ADR 0043 §7: the marker in `vars`, every member of the class provoked
    through a tool, and the marker absent from the `ToolError`'s text. A
    message digline did not write is payload, and it reaches the person who ran
    the command and no other recipient. (#445)"""
    root, tool = raising
    said = _refused(root, tool, str(root / "suite_raises.py"))
    assert CASE_VAR not in said, (
        f"the case crossed the boundary in a refusal from {tool!r}: {said}"
    )
    # Refused in words, not crashed: the SDK's crash string would satisfy the
    # line above for every path and prove nothing.
    assert "Error executing tool" not in said.removeprefix(
        f"Error executing tool {tool}: "
    ), said


@pytest.mark.parametrize("raising", list(CLASS), indirect=True)
def test_the_command_line_shows_what_the_agent_does_not(
    raising: tuple[Path, str],
) -> None:
    """The control, path by path. A gate that drives no path where the marker
    could appear passes vacuously: each path above is one where the marker
    **is** in the refusal, which the command line, for the person who ran it,
    prints whole. (ADR 0043 §3, §7)"""
    root, _tool = raising
    done = cli(root, "run", "--suite", "suite_raises.py")
    assert done.returncode == 64, done.stderr
    assert CASE_VAR in done.stderr, done.stderr
