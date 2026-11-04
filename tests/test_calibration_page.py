"""`docs/calibration.md` is a run, not a description of one.

The page holds a suite and the reading of its run. This runs that suite, as
the page says to, and holds the page to what digline printed: the `explain`
block line for line, the two `--json` facts it quotes, and the counts and the
reason it quotes from the run document. A change to what explain says, or to
the convention the matrix counts by, turns this red before the page is wrong.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest
from tests._helpers import cli

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "docs" / "calibration.md"


def blocks(kind: str) -> list[str]:
    text = PAGE.read_text(encoding="utf-8")
    return re.findall(rf"```{kind}\n(.*?)```", text, flags=re.DOTALL)


@pytest.fixture(scope="module")
def ran(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    root = tmp_path_factory.mktemp("calibration-page")
    [suite] = blocks("python")
    (root / "suite.py").write_text(suite, encoding="utf-8")
    assert cli(root, "run", "--suite", "suite.py").returncode == 0
    explained = cli(root, "explain", "--suite", "suite.py", "--run", "latest")
    as_json = cli(root, "explain", "--suite", "suite.py", "--run", "latest", "--json")
    [document] = (root / ".digline" / "acme" / "runs" / "refunds").glob("*.json")
    return {
        "code": explained.returncode,
        "text": explained.stdout,
        "facts": json.loads(as_json.stdout)["facts"],
        "run": json.loads(document.read_text(encoding="utf-8")),
    }


def test_the_explain_block_is_what_explain_prints(ran: dict[str, Any]) -> None:
    [console] = blocks("console")
    printed = [line for line in console.splitlines() if not line.startswith("$ ")]
    assert printed == ran["text"].rstrip("\n").splitlines()
    assert ran["code"] == 1


def test_the_two_json_facts_are_what_explain_json_carries(ran: dict[str, Any]) -> None:
    quoted = [json.loads(block) for block in blocks("json") if '"kind"' in block]
    assert [fact["kind"] for fact in quoted] == ["reviewed", "calibration"]
    for fact in quoted:
        assert fact in ran["facts"]


def test_the_matrix_counts_and_reason_are_the_run_documents(
    ran: dict[str, Any],
) -> None:
    [accuracy] = [v for v in ran["run"]["aggregate"] if v["assertion"] == "accuracy"]
    [reason] = [block.strip() for block in blocks("text") if "accuracy" in block]
    assert reason == accuracy["reason"]
    [counts] = [json.loads(b) for b in blocks("json") if "true_positive" in b]
    assert counts == {key: accuracy["metadata"][key] for key in counts}
    assert counts["false_positive"] == 2


def test_the_page_is_linked_from_the_api_reference_and_the_recorder() -> None:
    for page in ("api.md", "record.md"):
        assert "(calibration.md" in (ROOT / "docs" / page).read_text(encoding="utf-8")
