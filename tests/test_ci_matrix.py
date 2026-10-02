"""Every Python version `pyproject.toml` declares is one the gates run.

3.14 was a classifier with no gate. A defect that existed only there, a
baseline in an unreadable directory read as no baseline, was found by accident
while fixing something else (#365): nothing would ever have run the version it
lived on. A declared version that nothing runs is a claim nothing checks.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CI = ROOT / ".github" / "workflows" / "ci.yml"
PYPROJECT = ROOT / "pyproject.toml"


def declared() -> set[str]:
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    prefix = "Programming Language :: Python :: "
    return {
        classifier.removeprefix(prefix)
        for classifier in data["project"]["classifiers"]
        if re.fullmatch(re.escape(prefix) + r"3\.\d+", classifier)
    }


def gated() -> set[str]:
    """The `python:` list of the `gates` job's matrix, read from the text: the
    job ends where the next top-level job begins."""
    text = CI.read_text(encoding="utf-8")
    job = re.search(r"^  gates:\n(.*?)(?=^  \S)", text, re.M | re.S)
    assert job, "ci.yml has no `gates` job"
    found = re.search(r"^\s+python: \[(.*?)\]", job.group(1), re.M)
    assert found, "the `gates` job has no `python:` matrix"
    return set(re.findall(r'"(3\.\d+)"', found.group(1)))


def test_the_classifiers_name_at_least_the_floor() -> None:
    """Without this, an empty set on both sides would pass the test below."""
    assert "3.12" in declared()


def test_the_gates_run_every_declared_version_and_no_other() -> None:
    assert gated() == declared()
