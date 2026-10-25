"""`OUTPUT_VERSION` 3, and what it says about the version before it. (#669)

0.33.0 changed what `noise_min`, `noise_max`, `noise_samples` and both
`within_noise` mean, under `output_version: 2`, and nothing went red: the key
table sees keys and types, and the rule that a change of meaning is a bump had
no test and was not applied. These tests hold what the bump writes down, in the
places a reader meets it. They are goldens: they hold the words, not the
meaning, which only review can judge (`wire/contract.py` says so twice).

**The ambiguity of version 2 is held in two places, one test each**, so a
sentence taken out of one place is red there and nowhere else: the contract's
own record, which a contributor reads beside the constant, and `docs/api.md`,
which a consumer reads.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "src" / "digline" / "wire" / "contract.py"
API = ROOT / "docs" / "api.md"
RELEASING = ROOT / "RELEASING.md"


def _folded(path: Path, *, comments: bool = False) -> str:
    """The file's text with line breaks folded, and with the comment markers of
    a Python record taken off, so a sentence the file wraps is still found."""
    text = path.read_text(encoding="utf-8")
    if comments:
        text = re.sub(r"^\s*#:? ?", "", text, flags=re.MULTILINE)
    return " ".join(text.split())


#: What both places must say, in their own voice.
CONTRACT_SAYS = (
    "**Version 2 means two things, and nothing in a document tells them apart.**",
    "names the digline that **wrote the run**, not the one that produced the "
    "comparison",
)
API_SAYS = (
    "So version 2 means two things, and nothing in a document tells them apart.",
    "names the digline that wrote the run, not the one that produced the comparison",
)

#: The rules `RELEASING.md` gains with the bump.
RELEASING_SAYS = (
    "**A bump of `OUTPUT_VERSION` is a minor.**",
    "It is not added to the minor's list by analogy: it is derived from the "
    "patch's rule.",
    "**The rule of 2026-10-12 covers any value, not only a number.**",
    "`within_noise` is the case that showed it",
)


def test_the_contract_record_names_the_ambiguity_of_version_2() -> None:
    text = _folded(CONTRACT, comments=True)
    missing = [sentence for sentence in CONTRACT_SAYS if sentence not in text]
    assert not missing, missing


def test_api_md_names_the_ambiguity_of_version_2() -> None:
    text = _folded(API)
    missing = [sentence for sentence in API_SAYS if sentence not in text]
    assert not missing, missing


def test_releasing_carries_the_two_rules_of_the_bump() -> None:
    text = _folded(RELEASING)
    missing = [sentence for sentence in RELEASING_SAYS if sentence not in text]
    assert not missing, missing
