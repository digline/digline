"""`OUTPUT_VERSION` 4: one concept, one name. (#678)

Until 4, the value a verdict's `score.name` holds went by four names: `assertion`
in the run file, `compare`'s `deltas`, `diff`'s `checks` and `explain`'s
`facts`; `name` in `get_run`, `get_baseline`, `list_runs` and `log`'s
`spread`; `check` in `shape`; `rule` in `suite_deltas`. And `log` said
`answered` for what every sentence calls *reported*.

A renamed key breaks a consumer that reads the old one, so it is a bump, and
there is no alias: a document carrying both would keep the incoherence the
bump removes. The renames are the only change version 4 makes to the
contract's keys.
"""

from __future__ import annotations

import dataclasses
import re
from pathlib import Path
from typing import Any, cast

from tests.test_wire_boundary import loaded_run

from digline.core import Disclosure
from digline.store import Listing
from digline.wire import OUTPUT_VERSION, run_document, runs_json
from digline.wire.contract import _SHAPES  # pyright: ignore[reportPrivateUsage]

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


def test_the_output_version_is_4() -> None:
    assert OUTPUT_VERSION == 4
    assert run_document(loaded_run(), Disclosure())["output_version"] == 4


#: Every key version 4 renamed, as `(shape, before, after)`. One concept, one
#: name: each `assertion` here holds a verdict's `score.name`, the value the run
#: file and `compare`'s `deltas` call `assertion`. `reported` is the verb every
#: sentence already used for `resolved_model` (ADR 0020, amended).
RENAMED = (
    ("run_document.verdict", "name", "assertion"),
    ("runs.verdict", "name", "assertion"),
    ("log.spread", "name", "assertion"),
    ("shape", "check", "assertion"),
    ("rule_delta", "rule", "assertion"),
    ("log.sighting", "answered", "reported"),
    ("log.span", "answered", "reported"),
)

#: Kept as they are, on purpose. `fact.setting.name` holds a rule's name, a
#: configuration key or an artifact's path according to `kind`: a vocabulary,
#: not a rename. `calibration.check` is the name the suite declared, and a
#: verdict's `score.name` "is whatever the assertion chose to call its
#: `Score`, and a third-party one may call it otherwise" (`CalibrationBand`;
#: ADR 0024 §4.7, amended 2026-09-26): calling it `assertion` would claim an
#: identity the core denies.
KEPT = (("fact.setting", "name"), ("calibration", "check"))


def test_every_rename_is_in_the_contract() -> None:
    for shape, before, after in RENAMED:
        keys = _SHAPES[shape]
        assert after in keys, (shape, after)
        assert before not in keys, (shape, before)


def test_the_names_that_are_not_renames_are_kept() -> None:
    for shape, key in KEPT:
        assert key in _SHAPES[shape], (shape, key)
        assert "assertion" not in _SHAPES[shape], shape


def test_get_run_names_a_verdicts_check_assertion() -> None:
    """Each case's verdicts and each aggregate verdict, which `_verdict_document`
    builds for both."""
    run = loaded_run()
    run = dataclasses.replace(run, aggregate=(run.results[0].verdicts[0],))
    document = run_document(run, Disclosure())
    results = cast(list[dict[str, Any]], document["results"])
    aggregate = cast(list[dict[str, Any]], document["aggregate"])
    verdicts = [v for case in results for v in case["verdicts"]] + aggregate
    assert aggregate, "the control: the aggregate carries a verdict"
    expected = [v.score.name for case in run.results for v in case.verdicts] + [
        v.score.name for v in run.aggregate
    ]
    assert [verdict["assertion"] for verdict in verdicts] == expected
    assert all("name" not in verdict for verdict in verdicts)


def test_list_runs_names_an_aggregate_verdicts_check_assertion() -> None:
    run = loaded_run()
    run = dataclasses.replace(run, aggregate=(run.results[0].verdicts[0],))
    document = runs_json(
        [("k", run)],
        tenant="acme",
        suite="privacy",
        baseline_key=None,
        listing=Listing(runs=()),
    )
    rows = cast(list[dict[str, Any]], document["runs"])
    (verdict,) = rows[0]["aggregate"]
    assert verdict["assertion"] == "llm_rubric"
    assert "name" not in verdict


#: What the record beside the constant says about the bump, in its own voice.
CONTRACT_SAYS = (
    "4: **the first bump that renames keys.** One concept, one name",
    "No alias carries an old name beside its new one",
    "**Two names stay, and are not renames.**",
)
#: What `docs/api.md` says about it.
API_SAYS = (
    "**Version 4 renames keys, and one concept has one name.**",
    "No document carries both an old name and its new one",
)


def test_the_contract_record_names_the_rename() -> None:
    text = _folded(CONTRACT, comments=True)
    missing = [sentence for sentence in CONTRACT_SAYS if sentence not in text]
    assert not missing, missing


def test_api_md_names_the_rename() -> None:
    text = _folded(API)
    missing = [sentence for sentence in API_SAYS if sentence not in text]
    assert not missing, missing
