"""`OUTPUT_VERSION` 5: five keys, each a name that carried two things.

The name pass of 2026-10-27 found names that hold different concepts in
different shapes. These five are the ones whose fix touches no stored document:

- `sent` on a roll held one model, and on a sighting and a span a list;
- `artifacts` in `disclosure` held a flag, and on a run the files;
- `scope` at the top of `explain` held which document was read, and on a
  delta, a check and a rule a case or the run;
- `runs` on `list_runs` held the rows, and on `log` a count;
- `runs` on `diff` held the two sides, and on `log` a count.

A renamed key breaks a consumer that reads the old one, so it is a bump, and
there is no alias. Each test below builds the document and reads it: the new
name is there and the old one is not. Where the old name stays on purpose, in
another shape, the contract is read for it too.
"""

from __future__ import annotations

import dataclasses
import re
from pathlib import Path
from typing import Any, cast

from tests.test_wire_boundary import loaded_run

from digline.core import Disclosure
from digline.core import diff as core_diff
from digline.report import facts
from digline.report.log import Roll
from digline.store import Listing
from digline.wire import (
    OUTPUT_VERSION,
    diff_json,
    explain_json,
    run_document,
    runs_json,
)
from digline.wire.contract import _SHAPES  # pyright: ignore[reportPrivateUsage]
from digline.wire.log import roll_json

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "src" / "digline" / "wire" / "contract.py"
API = ROOT / "docs" / "api.md"


def _folded(path: Path, *, comments: bool = False) -> str:
    """The file's text with line breaks folded, and with the comment markers of
    a Python record taken off, so a sentence the file wraps is still found."""
    text = path.read_text(encoding="utf-8")
    if comments:
        text = re.sub(r"^\s*#:? ?", "", text, flags=re.MULTILINE)
    return " ".join(text.split())


def test_the_output_version_is_5() -> None:
    assert OUTPUT_VERSION == 5
    assert run_document(loaded_run(), Disclosure())["output_version"] == 5


#: Every key version 5 renamed, as `(shape, before, after)`.
RENAMED = (
    ("log.roll", "sent", "asked"),
    ("disclosure", "artifacts", "artifact_text"),
    ("explain", "scope", "reading"),
    ("runs", "runs", "rows"),
    ("diff", "runs", "sides"),
    ("diff.full", "runs", "sides"),
)

#: The other half of each name, kept where it holds its own concept.
KEPT = (
    ("log.sighting", "sent"),
    ("log.span", "sent"),
    ("run_document", "artifacts"),
    ("delta", "scope"),
    ("fact.check", "scope"),
    ("diff.check", "scope"),
    ("rule_delta", "scope"),
    ("log", "runs"),
    ("log.span", "runs"),
    ("log.spread", "runs"),
)


def test_every_rename_is_in_the_contract() -> None:
    for shape, before, after in RENAMED:
        keys = _SHAPES[shape]
        assert after in keys, (shape, after)
        assert before not in keys, (shape, before)


def test_the_other_half_of_each_name_is_kept() -> None:
    for shape, key in KEPT:
        assert key in _SHAPES[shape], (shape, key)


def test_a_roll_says_asked() -> None:
    roll = Roll(
        side="target",
        provider="anthropic",
        sent="claude-sonnet-5",
        before="claude-sonnet-5-20260901",
        after="claude-sonnet-5-20261001",
        last_before="2026-09-30T10:00:00+00:00",
        first_after="2026-10-01T10:00:00+00:00",
        silent_between=0,
    )
    document = roll_json(roll)
    assert document["asked"] == "claude-sonnet-5"
    assert "sent" not in document


def test_the_disclosure_says_artifact_text() -> None:
    document = run_document(loaded_run(), Disclosure(artifact_text=True))
    disclosure = cast(dict[str, Any], document["disclosure"])
    assert disclosure["artifact_text"] is True
    assert "artifacts" not in disclosure
    assert "artifacts" in document, "the control: the run's own `artifacts` stays"


def test_explain_says_reading() -> None:
    run = loaded_run()
    document = explain_json(facts(run), reading="run", exit_code=0)
    assert document["reading"] == "run"
    assert "scope" not in document


def test_list_runs_says_rows() -> None:
    document = runs_json(
        [("k", loaded_run())],
        tenant="acme",
        suite="privacy",
        baseline_key=None,
        listing=Listing(runs=()),
    )
    rows = cast(list[dict[str, Any]], document["rows"])
    assert [row["key"] for row in rows] == ["k"]
    assert "runs" not in document


def test_diff_says_sides() -> None:
    run = loaded_run()
    other = dataclasses.replace(run, created_at="2026-09-09T10:00:00+00:00")
    for full in (False, True):
        document = diff_json(
            core_diff(run, other),
            run,
            other,
            keys=("a", "b"),
            labels=("a", "b"),
            sentence="",
            full=full,
        )
        sides = cast(dict[str, Any], document["sides"])
        assert (sides["left"]["key"], sides["right"]["key"]) == ("a", "b")
        assert "runs" not in document


#: What the record beside the constant says about the bump, in its own voice.
CONTRACT_SAYS = (
    "5: **a bump that renames five keys, each a name that carried two things.**",
    "No alias carries an old name beside its new one, as at 4.",
    "**`reported` stays** on `log --json`'s sightings and spans",
)
#: What `docs/api.md` says about it.
API_SAYS = (
    "**Version 5 renames five keys, each to the one thing it holds.**",
    "what moved is the Python field behind it, `Sighting.answered` and "
    "`IdentitySpan.answered`, which is `reported` too.",
    "key is `output_version`, currently `5`.",
)


def test_the_contract_record_names_the_rename() -> None:
    text = _folded(CONTRACT, comments=True)
    missing = [sentence for sentence in CONTRACT_SAYS if sentence not in text]
    assert not missing, missing


def test_api_md_names_the_rename() -> None:
    text = _folded(API)
    missing = [sentence for sentence in API_SAYS if sentence not in text]
    assert not missing, missing
