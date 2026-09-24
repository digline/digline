"""Finding 5: the refusals that do not survive the SDK boundary.

`errors.TRANSLATED` lists the exceptions digline raises deliberately. `ValueError`
and `FileNotFoundError` are not among them, and they are what the store raises
for its two written refusals — `_check_name`'s illegal name and `_inside`'s
symlink out of the store. Both therefore reach the agent as the SDK's
`"Error executing tool <name>"`, with the sentence on stderr where no client
reads it.

**And the half that is about the test rather than the code.**
`test_tools.py::test_a_run_that_links_out_of_the_store_never_reaches_the_agent`
asserts `"exfiltrated" not in message`. That is vacuously true of the crash
string — and of a typo'd tool name, and of the empty string. The property it
names does hold; this file is what holds it, because a test that cannot fail for
the reason it names is not the thing keeping the boundary shut.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import anyio
import pytest
from mcp.server.mcpserver.exceptions import ToolError, UnexpectedToolError
from tests._helpers import run_key

from digline_mcp.server import build_server


def refusal(root: Path, tool: str, **arguments: Any) -> tuple[str, type[BaseException]]:
    async def go() -> tuple[str, type[BaseException]]:
        server = build_server(str(root), None, None)
        with pytest.raises(ToolError) as caught:
            await server.call_tool(tool, arguments)
        return str(caught.value), type(caught.value)

    return anyio.run(go)


def planted(repo: Path) -> Path:
    """A run file in the store that is a link to one outside it."""
    key = run_key(repo)
    stored = next((repo / ".digline").rglob(f"runs/qa/{key}.json"))
    outside = repo.parent / "linked.json"
    document = json.loads(stored.read_text(encoding="utf-8"))
    document["environment"] = "exfiltrated"
    outside.write_text(json.dumps(document), encoding="utf-8")
    (stored.parent / "planted-key.json").symlink_to(outside)
    return outside


def test_the_symlink_refusal_says_why_to_the_agent(repo: Path) -> None:
    """`_inside` writes a sentence naming the store and the path. An agent that
    is told only that something failed will retry, and retrying is the one
    response that cannot help here."""
    planted(repo)
    message, kind = refusal(
        repo, "get_run", suite=str(repo / "suite_qa.py"), run="planted-key"
    )

    # First the property the existing test names, kept: the linked-out document
    # does not reach the agent.
    assert "exfiltrated" not in message

    # Then the property that assertion cannot check on its own.
    assert kind is not UnexpectedToolError, (
        f"the store's symlink refusal reached the agent as an untranslated "
        f"crash ({kind.__name__}: {message!r}). `ValueError` is not in "
        "`errors.TRANSLATED`, so the sentence `_inside` wrote is on stderr only."
    )
    assert "outside" in message, f"the refusal does not say what was wrong: {message!r}"


def test_an_illegal_run_key_is_refused_in_words(repo: Path) -> None:
    """`_check_name` is the other written refusal on the same path."""
    run_key(repo)
    message, kind = refusal(
        repo, "get_run", suite=str(repo / "suite_qa.py"), run="../etc/passwd"
    )
    assert kind is not UnexpectedToolError, (
        f"an illegal run key crashed instead of being refused "
        f"({kind.__name__}: {message!r})"
    )


def test_a_missing_run_is_refused_in_words(repo: Path) -> None:
    """The ordinary case, and the one an agent meets first: a key that is
    well-formed and simply is not there."""
    run_key(repo)
    message, kind = refusal(
        repo,
        "get_run",
        suite=str(repo / "suite_qa.py"),
        run="2020-01-01T00-00-00-000000-00-00-abcdef",
    )
    assert kind is not UnexpectedToolError, (
        f"a missing run crashed instead of being refused "
        f"({kind.__name__}: {message!r}). `FileNotFoundError` is not in "
        "`errors.TRANSLATED`."
    )


def test_the_control_a_translated_refusal_arrives_whole(repo: Path) -> None:
    """The control for all three above.

    If the SDK stopped delivering any message at all, or `build_server` stopped
    reaching the store, the three tests above would fail for a reason that has
    nothing to do with `TRANSLATED`. This one passes today and says which.
    """
    message, kind = refusal(repo, "get_baseline", suite=str(repo / "suite_qa.py"))
    assert kind is ToolError, f"expected a translated refusal, got {kind.__name__}"
    assert "has no baseline" in message, message
    assert "digline promote" in message, (
        f"a translated refusal lost the remedy it names: {message!r}"
    )


def test_a_document_that_is_not_a_run_is_refused_in_words(repo: Path) -> None:
    """Finding 6's refusal, on this surface. Without a type of its own it would
    reach the agent as a crash — reopening, in the same release, the defect the
    store's two refusals were given types to close."""
    key = run_key(repo)
    stored = next((repo / ".digline").rglob(f"runs/qa/{key}.json"))
    stored.write_text("[1, 2]", encoding="utf-8")

    message, kind = refusal(repo, "get_run", suite=str(repo / "suite_qa.py"), run=key)
    assert kind is not UnexpectedToolError, (
        f"a malformed stored document crashed instead of being refused "
        f"({kind.__name__}: {message!r})"
    )
    assert "run" in message.lower(), message


def test_a_document_naming_another_suite_is_refused_in_words(repo: Path) -> None:
    """Finding 7's refusal, likewise: the document says one suite, the store
    filed it under another, and the agent is told which."""
    key = run_key(repo)
    stored = next((repo / ".digline").rglob(f"runs/qa/{key}.json"))
    stored.write_text(
        stored.read_text(encoding="utf-8").replace('"suite": "qa"', '"suite": "other"'),
        encoding="utf-8",
    )

    message, kind = refusal(repo, "get_run", suite=str(repo / "suite_qa.py"), run=key)
    assert kind is not UnexpectedToolError, (
        f"a suite mismatch crashed instead of being refused "
        f"({kind.__name__}: {message!r})"
    )
    assert "other" in message, message
