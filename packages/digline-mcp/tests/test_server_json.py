"""`server.json` describes this package to the MCP registry, by hand.

It names a version twice, and the registry verifies the package against that
exact release on PyPI. A release that moves `pyproject.toml` and not this file
would leave the entry describing the release before it, and nothing would turn
red: the same drift as a moving tag nobody re-points. So the declaration is
held to the package it describes, here, on every run.
"""

from __future__ import annotations

import json
import tomllib
from pathlib import Path
from typing import Any

PACKAGE = Path(__file__).resolve().parents[1]


def project() -> dict[str, Any]:
    with (PACKAGE / "pyproject.toml").open("rb") as handle:
        return tomllib.load(handle)["project"]


def manifest() -> dict[str, Any]:
    return json.loads((PACKAGE / "server.json").read_text(encoding="utf-8"))


def test_the_manifest_names_the_version_pyproject_declares() -> None:
    version = project()["version"]
    entry = manifest()
    (package,) = entry["packages"]
    assert entry["version"] == version, (
        f"server.json says {entry['version']} and pyproject.toml says {version}. "
        "A release of digline-mcp moves both (RELEASING.md, *digline-mcp's "
        "registry entry moves with its version*)."
    )
    assert package["version"] == version, (
        f"server.json's package says {package['version']} and pyproject.toml "
        f"says {version}"
    )


def test_the_manifest_names_this_distribution_on_pypi() -> None:
    (package,) = manifest()["packages"]
    assert package["registryType"] == "pypi"
    assert package["identifier"] == project()["name"]


def test_the_readme_carries_the_name_the_registry_verifies() -> None:
    """The registry reads the PyPI release's description, which is this README,
    for `mcp-name: <name>`. A name changed in one place and not the other is
    an entry PyPI no longer vouches for."""
    readme = (PACKAGE / project()["readme"]).read_text(encoding="utf-8")
    assert f"mcp-name: {manifest()['name']} " in readme


def test_the_root_is_declared_required_as_the_code_requires_it() -> None:
    """`main()` refuses to start without `--root` (test_perimeter.py holds
    that). The manifest says the same to whoever reads the registry."""
    (package,) = manifest()["packages"]
    root = [a for a in package["packageArguments"] if a.get("name") == "--root"]
    assert len(root) == 1
    assert root[0]["isRequired"] is True
