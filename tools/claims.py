"""The gate on absolute claims about where data goes.

"No data leaves" is the sentence a reader in world 3 quotes back, and the one
that is easiest to write a notch stronger than the code holds. Two lists:

- **Tier 1** is never admitted. Each phrase has been written somewhere and
  was false as written; it is rewritten, not registered.
- **Tier 2** is admitted only with an entry in `tools/claims_register.toml`,
  and an entry is admitted only when the claim is **anchored**: it names a file
  in this repository and the text in it that makes the sentence true. Being
  harmless is not a reason. An entry is checked on both ends — its quote must
  still be in its file, and its anchor must still hold the evidence — so a
  claim that outlives its reason fails here instead of drifting.

What is read: every tracked Markdown file, and the docstrings of the Python
under `src/`, `packages/` and `examples/`. Not `CHANGELOG.md`, `docs/adr/` or
`tests/`: those quote what was once written, which is how they are meant to
be read.

The text is compared lowercased, with runs of whitespace as one space and
Markdown's `*` dropped, so a phrase wrapped across two lines or set in bold is
the same phrase. A phrase matches on word boundaries: "data never leaves" does
not match inside "metadata never leaves".
"""

from __future__ import annotations

import ast
import re
import subprocess
import tomllib
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

__all__ = [
    "REGISTER",
    "TIER_1",
    "TIER_2",
    "Claim",
    "check",
    "covered",
    "load_register",
    "tracked",
]

TIER_1 = (
    "payload never leaves",
    "the payload never leaves the perimeter",
    "nothing leaves your machine",
    "nothing leaves the machine",
    "nothing ever leaves",
    "no data ever leaves",
    "data never leaves",
)

TIER_2 = (
    "no data leaves",
    "never leaves the perimeter",
    "never leaves your repository",
    "nothing is sent",
)

REGISTER = "tools/claims_register.toml"

_CODE_ROOTS = ("src/", "packages/", "examples/")
_EXCLUDED_DIRS = ("docs/adr/",)
_EXCLUDED_NAMES = ("CHANGELOG.md",)


@dataclass(frozen=True)
class Claim:
    """One admitted sentence, and the code that makes it true."""

    file: str
    quote: str
    anchor_path: str
    anchor_contains: str
    why: str
    since: str


@dataclass(frozen=True)
class _Text:
    """Normalised text, and the source line each of its characters came from."""

    text: str
    lines: tuple[int, ...]

    def line(self, offset: int) -> int:
        return self.lines[offset]


def _normalise(raw: str, first_line: int = 1) -> _Text:
    out: list[str] = []
    lines: list[int] = []
    line = first_line
    space = False
    for char in raw:
        if char == "\n":
            line += 1
        if char.isspace():
            space = bool(out)
            continue
        if char == "*":
            continue
        if space:
            out.append(" ")
            lines.append(line)
            space = False
        for lowered in char.lower():
            out.append(lowered)
            lines.append(line)
    return _Text("".join(out), tuple(lines))


def _phrase(phrase: str) -> re.Pattern[str]:
    return re.compile(r"\b" + re.escape(_normalise(phrase).text) + r"\b")


def covered(path: str) -> bool:
    """Whether the gate reads this repository-relative path."""
    parts = path.split("/")
    if "tests" in parts[:-1] or parts[-1] in _EXCLUDED_NAMES:
        return False
    if any(path.startswith(prefix) for prefix in _EXCLUDED_DIRS):
        return False
    if path.endswith(".md"):
        return True
    return path.endswith(".py") and path.startswith(_CODE_ROOTS)


def _texts(path: str, raw: str) -> list[_Text]:
    """What of a file is prose: all of a Markdown file, a module's docstrings."""
    if not path.endswith(".py"):
        return [_normalise(raw)]
    texts: list[_Text] = []
    for node in ast.walk(ast.parse(raw)):
        if not isinstance(
            node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef
        ):
            continue
        body = node.body
        if (
            body
            and isinstance(first := body[0], ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            texts.append(_normalise(first.value.value, first.lineno))
    return texts


def _string(entry: dict[str, Any], key: str, where: str) -> str:
    value = entry.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{where}: `{key}` is missing or empty")
    return value


def load_register(path: Path) -> list[Claim]:
    """The register, every field required: an entry without its anchor is the
    thing this gate exists to refuse."""
    with path.open("rb") as handle:
        document = tomllib.load(handle)
    claims: list[Claim] = []
    entries: list[Any] = document.get("claim", [])
    for index, entry in enumerate(entries, start=1):
        where = f"{path.name}, claim {index}"
        if not isinstance(entry, dict):
            raise ValueError(f"{where}: not a table")
        table: dict[str, Any] = entry  # pyright: ignore[reportUnknownVariableType]
        anchor = table.get("anchor")
        if not isinstance(anchor, dict):
            raise ValueError(f"{where}: `anchor` is missing")
        anchor_table: dict[str, Any] = anchor  # pyright: ignore[reportUnknownVariableType]
        claims.append(
            Claim(
                file=_string(table, "file", where),
                quote=_string(table, "quote", where),
                anchor_path=_string(anchor_table, "path", where),
                anchor_contains=_string(anchor_table, "contains", where),
                why=_string(table, "why", where),
                since=_string(table, "since", where),
            )
        )
    return claims


def tracked(root: Path) -> list[str]:
    """The files git knows about: what is committed is what is published."""
    listing = subprocess.run(
        ["git", "-C", str(root), "ls-files"],
        capture_output=True,
        text=True,
        check=True,
    )
    return listing.stdout.splitlines()


def _read(root: Path, path: str) -> str | None:
    try:
        return (root / path).read_text(encoding="utf-8")
    except (FileNotFoundError, IsADirectoryError):
        return None


def check(root: Path, paths: Iterable[str], register: Sequence[Claim]) -> list[str]:
    """Every problem, one line each, `path:line: what`. Empty is a pass."""
    problems: list[str] = []
    by_file: dict[str, list[Claim]] = {}
    for claim in register:
        by_file.setdefault(claim.file, []).append(claim)

    for claim in register:
        where = f"{REGISTER}: {claim.file}"
        if not covered(claim.file):
            problems.append(f"{where}: this file is not read by the gate")
            continue
        raw = _read(root, claim.file)
        quote = _normalise(claim.quote).text
        if raw is None:
            problems.append(f"{where}: the file does not exist")
        elif not any(quote in text.text for text in _texts(claim.file, raw)):
            problems.append(f"{where}: the quote is no longer there — {claim.quote!r}")
        evidence = _read(root, claim.anchor_path)
        if evidence is None:
            problems.append(f"{where}: the anchor {claim.anchor_path} does not exist")
        elif claim.anchor_contains not in evidence:
            problems.append(
                f"{where}: the anchor {claim.anchor_path} no longer contains "
                f"{claim.anchor_contains!r}"
            )

    tier_1 = [(phrase, _phrase(phrase)) for phrase in TIER_1]
    tier_2 = [(phrase, _phrase(phrase)) for phrase in TIER_2]
    for path in sorted(p for p in paths if covered(p)):
        raw = _read(root, path)
        if raw is None:
            continue
        quotes = [_normalise(claim.quote).text for claim in by_file.get(path, [])]
        for text in _texts(path, raw):
            for phrase, pattern in tier_1:
                for match in pattern.finditer(text.text):
                    problems.append(
                        f"{path}:{text.line(match.start())}: tier 1, {phrase!r} "
                        "is never admitted — rewrite it"
                    )
            admitted = [
                (found.start(), found.end())
                for quote in quotes
                for found in re.finditer(re.escape(quote), text.text)
            ]
            for phrase, pattern in tier_2:
                for match in pattern.finditer(text.text):
                    if not any(
                        start <= match.start() and match.end() <= end
                        for start, end in admitted
                    ):
                        problems.append(
                            f"{path}:{text.line(match.start())}: tier 2, {phrase!r} "
                            f"with no entry in {REGISTER} — rewrite it, or anchor it"
                        )
    return problems
