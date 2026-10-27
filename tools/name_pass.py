"""The names digline gives one thing in different places, and the one name it
gives different things: three passes, each a list to read.

`name` against `assertion` (#678) is the known instance of the first: a
verdict's check is `assertion` in the run file and in `compare --json`, and
`name` in the MCP tools `get_run` and `get_baseline`. The second is the worse
one, because no single document shows it: `outcome` carries one vocabulary in
`compare`'s deltas, another in `diff`'s checks and an object of counts in the
register. A rename of either is a change of the JSON contract, so the time to
find them is before a bump of `OUTPUT_VERSION`, not after one.

    uv run python tools/name_pass.py

prints the three lists below and exits 0: they are candidates to read, not a
verdict, and which name wins is a decision.

1. **The static pass** reads the contract `_lines(_SHAPES)` derives, the lines
   `tools/contract_diff.py` reads, groups them by their last key, and lists a
   key whose types differ between the shapes that hold it.
2. **The values pass** builds the fixture of the names gate of digline-mcp
   (`packages/digline-mcp/tests/test_names_gate.py`: `examples/prompt-first`
   as git tracks it, widened with an aggregate split by group, two runs and a
   reference). The copy leaves out what git ignores beside the example, the
   runs and journals of a checkout that has run it: they once entered a
   measurement as the fixture's own. It calls every tool the server
   registers, in clear, and reads every string of every answer, of the two
   run files, of the reference and of a journal. A
   finished run leaves no journal, so the store's own writer writes one for
   the second run: its keys are measured, its values are that run's. A value
   held under two or more different keys is listed, with every path it is
   held at. The empty string is not a value but an absence, and is skipped.
3. **The textual pass** reads `src/`, each plugin's sources and `docs/` for a
   sentence that names a bump beside a rename, or beside removing a key. It
   folds each paragraph and each run of comment lines into one line first.

**Where each one stops.**

- **The static pass sees one name on several concepts only when the types
  differ.** `field`, a configuration key in one shape and the bar that moved
  in another, is a string in both and is not listed.
- **The values pass sees one concept under several names only when the same
  value occurs in the fixture.** It indexes strings, never numbers nor
  booleans. A path the fixture leaves empty is not seen at all: in this
  fixture, a rule delta, a check fact, a setting fact, a calibration band,
  the register, a replay and a roll.
- **The textual pass sees a sentence only in the words it looks for.** Read a
  line at a time it did not see a sentence broken across lines: the first grep
  of this pass missed the note beside `answered` in `wire/log.py`, which is why
  it folds now. A deferral written in other words is not seen.

**Its controls are in `tests/test_name_pass.py`, and the positive one is
fixed there rather than read from the code**: a positive control that depends
on the defect falls silent when the defect is repaired, which is when it is
needed most.

**And one class no pass here can see: two counts of the same thing, one called
`cases` and the other `count`, with no value they share and no sentence that
says so.** Nothing in a name, a type or a value connects them. An empty list
from these three passes is not evidence that such a pair is absent.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from collections import defaultdict
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "packages" / "digline-mcp" / "tests" / "test_names_gate.py"


# -- the static pass ---------------------------------------------------------


def contract_lines() -> list[str]:
    """The derived contract, one `name.key: types` line per key."""
    from digline.wire import contract

    return list(contract._lines(contract._SHAPES))  # pyright: ignore[reportPrivateUsage]


def typed_collisions(lines: Iterable[str]) -> dict[str, list[tuple[str, str]]]:
    """Each last key held with different types, and every `(path, types)` of it."""
    held: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for line in lines:
        path, types = line.split(": ", 1)
        held[path.rsplit(".", 1)[-1].rstrip("?")].append((path, types))
    return {
        key: sorted(places)
        for key, places in sorted(held.items())
        if len({types for _, types in places}) > 1
    }


# -- the values pass ---------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Found:
    """One string, where it was read: a source and a JSON path in it."""

    source: str
    path: str
    value: str


@dataclass(frozen=True, slots=True)
class Shared:
    """One value held under more than one key, and each place it is held."""

    value: str
    keys: frozenset[str]
    places: tuple[tuple[str, str], ...]


def key_of(path: str) -> str:
    """The key that holds a value: the path's last step, without `[]`."""
    return path.rsplit(".", 1)[-1].replace("[]", "")


def shared_values(found: Iterable[Found]) -> list[Shared]:
    """The values held under two or more keys, the most keys first."""
    places: dict[str, set[tuple[str, str]]] = defaultdict(set)
    for item in found:
        if item.value:
            places[item.value].add((item.source, item.path))
    listed = [
        Shared(value, frozenset(key_of(path) for _, path in held), tuple(sorted(held)))
        for value, held in places.items()
    ]
    return sorted(
        (item for item in listed if len(item.keys) > 1),
        key=lambda item: (-len(item.keys), item.value),
    )


def _walk(value: object, path: str = "$") -> Iterator[tuple[str, str]]:
    if isinstance(value, dict):
        for key, item in cast(dict[str, object], value).items():
            yield from _walk(item, f"{path}.{key}")
    elif isinstance(value, list):
        for item in cast(list[object], value):
            yield from _walk(item, f"{path}[]")
    elif isinstance(value, str):
        yield path, value


def _gate() -> ModuleType:
    for entry in (ROOT, GATE.parent):
        if str(entry) not in sys.path:
            sys.path.insert(0, str(entry))
    spec = importlib.util.spec_from_file_location("_name_pass_gate", GATE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fixture_strings(work: Path) -> list[Found]:
    """Every string of the names gate's fixture, built under `work`: each tool's
    answer in clear, the two run files, the reference and the journal."""
    gate = _gate()
    repo, first, second = gate.build_repository(work)
    found = [
        Found(f"mcp:{tool}", path, value)
        for tool, strings in gate.drive(repo, first, second, table=None).items()
        for path, value in strings
        if not path.startswith("!")
    ]
    _journal(repo, second)
    store = tenant_store(repo)
    for key in (first, second):
        document = next(store.glob(f"runs/*/{key}.json"))
        found += document_strings(
            "run_document", json.loads(document.read_text("utf-8"))
        )
    for document in sorted(store.glob("baselines/*.json")):
        found += document_strings("baseline", json.loads(document.read_text("utf-8")))
    for journal in sorted(store.glob("runs/*/.pending/*.jsonl")):
        for line in journal.read_text("utf-8").splitlines():
            found += document_strings("journal", json.loads(line))
    return found


def tenant_store(repo: Path) -> Path:
    """The tenant's directory under `.digline`, which also holds files of its
    own, `.gitattributes` and `.gitignore`. A listing comes in no order the
    filesystem promises, so the directory is chosen, never the first entry."""
    tenants = [path for path in (repo / ".digline").iterdir() if path.is_dir()]
    assert len(tenants) == 1, tenants
    return tenants[0]


def _journal(repo: Path, key: str) -> None:
    """A journal for the run `key`, written by the store's own writer, header
    and cases, as a run killed before its document would have left it. A
    finished run leaves no journal, so the fixture has none of its own. What is
    measured is the writer's keys; the header's values are the run's, and
    `cases_digest`, which a run does not carry, is written empty."""
    from digline.core import CaseProgress
    from digline.store import FileResultStore, JournalHeader, RunRef

    run_file = next((repo / ".digline").glob(f"*/runs/*/{key}.json"))
    store = FileResultStore(repo)
    run = store.read_run(
        RunRef(tenant=run_file.parents[2].name, suite=run_file.parent.name, key=key)
    )
    journal = store.open_journal(
        JournalHeader(
            tenant=run.tenant,
            environment=run.environment,
            suite=run.suite,
            config_hash=run.config_hash,
            cases_digest="",
            created_at=run.created_at,
            started_at=run.created_at,
            digline_version=run.digline_version,
            record_responses=True,
            git_commit=run.git_commit,
            artifacts={path: item.sha for path, item in run.artifacts.items()},
            pinned=run.pinned,
            target_config=run.target_config,
            judge_config=run.judge_config,
        )
    )
    for result in run.results:
        journal.append(
            CaseProgress(
                result=result,
                observed_target=run.target_config,
                observed_judge=run.judge_config,
            )
        )


def document_strings(source: str, document: Any) -> list[Found]:
    """Every string of one JSON document, read as from `source`."""
    return [Found(source, path, value) for path, value in _walk(document)]


# -- the textual pass --------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Place:
    """A sentence that defers a rename or a removal, at its first line."""

    path: str
    line: int
    sentence: str


#: Where digline names its own fields: its sources, each plugin's, and the docs.
TEXT_ROOTS = ("src", "packages", "docs")
TEXT_SUFFIXES = frozenset({".py", ".md"})

_BUMP = re.compile(r"\bbump", re.IGNORECASE)
_DEFERRED = re.compile(r"renam|removing a key|removes a key", re.IGNORECASE)
_MARKER = re.compile(r"^\s*(?:#:?|//|\*|>)?\s?")
_SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z`*(])")


def _paragraphs(text: str, *, python: bool) -> Iterator[tuple[int, str]]:
    """Each paragraph, comment markers stripped and its lines joined, with the
    number of its first line. In Python a run of comment lines is a paragraph
    of its own, apart from the code around it."""
    start, lines, commented = 0, list[str](), False
    for number, raw in enumerate(text.splitlines(), start=1):
        line = _MARKER.sub("", raw).strip()
        comment = python and raw.lstrip().startswith("#")
        if lines and (not line or comment != commented):
            yield start, " ".join(lines)
            lines = []
        if line:
            if not lines:
                start, commented = number, comment
            lines.append(line)
    if lines:
        yield start, " ".join(lines)


def deferred(root: Path) -> list[Place]:
    """Every sentence under `root` that names a bump beside a rename, a removal
    or a wait for one."""
    places: list[Place] = []
    for top in TEXT_ROOTS:
        for path in sorted((root / top).rglob("*")):
            if path.suffix not in TEXT_SUFFIXES or not path.is_file():
                continue
            if any(
                part in {".venv", "node_modules", "__pycache__"} for part in path.parts
            ):
                continue
            text = path.read_text("utf-8", errors="replace")
            for line, paragraph in _paragraphs(text, python=path.suffix == ".py"):
                for sentence in _SENTENCE.split(paragraph):
                    if _BUMP.search(sentence) and _DEFERRED.search(sentence):
                        relative = path.relative_to(root).as_posix()
                        places.append(Place(relative, line, sentence))
    return places


# -- the report --------------------------------------------------------------


def main() -> int:
    import tempfile

    print("== the static pass: a key whose types differ")
    for key, places in typed_collisions(contract_lines()).items():
        print(f"{key}")
        for path, types in places:
            print(f"    {path}: {types}")
    print("== the values pass: a value held under more than one key")
    with tempfile.TemporaryDirectory() as work:
        for item in shared_values(fixture_strings(Path(work))):
            print(f"{item.value!r}: {', '.join(sorted(item.keys))}")
            for source, path in item.places:
                print(f"    {source} {path}")
    print("== the textual pass: a rename or a removal deferred to a bump")
    for place in deferred(ROOT):
        print(f"{place.path}:{place.line}: {place.sentence}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
