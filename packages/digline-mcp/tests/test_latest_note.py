"""The note `latest` leaves reaches the agent, on every tool that resolves a run.

Until #433 only the CLI said it, on stderr. Here the case that made it matter:
the baseline was promoted from the newest run and that run's file is gone, so
`latest` is an older run. `compare` then holds an older run against a newer
reference, and its `worse` is the past rather than a regression. Without the
note, the agent cannot tell.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import anyio
import pytest
from mcp.types import CallToolResult
from tests._helpers import baseline_in, cli, run_key

from digline_mcp.descriptions import DESCRIPTIONS
from digline_mcp.server import build_server


def call(root: Path, tool: str, **arguments: Any) -> dict[str, Any]:
    async def go() -> dict[str, Any]:
        result = await build_server(str(root), None, None).call_tool(tool, arguments)
        assert isinstance(result, CallToolResult)
        assert result.structured_content is not None
        return dict(result.structured_content)

    return anyio.run(go)


@pytest.fixture
def outrun(repo: Path) -> tuple[Path, str, str, str]:
    """Three runs, the newest promoted and then removed: `latest` is the middle
    one, and the baseline names a run nobody can read."""
    oldest, older, newer = run_key(repo), run_key(repo), run_key(repo)
    promoted = cli(
        repo,
        "promote",
        "--replacing",
        baseline_in(repo),
        "--suite",
        "suite_qa.py",
        "--run",
        newer,
    )
    assert promoted.returncode == 0, promoted.stderr
    (found,) = (repo / ".digline").glob(f"*/runs/**/{newer}.json")
    found.unlink()
    return repo, oldest, older, newer


def suite(root: Path) -> str:
    return str(root / "suite_qa.py")


def says_newer(note: str, *, newer: str, older: str) -> bool:
    return (
        f"the baseline was promoted from run {newer}, newer than {older}" in note
        and "not read here" in note
    )


def test_compare_carries_the_note_and_is_still_the_cli(
    outrun: tuple[Path, str, str, str],
) -> None:
    root, _oldest, older, newer = outrun
    done = cli(
        root,
        "compare",
        *("--suite", "suite_qa.py", "--run", "latest", "--locale", "en"),
        *("--json", "full"),
    )
    answered = call(root, "compare", suite=suite(root), run="latest")

    assert says_newer(answered["note"], newer=newer, older=older)
    assert answered == json.loads(done.stdout)
    # The terminal still says it, on stderr, in the same words.
    assert f"note: {answered['note']}" in done.stderr


def test_get_run_carries_it_and_get_baseline_does_not(
    outrun: tuple[Path, str, str, str],
) -> None:
    """A baseline is never resolved, so its document has no note at all: an
    empty one would claim a resolution that did not happen."""
    root, _oldest, older, newer = outrun
    document = call(root, "get_run", suite=suite(root), run="latest")
    assert document["key"] == older
    assert says_newer(document["note"], newer=newer, older=older)

    assert "note" not in call(root, "get_baseline", suite=suite(root))


def test_explain_carries_it_and_is_still_the_cli(
    outrun: tuple[Path, str, str, str],
) -> None:
    root, _oldest, older, newer = outrun
    done = cli(root, "explain", "--suite", "suite_qa.py", "--run", "latest", "--json")
    answered = call(root, "explain", suite=suite(root), run="latest")

    assert says_newer(answered["note"], newer=newer, older=older)
    assert answered.pop("key") == older
    assert answered == json.loads(done.stdout)


def test_diff_carries_one_note_per_side(outrun: tuple[Path, str, str, str]) -> None:
    root, oldest, older, newer = outrun
    done = cli(
        root,
        "diff",
        *("--suite", "suite_qa.py", oldest, "latest", "--locale", "en"),
        *("--json", "full"),
    )
    answered: dict[str, Any] = call(
        root, "diff", suite=suite(root), run1=oldest, run2="latest"
    )

    sides = answered["runs"]
    assert sides["left"]["note"] == ""
    assert says_newer(sides["right"]["note"], newer=newer, older=older)
    assert answered == json.loads(done.stdout)


def test_a_key_typed_by_hand_brings_an_empty_note(
    outrun: tuple[Path, str, str, str],
) -> None:
    """The note is about `latest`. Naming the same run by its key steps over
    nothing, and says so by saying nothing."""
    root, _oldest, older, _newer = outrun
    assert call(root, "compare", suite=suite(root), run=older)["note"] == ""
    assert call(root, "get_run", suite=suite(root), run=older)["note"] == ""
    assert call(root, "explain", suite=suite(root), run=older)["note"] == ""


@pytest.mark.parametrize("tool", ["get_run", "compare", "diff", "explain"])
def test_each_tool_that_resolves_a_run_says_what_the_note_is_for(tool: str) -> None:
    """The misuse the note invites is a new run to silence it, and it is said
    where the agent decides. `test_playbook.py` holds the phrase to AGENTS.md."""
    assert "make the note go away" in " ".join(DESCRIPTIONS[tool].split())
