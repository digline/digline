"""The file `digline suggest` writes, read back for a person to look at.
(ADR 0063, the read-only view ruled 2026-11-09)

`digline view` shows a suite's proposal, and `digline where` names it in the
state `no_suite_yet`: both find it here and read it here. Nothing here writes,
and nothing here loads the proposal as a suite: `load_suite` refuses the file
by its name (ADR 0063 §3), and a proposal would not build one anyway, its
judge being a placeholder.

**Where it is looked for**, by `suggest`'s own rule, and nowhere else:

- for a suite that exists, beside its file, where `suggest_for` writes it;
- for a suite that does not exist yet, in the store's root and in the
  directory the process runs in, where `suggest_new` writes it when run from
  there. The tree is not walked: a walk is a read with no bound, and could
  cross into another perimeter. A proposal elsewhere is not found, and the
  page says where it looked.

**How it is read.** The values by `read_toml`, the reader a suite file is read
with. What `tomllib` drops, the comments, carries what the file says of each
value: why a check is there, which value is a placeholder, which one the
assistant wrote and no run measured, the counterexample and the calibration
skeleton. Those are read from the text, line by line, in the form `suggest`
writes them (`_check`, `_placeholder`, `_toml` in `host/suggest.py`). A line
the reader cannot place, as after an edit by hand, is kept in `unread` and
shown as it stands, never guessed at.

**What it never adds.** Under `repository = "public"` the file holds no
recorded text, and what is read back is the file's text alone: no recording
is read here.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Literal, cast

from digline.host.toml_suite import PROPOSAL, read_toml

__all__ = [
    "MODEL_TO_CHOOSE",
    "Mark",
    "ProposalFile",
    "ProposedBlock",
    "ProposedParam",
    "found_proposal",
    "proposal_places",
    "proposed_for",
    "read_proposal",
    "relative_to_root",
    "suggest_lines",
    "suite_file_of",
]

#: The first line `suggest` writes, which names the suite and the tenant.
_FIRST_LINE = re.compile(
    r'^# \S+, written by `digline suggest` for suite ("(?:[^"\\]|\\.)*")'
    r'(?: of tenant ("(?:[^"\\]|\\.)*"))?'
)

#: The marks `suggest` puts after a value, by what they say of it.
MarkKind = Literal["placeholder", "assistant", "draft"]
_MARKS: tuple[tuple[str, MarkKind], ...] = (
    ("# placeholder: yours to write", "placeholder"),
    ("# from the assistant, not measured", "assistant"),
    ("# from the assistant: a draft, yours to read", "draft"),
)

_HEADER = re.compile(r"^\s*\[(\[?)\s*([A-Za-z0-9_.\-]+)\s*\]\]?\s*$")
_KEY = re.compile(r'^\s*("(?:[^"\\]|\\.)*"|[A-Za-z0-9_\-]+)\s*=')


def suite_file_of(spec: str, module: ModuleType | None) -> Path:
    """The file a suite was loaded from: its module's file where it is code,
    the path `--suite` named where it is data. The one rule `digline suggest`
    writes its proposal beside, and every reader of the proposal finds it by."""
    module_file = getattr(module, "__file__", None)
    return Path(module_file) if module_file else Path(spec.split(":")[0])


def proposal_places(suite_file: Path | None, root: Path, cwd: Path) -> tuple[Path, ...]:
    """Where the proposal of a suite is looked for: beside its file where it
    has one; otherwise in `root` and in `cwd`, once each. Never a walk."""
    if suite_file is not None:
        return (suite_file.parent / PROPOSAL,)
    places: list[Path] = []
    for directory in (root, cwd):
        place = directory / PROPOSAL
        if all(place.resolve() != seen.resolve() for seen in places):
            places.append(place)
    return tuple(places)


def proposed_for(target: Path) -> str | None:
    """The suite a proposal was written for, read from its first line, or
    `None` where that line is not the one digline writes."""
    found = _first(target)
    return None if found is None else found[0]


def _first(target: Path) -> tuple[str, str | None] | None:
    try:
        with target.open(encoding="utf-8", errors="replace") as handle:
            first = handle.readline()
    except OSError:
        return None
    found = _FIRST_LINE.match(first)
    if found is None:
        return None
    try:
        name = json.loads(found.group(1))
        tenant = None if found.group(2) is None else json.loads(found.group(2))
    except ValueError:
        return None
    if not isinstance(name, str) or not isinstance(tenant, str | None):
        return None
    return name[:40], tenant


def found_proposal(places: Sequence[Path], suite: str) -> Path | None:
    """The first of `places` that holds a proposal written for `suite`. A file
    of the name written for another suite is not this one's."""
    for place in places:
        if place.is_file() and proposed_for(place) == suite:
            return place
    return None


@dataclass(frozen=True, slots=True)
class Mark:
    """What the file says of a value after it: a placeholder, a value the
    assistant wrote and no run measured, or the assistant's draft rubric."""

    kind: MarkKind
    text: str


@dataclass(frozen=True, slots=True)
class ProposedParam:
    """One key of a check, as the file holds it: `inner.threshold` for a key
    of the inner table of a `repeated`."""

    key: str
    value: object
    mark: Mark | None


@dataclass(frozen=True, slots=True)
class ProposedBlock:
    """One `[[assertions]]` of the file, in the file's order: its type, its
    name where it has one, why it is there, what the assistant said of it,
    and its keys."""

    type: str
    name: str | None
    why: tuple[str, ...]
    said: tuple[str, ...]
    params: tuple[ProposedParam, ...]


@dataclass(frozen=True, slots=True)
class ProposalFile:
    """A proposal as it stands on disk. `declaration` is its `[suite]` and
    `[capture]` as read; `notes` the comments beside them; `checks` in the
    file's order, nothing ranked (ADR 0037 §6); the counterexample and the
    calibration skeleton as the file words them; `unread` every comment line
    the reader could not place."""

    path: Path
    suite: str
    tenant: str | None
    header: tuple[str, ...]
    declaration: Mapping[str, Mapping[str, object]]
    notes: tuple[str, ...]
    checks: tuple[ProposedBlock, ...]
    counterexample: str | None
    calibration: str | None
    unread: tuple[str, ...]


def _comment(line: str) -> str | None:
    stripped = line.strip()
    if not stripped.startswith("#"):
        return None
    return stripped[1:].removeprefix(" ")


def _mark(line: str) -> Mark | None:
    for text, kind in _MARKS:
        at = line.rfind("  " + text)
        if at != -1:
            return Mark(kind, line[at:].strip().removeprefix("# "))
    return None


@dataclass
class _Block:
    why: list[str]
    said: list[str]
    marks: dict[str, Mark]
    after: list[str]
    keyed: bool = False


def read_proposal(path: Path) -> ProposalFile:
    """The proposal at `path`, its values read by `read_toml` and what the
    comments say of them read from the text. Writes nothing; a refusal of
    `read_toml` (not UTF-8, not TOML) is a `UsageError` that locates it."""
    document = read_toml(path)
    text = path.read_text(encoding="utf-8")
    first = _first(path)
    lines = text.splitlines()

    header: list[str] = []
    notes: list[str] = []
    blocks: list[_Block] = []
    table = ""
    prefix = ""
    for line in lines:
        said = _comment(line)
        heading = _HEADER.match(line)
        if heading is not None:
            name = heading.group(2)
            if heading.group(1) and name == "assertions":
                blocks.append(_Block([], [], {}, []))
                table, prefix = "assertions", ""
            elif name.startswith("assertions.") and blocks:
                prefix = name.removeprefix("assertions.") + "."
            else:
                table, prefix = name, ""
            continue
        if not line.strip():
            if blocks and blocks[-1].keyed:
                blocks[-1].after.append("")
            continue
        if said is not None:
            if not table:
                header.append(said)
            elif table != "assertions":
                notes.append(said)
            else:
                block = blocks[-1]
                if block.keyed:
                    block.after.append(said)
                elif said.startswith("the assistant: ") or block.said:
                    block.said.append(said.strip())
                else:
                    block.why.append(said)
            continue
        key = _KEY.match(line)
        if key is not None and table == "assertions" and blocks:
            block = blocks[-1]
            block.keyed = True
            word = key.group(1)
            if word.startswith('"'):
                word = json.loads(word)
            mark = _mark(line)
            if mark is not None:
                block.marks[prefix + word] = mark
            continue
        if key is not None and table != "assertions" and _mark(line) is not None:
            notes.append(line.strip())

    trailing = blocks[-1].after if blocks else []
    counterexample, calibration, unread = _paragraphs(trailing)
    # A file that is not the one suggest writes keeps its comments, unread.
    if first is None:
        unread = [*header, *unread]
        header = []

    assertions = document.get("assertions")
    values: list[Mapping[str, object]] = []
    if isinstance(assertions, list):
        for item in cast(list[object], assertions):
            if isinstance(item, Mapping):
                values.append(cast(Mapping[str, object], item))
    checks = tuple(
        _block(value, blocks[index] if index < len(blocks) else None)
        for index, value in enumerate(values)
    )
    declaration = {
        name: cast(Mapping[str, object], document[name])
        for name in ("suite", "capture")
        if isinstance(document.get(name), Mapping)
    }
    return ProposalFile(
        path=path,
        suite=first[0] if first is not None else str(_named(document) or path.name),
        tenant=first[1] if first is not None else None,
        header=tuple(header),
        declaration=declaration,
        notes=tuple(notes),
        checks=checks,
        counterexample=counterexample,
        calibration=calibration,
        unread=tuple(unread),
    )


def _named(document: Mapping[str, object]) -> object:
    suite = document.get("suite")
    return (
        cast(Mapping[str, object], suite).get("name")
        if isinstance(suite, Mapping)
        else None
    )


def _paragraphs(lines: Sequence[str]) -> tuple[str | None, str | None, list[str]]:
    """The comment paragraphs after the last check: the counterexample, the
    calibration skeleton, and what is neither."""
    paragraphs: list[list[str]] = [[]]
    for line in lines:
        if line == "":
            if paragraphs[-1]:
                paragraphs.append([])
            continue
        paragraphs[-1].append(line)
    counterexample: list[str] = []
    calibration: str | None = None
    unread: list[str] = []
    for paragraph in (p for p in paragraphs if p):
        opening = paragraph[0]
        if opening.startswith("The counterexample"):
            counterexample.extend(paragraph)
        elif opening.startswith("The calibration skeleton"):
            calibration = "\n".join(paragraph)
        else:
            unread.extend(paragraph)
    return ("\n".join(counterexample) or None), calibration, unread


def _block(value: Mapping[str, object], block: _Block | None) -> ProposedBlock:
    marks = {} if block is None else block.marks
    params: list[ProposedParam] = []
    for key, item in value.items():
        if key in ("type", "name"):
            continue
        if key == "inner" and isinstance(item, Mapping):
            for inner, deeper in cast(Mapping[str, object], item).items():
                where = f"inner.{inner}"
                params.append(ProposedParam(where, deeper, marks.get(where)))
            continue
        params.append(ProposedParam(key, item, marks.get(key)))
    said = () if block is None else tuple(block.said)
    return ProposedBlock(
        type=str(value.get("type", "")),
        name=None if value.get("name") is None else str(value.get("name")),
        why=() if block is None else tuple(block.why),
        said=said,
        params=tuple(params),
    )


#: What `--model` is given in the line to copy: the person's to choose.
MODEL_TO_CHOOSE = "<provider/model>"


def suggest_lines(
    found: ProposalFile | None,
    *,
    suite_arg: str | None,
    suite: str,
    tenant: str,
    root: Sequence[str],
) -> tuple[list[str], list[str]]:
    """`digline suggest` for this suite, without and with `--model`, as a
    person types them: shown, never run, because what a model costs is said
    before its call (ADR 0063 §4). For a suite that does not exist yet, the
    regime is the proposal's where there is one, and the person's to write
    where there is none. `suggest` never overwrites a proposal: the page says
    so where one is there."""
    if suite_arg is not None:
        plain = ["digline", "suggest", "--suite", suite_arg, *root]
    else:
        capture: Mapping[str, object] = (
            {} if found is None else found.declaration.get("capture", {})
        )
        regime = capture.get("repository")
        plain = [
            "digline",
            "suggest",
            "--suite",
            suite,
            "--tenant",
            tenant,
            "--repository",
            regime if isinstance(regime, str) else "<private|public>",
            *root,
        ]
    return plain, [*plain, "--model", MODEL_TO_CHOOSE]


def relative_to_root(place: Path, root: Path) -> str:
    """`place` as `digline where` says it: relative to the store's root."""
    return os.path.relpath(place.resolve(), root.resolve())
