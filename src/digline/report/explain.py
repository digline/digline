"""The reading: the same facts the report compresses, expanded and in order.

Two things live here, and the order between them is the whole of ADR 0012 §2.
`facts()` produces the **fact list** — typed values, no language, no numbers of
its own — and `explain_text()` renders it. `digline.wire.explain` renders the
same list for a program. Neither rendering is the source; the list is, so two
front ends cannot come to describe one run differently.

Pure, like the rest of this package: no I/O, no clock. And **no fact carries a
reason.** Not filtered on the way out — absent from the types, which is what
makes fixed decision 9's boundary something a caller cannot get wrong here
(ADR 0012 §4). For the judge's words, `digline report` is one command away.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, assert_never

from digline.core import (
    IDENTITY_FIELD,
    ArtifactDelta,
    AssertionDelta,
    Comparison,
    ConfigDelta,
    ConfigOutcome,
    ConfigValue,
    Noise,
    Run,
    Scope,
    SystemConfig,
    Verdict,
)
from digline.report.render import (
    ABSENT,
    SECTIONS,
    diff_lines,
    diff_tally,
    errored_verdicts,
    fmt_score,
    fmt_value,
    run_tally,
)
from digline.report.text import Locale, phrase, strings

__all__ = [
    "CheckFact",
    "CheckKind",
    "Fact",
    "SettingFact",
    "SettingKind",
    "TallyFact",
    "TallyKind",
    "explain_text",
    "facts",
]

#: What a check-shaped fact can say. Eight of them, and the vocabulary is
#: `Outcome`'s plus the three states a run has without a reference: a check
#: under its bar, a check that errored, and a case somebody set aside.
#:
#: `suspended` carries a case and **no check**, which is the one place this
#: type bends. It bends the way the report already bends: `SECTIONS` puts the
#: suspended section among the outcome sections and feeds it from the run,
#: because a case set aside occupies the place checks occupy and says none ran.
type CheckKind = Literal[
    "regressed",
    "improved",
    "unchanged",
    "within_noise",
    "new",
    "missing",
    "errored",
    "failing",
    "suspended",
]

#: Which of the three things under examination a setting belongs to. Not the
#: outcome — that is `ConfigOutcome`, and it is the same five words for a
#: parameter and for a file, deliberately.
type SettingKind = Literal["target", "judge", "artifact"]

#: The run-level counts and states, and this list is closed by ADR 0012 §3. A
#: reading that wanted a ninth would be saying something the report does not,
#: which is the thing the same-truth rule forbids.
type TallyKind = Literal[
    "cases",
    "checks",
    "unjudged",
    "suspended",
    "within_noise",
    "suite_config",
    "comparability",
]


@dataclass(frozen=True, slots=True)
class CheckFact:
    """One check, and what is true of it.

    `case_id` is empty in run scope and `assertion` is empty on a suspension —
    the same convention `AssertionDelta` follows for the first, so a reader who
    has learnt it once has learnt it in both places.

    No `reason`, by ADR 0012 §4. The field is absent rather than emptied,
    because a field that exists is a field a later edit fills.
    """

    kind: CheckKind
    scope: Scope
    case_id: str
    assertion: str
    assertion_id: str
    before: float | None = None
    after: float | None = None
    delta: float | None = None
    threshold: float | None = None
    #: The interval the movement was judged against — the **baseline's**, as
    #: `compare()` measured it. Absent where there is none, and silence is what
    #: "not known" sounds like: ADR 0006 §5 refuses to print a phrase about a
    #: measurement nobody took.
    noise: Noise = Noise()


@dataclass(frozen=True, slots=True)
class SettingFact:
    """One named thing under examination that is worth stating.

    `outcome` is `None` where there was nothing to compare against — a run read
    on its own. That is not a sixth word in the vocabulary: it is the absence of
    a comparison, and `_run_artifacts` already says why the column is missing
    rather than empty in that document. `after` then carries what the value
    *was*, which is all a single run can say.

    No digest, ever, and not only when withheld: a digest is a verifier, prompts
    live in a guessable space, and one travelling beside a withheld prompt would
    defeat the withholding it travelled beside (ADR 0003 §4).
    """

    kind: SettingKind
    name: str
    outcome: ConfigOutcome | None = None
    before: ConfigValue = None
    after: ConfigValue = None
    withheld: bool = False
    #: Lines added and removed, for a file whose two versions are both in hand.
    #: Zero and zero where they are not, which the renderer reads as "no tally"
    #: rather than as "no change".
    added: int = 0
    removed: int = 0


@dataclass(frozen=True, slots=True)
class TallyFact:
    """One run-level count, or one run-level state.

    `count` for the first, `state` for the second, and never both: a fact that
    carried a number and a boolean would be two facts sharing a row.
    """

    kind: TallyKind
    count: int = 0
    state: bool | None = None


type Fact = CheckFact | SettingFact | TallyFact

#: The comparison outcomes, in the order the document reads them. Taken from
#: `SECTIONS` rather than written out again, so a change to the report's
#: reading order moves the reading with it — which is what ADR 0012 §2 asks of
#: every fact this module states about order as well as about content.
_OUTCOME_ORDER: Sequence[str] = tuple(
    outcome for section in SECTIONS for outcome in section.outcomes
)


def facts(run: Run, comparison: Comparison | None = None) -> tuple[Fact, ...]:
    """The reading, as values.

    `comparison` is `None` when the suite has no baseline, and that is the
    whole of the scope decision — the caller reads the store and passes what it
    found, exactly as `cmd_report` does. Nothing here asks which mode it is in;
    it asks whether there is a comparison, which is a fact rather than a flag.

    The baseline `Run` is deliberately not a parameter. Everything comparative
    a reading states is already on the `Comparison`, and a second copy of the
    reference in the signature would be a second place to read it from.
    """
    out: list[Fact] = [*_tallies(run, comparison)]
    out.extend(_settings(run, comparison))
    out.extend(_checks(run, comparison))
    return tuple(out)


def _tallies(run: Run, comparison: Comparison | None) -> list[Fact]:
    """The frame, before any number in it means anything.

    Every suppression here is copied from `headline()`, and copied on purpose:
    the report is silent about noise nobody measured and about a judge that did
    not move, so a reading that spoke would be stating a fact with nowhere to
    appear — which is the visibility half of ADR 0012 §2, failing.
    """
    tally = run_tally(run)
    out: list[Fact] = [
        TallyFact("cases", count=tally.cases),
        TallyFact("checks", count=tally.checks),
        TallyFact("unjudged", count=tally.unjudged),
        TallyFact("suspended", count=tally.suspended),
    ]
    if comparison is None:
        return out

    covered = sum(1 for delta in comparison.deltas if delta.within_noise)
    if covered:
        out.append(TallyFact("within_noise", count=covered))
    out.append(TallyFact("suite_config", state=comparison.config_changed))
    # The judge speaks only when it moved, as in the headline sentence. A judge
    # that did not is not news; one that did makes every number above it less
    # comparable than it looks.
    if comparison.comparability_reduced:
        out.append(TallyFact("comparability", state=True))
    return out


def _settings(run: Run, comparison: Comparison | None) -> list[Fact]:
    """What differed underneath the scores — or, alone, what was set up.

    Files first, then the system, then the instrument: ADR 0003 §5 and ADR 0005
    §5 both put what changed above what it did, and a prompt that moved changes
    how every line after it reads.
    """
    if comparison is None:
        alone: list[Fact] = [
            SettingFact("artifact", path, withheld=artifact.withheld)
            for path, artifact in sorted(run.artifacts.items())
        ]
        # The annotation is what keeps `kind` a `SettingKind`. A bare tuple of
        # pairs widens the literal to `str`, and every call below would then
        # accept any string at all: Python infers the narrowest type it is
        # asked for, so here it has to be asked.
        systems: Sequence[tuple[SettingKind, SystemConfig]] = (
            ("target", run.target_config),
            ("judge", run.judge_config),
        )
        for kind, config in systems:
            # `redacted()`, never `.values`. It is the one place ADR 0005 §2's
            # withholding lives, and reading around it would make a value one
            # surface keeps back reachable through another — which is the
            # hazard `tests/test_wire_boundary.py` was extended to catch, and
            # did, on this exact line.
            kept = config.redacted()
            alone.extend(
                SettingFact(kind, field, after=value)
                for field, value in sorted(kept.values.items())
            )
            # Named, and without a value. "This run kept it back" and "this run
            # recorded none" are different facts, and a reader is owed both.
            alone.extend(
                SettingFact(kind, field, withheld=True)
                for field in sorted(kept.withheld)
            )
        return alone

    out: list[Fact] = [
        _artifact_fact(delta)
        for delta in comparison.artifact_deltas
        if delta.outcome != "same"
    ]
    compared: Sequence[tuple[SettingKind, Sequence[ConfigDelta]]] = (
        ("target", comparison.target_config_deltas),
        ("judge", comparison.judge_config_deltas),
    )
    for kind, deltas in compared:
        out.extend(
            _setting_fact(kind, delta) for delta in deltas if delta.outcome != "same"
        )
    return out


def _artifact_fact(delta: ArtifactDelta) -> SettingFact:
    """One file, with a line tally where both versions are in hand.

    `diff_tally(diff_lines(...))` is the report's own arithmetic, called rather
    than repeated. Where a side is absent or withheld it returns zeroes, and the
    renderer reads a zero tally as "no tally" — there is nothing to count, which
    is a different statement from "nothing changed".
    """
    added, removed = diff_tally(diff_lines(delta))
    return SettingFact(
        "artifact",
        delta.path,
        outcome=delta.outcome,
        withheld=delta.withheld,
        added=added,
        removed=removed,
    )


def _setting_fact(kind: SettingKind, delta: ConfigDelta) -> SettingFact:
    return SettingFact(
        kind,
        delta.field,
        outcome=delta.outcome,
        before=delta.before,
        after=delta.after,
        withheld=delta.withheld,
    )


def _checks(run: Run, comparison: Comparison | None) -> list[Fact]:
    """The checks, worst first, in the document's own reading order."""
    if comparison is None:
        return _checks_alone(run)

    by_outcome: dict[str, list[AssertionDelta]] = {}
    for delta in comparison.deltas:
        if delta.outcome == "unchanged" and not _moved(delta):
            # A check that did not move at all is in the tally and nowhere
            # else. The dossier this depth is taken from draws the line in the
            # same place, and for the reason that makes the floor readable: a
            # movement the interval absorbed has to be shown, or the word
            # "noise" is printed over a page with no noise on it.
            continue
        by_outcome.setdefault(delta.outcome, []).append(delta)

    out: list[Fact] = []
    for outcome in _OUTCOME_ORDER:
        for delta in by_outcome.get(outcome, []):
            out.append(_check_fact(delta))
    out.extend(_suspensions(run))
    return out


def _moved(delta: AssertionDelta) -> bool:
    before = None if delta.baseline is None else delta.baseline.score.score
    after = None if delta.current is None else delta.current.score.score
    return before != after


def _check_fact(delta: AssertionDelta) -> CheckFact:
    """One delta, as a fact. `within_noise` becomes the kind rather than riding
    beside it: in a comparison it is a qualifier on `unchanged`, but a reading
    says one thing per line, and "moved, and the interval covered it" is a
    different sentence from "did not move enough to count"."""
    kind: CheckKind = "within_noise" if delta.within_noise else delta.outcome
    now = delta.current
    before = delta.baseline
    # One side is always present — `compare()` emits no delta with neither —
    # and the identity is the same on both, which is what paired them.
    named = now if now is not None else before
    assert named is not None
    return CheckFact(
        kind=kind,
        scope=delta.scope,
        case_id=delta.case_id,
        assertion=delta.assertion,
        assertion_id=named.assertion_id,
        before=None if before is None else before.score.score,
        after=None if now is None else now.score.score,
        delta=delta.delta,
        threshold=None if now is None else now.threshold,
        noise=Noise(delta.noise_min, delta.noise_max, delta.noise_samples),
    )


def _checks_alone(run: Run) -> list[Fact]:
    """A run with no reference: what it found, not what moved.

    Three states and not four. A check that passed is in the tally and nowhere
    else — naming every green check would bury the ones that are not, and the
    document this is held against files them in a section that is closed.
    """
    out: list[Fact] = [
        CheckFact(
            "failing",
            "case",
            case.case_id,
            verdict.score.name,
            verdict.assertion_id,
            after=verdict.score.score,
            threshold=verdict.threshold,
            noise=_recorded_noise(verdict),
        )
        for case in run.results
        for verdict in case.verdicts
        if verdict.status == "fail"
    ]
    out.extend(
        CheckFact(
            "failing",
            "run",
            "",
            verdict.score.name,
            verdict.assertion_id,
            after=verdict.score.score,
            threshold=verdict.threshold,
            noise=_recorded_noise(verdict),
        )
        for verdict in run.aggregate
        if verdict.status == "fail"
    )
    out.extend(
        CheckFact(
            "errored",
            found.scope,
            found.case_id,
            found.verdict.score.name,
            found.verdict.assertion_id,
            threshold=found.verdict.threshold,
        )
        for found in errored_verdicts(run)
    )
    out.extend(_suspensions(run))
    return out


def _recorded_noise(verdict: Verdict) -> Noise:
    """The interval this run's own samples spanned, where it took more than one.

    Not the baseline's — read alone, there is no baseline, and this is the only
    interval such a run can honestly show: what the instrument did when asked
    the same question several times. Absent at `samples=1`, where `Score` records
    none and ADR 0006 §5's silence applies unchanged.
    """
    score = verdict.score
    if not score.sampled:
        return Noise()
    return Noise(score.sample_min, score.sample_max, len(score.samples))


def _suspensions(run: Run) -> list[Fact]:
    """The cases somebody set aside, named and without their reasons.

    That a case was set aside is a fact about coverage and travels; the stated
    reason is payload and does not, exactly as `run_document` carries
    `suspended` as a boolean. A developer writes things like "fails on the
    Rossi account".
    """
    return [
        CheckFact("suspended", "case", case.case_id, "", "")
        for case in run.results
        if case.suspended is not None
    ]


# --------------------------------------------------------------------------- #
# The prose. One rendering of the list above, and the wire is the other.
# --------------------------------------------------------------------------- #


def explain_text(reading: Sequence[Fact], *, locale: Locale) -> tuple[str, ...]:
    """The reading, in sentences. One line per fact, in the list's order.

    A pure function of the fact list and of nothing else — that is what makes
    "the prose is a render of the list" a property rather than a promise
    (ADR 0012 §3). It is not told which scope it is in: it reads that off the
    list, because a comparison always states whether the suite's rules moved
    and a run read alone has nothing to say about a reference.

    Headings are structure, not facts. They name a group and state nothing, so
    they are the one thing here that answers to no entry in the list.
    """
    strings(locale)  # fail here, not halfway through a reading

    compared = any(
        isinstance(fact, TallyFact) and fact.kind == "suite_config" for fact in reading
    )
    tallies = [f for f in reading if isinstance(f, TallyFact)]
    settings = [f for f in reading if isinstance(f, SettingFact)]
    checks = [f for f in reading if isinstance(f, CheckFact)]
    where = "compared" if compared else "alone"

    lines: list[str] = [phrase(locale, "explain.heading.tally")]
    lines.extend(_tally_line(fact, locale) for fact in tallies)

    lines.append("")
    lines.append(phrase(locale, f"explain.heading.settings.{where}"))
    if settings:
        lines.extend(_setting_line(fact, locale) for fact in settings)
    else:
        lines.append(phrase(locale, "explain.nothing"))

    lines.append("")
    lines.append(phrase(locale, f"explain.heading.checks.{where}"))
    if checks:
        lines.extend(_check_line(fact, locale, compared=compared) for fact in checks)
    else:
        lines.append(phrase(locale, "explain.nothing"))
    return tuple(lines)


def _tally_line(fact: TallyFact, locale: Locale) -> str:
    match fact.kind:
        case "cases" | "checks" | "unjudged" | "suspended":
            return phrase(
                locale,
                f"explain.tally.{fact.kind}.{_count(fact.count)}",
                count=fact.count,
            )
        case "within_noise":
            return phrase(
                locale,
                f"explain.tally.within_noise.{'one' if fact.count == 1 else 'many'}",
                count=fact.count,
            )
        case "suite_config":
            moved = "changed" if fact.state else "unchanged"
            return phrase(locale, f"explain.tally.suite_config.{moved}")
        case "comparability":
            return phrase(locale, "explain.tally.comparability")
    assert_never(fact.kind)


def _count(count: int) -> str:
    """`none`, `one` or `many` — the suffix the tables are written in.

    Three forms rather than a plural rule: "1 case ran" and "no case ran" are
    different sentences in both locales, and a `{count}` template that produced
    "1 cases" would be the sort of thing a reader stops trusting the rest of
    the document for.
    """
    if count == 0:
        return "none"
    return "one" if count == 1 else "many"


def _setting_line(fact: SettingFact, locale: Locale) -> str:
    before, after = fmt_value(fact.before), fmt_value(fact.after)
    if fact.outcome is None:
        # Read alone: what it *was*, because there is no second version for it
        # to have moved from. `_run_artifacts` says the same thing by leaving
        # the outcome column out rather than filling it with a dash.
        if fact.kind != "artifact":
            withheld = ".withheld" if fact.withheld else ""
            return phrase(
                locale,
                f"explain.setting.{fact.kind}.alone{withheld}",
                name=fact.name,
                after=after,
            )
        withheld = ".withheld" if fact.withheld else ""
        return phrase(
            locale, f"explain.setting.artifact.alone{withheld}", name=fact.name
        )

    if fact.kind == "artifact":
        return _artifact_line(fact, locale)
    # An identity row names an instrument rather than a parameter, so a judge
    # that appears or disappears is one that started or stopped grading — never
    # a value that moved. `config_deltas` fixes that; this only reads it.
    if fact.kind == "judge" and fact.name == IDENTITY_FIELD:
        if fact.outcome == "new":
            return phrase(locale, "explain.setting.judge.added", after=after)
        if fact.outcome == "missing":
            return phrase(locale, "explain.setting.judge.removed", before=before)
    return phrase(
        locale,
        f"explain.setting.{fact.kind}.{fact.outcome}",
        name=fact.name,
        before=before,
        after=after,
    )


def _artifact_line(fact: SettingFact, locale: Locale) -> str:
    if fact.outcome != "changed":
        return phrase(
            locale, f"explain.setting.artifact.{fact.outcome}", name=fact.name
        )
    # A zero tally means there was nothing to count — a side absent, or a text
    # withheld — which is a different statement from "nothing changed", and the
    # sentence without the numbers is the one that does not claim otherwise.
    if not fact.added and not fact.removed:
        return phrase(
            locale, "explain.setting.artifact.changed.untallied", name=fact.name
        )
    # `artifacts.tally` and not a second spelling of the same two numbers: the
    # report prints "+3 −1 lines" and the terminal summary prints it too, so a
    # reading that wrote its own would be a third rendering of one arithmetic.
    return phrase(
        locale,
        "explain.setting.artifact.changed",
        name=fact.name,
        tally=phrase(locale, "artifacts.tally", added=fact.added, removed=fact.removed),
    )


#: What separates a case from the check on it. The same middle dot the terminal
#: summary uses, and not a slash: a slash reads as a path, and a case id can
#: contain one.
SUBJECT_SEPARATOR = " · "


def _where(fact: CheckFact, locale: Locale) -> str:
    subject = (
        fact.case_id if fact.scope == "case" else phrase(locale, "explain.where.run")
    )
    return f"{subject}{SUBJECT_SEPARATOR}{fact.assertion}"


def _check_line(fact: CheckFact, locale: Locale, *, compared: bool) -> str:
    where = _where(fact, locale)
    before = ABSENT if fact.before is None else fmt_score(fact.before)
    now = ABSENT if fact.after is None else fmt_score(fact.after)
    # The size of the movement, unsigned: the direction is in the verb, and
    # "a drop of -0.130000" is the sort of double negative a reader has to
    # stop and unpick.
    moved = ABSENT if fact.delta is None else fmt_score(abs(fact.delta))

    match fact.kind:
        case "regressed" | "improved":
            said = phrase(
                locale,
                f"explain.check.{fact.kind}",
                where=where,
                before=before,
                now=now,
                delta=moved,
            )
            return said + _beyond(fact, locale) + _bar(fact, locale, compared=compared)
        case "unchanged" | "within_noise":
            said = phrase(
                locale,
                f"explain.check.{fact.kind}",
                where=where,
                before=before,
                now=now,
            )
            return said + _bar(fact, locale, compared=compared)
        case "new":
            # No score, and the document is why: `detail.new` states that the
            # check is here and not in the reference, and states no number. A
            # reading that printed one would be stating a fact with nowhere to
            # appear. The value is on the fact and in `--json` either way.
            return phrase(locale, "explain.check.new", where=where)
        case "missing":
            return phrase(locale, "explain.check.missing", where=where)
        case "errored":
            return phrase(locale, "explain.check.errored", where=where)
        case "failing":
            said = phrase(locale, "explain.check.failing", where=where, now=now)
            return said + _bar(fact, locale, compared=compared)
        case "suspended":
            return phrase(locale, "explain.check.suspended", case=fact.case_id)
    assert_never(fact.kind)


def _interval(noise: Noise, locale: Locale) -> str:
    """The interval, rendered by the key the report already renders it with, so
    one movement reads the same in a reading and in a document."""
    assert noise.low is not None and noise.high is not None
    return phrase(
        locale,
        "noise.interval",
        low=fmt_score(noise.low),
        high=fmt_score(noise.high),
        count=noise.count,
    )


def _beyond(fact: CheckFact, locale: Locale) -> str:
    """The clause a movement that left the interval carries — and nothing at
    all where no interval was measured. Silence is what "not known" sounds
    like, and a sentence about an absent measurement would read as one
    (ADR 0006 §5)."""
    if not fact.noise.known:
        return ""
    return phrase(locale, "explain.noise.beyond", noise=_interval(fact.noise, locale))


def _bar(fact: CheckFact, locale: Locale, *, compared: bool) -> str:
    """The threshold, where a document states it and nowhere else.

    A run read alone prints `score / threshold` on every verdict row, and the
    aggregates table prints it in both documents. A comparison's case tables do
    not — they are about movement against a reference — so a reading of one
    states no bar either. The value stays on the fact and in `--json`
    regardless: what is held here is what the prose claims. (ADR 0012 §2)
    """
    if fact.threshold is None or (compared and fact.scope == "case"):
        return ""
    return phrase(locale, "explain.bar", threshold=fmt_score(fact.threshold))
