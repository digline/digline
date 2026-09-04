"""The two-run report, rendered for a reader deciding whether to switch.

Pure functions, like the rest of `digline.report`: nothing here opens a file,
reads the clock or touches the network.

**The computation reuses; the copy does not.** `diff()` reuses `compare()`'s
pairing, its `ConfigDelta` machinery and its artifact digests, because those
answer questions that do not depend on which side was approved. Everything in
this module is new, because everything on the copy side of that line carries the
perspective ADR 0008 §2 forbids: `config_changes()` renders `{before} → {after}`,
the config table's columns are *This run* and *Reference*, the sections are
headed *What got worse*. A diff has no reference, so it has no "before".

What is reused from `render` is *layout*: `fmt_score`, `fmt_value`, `ABSENT`,
and the artifact text-diff helpers, none of which contain a direction of travel.
"""

from __future__ import annotations

from collections.abc import Sequence

from digline.core import (
    ArtifactDelta,
    CheckDifference,
    ConfigDelta,
    Difference,
    Noise,
)
from digline.report.render import (
    SUMMARY_SEPARATOR,
    diff_lines,
    diff_tally,
    fmt_score,
    fmt_value,
)
from digline.report.text import Locale, phrase, strings

__all__ = [
    "artifact_lines",
    "detail",
    "header_lines",
    "run_labels",
    "sentence",
    "summary_lines",
    "system_lines",
    "when",
]


def when(created_at: str, *, seconds: bool = False) -> str:
    """`2026-09-04T09:12:33+00:00` becomes `2026-09-04 09:12`, or `…09:12:33`.

    Sliced rather than parsed, for `human_time`'s reason: `digline.report` may
    not import `datetime`, and a function that formats a *recorded* string must
    never be able to ask what time it is now.

    **Not localized, unlike `human_time`.** That one feeds a screen, where `4
    set 09:12` is what a person reads at a glance; this one feeds a report, and
    `text.py`'s rule is that a report keeps ISO dates so two renderings of it
    diff line by line. The month is a number here and stays one.

    Anything not shaped like the timestamps we write comes back untouched.
    """
    date, sep, rest = created_at.partition("T")
    if not sep or len(date) != 10 or len(rest) < 5:
        return created_at
    if seconds and len(rest) >= 8:
        return f"{date} {rest[:8]}"
    return f"{date} {rest[:5]}"


def run_labels(
    left_created: str,
    right_created: str,
    *,
    left_key: str,
    right_key: str,
) -> tuple[str, str]:
    """A short label per run, at the coarsest resolution that separates them.

    The report speaks of the runs by name (ADR 0008 §2), and a run key is
    forty-eight characters of which the last sixteen are the `config_hash` —
    **identical on both sides by §3**, so the half that would distinguish them
    is the half that cannot. The recorded instant is what actually differs, and
    `2026-09-04 09:12` fits on a line beside a case id.

    It escalates twice and then gives up honestly: minutes, seconds, the full
    keys. **Seconds are not an optional middle step**, they are the one that
    matters: two candidates launched back to back land in the same minute, and
    a sweep fired back to back is exactly the shape this command exists for. The
    first version of this function went straight from minutes to keys on the
    reasoning that the key is what separates them — true, and it made every line
    of the ordinary report carry two forty-eight-character keys. Found by
    running it, not by thinking about it.

    Both labels move together when either collides. Mixed precision down two
    columns reads as data — as though one run were more precisely known — when
    it is only formatting.
    """
    left, right = when(left_created), when(right_created)
    if left != right:
        return left, right
    left, right = when(left_created, seconds=True), when(right_created, seconds=True)
    if left != right:
        return left, right
    # Two runs inside one second. The label would repeat, and a label that does
    # not distinguish is worse than a long one that does.
    return left_key, right_key


def _plural(locale: Locale, stem: str, count: int, **params: object) -> str:
    """`stem.one` at one, `stem.many` otherwise. The house's counting shape,
    factored because this module counts six different things."""
    key = f"{stem}.one" if count == 1 else f"{stem}.many"
    return phrase(locale, key, count=count, **params)


def sentence(difference: Difference, *, locale: Locale, labels: tuple[str, str]) -> str:
    """The counts, and — where it has a population — the one honest comparison.

    Symmetric and exhaustive: every check is in exactly one clause, the two
    "favours" figures name their runs, and no word suggests a direction of
    travel. There is no `worse` here and no value carrying one, which is ADR
    0008 §1 in the only place a reader would look for it.
    """
    strings(locale)  # fail here, not halfway through a document
    left, right = labels
    total, differing = difference.total, difference.differing

    if differing == 0:
        head = phrase(locale, "diff.count.none", total=total)
    else:
        parts: list[str] = []
        if difference.favours_left:
            parts.append(
                _plural(
                    locale, "diff.breakdown.favours", difference.favours_left, run=left
                )
            )
        if difference.favours_right:
            parts.append(
                _plural(
                    locale,
                    "diff.breakdown.favours",
                    difference.favours_right,
                    run=right,
                )
            )
        one_side = difference.only_left + difference.only_right
        if one_side:
            parts.append(_plural(locale, "diff.breakdown.one_side", one_side))
        if difference.errored:
            parts.append(_plural(locale, "diff.breakdown.errored", difference.errored))
        # Last, and silent at zero like every other clause in this product. "58
        # within tolerance" is what tells a reader the other 58 were looked at;
        # "0 within tolerance" beside "2 of 2 checks differ" tells them nothing
        # and reads as a slot the renderer had to fill.
        if difference.within_tolerance:
            parts.append(
                _plural(locale, "diff.breakdown.tolerance", difference.within_tolerance)
            )
        key = "diff.count.one" if differing == 1 else "diff.count.many"
        head = phrase(
            locale, key, total=total, differing=differing, breakdown=", ".join(parts)
        )

    # Silent where nothing measured an interval on both sides — a suite at
    # `samples=1`, which is most suites. "0 of … exceed both intervals" would
    # report an absent measurement as a null result. (ADR 0008 §4)
    exceeds: list[str] = []
    if difference.interval_pairs:
        for count, label in (
            (difference.left_exceeds, left),
            (difference.right_exceeds, right),
        ):
            if count:
                exceeds.append(_plural(locale, "diff.exceeds", count, run=label))
    return " ".join((head, *exceeds))


def header_lines(
    difference: Difference, *, locale: Locale, labels: tuple[str, str]
) -> Sequence[str]:
    """What differs about the two systems, before what it did to the scores.

    ADR 0003 §5 and ADR 0005 §5 both put what changed above what it did; here
    the ordering is more load-bearing still, because *what differs about the
    systems* is the whole reason the reader opened the report.
    """
    lines = list(system_lines(difference, locale=locale, labels=labels))
    lines.extend(artifact_lines(difference, locale=locale, labels=labels))
    if difference.judges:
        # Identical on both sides by §3, so it is context and not a delta. It
        # earns its line because "which instrument said so" is the first thing
        # a sceptical reader asks of two scores that disagree.
        lines.append(
            phrase(locale, "diff.judge.same", judges=", ".join(difference.judges))
        )
    return tuple(lines)


def _pair(delta: ConfigDelta, locale: Locale) -> str:
    """`temperature 0.3 vs 0.7`, in argument order, always.

    One key for `changed`, `new` and `missing` alike, with `ABSENT` standing in
    for the side that has no value. `config.change.new`'s *"not sent for the
    reference"* cannot be said here — there is no reference — and inventing
    *"not sent for the left run"* would name a column rather than a run. The
    em-dash says the same thing without taking a side.
    """
    return phrase(
        locale,
        "diff.change.pair",
        field=delta.field,
        left=fmt_value(delta.before),
        right=fmt_value(delta.after),
    )


def system_lines(
    difference: Difference, *, locale: Locale, labels: tuple[str, str]
) -> Sequence[str]:
    """One line naming what differs between the two systems, or what does not.

    Nothing at all where neither side recorded a configuration — a
    plain-function target, or two runs predating ADR 0005. A sentence
    reassuring about a configuration nobody recorded is one the reader learns to
    skip, and the clause that matters gets skipped with it.
    """
    deltas = difference.target_config_deltas
    if not deltas:
        return ()
    changed = [d for d in deltas if d.outcome in ("changed", "new", "missing")]
    if changed:
        return (
            phrase(
                locale,
                "diff.systems.differ",
                changes=", ".join(_pair(d, locale) for d in changed),
            ),
        )
    if all(d.outcome == "unknown" for d in deltas):
        return (phrase(locale, "diff.systems.unknown"),)
    return (phrase(locale, "diff.systems.same"),)


def _artifact_detail(
    delta: ArtifactDelta, locale: Locale, labels: tuple[str, str]
) -> str:
    if delta.outcome == "unknown":
        return phrase(locale, "diff.artifacts.outcome.unknown")
    if delta.outcome in ("new", "missing"):
        # `new` is present on the `after` side, which is the right-hand run.
        run = labels[1] if delta.outcome == "new" else labels[0]
        return phrase(locale, "diff.artifacts.outcome.only", run=run)
    tally = diff_tally(diff_lines(delta))
    if any(tally):
        return phrase(locale, "artifacts.tally", added=tally[0], removed=tally[1])
    return phrase(locale, "diff.artifacts.outcome.differs")


def artifact_lines(
    difference: Difference, *, locale: Locale, labels: tuple[str, str]
) -> Sequence[str]:
    """One compact line per differing file. The tally, not the diff.

    Nothing at all when an artifact was withheld: a path is payload, and the
    count is in the note above.
    """
    deltas = difference.artifact_deltas
    if not deltas:
        return ()
    if any(d.withheld for d in deltas):
        return (phrase(locale, "diff.artifacts.unknown"),)
    differing = [d for d in deltas if d.outcome not in ("same", "unknown")]
    if not differing:
        return (phrase(locale, "diff.artifacts.same"),)
    note = _plural(locale, "diff.artifacts", len(differing))
    return (
        note,
        *(f"{d.path} · {_artifact_detail(d, locale, labels)}" for d in differing),
    )


def _interval(noise: Noise, locale: Locale) -> str:
    assert noise.low is not None and noise.high is not None
    return phrase(
        locale,
        "noise.interval",
        low=fmt_score(noise.low),
        high=fmt_score(noise.high),
        count=noise.count,
    )


def detail(check: CheckDifference, *, locale: Locale, labels: tuple[str, str]) -> str:
    """What the two runs said about one check, composed from structured facts.

    Neither run's number is introduced before the other's: they are printed in
    column order with their runs named, and the clauses that follow say what
    that ordering does *not* say — who passes, whether the tolerance covered it,
    what the two intervals do.
    """
    left, right = labels
    if check.outcome == "only_left":
        return phrase(locale, "diff.detail.only", run=left)
    if check.outcome == "only_right":
        return phrase(locale, "diff.detail.only", run=right)
    if check.outcome == "errored":
        assert check.left is not None and check.right is not None
        bad = [
            label
            for label, verdict in ((left, check.left), (right, check.right))
            if verdict.status == "error"
        ]
        if len(bad) == 2:
            return phrase(locale, "diff.detail.errored.both")
        return phrase(locale, "diff.detail.errored", run=bad[0])

    assert check.left is not None and check.right is not None
    assert check.left.score.score is not None
    assert check.right.score.score is not None
    text = phrase(
        locale,
        "diff.detail.scores",
        left_run=left,
        left_score=fmt_score(check.left.score.score),
        right_run=right,
        right_score=fmt_score(check.right.score.score),
    )

    if check.flipped:
        passing, failing = (
            (right, left) if check.right.status == "pass" else (left, right)
        )
        # No interval rides along, for ADR 0006 §6's reason unchanged: the
        # intervals did not decide this, and printing them would invite a reader
        # to check the scores against them and find both inside.
        return text + phrase(
            locale, "diff.detail.flipped", pass_run=passing, fail_run=failing
        )

    if check.outcome == "same":
        text += phrase(
            locale, "diff.detail.tolerance", tolerance=fmt_score(check.tolerance)
        )

    if check.intervals_overlap or check.intervals_disjoint:
        key = (
            "diff.detail.overlap" if check.intervals_overlap else "diff.detail.disjoint"
        )
        text += phrase(
            locale,
            key,
            left_noise=_interval(check.left_interval, locale),
            right_noise=_interval(check.right_interval, locale),
        )
    return text


#: Which outcomes a terminal summary lists, in reading order. Everything that
#: differs, and nothing that does not: the agreeing checks are the count in the
#: sentence, and printing sixty of them would bury the seven the reader came for.
SUMMARY_OUTCOMES = ("differs", "only_left", "only_right", "errored")


def summary_lines(
    difference: Difference,
    *,
    locale: Locale,
    labels: tuple[str, str],
    limit: int | None = None,
) -> Sequence[str]:
    """One line per differing check: what to look at, in order.

    The third field comes from the **same** `detail()` a document would use, so
    a terminal and a rendered page can never describe one difference in two
    ways — the reason `Headline.sentence` exists on the other path.

    `limit` truncates, and when it does the last line says so. A silent "first
    twenty" reads exactly like "all twenty".
    """
    strings(locale)  # fail here rather than halfway down a list
    order = {outcome: n for n, outcome in enumerate(SUMMARY_OUTCOMES)}
    chosen = sorted(
        (c for c in difference.checks if c.differs),
        key=lambda c: (order[c.outcome], c.scope != "case", c.case_id, c.assertion),
    )
    shown = chosen if limit is None else chosen[:limit]
    lines = [
        SUMMARY_SEPARATOR.join(
            (
                # A run-level verdict belongs to no case, so it says so rather
                # than opening the line with an empty field.
                c.case_id if c.scope == "case" else phrase(locale, "scope.run"),
                c.assertion,
                detail(c, locale=locale, labels=labels),
            )
        )
        for c in shown
    ]
    if len(shown) < len(chosen):
        lines.append(
            phrase(locale, "summary.truncated", shown=len(shown), total=len(chosen))
        )
    return tuple(lines)
