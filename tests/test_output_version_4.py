"""`OUTPUT_VERSION` 4: a verdict's check is named `assertion` everywhere. (#678)

Until 4, the MCP tools `get_run` and `get_baseline` named a verdict's check
`name`, and so did each aggregate row of `list_runs`, while the run file,
`compare --json`'s `deltas`, `diff --json`'s `checks` and `explain --json`'s
`facts` named the same field `assertion`. Inside one server the same verdict,
under the same `assertion_id`, had two spellings.

A renamed key breaks a consumer that reads the old one, so it is a bump, and
there is no alias: a document carrying both would keep the incoherence the
bump removes. The rename is the only change version 4 makes to the contract.
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

#: The two shapes a verdict is written in by `digline.wire.run`.
VERDICT_SHAPES = ("run_document.verdict", "runs.verdict")


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


def test_the_contract_names_a_verdicts_check_assertion() -> None:
    for shape in VERDICT_SHAPES:
        keys = _SHAPES[shape]
        assert "assertion" in keys, shape
        assert "name" not in keys, shape


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
    for verdict in verdicts:
        assert verdict["assertion"] == "llm_rubric"
        assert "name" not in verdict


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
    "4: **the first bump that renames a key.**",
    "No alias carries the old name beside the new one",
)
#: What `docs/api.md` says about it.
API_SAYS = (
    "**Version 4 renames a key.**",
    "No document carries both.",
)


def test_the_contract_record_names_the_rename() -> None:
    text = _folded(CONTRACT, comments=True)
    missing = [sentence for sentence in CONTRACT_SAYS if sentence not in text]
    assert not missing, missing


def test_api_md_names_the_rename() -> None:
    text = _folded(API)
    missing = [sentence for sentence in API_SAYS if sentence not in text]
    assert not missing, missing
