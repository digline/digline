"""No public callable has a required parameter it did not have at `v1.0.3`.

From 1.0.0 a minor does not give a public function, method or class a
required parameter (`RELEASING.md`, *Choosing the version*). 1.1.0 did:
`digline.host.measure` gained `marker_root` with no default, digline-mcp
0.8.1 called it the 1.0 way and raised `TypeError`, and publish run
42639021156 stopped the release before PyPI. So 1.1.0 never reached PyPI and
1.1.1 is the release.

**The reference is a file, not the tag.** `tests/fixtures/signatures/
v1.0.3.json` is `tools/public_signatures.py --src` run on `git archive v1.0.3
src` (commit `6134f2310bd96713f47d27442f0330da0310d907`), the last `v1.0.*`
tag. A CI checkout is shallow and has no tags, and importing a tag inside a
test would read whichever `digline` the path finds first.

**What it does not cover:** what the tool's docstring lists, and every name
that is public now and was not at `v1.0.3`. Those are held only once the
fixture is read again from a later tag.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parent.parent
TOOL = ROOT / "tools" / "public_signatures.py"
FIXTURE = ROOT / "tests" / "fixtures" / "signatures" / "v1.0.3.json"


def tool() -> ModuleType:
    spec = importlib.util.spec_from_file_location("public_signatures", TOOL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_no_public_callable_gained_a_required_parameter_since_1_0_3() -> None:
    then = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert tool().added(then, tool().signatures()) == []


def test_the_reading_reads_what_the_promise_is_about() -> None:
    """The control that the reading reads: a function, a constructor and a
    method are each found, with their required parameters."""
    now = tool().signatures()
    assert now["digline.host.measure"] == ["suite", "target", "store", "prepared"]
    assert now["digline.core.Contains"] == ["needle"]
    assert "digline.store.FileResultStore.read_run" not in now  # not in the scope
    assert any(key.startswith("digline.run.Suite.") for key in now)


def test_the_fixture_still_names_what_it_held() -> None:
    """A fixture that lost its entries would hold nothing and pass."""
    then = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert len(then) > 200
    assert then["digline.host.measure"] == ["suite", "target", "store", "prepared"]


def test_the_1_1_0_break_is_what_it_finds() -> None:
    """The case it exists for, as a pair of readings: `measure` at 1.1.0."""
    then = {"digline.host.measure": ["suite", "target", "store", "prepared"]}
    now = {
        "digline.host.measure": ["suite", "target", "store", "prepared", "marker_root"]
    }
    assert tool().added(then, now) == [
        "required parameter added  digline.host.measure: marker_root"
    ]


def test_a_name_new_since_the_tag_is_not_compared() -> None:
    """Said in the module's docstring, and held here so it is not believed."""
    assert tool().added({}, {"digline.host.new": ["x"]}) == []
