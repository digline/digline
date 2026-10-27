"""`tools/contract_diff.py`: the JSON contract as it stands, diffed between two
references, with nothing to choose (#709).

The contract is assembled from three tables, `_BASE`, `_ADDED` and
`_ADDED_WORDS`, and a bump of `OUTPUT_VERSION` folds the last two into the
first. A diff of one table therefore depends on whether a fold happened in
between. The tool diffs what `_lines(_SHAPES)` derives from all three, in each
tree, so a fold changes nothing it reads.

The acceptance measurement, v0.33.0 against v0.34.0, needs both tags, and the
`gates` job checks out none. It is in the pull request that added the tool; what
runs here is the diff itself and a reference against itself.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from tests._helpers import git

ROOT = Path(__file__).resolve().parents[1]

_spec = importlib.util.spec_from_file_location(
    "contract_diff", ROOT / "tools" / "contract_diff.py"
)
assert _spec is not None and _spec.loader is not None
tool = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = tool
_spec.loader.exec_module(tool)


def test_a_key_added_removed_and_retyped_are_each_named() -> None:
    then = [
        "run.key: string",
        "run.sentence: string",
        "run_document.case.case_id: string",
    ]
    now = [
        "run.errored_checks: integer",
        "run.key: string",
        "run_document.case.case_id: string | null",
    ]
    # In name order, as the tool prints: `run.sentence` sorts before
    # `run_document...`, `.` before `_`.
    assert tool.diff(then, now) == [
        "added    run.errored_checks: integer",
        "removed  run.sentence: string",
        "changed  run_document.case.case_id: string -> string | null",
    ]


def test_a_key_that_became_optional_is_a_change() -> None:
    """`?` marks an optional key: a key that may now be absent is a change a
    reader of the contract has to know about, though its type did not move."""
    assert tool.diff(["run.usage: object"], ["run.usage?: object"]) == [
        "changed  run.usage: object -> run.usage?: object"
    ]


def test_the_same_lines_diff_to_nothing() -> None:
    lines = ["run.key: string", "run.usage?: object"]
    assert tool.diff(lines, list(reversed(lines))) == []


def test_a_reference_against_itself_is_empty() -> None:
    """The control, on real trees: the contract `HEAD` derives, read twice, from
    two copies of the tree, moves nowhere. A tool that diffed anything else, or
    read one tree's table into the other, would print something here."""
    lines = tool.contract_at("HEAD", ROOT)
    assert len(lines) > 100, "the contract read is too small to be the contract"
    assert tool.diff(lines, tool.contract_at("HEAD", ROOT)) == []


def test_what_it_reads_is_the_derived_contract_and_not_a_table() -> None:
    """The point of the tool: it reads `_lines(_SHAPES)`, the contract as it
    stands, and not `_BASE`, `_ADDED` or `_ADDED_WORDS`, which are how the
    contract is assembled. (#709)

    On this tree that tells nothing apart right after a bump: the fold empties
    `_ADDED` and `_ADDED_WORDS`, and `_BASE` is then `_SHAPES`. The test below
    is the one that does, on a tree where they differ."""
    from digline.wire.contract import (
        _SHAPES,  # pyright: ignore[reportPrivateUsage]
        _lines,  # pyright: ignore[reportPrivateUsage]
    )

    assert tool.contract_at("HEAD", ROOT) == _lines(_SHAPES)


def test_it_reads_the_shapes_where_the_base_differs(tmp_path: Path) -> None:
    """A tree whose `_BASE` and `_SHAPES` differ, as they do whenever `_ADDED`
    holds a key: the tool reads `_SHAPES`. Written for the bump to 4 (#678),
    which emptied `_ADDED` and left the test above unable to tell the two
    apart."""
    wire = tmp_path / "src" / "digline" / "wire"
    wire.mkdir(parents=True)
    (tmp_path / "src" / "digline" / "__init__.py").write_text("")
    (wire / "__init__.py").write_text("")
    (wire / "contract.py").write_text(
        "_BASE = ['run.key: string']\n"
        "_SHAPES = ['run.key: string', 'run.added: integer']\n"
        "def _lines(shapes):\n"
        "    return list(shapes)\n"
    )
    git(tmp_path, "init", "-q")
    git(tmp_path, "add", "src")
    git(
        tmp_path,
        "-c",
        "user.name=t",
        "-c",
        "user.email=t@example.com",
        "commit",
        "-q",
        "-m",
        "a tree",
    )
    assert tool.contract_at("HEAD", tmp_path) == [
        "run.key: string",
        "run.added: integer",
    ]
