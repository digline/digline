"""An example may not cap digline below a version that can read its baseline.

Each example is a project meant to leave: it depends on the *published*
package, with a floor and a ceiling — `digline>=0.4,<0.5`. The ceiling is there
on purpose, because an example is a fixed artifact and a major-version change
could break it. What the ceiling also does, silently, is decide **which digline
a reader ends up with**: `uv sync` in `examples/rag` installs the newest release
the cap admits, and that release then has to read the baseline committed in the
same directory.

`run_from_json` refuses any `schema_version` that is not the one it knows —
exactly, in both directions, because a document from another schema is not a
document this code can be trusted to interpret. So a cap whose highest admitted
release is a digline at schema 8, over a baseline committed at schema 9, is an
example that cannot be run by the only person it exists for. It has happened:
four example baselines had stopped being readable at all, and nothing said so
until somebody tried.

Today the rule holds by luck. Schema 9 arrived in 0.4.0, so the `<0.5` caps
admit 0.4.0 and 0.4.0 is at 9. Had schema 9 landed one release later, every one
of those examples would have been broken on the day it was written. This file
makes it hold by construction instead.

The check needs a fact the working tree does not carry: **which schema each
released version wrote**. That is in the tags, and `RELEASED` below is it,
pinned — read once with `git show vX.Y.Z:src/digline/core/run.py`, not
remembered. Pinned rather than read at test time because CI checks out shallow
and without tags, and a gate that cannot run in CI is not a gate;
`test_the_table_agrees_with_the_tags` verifies the pin wherever the history is
actually present.

The `INTRODUCED` discipline from `test_plugin_floors.py`, in the same shape: the
current release must have a row, and its row must agree with the
`SCHEMA_VERSION` this workspace writes. So a release cannot be cut without
someone recording what it writes, and the newest row — the one that matters —
is never taken on trust.
"""

from __future__ import annotations

import json
import re
import subprocess
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import cast

import pytest

from digline.core.run import SCHEMA_VERSION

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"

#: The schema each released version writes and reads, from the tag that
#: released it:
#:
#:     git show vX.Y.Z:src/digline/core/run.py | grep '^SCHEMA_VERSION'
#:
#: A row can be wrong only in a way nothing else notices, which is why it is
#: read from the history rather than recalled, and why the newest row is
#: checked against the live constant below.
RELEASED: dict[str, int] = {
    # 7 — the first published schema.
    "0.1.0": 7,
    "0.1.1": 7,
    "0.1.2": 7,
    "0.1.3": 7,
    # 8 — the configuration of the system under test (ADR 0005).
    "0.2.0": 8,
    "0.3.0": 8,
    # 9 — repeated samples and the noise floor (ADR 0006).
    "0.4.0": 9,
    "0.5.0": 9,
    "0.6.0": 9,
    "0.7.0": 9,
    "0.7.1": 9,
    "0.7.2": 9,
    "0.8.0": 9,
}

#: `digline>=0.4,<0.5` → the `0.5`. Only the upper bound: the floor is a
#: different promise and `test_plugin_floors.py` is where floors are judged.
CAP = re.compile(r"^digline>=[\d.]+,<([\d.]+)$")

STANDALONE = (
    "classifier",
    "prompt-first",
    "rag",
    "external-app",
    "langchain4j",
    "langchain",
    "llamaindex",
    "quickstart-toml",
    "operator",
)


def as_tuple(text: str) -> tuple[int, ...]:
    return tuple(int(part) for part in text.split("."))


def workspace_version() -> str:
    with (ROOT / "pyproject.toml").open("rb") as handle:
        version = tomllib.load(handle)["project"]["version"]
    assert isinstance(version, str)
    return version


def declared_cap(name: str) -> str:
    """The `<X.Y` an example writes, as it writes it."""
    with (EXAMPLES / name / "pyproject.toml").open("rb") as handle:
        project = tomllib.load(handle)["project"]
    for dependency in project["dependencies"]:
        found = CAP.match(str(dependency).replace(" ", ""))
        if found:
            return found.group(1)
    pytest.fail(
        f"examples/{name} declares no upper bound on digline. An example is a "
        "fixed artifact and an uncapped one silently follows the core "
        "wherever it goes — write `digline>=X.Y,<X.Z` like the others."
    )


def admitted_by(cap: str) -> str:
    """The newest release a `<cap>` would actually install."""
    ceiling = as_tuple(cap)
    below = [v for v in RELEASED if as_tuple(v) < ceiling]
    assert below, f"no released version is below {cap}"
    return max(below, key=as_tuple)


def committed_schemas(name: str) -> dict[Path, int]:
    """Every run document the example ships, by the schema it was written at."""
    found: dict[Path, int] = {}
    for path in sorted((EXAMPLES / name).rglob(".digline/**/*.json")):
        document: object = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(document, dict):
            # Read as `object` and narrowed here: a run file is written by
            # whoever holds it, and this is the one place that decides what
            # `schema_version` in it means.
            schema = cast("Mapping[str, object]", document).get("schema_version")
            if isinstance(schema, int):
                found[path] = schema
    return found


# --------------------------------------------------------------------------- #
# The table, and what keeps it honest
# --------------------------------------------------------------------------- #


def test_the_schema_this_workspace_writes_belongs_to_a_release() -> None:
    """The half that makes a release add its row — and that catches the window
    where the examples are unrunnable.

    `pyproject.toml` is bumped at release time, so through ordinary development
    it names the last release and this tree writes exactly what that release
    wrote. The two ways out of that state are the two failures below, and they
    want opposite things done.
    """
    version = workspace_version()
    recorded = RELEASED.get(version)
    if recorded == SCHEMA_VERSION:
        return

    assert recorded is not None, (
        f"this workspace is at {version} and RELEASED has no row for it. Add "
        f'`"{version}": {SCHEMA_VERSION},` — the schema it writes — so the caps '
        "below can be checked against it."
    )
    pytest.fail(
        f"digline {version} shipped writing schema {recorded}, and this tree "
        f"writes {SCHEMA_VERSION}: the schema has moved since the last "
        "release.\n\n"
        f"**Do not edit the {version} row.** It is what that release put on "
        "PyPI, and the examples' caps are checked against it. What the schema "
        "bump costs is a release: bump `pyproject.toml` to the version that "
        f"will carry schema {SCHEMA_VERSION}, give it a row here, and raise "
        "every example cap to admit it. Until that version is on the index a "
        "reader cannot resolve these examples at all — their committed "
        f"baselines are at schema {SCHEMA_VERSION} and every release they "
        "admit refuses it — which is what the cap gate is about to say, "
        "correctly, once per example."
    )


def test_the_table_agrees_with_the_tags() -> None:
    """The pin, verified against the history it was taken from.

    Skipped where the tags are absent — CI checks out shallow — so this is the
    check that runs on a full clone and on anyone's machine, not the one the
    gate depends on.
    """
    for version, schema in sorted(RELEASED.items(), key=lambda row: as_tuple(row[0])):
        tag = f"v{version}"
        shown = subprocess.run(  # noqa: S603
            ["git", "show", f"{tag}:src/digline/core/run.py"],  # noqa: S607
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if shown.returncode != 0:
            pytest.skip(f"{tag} is not in this checkout (shallow clone, no tags)")
        found = re.search(r"^SCHEMA_VERSION = (\d+)$", shown.stdout, re.M)
        assert found is not None, f"{tag} has no SCHEMA_VERSION in core/run.py"
        assert int(found.group(1)) == schema, (
            f"RELEASED says {version} writes schema {schema}, and {tag} "
            f"declares {found.group(1)}. The tag is the record."
        )


# --------------------------------------------------------------------------- #
# The gate
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("name", STANDALONE)
def test_every_cap_admits_a_digline_that_can_read_the_baseline(name: str) -> None:
    """The whole point of the file.

    Not "the cap is the current version" — an example is allowed to be pinned
    to an older line, and several are. What it may not be is pinned below the
    schema its own committed baseline is written at, because then the reader's
    resolver hands them a digline that refuses the file in the next directory.
    """
    cap = declared_cap(name)
    newest = admitted_by(cap)
    schema = RELEASED[newest]
    assert schema >= SCHEMA_VERSION, (
        f"examples/{name} caps digline at <{cap}, so a reader gets {newest}, "
        f"which reads schema {schema}. This workspace writes schema "
        f"{SCHEMA_VERSION}, and the baseline committed in that example is at "
        f"{SCHEMA_VERSION} too — `digline compare` would refuse it before "
        "reading a single verdict. Raise the cap to admit a release at "
        f"schema {SCHEMA_VERSION} or higher."
    )


@pytest.mark.parametrize("name", STANDALONE)
def test_every_committed_document_is_the_schema_this_workspace_writes(
    name: str,
) -> None:
    """The other half of the same invariant, and the one that actually rotted.

    The gate above compares a cap with `SCHEMA_VERSION`; that is only the right
    comparison while the files in `.digline/` are at `SCHEMA_VERSION` too. A
    baseline left behind by a schema bump is the original failure — four of
    them, unreadable, found by hand.
    """
    stale = {
        path.relative_to(ROOT).as_posix(): schema
        for path, schema in committed_schemas(name).items()
        if schema != SCHEMA_VERSION
    }
    assert not stale, (
        f"examples/{name} commits documents at a schema this workspace does "
        f"not write ({SCHEMA_VERSION}):\n  "
        + "\n  ".join(f"{path}: schema {schema}" for path, schema in stale.items())
        + "\nRun `digline migrate` in the example and commit the result: "
        "`run_from_json` refuses any schema but its own, so these are files "
        "nobody can read."
    )


@pytest.mark.parametrize("name", STANDALONE)
def test_every_example_commits_something_for_the_gate_to_check(name: str) -> None:
    """An example with no committed run makes both tests above vacuous — they
    would pass on an empty directory. What each one ships is a baseline, which
    is what `compare` reads."""
    assert committed_schemas(name), (
        f"examples/{name} commits no run document at all, so the schema gates "
        "have nothing to judge. Every example ships the baseline its README "
        "compares against."
    )
