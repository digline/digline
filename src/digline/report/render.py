"""The report: a comparison rendered for someone who does not read code.

Pure functions. Nothing here opens a file, reads the clock or touches the
network — the caller writes the string wherever it belongs. The report is itself
a committable artifact, so it is deterministic byte for byte: the only dates it
shows are the ones the runs recorded.
"""

from __future__ import annotations

import difflib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from html import escape
from typing import Literal

from digline.core import (
    IDENTITY_FIELD,
    OBSERVED_FIELDS,
    ArtifactDelta,
    AssertionDelta,
    CaseResult,
    Comparison,
    ConfigDelta,
    ConfigValue,
    Outcome,
    Run,
    Scope,
    Status,
    SystemConfig,
    Verdict,
)
from digline.report.text import Locale, phrase, strings

__all__ = [
    "fmt_score",
    "ABSENT",
    "DIRTY_SUFFIX",
    "RUN_SECTIONS",
    "SECTIONS",
    "SUMMARY_OUTCOMES",
    "ErroredVerdict",
    "Headline",
    "RunTally",
    "Section",
    "check_line",
    "config_changes",
    "config_lines",
    "errored_verdicts",
    "fmt_value",
    "headline",
    "render_html",
    "render_run_html",
    "run_tally",
    "summary_lines",
    "suspended_cases",
    "unjudged_cases",
]

#: What stands where a parameter has no value on one side. Not localized, for
#: the reason ISO dates are not: two reports of one run must diff line by line.
ABSENT = "—"

#: How the CLI marks a commit taken from a tree with uncommitted changes. The
#: report only reads it: reaching for git is the CLI's job alone.
DIRTY_SUFFIX = "-dirty"


#: Reading order, worst first. The layout is data so it can be reviewed without
#: reading markup, and so the order is one obvious edit rather than a rewrite.
@dataclass(frozen=True, slots=True)
class Section:
    key: str
    open_by_default: bool
    #: Which comparison outcomes land here. Empty for a section fed by the run
    #: itself rather than by the comparison.
    outcomes: Sequence[Outcome] = ()
    #: `suspended` reads the run: a case set aside produces no verdicts, so it
    #: produces no deltas, so the comparison cannot report it at all.
    source: Literal["outcomes", "suspended"] = "outcomes"


SECTIONS: Sequence[Section] = (
    Section("regressions", True, ("regressed",)),
    Section("unjudged", True, ("errored",)),
    Section("suspended", True, source="suspended"),
    Section("changes", False, ("new", "missing")),
    Section("improvements", False, ("improved",)),
    Section("unchanged", False, ("unchanged",)),
)

#: Fixed iteration order for counts, so two renders of one comparison are equal
#: byte for byte regardless of how the mapping was built.
OUTCOME_ORDER: Sequence[Outcome] = (
    "regressed",
    "errored",
    "new",
    "missing",
    "improved",
    "unchanged",
)


@dataclass(frozen=True, slots=True)
class Headline:
    """The first screen, and what a CLI exits on.

    It carries **eight** facts, and they are deliberately not merged into one.

    A regression, a case the suite could not judge, and a case someone chose to
    set aside are three different events needing three different actions: an
    error is neither green nor a regression (ADR 0001), and a suspension is a
    decision rather than an outcome. `config_changed` then changes the meaning
    of all three — if the rules moved, the numbers compare different rules, and
    a reader who does not know that draws the wrong conclusion from every one.

    `target_config_changed` and `judge_config_changed` joined them with ADR
    0005, and they are the answer to the same complaint from the other side:
    `config_changed` says the *rules* moved, `artifacts_changed` says the prompt
    moved, and these two say the system that answered — or the judge that graded
    — was set up differently. Both are absent from the sentence when nothing was
    recorded, for the reason the artifact clause is.

    `artifacts_changed` is the fifth and joined them with ADR 0003. It answers
    the question `config_changed` cannot: the rules are the same and the
    *system* is not, because the prompt moved. Absent from the sentence when the
    suite declares no artifact — a clause about files nobody named would be an
    answer to a question nobody asked.

    `sentence` is the same wording the report prints, so a CLI gate and the
    document a customer opens can never say two different things about one run.
    """

    worse: bool
    unjudged: int
    suspended: int
    config_changed: bool
    counts: Mapping[Outcome, int]
    reasons_available: bool
    sentence: str
    artifacts_changed: bool = False
    #: The system that answered was configured differently — model, temperature,
    #: token cap, region, endpoint. The sixth fact, and the one that separates
    #: "the rules moved" from "the thing being judged moved". (ADR 0005)
    target_config_changed: bool = False
    #: The instrument that graded is not the one that graded the reference, so
    #: the scores are less comparable than their difference suggests. Reported
    #: more strongly than a target change for exactly that reason.
    judge_config_changed: bool = False
    #: The answers were replayed from a stored run rather than measured. The
    #: ninth fact, and it qualifies every number above it: the target was not
    #: asked anything, so what these scores measure is the judging. (ADR 0015 §8)
    rejudged: bool = False
    #: A case that watches the model moved. The tenth fact, and the one that is
    #: **not** folded into `worse`: a canary that improved is a changed model
    #: just as loudly as one that got worse, and saying "one check got worse"
    #: about a check that got better would be the report telling a reader
    #: something untrue in order to produce the right exit code. `exit_code()`
    #: returns 1 for either. (ADR 0016 §5)
    canary_moved: bool = False
    #: How many checks moved and were covered by the interval their baseline
    #: measured. The eighth fact, and the one that keeps the first honest: a run
    #: reported as clean because nothing moved and one reported as clean because
    #: what moved was noise are two different states of the world. (ADR 0006 §9)
    within_noise: int = 0


def fmt_value(value: ConfigValue) -> str:
    """One configuration value, as a reader sees it.

    `str()` and not `fmt_score()`: `0.7` is a temperature somebody typed, and
    `0.700000` reads as a measurement it is not. Python's float repr is the
    shortest one that round-trips, so `0.3` stays `0.3` — and it keeps the dot
    in every locale, like every other number in this document.
    """
    if value is None:
        return ABSENT
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def config_changes(deltas: Sequence[ConfigDelta], locale: Locale) -> str:
    """`temperature 0.3 → 0.7, max_tokens 1024 → 512`.

    The sentence the whole ADR is for: "the configuration differs" sends a
    reader to reconstruct what differed; this is what they would have
    reconstructed. `same` and `unknown` are left out — neither is a change, and
    `unknown` in particular must never be reported as one.
    """
    parts = [
        _change(delta, locale)
        for delta in deltas
        if delta.outcome in ("changed", "new", "missing")
    ]
    return ", ".join(parts)


def _change(delta: ConfigDelta, locale: Locale) -> str:
    """One line of it: a parameter that moved, or an instrument that joined or
    left.

    An instrument is not a value, so it does not read as one. `model a → b` is
    what a *single* judge replaced looks like; two judges where one was swapped
    is one gone and one arrived, and saying it that way is the only phrasing
    that stays true when there are three.
    """
    if delta.field == IDENTITY_FIELD:
        key = "added" if delta.outcome == "new" else "removed"
        label = delta.after if delta.outcome == "new" else delta.before
        return phrase(locale, f"config.judge.{key}", judge=fmt_value(label))
    # `new` and `missing` say "not sent", which is true of a parameter and false
    # of a field the *provider* reported: nobody sent a resolved model id, on
    # either side. `changed` needs no variant — a value that moved reads the
    # same however it was learnt. (ADR 0005 §9)
    key = f"config.change.{delta.outcome}"
    if delta.outcome != "changed" and delta.field in OBSERVED_FIELDS:
        key += ".observed"
    return phrase(
        locale,
        key,
        field=delta.field,
        before=fmt_value(delta.before),
        after=fmt_value(delta.after),
    )


def config_lines(comparison: Comparison, *, locale: Locale) -> Sequence[str]:
    """One compact line per side that moved, for the terminal.

    `system · temperature 0.3 → 0.7`. Short enough to print beside the
    regressions rather than in place of them — unlike a prompt diff, a
    configuration delta *is* the tally.
    """
    lines: list[str] = []
    for key, deltas in (
        ("target", comparison.target_config_deltas),
        ("judge", comparison.judge_config_deltas),
    ):
        changes = config_changes(deltas, locale)
        if changes:
            lines.append(f"{phrase(locale, f'config.terminal.{key}')} · {changes}")
    return tuple(lines)


def fmt_score(value: float) -> str:
    """Numbers keep the dot in every locale: two reports of one run must stay
    comparable line by line."""
    return f"{value:.6f}"


def unjudged_cases(run: Run) -> int:
    """How many cases this run could not judge.

    Counted from the run and from nothing else, which is what makes it usable
    without a reference: a case the suite could not judge is a fact about the
    harness, true whether or not there is anything to compare against. It is
    what `digline report` exits on when there is no baseline.

    Cases, not verdicts, because that is what every sentence built on it says.
    """
    return sum(
        1
        for case in run.results
        if any(verdict.status == "error" for verdict in case.verdicts)
    )


def suspended_cases(run: Run) -> int:
    """How many cases somebody set aside.

    Beside `unjudged_cases` and counted the same way, from the run alone: a
    suspension is a decision rather than an outcome, so it is true whether or
    not there is a reference to compare against.

    A function rather than the expression it replaces, and the expression is
    why: it was written out twice, independently, in `headline()` and in
    `_run_answer()`. Two counters over one fact are two chances to disagree
    about it, and the document that would then contradict itself is the one
    where the headline says a case is suspended and the tally beside it says
    none is. (ADR 0012 §2)
    """
    return sum(1 for case in run.results if case.suspended is not None)


@dataclass(frozen=True, slots=True)
class RunTally:
    """What a run counts about itself, with no reference in sight.

    Four numbers rather than four locals, because they are now read by two
    renderings — the document's tally and the reading `digline explain` gives —
    and a fact two documents state has to come from one place. (ADR 0012 §2)

    `checks` counts verdicts and `unjudged` counts cases, which is a difference
    the report already carries in its labels: one errored case can hold three
    errored verdicts, and both numbers are true. Anything printing them says
    which it is counting.
    """

    cases: int
    checks: int
    unjudged: int
    suspended: int


def run_tally(run: Run) -> RunTally:
    """The run's own four numbers."""
    return RunTally(
        cases=len(run.results),
        checks=sum(len(case.verdicts) for case in run.results),
        unjudged=unjudged_cases(run),
        suspended=suspended_cases(run),
    )


@dataclass(frozen=True, slots=True)
class ErroredVerdict:
    """One check that could not be judged, and where it sits.

    `case_id` is empty in run scope, where the verdict belongs to no case —
    the same convention `AssertionDelta` follows, so a reader who has learnt
    it once has learnt it everywhere.
    """

    scope: Scope
    case_id: str
    verdict: Verdict


def errored_verdicts(run: Run) -> tuple[ErroredVerdict, ...]:
    """Every check this run could not judge, named.

    `unjudged_cases` answers *how many* and is what an exit code is built from.
    This answers *which*, which is what a reading has to say, and it answers it
    **from the run alone**. `_summarized()` can already name them, but only out
    of a `Comparison` — so without a baseline there is nothing that can, and
    "1 case could not be judged" would be as much as any document could manage.

    The traversal is `index_verdicts`' — every case in the run's order, then the
    aggregates — because that is the one walk over a run's verdicts this
    codebase has already fixed, and a second order would be a second answer to
    "which check comes first".
    """
    found = [
        ErroredVerdict("case", case.case_id, verdict)
        for case in run.results
        for verdict in case.verdicts
        if verdict.status == "error"
    ]
    found.extend(
        ErroredVerdict("run", "", verdict)
        for verdict in run.aggregate
        if verdict.status == "error"
    )
    return tuple(found)


def headline(
    comparison: Comparison, run: Run, baseline: Run, *, locale: Locale
) -> Headline:
    strings(locale)  # fail here, not halfway through a document
    counts: dict[Outcome, int] = {o: comparison.counts.get(o, 0) for o in OUTCOME_ORDER}
    regressed = counts["regressed"]

    # Counted from the run, not from the comparison outcomes, and counted in
    # cases because that is what the sentence says.
    #
    # `errored` as an outcome only appears where a verdict *met* its counterpart
    # in the baseline: rule 1 of `compare()` classifies an absent counterpart as
    # `new` before rule 2 can call it `errored`. So a case that is both new and
    # unjudgeable — a case added to the suite that immediately fails to run — is
    # reported as `new`, and reading the tally would let the report announce
    # that every case could be judged while three of them could not.
    unjudged = unjudged_cases(run)

    if regressed == 0:
        worse_text = phrase(locale, "fact.worse.none")
    elif regressed == 1:
        worse_text = phrase(locale, "fact.worse.one")
    else:
        worse_text = phrase(locale, "fact.worse.many", count=regressed)

    suspended = suspended_cases(run)

    # Silent at zero, like the artifact clause and for the same reason: a
    # sentence about noise nobody measured is one the reader learns to skip, and
    # the clause that matters gets skipped with it.
    within_noise = sum(1 for d in comparison.deltas if d.within_noise)
    if within_noise == 0:
        noise_text = ""
    elif within_noise == 1:
        noise_text = phrase(locale, "fact.noise.one")
    else:
        noise_text = phrase(locale, "fact.noise.many", count=within_noise)

    if unjudged == 0:
        unjudged_text = phrase(locale, "fact.unjudged.none")
    elif unjudged == 1:
        unjudged_text = phrase(locale, "fact.unjudged.one")
    else:
        unjudged_text = phrase(locale, "fact.unjudged.many", count=unjudged)

    if suspended == 0:
        suspended_text = phrase(locale, "fact.suspended.none")
    elif suspended == 1:
        suspended_text = phrase(locale, "fact.suspended.one")
    else:
        suspended_text = phrase(locale, "fact.suspended.many", count=suspended)

    config_text = phrase(
        locale,
        "fact.config.changed" if comparison.config_changed else "fact.config.unchanged",
    )

    # Nothing at all when no artifact was declared: most suites declare none,
    # and a sentence that reassures about files nobody named is a sentence the
    # reader learns to skip — which is how the clause that matters gets skipped
    # with it.
    # `unknown` is not a change. A redacted comparison cannot tell whether the
    # prompt moved, and a sentence that counted "cannot tell" as "changed" would
    # put in front of a customer a fact nobody established.
    changed_artifacts = [
        d for d in comparison.artifact_deltas if d.outcome not in ("same", "unknown")
    ]
    unknown_artifacts = [
        d for d in comparison.artifact_deltas if d.outcome == "unknown"
    ]
    artifact_text = ""
    if comparison.artifact_deltas:
        if unknown_artifacts and not changed_artifacts:
            artifact_text = phrase(locale, "fact.artifacts.unknown")
        elif not changed_artifacts:
            artifact_text = phrase(locale, "fact.artifacts.unchanged")
        elif len(changed_artifacts) == 1:
            artifact_text = phrase(locale, "fact.artifacts.one")
        else:
            artifact_text = phrase(
                locale, "fact.artifacts.many", count=len(changed_artifacts)
            )

    # The canary speaks after what the system *declared* and before the judge,
    # because it says what the system *did*: measured rather than declared, and
    # the stronger of the two. The judge stays last — a moved scale makes even
    # the canary's own numbers less comparable. (ADR 0016 §7)
    canary_text = _canary_fact(comparison, locale)
    # Before the configuration clause, because it qualifies what the numbers
    # *are* rather than how the system was set up: a replay did not ask the
    # target anything. The configuration clause still prints below it — it
    # describes the system that produced the answers being judged, which is
    # still true of them. (ADR 0015 §8)
    rejudged_text = (
        phrase(locale, "fact.rejudged") if run.rejudged_from is not None else ""
    )
    # Same shape as the artifact clause, and silent for the same reason: most
    # runs before ADR 0005 recorded nothing, and a sentence that reassures about
    # a configuration nobody recorded is one the reader learns to skip.
    target_text = _config_fact(
        comparison.target_config_deltas, locale, key="target_config"
    )
    # The judge speaks only when it moved. A judge that did not is not news, and
    # `unknown` about an instrument nobody recorded is not either — while a
    # judge that *did* move is the loudest thing on the page, because it makes
    # every number above it less comparable than it looks.
    judge_changes = config_changes(comparison.judge_config_deltas, locale)
    judge_text = (
        phrase(locale, "fact.judge_config.changed", changes=judge_changes)
        if judge_changes
        else ""
    )

    return Headline(
        worse=regressed > 0,
        within_noise=within_noise,
        unjudged=unjudged,
        suspended=suspended,
        config_changed=comparison.config_changed,
        counts=counts,
        reasons_available=not (run.redacted or baseline.redacted),
        artifacts_changed=bool(changed_artifacts),
        target_config_changed=comparison.target_config_changed,
        judge_config_changed=comparison.judge_config_changed,
        rejudged=run.rejudged_from is not None,
        canary_moved=comparison.canary_moved,
        # Config and artifacts last, because they modify the meaning of
        # everything before them: same rules, different prompt, different run.
        # The judge is last of all: it is the only one that makes the numbers
        # themselves less comparable rather than explaining them.
        sentence=" ".join(
            part
            for part in (
                worse_text,
                # Straight after "nothing got worse", because it is what
                # qualifies it: something did move, and it moved no further than
                # the check moves by itself.
                noise_text,
                unjudged_text,
                suspended_text,
                config_text,
                artifact_text,
                rejudged_text,
                target_text,
                canary_text,
                judge_text,
            )
            if part
        ),
    )


def _canary_fact(comparison: Comparison, locale: Locale) -> str:
    """The clause a moved canary earns, or nothing at all.

    Silent when no canary moved — and silent when a suite declares none, which
    is the same silence for the same reason as the artifact clause: a sentence
    reassuring about a watch nobody set is one the reader learns to skip.

    The first moved canary is named with its numbers, because a name and a pair
    of scores is what a reader acts on; where several moved the count leads and
    one is still named, so the sentence stays a sentence.
    """
    moved = comparison.moved_canaries
    if not moved:
        return ""
    first = moved[0]
    assert first.current is not None and first.baseline is not None
    assert first.current.score.score is not None
    assert first.baseline.score.score is not None
    interval = _noise_interval(first, locale)
    beyond = phrase(locale, "fact.canary.beyond", interval=interval) if interval else ""
    where = first.case_id or first.assertion
    key = "fact.canary.one" if len(moved) == 1 else "fact.canary.many"
    return phrase(
        locale,
        key,
        count=len(moved),
        case=where,
        before=fmt_score(first.baseline.score.score),
        after=fmt_score(first.current.score.score),
        beyond=beyond,
    )


def _config_fact(deltas: Sequence[ConfigDelta], locale: Locale, *, key: str) -> str:
    """The headline clause about one configuration, or nothing to say.

    Nothing at all when neither side recorded one — a plain-function target, or
    two runs that predate ADR 0005. `unknown` is not a change and never renders
    as one: a run compared against a baseline that predates the record says so,
    which is a different sentence from "it moved" and from "it did not".
    """
    if not deltas:
        return ""
    changes = config_changes(deltas, locale)
    if changes:
        return phrase(locale, f"fact.{key}.changed", changes=changes)
    if all(delta.outcome == "unknown" for delta in deltas):
        return phrase(locale, f"fact.{key}.unknown")
    return phrase(locale, f"fact.{key}.unchanged")


def check_line(delta: AssertionDelta, *, locale: Locale, coincides: str = "") -> str:
    """What happened to one check, in one sentence, for a reader.

    Public rather than new: this is the sentence that already filled the
    report's "what happened" column and `compare`'s summary lines, given a name
    so that a third front end can ask for it instead of composing its own. The
    release it became public in is recorded once, in `test_plugin_floors.py`'s
    `INTRODUCED`, which is where a floor is computed from — a second copy here
    would be a version claim nothing gates.

    `pytest-digline` prints it on a failing row (ADR 0013 §6), and the
    alternative — a plugin building the sentence out of
    `delta.current.score`, `delta.threshold` and the interval — would be a
    fourth prose rendering of one comparison with nothing binding it to the
    other three.

    `locale` is keyword-only and mandatory, like every entry point of this
    package: a document string has a recipient who did not choose English.

    Compose the explanation from the structured facts.

    `coincides` is the sentence ADR 0005 exists for: where a drop and a
    configuration change land in the same comparison, the report says so beside
    the drop — *"this drop coincides with temperature 0.3 → 0.7"* — instead of
    leaving a reviewer to blame the prompt for something the temperature did.
    "Coincides" is the strongest word the data supports: two facts in one
    comparison are not a cause, and claiming one would be a finding nobody
    established.

    `AssertionDelta.reason` is deliberately not echoed: it is English text
    generated by `compare()` for a developer, and reprinting it inside an
    Italian report would leak the engine's language into the document. Only the
    judge's own `reason` is quoted verbatim, because that is content rather than
    interface.
    """
    text = _detail_text(delta, locale)
    if coincides and delta.outcome == "regressed":
        text += phrase(locale, "config.coincides", changes=coincides)
    return text


def _detail_text(delta: AssertionDelta, locale: Locale) -> str:
    now, before = delta.current, delta.baseline
    errored_now = now is not None and now.status == "error"
    if delta.outcome == "new":
        # A case added to the suite that fails to run on its first day is `new`
        # by rule 1 of `compare()`, which classifies an absent counterpart
        # before rule 2 can call it `errored`. Saying only "new" would hide the
        # part that needs fixing.
        return phrase(locale, "detail.new.errored" if errored_now else "detail.new")
    if delta.outcome == "missing":
        return phrase(locale, "detail.missing")
    if delta.outcome == "errored":
        return phrase(locale, "detail.errored")

    assert now is not None and before is not None
    assert now.score.score is not None and before.score.score is not None
    was, is_now = fmt_score(before.score.score), fmt_score(now.score.score)

    if now.status != before.status:
        key = (
            "detail.flipped.worse"
            if before.status == "pass"
            else "detail.flipped.better"
        )
        text = phrase(locale, key, before=was, now=is_now)
        if now.threshold != before.threshold:
            text += phrase(
                locale,
                "detail.threshold_moved",
                before_threshold=fmt_score(before.threshold),
                now_threshold=fmt_score(now.threshold),
            )
        return text

    # The measured floor, where there is one. Three sentences rather than a
    # clause appended to the existing three: "beyond the noise" changes what the
    # sentence claims, and a reader has to see it inside the statement rather
    # than trailing it. (ADR 0006 §10)
    noise = _noise_interval(delta, locale)

    if delta.within_noise:
        return phrase(
            locale, "detail.within_noise", before=was, now=is_now, noise=noise
        )
    if delta.outcome == "regressed":
        key = "detail.dropped.beyond_noise" if noise else "detail.dropped"
        return phrase(locale, key, before=was, now=is_now, noise=noise)
    if delta.outcome == "improved":
        key = "detail.rose.beyond_noise" if noise else "detail.rose"
        return phrase(locale, key, before=was, now=is_now, noise=noise)
    return phrase(locale, "detail.unchanged", now=is_now)


def _noise_interval(delta: AssertionDelta, locale: Locale) -> str:
    """`0.850000–0.950000 across 5 samples`, or nothing at all.

    Nothing where the baseline recorded no interval — a run at `samples=1`, or a
    baseline promoted before ADR 0006. The report then says what it always said,
    rather than a sentence about a measurement nobody has: "the noise of this
    check is not known" is what silence means here, and inventing a phrase for
    it would put an absent fact on the page. (ADR 0006 §5)
    """
    if delta.noise_min is None or delta.noise_max is None:
        return ""
    return phrase(
        locale,
        "noise.interval",
        low=fmt_score(delta.noise_min),
        high=fmt_score(delta.noise_max),
        count=delta.noise_samples,
    )


#: What separates the three fields of a summary line. Not a tab: the columns
#: have wildly different widths and aligning them would make the short lines
#: unreadable to buy neatness for the long ones.
SUMMARY_SEPARATOR = " · "

#: Which outcomes a terminal summary reports, in reading order. The rest is
#: noise on a command line — it belongs in the document, where it can be folded.
SUMMARY_OUTCOMES: Sequence[Outcome] = ("regressed", "errored")


def _summarized(comparison: Comparison) -> Sequence[AssertionDelta]:
    """Regressions first, then anything that could not run.

    The second group is *not* simply the `errored` outcome. A case added to the
    suite that fails on its first day is classified `new`, because rule 1 of
    `compare()` looks at presence before rule 2 looks at status — so selecting
    on the outcome alone would let the headline say "1 case could not be judged"
    while the list below it named nothing. The two must agree.
    """
    regressed = [d for d in comparison.deltas if d.outcome == "regressed"]
    unjudged = [
        d
        for d in comparison.deltas
        if d.outcome != "regressed"
        and d.current is not None
        and d.current.status == "error"
    ]
    return (*regressed, *unjudged)


def artifact_lines(comparison: Comparison, *, locale: Locale) -> Sequence[str]:
    """One compact line per changed file, for the terminal.

    `prompt.md · +3 −1 lines`. The tally, not the diff: a terminal summary that
    unrolled a prompt would bury the regressions it exists to point at, and the
    document is one command away.

    Nothing at all when an artifact was withheld — the count is in the headline
    sentence, and a path is payload.
    """
    if any(delta.withheld for delta in comparison.artifact_deltas):
        return ()
    lines: list[str] = []
    for delta in comparison.artifact_deltas:
        if delta.outcome in ("same", "unknown"):
            continue
        tally = diff_tally(diff_lines(delta))
        detail = (
            phrase(locale, "artifacts.tally", added=tally[0], removed=tally[1])
            if any(tally)
            else phrase(locale, f"artifacts.outcome.{delta.outcome}")
        )
        lines.append(f"{delta.path} · {detail}")
    return tuple(lines)


def summary_lines(
    comparison: Comparison,
    run: Run,
    baseline: Run,
    *,
    locale: Locale,
    limit: int | None = None,
) -> Sequence[str]:
    """One line per regression and per unjudged check: what to fix, in order.

    The third field is produced by the **same** `check_line()` that fills the
    report's "what happened" column, so a terminal and a document can never
    describe one delta in two ways. That is the same reason `Headline.sentence`
    exists: two renderings of one fact drift apart the moment they have two
    sources.

    `limit` truncates, and when it does the last line **says so**. A silent
    "first twenty" reads exactly like "all twenty", which is the difference
    between a developer who fixes three regressions and one who fixes two.

    `run` and `baseline` are taken for symmetry with `headline()` and
    `render_html()` — the three entry points of this module accept the same
    three arguments — and are not read: a summary line is composed entirely
    from the delta, so it says the same thing whether or not the run is
    redacted.
    """
    strings(locale)  # fail here rather than halfway down a list
    chosen = _summarized(comparison)
    shown = chosen if limit is None else chosen[:limit]
    # The same coincidence the document prints, from the same function: a
    # terminal that omitted it would send the developer looking at the prompt
    # while the report told the customer about the temperature.
    coincides = config_changes(comparison.config_changes, locale)
    lines = [
        SUMMARY_SEPARATOR.join(
            (
                # A run-level verdict belongs to no case, so it says so rather
                # than opening the line with an empty field.
                d.case_id if d.scope == "case" else phrase(locale, "scope.run"),
                d.assertion,
                check_line(d, locale=locale, coincides=coincides),
            )
        )
        for d in shown
    ]
    if len(shown) < len(chosen):
        lines.append(
            phrase(locale, "summary.truncated", shown=len(shown), total=len(chosen))
        )
    return tuple(lines)


def _reason(delta: AssertionDelta, locale: Locale, *, available: bool) -> str:
    """The judge's own words, when this report is allowed to carry them."""
    if not available:
        return phrase(locale, "reason.unavailable")
    source = delta.current if delta.current is not None else delta.baseline
    return "" if source is None else source.reason


CSS = """\
:root { color-scheme: light; }
body { font: 16px/1.5 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
       margin: 0 auto; max-width: 52rem; padding: 2rem 1rem; color: #16181d; }
h1 { font-size: 1.5rem; margin: 0 0 .25rem; }
h2 { font-size: 1.1rem; margin: 0 0 .25rem; }
.aggregates { margin: 0 0 2rem; }
dl.meta { display: grid; grid-template-columns: max-content 1fr; gap: .25rem 1rem;
          margin: 1rem 0 2rem; font-size: .9rem; }
dt { color: #5b6270; }
dd { margin: 0; }
.answer { border: 2px solid currentColor; border-radius: .5rem; padding: 1rem 1.25rem;
          margin: 0 0 2rem; }
.answer.worse { color: #8a1c1c; }
.answer.fine { color: #17552e; }
.answer .verdict { font-size: 2rem; font-weight: 700; line-height: 1; }
.answer p { color: #16181d; margin: .75rem 0 0; }
.tally { list-style: none; display: flex; flex-wrap: wrap; gap: 1rem;
         padding: 0; margin: 1rem 0 0; font-size: .85rem; color: #5b6270; }
.tally b { color: #16181d; }
details { border-top: 1px solid #d8dce3; padding: .75rem 0; }
summary { cursor: pointer; font-weight: 600; }
table { border-collapse: collapse; width: 100%; margin-top: .75rem;
        font-size: .9rem; }
th, td { border-bottom: 1px solid #e6e9ee; padding: .5rem .5rem .5rem 0;
         text-align: left; vertical-align: top; }
th { color: #5b6270; font-weight: 600; }
code { font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
       font-size: .875em; }
.empty { color: #5b6270; font-style: italic; margin: .5rem 0 0; }

/* The diff of a file under test. Fixed width because alignment is the content,
   and coloured rather than only signed so the eye finds the change before it
   reads it. */
pre.diff { background: #f5f6f8; border: 1px solid #d8dce3; border-radius: .375rem;
           padding: .75rem 1rem; overflow-x: auto; font-size: .8125rem;
           line-height: 1.45; margin: .5rem 0 1rem; white-space: pre; }
pre.diff span { display: block; }
.d-add { background: #e6f4ea; color: #14532d; }
.d-del { background: #fceceb; color: #7f1d1d; }
.d-meta { color: #7a828f; }
.d-ctx { color: #3c4350; }
section.config { margin: 0 0 2rem; }
section.artifacts details { border-top: none; padding: .25rem 0; }
section.artifacts summary { font-weight: 400; }

/* Printing is the declared route to PDF, and a printed report that hides the
   regressions is a wrong report. Collapsed sections open on paper. */
@media print {
  body { max-width: none; padding: 0; color: #000; }
  details { display: block; }
  details > summary { list-style: none; }
  details > *:not(summary) { display: block !important; }
  details[open] > *, details:not([open]) > * { display: block !important; }
  .answer { border-color: #000; }
  a[href]::after { content: ""; }
}
"""


def _row(
    delta: AssertionDelta, locale: Locale, *, reasons: bool, coincides: str = ""
) -> str:
    reason = _reason(delta, locale, available=reasons)
    return (
        "<tr>"
        f"<td><code>{escape(delta.case_id)}</code></td>"
        f"<td><code>{escape(delta.assertion)}</code></td>"
        f"<td>{escape(check_line(delta, locale=locale, coincides=coincides))}</td>"
        f"<td>{escape(reason)}</td>"
        "</tr>"
    )


def _suspended_row(case: CaseResult, locale: Locale, *, reasons: bool) -> str:
    stated = case.suspended if reasons else phrase(locale, "reason.unavailable")
    return (
        "<tr>"
        f"<td><code>{escape(case.case_id)}</code></td>"
        f"<td>{escape(stated or '')}</td>"
        "</tr>"
    )


def _table(head_keys: Sequence[str], rows: Sequence[str], locale: Locale) -> str:
    head = "".join(f"<th>{escape(phrase(locale, k))}</th>" for k in head_keys)
    return (
        f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(rows)}</tbody></table>"
    )


def _section(
    section: Section,
    comparison: Comparison,
    run: Run,
    locale: Locale,
    *,
    reasons: bool,
    coincides: str = "",
) -> str:
    title = escape(phrase(locale, f"section.{section.key}"))
    empty = f'<p class="empty">{escape(phrase(locale, "section.empty"))}</p>'
    open_attr = " open" if section.open_by_default else ""

    if section.source == "suspended":
        # Read from the run, not from the comparison: a suspended case produces
        # no verdicts, so it produces no deltas, so the comparison cannot report
        # it at all — and a coverage gap nobody sees is the reason suspension
        # had to be declared in the first place.
        cases = [c for c in run.results if c.suspended is not None]
        body = (
            empty
            if not cases
            else _table(
                ("column.case", "column.reason"),
                [_suspended_row(c, locale, reasons=reasons) for c in cases],
                locale,
            )
        )
        count = len(cases)
    else:
        wanted = frozenset(section.outcomes)
        rows = [d for d in comparison.deltas if d.outcome in wanted]
        body = (
            empty
            if not rows
            else _table(
                ("column.case", "column.check", "column.detail", "column.reason"),
                [_row(d, locale, reasons=reasons, coincides=coincides) for d in rows],
                locale,
            )
        )
        count = len(rows)

    return f"<details{open_attr}><summary>{title} ({count})</summary>{body}</details>"


def _aggregates(
    run: Run, locale: Locale, *, reasons: bool, worse: bool, comparative: bool = True
) -> str:
    """The run-level verdicts, above the cases.

    They come first because they are what gates a release: four runs of one
    unchanged prompt agreed with the human mark on 14, 14, 15, 15 of 21 cases
    while individual cases moved by three votes. The aggregate is the answer,
    the cases are the diagnosis.

    The two exclusions are printed **beside** every figure, never under it.
    `suspended_excluded` is the one number in this product that improves by
    doing less work — setting aside a failing case raises the ratio without
    anyone lying — so it travels with the ratio wherever the ratio goes.
    """
    if not run.aggregate:
        return ""

    rows: list[str] = []
    for verdict in run.aggregate:
        score = verdict.score.score
        result = phrase(locale, "detail.errored") if score is None else fmt_score(score)
        counted = phrase(
            locale,
            "aggregate.counted",
            considered=verdict.score.metadata.get("considered", 0),
            suspended=verdict.score.metadata.get("suspended_excluded", 0),
            errored=verdict.score.metadata.get("errored_excluded", 0),
        )
        why = verdict.reason if reasons else phrase(locale, "reason.unavailable")
        rows.append(
            "<tr>"
            f"<td><code>{escape(verdict.score.name)}</code></td>"
            f"<td><b>{escape(result)}</b> / {fmt_score(verdict.threshold)}</td>"
            f"<td>{escape(counted)}</td>"
            f"<td>{escape(why)}</td>"
            "</tr>"
        )

    table = _table(
        ("column.measure", "column.result", "column.detail", "column.reason"),
        rows,
        locale,
    )
    # A failing measure beside an answer of "no" is a combination this document
    # can now show often — a group can be under its threshold in this run and
    # have been under it in the reference, which is `unchanged` and gates
    # nothing. Left unexplained it reads as a defect in the report, so it is
    # said in words, here, under the figures that raise the question rather
    # than in a note somebody has to go and find. (ADR 0010 §10)
    #
    # `comparative` is what turns it off. Without a reference there is no
    # "not worse" to contrast a failing measure with, so the sentence would be
    # a comparison claim in a document that makes none — and a failing figure
    # in a single-run document raises no question to answer: it says the run
    # is under the bar, which is all it says.
    note = ""
    if comparative and not worse and any(v.status == "fail" for v in run.aggregate):
        told = escape(phrase(locale, "aggregates.failing_not_worse"))
        note = f'<p class="note">{told}</p>'
    title = escape(phrase(locale, "aggregates.title"))
    return f'<section class="aggregates"><h2>{title}</h2>{table}{note}</section>'


def _meta(comparison: Comparison, run: Run, baseline: Run, locale: Locale) -> str:
    """The header declares which two environments are being held against each
    other: comparing staging with a production reference is legitimate, and a
    reader must be able to see that is what they are looking at."""
    pairs = [
        ("header.tenant", comparison.tenant),
        ("header.suite", comparison.suite),
        ("header.environment", f"{comparison.environment} — {run.created_at}"),
        (
            "header.baseline_environment",
            f"{comparison.baseline_environment} — {baseline.created_at}",
        ),
    ]
    if run.git_commit is not None:
        commit = run.git_commit
        # A run produced from a dirty tree cannot be reproduced from the
        # repository, and a reader deciding whether to act on it deserves to
        # know that before the numbers, not after.
        if commit.endswith(DIRTY_SUFFIX):
            commit += phrase(locale, "header.dirty")
        pairs.append(("header.commit", commit))
    if baseline.promoted_at:
        # Beside the reference's own line, because it is a fact about *that*
        # document: when somebody read the run and signed it off, which is not
        # when it was measured. Absent where it was not recorded — a baseline
        # promoted before the field existed says nothing rather than guessing.
        pairs.append(("header.promoted", baseline.promoted_at))
    if run.rejudged_from is not None:
        pairs.append(("header.rejudged", run.rejudged_from))
    if run.redacted or baseline.redacted:
        pairs.append(("header.redacted", phrase(locale, "header.redacted.value")))
    return "".join(
        f"<dt>{escape(phrase(locale, key))}</dt><dd>{escape(value)}</dd>"
        for key, value in pairs
    )


def _artifacts(comparison: Comparison, locale: Locale) -> str:
    """What changed in the files under test, before what it did to the scores.

    Above the deltas because it is the cause and they are the effect: a reader
    who sees the prompt changed reads the regressions differently, and finding
    that out afterwards is finding it out too late. A suite that declares no
    artifact renders nothing at all — an empty section would be a question the
    reader did not ask.

    The diff is not rendered here, only what moved and the texts themselves. A
    line-level diff belongs where there is room for it; the document's job is to
    say that the thing under test is not the thing that was approved.
    """
    if not comparison.artifact_deltas:
        return ""
    changed = [
        d for d in comparison.artifact_deltas if d.outcome not in ("same", "unknown")
    ]
    unknown = [d for d in comparison.artifact_deltas if d.outcome == "unknown"]
    if unknown and not changed:
        note = phrase(locale, "artifacts.withheld")
    elif not changed:
        note = phrase(locale, "artifacts.unchanged")
    elif len(changed) == 1:
        note = phrase(locale, "artifacts.changed.one")
    else:
        note = phrase(locale, "artifacts.changed.many", count=len(changed))

    rows = "".join(
        "<tr>"
        f"<td><code>{escape(delta.path)}</code></td>"
        f"<td>{escape(_artifact_detail(delta, locale))}</td>"
        "</tr>"
        for delta in (*changed, *unknown)
    )
    table = (
        "<table><thead><tr>"
        f"<th>{escape(phrase(locale, 'artifacts.column.file'))}</th>"
        f"<th>{escape(phrase(locale, 'artifacts.column.what'))}</th>"
        "</tr></thead>"
        f"<tbody>{rows}</tbody></table>\n"
        if rows
        else ""
    )
    # Withheld: the count and nothing else. Not the diff, not the digest, and
    # not the table either — a path is `prompts/acme-underwriting-rules.md`
    # often enough that a list of them is a description of the customer. The
    # sentence above is a measurement; everything below it is payload.
    if any(delta.withheld for delta in comparison.artifact_deltas):
        return (
            '<section class="artifacts">\n'
            f"<h2>{escape(phrase(locale, 'artifacts.title'))}</h2>\n"
            f"<p>{escape(note)}</p>\n"
            "</section>"
        )

    # The diffs come after the table and before the score deltas: what changed,
    # then how, then what it did.
    diffs = "".join(_diff_html(delta, locale) for delta in changed)
    return (
        '<section class="artifacts">\n'
        f"<h2>{escape(phrase(locale, 'artifacts.title'))}</h2>\n"
        f"<p>{escape(note)}</p>\n"
        f"{table}"
        f"{diffs}"
        "</section>"
    )


def _config_table(
    deltas: Sequence[ConfigDelta], locale: Locale, *, key: str, note: str
) -> str:
    """One side's configuration, this run beside the reference.

    Every recorded parameter, not only the ones that moved: a reader in world 3
    wants to know what answered, and a table that showed only the differences
    would answer a question they did not ask while leaving the one they did.

    A withheld value says so in both columns. The parameter *names* are not
    payload — `temperature` describes nobody — so unlike a withheld artifact,
    whose very path can name a customer, the row survives with its value gone.
    """
    if not deltas:
        return ""
    rows = "".join(_config_row(delta, locale) for delta in deltas)
    heads = "".join(
        f"<th>{escape(phrase(locale, column))}</th>"
        for column in (
            "config.column.parameter",
            "config.column.value",
            "config.column.reference",
        )
    )
    return (
        f'<section class="config">\n'
        f"<h2>{escape(phrase(locale, key))}</h2>\n"
        f"<p>{escape(note)}</p>\n"
        f"<table><thead><tr>{heads}</tr></thead><tbody>{rows}</tbody></table>\n"
        "</section>"
    )


def _config_row(delta: ConfigDelta, locale: Locale) -> str:
    now = _config_cell(delta.after, locale, withheld=delta.withheld)
    before = _config_cell(delta.before, locale, withheld=delta.withheld)
    return (
        "<tr>"
        f"<td><code>{escape(delta.field)}</code></td>"
        f"<td>{escape(now)}</td>"
        f"<td>{escape(before)}</td>"
        "</tr>"
    )


def _config_cell(value: ConfigValue, locale: Locale, *, withheld: bool) -> str:
    return phrase(locale, "config.value.withheld") if withheld else fmt_value(value)


def _config_note(deltas: Sequence[ConfigDelta], locale: Locale) -> str:
    changed = [d for d in deltas if d.outcome in ("changed", "new", "missing")]
    if changed:
        key = "config.changed.one" if len(changed) == 1 else "config.changed.many"
        return phrase(locale, key, count=len(changed))
    if all(delta.outcome == "unknown" for delta in deltas):
        return phrase(locale, "config.unknown")
    return phrase(locale, "config.unchanged")


def _configs(comparison: Comparison, locale: Locale) -> str:
    """What answered and what judged, above the scores that came out of them.

    Beside the artifact diff and for its reason (ADR 0003 §5): what changed
    comes before what it did. The judge's table carries the stronger note, since
    a moved instrument makes every number below it less comparable rather than
    explaining it.
    """
    target = _config_table(
        comparison.target_config_deltas,
        locale,
        key="config.title",
        note=_config_note(comparison.target_config_deltas, locale),
    )
    judge_note = (
        phrase(locale, "config.judge.reduced")
        if comparison.comparability_reduced
        else _config_note(comparison.judge_config_deltas, locale)
    )
    judge = _config_table(
        comparison.judge_config_deltas,
        locale,
        key="config.judge.title",
        note=judge_note,
    )
    return "\n".join(part for part in (target, judge) if part)


#: Above this many changed lines the diff opens closed. A prompt rewritten from
#: scratch is not read line by line in a report; a prompt with one clause moved
#: is exactly what the reader came for, and making them click for it is making
#: them miss it.
DIFF_OPEN_LIMIT = 30

#: Lines of context either side, `diff -U3` and every review tool since.
DIFF_CONTEXT = 3


def diff_lines(delta: ArtifactDelta) -> list[str]:
    """The unified diff of one artifact, or nothing to show.

    Empty whenever a side is missing — withheld, added or removed — because a
    diff against nothing is the whole file, and printing a whole withheld file
    is the one thing this must never do.
    """
    if delta.withheld or delta.before is None or delta.after is None:
        return []
    return list(
        difflib.unified_diff(
            delta.before.splitlines(),
            delta.after.splitlines(),
            fromfile=f"a/{delta.path}",
            tofile=f"b/{delta.path}",
            lineterm="",
            n=DIFF_CONTEXT,
        )
    )


def diff_tally(lines: Sequence[str]) -> tuple[int, int]:
    """Added and removed, not counting the `+++`/`---` file headers."""
    added = sum(1 for x in lines if x.startswith("+") and not x.startswith("+++"))
    removed = sum(1 for x in lines if x.startswith("-") and not x.startswith("---"))
    return added, removed


def _diff_html(delta: ArtifactDelta, locale: Locale) -> str:
    lines = diff_lines(delta)
    if not lines:
        return ""
    added, removed = diff_tally(lines)
    body = "".join(
        f'<span class="{_diff_class(line)}">{escape(line)}</span>\n' for line in lines
    )
    tally = phrase(locale, "artifacts.tally", added=added, removed=removed)
    opened = " open" if added + removed < DIFF_OPEN_LIMIT else ""
    return (
        f"<details{opened}><summary><code>{escape(delta.path)}</code> "
        f"{escape(tally)}</summary>\n"
        f'<pre class="diff">{body}</pre>\n'
        "</details>\n"
    )


def _diff_class(line: str) -> str:
    if line.startswith(("+++", "---", "@@")):
        return "d-meta"
    if line.startswith("+"):
        return "d-add"
    if line.startswith("-"):
        return "d-del"
    return "d-ctx"


def _artifact_detail(delta: ArtifactDelta, locale: Locale) -> str:
    detail = phrase(locale, f"artifacts.outcome.{delta.outcome}")
    if delta.withheld:
        return f"{detail} — {phrase(locale, 'artifacts.withheld')}"
    return detail


def render_html(
    comparison: Comparison, run: Run, baseline: Run, *, locale: Locale
) -> str:
    """A self-contained HTML document, deterministic byte for byte.

    One inline stylesheet, no external asset, no script: collapsing uses
    `<details>`, which is markup rather than behaviour, so the report reads with
    JavaScript disabled and prints with every section open.

    Complete or redacted is not a parameter — it follows from `run.redacted` and
    `baseline.redacted`. When either side is redacted the document says so and
    states that the reasons are not included, rather than printing the marker.

    `locale` is mandatory and has no default: the language of a document with a
    recipient is not something to settle by omission.
    """
    head = headline(comparison, run, baseline, locale=locale)
    answer = phrase(locale, "answer.yes" if head.worse else "answer.no")
    tally = "".join(
        f"<li>{escape(outcome)} <b>{head.counts[outcome]}</b></li>"
        for outcome in OUTCOME_ORDER
    )
    coincides = config_changes(comparison.config_changes, locale)
    sections = "".join(
        _section(
            s,
            comparison,
            run,
            locale,
            reasons=head.reasons_available,
            coincides=coincides,
        )
        for s in SECTIONS
    )
    title = phrase(locale, "document.title", suite=comparison.suite)
    aggregates = _aggregates(
        run, locale, reasons=head.reasons_available, worse=head.worse
    )

    return (
        "<!DOCTYPE html>\n"
        f'<html lang="{escape(locale)}">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{escape(title)}</title>\n"
        f"<style>\n{CSS}</style>\n"
        "</head>\n"
        "<body>\n"
        f"<h1>{escape(title)}</h1>\n"
        f'<dl class="meta">{_meta(comparison, run, baseline, locale)}</dl>\n'
        f'<section class="answer {"worse" if head.worse else "fine"}">\n'
        f'<p class="verdict">{escape(phrase(locale, "answer.question"))} '
        f"{escape(answer)}</p>\n"
        f"<p>{escape(head.sentence)}</p>\n"
        f'<ul class="tally">{tally}</ul>\n'
        "</section>\n"
        f"{aggregates}\n"
        f"{_artifacts(comparison, locale)}\n"
        f"{_configs(comparison, locale)}\n"
        f"{sections}\n"
        "</body>\n"
        "</html>\n"
    )


# --------------------------------------------------------------------------- #
# The single-run document: what was measured, with nothing held against it
# --------------------------------------------------------------------------- #

#: Reading order for a run judged on its own. The comparison groups by what a
#: verdict *did* — regressed, improved — which is a question about two runs.
#: With one run the only thing a verdict can be grouped by is what it *is*, so
#: these are statuses. Worst first and the first three open, the same rule
#: `SECTIONS` follows, so a reader who knows one document can read the other.
RUN_SECTIONS: Sequence[tuple[str, bool, Status | None]] = (
    ("failed", True, "fail"),
    ("unjudged", True, "error"),
    ("suspended", True, None),
    ("passed", False, "pass"),
)


def _run_meta(run: Run, locale: Locale) -> str:
    """The header, without the row that names a reference.

    Absent rather than empty: a "Reference" line reading "—" would invite the
    reader to wonder which reference produced nothing, when the answer is that
    there is none.
    """
    pairs = [
        ("header.tenant", run.tenant),
        ("header.suite", run.suite),
        ("header.environment", f"{run.environment} — {run.created_at}"),
    ]
    if run.git_commit is not None:
        commit = run.git_commit
        if commit.endswith(DIRTY_SUFFIX):
            commit += phrase(locale, "header.dirty")
        pairs.append(("header.commit", commit))
    if run.rejudged_from is not None:
        pairs.append(("header.rejudged", run.rejudged_from))
    if run.redacted:
        pairs.append(("header.redacted", phrase(locale, "header.redacted.value")))
    return "".join(
        f"<dt>{escape(phrase(locale, key))}</dt><dd>{escape(value)}</dd>"
        for key, value in pairs
    )


def _run_answer(run: Run, locale: Locale) -> str:
    """The slot the verdict occupies in a comparison, saying why there is none.

    `class="answer"` with no modifier, which is the whole of the styling
    decision: `worse` is red and `fine` is green, and either would be a claim.
    The neutral state is the absence of the claim, so it is the absence of the
    modifier — and it costs the stylesheet nothing, which keeps every existing
    report byte for byte what it was.

    The tally beside it counts the run's own facts. The comparison tally counts
    outcomes, and an outcome is a relation between two runs: printing it here
    with six zeroes would say "nothing regressed", which is exactly the thing
    this document must not say.
    """
    tally_of = run_tally(run)
    counted = (
        ("runtally.cases", tally_of.cases),
        ("runtally.checks", tally_of.checks),
        ("runtally.unjudged", tally_of.unjudged),
        ("runtally.suspended", tally_of.suspended),
    )
    tally = "".join(
        f"<li>{escape(phrase(locale, key))} <b>{value}</b></li>"
        for key, value in counted
    )
    return (
        '<section class="answer">\n'
        f'<p class="verdict">{escape(phrase(locale, "noreference.title"))}</p>\n'
        f"<p>{escape(phrase(locale, 'noreference.sentence'))}</p>\n"
        f'<ul class="tally">{tally}</ul>\n'
        "</section>"
    )


def _run_artifacts(run: Run, locale: Locale) -> str:
    """The files that were under test, by path and fingerprint.

    No diff and no outcome column: both are statements about a second version
    that does not exist here. What is left is what ADR 0003 says a run records
    — which files were the thing under test, and what they were.

    The text follows the same rule it does everywhere: present when the run
    carries it, absent when the suite withheld it. Nothing is decided here; the
    run already had the decision applied to it.
    """
    if not run.artifacts:
        return ""
    rows: list[str] = []
    bodies: list[str] = []
    for path, artifact in sorted(run.artifacts.items()):
        mark = (
            phrase(locale, "artifacts.withheld")
            if artifact.withheld
            else artifact.sha[:12]
        )
        rows.append(
            "<tr>"
            f"<td><code>{escape(path)}</code></td>"
            f"<td><code>{escape(mark)}</code></td>"
            "</tr>"
        )
        if artifact.text is not None:
            bodies.append(
                f"<details><summary>{escape(path)}</summary>"
                f"<pre>{escape(artifact.text)}</pre></details>"
            )
    table = _table(
        ("artifacts.column.file", "artifacts.column.fingerprint"), rows, locale
    )
    title = escape(phrase(locale, "artifacts.title"))
    return (
        f'<section class="artifacts"><h2>{title}</h2>{table}{"".join(bodies)}</section>'
    )


def _run_config_table(config: SystemConfig, locale: Locale, *, key: str) -> str:
    """One system's configuration as values, where the comparison shows deltas.

    Through `SystemConfig` as recorded: a withheld parameter is named and its
    value is not, which is the same shape ADR 0005 gives the delta table — the
    reader is owed the fact that a parameter exists even when its value stays
    inside the perimeter.
    """
    if not config.values and not config.withheld:
        return ""
    rows = [
        f"<tr><td><code>{escape(name)}</code></td><td>{escape(str(value))}</td></tr>"
        for name, value in sorted(config.values.items())
    ]
    rows += [
        "<tr>"
        f"<td><code>{escape(name)}</code></td>"
        f"<td>{escape(phrase(locale, 'config.value.withheld'))}</td>"
        "</tr>"
        for name in sorted(config.withheld)
    ]
    table = _table(("config.column.parameter", "config.column.value"), rows, locale)
    title = escape(phrase(locale, key))
    return f'<section class="config"><h2>{title}</h2>{table}</section>'


def _run_configs(run: Run, locale: Locale) -> str:
    parts = (
        _run_config_table(run.target_config, locale, key="config.title"),
        _run_config_table(run.judge_config, locale, key="config.judge.title"),
    )
    return "\n".join(part for part in parts if part)


def _run_verdict_row(
    case_id: str, verdict: Verdict, locale: Locale, *, reasons: bool
) -> str:
    score = verdict.score.score
    result = phrase(locale, "detail.errored") if score is None else fmt_score(score)
    why = verdict.reason if reasons else phrase(locale, "reason.unavailable")
    return (
        "<tr>"
        f"<td><code>{escape(case_id)}</code></td>"
        f"<td><code>{escape(verdict.score.name)}</code></td>"
        f"<td><b>{escape(result)}</b> / {fmt_score(verdict.threshold)}</td>"
        f"<td>{escape(why)}</td>"
        "</tr>"
    )


def _run_section(
    key: str,
    open_by_default: bool,
    status: Status | None,
    run: Run,
    locale: Locale,
    *,
    reasons: bool,
) -> str:
    title = escape(phrase(locale, f"section.{key}"))
    empty = f'<p class="empty">{escape(phrase(locale, "section.empty"))}</p>'
    open_attr = " open" if open_by_default else ""

    if status is None:
        cases = [c for c in run.results if c.suspended is not None]
        body = (
            empty
            if not cases
            else _table(
                ("column.case", "column.reason"),
                [_suspended_row(c, locale, reasons=reasons) for c in cases],
                locale,
            )
        )
        count = len(cases)
    else:
        rows = [
            _run_verdict_row(case.case_id, verdict, locale, reasons=reasons)
            for case in run.results
            for verdict in case.verdicts
            if verdict.status == status
        ]
        body = (
            empty
            if not rows
            else _table(
                ("column.case", "column.check", "column.result", "column.reason"),
                rows,
                locale,
            )
        )
        count = len(rows)

    return f"<details{open_attr}><summary>{title} ({count})</summary>{body}</details>"


def _recorded_answers(run: Run, locale: Locale) -> str:
    """What the target actually said, where the document is allowed to show it.

    Rendered only from a complete run. A redacted one carries nothing but the
    count — `redact()` removed the text, and no `Disclosure` can put it back —
    so the rule needs no flag here: there is simply nothing to render, and the
    section does not appear. (ADR 0015 §4, §8)

    Collapsed by default and last, because it is evidence rather than a finding:
    a reader opens it when a verdict surprises them.
    """
    rows: list[str] = []
    for case in run.results:
        for index, response in enumerate(case.responses, start=1):
            if response.output is None:
                continue
            label = (
                escape(case.case_id)
                if len(case.responses) == 1
                else f"{escape(case.case_id)} · {index}"
            )
            question = "" if response.input is None else response.input
            rows.append(
                "<tr>"
                f"<td><code>{label}</code></td>"
                f"<td><pre>{escape(question)}</pre></td>"
                f"<td><pre>{escape(response.output)}</pre></td>"
                "</tr>"
            )
    if not rows:
        return ""
    table = _table(
        ("answers.column.case", "answers.column.input", "answers.column.output"),
        rows,
        locale,
    )
    title = escape(phrase(locale, "answers.title"))
    return (
        f"<details><summary>{title} ({len(rows)})</summary>"
        f'<p class="empty">{escape(phrase(locale, "answers.note"))}</p>'
        f"{table}</details>"
    )


def render_run_html(run: Run, *, locale: Locale) -> str:
    """One run, rendered on its own, because there is no reference yet.

    The same document as `render_html` wherever a section is a statement about
    the run — the header, the aggregates, the files under test, what answered
    and what judged — and a different one wherever a section was a statement
    about two runs. The verdict block says there is no reference instead of
    answering a question it cannot ask, and the cases are grouped by what each
    verdict *is* rather than by what it did.

    It exists because the refusal it replaces was circular: `digline report`
    told a first-time reader to look at the result and then promote, and was
    itself the only way to look. A command that names looking as the
    prerequisite for looking is a command that has to be fixed, not documented.

    Not a verdict, and the exit code says so: `digline report` on a run with no
    baseline never exits 1, because "worse" is a relation and there is nothing
    to be worse than.

    `locale` is mandatory here for the reason it is there: the language of a
    document with a recipient is not something to settle by omission.
    """
    strings(locale)  # fail here, not halfway through a document
    title = phrase(locale, "document.title", suite=run.suite)
    reasons = not run.redacted
    sections = "".join(
        _run_section(key, open_by_default, status, run, locale, reasons=reasons)
        for key, open_by_default, status in RUN_SECTIONS
    )
    aggregates = _aggregates(
        run, locale, reasons=reasons, worse=False, comparative=False
    )

    return (
        "<!DOCTYPE html>\n"
        f'<html lang="{escape(locale)}">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{escape(title)}</title>\n"
        f"<style>\n{CSS}</style>\n"
        "</head>\n"
        "<body>\n"
        f"<h1>{escape(title)}</h1>\n"
        f'<dl class="meta">{_run_meta(run, locale)}</dl>\n'
        f"{_run_answer(run, locale)}\n"
        f"{aggregates}\n"
        f"{_run_artifacts(run, locale)}\n"
        f"{_run_configs(run, locale)}\n"
        f"{sections}\n"
        f"{_recorded_answers(run, locale)}\n"
        "</body>\n"
        "</html>\n"
    )
