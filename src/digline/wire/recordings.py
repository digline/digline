"""What `digline record import` lists, for a program. (ADR 0023 §9, ADR 0058)

**The listing's facts, never its text.** The host reads a suite's recordings
into an `ImportListing`, which holds every answer whole, because the person
who runs the listing inside the perimeter reads them. A program is handed
`Listed`, built from it: the declaration, the setup in force per form, and
per group the shape of the output and counts. No input, no answer, no vars,
no step and no call site is a field here, and no answer's id, which carries
the digest of its text.

**A yes or a no is not given here.** The listing says where a person gives
one, `review`: the page of `digline view` that lists the same answers.
"""

from __future__ import annotations

import shlex
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from digline.core.types import OutputKind
from digline.report.pages import VIEW_PORT, recordings_address
from digline.wire.contract import OUTPUT_VERSION
from digline.wire.text import neutralised

__all__ = [
    "REFUSAL_REASONS",
    "REVIEW",
    "Listed",
    "ListedGroup",
    "Shape",
    "import_listing_json",
    "shape_json",
]

#: Why an answer cannot be given a yes or a no, each by the word a program
#: reads, in the order `digline record import` asks them.
REFUSAL_REASONS = ("already_in_the_file", "earlier_setups", "no_input", "conversation")

#: What the listing says about a yes or a no, which it does not give.
REVIEW = "to review an answer, open digline view"


@dataclass(frozen=True, slots=True)
class Shape:
    """The shape of an output, which is what the listing groups by.

    `episode` is false for a single call, whose shape is its `OutputKind`
    alone until a call carries a finish (ADR 0057's schema 23). For an episode,
    `actors` are its steps' actors in order and `finish` the last finish they
    carry. `None` is *not recorded*, never a kind."""

    episode: bool
    kind: OutputKind | None
    actors: tuple[str, ...] = ()
    finish: str | None = None

    def says(self) -> str:
        kind = self.kind or "kind not recorded"
        if not self.episode:
            return f"a single call, {kind}"
        steps = " → ".join(self.actors) if self.actors else "no step recorded"
        return (
            f"an episode, {kind}, steps {steps}, finish {self.finish or 'not recorded'}"
        )


def shape_json(shape: Shape) -> dict[str, object]:
    """A shape for a program: the form, the kind, the actors and the finish,
    each digline's word or a recorded `finish`, never a recorded text."""
    return {
        "episode": shape.episode,
        "kind": shape.kind,
        "actors": list(shape.actors),
        "finish": shape.finish,
    }


@dataclass(frozen=True, slots=True)
class ListedGroup:
    """One group of the listing, counted: how many answers it holds, how many
    recordings gave them, how many no person has named yet, how many are
    already in the file as a yes or as a no, and how many cannot be named,
    by `REFUSAL_REASONS`."""

    shape: Shape
    setup: str | None
    answers: int
    recordings: int
    waiting: int
    good: int
    bad: int
    refused: Mapping[str, int]


@dataclass(frozen=True, slots=True)
class Listed:
    """The listing's facts: what `digline record import` prints before a
    person names anything, without one recorded word.

    `cases_file` is said as the listing says it, relative to the repository.
    `setups` is the setup in force per form, `True` for the episodes."""

    tenant: str
    suite: str
    cases_file: str
    repository: str
    check: str | None
    taken_from: str | None
    setups: Mapping[bool, str | None]
    samples: int
    deterministic_output: bool
    groups: tuple[ListedGroup, ...]
    recordings: int
    orphans: int
    detached: int
    interrupted: int
    oversize: int
    unreadable: int
    examined_through: str | None


def import_listing_json(listed: Listed, *, review: Sequence[str]) -> dict[str, object]:
    """The listing for a program. `review` is the command that serves the page
    where a person gives a yes or a no, and the address is that page at the
    view's default port, which the sentence says: a view started on another
    port serves it there. No `exit_code`: the listing is not a gate."""
    return neutralised(
        {
            "output_version": OUTPUT_VERSION,
            "tenant": listed.tenant,
            "suite": listed.suite,
            "declaration": {
                "cases_file": listed.cases_file,
                "repository": listed.repository,
                "check": listed.check,
                "taken_from": listed.taken_from,
            },
            "setups": {
                "single_calls": _short(listed.setups.get(False)),
                "episodes": _short(listed.setups.get(True)),
            },
            "samples": listed.samples,
            "deterministic_output": listed.deterministic_output,
            "groups": [
                {
                    "shape": shape_json(group.shape),
                    "setup": _short(group.setup),
                    "answers": group.answers,
                    "recordings": group.recordings,
                    "waiting": group.waiting,
                    "good": group.good,
                    "bad": group.bad,
                    "refused": {
                        reason: group.refused.get(reason, 0)
                        for reason in REFUSAL_REASONS
                    },
                }
                for group in listed.groups
            ],
            "recordings": listed.recordings,
            "not_shown": {
                "orphans": listed.orphans,
                "detached": listed.detached,
                "interrupted": listed.interrupted,
                "oversize": listed.oversize,
                "unreadable": listed.unreadable,
            },
            "examined_through": listed.examined_through,
            "review": {
                "sentence": f"{REVIEW}: the address is its page at the default "
                f"port, {VIEW_PORT}, and a view started with another --port "
                "serves it there",
                "command": shlex.join(review),
                "address": f"http://127.0.0.1:{VIEW_PORT}"
                + recordings_address(listed.tenant, listed.suite),
            },
        }
    )


def _short(setup: str | None) -> str | None:
    return None if setup is None else setup[:8]
