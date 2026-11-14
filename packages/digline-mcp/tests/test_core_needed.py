"""A core without what `where` answers with is refused at start, by name.

`where` reads `idle_checks` off the core's document, and digline 1.2.0 has no
such key: under `--names project` the tool raised `KeyError` in the middle of
a call. The floor in `pyproject.toml` is the rule that keeps that core out;
this is the alarm for an environment that installed around the floor, and it
sounds before any tool is served. (P-1683)
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

import digline.run.suite as suite_module
from digline_mcp import server

PACKAGE = Path(__file__).resolve().parents[1]
RELEASING = PACKAGE.parents[1] / "RELEASING.md"


def test_this_workspace_s_core_is_served() -> None:
    """The control: the core beside this package carries what it reads."""
    assert server.core_missing() is None


def test_a_core_without_idle_checks_is_refused_before_anything_starts(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    older = [name for name in suite_module.__all__ if name != "idle_checks"]
    monkeypatch.setattr(suite_module, "__all__", older)

    def never(*args: object, **kwargs: object) -> object:
        raise AssertionError("the server was built against a core it cannot read")

    monkeypatch.setattr(server, "build_server", never)
    with pytest.raises(SystemExit) as stopped:
        server.main(["--root", str(tmp_path), "--names", "clear"])
    # The parser's own refusal, as for every flag this server refuses.
    assert stopped.value.code == 64
    said = capsys.readouterr().err
    assert "digline-mcp needs digline 1.3.0 or later" in said
    assert "Install digline>=1.3.0." in said
    assert "KeyError" not in said


def floor_declared() -> str:
    project = tomllib.loads((PACKAGE / "pyproject.toml").read_text(encoding="utf-8"))
    [floor] = [
        re.sub(r"^digline>=([0-9.]+).*$", r"\1", requirement)
        for requirement in project["project"]["dependencies"]
        if requirement.startswith("digline>=")
    ]
    return floor


def floor_owed() -> str | None:
    """The *Raise to* of this package's row in the table of floors owed at the
    cut, read between the two sentences `tests/test_plugin_floors.py` reads it
    between; the table owed to the next version has rows of this package too."""
    text = RELEASING.read_text(encoding="utf-8")
    start = text.find("raise the floors owed to this release.")
    end = text.find("**An empty table is the normal state.**")
    assert 0 <= start < end
    for line in text[start:end].splitlines():
        if line.startswith("| `digline-mcp` |"):
            return line.split("|")[3].strip().strip("`")
    return None


def test_the_alarm_names_the_floor_the_rule_names() -> None:
    """The sentence and the floor say one version: the one in the pyproject,
    or, until the cut raises it there, the one owed at the cut."""
    named = floor_owed() or floor_declared()
    assert named == server.NEEDS_CORE
