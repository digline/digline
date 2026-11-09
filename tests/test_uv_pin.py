"""One `uv` everywhere: the root `pyproject.toml`'s `required-version`, the
`version` every `setup-uv` in the workflows installs, and the version
`tests/test_lock_revision.py` says the tool was fixed at.

Decided 2026-11-09 by Alessandro Prandini. A lock's `revision` is the format of
the `uv` that wrote it, and with no pin CI took the newest `uv` while a person
relocked with whatever was installed: the lock moved in diffs that read as one
more line (`test_lock_revision.py` keeps the history). The pin is the repair;
this test is what keeps its three places from drifting apart. A `setup-uv`
without a `version`, which is what every one was before, is red here by name.

The workflows are read as text, as `tests/test_docker.py` and
`tests/test_examples.py` read them: PyYAML is here only transitively, and a
gate that fails when an unrelated dependency drops it gets deleted.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"

_USES = re.compile(r"^(?P<indent>[ ]*)- uses: astral-sh/setup-uv@", re.MULTILINE)
_VERSION = re.compile(r'^[ ]+version: "(?P<version>[^"]+)"[ ]*$')
_FIXED = re.compile(
    r"\*\*Fixed on (?P<day>\d{4}-\d{2}-\d{2}) at uv (?P<version>[0-9.]+)\*\*"
)


def required_version(root: Path) -> str:
    """The root project's `required-version`, which must name one version
    exactly: a range would let two uvs write two formats."""
    found = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    spec = found.get("tool", {}).get("uv", {}).get("required-version")
    assert isinstance(spec, str), (
        "the root pyproject.toml sets no [tool.uv] required-version"
    )
    assert spec.startswith("==") and "," not in spec, (
        f"required-version is {spec!r}: one version, written ==X.Y.Z"
    )
    return spec[2:]


def setup_uv_versions(workflows: Path) -> dict[str, str | None]:
    """`file:line` of each `setup-uv` step, and the `version` its step gives,
    or `None` where it gives none. The step is read from its `- uses:` line to
    the next line at its own indent or less."""
    found: dict[str, str | None] = {}
    for path in sorted(workflows.glob("*.yml")):
        text = path.read_text(encoding="utf-8")
        lines = text.split("\n")
        for match in _USES.finditer(text):
            start = text.count("\n", 0, match.start())
            depth = len(match.group("indent"))
            version: str | None = None
            for line in lines[start + 1 :]:
                if line.strip() and len(line) - len(line.lstrip()) <= depth:
                    break
                read = _VERSION.match(line)
                if read is not None:
                    version = read.group("version")
            found[f"{path.name}:{start + 1}"] = version
    return found


def fixed_at(root: Path) -> str:
    """The version `test_lock_revision.py`'s docstring says the tool was fixed
    at."""
    text = (root / "tests" / "test_lock_revision.py").read_text(encoding="utf-8")
    found = _FIXED.search(text)
    assert found is not None, "test_lock_revision.py no longer says where uv was fixed"
    return found.group("version")


def test_every_setup_uv_installs_the_required_version() -> None:
    pinned = required_version(ROOT)
    steps = setup_uv_versions(WORKFLOWS)
    # The positive control: the three files that install uv each do, so an
    # empty reading is a broken pattern and not a repository without uv.
    files = {step.split(":", 1)[0] for step in steps}
    assert {"ci.yml", "publish.yml", "release-followup.yml"} <= files, files
    wrong = {step: version for step, version in steps.items() if version != pinned}
    assert not wrong, (
        f"these setup-uv steps do not install uv {pinned}, the root "
        f"pyproject.toml's required-version: {wrong}"
    )


def test_the_lock_revision_test_names_the_same_uv() -> None:
    assert fixed_at(ROOT) == required_version(ROOT)


def test_a_step_with_another_version_or_none_is_named(tmp_path: Path) -> None:
    """The control: a copy of the workflows where one step installs another uv
    and one installs whatever is newest is red on exactly those two steps."""
    copied = tmp_path / "workflows"
    copied.mkdir()
    for path in WORKFLOWS.glob("*.yml"):
        (copied / path.name).write_text(
            path.read_text(encoding="utf-8"), encoding="utf-8"
        )
    pinned = required_version(ROOT)
    ci = copied / "ci.yml"
    text = ci.read_text(encoding="utf-8")
    pin = f'          version: "{pinned}"\n'
    assert text.count(pin) >= 2
    text = text.replace(pin, '          version: "0.11.14"\n', 1)
    at = text.index(pin)
    text = text[:at] + text[at + len(pin) :]
    ci.write_text(text, encoding="utf-8")
    wrong = {
        step: version
        for step, version in setup_uv_versions(copied).items()
        if version != pinned
    }
    assert sorted(wrong.values(), key=str) == ["0.11.14", None], wrong
    assert all(step.startswith("ci.yml:") for step in wrong), wrong
