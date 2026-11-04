"""What `digline record compare` reads, and what it says for a program. (ADR 0058)

**One structure, two readers.** The host builds a `RecordComparison` from a
suite's recordings; the CLI lays it out for the person who ran the command, and
the local page reads the same structure from the host. This module holds the
structure and the one rendering for a program, `record_compare_json`.

**The text stays where it was born** (fixed decision 9). A recorded answer, a
case's input and a setup's values are payload: they are fields here, because
the terminal and the page show them to the person inside the perimeter, and
`record_compare_json` writes **none** of them. What it writes is the shape: the
cases by their ids, the setups by their digests, each answer by the digest of
its text, the dates, how many times an answer came back, and, for two setups,
the keys whose values differ, never the values.

**Nothing is judged.** No answer is better than another, and no word here or in
what is built from it says so: the view shows, and the person reads.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from digline.wire.contract import OUTPUT_VERSION
from digline.wire.text import neutralised

__all__ = [
    "ComparedAnswer",
    "ComparedCase",
    "ComparedSetup",
    "RecordComparison",
    "SetupKey",
    "SetupValue",
    "record_compare_json",
]

#: Where a key of two setups stands: in both with different values, or in
#: one of them only.
type KeySide = Literal["both", "a", "b"]


@dataclass(frozen=True, slots=True)
class ComparedAnswer:
    """One answer, or a run of equal ones recorded one after the other under
    the same setup, never hidden: `times` says how many.

    `digest` is the first eight characters of the answer's SHA-256. `text` is
    the answer itself, payload, and never on the wire. `first_at` and
    `last_at` are the `recorded_at` of the run's first and last recording,
    `None` where a recording carried none."""

    digest: str
    text: str
    first_at: str | None
    last_at: str | None
    times: int


@dataclass(frozen=True, slots=True)
class ComparedSetup:
    """A case's answers under one setup, in the order they were recorded.
    `setup` is the setup's digest, as the recordings carry it."""

    setup: str
    answers: tuple[ComparedAnswer, ...]


@dataclass(frozen=True, slots=True)
class ComparedCase:
    """One case: the recordings with the same input, under every setup they
    were made under, the setups in the order of their first answer. `vars` is
    the input, payload, and never on the wire. `kind` is `call` or
    `episode`."""

    id: str
    vars: Mapping[str, object]
    kind: str
    setups: tuple[ComparedSetup, ...]


@dataclass(frozen=True, slots=True)
class SetupValue:
    """A setup's value, as far as it is shown: its first line, clipped, and how
    many characters the whole value has. Payload, and never on the wire."""

    preview: str
    chars: int
    clipped: bool


@dataclass(frozen=True, slots=True)
class SetupKey:
    """One key two setups do not share, or hold different values under. `a`
    and `b` are `None` on the side that does not have the key."""

    key: str
    a: SetupValue | None
    b: SetupValue | None

    @property
    def side(self) -> KeySide:
        return "a" if self.b is None else "b" if self.a is None else "both"


@dataclass(frozen=True, slots=True)
class RecordComparison:
    """A suite's recorded answers, by case and by setup.

    `setups` is every setup the suite's answers were recorded under, in the
    order of its first answer. `pair` is the two setups `--setup` named, as
    the recordings carry them, or `None`. `setup_keys` is what `--show-setup`
    asked for, the keys the two differ on, or `None` where it was not asked;
    `same_keys` is how many keys they share with equal values.

    `case` and `since` are the filters given. `undated` counts the recordings
    `since` left out because they carry no `recorded_at`. The other counts are
    the recordings of the suite that are not cases, as the import counts them.
    """

    tenant: str
    suite: str
    case: str | None
    since: str | None
    setups: tuple[str, ...]
    pair: tuple[str, str] | None
    setup_keys: tuple[SetupKey, ...] | None
    same_keys: int | None
    cases: tuple[ComparedCase, ...]
    recordings: int
    orphans: int
    detached: int
    interrupted: int
    oversize: int
    unreadable: int
    undated: int


#: The first eight characters of a digest: how the view names a setup and an
#: answer.
SHORT = 8


def record_compare_json(comparison: RecordComparison) -> dict[str, object]:
    """The comparison for a program: the shape, without one recorded word.
    No `exit_code`: the view is not a gate."""
    return neutralised(
        {
            "output_version": OUTPUT_VERSION,
            "tenant": comparison.tenant,
            "suite": comparison.suite,
            "case": comparison.case,
            "since": comparison.since,
            "setups": [setup[:SHORT] for setup in comparison.setups],
            "pair": (
                None
                if comparison.pair is None
                else [setup[:SHORT] for setup in comparison.pair]
            ),
            "setup_keys": (
                None
                if comparison.setup_keys is None
                else {
                    "same": comparison.same_keys or 0,
                    "keys": [
                        {"key": key.key, "side": key.side}
                        for key in comparison.setup_keys
                    ],
                }
            ),
            "cases": [
                {
                    "id": case.id,
                    "kind": case.kind,
                    "setups": [
                        {
                            "setup": setup.setup[:SHORT],
                            "answers": [
                                {
                                    "digest": answer.digest,
                                    "first_at": answer.first_at,
                                    "last_at": answer.last_at,
                                    "times": answer.times,
                                }
                                for answer in setup.answers
                            ],
                        }
                        for setup in case.setups
                    ],
                }
                for case in comparison.cases
            ],
            "recordings": comparison.recordings,
            "not_shown": {
                "orphans": comparison.orphans,
                "detached": comparison.detached,
                "interrupted": comparison.interrupted,
                "oversize": comparison.oversize,
                "unreadable": comparison.unreadable,
                "undated": comparison.undated,
            },
        }
    )
