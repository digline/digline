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
from tests._tags import tags_absent
from tests.test_plugin_floors import CALLED, UNDATED, UNRELEASED

ROOT = Path(__file__).resolve().parents[1]

_spec = importlib.util.spec_from_file_location(
    "plugin_calls", ROOT / "tools" / "plugin_calls.py"
)
assert _spec is not None and _spec.loader is not None
tool = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = tool
_spec.loader.exec_module(tool)

_dates_spec = importlib.util.spec_from_file_location(
    "plugin_call_dates", ROOT / "tools" / "plugin_call_dates.py"
)
assert _dates_spec is not None and _dates_spec.loader is not None
dates = importlib.util.module_from_spec(_dates_spec)
sys.modules[_dates_spec.name] = dates
_dates_spec.loader.exec_module(dates)


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


def test_the_unresolved_receivers_are_five_replies_of_the_sdk(
    scanned: Scanned,
) -> None:
    """Five, each a reply of the Anthropic SDK, which pyright types `Any`. A
    seventh was `pytest_digline/plugin.py`'s `loaded`, annotated `Any` where
    digline's `Loaded` is the type: annotated, its `modules_unchecked` is
    counted. A sixth was `usage_of`'s `reply.usage`, read through `getattr`
    since #629, because a reply may carry no `usage` and that is now judged."""
    found, unresolved, _ = scanned
    assert len(unresolved) == 5, "\n".join(unresolved)
    assert all(
        line.startswith("packages/digline-anthropic/src/digline_anthropic/client.py:")
        for line in unresolved
    ), "\n".join(unresolved)
    assert found[("pytest-digline", "attribute", "modules_unchecked")] == 1


def test_every_entry_the_scan_finds_is_dated_unreleased_or_undated(
    scanned: Scanned,
) -> None:
    """Each `(module, class, attribute)` a plugin reads on something digline
    gives it has a date in `CALLED`, is declared in `UNRELEASED` as on `main`
    and in no tag yet, or has a reason in `UNDATED`: a level-2 public name the
    delta-pass cannot place is a name it cannot tell new from old. The five
    unresolved receivers are not entries: they are replies of an SDK, not
    names of digline's. (#702)"""
    _, _, defined = scanned
    found = {(module, cls, attr) for (_, module, cls, attr) in defined}
    missing = sorted(found - set(CALLED) - set(UNRELEASED) - set(UNDATED))
    assert found, "the scan found no call at all; this would prove nothing"
    assert not missing, (
        f"plugins call {missing} and tests/test_plugin_floors.py dates none of "
        "them. Run `uv run python tools/plugin_call_dates.py` and add each to "
        "CALLED with the version it prints, to UNRELEASED where it prints *in "
        "no release tag* for a name on main, or to UNDATED with its reason."
    )


def test_each_entry_is_in_one_table() -> None:
    """Dated, unreleased and undated are three answers, and a name gets one."""
    tables = (set(CALLED), set(UNRELEASED), set(UNDATED))
    twice = sorted(
        key for i, a in enumerate(tables) for b in tables[i + 1 :] for key in a & b
    )
    assert not twice, twice


def test_an_unreleased_entry_is_in_no_release_tag() -> None:
    """What makes `UNRELEASED` a state and not a place to park a name: each
    entry is in no tag. Once a release carries it, this fails until the cut
    moves it into `CALLED` with that release's number, so the table cannot
    stay full for ever without anybody noticing.

    It reads the tags, through `tools/plugin_call_dates.py`: skipped on a
    checkout without them, and an error in `ci.yml`'s `readers` job."""
    if not dates.release_tags():
        tags_absent(["v0.1.0"])
    released = [
        (entry, version or note)
        for entry, version, note in dates.date(sorted(UNRELEASED))
        if version is not None or note != "in no release tag"
    ]
    assert not released, (
        f"{released} are in UNRELEASED and a release tag carries them: move "
        "each into CALLED with the version `tools/plugin_call_dates.py` prints "
        "(RELEASING.md, *Before the tag: moving the number*)."
    )
