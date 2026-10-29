"""The five keys `OUTPUT_VERSION` 5 renamed, and where their old names stand.

A bare old name cannot be searched for: `sent`, `artifacts`, `scope` and
`runs` are still keys in other shapes, on purpose (`test_output_version_5.py`).
So this file counts the forms that can only mean the renamed keys:

- **a qualified path**: `log.roll.sent`, `disclosure.artifacts`,
  `explain.scope`, `runs.runs`, `diff.runs`;
- **`artifacts=` inside a `Disclosure(` call** and **`scope=` inside an
  `explain_json(` call**, the Python parameters that moved with their keys.

A search for these does not answer zero, and zero is the wrong number: 25
lines keep one, each for a reason in one of five classes, and `KEPT` declares
them.

- **released history**, which is not rewritten: changelog entries of released
  versions;
- **an accepted record**, kept as written, with a dated note where its text
  became false;
- **a fixed decision's paragraph**, annotated and never rewritten, as ADR 0046
  did with the same paragraph;
- **the contract's record of the bump**, which names what it renamed;
- **the changelog lines that announce the renames**, which have to name the
  old parameter for whoever reads them against the last release.

The count is fixed and red both ways: a line more is a use that came back or a
mention nobody declared, and a declared line that is gone is a declaration
that no longer says anything.

**Each search carries its control in the same pass**: a form known to stand in
the tree, read by the same matcher over the same files, so a search that
answers 25 is a search that looks.

**Whole word, by the names gate's derivation** (`named_in` in
`packages/digline-mcp/tests/test_names_gate.py`): a path is continued only by
a letter or a digit touching it, as `str.isalnum` reads them. So
`` `diff.runs` `` and `diff.runs.left` are the path, and `diff.runsX` is not.

**This file is left out of the search**, by its own path: its table has to
name the old forms to declare where they stay.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import NamedTuple

ROOT = Path(__file__).resolve().parents[1]
THIS = Path(__file__).resolve().relative_to(ROOT).as_posix()

#: The old qualified paths, each with a path of the same kind known to stand
#: in the tree: its control.
QUALIFIED: dict[str, str] = {
    "log.roll.sent": "log.roll.silence",
    "disclosure.artifacts": "disclosure.run_metadata",
    "explain.scope": "delta.scope",
    "runs.runs": "span.runs",
    "diff.runs": "diff.sides",
}
#: Each renamed parameter as `(call, parameter)`, with its control: another
#: parameter of the same call.
PARAMETERS: dict[tuple[str, str], tuple[str, str]] = {
    ("Disclosure", "artifacts"): ("Disclosure", "run_metadata"),
    ("explain_json", "scope"): ("explain_json", "exit_code"),
}


class Kept(NamedTuple):
    path: str
    #: Text the line carries, so a declared line is found wherever the file
    #: around it moves.
    excerpt: str
    reason: str


HISTORY = "released history, not rewritten"
RECORD = "an accepted record, kept as written and noted where it became false"
FIXED = "a fixed decision's paragraph, annotated and not rewritten"
BUMP = "the contract's record of the bump"
ANNOUNCED = "a changelog line that announces a rename"

_0042 = "docs/adr/0042-the-two-boundaries-of-an-artifact.md"
_0046 = "docs/adr/0046-a-widening-is-a-declared-class.md"
_0011 = "docs/adr/0011-the-mcp-server.md"
_CONTRACT = "src/digline/wire/contract.py"

KEPT: tuple[Kept, ...] = (
    Kept(
        "CHANGELOG.md", "`Disclosure(artifacts=True)` its whole text crossed", HISTORY
    ),
    Kept("CHANGELOG.md", "URL. `Disclosure(artifacts=True)` is still needed", HISTORY),
    Kept("CHANGELOG.md", "A suite with `Disclosure(artifacts=True)`", HISTORY),
    Kept(
        "docs/adr/0002-three-worlds-and-where-the-data-lives.md",
        "> unless the suite declares `Disclosure(artifacts=True)`.",
        RECORD,
    ),
    Kept(_0011, "`Disclosure(artifacts=True)`, per ADR 0003 §4", RECORD),
    Kept(_0011, "5. `Disclosure(artifacts=True)` lets artifact text through", RECORD),
    Kept(
        "docs/adr/0012-the-reading.md",
        "**Artifacts.** `Disclosure(artifacts=True)` governs",
        RECORD,
    ),
    Kept(_0042, "by a pointer only. `Disclosure(artifacts=True)` stays", RECORD),
    Kept(_0042, '`Disclosure(artifacts=True)`"*. That stays true', RECORD),
    Kept(_0042, "`Disclosure(artifacts=True)` the text crosses a boundary", RECORD),
    Kept(_0042, "when `disclosure.artifacts` is true", RECORD),
    Kept(_0042, "`notes.md` under `Disclosure(artifacts=True)`", RECORD),
    Kept(_0042, "five pages say `Disclosure(artifacts=True)`", RECORD),
    Kept(_0042, "`Disclosure(artifacts=True)`. `report --redacted` exits 64", RECORD),
    Kept(_0042, "as well as under `Disclosure(artifacts=True)`, and no", RECORD),
    Kept(_0046, 'declares `Disclosure(artifacts=True)`."* No other section', RECORD),
    Kept(_0046, "the pages that say `Disclosure(artifacts=True)` is what", RECORD),
    Kept("CLAUDE.md", "`Disclosure(artifacts=True)`: a prompt carries", FIXED),
    Kept(_CONTRACT, "`log.roll.sent` is `asked`", BUMP),
    Kept(_CONTRACT, "`disclosure.artifacts` is `artifact_text`", BUMP),
    Kept(_CONTRACT, "`explain.scope` is `reading`", BUMP),
    Kept(_CONTRACT, "`runs.runs` is `rows`", BUMP),
    Kept(_CONTRACT, "`diff.runs` is `sides`", BUMP),
    Kept(
        "CHANGELOG.md",
        "**`Disclosure(artifacts=...)` is now `Disclosure(artifact_text=...)`",
        ANNOUNCED,
    ),
    Kept(
        "CHANGELOG.md",
        "**`explain_json(scope=...)` is now `explain_json(reading=...)`",
        ANNOUNCED,
    ),
)


def stands_in(text: str, name: str) -> bool:
    """Whether `name` stands in `text` as a name: the names gate's rule."""
    start = text.find(name)
    while start != -1:
        end = start + len(name)
        before = text[start - 1] if start > 0 else ""
        after = text[end] if end < len(text) else ""
        if not before.isalnum() and not after.isalnum():
            return True
        start = text.find(name, start + 1)
    return False


#: A parameter is a word of its own followed by `=`: `artifact_text=` and
#: `some_artifacts=` are not `artifacts=`. A call is its name as a word too:
#: `explain_json(` is not `explain_json_x(` or `my_explain_json(`.
def _parameter(name: str) -> re.Pattern[str]:
    return re.compile(rf"(?<![A-Za-z0-9_]){name}\s*=")


#: How far a call is read for its closing parenthesis. A call in prose
#: that never closes is not read to the end of the file.
_CALL_REACH = 400


def passes(text: str, call: str, name: str) -> list[int]:
    """The 0-based line of each `call(` in `text` whose arguments pass `name`,
    read to the call's closing parenthesis, so a call that spans lines is read
    whole."""
    pattern = _parameter(name)
    lines: list[int] = []
    for opened in re.finditer(rf"(?<![A-Za-z0-9_]){call}\(", text):
        depth, at = 1, opened.end()
        limit = min(len(text), at + _CALL_REACH)
        while at < limit and depth:
            depth += {"(": 1, ")": -1}.get(text[at], 0)
            at += 1
        if pattern.search(text[opened.end() : at]):
            lines.append(text.count("\n", 0, opened.start()))
    return lines


def _tracked(root: Path) -> list[tuple[str, str]]:
    tracked = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z"],
        check=True,
        capture_output=True,
    ).stdout.split(b"\0")
    texts: list[tuple[str, str]] = []
    for raw in tracked:
        path = raw.decode()
        if not path or path == THIS:
            continue
        try:
            texts.append((path, (root / path).read_text(encoding="utf-8")))
        except (UnicodeDecodeError, FileNotFoundError, IsADirectoryError):
            continue
    return texts


def search(
    paths: tuple[str, ...], parameters: tuple[tuple[str, str], ...], root: Path = ROOT
) -> dict[object, list[tuple[str, str]]]:
    """Every `(path, line)` where each qualified path stands, and where each
    `(call, parameter)` is passed, in one pass over the tracked text files,
    this file left out."""
    found: dict[object, list[tuple[str, str]]] = {n: [] for n in (*paths, *parameters)}
    for path, text in _tracked(root):
        lines = text.splitlines()
        for line in lines:
            for name in paths:
                if stands_in(line, name):
                    found[name].append((path, line))
        for call, name in parameters:
            found[call, name].extend(
                (path, lines[at]) for at in passes(text, call, name)
            )
    return found


def old_lines(found: dict[object, list[tuple[str, str]]]) -> list[tuple[str, str]]:
    """The lines that carry any old form, each once."""
    seen: dict[tuple[str, str], None] = {}
    for name in (*QUALIFIED, *PARAMETERS):
        for hit in found[name]:
            seen.setdefault(hit)
    return list(seen)


def unexplained(
    found: list[tuple[str, str]], kept: tuple[Kept, ...] = KEPT
) -> list[str]:
    """A line found that no declaration covers, and a declaration no line meets."""
    problems: list[str] = []
    met: set[Kept] = set()
    for path, line in found:
        covering = [k for k in kept if k.path == path and k.excerpt in line]
        if covering:
            met.update(covering)
        else:
            problems.append(
                f"{path}: names an old key and is not declared: {line.strip()}"
            )
    problems.extend(
        f"{k.path}: declared ({k.reason}) and no longer names an old key: {k.excerpt}"
        for k in kept
        if k not in met
    )
    return problems


def test_the_old_keys_stand_only_where_they_are_declared() -> None:
    found = search(
        (*QUALIFIED, *QUALIFIED.values()), (*PARAMETERS, *PARAMETERS.values())
    )
    controls: list[object] = [*QUALIFIED.values(), *PARAMETERS.values()]
    blind = [control for control in controls if not found[control]]
    assert not blind, f"the search found no control, so it did not look: {blind}"
    lines = old_lines(found)
    problems = unexplained(lines)
    assert not problems, "\n".join(problems)
    assert len(lines) == len(KEPT) == 25


def test_the_declared_lines_are_25_in_five_classes() -> None:
    assert len(KEPT) == 25
    assert {k.reason for k in KEPT} == {HISTORY, RECORD, FIXED, BUMP, ANNOUNCED}
    assert len(set(KEPT)) == len(KEPT), "a line declared twice"


def test_the_matcher_is_the_names_gates() -> None:
    assert stands_in("`diff.runs`", "diff.runs")
    assert stands_in('"$.diff.runs.left"', "diff.runs")
    assert stands_in("_runs.runs", "runs.runs")
    assert not stands_in("diff.runsX", "diff.runs")
    assert not stands_in("xdiff.runs", "diff.runs")
    assert not stands_in("log.roll.sentinel", "log.roll.sent")


def test_a_parameter_is_read_inside_the_call_only() -> None:
    d = ("Disclosure", "artifacts")
    assert passes("Disclosure(artifacts=True)", *d) == [0]
    assert passes(
        "x\nDisclosure(\n    run_metadata=frozenset(),\n    artifacts=True,\n)", *d
    ) == [1]
    assert passes("Disclosure(artifacts = True)", *d) == [0]
    assert passes("Disclosure(artifact_text=True)", *d) == []
    assert passes("Suite(artifacts=[path])", *d) == []
    assert passes("Disclosure(some_artifacts=True)", *d) == []
    assert passes("Disclosure(f(x), run_metadata=s) artifacts=", *d) == []
    e = ("explain_json", "scope")
    assert passes("explain_json(facts(run), scope='run', exit_code=0)", *e) == [0]
    assert passes("explain_json(facts(run, scope=s), reading='run')", *e) == [0]
    assert passes("explain_json(f, reading='run', exit_code=0)", *e) == []
    assert passes("my_explain_json(f, scope='run')", *e) == []
    assert passes("fact_json(f, scope='run')", *e) == []


def test_a_line_more_and_a_line_missing_are_both_red() -> None:
    """Both directions, on a listing built here rather than the tree."""
    found = [(k.path, f"... {k.excerpt} ...") for k in KEPT]
    assert unexplained(found) == []
    more = [*found, ("docs/api.md", "set `Disclosure(artifacts=True)` in the suite")]
    assert unexplained(more) == [
        "docs/api.md: names an old key and is not declared: "
        "set `Disclosure(artifacts=True)` in the suite"
    ]
    missing = found[1:]
    assert unexplained(missing) == [
        f"{KEPT[0].path}: declared ({KEPT[0].reason}) and no longer names an old "
        f"key: {KEPT[0].excerpt}"
    ]
