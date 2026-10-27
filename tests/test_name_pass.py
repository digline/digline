"""`tools/name_pass.py`: the pass over the names digline gives one thing in
different places, and the one name it gives different things.

The two assertions on the values pass are its controls, kept as a guard.

**The positive one is fixed here, and does not read the code.** It is the
instance known before the pass was written, #678: a verdict's check was
`assertion` in the run file and `name` in `get_run`, and the pass finds it by
itself in the two documents as digline wrote them before `OUTPUT_VERSION` 4.
It was first written over the live fixture, and #757 renamed `name` away and
turned it red. **A positive control that depends on the defect falls silent
when the defect is repaired, which is when it is needed most**: from then on
it would say nothing about whether the pass can still find one.

**The negative one reads the live fixture**: `case_id` and `assertion_id`,
which every document spells the same way, must not be listed. Reading by the
whole path instead of the holding key lists them, and that is what tells a
candidate from a field met in two places.

The textual pass has its control on a paragraph written here, broken across
lines, and on ADR 0020's note on `answered`, which stays as the record of a
rename deferred. The static pass has its control on an instance this tree
holds.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]

_spec = importlib.util.spec_from_file_location(
    "name_pass", ROOT / "tools" / "name_pass.py"
)
assert _spec is not None and _spec.loader is not None
tool = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = tool
_spec.loader.exec_module(tool)


@pytest.fixture(scope="module")
def found(tmp_path_factory: pytest.TempPathFactory) -> list[Any]:
    return tool.fixture_strings(tmp_path_factory.mktemp("name-pass"))


@pytest.fixture(scope="module")
def shared(found: list[Any]) -> dict[str, frozenset[str]]:
    return {item.value: item.keys for item in tool.shared_values(found)}


#: One verdict and one group's aggregate, in the run file and in `get_run`'s
#: answer, as digline wrote them before `OUTPUT_VERSION` 4: the keys and the
#: values measured on `208b1dd5`, the last `main` before #757, with the gate's
#: fixture, and every other key left out.
BEFORE_THE_BUMP: dict[str, dict[str, Any]] = {
    "run_document": {
        "results": [
            {
                "case_id": "gift-wrap",
                "verdicts": [{"assertion": "levenshtein"}],
            }
        ],
        "aggregate": [{"assertion": "accuracy[group=till]"}],
    },
    "mcp:get_run": {
        "results": [
            {
                "case_id": "gift-wrap",
                "verdicts": [{"name": "levenshtein"}],
            }
        ],
        "aggregate": [{"name": "accuracy[group=till]"}],
    },
}


@pytest.mark.parametrize("value", ["levenshtein", "accuracy[group=till]"])
def test_the_values_pass_finds_the_check_under_assertion_and_name(value: str) -> None:
    found = [
        item
        for source, document in BEFORE_THE_BUMP.items()
        for item in tool.document_strings(source, document)
    ]
    shared = {item.value: item.keys for item in tool.shared_values(found)}
    assert value in shared, sorted(shared)
    assert {"assertion", "name"} <= shared[value], shared[value]


@pytest.mark.parametrize("key", ["case_id", "assertion_id"])
def test_the_values_pass_does_not_list_a_name_every_document_shares(
    found: list[Any], shared: dict[str, frozenset[str]], key: str
) -> None:
    """Held at several paths in several sources, so a reading by the whole path
    would list it; held under one key, so this one does not."""
    held = [item for item in found if item.path.endswith(f".{key}")]
    paths = {item.path for item in held}
    sources = {item.source for item in held}
    assert len(paths) > 1 and len(sources) > 1, (paths, sources)
    listed = sorted(value for value, keys in shared.items() if key in keys)
    assert not listed, f"{key} is listed for {listed}"


def test_the_static_pass_finds_a_key_whose_types_differ() -> None:
    """`samples` is a count in an interval and a list of scores in a verdict."""
    collisions = tool.typed_collisions(tool.contract_lines())
    assert {
        ("interval.samples", "integer"),
        ("run_document.verdict.samples", "[number]"),
    } <= set(collisions["samples"])
    assert "case_id" not in collisions


def test_the_textual_pass_finds_a_deferral_across_a_line_break(
    tmp_path: Path,
) -> None:
    """The first grep of the pass missed the note on `answered`, because it read
    a line at a time and the sentence wraps. Each sentence here wraps too."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "wire.py").write_text(
        "def answer() -> dict[str, str]:\n"
        "    # The key stays as it is, because renaming it is an\n"
        "    # `OUTPUT_VERSION` bump for a word.\n"
        '    return {"key": "value"}\n',
        encoding="utf-8",
    )
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "record.md").write_text(
        "Kept because a client reads it: removing a key is a change,\n"
        "and it waits for a bump.\n",
        encoding="utf-8",
    )
    found = {(place.path, place.line) for place in tool.deferred(tmp_path)}
    assert found == {("src/wire.py", 2), ("docs/record.md", 1)}, sorted(found)
    adr = "docs/adr/0020-the-reading-across-runs.md"
    assert adr in {place.path for place in tool.deferred(ROOT)}


def test_the_values_pass_reads_a_journal(found: list[Any]) -> None:
    """A finished run leaves none, so the pass has the store write one: the
    check is `assertion` there too."""
    assert any(
        item.source == "journal"
        and item.path == "$.case.verdicts[].assertion"
        and item.value == "levenshtein"
        for item in found
    )
