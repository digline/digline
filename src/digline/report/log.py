"""Which system answered, read down a suite's stored runs. (ADR 0020)

`compare()` reads across a pair and `history.py` reads one case down the runs.
This reads the *identity* down the runs: what each side sent, what the provider
said answered, and — mostly, on real history — what was not recorded at all.

Two rules shape everything here, and both are types before they are prose.

**A roll is declared by the record, never deduced.** A roll is two sightings of
the same sent model whose recorded answering models differ (§1). Nothing in
this module reads a score, a verdict or a canary, and no type in it has a field
one could occupy (§4): a reading that put a score beside an identity would hand
every consumer the arithmetic this refuses to do.

**Every absence is its own fact.** Six of them, named in order (§3), and a span
of silent runs is its own row — so *nothing was recorded for four days* can
never read as *the same model answered for four days*.

The configuration is reduced with `SystemConfig.redacted()` **here**, inside the
fold, so the terminal, `--json` and the MCP all read the same reduced value: the
door 0.12.1 closed in `config_deltas` stays closed by construction (§6).

Pure like the rest of `report`: it takes runs someone else read, and counts of
what they could not.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal

from digline.core import RegisterEntry, Run, SystemConfig
from digline.report.text import Locale, phrase, strings

__all__ = [
    "ABSENCES",
    "SIDES",
    "AbsenceKind",
    "IdentityLog",
    "IdentitySpan",
    "Reference",
    "Replay",
    "Roll",
    "Side",
    "Sighting",
    "identity_log",
    "log_text",
    "sighting",
]

type Side = Literal["target", "judge"]

#: §3's rows 2–6, in the order they are checked. Row 1 — a file that was not
#: read at all — is not a sighting of anything, so it is a count on the log
#: rather than a kind here.
type AbsenceKind = Literal[
    "declared_nothing", "several_judges", "withheld", "not_reported", "not_recorded"
]

SIDES: tuple[Side, ...] = ("target", "judge")
ABSENCES: tuple[AbsenceKind, ...] = (
    "declared_nothing",
    "several_judges",
    "withheld",
    "not_reported",
    "not_recorded",
)


@dataclass(frozen=True, slots=True)
class Sighting:
    """What one run declares about one side: who was asked, and what answered.

    `answered` is `None` exactly when `absence` is set. `sent` is a tuple because
    a judge side may name several instruments, and then there is no single
    model to name — it is empty only where nothing was declared.
    """

    provider: str
    sent: tuple[str, ...]
    answered: str | None
    absence: AbsenceKind | None


@dataclass(frozen=True, slots=True)
class IdentitySpan:
    """Consecutive runs whose sighting on one side was the same.

    No score, no status, no outcome, no canary — by type (ADR 0020 §4).
    `environments` is reported and never splits a span: decision 8 keeps the
    environment inside the perimeter and out of any constraint.
    """

    side: Side
    provider: str
    sent: tuple[str, ...]
    answered: str | None
    absence: AbsenceKind | None
    first_seen: str
    last_seen: str
    runs: int
    environments: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Roll:
    """The same sent model, recorded answering as two different models.

    The moment is **not known** and is never pinned: it is after the last run
    that recorded `before` and no later than the first that recorded `after`,
    with `silent_between` runs in that window that recorded nothing.
    """

    side: Side
    provider: str
    sent: str
    before: str
    after: str
    last_before: str
    first_after: str
    silent_between: int


@dataclass(frozen=True, slots=True)
class Replay:
    """A run that re-judged another and asked the target nothing (ADR 0015 §6).

    Its target configuration is a copy of the source's, so it is never a
    sighting of the target. Its judge *was* asked, so on that side it is one.
    """

    key: str
    created_at: str
    source: str


@dataclass(frozen=True, slots=True)
class Reference:
    """The approved baseline's own sighting — the one that is committed."""

    key: str
    created_at: str
    promoted_at: str
    target: Sighting
    judge: Sighting


@dataclass(frozen=True, slots=True)
class IdentityLog:
    """The whole reading of one suite in one tenant, oldest first.

    `first` and `last` bound the runs read, inside the window when one was
    given. They are *in this store*: runs are ignored by fixed decision 2, so a
    hosted runner or a fresh clone reads none, and that is `runs == 0` rather
    than a history with no roll in it.

    `register` is the story of the reference beside the story of the alias: the
    dispositions a person recorded, in `recorded_at` order (ADR 0021 §8). It is
    committed, so unlike the runs it is on every clone. An incomplete last line
    and a register that could not be read at all are stated, never shown as an
    empty register.
    """

    tenant: str
    suite: str
    since: str
    until: str
    runs: int
    first: str
    last: str
    spans: tuple[IdentitySpan, ...]
    rolls: tuple[Roll, ...]
    replays: tuple[Replay, ...]
    skipped: Mapping[int, int] = field(default_factory=dict[int, int])
    unreadable: int = 0
    reference: Reference | None = None
    register: tuple[RegisterEntry, ...] = ()
    register_torn: bool = False
    register_unreadable: bool = False


def sighting(config: SystemConfig, *, writer: str) -> Sighting:
    """One side of one run, reduced at the boundary and then classified.

    `writer` is the run's `digline_version` — empty where the document does not
    name the release that wrote it, which is what separates *no answering model
    was reported* from *not recorded*. A `resolved_model` wins over both: a file
    from 0.8 or 0.9 carries the model and not the writer, and the record
    declaring the identity is all a sighting needs.

    The writer is **never** dated from anywhere else. The dependency pin at
    `git_commit` would put a release on most undated runs, and it is a second
    record, read off trees that are commonly dirty (ADR 0020 §3).
    """
    seen = config.redacted()
    if len(seen.identities) > 1:
        # `SystemConfig` refuses one set-up beside two instruments, so which
        # judges graded is known and what answered for either one is not.
        return Sighting("", seen.identities, None, "several_judges")
    if not seen.values:
        return Sighting("", (), None, "declared_nothing")
    provider = str(seen.values["provider"])
    sent = (str(seen.values["model"]),)
    answered = seen.values.get("resolved_model")
    if answered is not None:
        return Sighting(provider, sent, str(answered), None)
    if "resolved_model" in seen.withheld:
        return Sighting(provider, sent, None, "withheld")
    if writer:
        return Sighting(provider, sent, None, "not_reported")
    return Sighting(provider, sent, None, "not_recorded")


def _in_window(created_at: str, since: str, until: str) -> bool:
    """Inclusive at both ends, compared on the bound's own precision.

    The bounds arrive normalised to UTC by the host — a date, or a date and a
    time to the second — and a stored `created_at` is UTC too, so comparing the
    prefix of the same length is comparing the same instant at the same grain.
    `--until 2026-09-14` therefore includes every run of that day.
    """
    if since and created_at[: len(since)] < since:
        return False
    return not (until and created_at[: len(until)] > until)


def _config(run: Run, side: Side) -> SystemConfig:
    return run.target_config if side == "target" else run.judge_config


def _spans(side: Side, seen: Sequence[tuple[Run, Sighting]]) -> list[IdentitySpan]:
    spans: list[IdentitySpan] = []
    for run, found in seen:
        last = spans[-1] if spans else None
        if last is not None and (
            last.provider,
            last.sent,
            last.answered,
            last.absence,
        ) == (found.provider, found.sent, found.answered, found.absence):
            spans[-1] = IdentitySpan(
                side=side,
                provider=last.provider,
                sent=last.sent,
                answered=last.answered,
                absence=last.absence,
                first_seen=last.first_seen,
                last_seen=run.created_at,
                runs=last.runs + 1,
                environments=tuple(sorted({*last.environments, run.environment})),
            )
            continue
        spans.append(
            IdentitySpan(
                side=side,
                provider=found.provider,
                sent=found.sent,
                answered=found.answered,
                absence=found.absence,
                first_seen=run.created_at,
                last_seen=run.created_at,
                runs=1,
                environments=(run.environment,),
            )
        )
    return spans


def _rolls(side: Side, seen: Sequence[tuple[Run, Sighting]]) -> list[Roll]:
    """Every change of answering model under one sent model, in order.

    Compared with the **previous recorded** sighting of the same provider and
    sent model — not the previous run — so a run of silences between them is
    counted into the window rather than breaking the comparison, and a suite
    that switched to another model and back still sees the first one's roll.
    """
    rolls: list[Roll] = []
    last: dict[tuple[str, str], tuple[str, str, int]] = {}
    silent: list[int] = []
    for index, (run, found) in enumerate(seen):
        if found.answered is None:
            silent.append(index)
            continue
        identity = (found.provider, found.sent[0])
        previous = last.get(identity)
        if previous is not None and previous[0] != found.answered:
            before, last_before, at = previous
            rolls.append(
                Roll(
                    side=side,
                    provider=found.provider,
                    sent=found.sent[0],
                    before=before,
                    after=found.answered,
                    last_before=last_before,
                    first_after=run.created_at,
                    silent_between=sum(1 for i in silent if at < i < index),
                )
            )
        last[identity] = (found.answered, run.created_at, index)
    return rolls


def identity_log(
    rows: Sequence[tuple[str, Run]],
    *,
    tenant: str,
    suite: str,
    since: str = "",
    until: str = "",
    skipped: Mapping[int, int] | None = None,
    unreadable: int = 0,
    baseline: tuple[str, Run] | None = None,
    register: Sequence[RegisterEntry] = (),
    register_torn: bool = False,
    register_unreadable: bool = False,
) -> IdentityLog:
    """Fold `(key, run)` pairs into the reading, oldest first.

    Sorted on `created_at`, the recorded fact, with the key as tie-breaker —
    `history.case_history`'s rule, for its reason. A resumed run is one sighting
    at its original `created_at` (ADR 0017 §8), and one run never carries two
    answering models on a side: `ObservedIdentity` errors the case where an alias
    answers as a second model mid-run (ADR 0005 §8).
    """
    ordered = sorted(
        ((key, run) for key, run in rows if _in_window(run.created_at, since, until)),
        key=lambda pair: (pair[1].created_at, pair[0]),
    )
    replays = tuple(
        Replay(key=key, created_at=run.created_at, source=run.rejudged_from)
        for key, run in ordered
        if run.rejudged_from is not None
    )
    spans: list[IdentitySpan] = []
    rolls: list[Roll] = []
    for side in SIDES:
        seen = [
            (run, sighting(_config(run, side), writer=run.digline_version))
            for _key, run in ordered
            # A replay's target configuration is its source's, copied: counting
            # it would stretch the source's last sighting on a copy.
            if not (side == "target" and run.rejudged_from is not None)
        ]
        spans.extend(_spans(side, seen))
        rolls.extend(_rolls(side, seen))

    reference = None
    if baseline is not None:
        key, approved = baseline
        reference = Reference(
            key=key,
            created_at=approved.created_at,
            promoted_at=approved.promoted_at,
            target=sighting(approved.target_config, writer=approved.digline_version),
            judge=sighting(approved.judge_config, writer=approved.digline_version),
        )
    return IdentityLog(
        tenant=tenant,
        suite=suite,
        since=since,
        until=until,
        runs=len(ordered),
        first=ordered[0][1].created_at if ordered else "",
        last=ordered[-1][1].created_at if ordered else "",
        spans=tuple(spans),
        rolls=tuple(rolls),
        replays=replays,
        skipped=dict(skipped or {}),
        unreadable=unreadable,
        reference=reference,
        # The same window, over the moment each disposition was recorded.
        register=tuple(
            sorted(
                (
                    entry
                    for entry in register
                    if _in_window(entry.recorded_at, since, until)
                ),
                key=lambda entry: entry.recorded_at,
            )
        ),
        register_torn=register_torn,
        register_unreadable=register_unreadable,
    )


# --------------------------------------------------------------------------- #
# The terminal reading
# --------------------------------------------------------------------------- #


def _who(provider: str, sent: tuple[str, ...]) -> str:
    return " ".join(part for part in (provider, ", ".join(sent)) if part)


def _sighting_text(found: Sighting, locale: Locale) -> str:
    who = _who(found.provider, found.sent)
    if found.absence is None:
        return phrase(locale, "log.sighting.answered", who=who, answered=found.answered)
    absence = phrase(locale, f"log.absence.{found.absence}")
    if not who:
        return absence
    return phrase(locale, "log.sighting.absent", who=who, absence=absence)


def _span_line(span: IdentitySpan, locale: Locale) -> str:
    environments = (
        phrase(locale, "log.environments", environments=", ".join(span.environments))
        if span.environments
        else ""
    )
    found = Sighting(span.provider, span.sent, span.answered, span.absence)
    return phrase(
        locale,
        "log.span",
        sighting=_sighting_text(found, locale),
        first=span.first_seen,
        last=span.last_seen,
        runs=span.runs,
        environments=environments,
    )


def log_text(log: IdentityLog, *, locale: Locale) -> tuple[str, ...]:
    """The reading, in lines, for a terminal. A pure function of the log.

    It states and never advises, and it never says *likely*: that word belongs
    to the canary, and a reading of the record does not speculate.
    """
    strings(locale)  # fail here, not halfway through a reading

    lines: list[str] = []
    if log.runs:
        lines.append(
            phrase(
                locale,
                "log.heading",
                suite=log.suite,
                count=log.runs,
                first=log.first,
                last=log.last,
            )
        )
    else:
        lines.append(phrase(locale, "log.empty", suite=log.suite))
    if log.since or log.until:
        open_end = phrase(locale, "log.window.open")
        lines.append(
            phrase(
                locale,
                "log.window",
                since=log.since or open_end,
                until=log.until or open_end,
            )
        )
    for version, count in sorted(log.skipped.items()):
        lines.append(
            phrase(locale, "log.not_read.schema", count=count, version=version)
        )
    if log.unreadable:
        lines.append(phrase(locale, "log.not_read.unreadable", count=log.unreadable))

    if log.runs:
        for side in SIDES:
            lines.append("")
            lines.append(phrase(locale, f"log.side.{side}"))
            lines.extend(
                _span_line(span, locale) for span in log.spans if span.side == side
            )
            if side == "target":
                lines.extend(
                    "  " + phrase(locale, "log.replay", run=r.key, source=r.source)
                    for r in log.replays
                )
        lines.append("")
        if not log.rolls:
            lines.append(phrase(locale, "log.rolls.none"))
        for roll in log.rolls:
            lines.append(
                phrase(
                    locale,
                    "log.roll",
                    side=phrase(locale, f"log.side.{roll.side}"),
                    sent=_who(roll.provider, (roll.sent,)),
                    before=roll.before,
                    after=roll.after,
                    last_before=roll.last_before,
                    first_after=roll.first_after,
                )
            )
            if roll.silent_between:
                lines.append(
                    "  " + phrase(locale, "log.roll.silence", count=roll.silent_between)
                )

    lines.append("")
    reference = log.reference
    if reference is None:
        lines.append(phrase(locale, "log.reference.none"))
    else:
        sentence = "log.reference" if reference.promoted_at else "log.reference.undated"
        lines.append(
            phrase(
                locale,
                sentence,
                run=reference.key,
                created_at=reference.created_at,
                promoted_at=reference.promoted_at,
            )
        )
        for side in SIDES:
            lines.append(
                phrase(
                    locale,
                    "log.reference.side",
                    side=phrase(locale, f"log.side.{side}"),
                    sighting=_sighting_text(getattr(reference, side), locale),
                )
            )

    # The story of the reference: what a person decided about each comparison,
    # grouped under the reference it was judged against. A change of reference
    # between two dispositions is said because both entries declare it; where
    # nothing was recorded, nothing is inferred. (ADR 0021 §9)
    lines.append("")
    lines.append(phrase(locale, "log.register.heading"))
    if log.register_unreadable:
        lines.append(phrase(locale, "log.register.unreadable"))
    elif not log.register:
        lines.append(phrase(locale, "log.register.none"))
    against: str | None = None
    for entry in log.register:
        if entry.baseline_key != against:
            against = entry.baseline_key
            lines.append(phrase(locale, "log.register.reference", run=against))
        lines.append(
            phrase(
                locale,
                "log.register.entry",
                recorded_at=entry.recorded_at,
                disposition=phrase(locale, f"log.disposition.{entry.disposition}"),
                run=entry.run_key,
                exit_code=entry.exit_code,
                regressed=entry.outcome.regressed,
                improved=entry.outcome.improved,
                unjudged=entry.outcome.unjudged,
            )
        )
    if log.register_torn:
        lines.append(phrase(locale, "log.register.torn"))
    return tuple(lines)
