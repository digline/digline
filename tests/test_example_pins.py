"""The versions `examples-from-pypi` waits for: every workspace package an
example depends on, plugins included (RELEASING.md, P-1632).

On 2026-11-10 the leg `operator` installed digline-mcp 0.8.1 two minutes after
0.9.0 was uploaded, because the wait asked for the core alone. These hold the
list to the examples and the step to the list.
"""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]

sys.path.insert(0, str(ROOT / ".github"))
import example_pins  # noqa: E402


def declared(path: Path) -> str:
    return str(tomllib.loads(path.read_text(encoding="utf-8"))["project"]["version"])


def test_the_tree_waits_for_the_core_and_each_plugin_an_example_installs() -> None:
    pins = example_pins.pins(ROOT)
    core = declared(ROOT / "pyproject.toml")
    mcp = declared(ROOT / "packages" / "digline-mcp" / "pyproject.toml")
    anthropic = declared(ROOT / "packages" / "digline-anthropic" / "pyproject.toml")
    assert f"digline=={core}" in pins
    # `operator` installs the server: the leg that installed 0.8.1.
    assert f"digline-mcp=={mcp}" in pins
    assert f"digline-anthropic=={anthropic}" in pins
    # No example installs pytest-digline: the control, a package of this
    # workspace that is not waited for.
    assert not any(pin.startswith("pytest-digline==") for pin in pins)


def project(path: Path, text: str) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "pyproject.toml").write_text(text, encoding="utf-8")


def test_a_plugin_named_only_in_an_optional_group_is_waited_for(tmp_path: Path) -> None:
    project(tmp_path, '[project]\nname = "digline"\nversion = "9.0.0"\n')
    project(
        tmp_path / "packages" / "digline-openai",
        '[project]\nname = "digline-openai"\nversion = "1.2.3"\n',
    )
    project(
        tmp_path / "examples" / "one",
        '[project]\nname = "one"\nversion = "0"\ndependencies = ["digline>=9,<10"]\n'
        '[project.optional-dependencies]\nlive = ["digline_openai >=1"]\n',
    )
    assert example_pins.pins(tmp_path) == ["digline==9.0.0", "digline-openai==1.2.3"]


def test_no_workspace_package_in_any_example_is_refused(tmp_path: Path) -> None:
    project(tmp_path, '[project]\nname = "digline"\nversion = "9.0.0"\n')
    project(
        tmp_path / "examples" / "one",
        '[project]\nname = "one"\nversion = "0"\ndependencies = ["requests"]\n',
    )
    with pytest.raises(SystemExit, match="hold the index to nothing"):
        example_pins.pins(tmp_path)


def test_the_step_waits_for_the_list_before_anything_resolves() -> None:
    workflow = yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text())
    steps = list(workflow["jobs"]["examples-from-pypi"]["steps"])
    runs = [str(step.get("run", "")) for step in steps]
    (wait,) = [i for i, run in enumerate(runs) if "await_index.py" in run]
    (resolve,) = [i for i, run in enumerate(runs) if "uv sync" in run]
    assert wait < resolve
    script = runs[wait]
    assert "example_pins.py > /tmp/example-pins.txt" in script
    assert "await_index.py --manifest /tmp/example-pins.txt" in script
    assert "set -euo pipefail" in script
