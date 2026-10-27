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
from tests.test_plugin_floors import CALLED, UNDATED

ROOT = Path(__file__).resolve().parents[1]

_spec = importlib.util.spec_from_file_location(
    "plugin_calls", ROOT / "tools" / "plugin_calls.py"
)
assert _spec is not None and _spec.loader is not None
tool = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = tool
_spec.loader.exec_module(tool)


Scanned = tuple[
    Counter[tuple[str, str, str]], list[str], Counter[tuple[str, str, str, str]]
]


@pytest.fixture(scope="module")
def scanned() -> Scanned:
    return tool.scan()


def test_the_control_is_found_at_its_import_and_its_call(
    scanned: Scanned,
) -> None:
    found, _, _ = scanned
    assert found[("pytest-digline", "import", "refuse_unreadable_baseline")] == 2


def test_append_is_found_nowhere(
    scanned: Scanned,
) -> None:
    """Every `.append` in the plugins is on a list. A reading by name counts
    them as `Journal.append`'s."""
    found, _, _ = scanned
    assert [key for key in found if key[2] == "append"] == []


def test_the_unresolved_receivers_are_six_replies_of_the_sdk(
    scanned: Scanned,
) -> None:
    """Six, each a reply of the Anthropic SDK, which pyright types `Any`. A
    seventh was `pytest_digline/plugin.py`'s `loaded`, annotated `Any` where
    digline's `Loaded` is the type: annotated, its `modules_unchecked` is
    counted."""
    found, unresolved, _ = scanned
    assert len(unresolved) == 6, "\n".join(unresolved)
    assert all(
        line.startswith("packages/digline-anthropic/src/digline_anthropic/client.py:")
        for line in unresolved
    ), "\n".join(unresolved)
    assert found[("pytest-digline", "attribute", "modules_unchecked")] == 1


def test_every_entry_the_scan_finds_is_dated_or_declared_undated(
    scanned: Scanned,
) -> None:
    """Each `(module, class, attribute)` a plugin reads on something digline
    gives it has a date in `CALLED`, or a reason in `UNDATED`: a level-2 public
    name the delta-pass cannot place is a name it cannot tell new from old.
    The six unresolved receivers are not entries: they are replies of an SDK,
    not names of digline's. (#702)"""
    _, _, defined = scanned
    found = {(module, cls, attr) for (_, module, cls, attr) in defined}
    missing = sorted(found - set(CALLED) - set(UNDATED))
    assert found, "the scan found no call at all; this would prove nothing"
    assert not missing, (
        f"plugins call {missing} and tests/test_plugin_floors.py dates none of "
        "them. Run `uv run python tools/plugin_call_dates.py` and add each to "
        "CALLED with the version it prints, or to UNDATED with its reason."
    )
