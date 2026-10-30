"""Why a cost is not known, on the `run` tool. (ADR 0004 §8.0, item 2)

`digline run --json` carries the sentences a plugin wrote for a cost it could
not compute, as `unpriced`. The tool now carries the same key, rendered by the
same `run_json` (ADR 0011 §6), in the three states the core gives it:

- empty, where the run looked and nobody said why;
- the sentences as given, where the answer is read in clear;
- under `--names project`, each sentence withheld whole as
  `WITHHELD_WORDS["cost_reason"]`, the list keeping its length. A sentence is a
  plugin's free text, which names a model and which nothing mints.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import anyio
from mcp.types import CallToolResult
from tests._helpers import cli

from digline.core import WITHHELD_WORDS
from digline_mcp.descriptions import DESCRIPTIONS
from digline_mcp.server import Names, build_server

#: What a plugin says when the reply's geography has no price: it names the
#: model, which is why it may not cross under `project`.
GEO = "claude-haiku-4-5 replied from inference_geo 'not_available', which has no price"

UNPRICED = f"""
from digline.core import Contains
from digline.run import Case, Response, Suite

suite = Suite(
    tenant="acme-bank",
    environment="staging",
    name="unpriced",
    assertions=[Contains(needle="Paris")],
    cases=[Case(id="a"), Case(id="b")],
)


def target(case):
    return Response(output="Paris", cost_usd=None, unpriced={GEO!r})
"""


def run_tool(
    repo: Path, suite: str, *, names: Names, table: Any = None
) -> dict[str, Any]:
    async def go() -> dict[str, Any]:
        server = build_server(str(repo), None, None, names=names, table=table)
        result = await server.call_tool(
            "run", {"suite": str(repo / suite), "acknowledge_calls": 2}
        )
        assert isinstance(result, CallToolResult)
        assert result.structured_content is not None
        return dict(result.structured_content)

    return anyio.run(go)


def test_in_clear_the_tool_carries_the_sentences_the_cli_carries(repo: Path) -> None:
    (repo / "suite_unpriced.py").write_text(UNPRICED, encoding="utf-8")
    through_the_tool = run_tool(repo, "suite_unpriced.py", names="clear")
    done = cli(repo, "run", "--suite", "suite_unpriced.py", "--json")
    through_the_cli = json.loads(done.stdout)
    assert through_the_tool["unpriced"] == [GEO], through_the_tool
    assert through_the_tool["unpriced"] == through_the_cli["unpriced"]


def test_under_project_each_sentence_is_withheld_and_counted(repo: Path) -> None:
    """The sentence names a model and nothing mints it, so it does not cross;
    that a reason exists, and how many, does."""
    from _names import RecordingTable

    (repo / "suite_unpriced.py").write_text(UNPRICED, encoding="utf-8")
    answer = run_tool(
        repo, "suite_unpriced.py", names="project", table=RecordingTable()
    )
    assert answer["unpriced"] == [WITHHELD_WORDS["cost_reason"]], answer
    assert GEO not in json.dumps(answer)
    assert "claude-haiku-4-5" not in json.dumps(answer)


def test_a_run_whose_every_cost_is_known_carries_an_empty_list(repo: Path) -> None:
    """The control, and the reason the key is always there: an empty list is a
    run that looked and was given no sentence, not a tool that did not look."""
    answer = run_tool(repo, "suite_qa.py", names="clear")
    assert answer["unpriced"] == [], answer


def test_the_description_says_what_unpriced_is() -> None:
    text = " ".join(DESCRIPTIONS["run"].split())
    assert "`unpriced` holds why a cost is not known" in text
    assert "withheld" in text
