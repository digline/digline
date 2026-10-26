"""`tools/plugin_calls.py`: the names a plugin reaches for in digline, read by
the type of what it reaches into, and not by the name alone (#702).

The two assertions are the scan's control, kept as a guard. The positive one
finds what is known to be there. The negative one does not find `append`,
which a reading by name took from every `list` for `Journal.append`: put back
to counting by name, the scan still finds the control, and `append` comes
back. That second assertion is what tells the two readings apart.

The unresolved receivers are counted, because an unresolved receiver is not
measured, never not present: a new one is a place the list may be short.
"""

from __future__ import annotations

import importlib.util
import sys
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

_spec = importlib.util.spec_from_file_location(
    "plugin_calls", ROOT / "tools" / "plugin_calls.py"
)
assert _spec is not None and _spec.loader is not None
tool = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = tool
_spec.loader.exec_module(tool)


@pytest.fixture(scope="module")
def scanned() -> tuple[Counter[tuple[str, str, str]], list[str]]:
    return tool.scan()


def test_the_control_is_found_at_its_import_and_its_call(
    scanned: tuple[Counter[tuple[str, str, str]], list[str]],
) -> None:
    found, _ = scanned
    assert found[("pytest-digline", "import", "refuse_unreadable_baseline")] == 2


def test_append_is_found_nowhere(
    scanned: tuple[Counter[tuple[str, str, str]], list[str]],
) -> None:
    """Every `.append` in the plugins is on a list. A reading by name counts
    them as `Journal.append`'s."""
    found, _ = scanned
    assert [key for key in found if key[2] == "append"] == []


def test_the_unresolved_receivers_are_six_replies_of_the_sdk(
    scanned: tuple[Counter[tuple[str, str, str]], list[str]],
) -> None:
    """Six, each a reply of the Anthropic SDK, which pyright types `Any`. A
    seventh was `pytest_digline/plugin.py`'s `loaded`, annotated `Any` where
    digline's `Loaded` is the type: annotated, its `modules_unchecked` is
    counted."""
    found, unresolved = scanned
    assert len(unresolved) == 6, "\n".join(unresolved)
    assert all(
        line.startswith("packages/digline-anthropic/src/digline_anthropic/client.py:")
        for line in unresolved
    ), "\n".join(unresolved)
    assert found[("pytest-digline", "attribute", "modules_unchecked")] == 1
