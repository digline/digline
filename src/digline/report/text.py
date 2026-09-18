"""Every visible string of the report, in one place, per locale.

This is the declared exception to the English-everywhere rule. The rule is about
code and runtime strings; the report is a *document with a recipient*, and the
recipient — an end company that does not read code — did not choose English.

Two things are deliberately **not** localized, and the reason is the same for
both: a report is a committed artifact, and two reports of the same run in two
languages must remain comparable line by line.

- **Dates** stay ISO 8601, exactly as they were recorded.
- **Numbers** keep the dot as decimal separator, and a measured interval is
  rendered at `FLOAT_PRECISION` like every other score (ADR 0006 §10).

Localizing either would produce documents that say the same thing and cannot be
diffed against each other.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal

__all__ = ["LOCALES", "MONTHS", "TEXT", "Locale", "phrase", "strings"]

type Locale = Literal["en", "it"]

LOCALES: tuple[Locale, ...] = ("en", "it")

#: Abbreviated month names, per locale, for the *view* only.
#:
#: The report keeps ISO dates and always will: it is a committed artifact and two
#: renderings of one run must diff line by line. A screen is not that. `26 ago
#: 08:51` is what a developer reads at a glance, and the full key underneath —
#: which begins with the ISO instant — is still the fact.
#:
#: A table rather than the `locale` module: `locale.setlocale` is process-global,
#: depends on what the operating system has installed, and would make one
#: function's output depend on state nothing here set.
MONTHS: Mapping[Locale, tuple[str, ...]] = {
    "en": (
        "Jan", "Feb", "Mar", "Apr", "May", "Jun",
        "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
    ),
    "it": (
        "gen", "feb", "mar", "apr", "mag", "giu",
        "lug", "ago", "set", "ott", "nov", "dic",
    ),
}  # fmt: skip

TEXT: Mapping[Locale, Mapping[str, str]] = {
    "en": {
        "document.title": "Evaluation report — {suite}",
        "header.tenant": "Customer",
        "header.suite": "Suite",
        "header.environment": "This run",
        "header.baseline_environment": "Reference",
        "header.commit": "Code version",
        "header.dirty": (
            " — uncommitted changes were present, so this run cannot be "
            "reproduced from the repository"
        ),
        "header.redacted": "Contents omitted",
        "header.redacted.value": "This report was produced from redacted data.",
        # Named in the header rather than only in the sentence: a reader who
        # scrolls past the first screen must still be able to see that the
        # answers came from a stored run, and which one.
        "header.promoted": "Reference approved",
        "header.rejudged": "Answers replayed from",
        # The evidence block: shown only where the document carries it, which
        # is never at a boundary (ADR 0015 §4).
        "answers.title": "What the system answered",
        "answers.note": (
            "Recorded because this suite asked for it. It stays in this "
            "repository: a document produced for anyone outside it carries the "
            "verdicts and not the answers."
        ),
        "answers.column.case": "Case",
        "answers.column.input": "Question",
        "answers.column.output": "Answer",
        # The third state of the answer block: a run with no approved
        # reference. Not a verdict and not an empty box — the fact, stated.
        "noreference.title": "No reference to compare against",
        "noreference.sentence": (
            "This is the run as measured. Whether it got worse is a question "
            "that needs an approved reference; nothing in this document "
            "answers it."
        ),
        "runtally.cases": "cases",
        "runtally.checks": "checks",
        # The unit is in the label. The sections below count verdicts —
        # one errored case can carry three — and the headline slot counts
        # cases, the way every sentence in this document does. Two true
        # numbers that differ need to say what they are counting.
        "runtally.unjudged": "cases not judged",
        "runtally.suspended": "cases set aside",
        "answer.question": "Did it get worse?",
        "answer.yes": "Yes",
        "answer.no": "No",
        "fact.worse.none": "Nothing got worse compared with the reference.",
        "fact.worse.one": "1 check got worse compared with the reference.",
        "fact.worse.many": "{count} checks got worse compared with the reference.",
        "fact.noise.one": "1 check moved within noise.",
        "fact.noise.many": "{count} checks moved within noise.",
        "fact.unjudged.none": "Every case could be judged.",
        "fact.unjudged.one": "1 case could not be judged.",
        "fact.unjudged.many": "{count} cases could not be judged.",
        "fact.suspended.none": "No case is suspended.",
        "fact.suspended.one": "1 case is suspended.",
        "fact.suspended.many": "{count} cases are suspended.",
        "fact.config.changed": (
            "The suite changed since the reference, so these numbers compare "
            "different rules."
        ),
        "fact.config.unchanged": "The suite is unchanged from the reference.",
        "fact.artifacts.unchanged": (
            "The files under test are the same as the reference."
        ),
        "fact.artifacts.one": "1 file under test changed since the reference.",
        "fact.artifacts.unknown": (
            "The files under test are not included, so whether they changed "
            "is not known."
        ),
        "fact.artifacts.many": (
            "{count} files under test changed since the reference."
        ),
        "fact.rejudged": (
            "The answers in this run were replayed from a stored run, not "
            "measured: the target was not asked anything."
        ),
        "fact.on_the_line.one": (
            "1 check is on the line: the band it measured covers its threshold."
        ),
        "fact.on_the_line.many": (
            "{count} checks are on the line: the bands they measured cover "
            "their thresholds."
        ),
        # *Likely*, and the word is chosen: the canary observes behaviour and
        # cannot read a model id, so a suite whose canary moved because the
        # shared prompt was edited has told the truth about a change with the
        # wrong cause. The report states the observation and stops short of the
        # diagnosis. (ADR 0016 §7)
        "fact.canary.one": (
            "The model under this alias likely changed: the canary {case} "
            "moved from {before} to {after}{beyond}."
        ),
        "fact.canary.many": (
            "The model under this alias likely changed: {count} canary checks "
            "moved, including {case} from {before} to {after}{beyond}."
        ),
        "fact.canary.beyond": ", beyond the noise of this check ({interval})",
        # No *likely*, and the absence is chosen: that word is the canary's,
        # which infers a model from behaviour. Here nothing is inferred — the
        # band was declared and the score was observed. (ADR 0024 §4.6)
        "fact.calibration.one": (
            "The calibration case {case} scored {score}{across}, outside its "
            "declared band {low}–{high}: the judged scores in this run are not "
            "placed on the scale they are compared on."
        ),
        "fact.calibration.many": (
            "{count} calibration cases scored outside their declared bands, "
            "including {case} at {score}{across} against {low}–{high}: the "
            "judged scores in this run are not placed on the scale they are "
            "compared on."
        ),
        "fact.calibration.across": " across {count} samples ({values})",
        "fact.target_config.changed": (
            "The system under test answered under a different configuration: {changes}."
        ),
        "fact.target_config.unchanged": (
            "The system under test answered under the same configuration as "
            "the reference."
        ),
        "fact.target_config.unknown": (
            "The configuration of the system under test is not recorded on "
            "both sides, so whether it changed is not known."
        ),
        # Never "the same configuration" over an identity that was withheld: a
        # withheld answering model is not an unchanged one, and saying so would
        # be the report asserting what it does not know.
        "fact.target_config.withheld_identity": (
            "The system under test answered under the same declared "
            "configuration; what answered is withheld, so whether the model "
            "changed is not known."
        ),
        # An absence disguised as a presence, stated as a fact: the endpoint
        # returned the id it was sent. Not a diagnosis. (ADR 0020 §3, row 7)
        "fact.target_config.echoed": (
            "The endpoint returned the requested id, {model}, as the model that "
            "answered, so which model answered is not identified; only a canary "
            "sees whether its behaviour changed."
        ),
        "explain.tally.echoed": (
            "The endpoint returned the requested id as the model that answered, "
            "so which model answered is not identified."
        ),
        # Shape (ADR 0024 §6): the shares side by side, and nothing that says
        # which is more. That sentence waits for a threshold sized on data.
        "explain.tally.shape": (
            "{check}: {share} of {scores} judged scores at 0 or 1, against "
            "{reference_share} of {reference_scores} in the reference."
        ),
        "explain.tally.shape.noreference": (
            "{check}: {share} of {scores} judged scores at 0 or 1; the reference "
            "records no judged score of it to set beside that."
        ),
        "explain.tally.shape.none": (
            "{check}: no judged score of it could be read in this run."
        ),
        # A fold of folds (ADR 0024 §6.5): left out, counted, and said to be an
        # absence rather than a score.
        "explain.tally.shape.sample_means.one": (
            " 1 verdict is left out: its per-judgement scores were not recorded, "
            "only their means."
        ),
        "explain.tally.shape.sample_means.many": (
            " {count} verdicts are left out: their per-judgement scores were not "
            "recorded, only their means."
        ),
        "explain.tally.shape.reference_sample_means.one": (
            " In the reference, 1 verdict is left out: its per-judgement scores "
            "were not recorded, or cannot be told from means."
        ),
        "explain.tally.shape.reference_sample_means.many": (
            " In the reference, {count} verdicts are left out: their per-judgement "
            "scores were not recorded, or cannot be told from means."
        ),
        "explain.tally.shape.single_claim.one": (
            " 1 verdict with a single claim is left out: it can only score 0 or 1."
        ),
        "explain.tally.shape.single_claim.many": (
            " {count} verdicts with a single claim are left out: they can only "
            "score 0 or 1."
        ),
        "explain.tally.shape.claims_unrecorded.one": (
            " 1 sampled verdict is read whose claim count per sample was not recorded."
        ),
        "explain.tally.shape.claims_unrecorded.many": (
            " {count} sampled verdicts are read whose claim counts per sample were "
            "not recorded."
        ),
        "fact.judge_config.changed": (
            "The judging changed ({changes}), so these scores are less "
            "comparable with the reference: what moved is the measuring "
            "instrument, not only what it measured."
        ),
        "config.title": "What answered",
        "config.judge.title": "What judged",
        "config.column.parameter": "Parameter",
        "config.column.value": "This run",
        "config.column.reference": "Reference",
        "config.value.withheld": "not included",
        "config.unchanged": "Configured as in the reference.",
        "config.changed.one": "1 parameter changed since the reference.",
        "config.changed.many": "{count} parameters changed since the reference.",
        "config.unknown": (
            "The reference does not record its configuration, so whether it "
            "changed is not known."
        ),
        "config.judge.reduced": (
            "The judge is not the one that produced the reference, so these "
            "scores are less comparable than their difference suggests."
        ),
        "config.change.changed": "{field} {before} → {after}",
        "config.change.new": "{field} {after}, not sent for the reference",
        "config.change.missing": "{field} {before}, no longer sent",
        # An observed field was never *sent* — not by this run and not by the
        # reference — so the two sentences above would state something false
        # about it. Which fields these are is `OBSERVED_FIELDS`. (ADR 0005 §9)
        "config.change.new.observed": (
            "{field} {after}, not reported for the reference"
        ),
        "config.change.missing.observed": "{field} {before}, no longer reported",
        "config.judge.added": "{judge} was added as a judge",
        "config.judge.removed": "{judge} no longer judges",
        "config.coincides": " This drop coincides with {changes}.",
        "config.terminal.target": "system",
        "config.terminal.judge": "judge",
        "artifacts.title": "What was under test",
        "artifacts.unchanged": "The files under test are the same as the reference.",
        "artifacts.changed.one": "1 file under test changed.",
        "artifacts.changed.many": "{count} files under test changed.",
        "artifacts.outcome.changed": "changed",
        "artifacts.outcome.new": "added since the reference",
        "artifacts.outcome.missing": "no longer declared",
        "artifacts.outcome.unknown": "not included, so whether it changed is not known",
        "artifacts.withheld": "The contents are not included in this report.",
        "artifacts.tally": "+{added} −{removed} lines",
        "artifacts.column.file": "File",
        "artifacts.column.fingerprint": "Fingerprint",
        "artifacts.column.what": "What happened",
        "aggregates.title": "Overall",
        "aggregates.failing_not_worse": (
            "Some measures are below their threshold and are still not reported "
            "as having got worse: they were below it in the reference too. The "
            "threshold says the system does not meet the bar; the comparison "
            "says it has not moved. Both are true, and only movement decides "
            "the answer above."
        ),
        "aggregate.counted": (
            "{considered} counted · {suspended} suspended · {errored} not judged"
        ),
        "column.measure": "Measure",
        "column.result": "Result",
        "scope.run": "whole run",
        # The single-run document groups by what a verdict *is*, where the
        # comparison groups by what it did. `unjudged` and `suspended` are
        # shared: they mean the same thing with or without a reference.
        "section.failed": "What did not meet its threshold",
        "section.passed": "What met its threshold",
        "section.regressions": "What got worse",
        "section.unjudged": "What could not be judged",
        "section.suspended": "What is set aside",
        "section.changes": "What was added or removed",
        "section.improvements": "What got better",
        "section.unchanged": "What stayed the same",
        "section.calibration": "Where the judge placed the calibration answers",
        "section.empty": "Nothing in this section.",
        "summary.truncated": (
            "showing the first {shown} of {total}; the full list is in the report"
        ),
        "column.case": "Case",
        "column.check": "Check",
        "column.band": "Declared band",
        "calibration.inside": "inside",
        "calibration.outside": "outside",
        "column.detail": "What happened",
        "column.reason": "Why",
        "detail.dropped": "Score fell from {before} to {now}.",
        "detail.rose": "Score rose from {before} to {now}.",
        "detail.unchanged": "Score unchanged at {now}.",
        "noise.interval": "{low}–{high} across {count} samples",
        "detail.within_noise": (
            "Score moved from {before} to {now} — within the noise of this "
            "check ({noise}); not counted as a regression."
        ),
        "detail.dropped.beyond_noise": (
            "Score fell from {before} to {now} — beyond the noise of this "
            "check ({noise})."
        ),
        "detail.rose.beyond_noise": (
            "Score rose from {before} to {now} — beyond the noise of this "
            "check ({noise})."
        ),
        "detail.flipped.worse": "Went from passing to failing ({before} → {now}).",
        "detail.flipped.better": "Went from failing to passing ({before} → {now}).",
        "detail.threshold_moved": (
            " The bar moved from {before_threshold} to {now_threshold}, so this is "
            "a change of rule rather than of behaviour."
        ),
        "detail.new": "Checked here, not present in the reference.",
        "detail.new.errored": ("New here, and the check could not run."),
        "detail.missing": "Present in the reference, not checked here.",
        "detail.errored": "The check could not run.",
        "detail.three_way": (
            " The samples went three ways: {passed} passed, {failed} failed, "
            "{errored} could not be judged."
        ),
        "detail.exceedances": (
            " {over} of {judged} calls went over the {cap} cap on their own, "
            "the largest at {worst}."
        ),
        "detail.exceedances.pinned": (
            " {over} of {judged} calls went over the {cap} cap on their own; "
            "the largest sits at the cap."
        ),
        "reason.unavailable": "Not included in this report.",
        "diff.title": "Two runs compared — {suite}",
        "diff.column.run": "Run",
        "diff.column.check": "Check",
        "diff.column.case": "Case",
        "diff.column.what": "What the two runs said",
        "diff.systems.same": (
            "The two runs answered under the same recorded configuration."
        ),
        "diff.systems.differ": "The systems differ: {changes}.",
        "diff.systems.unknown": (
            "The configuration is not recorded on both sides, so whether the "
            "systems differ is not known."
        ),
        "diff.judge.same": "Both runs were graded by {judges}.",
        "diff.change.pair": "{field} {left} vs {right}",
        "diff.artifacts.same": "The files under test are the same in both runs.",
        "diff.artifacts.one": "1 file under test differs between the two runs.",
        "diff.artifacts.many": (
            "{count} files under test differ between the two runs."
        ),
        "diff.artifacts.unknown": (
            "The files under test are not included, so whether they differ is "
            "not known."
        ),
        "diff.artifacts.outcome.differs": "differs",
        "diff.artifacts.outcome.only": "declared in {run} only",
        "diff.artifacts.outcome.unknown": (
            "not included, so whether it differs is not known"
        ),
        "diff.count.none": "No check differs, out of {total}.",
        "diff.count.one": "1 of {total} checks differs: {breakdown}.",
        "diff.count.many": "{differing} of {total} checks differ: {breakdown}.",
        "diff.breakdown.favours.one": "1 favours {run}",
        "diff.breakdown.favours.many": "{count} favour {run}",
        "diff.breakdown.tolerance.one": "1 within tolerance",
        "diff.breakdown.tolerance.many": "{count} within tolerance",
        "diff.breakdown.one_side.one": "1 present in only one run",
        "diff.breakdown.one_side.many": "{count} present in only one run",
        "diff.breakdown.errored.one": "1 could not be judged",
        "diff.breakdown.errored.many": "{count} could not be judged",
        "diff.overlap.one": (
            "1 difference sits inside both runs' observed intervals, so no "
            "claim can be made about it."
        ),
        "diff.overlap.many": (
            "{count} differences sit inside both runs' observed intervals, so "
            "no claim can be made about them."
        ),
        "diff.exceeds.one": (
            "1 of {run}'s advantages exceeds both runs' observed intervals."
        ),
        "diff.exceeds.many": (
            "{count} of {run}'s advantages exceed both runs' observed intervals."
        ),
        "diff.detail.scores": "{left_run} {left_score}, {right_run} {right_score}.",
        "diff.detail.flipped": " {pass_run} passes this check and {fail_run} does not.",
        "diff.detail.tolerance": " Within the declared tolerance {tolerance}.",
        "diff.detail.overlap": (
            " Observed intervals {left_noise} and {right_noise} overlap, so "
            "these two are not distinguishable by this check."
        ),
        "diff.detail.disjoint": (
            " Observed intervals {left_noise} and {right_noise} do not overlap."
        ),
        "diff.detail.only": "Checked in {run} only.",
        "diff.detail.errored": "The check could not run in {run}.",
        "diff.detail.errored.both": "The check could not run in either run.",
        "diff.section.differ": "What the two runs answered differently",
        "diff.section.same": "What the two runs agree on",
        "view.title.runs": "Runs — {suite}",
        "view.title.case": "Case {case_id} — {suite}",
        "view.title.suspend": "Suspend {case_id} — {suite}",
        "view.nav.runs": "Runs",
        "view.nav.report": "Report",
        "view.baseline": "baseline",
        "view.column.key": "Run",
        "view.column.aggregate_note": "change against the baseline",
        "view.commit.dirty": "uncommitted changes",
        "view.commit.none": "no git repository",
        "view.promote.errored": (
            "{count} case(s) could not be judged, so this run cannot become a "
            "baseline: an error is not a reference."
        ),
        "view.promote.older": (
            "This run was produced under an earlier version of the suite, so it "
            "cannot become a baseline: its scores were obtained under rules "
            "other than the ones in force. It can still be compared."
        ),
        "view.chip.errored": "{count} not judged",
        "view.chip.older_config": "older suite",
        "view.action.compare": "Compare",
        "view.action.compare.title": "compare this run with the baseline",
        "view.copy_snippet": "click the line to select it",
        "view.column.created": "Recorded",
        "view.column.env": "Environment",
        "view.column.commit": "Code version",
        "view.column.cases": "Cases",
        "view.column.actions": "Actions",
        "view.artifacts.stamp": "prompt {sha}",
        "view.artifacts.title": "digest of the {count} file(s) under test in this run",
        "view.column.run": "Run",
        "view.column.votes": "Votes",
        "view.no_runs": "No run has been recorded yet.",
        "view.no_aggregates": "This suite declares no aggregate.",
        "view.ignored": "Not shown: {note}. Run `digline migrate`.",
        "view.compare.pick": "Compare",
        "view.compare.against": "against",
        "view.compare.go": "Show",
        "view.compare.same": "A run compared with itself has nothing to report.",
        "view.case.absent": "not in this run",
        "view.case.suspended": "set aside",
        "view.case.title": "How {case_id} was judged, oldest first",
        "view.case.votes_note": (
            "For a sampled check the raw votes are shown beneath the combined "
            "score: that is where judge noise is visible."
        ),
        "view.promote.button": "Make baseline",
        "view.promote.done": "Baseline set to {run_key}.",
        "view.promote.refused": "Refused: {why}",
        "view.suspend.title": "Set {case_id} aside",
        "view.suspend.reason": "Why is it set aside?",
        "view.suspend.show": "Show the edit",
        "view.suspend.explain": (
            "A suspension lives in the suite, which is code. This page writes "
            "nothing: it produces the line to add, and you commit it — so the "
            "reason travels with the case in the same review as everything else."
        ),
        "view.suspend.needs_reason": (
            "A suspension without a stated reason is a case that disappears "
            "quietly. Write why."
        ),
        # --- the reading (`digline explain`, ADR 0012) ----------------------
        #
        # Every string here is a statement, never an instruction. No modal verb
        # aimed at the reader, and no word about a second run: a reading is of
        # one run and its reference, so "again", "repeats" and "drift" are
        # measurements nobody took here. Both are gates, not conventions.
        "explain.heading.tally": "What ran",
        "explain.heading.settings.compared": "What differed underneath",
        "explain.heading.settings.alone": "How it was set up",
        "explain.heading.checks.compared": "What moved",
        "explain.heading.checks.alone": "What it found",
        "explain.tally.cases.none": "No case ran.",
        "explain.tally.cases.one": "1 case ran.",
        "explain.tally.cases.many": "{count} cases ran.",
        "explain.tally.checks.none": "No check ran.",
        "explain.tally.checks.one": "1 check ran.",
        "explain.tally.checks.many": "{count} checks ran.",
        "explain.tally.unjudged.none": "Every case could be judged.",
        "explain.tally.unjudged.one": "1 case could not be judged.",
        "explain.tally.unjudged.many": "{count} cases could not be judged.",
        "explain.tally.suspended.none": "No case is suspended.",
        "explain.tally.suspended.one": "1 case is suspended.",
        "explain.tally.suspended.many": "{count} cases are suspended.",
        "explain.tally.within_noise.one": (
            "1 check moved, and the interval its reference measured covers "
            "the movement."
        ),
        "explain.tally.within_noise.many": (
            "{count} checks moved, and the intervals their reference measured "
            "cover the movement."
        ),
        "explain.tally.suite_config.changed": (
            "The suite changed since the reference, so these numbers compare "
            "different rules."
        ),
        "explain.tally.suite_config.unchanged": (
            "The suite is unchanged from the reference."
        ),
        "explain.tally.comparability": (
            "The judge changed: these scores are not comparable with the "
            "reference. The instrument that graded is not the one that graded "
            "the reference, so every difference below is measured on two "
            "scales."
        ),
        "explain.tally.rejudged": (
            "The answers judged here were replayed from a stored run: the "
            "target was not asked anything, so what these numbers measure is "
            "the judging."
        ),
        "explain.tally.canary": (
            "A canary check moved. It is counted in no aggregate, and what its "
            "movement is about is which model answered rather than how well it "
            "answered."
        ),
        # `digline rejudge --judge-samples` (ADR 0024 §5.4). A terminal line,
        # printed after `digline: ` like the planned-calls line, so it starts
        # lower-case and has no full stop. The range never goes without the
        # calibration: a collapsed judge is perfectly repeatable.
        "judged.range": (
            "the judge's own range on these answers is at most {range} across "
            "{count} judgements ({check}, answer {answer} of case {case})"
        ),
        "judged.range.none": (
            "the judge's own range on these answers was not measured: no judged "
            "answer returned two scores"
        ),
        "judged.errored.one": ", and 1 judgement returned no score",
        "judged.errored.many": ", and {count} judgements returned no score",
        "judged.calibration.inside": (
            "; the calibration case {case} scored {score}, inside its declared "
            "band {low}–{high}"
        ),
        "judged.calibration.outside": (
            "; the calibration case {case} scored {score}, outside its declared "
            "band {low}–{high}"
        ),
        "judged.calibration.unjudged": (
            "; the calibration case {case} could not be judged"
        ),
        "judged.calibration.none": (
            "; this suite declares no calibration case, and a judge that has "
            "lost its scale reads as perfectly repeatable"
        ),
        "explain.tally.calibration.one": (
            "1 calibration case scored outside its declared band: the judged "
            "scores in this run are not placed on the scale they are compared "
            "on. It is counted in no aggregate, and the target was not asked "
            "for it."
        ),
        "explain.tally.calibration.many": (
            "{count} calibration cases scored outside their declared bands: the "
            "judged scores in this run are not placed on the scale they are "
            "compared on. They are counted in no aggregate, and the target was "
            "not asked for them."
        ),
        "explain.tally.on_the_line.one": (
            "1 check measured a band that covers its own threshold, so which "
            "side it landed on is a property of the samples that were drawn."
        ),
        "explain.tally.on_the_line.many": (
            "{count} checks measured a band that covers their own threshold, so "
            "which side they landed on is a property of the samples that were "
            "drawn."
        ),
        "explain.tally.denominator_moved.one": (
            "1 run-level check was measured over a different number of cases "
            "than the reference it is set beside, so the two are not the same "
            "measurement and neither is a movement of the other."
        ),
        "explain.tally.denominator_moved.many": (
            "{count} run-level checks were measured over a different number of "
            "cases than the reference they are set beside, so the two are not "
            "the same measurement and neither is a movement of the other."
        ),
        "explain.check.on_the_line": (
            " The band this run measured covers the threshold, so which side it "
            "landed on is a property of the samples that were drawn."
        ),
        "explain.setting.target.changed": (
            "The system under test answered with {name} {after}; the reference "
            "answered with {before}."
        ),
        "explain.setting.target.new": (
            "The system under test recorded {name} {after}, which the "
            "reference did not record."
        ),
        "explain.setting.target.missing": (
            "The reference recorded {name} {before}; this run recorded none."
        ),
        "explain.setting.target.unknown": (
            "Whether {name} changed is not known: one side did not record it, "
            "or it was withheld."
        ),
        "explain.setting.judge.changed": (
            "The judge graded with {name} {after}; the reference was graded "
            "with {before}."
        ),
        "explain.setting.judge.new": (
            "The judge recorded {name} {after}, which the reference did not record."
        ),
        "explain.setting.judge.missing": (
            "The reference was graded with {name} {before}; this run recorded none."
        ),
        "explain.setting.judge.unknown": (
            "Whether the judge's {name} changed is not known: one side did not "
            "record it, or it was withheld."
        ),
        "explain.setting.judge.added": (
            "{after} graded this run and did not grade the reference."
        ),
        "explain.setting.judge.removed": (
            "{before} graded the reference and did not grade this run."
        ),
        "explain.setting.artifact.changed": "{name} changed: {tally}.",
        "explain.setting.artifact.changed.untallied": "{name} changed.",
        "explain.setting.artifact.new": (
            "{name} is under test in this run and was not in the reference."
        ),
        "explain.setting.artifact.missing": (
            "{name} was under test in the reference and is not in this run."
        ),
        "explain.setting.artifact.unknown": (
            "{name} is under test; its contents are not included, so whether "
            "it changed is not known."
        ),
        "explain.setting.target.alone": (
            "The system under test answered with {name} {after}."
        ),
        "explain.setting.judge.alone": "The judge graded with {name} {after}.",
        "explain.setting.target.alone.withheld": (
            "The system under test recorded {name}; the value is not included."
        ),
        "explain.setting.judge.alone.withheld": (
            "The judge recorded {name}; the value is not included."
        ),
        "explain.setting.artifact.alone": "{name} was under test.",
        "explain.setting.artifact.alone.withheld": (
            "{name} was under test; its contents are not included."
        ),
        "explain.check.regressed": (
            "{where} got worse: {before} to {now}, a drop of {delta}."
        ),
        "explain.check.improved": (
            "{where} got better: {before} to {now}, a rise of {delta}."
        ),
        "explain.check.unchanged": (
            "{where} moved from {before} to {now}, inside the tolerance the "
            "suite declares."
        ),
        "explain.check.within_noise": (
            "{where} moved from {before} to {now}, inside the interval its "
            "reference measured."
        ),
        "explain.check.new": (
            "{where} was checked here and is not in the reference, so there is "
            "nothing to hold it against."
        ),
        "explain.check.missing": (
            "{where} is in the reference and was not checked here."
        ),
        "explain.check.errored": "{where} could not be judged.",
        "explain.check.failing": "{where} is under its bar at {now}.",
        "explain.check.suspended": (
            "The case {case} was set aside, so nothing was measured on it. The "
            "stated reason is not carried here."
        ),
        "explain.where.run": "the whole run",
        "explain.bar": " The bar is {threshold}.",
        "explain.noise.beyond": (
            " That is outside the interval its reference measured, {noise}."
        ),
        "explain.nothing": "Nothing in this group.",
        # `digline log` (ADR 0020). The multi-run vocabulary is this reading's
        # whole subject, so it is allowed here; advice is not, and neither is
        # "likely", which belongs to the canary.
        "log.heading": "{suite} · {count} run(s) read in this store, {first} to {last}",
        "log.empty": "{suite} · no run read in this store, in this window.",
        "log.window": "Window: {since} to {until}.",
        "log.window.open": "…",
        "log.not_read.schema": "{count} run(s) at schema {version} were not read.",
        "log.not_read.unreadable": "{count} file(s) could not be read.",
        "log.side.target": "Target",
        "log.side.judge": "Judge",
        "log.span": "  {sighting} — {first} to {last}, {runs} run(s){environments}",
        "log.environments": " ({environments})",
        "log.sighting.answered": "{who}, answered as {answered}",
        "log.sighting.absent": "{who}: {absence}",
        "log.absence.declared_nothing": "declared no configuration",
        "log.absence.several_judges": "several judges; no single answering model",
        "log.absence.withheld": ("the answering model is withheld at a named endpoint"),
        "log.absence.not_reported": "no answering model was reported",
        "log.absence.not_recorded": (
            "not recorded: the document does not name its writer"
        ),
        # Row 7, stated as a fact and never as a diagnosis: an honest provider
        # may return the id it was sent. (ADR 0020 §3)
        "log.absence.echoed": (
            "the endpoint echoed the requested id, so what answered is not identified"
        ),
        "log.canary_only": (
            "Where what answered is not identified, only a canary sees whether "
            "the model's behaviour changed."
        ),
        "log.replay": (
            "{run} re-judged {source} and asked the target nothing; it is not "
            "counted as a sighting of the target."
        ),
        "log.rolls.none": "No roll recorded.",
        "log.roll": (
            "{side}: {sent} answered as {before} last at {last_before}, and as "
            "{after} first at {first_after}."
        ),
        "log.roll.silence": (
            "{count} run(s) between them recorded no answering model."
        ),
        "log.reference": (
            "Reference {run}, recorded {created_at}, approved {promoted_at}."
        ),
        "log.reference.undated": (
            "Reference {run}, recorded {created_at}; when it was approved was "
            "not recorded."
        ),
        "log.reference.none": "No reference is approved for this suite.",
        "log.reference.side": "  {side}: {sighting}",
        # The register's section of the same reading (ADR 0021 §8).
        "log.register.heading": "Dispositions recorded",
        "log.register.none": "  No disposition is recorded for this suite.",
        "log.register.unreadable": (
            "  The register could not be read, so no disposition is shown."
        ),
        "log.register.torn": (
            "  The register's last line is incomplete and was not read."
        ),
        "log.register.reference": "  Against reference {run}:",
        "log.register.entry": (
            "    {recorded_at} · {disposition}: {run}, exit {exit_code} — "
            "{regressed} worse, {improved} better, {unjudged} not judged"
        ),
        "log.disposition.accepted": "accepted",
        "log.disposition.rejected": "rejected",
        "log.disposition.unsure": "unsure",
    },
    "it": {
        "document.title": "Rapporto di valutazione — {suite}",
        "header.tenant": "Cliente",
        "header.suite": "Suite",
        "header.environment": "Questa esecuzione",
        "header.baseline_environment": "Riferimento",
        "header.commit": "Versione del codice",
        "header.dirty": (
            " — erano presenti modifiche non committate, quindi questa "
            "esecuzione non è riproducibile dal repository"
        ),
        "header.redacted": "Contenuti omessi",
        "header.redacted.value": "Questo rapporto è prodotto da dati redatti.",
        "header.promoted": "Riferimento approvato",
        "header.rejudged": "Risposte riascoltate da",
        "answers.title": "Che cosa ha risposto il sistema",
        "answers.note": (
            "Registrate perché questa suite lo ha chiesto. Restano in questo "
            "repository: un documento prodotto per chi sta fuori porta i "
            "verdetti, non le risposte."
        ),
        "answers.column.case": "Caso",
        "answers.column.input": "Domanda",
        "answers.column.output": "Risposta",
        "noreference.title": "Nessun riferimento con cui confrontare",
        "noreference.sentence": (
            "Questa è l'esecuzione così come è stata misurata. Se sia "
            "peggiorata è una domanda che richiede un riferimento approvato: "
            "questo documento non risponde a quella domanda."
        ),
        "runtally.cases": "casi",
        "runtally.checks": "controlli",
        "runtally.unjudged": "casi non giudicati",
        "runtally.suspended": "casi messi da parte",
        "answer.question": "È peggiorato?",
        "answer.yes": "Sì",
        "answer.no": "No",
        "fact.worse.none": "Nulla è peggiorato rispetto al riferimento.",
        "fact.worse.one": "1 controllo è peggiorato rispetto al riferimento.",
        "fact.worse.many": "{count} controlli sono peggiorati rispetto al riferimento.",
        "fact.noise.one": "1 controllo si è mosso entro il rumore.",
        "fact.noise.many": "{count} controlli si sono mossi entro il rumore.",
        "fact.unjudged.none": "Tutti i casi sono stati giudicati.",
        "fact.unjudged.one": "1 caso non è stato possibile giudicarlo.",
        "fact.unjudged.many": "{count} casi non è stato possibile giudicarli.",
        "fact.suspended.none": "Nessun caso è sospeso.",
        "fact.suspended.one": "1 caso è sospeso.",
        "fact.suspended.many": "{count} casi sono sospesi.",
        "fact.config.changed": (
            "La suite è cambiata rispetto al riferimento, quindi questi numeri "
            "confrontano regole diverse."
        ),
        "fact.config.unchanged": "La suite è invariata rispetto al riferimento.",
        "fact.artifacts.unchanged": (
            "I file in prova sono gli stessi del riferimento."
        ),
        "fact.artifacts.one": "1 file in prova è cambiato rispetto al riferimento.",
        "fact.artifacts.unknown": (
            "I file in prova non sono inclusi, quindi non si sa se siano cambiati."
        ),
        "fact.artifacts.many": (
            "{count} file in prova sono cambiati rispetto al riferimento."
        ),
        "fact.rejudged": (
            "Le risposte di questa esecuzione sono state riascoltate da una "
            "esecuzione archiviata, non misurate: al sistema in prova non è "
            "stato chiesto nulla."
        ),
        "fact.on_the_line.one": (
            "1 controllo è sul filo: la banda misurata copre la sua soglia."
        ),
        "fact.on_the_line.many": (
            "{count} controlli sono sul filo: le bande misurate coprono le loro soglie."
        ),
        "fact.canary.one": (
            "Il modello dietro questo alias è probabilmente cambiato: la "
            "sentinella {case} si è mossa da {before} a {after}{beyond}."
        ),
        "fact.canary.many": (
            "Il modello dietro questo alias è probabilmente cambiato: {count} "
            "controlli sentinella si sono mossi, fra cui {case} da {before} a "
            "{after}{beyond}."
        ),
        "fact.canary.beyond": ", oltre il rumore di questo controllo ({interval})",
        "fact.calibration.one": (
            "Il caso di calibrazione {case} ha ottenuto {score}{across}, fuori "
            "dalla banda dichiarata {low}–{high}: i punteggi giudicati in questa "
            "esecuzione non stanno sulla scala su cui vengono confrontati."
        ),
        "fact.calibration.many": (
            "{count} casi di calibrazione sono fuori dalla banda dichiarata, fra "
            "cui {case} con {score}{across} rispetto a {low}–{high}: i punteggi "
            "giudicati in questa esecuzione non stanno sulla scala su cui "
            "vengono confrontati."
        ),
        "fact.calibration.across": " su {count} campioni ({values})",
        "fact.target_config.changed": (
            "Il sistema in prova ha risposto con una configurazione diversa: {changes}."
        ),
        "fact.target_config.unchanged": (
            "Il sistema in prova ha risposto con la stessa configurazione del "
            "riferimento."
        ),
        "fact.target_config.unknown": (
            "La configurazione del sistema in prova non è registrata da "
            "entrambe le parti, quindi non si sa se sia cambiata."
        ),
        "fact.target_config.withheld_identity": (
            "Il sistema in prova ha risposto con la stessa configurazione "
            "dichiarata; il modello che ha risposto è trattenuto, quindi non si "
            "sa se sia cambiato."
        ),
        "fact.target_config.echoed": (
            "L'endpoint ha restituito l'id richiesto, {model}, come modello che "
            "ha risposto, quindi quale modello abbia risposto non è "
            "identificato; solo un canary vede se il suo comportamento è "
            "cambiato."
        ),
        "explain.tally.echoed": (
            "L'endpoint ha restituito l'id richiesto come modello che ha "
            "risposto, quindi quale modello abbia risposto non è identificato."
        ),
        "explain.tally.shape": (
            "{check}: {share} di {scores} punteggi giudicati a 0 o 1, rispetto a "
            "{reference_share} di {reference_scores} nel riferimento."
        ),
        "explain.tally.shape.noreference": (
            "{check}: {share} di {scores} punteggi giudicati a 0 o 1; il "
            "riferimento non registra punteggi giudicati da affiancare."
        ),
        "explain.tally.shape.none": (
            "{check}: nessun suo punteggio giudicato è leggibile in questa esecuzione."
        ),
        "explain.tally.shape.sample_means.one": (
            " 1 verdetto è escluso: i suoi punteggi per giudizio non sono stati "
            "registrati, solo le loro medie."
        ),
        "explain.tally.shape.sample_means.many": (
            " {count} verdetti sono esclusi: i loro punteggi per giudizio non sono "
            "stati registrati, solo le loro medie."
        ),
        "explain.tally.shape.reference_sample_means.one": (
            " Nel riferimento, 1 verdetto è escluso: i suoi punteggi per giudizio "
            "non sono stati registrati, o non si distinguono da medie."
        ),
        "explain.tally.shape.reference_sample_means.many": (
            " Nel riferimento, {count} verdetti sono esclusi: i loro punteggi per "
            "giudizio non sono stati registrati, o non si distinguono da medie."
        ),
        "explain.tally.shape.single_claim.one": (
            " 1 verdetto con una sola affermazione è escluso: può valere solo 0 o 1."
        ),
        "explain.tally.shape.single_claim.many": (
            " {count} verdetti con una sola affermazione sono esclusi: possono "
            "valere solo 0 o 1."
        ),
        "explain.tally.shape.claims_unrecorded.one": (
            " 1 verdetto campionato è letto senza che il numero di affermazioni "
            "per campione sia registrato."
        ),
        "explain.tally.shape.claims_unrecorded.many": (
            " {count} verdetti campionati sono letti senza che il numero di "
            "affermazioni per campione sia registrato."
        ),
        "fact.judge_config.changed": (
            "Il modo di giudicare è cambiato ({changes}), quindi questi "
            "punteggi sono meno confrontabili con il riferimento: a spostarsi "
            "è lo strumento di misura, non solo ciò che misura."
        ),
        "config.title": "Che cosa ha risposto",
        "config.judge.title": "Che cosa ha giudicato",
        "config.column.parameter": "Parametro",
        "config.column.value": "Questa esecuzione",
        "config.column.reference": "Riferimento",
        "config.value.withheld": "non incluso",
        "config.unchanged": "Configurato come nel riferimento.",
        "config.changed.one": "1 parametro è cambiato rispetto al riferimento.",
        "config.changed.many": (
            "{count} parametri sono cambiati rispetto al riferimento."
        ),
        "config.unknown": (
            "Il riferimento non registra la propria configurazione, quindi "
            "non si sa se sia cambiata."
        ),
        "config.judge.reduced": (
            "Il giudice non è quello che ha prodotto il riferimento, quindi "
            "questi punteggi sono meno confrontabili di quanto la loro "
            "differenza suggerisca."
        ),
        "config.change.changed": "{field} {before} → {after}",
        "config.change.new": "{field} {after}, non inviato per il riferimento",
        "config.change.missing": "{field} {before}, non più inviato",
        "config.change.new.observed": (
            "{field} {after}, non riportato per il riferimento"
        ),
        "config.change.missing.observed": "{field} {before}, non più riportato",
        "config.judge.added": "{judge} è stato aggiunto come giudice",
        "config.judge.removed": "{judge} non giudica più",
        "config.coincides": " Questo calo coincide con {changes}.",
        "config.terminal.target": "sistema",
        "config.terminal.judge": "giudice",
        "artifacts.title": "Che cosa era in prova",
        "artifacts.unchanged": "I file in prova sono gli stessi del riferimento.",
        "artifacts.changed.one": "1 file in prova è cambiato.",
        "artifacts.changed.many": "{count} file in prova sono cambiati.",
        "artifacts.outcome.changed": "cambiato",
        "artifacts.outcome.new": "aggiunto rispetto al riferimento",
        "artifacts.outcome.missing": "non più dichiarato",
        "artifacts.outcome.unknown": ("non incluso, quindi non si sa se sia cambiato"),
        "artifacts.withheld": "Il contenuto non è incluso in questo rapporto.",
        "artifacts.tally": "+{added} −{removed} righe",
        "artifacts.column.file": "File",
        "artifacts.column.fingerprint": "Impronta",
        "artifacts.column.what": "Che cosa è successo",
        "aggregates.title": "Nel complesso",
        "aggregates.failing_not_worse": (
            "Alcune misure sono sotto la loro soglia e non sono comunque "
            "segnalate come peggiorate: erano sotto anche nel riferimento. La "
            "soglia dice che il sistema non raggiunge l'asticella; il confronto "
            "dice che non si è spostato. Sono vere entrambe, e la risposta qui "
            "sopra la decide solo lo spostamento."
        ),
        "aggregate.counted": (
            "{considered} contati · {suspended} sospesi · {errored} non giudicabili"
        ),
        "column.measure": "Misura",
        "column.result": "Risultato",
        "scope.run": "intera esecuzione",
        "section.failed": "Che cosa non ha raggiunto la soglia",
        "section.passed": "Che cosa ha raggiunto la soglia",
        "section.regressions": "Che cosa è peggiorato",
        "section.unjudged": "Che cosa non è stato possibile giudicare",
        "section.suspended": "Che cosa è messo da parte",
        "section.changes": "Che cosa è stato aggiunto o tolto",
        "section.improvements": "Che cosa è migliorato",
        "section.unchanged": "Che cosa è rimasto uguale",
        "section.calibration": (
            "Dove il giudice ha collocato le risposte di calibrazione"
        ),
        "section.empty": "Niente in questa sezione.",
        "summary.truncated": (
            "mostrate le prime {shown} di {total}; l'elenco completo è nel rapporto"
        ),
        "column.case": "Caso",
        "column.check": "Controllo",
        "column.band": "Banda dichiarata",
        "calibration.inside": "dentro",
        "calibration.outside": "fuori",
        "column.detail": "Che cosa è successo",
        "column.reason": "Perché",
        "detail.dropped": "Il punteggio è sceso da {before} a {now}.",
        "detail.rose": "Il punteggio è salito da {before} a {now}.",
        "detail.unchanged": "Punteggio invariato a {now}.",
        "noise.interval": "{low}–{high} su {count} campioni",
        "detail.within_noise": (
            "Il punteggio si è spostato da {before} a {now} — entro il rumore "
            "di questo controllo ({noise}); non conta come peggioramento."
        ),
        "detail.dropped.beyond_noise": (
            "Il punteggio è sceso da {before} a {now} — oltre il rumore di "
            "questo controllo ({noise})."
        ),
        "detail.rose.beyond_noise": (
            "Il punteggio è salito da {before} a {now} — oltre il rumore di "
            "questo controllo ({noise})."
        ),
        "detail.flipped.worse": "Da superato a non superato ({before} → {now}).",
        "detail.flipped.better": "Da non superato a superato ({before} → {now}).",
        "detail.threshold_moved": (
            " La soglia si è spostata da {before_threshold} a {now_threshold}, "
            "quindi è un cambio di regola e non di comportamento."
        ),
        "detail.new": "Controllato qui, assente nel riferimento.",
        "detail.new.errored": (
            "Nuovo qui, e il controllo non ha potuto essere eseguito."
        ),
        "detail.missing": "Presente nel riferimento, non controllato qui.",
        "detail.errored": "Il controllo non ha potuto essere eseguito.",
        "detail.three_way": (
            " I campioni sono andati in tre direzioni: {passed} superati, "
            "{failed} falliti, {errored} non giudicabili."
        ),
        "detail.exceedances": (
            " {over} chiamate su {judged} hanno superato da sole il tetto di "
            "{cap}, la maggiore a {worst}."
        ),
        "detail.exceedances.pinned": (
            " {over} chiamate su {judged} hanno superato da sole il tetto di "
            "{cap}; la maggiore si ferma sul tetto."
        ),
        "reason.unavailable": "Non inclusa in questo rapporto.",
        "diff.title": "Due esecuzioni a confronto — {suite}",
        "diff.column.run": "Esecuzione",
        "diff.column.check": "Controllo",
        "diff.column.case": "Caso",
        "diff.column.what": "Che cosa hanno detto le due esecuzioni",
        "diff.systems.same": (
            "Le due esecuzioni hanno risposto con la stessa configurazione registrata."
        ),
        "diff.systems.differ": "I sistemi sono diversi: {changes}.",
        "diff.systems.unknown": (
            "La configurazione non è registrata da entrambe le parti, quindi "
            "non si sa se i sistemi siano diversi."
        ),
        "diff.judge.same": "Entrambe le esecuzioni sono state giudicate da {judges}.",
        "diff.change.pair": "{field} {left} contro {right}",
        "diff.artifacts.same": (
            "I file in prova sono gli stessi nelle due esecuzioni."
        ),
        "diff.artifacts.one": ("1 file in prova è diverso fra le due esecuzioni."),
        "diff.artifacts.many": (
            "{count} file in prova sono diversi fra le due esecuzioni."
        ),
        "diff.artifacts.unknown": (
            "I file in prova non sono inclusi, quindi non si sa se siano diversi."
        ),
        "diff.artifacts.outcome.differs": "diverso",
        "diff.artifacts.outcome.only": "dichiarato solo in {run}",
        "diff.artifacts.outcome.unknown": (
            "non incluso, quindi non si sa se sia diverso"
        ),
        "diff.count.none": "Nessun controllo è diverso, su {total}.",
        "diff.count.one": "1 controllo su {total} è diverso: {breakdown}.",
        "diff.count.many": (
            "{differing} controlli su {total} sono diversi: {breakdown}."
        ),
        "diff.breakdown.favours.one": "1 va a {run}",
        "diff.breakdown.favours.many": "{count} vanno a {run}",
        "diff.breakdown.tolerance.one": "1 entro la tolleranza",
        "diff.breakdown.tolerance.many": "{count} entro la tolleranza",
        "diff.breakdown.one_side.one": "1 presente in una sola esecuzione",
        "diff.breakdown.one_side.many": ("{count} presenti in una sola esecuzione"),
        "diff.breakdown.errored.one": "1 non è stato possibile giudicarlo",
        "diff.breakdown.errored.many": ("{count} non è stato possibile giudicarli"),
        "diff.overlap.one": (
            "1 differenza ricade dentro gli intervalli osservati di entrambe "
            "le esecuzioni: non se ne può affermare nulla."
        ),
        "diff.overlap.many": (
            "{count} differenze ricadono dentro gli intervalli osservati di "
            "entrambe le esecuzioni: non se ne può affermare nulla."
        ),
        "diff.exceeds.one": (
            "1 dei vantaggi di {run} supera gli intervalli osservati di "
            "entrambe le esecuzioni."
        ),
        "diff.exceeds.many": (
            "{count} dei vantaggi di {run} superano gli intervalli osservati "
            "di entrambe le esecuzioni."
        ),
        "diff.detail.scores": "{left_run} {left_score}, {right_run} {right_score}.",
        "diff.detail.flipped": (" {pass_run} supera questo controllo e {fail_run} no."),
        "diff.detail.tolerance": " Entro la tolleranza dichiarata {tolerance}.",
        "diff.detail.overlap": (
            " Gli intervalli osservati {left_noise} e {right_noise} si "
            "sovrappongono, quindi le due non sono distinguibili da questo "
            "controllo."
        ),
        "diff.detail.disjoint": (
            " Gli intervalli osservati {left_noise} e {right_noise} non si "
            "sovrappongono."
        ),
        "diff.detail.only": "Controllato solo in {run}.",
        "diff.detail.errored": "Il controllo non ha potuto essere eseguito in {run}.",
        "diff.detail.errored.both": (
            "Il controllo non ha potuto essere eseguito in nessuna delle due."
        ),
        "diff.section.differ": (
            "Che cosa le due esecuzioni hanno risposto in modo diverso"
        ),
        "diff.section.same": "Su che cosa le due esecuzioni concordano",
        "view.title.runs": "Esecuzioni — {suite}",
        "view.title.case": "Caso {case_id} — {suite}",
        "view.title.suspend": "Sospendi {case_id} — {suite}",
        "view.nav.runs": "Esecuzioni",
        "view.nav.report": "Rapporto",
        "view.baseline": "riferimento",
        "view.column.key": "Esecuzione",
        "view.column.aggregate_note": "variazione rispetto al riferimento",
        "view.commit.dirty": "modifiche non committate",
        "view.commit.none": "nessun repository git",
        "view.promote.errored": (
            "{count} caso/i non è stato possibile giudicarli, quindi questa "
            "esecuzione non può diventare un riferimento: un errore non è un "
            "riferimento."
        ),
        "view.promote.older": (
            "Questa esecuzione è stata prodotta con una versione precedente "
            "della suite, quindi non può diventare un riferimento: i suoi "
            "punteggi sono stati ottenuti con regole diverse da quelle in "
            "vigore. Resta confrontabile."
        ),
        "view.chip.errored": "{count} non giudicati",
        "view.chip.older_config": "suite precedente",
        "view.action.compare": "Confronta",
        "view.action.compare.title": ("confronta questa esecuzione con il riferimento"),
        "view.copy_snippet": "clicca la riga per selezionarla",
        "view.column.created": "Registrata",
        "view.column.env": "Ambiente",
        "view.column.commit": "Versione del codice",
        "view.column.cases": "Casi",
        "view.column.actions": "Azioni",
        "view.artifacts.stamp": "prompt {sha}",
        "view.artifacts.title": (
            "impronta dei {count} file in prova in questa esecuzione"
        ),
        "view.column.run": "Esecuzione",
        "view.column.votes": "Voti",
        "view.no_runs": "Nessuna esecuzione registrata.",
        "view.no_aggregates": "Questa suite non dichiara aggregati.",
        "view.ignored": "Non mostrate: {note}. Esegui `digline migrate`.",
        "view.compare.pick": "Confronta",
        "view.compare.against": "con",
        "view.compare.go": "Mostra",
        "view.compare.same": "Una run confrontata con se stessa non ha nulla da dire.",
        "view.case.absent": "assente in questa run",
        "view.case.suspended": "messo da parte",
        "view.case.title": "Come è stato giudicato {case_id}, dal più vecchio",
        "view.case.votes_note": (
            "Per un controllo campionato i voti grezzi stanno sotto al punteggio "
            "combinato: è lì che il rumore del giudice si vede."
        ),
        "view.promote.button": "Rendi riferimento",
        "view.promote.done": "Riferimento impostato su {run_key}.",
        "view.promote.refused": "Rifiutato: {why}",
        "view.suspend.title": "Metti da parte {case_id}",
        "view.suspend.reason": "Perché viene messo da parte?",
        "view.suspend.show": "Mostra la modifica",
        "view.suspend.explain": (
            "Una sospensione vive nella suite, che è codice. Questa pagina non "
            "scrive nulla: produce la riga da aggiungere, e la committi tu — "
            "così il motivo viaggia col caso nella stessa revisione di tutto "
            "il resto."
        ),
        "view.suspend.needs_reason": (
            "Una sospensione senza motivo dichiarato è un caso che sparisce in "
            "silenzio. Scrivi perché."
        ),
        # --- la lettura (`digline explain`, ADR 0012) ------------------------
        #
        # Vale qui la regola scritta in inglese sopra: ogni stringa è una
        # constatazione, mai un'istruzione, e nessuna parla di una seconda
        # esecuzione — una lettura riguarda una run e il suo riferimento.
        "explain.heading.tally": "Che cosa è stato eseguito",
        "explain.heading.settings.compared": "Che cosa differiva sotto",
        "explain.heading.settings.alone": "Com'era configurato",
        "explain.heading.checks.compared": "Che cosa si è mosso",
        "explain.heading.checks.alone": "Che cosa ha rilevato",
        "explain.tally.cases.none": "Nessun caso è stato eseguito.",
        "explain.tally.cases.one": "È stato eseguito 1 caso.",
        "explain.tally.cases.many": "Sono stati eseguiti {count} casi.",
        "explain.tally.checks.none": "Nessun controllo è stato eseguito.",
        "explain.tally.checks.one": "È stato eseguito 1 controllo.",
        "explain.tally.checks.many": "Sono stati eseguiti {count} controlli.",
        "explain.tally.unjudged.none": "Ogni caso è stato valutato.",
        "explain.tally.unjudged.one": "1 caso non è stato valutato.",
        "explain.tally.unjudged.many": "{count} casi non sono stati valutati.",
        "explain.tally.suspended.none": "Nessun caso è sospeso.",
        "explain.tally.suspended.one": "1 caso è sospeso.",
        "explain.tally.suspended.many": "{count} casi sono sospesi.",
        "explain.tally.within_noise.one": (
            "1 controllo si è mosso, e l'intervallo misurato dal riferimento "
            "copre lo spostamento."
        ),
        "explain.tally.within_noise.many": (
            "{count} controlli si sono mossi, e gli intervalli misurati dal "
            "riferimento coprono lo spostamento."
        ),
        "explain.tally.suite_config.changed": (
            "La suite è cambiata rispetto al riferimento: questi numeri "
            "confrontano regole diverse."
        ),
        "explain.tally.suite_config.unchanged": (
            "La suite è invariata rispetto al riferimento."
        ),
        "explain.tally.comparability": (
            "Il modo di giudicare è cambiato: questi punteggi non sono "
            "confrontabili con il riferimento. Lo strumento che ha valutato non "
            "è quello che ha valutato il riferimento, e ogni differenza qui "
            "sotto è misurata su due scale."
        ),
        "explain.tally.rejudged": (
            "Le risposte giudicate qui sono state riascoltate da una "
            "esecuzione archiviata: al sistema sotto esame non è stato chiesto "
            "nulla, quindi questi numeri misurano il modo di giudicare."
        ),
        "explain.tally.canary": (
            "Un controllo sentinella si è mosso. Non entra in nessun "
            "aggregato, e ciò di cui il suo movimento parla è quale modello "
            "abbia risposto, non quanto bene."
        ),
        "judged.range": (
            "l'intervallo del giudice su queste risposte è al più {range} su "
            "{count} giudizi ({check}, risposta {answer} del caso {case})"
        ),
        "judged.range.none": (
            "l'intervallo del giudice su queste risposte non è stato misurato: "
            "nessuna risposta giudicata ha restituito due punteggi"
        ),
        "judged.errored.one": ", e 1 giudizio non ha restituito un punteggio",
        "judged.errored.many": (
            ", e {count} giudizi non hanno restituito un punteggio"
        ),
        "judged.calibration.inside": (
            "; il caso di calibrazione {case} ha ottenuto {score}, dentro la "
            "banda dichiarata {low}–{high}"
        ),
        "judged.calibration.outside": (
            "; il caso di calibrazione {case} ha ottenuto {score}, fuori dalla "
            "banda dichiarata {low}–{high}"
        ),
        "judged.calibration.unjudged": (
            "; il caso di calibrazione {case} non è stato possibile giudicarlo"
        ),
        "judged.calibration.none": (
            "; questa suite non dichiara un caso di calibrazione, e un giudice "
            "che ha perso la sua scala risulta perfettamente ripetibile"
        ),
        "explain.tally.calibration.one": (
            "1 caso di calibrazione è fuori dalla banda dichiarata: i punteggi "
            "giudicati in questa esecuzione non stanno sulla scala su cui "
            "vengono confrontati. Non entra in nessun aggregato, e al sistema "
            "sotto esame non è stato chiesto nulla per esso."
        ),
        "explain.tally.calibration.many": (
            "{count} casi di calibrazione sono fuori dalla banda dichiarata: i "
            "punteggi giudicati in questa esecuzione non stanno sulla scala su "
            "cui vengono confrontati. Non entrano in nessun aggregato, e al "
            "sistema sotto esame non è stato chiesto nulla per essi."
        ),
        "explain.tally.on_the_line.one": (
            "1 controllo ha misurato una banda che copre la propria soglia: da "
            "quale lato sia caduto dipende dai campioni estratti."
        ),
        "explain.tally.on_the_line.many": (
            "{count} controlli hanno misurato una banda che copre la propria "
            "soglia: da quale lato siano caduti dipende dai campioni estratti."
        ),
        "explain.tally.denominator_moved.one": (
            "1 controllo di esecuzione è stato misurato su un numero di casi "
            "diverso da quello del riferimento accanto: le due non sono la "
            "stessa misura, e nessuna è uno spostamento dell'altra."
        ),
        "explain.tally.denominator_moved.many": (
            "{count} controlli di esecuzione sono stati misurati su un numero di "
            "casi diverso da quello del riferimento accanto: le due non sono la "
            "stessa misura, e nessuna è uno spostamento dell'altra."
        ),
        "explain.check.on_the_line": (
            " La banda misurata da questa esecuzione copre la soglia: da quale "
            "lato sia caduto dipende dai campioni estratti."
        ),
        "explain.setting.target.changed": (
            "Il sistema sotto esame ha risposto con {name} {after}; il "
            "riferimento ha risposto con {before}."
        ),
        "explain.setting.target.new": (
            "Il sistema sotto esame ha registrato {name} {after}, che il "
            "riferimento non registrava."
        ),
        "explain.setting.target.missing": (
            "Il riferimento registrava {name} {before}; questa esecuzione non "
            "ne registra alcuno."
        ),
        "explain.setting.target.unknown": (
            "Se {name} sia cambiato non è noto: un lato non l'ha registrato, "
            "oppure è stato trattenuto."
        ),
        "explain.setting.judge.changed": (
            "Il giudice ha valutato con {name} {after}; il riferimento è stato "
            "valutato con {before}."
        ),
        "explain.setting.judge.new": (
            "Il giudice ha registrato {name} {after}, che il riferimento non "
            "registrava."
        ),
        "explain.setting.judge.missing": (
            "Il riferimento è stato valutato con {name} {before}; questa "
            "esecuzione non ne registra alcuno."
        ),
        "explain.setting.judge.unknown": (
            "Se {name} del giudice sia cambiato non è noto: un lato non l'ha "
            "registrato, oppure è stato trattenuto."
        ),
        "explain.setting.judge.added": (
            "{after} ha valutato questa esecuzione e non ha valutato il riferimento."
        ),
        "explain.setting.judge.removed": (
            "{before} ha valutato il riferimento e non ha valutato questa esecuzione."
        ),
        "explain.setting.artifact.changed": "{name} è cambiato: {tally}.",
        "explain.setting.artifact.changed.untallied": "{name} è cambiato.",
        "explain.setting.artifact.new": (
            "{name} è sotto esame in questa esecuzione e non lo era nel riferimento."
        ),
        "explain.setting.artifact.missing": (
            "{name} era sotto esame nel riferimento e non lo è in questa esecuzione."
        ),
        "explain.setting.artifact.unknown": (
            "{name} è sotto esame; il contenuto non è incluso, quindi se sia "
            "cambiato non è noto."
        ),
        "explain.setting.target.alone": (
            "Il sistema sotto esame ha risposto con {name} {after}."
        ),
        "explain.setting.judge.alone": "Il giudice ha valutato con {name} {after}.",
        "explain.setting.target.alone.withheld": (
            "Il sistema sotto esame ha registrato {name}; il valore non è incluso."
        ),
        "explain.setting.judge.alone.withheld": (
            "Il giudice ha registrato {name}; il valore non è incluso."
        ),
        "explain.setting.artifact.alone": "{name} era sotto esame.",
        "explain.setting.artifact.alone.withheld": (
            "{name} era sotto esame; il contenuto non è incluso."
        ),
        "explain.check.regressed": (
            "{where} è peggiorato: da {before} a {now}, un calo di {delta}."
        ),
        "explain.check.improved": (
            "{where} è migliorato: da {before} a {now}, un aumento di {delta}."
        ),
        "explain.check.unchanged": (
            "{where} si è spostato da {before} a {now}, entro la tolleranza "
            "dichiarata dalla suite."
        ),
        "explain.check.within_noise": (
            "{where} si è spostato da {before} a {now}, entro l'intervallo "
            "misurato dal riferimento."
        ),
        "explain.check.new": (
            "{where} è stato controllato qui e non è nel riferimento, quindi "
            "non c'è nulla con cui confrontarlo."
        ),
        "explain.check.missing": (
            "{where} è nel riferimento e qui non è stato controllato."
        ),
        "explain.check.errored": "{where} non è stato valutato.",
        "explain.check.failing": "{where} è sotto la sua soglia, a {now}.",
        "explain.check.suspended": (
            "Il caso {case} è stato messo da parte, quindi su di esso non è "
            "stato misurato nulla. Il motivo dichiarato non viaggia qui."
        ),
        "explain.where.run": "l'intera esecuzione",
        "explain.bar": " La soglia è {threshold}.",
        "explain.noise.beyond": (
            " È fuori dall'intervallo misurato dal riferimento, {noise}."
        ),
        "explain.nothing": "Niente in questo gruppo.",
        "log.heading": (
            "{suite} · {count} esecuzioni lette in questo archivio, da {first} a {last}"
        ),
        "log.empty": (
            "{suite} · nessuna esecuzione letta in questo archivio, in questa finestra."
        ),
        "log.window": "Finestra: da {since} a {until}.",
        "log.window.open": "…",
        "log.not_read.schema": (
            "{count} esecuzioni allo schema {version} non sono state lette."
        ),
        "log.not_read.unreadable": "{count} file non si sono potuti leggere.",
        "log.side.target": "Sistema",
        "log.side.judge": "Giudice",
        "log.span": (
            "  {sighting} — da {first} a {last}, {runs} esecuzioni{environments}"
        ),
        "log.environments": " ({environments})",
        "log.sighting.answered": "{who}, ha risposto come {answered}",
        "log.sighting.absent": "{who}: {absence}",
        "log.absence.declared_nothing": "nessuna configurazione dichiarata",
        "log.absence.several_judges": (
            "più giudici; nessun singolo modello che ha risposto"
        ),
        "log.absence.withheld": (
            "il modello che ha risposto è trattenuto presso un endpoint nominato"
        ),
        "log.absence.not_reported": "nessun modello che ha risposto è stato riportato",
        "log.absence.not_recorded": (
            "non registrato: il documento non dice quale versione l'ha scritto"
        ),
        "log.absence.echoed": (
            "l'endpoint ha restituito l'id richiesto, quindi il modello che ha "
            "risposto non è identificato"
        ),
        "log.canary_only": (
            "Dove il modello che ha risposto non è identificato, solo un canary "
            "vede se il suo comportamento è cambiato."
        ),
        "log.replay": (
            "{run} ha rivalutato {source} senza interrogare il sistema; non conta "
            "come avvistamento del sistema."
        ),
        "log.rolls.none": "Nessun cambio di modello registrato.",
        "log.roll": (
            "{side}: {sent} ha risposto come {before} l'ultima volta a "
            "{last_before}, e come {after} la prima volta a {first_after}."
        ),
        "log.roll.silence": (
            "{count} esecuzioni tra le due non hanno registrato il modello che ha "
            "risposto."
        ),
        "log.reference": (
            "Riferimento {run}, registrato a {created_at}, approvato a {promoted_at}."
        ),
        "log.reference.undated": (
            "Riferimento {run}, registrato a {created_at}; quando sia stato "
            "approvato non è registrato."
        ),
        "log.reference.none": "Nessun riferimento approvato per questa suite.",
        "log.reference.side": "  {side}: {sighting}",
        "log.register.heading": "Decisioni registrate",
        "log.register.none": "  Nessuna decisione registrata per questa suite.",
        "log.register.unreadable": (
            "  Il registro non si è potuto leggere, quindi nessuna decisione è "
            "mostrata."
        ),
        "log.register.torn": (
            "  L'ultima riga del registro è incompleta e non è stata letta."
        ),
        "log.register.reference": "  Rispetto al riferimento {run}:",
        "log.register.entry": (
            "    {recorded_at} · {disposition}: {run}, uscita {exit_code} — "
            "{regressed} peggiorati, {improved} migliorati, {unjudged} non valutati"
        ),
        "log.disposition.accepted": "accettata",
        "log.disposition.rejected": "rifiutata",
        "log.disposition.unsure": "incerta",
    },
}


def strings(locale: Locale) -> Mapping[str, str]:
    """The table for `locale`, or `ValueError` naming what is available.

    Checked **at the call**, before any markup is produced: a document that
    fails halfway is worse than one that never starts, because a truncated
    report still looks like a report.
    """
    table = TEXT.get(locale)
    if table is None:
        available = ", ".join(sorted(TEXT))
        raise ValueError(f"unknown locale {locale!r}; available: {available}")
    return table


def phrase(locale: Locale, key: str, **params: object) -> str:
    """One localized string. A missing key is a programming error and says so
    with the key, rather than rendering an empty cell nobody notices."""
    table = strings(locale)
    template = table.get(key)
    if template is None:
        raise KeyError(f"no text for {key!r} in locale {locale!r}")
    return template.format(**params) if params else template
