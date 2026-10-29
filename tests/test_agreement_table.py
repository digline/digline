"""The agreement table, held to the gate it describes. (#703)

Three places tell a reader what each `min_agreement` floor asks at five samples
and where it binds: the table in ADR 0006 §13, the table in `docs/guide.md`, and
the block in `as_agreement`'s docstring, which ships in the package. Until #703
the `3/5` row said *"any majority of the judged samples"*, and nothing compared
that with the gate, which divides by every sample asked for.

A sentence cannot be run, so this file holds two things apart:

- **What can be computed.** Each row has a predicate below, written from its
  words: on which compositions of five samples, so many `pass`, so many `fail`,
  so many errored, the floor binds and the check ends in `error`. Each
  predicate is compared with `combine_samples` itself on every composition.
- **What can only be held still.** The words of each row, in each of the three
  places, are a golden set. Changing one is a decision, not a drift.

What neither proves is that the words say what the predicate says. That link
was approved once, with the wording (#703), and the two halves keep it from
moving on either side without something going red.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

import pytest

from digline.core import Score, Verdict, combine_samples
from digline.core.ratio import as_agreement

ROOT = Path(__file__).resolve().parents[1]
ADR = ROOT / "docs" / "adr" / "0006-repeated-samples-and-the-noise-floor.md"
GUIDE = ROOT / "docs" / "guide.md"

SAMPLES = 5

Binds = Callable[[int, int, int], bool]

#: Where each floor binds, as its row says it, over (pass, fail, errored). The
#: side that agrees can be either one, so "agreeing" is the larger of the two.
PREDICATES: dict[str, Binds] = {
    # "only when errored samples leave fewer than three in agreement"
    "3/5": lambda p, f, e: e > 0 and max(p, f) < 3,
    # "on a genuine 3-2 split, and wherever errored samples leave fewer than
    # four in agreement"
    "4/5": lambda p, f, e: (
        (e == 0 and sorted((p, f)) == [2, 3]) or (e > 0 and max(p, f) < 4)
    ),
    # "on any split, and on any errored sample"
    "5/5": lambda p, f, e: (p > 0 and f > 0) or e > 0,
}

#: The rows as each place words them: what the floor asks, and where it binds.
ADR_ROWS = {
    "3/5": (
        "three of the five samples agree, errored samples counted among the five",
        "only when errored samples leave fewer than three in agreement — the "
        "floor that protects the mean from resting on too few judged samples",
    ),
    "4/5": (
        "four of the five samples agree, errored samples counted among the five",
        "on a genuine 3–2 split, and wherever errored samples leave fewer than "
        "four in agreement",
    ),
    "5/5": ("unanimity", "on any split, and on any errored sample"),
}
GUIDE_ROWS = {
    "3/5": (
        "three of the five you asked for agree",
        "only when samples that could not judge leave fewer than three agreeing "
        "— the floor that protects the mean from resting on too few judged "
        "samples",
    ),
    "4/5": (
        "four of the five you asked for agree",
        "on a genuine 3–2 split, and wherever samples that could not judge "
        "leave fewer than four agreeing",
    ),
    "5/5": ("unanimity", "on any split, and on any errored sample"),
}
DOCSTRING_ROWS = {
    "3/5": "three of the five agree, errored samples counted; binds only when "
    "errors leave fewer than three agreeing (the floor that protects the mean)",
    "4/5": "four of the five agree, errored samples counted; binds on a genuine "
    "3-2 split, and wherever errors leave fewer than four agreeing",
    "5/5": "unanimity; binds on any split and on any errored sample",
}


def _sample(status: str) -> Verdict:
    if status == "error":
        return Verdict(
            score=Score(name="rubric", score=None),
            threshold=0.7,
            status="error",
            reason="could not judge",
            assertion_id="id-rubric",
        )
    return Verdict(
        score=Score(name="rubric", score=0.9 if status == "pass" else 0.1),
        threshold=0.7,
        status=status,  # type: ignore[arg-type]
        reason="judged",
        assertion_id="id-rubric",
    )


def _folded(p: int, f: int, e: int, floor: str) -> Verdict:
    samples = [_sample("pass")] * p + [_sample("fail")] * f + [_sample("error")] * e
    minimum = as_agreement(floor, samples=SAMPLES, field="min_agreement")
    return combine_samples(samples, min_agreement=minimum)


#: Every composition of five samples but one: 0 `pass`, 0 `fail`, 5 errored.
#: There `combine_samples` returns `error` before agreement is computed, from
#: its first check that any score exists, with the samples' own causes under
#: the summary (`_all_errored`, ADR 0006 §12). That outcome is the same at every
#: floor, so no row of the table decides it, and a predicate asked about it
#: would be asked about something the floor never reaches.
COMPOSITIONS = [
    (p, f, SAMPLES - p - f)
    for p in range(SAMPLES + 1)
    for f in range(SAMPLES + 1 - p)
    if p + f > 0
]


def test_the_compositions_are_every_vote_with_a_judged_sample() -> None:
    assert len(COMPOSITIONS) == 20
    assert all(sum(c) == SAMPLES for c in COMPOSITIONS)
    assert (0, 0, SAMPLES) not in COMPOSITIONS


@pytest.mark.parametrize("floor", sorted(PREDICATES))
def test_each_row_binds_where_the_gate_binds(floor: str) -> None:
    said = {c for c in COMPOSITIONS if PREDICATES[floor](*c)}
    computed = {c for c in COMPOSITIONS if _folded(*c, floor).status == "error"}
    assert said == computed, (
        f"{floor}: the row says it binds on {sorted(said - computed)} where the "
        f"gate does not, and the gate binds on {sorted(computed - said)} where "
        "the row does not"
    )


@pytest.mark.parametrize(
    ("p", "f", "e", "binds"),
    [
        # The vote that refutes "any majority of the judged samples": two of the
        # three judged agree, and the floor still binds.
        (2, 1, 2, True),
        # Three agree beside a `fail` and an error, and beside two errors: a
        # `fail` and an errored sample weigh the same.
        (3, 1, 1, False),
        (3, 0, 2, False),
    ],
)
def test_the_three_measured_votes_at_three_of_five(
    p: int, f: int, e: int, binds: bool
) -> None:
    assert (_folded(p, f, e, "3/5").status == "error") is binds
    assert PREDICATES["3/5"](p, f, e) is binds


def _table_rows(text: str, after: str) -> dict[str, tuple[str, str]]:
    """The three-column rows of the first table after `after`, keyed by floor."""
    start = text.index(after)
    rows: dict[str, tuple[str, str]] = {}
    for line in text[start:].splitlines():
        if rows and not line.startswith("|"):
            break
        match = re.fullmatch(r"\| `(\d/\d)` \| (.+?) \| (.+?) \|", line)
        if match:
            rows[match.group(1)] = (match.group(2), match.group(3))
    return rows


def _docstring_rows() -> dict[str, str]:
    """The block under "At five samples:", one row per floor, lines rejoined."""
    doc = as_agreement.__doc__ or ""
    block = doc[doc.index("At five samples:") :].split("\n\n")[1]
    rows: dict[str, str] = {}
    current = ""
    for line in block.splitlines():
        match = re.fullmatch(r"\s*(\d/\d)\s{2}(.+)", line)
        if match:
            current = match.group(1)
            rows[current] = match.group(2).strip()
        else:
            rows[current] += " " + line.strip()
    return rows


def test_the_adr_rows_are_the_approved_words() -> None:
    rows = _table_rows(
        ADR.read_text(encoding="utf-8"), "### 13. What each floor can catch"
    )
    assert rows == ADR_ROWS


def test_the_guide_rows_are_the_approved_words() -> None:
    rows = _table_rows(
        GUIDE.read_text(encoding="utf-8"), "**Choose the floor knowing what it can"
    )
    assert rows == GUIDE_ROWS


def test_the_docstring_rows_are_the_approved_words() -> None:
    assert _docstring_rows() == DOCSTRING_ROWS


def test_every_place_has_a_row_for_every_predicate() -> None:
    assert set(ADR_ROWS) == set(GUIDE_ROWS) == set(DOCSTRING_ROWS) == set(PREDICATES)


# Two and four samples. ADR 0006 §13 said the smallest majority is met by every
# fully judged vote "at any `n`"; at an even `n` a fully judged vote can tie,
# and that floor refuses the tie (corrected there on 2026-10-29). No place words
# a row for these counts, so each floor is held to §12 itself: it binds where
# the larger judged side, out of every sample asked for, is below the floor.
EVEN_SAMPLES = (2, 4)


def _compositions(samples: int) -> list[tuple[int, int, int]]:
    """Every vote of `samples` with a judged sample, as `COMPOSITIONS` is."""
    return [
        (p, f, samples - p - f)
        for p in range(samples + 1)
        for f in range(samples + 1 - p)
        if p + f > 0
    ]


def _folded_at(samples: int, p: int, f: int, e: int, floor: str) -> Verdict:
    votes = [_sample("pass")] * p + [_sample("fail")] * f + [_sample("error")] * e
    minimum = as_agreement(floor, samples=samples, field="min_agreement")
    return combine_samples(votes, min_agreement=minimum)


EVEN_VOTES = [
    (samples, f"{n}/{samples}", *vote)
    for samples in EVEN_SAMPLES
    for n in range(1, samples + 1)
    for vote in _compositions(samples)
]


def test_the_even_votes_are_every_floor_against_every_judged_vote() -> None:
    assert len(_compositions(2)) == 5
    assert len(_compositions(4)) == 14
    assert len(EVEN_VOTES) == 2 * 5 + 4 * 14


@pytest.mark.parametrize(("samples", "floor", "p", "f", "e"), EVEN_VOTES)
def test_at_an_even_count_each_floor_binds_where_section_12_says(
    samples: int, floor: str, p: int, f: int, e: int
) -> None:
    agreeing = int(floor.split("/")[0])
    binds = max(p, f) < agreeing
    assert (_folded_at(samples, p, f, e, floor).status == "error") is binds


@pytest.mark.parametrize(
    ("samples", "floor", "p", "f"), [(4, "3/4", 2, 2), (2, "2/2", 1, 1)]
)
def test_the_smallest_majority_refuses_a_fully_judged_tie(
    samples: int, floor: str, p: int, f: int
) -> None:
    assert _folded_at(samples, p, f, 0, floor).status == "error"
