"""`tools/name_pass.py`: the pass over the names digline gives one thing in
different places, and the one name it gives different things.

The two assertions on the values pass are its controls, kept as a guard. The
positive one is the instance known before the pass was written, #678: a
verdict's check is `assertion` in the run file and `name` in `get_run`, and the
pass finds it by itself. The negative one is two names known to be coherent,
`case_id` and `assertion_id`, which every document spells the same way and
which must not be listed. Reading by the whole path instead of the holding key
lists them, and that is what tells a candidate from a field met in two places.

The static and the textual pass carry one control each, on an instance this
tree holds.
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


@pytest.mark.parametrize("value", ["levenshtein", "accuracy[group=till]"])
def test_the_values_pass_finds_the_check_under_assertion_and_name(
    shared: dict[str, frozenset[str]], value: str
) -> None:
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


def test_the_textual_pass_finds_a_deferral_across_a_line_break() -> None:
    """Both notes wrap: the first grep of the pass missed the one on
    `answered`, because it read a line at a time."""
    found = {(place.path, place.line) for place in tool.deferred(ROOT)}
    paths = {path for path, _ in found}
    assert "src/digline/wire/log.py" in paths, sorted(found)
    assert "packages/digline-mcp/src/digline_mcp/server.py" in paths, sorted(found)
