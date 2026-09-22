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

from digline.core import RegisterEntry, Run, SystemConfig, Verdict
from digline.core.calibration import scale_lost
from digline.report.render import fmt_score, unjudged_cases
from digline.report.text import Locale, phrase, strings

__all__ = [
    "ABSENCES",
    "EXCLUSIONS",
    "AggregateSpread",
    "SIDES",
    "AbsenceKind",
    "IdentityLog",
    "IdentitySpan",
    "Reference",
    "Replay",
    "Roll",
    "Side",
    "SPREAD_ABSENCES",
    "Sighting",
    "ExclusionKind",
    "SpreadAbsence",
    "identity_log",
    "log_text",
    "sighting",
]

type Side = Literal["target", "judge"]

#: §3's rows 2–7, in the order they are checked. Row 1 — a file that was not
#: read at all — is not a sighting of anything, so it is a count on the log
#: rather than a kind here.
type AbsenceKind = Literal[
    "declared_nothing",
    "several_judges",
    "withheld",
    "not_reported",
    "not_recorded",
    "echoed",
]

SIDES: tuple[Side, ...] = ("target", "judge")
ABSENCES: tuple[AbsenceKind, ...] = (
    "declared_nothing",
    "several_judges",
    "withheld",
    "not_reported",
    "not_recorded",
    "echoed",
)

#: The absences under which no answering model is identified, so the canary is
#: the only instrument that sees whether behaviour changed (ADR 0020 §3). A
#: fact about which instruments can see what — the reading states it once.
UNIDENTIFIED: frozenset[AbsenceKind] = frozenset(
    {"withheld", "not_reported", "not_recorded", "echoed"}
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


#: Why a stored run is not in the N, in the order §7.2's table checks them. A
#: closed vocabulary: a run excluded for a reason nobody named is a number
#: nobody can check, which is ADR 0016 §3's rule and the seven absences'.
type ExclusionKind = Literal[
    "rejudged",
    "unjudged",
    "scale_lost",
    "config_hash",
    "population",
    "artifacts",
    "target_config",
    "judge_config",
    "identity",
]

EXCLUSIONS: tuple[ExclusionKind, ...] = (
    "rejudged",
    "unjudged",
    "scale_lost",
    "config_hash",
    "population",
    "artifacts",
    "target_config",
    "judge_config",
    "identity",
)


#: Why there is no spread to read, in the order the fold decides it. Four
#: facts, and only `declares_none` is a fact about the **suite** — it was the
#: sentence printed for all four until 2026-09-22, so a fresh clone was told
#: its suite declared no run-level check and so was a run whose every aggregate
#: had flipped. A checkable sentence standing in for one that cannot be
#: checked, which is the defect §7.4's amendment closed on the exclusion
#: clause. (ADR 0024 §7.5, amended 2026-09-22)
type SpreadAbsence = Literal[
    "no_runs",
    "declares_none",
    "flipped",
    "scoreless",
]

SPREAD_ABSENCES: tuple[SpreadAbsence, ...] = (
    "no_runs",
    "declares_none",
    "flipped",
    "scoreless",
)


@dataclass(frozen=True, slots=True)
class AggregateSpread:
    """How much one run-level aggregate moved across the comparable runs.

    **A type of its own, sharing no row with `IdentitySpan`.** ADR 0020 §4 says
    the row has no score by type, and its hazard was a reader deducing a roll
    from scores printed beside identities. This uses that juxtaposition in the
    one direction the amendment permits: *identity decides which runs are
    grouped; scores never decide identity.*

    `low` and `high` are a **range**, not a standard deviation: the house reads
    noise as `sample_min`–`sample_max` (ADR 0006 §2, §5), a deviation over four
    stored runs is itself noise, and a second definition of *inside the noise*
    would answer with a different rule from the one `compare` applies per case.

    `within_low` and `within_high` are the **other** interval — the aggregate
    re-evaluated per sample index inside the latest run (ADR 0006 §7). They are
    a different quantity from `low`/`high` and are printed labelled and never
    compared with them: the folded aggregate is steadier than any single-sample
    one, and on a real store the between-run range came out *narrower* than the
    within-run interval (ADR 0024 §10).

    `runs` never counts the latest run: ADR 0006 §5's asymmetry, a noisy new run
    must not widen its own excuse.
    """

    name: str
    latest: float
    reference: float | None
    #: The range **over the counted runs only**. `None` where nothing was
    #: comparable, which is a reading with exclusions and no range rather than a
    #: range of one number. The latest run is never in it: a spread that
    #: contained the value it is read against would make *inside* true by
    #: construction, which is the excuse ADR 0024 §7.4 refuses to promote to a
    #: feature.
    low: float | None
    high: float | None
    runs: int
    excluded: Mapping[ExclusionKind, int] = field(
        default_factory=dict[ExclusionKind, int]
    )
    #: Of the runs in `runs`, how many did not identify the answering model.
    #: Named because a roll inside the set is absorbed into the spread, and
    #: where the provider does not name the model the canary is the only
    #: instrument that sees one.
    unidentified: int = 0
    #: Distinct `git_commit` values across the counted runs, reported and never
    #: a constraint: commonly `-dirty`, and excluding on it collapses N to one.
    commits: int = 0
    #: The releases that wrote the counted runs, lowest to highest.
    versions: tuple[str, ...] = ()
    within_low: float | None = None
    within_high: float | None = None


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
    #: One per run-level aggregate the latest run measured, or empty — a suite
    #: that declares none gets no section and the reading says so, rather than
    #: a suite-wide number built out of the checks, which would be inventing a
    #: summary. (ADR 0024 §7.1)
    spread: tuple[AggregateSpread, ...] = ()
    #: Why `spread` is empty, counted by cause; empty when `spread` is not.
    #:
    #: The count is how many of the latest run's aggregates the cause accounts
    #: for. It is genuinely `0` for the two causes that mean there were none to
    #: account for — no run read, or a suite that declares no run-level check —
    #: and above zero for the two that are facts about aggregates that do
    #: exist. Both entries are present where both hold: a run with one flipped
    #: aggregate and one scoreless one is two facts, and printing one of them
    #: would be the substitution this field exists to end.
    #: (ADR 0024 §7.5, amended 2026-09-22)
    spread_absence: Mapping[SpreadAbsence, int] = field(
        default_factory=dict[SpreadAbsence, int]
    )


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
        # Row 7: an absence disguised as a presence. The endpoint returned the
        # id it was sent, which says what was asked for and not what answered.
        # Literal equality, and nothing normalised — normalising is
        # interpretation. Only reachable in clear: behind a named endpoint the
        # value was withheld above, and saying "echoed" would disclose it.
        if str(answered) == sent[0]:
            return Sighting(provider, sent, None, "echoed")
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


def _population(run: Run) -> tuple[frozenset[str], ...]:
    """What the aggregate counted over, as four sets the document can verify.

    The case ids, and the three kinds of case that leave a denominator without
    being a failure. Read off the results rather than out of an aggregate's
    metadata: a set the reader can rebuild from the document beats a count it
    has to trust, and `Matrix`'s own numbers are derived from exactly these.
    """
    return (
        frozenset(case.case_id for case in run.results),
        frozenset(c.case_id for c in run.results if c.suspended is not None),
        frozenset(c.case_id for c in run.results if c.canary),
        frozenset(c.case_id for c in run.results if c.calibration is not None),
    )


def _artifacts(run: Run) -> Mapping[str, str]:
    """Each declared artifact's digest. A run that declares none compares equal
    to another that declares none — counted, and the reading says so."""
    return {path: item.sha for path, item in sorted(run.artifacts.items())}


def _why_not(latest: Run, run: Run, *, in_span: bool) -> ExclusionKind | None:
    """Why this run may not be measured beside the latest one, or `None`.

    §7.2's table, in its order. Every answer is verifiable from the two
    documents: nothing here infers, and what cannot be held — the case content
    behind a stable id, the mapper, every other line of code — is reported
    elsewhere rather than guessed at.
    """
    if run.rejudged_from is not None:
        # Zero target variance would narrow the spread with a run that asked
        # the target nothing (ADR 0015 §7).
        return "rejudged"
    if unjudged_cases(run):
        return "unjudged"
    if scale_lost(run):
        return "scale_lost"
    if run.config_hash != latest.config_hash:
        return "config_hash"
    if _population(run) != _population(latest):
        return "population"
    if _artifacts(run) != _artifacts(latest):
        return "artifacts"
    if run.target_config.redacted() != latest.target_config.redacted():
        return "target_config"
    if run.judge_config.redacted() != latest.judge_config.redacted():
        return "judge_config"
    if not in_span:
        # The set is the **latest identity span** only. What answered is mostly
        # not verifiable (ADR 0020 §3), so it is never inferred: the span is the
        # run of consecutive sightings the latest run belongs to, and how many
        # of them identified the model is said rather than assumed.
        #
        # **Subsumed in all but one corner, and kept anyway.** A sighting is
        # derived from the configuration — `resolved_model` is a value in it —
        # so a run a different model answered differs in `target_config` and is
        # excluded three rows above, under that name. What reaches here is the
        # residue: equal configurations whose `digline_version` differs, where
        # one absence reads `not_reported` and the other `not_recorded`. The
        # row's own contribution is the count `unidentified` carries, not this
        # exclusion. (ADR 0024 §7.2)
        return "identity"
    return None


def _aggregate(run: Run, name: str) -> Verdict | None:
    return next((v for v in run.aggregate if v.score.name == name), None)


def _spread(
    ordered: Sequence[tuple[str, Run]], reference: Run | None
) -> tuple[tuple[AggregateSpread, ...], dict[SpreadAbsence, int]]:
    """One reading per run-level aggregate of the latest run.

    The latest run is never in the N — ADR 0006 §5's asymmetry, a noisy new run
    must not widen its own excuse — so a store holding one run reads `runs=0`
    and **no range at all**, which the sentence states rather than dresses up.
    An empty store reads no aggregate either, and the caller says *no run was
    read* rather than anything about what the suite declares.

    **Silent on a flip.** Where an aggregate's status differs between the
    reference and the latest run, no spread is produced for it: ADR 0006 §6, a
    flip carries no interval, and printing one invites the reader to argue it
    away. (ADR 0024 §7.5)
    """
    if not ordered:
        # Zero aggregates because there was no run to read them off, which is
        # not a statement about what the suite declares.
        return (), {"no_runs": 0}
    _key, latest = ordered[-1]
    earlier = ordered[:-1]

    # The trailing group of runs whose target sighting is the latest run's. A
    # replay is not a sighting of the target at all, so it stops nothing.
    latest_sighting = sighting(_config(latest, "target"), writer=latest.digline_version)
    in_span: set[str] = set()
    for key, run in reversed(earlier):
        if run.rejudged_from is not None:
            continue
        if sighting(_config(run, "target"), writer=run.digline_version) != (
            latest_sighting
        ):
            break
        in_span.add(key)

    counted: list[Run] = []
    excluded: dict[ExclusionKind, int] = {}
    for key, run in earlier:
        why = _why_not(latest, run, in_span=key in in_span)
        if why is None:
            counted.append(run)
        else:
            excluded[why] = excluded.get(why, 0) + 1

    found: list[AggregateSpread] = []
    absence: dict[SpreadAbsence, int] = {}
    for verdict in latest.aggregate:
        name = verdict.score.name
        if verdict.score.score is None:
            absence["scoreless"] = absence.get("scoreless", 0) + 1
            continue
        before = None if reference is None else _aggregate(reference, name)
        if before is not None and before.status != verdict.status:
            absence["flipped"] = absence.get("flipped", 0) + 1
            continue
        scores = [
            other.score.score
            for run in counted
            if (other := _aggregate(run, name)) is not None
            and other.score.score is not None
        ]
        found.append(
            AggregateSpread(
                name=name,
                latest=verdict.score.score,
                reference=None if before is None else before.score.score,
                low=min(scores) if scores else None,
                high=max(scores) if scores else None,
                runs=len(scores),
                excluded=dict(sorted(excluded.items())),
                unidentified=sum(
                    1
                    for run in counted
                    if sighting(
                        _config(run, "target"), writer=run.digline_version
                    ).answered
                    is None
                ),
                commits=len({run.git_commit for run in counted if run.git_commit}),
                versions=tuple(
                    sorted({r.digline_version for r in counted if r.digline_version})
                ),
                within_low=verdict.score.sample_min,
                within_high=verdict.score.sample_max,
            )
        )
    if found:
        # Something is readable, so no cause is reported: the absences describe
        # a section with nothing in it, not aggregates that were passed over.
        return tuple(found), {}
    if not latest.aggregate:
        return (), {"declares_none": 0}
    return (), dict(sorted(absence.items()))


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
    readings, absence = _spread(ordered, None if baseline is None else baseline[1])
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
        spread=readings,
        spread_absence=absence,
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


def _excluded_text(spread: AggregateSpread, locale: Locale) -> str:
    """The exclusions, in §7.2's order and never as a total.

    A run excluded silently is a number nobody can check, and a single figure
    for *excluded* would be exactly that: which reason is what a reader acts on.

    The verb belongs to the **clause**, once, and each reason is a bare counted
    phrase joined after it. It used to sit on the `rejudged` string alone, which
    read correctly only while that reason came first: on scout's store, whose
    exclusions are all `unjudged`, the reading ended *"; 3 as not fully
    judged."* (ADR 0024 §7.4, amended 2026-09-22)
    """
    said = [
        phrase(locale, f"log.spread.excluded.{kind}", count=spread.excluded[kind])
        for kind in EXCLUSIONS
        if spread.excluded.get(kind)
    ]
    if not said:
        return ""
    return phrase(locale, "log.spread.excluded", excluded=", ".join(said))


#: Each cause's sentence. `declares_none` keeps the string it always had: it was
#: never the wrong sentence, it was the only right one asked to cover three
#: cases it was not about. (ADR 0024 §7.5)
_ABSENCE_STRING: Mapping[SpreadAbsence, str] = {
    "no_runs": "log.spread.no_runs",
    "declares_none": "log.spread.none",
    "flipped": "log.spread.flipped",
    "scoreless": "log.spread.scoreless",
}


def _spread_lines(log: IdentityLog, locale: Locale) -> list[str]:
    """The spread section: the set once, then one line per aggregate.

    The set-level facts — how many runs, what was excluded and why, how many
    identified the model, the commits and the releases — are one statement
    about one set, so they are said once. Repeating them under every aggregate
    would read as several measurements where there is one.

    **The inside/outside clause is withheld**, and the reading says it is —
    because the statistic cannot carry it, not because a number is missing. A
    min-max range is monotone in N: it cannot converge, so a score outside it
    names a value not seen before rather than a change. Measured on scout's
    twelve operator runs, where *outside* fired on 4 of 12 readings at N >= 6
    and every firing above the high became the next reading's high. The range
    stays because it is honest about what was seen; what it may not do is
    decide. (ADR 0024 §7.4, amended 2026-09-22)
    """
    if not log.spread:
        # **Four facts, and one sentence used to cover all of them.** `spread`
        # is derived from the latest run's aggregates, and it comes out empty
        # for four different reasons — of which only `declares_none` is a
        # statement about the *suite*. That was the one printed for all four,
        # so a fresh clone was told its suite declared no run-level check, and
        # so was a run whose every aggregate had flipped: a checkable sentence
        # standing in for one that cannot be checked.
        #
        # One sentence per cause present, in `SPREAD_ABSENCES` order, and both
        # where both hold — a run with one flipped aggregate and one scoreless
        # one is two facts, and naming one would be the substitution this
        # replaced. (ADR 0024 §7.5, amended 2026-09-22)
        return [
            phrase(locale, _ABSENCE_STRING[kind], count=log.spread_absence[kind])
            for kind in SPREAD_ABSENCES
            if kind in log.spread_absence
        ]
    first = log.spread[0]
    lines = [
        phrase(
            locale,
            "log.spread.set",
            count=first.runs,
            excluded=_excluded_text(first, locale),
        )
    ]
    if first.unidentified:
        lines.append(
            phrase(
                locale,
                "log.spread.unidentified",
                count=first.unidentified,
                total=first.runs,
            )
        )
    if first.commits:
        lines.append(phrase(locale, "log.spread.commits", count=first.commits))
    if first.versions:
        lines.append(
            phrase(locale, "log.spread.versions", versions=", ".join(first.versions))
        )
    for item in log.spread:
        if item.low is None or item.high is None:
            # Exclusions and no range. The reader is told which runs were left
            # out and why, which is the whole of what this reading can say when
            # nothing in the store was measured the same way.
            lines.append(phrase(locale, "log.spread.no_comparable", name=item.name))
            continue
        if item.reference is None:
            lines.append(
                phrase(
                    locale,
                    "log.spread.range.alone",
                    name=item.name,
                    latest=fmt_score(item.latest),
                    low=fmt_score(item.low),
                    high=fmt_score(item.high),
                )
            )
        else:
            lines.append(
                phrase(
                    locale,
                    "log.spread.range",
                    name=item.name,
                    latest=fmt_score(item.latest),
                    reference=fmt_score(item.reference),
                    difference=fmt_score(item.latest - item.reference),
                    low=fmt_score(item.low),
                    high=fmt_score(item.high),
                )
            )
        # Printed where it exists and labelled as the other measurement: the
        # folded aggregate is steadier than any single-sample one, so the two
        # intervals answer different questions and are never set against each
        # other. (ADR 0024 §7.3)
        if item.within_low is not None and item.within_high is not None:
            lines.append(
                phrase(
                    locale,
                    "log.spread.within",
                    low=fmt_score(item.within_low),
                    high=fmt_score(item.within_high),
                )
            )
    lines.append(phrase(locale, "log.spread.floor"))
    return lines


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
        if any(span.absence in UNIDENTIFIED for span in log.spans):
            lines.append("")
            lines.append(phrase(locale, "log.canary_only"))
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
    lines.append(phrase(locale, "log.spread.heading"))
    lines.extend(_spread_lines(log, locale))

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
