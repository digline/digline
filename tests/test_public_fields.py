"""`tools/public_fields.py`: the third kind of public surface, found by a
command. (RELEASING.md, *After the green, before the announcement*)

Written from the miss it exists for: on 0.25.3, a field added to a class
already in an `__all__` (`SuiteRuns.unnamed`) was invisible to the diff of
the `__all__`s.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType

TOOL = Path(__file__).resolve().parent.parent / "tools" / "public_fields.py"


def tool() -> ModuleType:
    spec = importlib.util.spec_from_file_location("public_fields", TOOL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_it_reads_the_fields_of_a_listed_dataclass() -> None:
    found = tool().fields()
    assert "unnamed" in found["digline.host.SuiteRuns"]


def test_a_field_added_to_a_class_already_public_is_listed() -> None:
    """The 0.25.3 case: the class's name did not move, its fields did."""
    then = {"digline.host.SuiteRuns": ["runs", "refused"]}
    now = {"digline.host.SuiteRuns": ["runs", "refused", "unnamed"]}
    assert tool().diff(then, now) == ["field added    digline.host.SuiteRuns.unnamed"]


def test_classes_and_fields_both_ways() -> None:
    then = {"a.Gone": ["x"], "a.Kept": ["x", "y"]}
    now = {"a.Kept": ["x"], "a.New": ["z"]}
    assert tool().diff(then, now) == [
        "class removed  a.Gone",
        "field removed  a.Kept.y",
        "class added    a.New: z",
    ]


def test_nothing_moved_prints_nothing(tmp_path: Path) -> None:
    same = tmp_path / "same.json"
    same.write_text(json.dumps({"a.Kept": ["x"]}), encoding="utf-8")
    done = subprocess.run(
        [sys.executable, str(TOOL), "--diff", str(same), str(same)],
        capture_output=True,
        text=True,
        check=True,
    )
    assert done.stdout == ""


def test_it_reads_the_properties_of_a_listed_dataclass() -> None:
    """The 0.34.0 case: `Comparison` gained three properties, and no diff the
    delta-pass ran could see them. They were found because the changelog
    entry named them."""
    found = tool().fields()["digline.core.Comparison"]
    assert {"@pinned_changed", "@pinned_changed_count", "@pinned_gone"} <= set(found)
    assert "pinned_changed" not in found


def test_a_property_is_listed_as_a_property_both_ways() -> None:
    then = {"a.Kept": ["x", "@gone"]}
    now = {"a.Kept": ["x", "@new"]}
    assert tool().diff(then, now) == [
        "property added a.Kept.new",
        "property removed a.Kept.gone",
    ]
