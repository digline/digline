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

from digline.core.refused import RefusedError

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
        # Beside the line above, not instead of it: a projected document is
        # redacted too. This one says what the 22-character strings are, to a
        # reader who has never met a token, and where the names are, which is
        # what tells them what to do. It does not say that one name is one
        # string across documents: that holds only while the data owner keeps
        # one table, and nothing checks it (ADR 0036). (#313)
        "header.projected": "Names replaced",
        "header.projected.value": (
            "The names in this report (of cases, checks, groups, files, "
            "configuration parameters and their text values, and the judge) "
            "are replaced by strings of 22 characters. Numbers, outcomes and "
            "dates are as measured. The names are kept by the data owner, and "
            "only there can a string be turned back into the name it stands "
            "for: to learn one, ask the data owner."
        ),
        # Named in the header rather than only in the sentence: a reader who
        # scrolls past the first screen must still be able to see that the
        # answers came from a stored run, and which one.
        "header.promoted": "Reference approved",
        # The key a promotion has to name to replace this reference, printed
        # where a reader of the comparison can copy it from (ADR 0031 §2).
        "header.baseline_key": "Reference key",
        "summary.against": "tenant {tenant}, against baseline {reference}",
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
        # Straight after the `worse` clauses, on `fact.denominator_moved`'s
        # precedent: these checks were not compared, so the count above is not
        # about them. Each pair names both sides with their scores, because
        # nowhere else does a fall between them show, and the clause ends on
        # what two documents cannot say. A cause of exit 2. (#642)
        "fact.unpaired.one": (
            "1 check was not compared, because the reference and this run "
            "hold a different check under its name: {pairs}. Whether it was "
            "changed or replaced, the two documents cannot say."
        ),
        "fact.unpaired.many": (
            "{count} checks were not compared, because the reference and this "
            "run hold a different check under each name: {pairs}. Whether each "
            "was changed or replaced, the two documents cannot say."
        ),
        # The way back in line, after what the two documents cannot say: the
        # run made the reference, which `promote` does not refuse for this.
        "fact.unpaired.step": (
            "If the change was meant, make this run the reference to compare "
            "them again: digline promote --suite <suite> --run {run} "
            "--replacing {reference}."
        ),
        "fact.unpaired.pair": (
            "{case} · {check}, {before} in the reference and {after} here"
        ),
        "fact.unpaired.moved": ", {field} {before} → {after}",
        "fact.unpaired.field.threshold": "threshold",
        "fact.unpaired.field.tolerance": "tolerance",
        "fact.unpaired.state.pass": "passing at {score}",
        "fact.unpaired.state.fail": "failing at {score}",
        "fact.unpaired.state.error": "in error at {score}",
        "fact.unpaired.state.pass.unscored": "passing with no score",
        "fact.unpaired.state.fail.unscored": "failing with no score",
        "fact.unpaired.state.error.unscored": "in error with no score",
        # Straight after the `worse` clauses, because it qualifies them: a
        # gate measured over a different number of cases was not compared at
        # all, so "Nothing got worse" is an answer about the checks that
        # were. Silent at zero. (the delta-pass over 0.15.1)
        "fact.denominator_moved.one": (
            "1 run-level check was measured over a different number of cases "
            "than the reference, so it is not a comparison."
        ),
        "fact.denominator_moved.many": (
            "{count} run-level checks were measured over a different number "
            "of cases than the reference, so they are not comparisons."
        ),
        "fact.noise.one": "1 check moved within noise.",
        "fact.noise.many": "{count} checks moved within noise.",
        # Before every count, because it is what they would be counts of: no
        # case the suite measures was judged, so "nothing got worse" beside it
        # is not a measurement. (ADR 0049 §3, §4)
        "fact.nothing_judged": (
            "None of the cases this suite measures was judged, so this run "
            "cannot say whether anything got worse."
        ),
        # The line a pytest session prints for a suite digline did not say green
        # for, named the way the session names that suite's rows. The code is
        # `exit_code()`'s; its cause is in the suite's own sentence, which this
        # line does not repeat. (ADR 0049 §7)
        "fact.session_not_green": (
            "{suite}: digline exits {code}, so this session does not end green."
        ),
        # Why a pytest row reads SKIPPED when the baseline judged its check and
        # the run did not. A suspension carries the reason the suite declares;
        # these are the other three, the last being whatever none of the named
        # causes explains. (#574)
        "fact.row_missing.case": "the suite no longer declares this case",
        "fact.row_missing.check": "the suite no longer declares this check",
        "fact.row_missing.unrecorded": (
            "the stored run has no verdict for this check: run it again, or "
            "pass --digline-run"
        ),
        # What `digline run` says on stderr when checks could not run: the
        # count of `errored_verdicts`, case checks and aggregates. Said only
        # above zero; `run --json` carries the number always. (#654)
        "fact.errored_checks.one": "1 check could not run.",
        "fact.errored_checks.many": "{count} checks could not run.",
        # Said by `digline run` beside the bill, as the errored checks are: a
        # contradiction exits 1 from report, explain and compare, and the
        # person who ran the command should not learn it there first.
        # (ADR 0059 §1)
        # The halves of `contradicted_said`, which joins them: who contradicted
        # a person, the judge or a check on the steps, named with its case.
        # Lower case and with no full stop; the caller closes the line.
        # (ADR 0059 §1, amended 2026-11-05)
        "fact.contradicted.one": (
            "the judge contradicted a person on 1 reviewed answer"
        ),
        "fact.contradicted.many": (
            "the judge contradicted a person on {count} reviewed answers"
        ),
        "fact.contradicted.steps.one": (
            "a check on the steps contradicted a person on {answers}: {checks}"
        ),
        "fact.contradicted.steps.many": (
            "checks on the steps contradicted a person on {answers}: {checks}"
        ),
        "fact.contradicted.answers.one": "1 reviewed answer",
        "fact.contradicted.answers.many": "{count} reviewed answers",
        "fact.contradicted.step_check": "{check}, on case {case}",
        "fact.unjudged.none": "Every case could be judged.",
        "fact.unjudged.one": "1 case could not be judged.",
        # The same count with the denominator it is a count of, and the form
        # every run with more than one case takes: "7 cases could not be
        # judged" leaves the reader to find the 50 somewhere else, which is the
        # disclosure that existed and was never where anybody read it.
        "fact.unjudged.of.one": "{judged} of {total} cases judged, 1 could not be.",
        "fact.unjudged.of.many": (
            "{judged} of {total} cases judged, {count} could not be."
        ),
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
        # Declared must-not-drift, and moved. Worded as what the author asked
        # for rather than as a verdict on it: the run is not worse, the thing it
        # measured is not the thing that was approved.
        "fact.pinned.one": ("1 of them was declared not to change, and it changed."),
        "fact.pinned.many": (
            "{count} of them were declared not to change, and they changed."
        ),
        # Not a pass and not a failure. The sentence says what is missing and
        # who can supply it, because a reader told only "not known" has nothing
        # to do next.
        "fact.pinned.unchecked.one": (
            "1 file declared not to change is not included here, so whether it "
            "changed was not checked."
        ),
        "fact.pinned.unchecked.many": (
            "{count} files declared not to change are not included here, so "
            "whether they changed was not checked."
        ),
        # A pinned file the reference never recorded: included, and with nothing
        # to be compared with. Not the unchecked sentence, whose "not included
        # here" would be false for it. (ADR 0051 §1)
        "fact.pinned.unreferenced.one": (
            "1 file declared not to change has no reference to compare with, so "
            "whether it changed was not checked."
        ),
        "fact.pinned.unreferenced.many": (
            "{count} files declared not to change have no reference to compare "
            "with, so whether they changed was not checked."
        ),
        # A pin the reference held and this run does not: the file may be gone
        # or still here, and the sentence says only what is known. (ADR 0051 §2)
        "fact.pinned.withdrawn.one": (
            "1 file the reference declared not to change is not declared here."
        ),
        "fact.pinned.withdrawn.many": (
            "{count} files the reference declared not to change are not declared here."
        ),
        # The two together, and the reason this exits 2: the readings cannot be
        # told apart. One form, because it is a single fact about the
        # comparison and the counts are in the two clauses before it.
        # (ADR 0051 §3)
        "fact.pinned.lost": (
            "A file the reference declared not to change is gone, and a file "
            "declared not to change here has no reference, so whether one became "
            "the other could not be judged."
        ),
        # Three states of the judged run: a count, or *not recorded*; zero is
        # silent. One clause they end on, the consequence; only the cause
        # differs. (ADR 0052, decision 3)
        "fact.modules_unchecked.one": (
            "1 module was already loaded elsewhere in this process, so whether "
            "it matches the file on disk is not known."
        ),
        "fact.modules_unchecked.many": (
            "{count} modules were already loaded elsewhere in this process, so "
            "whether they match the files on disk is not known."
        ),
        "fact.modules_unchecked.unrecorded": (
            "This run does not record whether the modules it measured were read "
            "from source, so whether they match the files on disk is not known."
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
        "fact.canary.beyond": (
            ", outside the range of the reference's individual samples ({interval})"
        ),
        "fact.canary.beyond.mean": ", outside the reference's noise floor ({interval})",
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
        # Beside the calibration clause, and as plain: who contradicted a
        # person, in `contradicted_said`'s words, which `run` and `explain` say
        # too, then each contradiction with its direction, because a judge too
        # lenient and one too strict are two faults. One and many count
        # answers, not checks. (ADR 0059 §1, amended 2026-11-05)
        "fact.reviewed.one": "{said}, and the case fails: {cases}.",
        "fact.reviewed.many": "{said}, and each of those cases fails: {cases}.",
        # First in the sentence, before any count: a run that does not know what
        # it measured qualifies every number after it. Named, because "1 check
        # short" sends somebody hunting and the name ends the question.
        # (ADR 0027 §3)
        "fact.unreconciled.one": (
            "The run does not reconcile with what the suite asked, at 1 check: "
            "{gaps}. This is not a regression: what the run measured is not "
            "known."
        ),
        "fact.unreconciled.many": (
            "The run does not reconcile with what the suite asked, at {count} "
            "checks: {gaps}. This is not a regression: what the run measured is "
            "not known."
        ),
        # More gaps than a sentence can carry. "including" is the word
        # `fact.calibration.many` uses for the same job, and every one of them
        # is in the run file. (F-5, the second 0.17.0 delta-pass)
        "fact.unreconciled.capped": (
            "The run does not reconcile with what the suite asked, at {count} "
            "checks, including {gaps}. This is not a regression: what the run "
            "measured is not known."
        ),
        # The reference's own gaps, and a clause of their own: a run that does
        # not reconcile is re-run, a reference that does not is re-promoted.
        # (F-10, the second 0.17.0 delta-pass)
        "fact.reference_unreconciled.one": (
            "The reference does not reconcile with what its suite asked, at 1 "
            "check: {gaps}. What the reference measured is not known, and this "
            "comparison is made against it."
        ),
        "fact.reference_unreconciled.many": (
            "The reference does not reconcile with what its suite asked, at "
            "{count} checks: {gaps}. What the reference measured is not known, "
            "and this comparison is made against it."
        ),
        "fact.reference_unreconciled.capped": (
            "The reference does not reconcile with what its suite asked, at "
            "{count} checks, including {gaps}. What the reference measured is "
            "not known, and this comparison is made against it."
        ),
        # A verdict named otherwise than its assertion was refused, and each is
        # one of the checks the unjudged clause counts: this says why, so it
        # sits directly before that clause. (ADR 0027 §6, amended 2026-09-28)
        "fact.misnamed.one": (
            "1 check returned a verdict under a name that is not its "
            "assertion's, and it was refused: {gaps}. The assertion is at "
            "fault, not the system under test."
        ),
        "fact.misnamed.many": (
            "{count} checks returned a verdict under a name that is not their "
            "assertion's, and they were refused: {gaps}. The assertion is at "
            "fault, not the system under test."
        ),
        "fact.misnamed.capped": (
            "{count} checks returned a verdict under a name that is not their "
            "assertion's, and they were refused, including {gaps}. The "
            "assertion is at fault, not the system under test."
        ),
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
        # Never "the same configuration" over a field that was withheld: a
        # withheld field is not an unchanged one, and saying so would be the
        # report asserting what it does not know. Counted and not named, because
        # a count is true in clear and on a projected document alike, where the
        # name is a token and which field it is cannot be told. (#275)
        "fact.target_config.withheld.one": (
            "The system under test answered under the same declared "
            "configuration; 1 of its fields is withheld, so whether it changed "
            "is not known."
        ),
        "fact.target_config.withheld.many": (
            "The system under test answered under the same declared "
            "configuration; {count} of its fields are withheld, so whether they "
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
        "config.title": "How it was set up",
        "config.judge.title": "How the judge was set up",
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
        # A token's field may have been either, so the verb is the one true of
        # both: on a projected document every key is a token. (#275)
        "config.change.new.recorded": (
            "{field} {after}, not recorded for the reference"
        ),
        "config.change.missing.recorded": "{field} {before}, no longer recorded",
        "config.judge.added": "{judge} was added as a judge",
        "config.judge.removed": "{judge} no longer judges",
        "config.coincides": " This drop coincides with {changes}.",
        # The rules, for the terminal. `rules` and not `suite`, because the
        # line stands beside `system` and `judge` and names the same grain: what
        # this run was held to. (ADR 0028 §8)
        "rules.title": "What the rules were",
        "rules.note": (
            "Only the rules that moved. A looser bar lets a run pass where the "
            "reference would not have; the rules in force are in the run's own "
            "document."
        ),
        "rules.column.rule": "Rule",
        "rules.column.moved": "What moved",
        "rules.column.direction": "Which way",
        "rules.cell.moved": "{field} {before} → {after}",
        "rules.cell.new": "added",
        "rules.cell.missing": "removed",
        "rules.cell.unknown": (
            "no single value on one side, so whether it moved is not known"
        ),
        # A width reaches `unknown` where the cases of one side or of both
        # declare different widths, so both sides have values and the row does
        # not say which of the two it is. (F-2, the delta-pass over 1.0.2)
        "rules.cell.unknown.width": (
            "declared differently by the cases of one side or of both, so "
            "whether it moved is not known"
        ),
        "rules.direction.loosened": "looser",
        "rules.direction.tightened": "stricter",
        "rules.terminal": "rules",
        "rules.field.threshold": "threshold of",
        "rules.field.tolerance": "tolerance of",
        "rules.field.samples": "samples of",
        "rules.field.floor_standard_errors": "floor width of",
        "rules.moved.loosened": "{field} {name} {before} → {after} (looser)",
        "rules.moved.tightened": "{field} {name} {before} → {after} (stricter)",
        # No parenthesis, for a row whose movement has no direction: `samples`
        # on a run-level aggregate, whose floor is outside ADR 0050. A case's
        # `samples` and the floor's width take the parenthesis above. (ADR 0028
        # §4, as amended 2026-10-15; ADR 0050, the passenger rule, amended
        # 2026-10-21)
        "rules.moved": "{field} {name} {before} → {after}",
        "rules.new": "{name} added",
        "rules.new.new_group": "{name} added, over a group the reference lacked",
        "rules.new.now_grouped": "{name} added, this aggregate is now per group",
        "rules.missing": "{name} removed",
        "rules.unknown": (
            "{name} has no single value on one side, so whether it moved is not known"
        ),
        "rules.unknown.width": (
            "{name} is declared differently by the cases of one side or of both, "
            "so whether it moved is not known"
        ),
        "rules.unnameable": (
            "the agreement floor is not recorded, so it cannot be compared"
        ),
        "rules.cell.unnameable": "not recorded in a run, so it cannot be compared",
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
        # Counts and never a path: the withheld branch of `artifact_lines` drops
        # the table because a list of paths describes a customer, and a clause
        # naming one would put back what that branch removes.
        "artifacts.pinned.marker": "declared not to change",
        "artifacts.pinned.one": "1 of them was declared not to change.",
        "artifacts.pinned.many": "{count} of them were declared not to change.",
        "artifacts.pinned.unchecked.one": (
            "1 file declared not to change is not included, so whether it "
            "changed was not checked."
        ),
        "artifacts.pinned.unchecked.many": (
            "{count} files declared not to change are not included, so whether "
            "they changed was not checked."
        ),
        # ADR 0051's three, as the headline gives them. "In this run" where the
        # headline says "here": a document is read apart from the command that
        # printed it, and "here" would point at the page.
        "artifacts.pinned.unreferenced.one": (
            "1 file declared not to change has no reference to compare with, so "
            "whether it changed was not checked."
        ),
        "artifacts.pinned.unreferenced.many": (
            "{count} files declared not to change have no reference to compare "
            "with, so whether they changed was not checked."
        ),
        "artifacts.pinned.withdrawn.one": (
            "1 file the reference declared not to change is not declared so in "
            "this run."
        ),
        "artifacts.pinned.withdrawn.many": (
            "{count} files the reference declared not to change are not declared "
            "so in this run."
        ),
        "artifacts.pinned.lost": (
            "A file the reference declared not to change is gone, and a file "
            "declared not to change in this run has no reference, so whether one "
            "became the other could not be judged."
        ),
        # Beside a file's line on the terminal, as `artifacts.pinned.marker` is.
        "artifacts.pinned.marker.unreferenced": (
            "declared not to change, no reference to compare with"
        ),
        "artifacts.pinned.marker.withdrawn": "was declared not to change",
        # Beside a module's name on the terminal, in the form of the pin markers.
        # (ADR 0052, decision 2)
        "modules_unchecked.marker": "already loaded, not read from source",
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
        # The denominator as a sentence, beside every figure computed over one
        # and never as a column of zeros: "43 of 50 cases counted; 7 could not
        # be judged" rather than a bare 0.860000. Every exclusion is named, the
        # ones a suite declares on purpose too, so the two numbers always add
        # up; a figure that left nothing out says so in four words where there
        # is a cell to fill, and says nothing inside a sentence.
        "denominator.whole.none": "No case to count.",
        "denominator.whole.one": "The only case was counted.",
        "denominator.whole.many": "All {seen} cases counted.",
        "denominator.partial.one": "{considered} of 1 case counted; {excluded}.",
        "denominator.partial.many": (
            "{considered} of {seen} cases counted; {excluded}."
        ),
        "denominator.errored_excluded.one": "1 could not be judged",
        "denominator.errored_excluded.many": "{count} could not be judged",
        "denominator.suspended_excluded.one": "1 suspended",
        "denominator.suspended_excluded.many": "{count} suspended",
        "denominator.unlabelled_excluded.one": "1 without a label",
        "denominator.unlabelled_excluded.many": "{count} without a label",
        "denominator.canary_excluded.one": "1 canary",
        "denominator.canary_excluded.many": "{count} canaries",
        "denominator.calibration_excluded.one": "1 calibration case",
        "denominator.calibration_excluded.many": "{count} calibration cases",
        "denominator.reviewed_excluded.one": "1 reviewed answer",
        "denominator.reviewed_excluded.many": "{count} reviewed answers",
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
        "section.reviewed": "What the judge said of the reviewed answers",
        "section.incomparable": (
            "What was not compared: measured over a different number of cases"
        ),
        "section.empty": "Nothing in this section.",
        "summary.truncated": (
            "showing the first {shown} of {total}; the full list is in the report"
        ),
        "column.case": "Case",
        "column.check": "Check",
        "column.band": "Declared band",
        "calibration.inside": "inside",
        "calibration.outside": "outside",
        "column.person": "The person said",
        "reviewed.yes": "yes",
        "reviewed.no": "no",
        "reviewed.agrees": "agrees",
        "reviewed.contradicts": "contradicts the person",
        "column.detail": "What happened",
        "column.reason": "Why",
        "detail.dropped": "Score fell from {before} to {now}.",
        "detail.rose": "Score rose from {before} to {now}.",
        "detail.unchanged": "Score unchanged at {now}.",
        # No verb of movement, and both numbers: "rose", "fell" and "moved
        # within" are each a claim about one measurement taken twice, which
        # this is not. (the delta-pass over 0.15.1)
        "detail.incomparable": (
            "Measured over {considered} cases here and {reference_considered} "
            "in the reference, so {before} and {now} are not a movement of one "
            "another."
        ),
        "noise.interval": "{low}–{high} across {count} samples",
        # A floor from the mean, printed with what it was computed from: a
        # declared width cannot be checked by eye otherwise. (ADR 0050)
        "noise.mean": (
            "{low}–{high}, {width} standard errors of the movement either side "
            "of the reference's score: standard deviation {sd} over {count} "
            "judged samples ({values}), a standard error of the mean of "
            "{mean_se}, and √2 times that, {movement_se}, for the movement"
        ),
        # The same, where a sample the suite asked for never voted: the count
        # asked for beside the judged one, so the floor says what it rests on.
        # (#656)
        "noise.mean.asked": (
            "{low}–{high}, {width} standard errors of the movement either side "
            "of the reference's score: standard deviation {sd} over {count} "
            "judged samples of the {asked} asked for ({values}), a standard "
            "error of the mean of {mean_se}, and √2 times that, {movement_se}, "
            "for the movement"
        ),
        # What `promote` says, one line per check, where a check met its
        # agreement with a sample that never voted. It does not refuse:
        # `min_agreement` is the suite author's declaration of how many samples
        # are enough. (#656)
        "promote.unjudged_samples": (
            "{case} · {check}: {judged} of {asked} samples were judged, so the "
            "reference rests on fewer samples than the suite asked for"
        ),
        "detail.within_noise": (
            "Score moved from {before} to {now} — inside the range of the "
            "reference's individual samples ({noise}); not counted as a "
            "regression."
        ),
        "detail.within_noise.mean": (
            "Score moved from {before} to {now} — inside the reference's "
            "noise floor ({noise}); not counted as a regression."
        ),
        "detail.dropped.beyond_noise": (
            "Score fell from {before} to {now} — outside the range of the "
            "reference's individual samples ({noise})."
        ),
        "detail.dropped.beyond_noise.mean": (
            "Score fell from {before} to {now} — outside the reference's "
            "noise floor ({noise})."
        ),
        "detail.rose.beyond_noise": (
            "Score rose from {before} to {now} — outside the range of the "
            "reference's individual samples ({noise})."
        ),
        "detail.rose.beyond_noise.mean": (
            "Score rose from {before} to {now} — outside the reference's "
            "noise floor ({noise})."
        ),
        "detail.flipped.worse": "Went from passing to failing ({before} → {now}).",
        "detail.flipped.better": "Went from failing to passing ({before} → {now}).",
        "detail.threshold_moved": (
            " The bar moved from {before_threshold} to {now_threshold}, so this is "
            "a change of rule rather than of behaviour."
        ),
        # Where the score moved beyond the check's tolerance as well, the sentence
        # above would say the behaviour did not change, and it did: both are
        # named, and neither is said to exclude the other. (#642)
        "detail.threshold_moved.score_moved": (
            " The bar moved from {before_threshold} to {now_threshold}, and the "
            "score moved beyond the check's tolerance too, so both the rule and "
            "the behaviour changed."
        ),
        "detail.new": "Checked here, not present in the reference.",
        # A reviewed answer's failing row, in pytest: the contradiction, which
        # is what fails it, and not the movement. (ADR 0059 §1)
        "detail.reviewed.passed_no": "{check} passed where the person said no.",
        "detail.reviewed.failed_yes": "{check} failed where the person said yes.",
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
        # Said after `reason.unavailable` on an errored case, where the reason
        # that says what failed was removed: digline's own word for the kind of
        # error, which crosses where the sentence does not. (#425)
        "reason.error_kind.raised": (
            "The case could not be measured: the code that asks the system "
            "under test, or the code that reads its answer, raised an error."
        ),
        "reason.error_kind.shape": (
            "The case could not be measured: the code that asks the system "
            "under test returned something that is not an answer."
        ),
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
        "view.nav.where": "Where you are",
        "view.title.where_tenant": "Where you are — tenant {tenant}",
        "view.where.tenant_label": "tenant {tenant}",
        "view.where.nothing_recorded.tenant": (
            "digline holds no recording of tenant {tenant}. Record what the "
            "application asks the model, from its own language, and the calls "
            "become the material a suite is made of."
        ),
        "view.where.unassigned.declare": (
            "First declare where the suite's captured cases go, a [capture] "
            "table or capture=: the import refuses --from _unassigned for a "
            "suite that declares none."
        ),
        "view.where.suites": "The suites tenant {tenant} holds",
        "view.where.suite_found": "{suite}: {recordings} recording(s), {runs} run(s)",
        "view.title.where": "Where you are — {suite}",
        "view.where.idle_checks": "Checks that judge no case: {checks}",
        "view.where.command": "The command",
        "view.where.docs": "The page that says more",
        "view.where.open": "Open it here",
        "view.where.language": "Recording, in the language of the application",
        "view.where.lines": "Three lines from {page}, as they stand there.",
        "view.where.shapes": "The recordings, by the shape of their output",
        "view.where.never": "no import yet",
        "view.where.nothing_recorded.title": "Nothing recorded yet",
        "view.where.nothing_recorded.say": (
            "digline holds no recording of tenant {tenant}, and this suite has "
            "never run. Record what the application asks the model, from its own "
            "language, and the calls become the material a suite is made of."
        ),
        "view.where.recording_off.title": "Recording is off",
        "view.where.recording_off.say": (
            "The switch of tenant {tenant} says off, and the {count} recording(s) "
            "it holds have all been through an import. Switch it on to keep the "
            "calls the application makes from now on."
        ),
        "view.where.unassigned.title": "{count} call(s) named no suite",
        "view.where.unassigned.say": (
            "Every recording of tenant {tenant} was made by a call that named no "
            "suite, so no suite reads it. Name the suite where the call is made, "
            "or list these calls as a suite's with --from _unassigned."
        ),
        "view.where.no_suite_yet.title": (
            "{count} recording(s) in {suite}, no suite yet"
        ),
        "view.where.no_suite_yet.say": (
            "The recordings name suite {suite}, and no suite declares where its "
            "captured cases go, so nothing reads them as cases. Write the suite "
            "with a capture declaration, or let an agent propose one by "
            "digline's method."
        ),
        "view.where.to_import.title": "{count} since the last import",
        "view.where.to_import.say": (
            "Suite {suite} has {count} recording(s) no import has read yet. List "
            "them, and name the answers you would say yes or no to."
        ),
        "view.where.never_run.title": "The suite has never run",
        "view.where.never_run.say": (
            "Suite {suite} holds {count} reviewed answer(s) and no run. Run it "
            "to read what its checks say: this page shows the command and never "
            "runs it."
        ),
        "view.where.judge_disagrees.title": (
            "The judge disagrees with a person on {count}"
        ),
        "view.where.judge_disagrees.say": (
            "The newest run has {count} reviewed answer(s) the judge contradicted "
            "or calibration case(s) outside their band. Read them before any "
            "other number: a person's yes or no is the expected verdict."
        ),
        "view.where.green_without_red.title": "Green without a red",
        "view.where.green_without_red.say": (
            "The newest run exits 0, and no run of suite {suite} has ever failed "
            "a check. A suite that cannot fail measures nothing: add a case it "
            "must fail on."
        ),
        "view.where.new_setup.title": "{count} answer(s) from a new setup",
        "view.where.new_setup.say": (
            "The setup in force first answered after the newest run, and {count} "
            "of its answers are to cases an earlier setup answered too. Read them "
            "side by side before the suite runs again."
        ),
        "view.where.nothing_to_do.title": "Nothing to do",
        "view.where.nothing_to_do.say": (
            "{count} case(s), the newest run exits 0, and the last import read "
            "the recordings up to {last_import}. Come back when the application "
            "changes."
        ),
        "view.where.last_run_red.title": "The newest run exits {exit_code}",
        "view.where.last_run_red.say": (
            "The newest run of suite {suite} exits {exit_code}, for a reason none "
            "of the states before this one names. digline explain says which."
        ),
        "view.nav.runs": "Runs",
        "view.nav.report": "Report",
        # The recorder's three views (ADR 0061 §1). What the host says about
        # the recordings is printed as the command prints it, in English; the
        # frame around it is the page's.
        "view.nav.recordings": "Recordings",
        "view.nav.setups": "Across setups",
        "view.nav.recorder": "Recorder",
        "view.nav.proposal": "Proposal",
        "view.title.proposal": "Proposal — {suite}",
        "view.where.no_suite_yet.proposal": (
            "digline suggest wrote a proposal for it, not adopted yet: {proposal}."
        ),
        "view.where.proposal.open": "Read the proposal",
        "view.proposal.heading": "The proposal digline suggest wrote for {suite}",
        "view.proposal.lead": (
            "A proposal, not a suite: no command of digline reads it, nothing in "
            "it is a verdict, and no answer was marked. This page reads the file "
            "and writes nothing; adopting its lines into your suite is yours."
        ),
        "view.proposal.file": "The file",
        "view.proposal.declaration": "What it declares",
        "view.proposal.notes": "What the file says beside it",
        "view.proposal.checks": "The checks, in the file's order",
        "view.proposal.key": "Key",
        "view.proposal.value": "Value",
        "view.proposal.mark": "Marked",
        "view.proposal.mark.placeholder": "a placeholder: yours to write",
        "view.proposal.mark.assistant": "from the assistant, not measured",
        "view.proposal.mark.draft": "from the assistant: a draft, yours to read",
        "view.proposal.said": "The assistant said",
        "view.proposal.counterexample": "The counterexample",
        "view.proposal.calibration": "The calibration skeleton",
        "view.proposal.unread": "Lines this page could not place, as they stand",
        "view.proposal.none": (
            "No proposal for {suite} where digline suggest writes one. This page "
            "looked in:"
        ),
        "view.proposal.invalid": "The file is there and could not be read: {error}",
        "view.proposal.commands": (
            "The command that writes one, without an assistant and with one. A "
            "model [suggest] names in the suite.toml is asked only with --assist, "
            "and --model wins over it. It is shown and never run here: what a "
            "model costs is said before its call."
        ),
        "view.proposal.overwrite": (
            "digline suggest does not overwrite a proposal: move or delete {path} "
            "first."
        ),
        "view.writes.behind": (
            "This page writes nothing: the import and the recorder's switch "
            "are served only by digline view --allow-record."
        ),
        "view.title.recordings": "Recordings — {suite}",
        "view.recordings.column.id": "Answer",
        "view.recordings.column.when": "First recorded",
        "view.recordings.column.setup": "Setup",
        "view.recordings.column.answer": "Response",
        "view.recordings.column.times": "Same answer",
        "view.recordings.column.state": "State",
        "view.recordings.whole": "show all",
        "view.recordings.earlier": "earlier",
        "view.recordings.undated": "undated",
        "view.recordings.attached": "{count} call(s) attached",
        "view.recordings.from_first_call": "case from the first call",
        "view.title.answer": "Answer {answer} — {suite}",
        "view.answer.input": "Input",
        "view.answer.response": "Response",
        "view.answer.back": "Back to the recordings",
        "view.answer.missing": (
            "{answer} is not an answer the recordings of suite {suite} hold."
        ),
        "view.title.setups": "Across setups — {suite}",
        "view.setups.lead": (
            "The answers recorded for suite {suite} in tenant {tenant}, by case "
            "and by setup, oldest first. Shown, never judged."
        ),
        "view.setups.setups": "Setups, in the order of their first answer",
        "view.setups.pick": "Side by side",
        "view.setups.and": "and",
        "view.setups.go": "Show",
        "view.setups.side": "A {a}, B {b}",
        "view.setups.keys": "Keys the two setups differ on ({same} the same)",
        "view.setups.keys.none": "The two setups hold the same {same} keys.",
        "view.setups.absent": "not in {side}",
        "view.setups.chars": "{chars} characters",
        "view.setups.messages.one": "{count} message",
        "view.setups.messages.many": "{count} messages",
        "view.setups.episode": "model calls per episode: {calls} · models: {models}",
        "view.setups.unrecorded": "not recorded",
        "view.setups.case": "Case {case_id} · {kind}",
        "view.setups.digest": (
            "setup {digest}: shown by its first 8 characters, as digline record "
            "compare prints it; the cases file holds it whole"
        ),
        "view.setups.over_time": "this case alone, over time",
        "view.setups.every_case": "every case",
        "view.setups.column.when": "Recorded",
        "view.setups.column.setup": "Setup",
        "view.setups.column.digest": "Digest",
        "view.setups.column.answer": "Answer",
        "view.setups.column.times": "Times",
        "view.setups.through": "through {last}",
        "view.setups.nothing": "nothing recorded",
        "view.setups.chart": (
            "The length of each recorded answer, in characters, by setup, over "
            "time. The same answer recorded again is a point at the same height; "
            "the table says what each answer was."
        ),
        "view.setups.chart.label": "characters",
        "view.setups.empty": "Nothing recorded for suite {suite} in tenant {tenant}.",
        "view.setups.only": "Only: {filters}",
        "view.not_shown.orphans": "orphans",
        "view.not_shown.detached": "calls whose episode is not among the files",
        "view.not_shown.interrupted": "interrupted episodes",
        "view.not_shown.oversize": "over the ceiling of a recording",
        "view.not_shown.unreadable": "files that are not readable recordings",
        "view.not_shown.undated": "with no recorded_at",
        "view.not_shown": "Not shown",
        "view.title.recorder": "Recorder — {tenant}",
        "view.recorder.size": "Recordings, as written",
        "view.recorder.size.note": "bytes; disk use is higher",
        "view.recorder.ceiling": "Ceiling",
        "view.recorder.ceiling.none": "none read",
        "view.recorder.held": "Recordings held",
        "view.recorder.held.note": "calls {calls} · episodes {episodes}",
        "view.recorder.to_import": "To import",
        "view.recorder.to_import.since": "suite {suite}, since the last import",
        "view.recorder.to_import.never": "suite {suite}, never imported: all of them",
        "view.recorder.not_read": "not read",
        "view.recorder.not_read.note": (
            "read for a suite whose capture file is declared"
        ),
        "view.recorder.state.absent": "no switch file",
        "view.recorder.state.invalid": "switch file invalid",
        "view.recorder.state.on": "recording on",
        "view.recorder.state.off": "recording off",
        "view.recorder.switch": "Switch",
        "view.recorder.writes_to": "Writes to",
        "view.recorder.values": "Values",
        "view.recorder.default": "default",
        "view.recorder.declared": "declared",
        "view.recorder.refused": "Refused",
        "view.recorder.absent": (
            "Without a file, an application records only with DIGLINE_RECORD=1, "
            "and only in development."
        ),
        "view.recorder.stopped": "The recorder stopped at the ceiling.",
        "view.recorder.unreadable": "{count} file(s) that are not recordings",
        # `digline record status`'s sentence, with the suite it is printed
        # under (ADR 0058, 2026-11-05).
        "view.recorder.from_gate": (
            "suite {suite}: {count} from gate runs, kept apart: not listed, "
            "imported or compared"
        ),
        "view.recorder.uncounted": (
            "Not counted: {count} process(es) keep recordings and no counts, so "
            "what was not recorded there is not known."
        ),
        "view.recorder.column.suite": "Suite",
        "view.recorder.column.calls": "Calls",
        "view.recorder.column.inside": "In an episode",
        "view.recorder.column.orphans": "Orphans",
        "view.recorder.column.episodes": "Episodes",
        "view.recorder.column.interrupted": "Interrupted",
        "view.recorder.column.since": "Since the last import",
        "view.recorder.column.not_recorded": "Not recorded",
        "view.recorder.never": "never imported, {count} in all",
        "view.recorder.no_suite": "No suite has recordings in this tenant.",
        # The two writes (ADR 0061 §2). A flag is not translated: it is what the
        # command takes, and the line under the button carries it.
        "view.recordings.column.elect": "Name it",
        "view.import.by": "Your name, the mark each case carries (--by)",
        "view.import.button": "Write the answers named",
        "view.command.note": (
            "The command that does what the button does. It follows the form as "
            "you fill it in where the page's script runs, and otherwise shows the "
            "form as it was served."
        ),
        "view.switch.title": "Switch the recorder",
        "view.switch.on": "Switch on",
        "view.switch.off": "Switch off",
        "view.switch.production": "production (--production)",
        "view.switch.sample": "sample (--sample)",
        "view.switch.redact": "redact (--redact)",
        "view.switch.ceiling": "ceiling, bytes (--ceiling)",
        "view.switch.interval": "interval, seconds (--interval)",
        "view.write.refused": "Nothing was written. {why}",
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
        "view.chip.crossing": "artifact held",
        "view.promote.crossing": (
            "A file this suite declares may not leave the perimeter, and a "
            "baseline carries every artifact's text into baselines/, which is "
            "versioned. Change the suite before promoting."
        ),
        "view.chip.nothing_judged": "nothing judged",
        "view.promote.nothing_judged": (
            "This run judged none of the cases its suite measures: it measured "
            "nothing, so it cannot become a baseline."
        ),
        "view.chip.unmeasured": "not measured",
        "view.promote.unmeasured": (
            "What this run measured cannot be stated: a check does not reconcile "
            "with its suite, or a run-level check could not be computed. An error "
            "is not a reference."
        ),
        "view.chip.uncalibrated": "scale lost",
        "view.promote.uncalibrated": (
            "A calibration case fell outside its declared band, so the judge lost "
            "its scale in this run and it cannot become a baseline. Promote a run "
            "whose calibration held."
        ),
        "view.chip.contradicted": "contradicts a person",
        "view.promote.contradicted": (
            "The judge contradicted a person's yes or no on a reviewed answer, "
            "and the person's answer is the expected verdict, so this run cannot "
            "become a baseline. Promote a run whose judge agreed with every person."
        ),
        "view.chip.pinned": "pin moved",
        "view.promote.pinned": (
            "A file declared not to change moved, or lost its path, since the "
            "baseline. This page carries no authorisation: compare the run, and "
            "if the change was meant, promote it from the command line, naming "
            "each path with --accepting-pin."
        ),
        "view.chip.refused": "refused",
        "view.promote.unnamed": (
            "The store would refuse to promote this run, for a reason this page "
            "has no marker for yet: digline promote names it."
        ),
        "view.chip.replayed": "replay",
        "view.promote.replayed": (
            "This run judged again the recorded answers of {run_key}, and never "
            "asked the target, so it cannot become a baseline: its interval is "
            "the judge's wobble alone. Promote a run that measured."
        ),
        # The header marker, and the only line in the product that has to teach
        # `--allow-promote`. The flag itself is not localised, for the reason an
        # ISO date is not: the sentence around it is the document, the eight
        # characters are the product. (ADR 0032 §2)
        "view.read_only": "read-only — restart with --allow-promote to promote",
        "view.read_only.why": (
            "This server does not promote: no button on any row, and "
            "POST /promote is not a route on it. Stop it and start "
            "digline view --allow-promote to enable promotion for every run in "
            "the store, for as long as the server is up."
        ),
        "view.action.compare": "Compare",
        "view.action.compare.title": "compare this run with the baseline",
        "view.action.open": "Open",
        "view.action.open.title": (
            "this run on its own: there is no baseline to compare it with yet"
        ),
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
        # What a list of runs left out (`digline.host.left_out`, #339). True
        # beside a list and beside one case's history alike.
        "left_out.ignored": "ignored: {parts}",
        "left_out.schema": "{count} run(s) at schema {version}",
        "left_out.unreadable": "{count} unreadable file(s)",
        "left_out.migrate": "run `digline migrate` to bring them up to date",
        "left_out.upgrade": "upgrade digline to read the newer ones",
        "left_out.refused": "refused: {count} run(s): {keys}",
        "left_out.more": "and {count} more",
        "left_out.unnamed": (
            "left out without a name: {count} file(s) whose name is not a run key"
        ),
        "left_out.misfiled": (
            "left out for their name: {count} file(s) whose name is not their run's key"
        ),
        "left_out.baseline_refused": "the baseline could not be read: {why}",
        "left_out.baseline_missing": (
            "the run the baseline was promoted from, {run_key}, is not among the "
            "runs read"
        ),
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
        "view.promote.refused": "Refused: {why}",
        # The runs page when its list cannot be drawn: the baseline, read from
        # the store on its own, still has to reach a person who has just
        # promoted, whom the 303 brings here (friction 59).
        "view.list.unavailable": "The list of runs could not be drawn: {why}",
        "view.baseline.promoted": (
            "The baseline is {run_key}, promoted at {promoted_at}."
        ),
        "view.baseline.is": "The baseline is {run_key}.",
        "view.baseline.none": "This suite has no baseline yet.",
        "view.baseline.unreadable": "The baseline could not be read either: {why}",
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
        "explain.tally.unjudged.of.one": (
            "{judged} of {total} cases judged, 1 could not be."
        ),
        "explain.tally.unjudged.of.many": (
            "{judged} of {total} cases judged, {count} could not be."
        ),
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
        "judged.floor": (
            "; measured on recorded answers, which are not a sample of what a "
            "live run produces, so this is a lower bound on the judge's range "
            "in production"
        ),
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
        "explain.tally.unreconciled.one": (
            "1 check does not reconcile with what the suite asked. This is not "
            "a regression: what the run measured is not known. It is named "
            "below, among the checks that could not be judged."
        ),
        "explain.tally.unreconciled.many": (
            "{count} checks do not reconcile with what the suite asked. This is "
            "not a regression: what the run measured is not known. They are "
            "named below, among the checks that could not be judged."
        ),
        "explain.tally.reference_unreconciled.one": (
            "1 check of the reference does not reconcile with what its suite "
            "asked. What the reference measured is not known, and this "
            "comparison is made against it."
        ),
        "explain.tally.reference_unreconciled.many": (
            "{count} checks of the reference do not reconcile with what its "
            "suite asked. What the reference measured is not known, and this "
            "comparison is made against it."
        ),
        "explain.tally.misnamed.one": (
            "1 check returned a verdict under a name that is not its "
            "assertion's, and it was refused. The assertion is at fault, not "
            "the system under test. It is named below, among the checks that "
            "could not be judged."
        ),
        "explain.tally.misnamed.many": (
            "{count} checks returned a verdict under a name that is not their "
            "assertion's, and they were refused. The assertion is at fault, not "
            "the system under test. They are named below, among the checks "
            "that could not be judged."
        ),
        "explain.tally.calibration.one": (
            "1 calibration case scored outside its declared band: {cases}. The "
            "judged scores in this run are not placed on the scale they are "
            "compared on. It is counted in no aggregate, and the target was not "
            "asked for it."
        ),
        "explain.tally.calibration.many": (
            "{count} calibration cases scored outside their declared bands: "
            "{cases}. The judged scores in this run are not placed on the scale "
            "they are compared on. They are counted in no aggregate, and the "
            "target was not asked for them."
        ),
        # The report's section, in a clause: the case, the check, the score,
        # and which side of which band. (ADR 0024 §4.5)
        "explain.tally.calibration.case": (
            "{case} for {check} at {score}, {side} {low}–{high}"
        ),
        "explain.side.above": "above",
        "explain.side.below": "below",
        "explain.tally.reviewed.one": (
            "{said}, and the case fails: {cases}. It is counted in no "
            "aggregate, and the target was not asked for it."
        ),
        "explain.tally.reviewed.many": (
            "{said}, and each fails: {cases}. They are counted in no "
            "aggregate, and the target was not asked for them."
        ),
        "explain.tally.reviewed.passed_no": (
            "{case} for {check}, passed where the person said no"
        ),
        "explain.tally.reviewed.failed_yes": (
            "{case} for {check}, failed where the person said yes"
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
        # `{name}` is a configuration field, and outside `OBSERVED_FIELDS` it
        # is what this run **sent**. "Answered with" made an execution claim
        # out of it — the one ADR 0020 §3 row 7 forbids, since a sent id says
        # what was asked for and not what answered. The `.observed` variants
        # carry the fields a provider reported, where "reported" is the verb
        # `config.change.*.observed` already uses for the same reason.
        "explain.setting.target.changed": (
            "The system under test was configured with {name} {after}; the "
            "reference with {before}."
        ),
        "explain.setting.target.changed.observed": (
            "The system under test reported {name} {after}; the reference "
            "reported {before}."
        ),
        # `.recorded`: the name is a token, so whether it was sent or reported
        # cannot be told, and "recorded" is true of both. (#275)
        "explain.setting.target.changed.recorded": (
            "The system under test recorded {name} {after}; the reference "
            "recorded {before}."
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
            "The judge was configured with {name} {after}; the reference's "
            "judge with {before}."
        ),
        "explain.setting.judge.changed.observed": (
            "The judge reported {name} {after}; the reference's judge "
            "reported {before}."
        ),
        "explain.setting.judge.changed.recorded": (
            "The judge recorded {name} {after}; the reference's judge "
            "recorded {before}."
        ),
        "explain.setting.judge.new": (
            "The judge recorded {name} {after}, which the reference did not record."
        ),
        "explain.setting.judge.missing": (
            "The reference's judge recorded {name} {before}; this run recorded none."
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
        # The rules that moved, beside the things under test. ADR 0028 §4: the
        # direction is in the sentence, because a reader who is shown
        # `0.6 -> 0.5` and no verb has been shown a number and not a fact.
        "explain.setting.rule.changed.loosened": (
            "{name} moved from {before} to {after}, which is a looser bar than "
            "the reference was approved under."
        ),
        "explain.setting.rule.changed.tightened": (
            "{name} moved from {before} to {after}, which is a stricter bar "
            "than the reference was approved under."
        ),
        # No verb, for a rule whose movement has no direction: `samples` on a
        # run-level aggregate, whose floor is outside ADR 0050. A case's
        # `samples` and the floor's width take `.tightened` or `.loosened`
        # above. (ADR 0028 §4, as amended 2026-10-15; ADR 0050, the passenger
        # rule, amended 2026-10-21)
        "explain.setting.rule.changed": "{name} moved from {before} to {after}.",
        "explain.setting.rule.new.tightened": (
            "{name} is a check this run was held to and the reference was not."
        ),
        "explain.setting.rule.new.new_group": (
            "{name} gates a group the reference did not have. The aggregate was "
            "already gated per group, so a case was labelled rather than a rule "
            "rewritten."
        ),
        "explain.setting.rule.new.now_grouped": (
            "{name} is here because this aggregate is now gated per group, "
            "which the reference was not."
        ),
        "explain.setting.rule.missing.loosened": (
            "{name} no longer applies; the reference was held to it."
        ),
        "explain.setting.rule.unknown": (
            "Whether {name} changed is not known: one side did not record it."
        ),
        "explain.setting.rule.unnameable": (
            "The agreement floor is not recorded in a run, so whether it moved "
            "cannot be told from these two."
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
            "The system under test was configured with {name} {after}."
        ),
        "explain.setting.target.alone.observed": (
            "The system under test reported {name} {after}."
        ),
        "explain.setting.judge.alone": (
            "The judge was configured with {name} {after}."
        ),
        "explain.setting.judge.alone.observed": ("The judge reported {name} {after}."),
        "explain.setting.target.alone.recorded": (
            "The system under test recorded {name} {after}."
        ),
        "explain.setting.judge.alone.recorded": ("The judge recorded {name} {after}."),
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
        # The line the tally above it was contradicting: this one says the
        # same thing about the same check, so a reader is not asked to decide
        # which of two sentences to believe. (the delta-pass over 0.15.1)
        "explain.check.incomparable": (
            "{where}: measured over {considered} cases here and "
            "{reference_considered} in the reference, so {before} and {now} "
            "are not a movement of one another."
        ),
        "explain.check.unchanged": (
            "{where} moved from {before} to {now}, inside the tolerance the "
            "suite declares."
        ),
        "explain.check.within_noise": (
            "{where} moved from {before} to {now}, inside the interval its "
            "reference measured."
        ),
        "explain.check.within_noise.mean": (
            "{where} moved from {before} to {now}, inside the noise floor "
            "its reference's samples give, {noise}."
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
        "explain.check.contradicted.no": (
            "{where} passed at {now}, and a person said no to the answer: the "
            "judge contradicts the person, and the case fails."
        ),
        "explain.check.contradicted.yes": (
            "{where} failed at {now}, and a person said yes to the answer: the "
            "judge contradicts the person, and the case fails."
        ),
        "explain.check.contradicted.steps": (
            "{where} failed at {now}, and a person said yes to the turn: its "
            "steps contradict the person, and the case fails."
        ),
        "explain.check.suspended": (
            "The case {case} was set aside, so nothing was measured on it. The "
            "stated reason is not carried here."
        ),
        "explain.where.run": "the whole run",
        "explain.bar": " The bar is {threshold}.",
        "explain.noise.beyond": (
            " That is outside the interval its reference measured, {noise}."
        ),
        "explain.noise.beyond.mean": (
            " That is outside the noise floor its reference's samples give, {noise}."
        ),
        "explain.nothing": "Nothing in this group.",
        # `digline log` (ADR 0020). The multi-run vocabulary is this reading's
        # whole subject, so it is allowed here; advice is not, and neither is
        # "likely", which belongs to the canary.
        "log.heading": (
            "tenant {tenant} · {suite} · {count} run(s) read in this store, "
            "{first} to {last}"
        ),
        "log.empty": (
            "tenant {tenant} · {suite} · no run read in this store, in this window."
        ),
        "log.window": "Window: {since} to {until}.",
        "log.window.open": "…",
        "log.not_read.schema": "{count} run(s) at schema {version} were not read.",
        "log.not_read.unreadable": "{count} file(s) could not be read.",
        # A run the scan passed and the store refused. `digline list` names
        # each one and why; this reading only counts them. (#314)
        "log.not_read.refused": (
            "{count} run(s) were refused by the store and not read: "
            "`digline list` names them."
        ),
        # A run the baseline or the register names, and the scan did not read:
        # absent or unreadable, never said to be removed. Only said where one
        # of the two records it — a run neither names leaves no trace. (#287)
        "log.not_read.on_record": (
            "{count} run(s) named by the baseline or the register were not read "
            "here: {before} before the first run read, {after} after the last."
        ),
        "log.not_read.on_record.none_read": (
            "{count} run(s) named by the baseline or the register were not read here."
        ),
        "log.span.unread": "; {count} run(s) on record inside it were not read",
        "log.roll.unread": (
            "{count} run(s) on record between them were not read, so what they "
            "recorded is not known."
        ),
        "log.side.target": "Target",
        "log.side.judge": "Judge",
        "log.span": "  {sighting} — {first} to {last}, {runs} run(s){environments}",
        "log.environments": " ({environments})",
        # `reported as`, never `answered as`. `resolved_model` is in
        # `OBSERVED_FIELDS` — what a provider **reported** rather than what
        # the target **sent** — and `config.change.*.observed` has said
        # "reported" about that same field since ADR 0005 §9. This surface
        # said "answered" about it, so one field had two verbs in two
        # renderings. An id that differs from the one we sent is more than
        # an echo and still only what the provider told us.
        "log.sighting.answered": "{who}, reported as {answered}",
        "log.sighting.absent": "{who}: {absence}",
        "log.absence.declared_nothing": "declared no configuration",
        "log.absence.several_judges": "several judges; no single answering model",
        # Row 8: names no token. A token tells a terminal's reader nothing, and
        # two printed side by side invite matching them by eye. (ADR 0020 §3,
        # amended 2026-10-03)
        "log.absence.projected": (
            "the configuration is projected, so who was asked and what answered "
            "are tokens that only the name table can read"
        ),
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
            "{side}: {sent} reported {before} last at {last_before}, and "
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
        # The spread: how much the suite moved between runs (ADR 0024 §7).
        # *Across* and *runs* are multi-run words, which this reading alone is
        # permitted. No advice word, and no *likely*.
        "log.spread.heading": "Run-to-run spread",
        "log.spread.none": (
            "  This suite declares no run-level check, so there is nothing to "
            "read across runs."
        ),
        # Read off the runs, so with none it says that and stops. The sentence
        # above is a claim about the *suite*, and against an empty store it was
        # false — `scout-judge` declares four run-level checks and the reading
        # said it declared none. (ADR 0024 §7.1)
        "log.spread.no_runs": (
            "  No run was read in this store, in this window, so there is "
            "nothing to read across runs. Whether this suite declares a "
            "run-level check is not something this reading can say: it reads "
            "the runs, and there are none."
        ),
        # The other two causes, and neither is a statement about the suite.
        # "Silent on a flip" is *do not report a range*, not print nothing:
        # naming the flip is not printing an interval.
        # (ADR 0024 §7.5, amended 2026-09-22)
        "log.spread.flipped": (
            "  {count} run-level check(s) changed status against the "
            "reference, so no range is read for them: a changed status carries "
            "no interval."
        ),
        "log.spread.scoreless": (
            "  {count} run-level check(s) recorded no score, so there is no "
            "range to read for them."
        ),
        # A flip that cannot be ruled out carries no interval either: the
        # reference names its checks by tokens. (ADR 0024 §7.5, amended
        # 2026-10-03)
        "log.spread.projected": (
            "  The reference is projected, so its run-level checks are named by "
            "tokens and cannot be paired with these {count}. Whether one "
            "changed status against it is not known, so no range is read for "
            "them: a changed status carries no interval."
        ),
        "log.spread.set": (
            "  Across {count} comparable run(s) in this store, in this window — "
            "the latest not among them{excluded}."
        ),
        # The verb is carried **once, by the clause**, and every reason after
        # it is a bare counted phrase. It used to sit on `rejudged` alone, so a
        # reading whose exclusions began with any other reason ended in a
        # verbless fragment — "; 3 as not fully judged." — which is what
        # scout's store printed. (ADR 0024 §7.4, amended 2026-09-22)
        "log.spread.excluded": "; excluded: {excluded}",
        "log.spread.excluded.rejudged": "{count} re-judged",
        "log.spread.excluded.unjudged": "{count} not fully judged",
        "log.spread.excluded.scale_lost": "{count} uncalibrated",
        "log.spread.excluded.config_hash": "{count} measuring other rules",
        "log.spread.excluded.population": "{count} counting other cases",
        "log.spread.excluded.artifacts": "{count} testing another prompt",
        "log.spread.excluded.target_config": "{count} asking another system",
        "log.spread.excluded.judge_config": ("{count} grading with another instrument"),
        "log.spread.excluded.config_unrecorded": (
            "{count} where only one of the two runs recorded its configuration"
        ),
        "log.spread.excluded.identity": ("{count} where another model was reported"),
        "log.spread.unidentified": (
            "  {count} of the {total} run(s) did not identify the answering model."
        ),
        "log.spread.commits": "  The counted runs were written at {count} commit(s).",
        "log.spread.versions": "  Written by digline {versions}.",
        "log.spread.range": (
            "  {name}: the latest run scored {latest} against the reference's "
            "{reference}, a difference of {difference}. {name} ranged {low} to "
            "{high} across the counted runs."
        ),
        "log.spread.range.alone": (
            "  {name}: the latest run scored {latest}. {name} ranged {low} to "
            "{high} across the counted runs."
        ),
        "log.spread.no_comparable": (
            "  {name}: no run in this store was measured the same way, so there "
            "is no range to read."
        ),
        "log.spread.within": (
            "    Within the latest run, the same aggregate per sample ranged "
            "{low} to {high} — a different measurement, not comparable with the "
            "range above."
        ),
        # Withheld because the statistic cannot carry it, never pending a
        # number: a min-max range is monotone in N, so it cannot converge and
        # falling outside it names a value not seen before. The sentence says
        # what the range is instead of what it lacks.
        # (ADR 0024 §7.4, amended 2026-09-22)
        "log.spread.floor": (
            "  Whether the latest score is inside this spread is not stated: a "
            "range describes the runs it read and cannot carry that clause. A "
            "value under the low or over the high widens the range, so falling "
            "outside it names a score not seen before, not a change."
        ),
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
        "header.projected": "Nomi sostituiti",
        "header.projected.value": (
            "I nomi in questo rapporto (di casi, controlli, gruppi, file, "
            "parametri di configurazione e loro valori testuali, e del giudice) "
            "sono sostituiti da stringhe di 22 caratteri. Numeri, esiti e date "
            "sono come misurati. I nomi sono conservati dal titolare dei dati, "
            "e solo lì una stringa può tornare al nome che rappresenta: per "
            "conoscerne uno, va chiesto al titolare dei dati."
        ),
        "header.promoted": "Riferimento approvato",
        "header.baseline_key": "Chiave del riferimento",
        "summary.against": "tenant {tenant}, rispetto alla baseline {reference}",
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
        "fact.unpaired.one": (
            "1 controllo non è stato confrontato, perché il riferimento e questa "
            "esecuzione hanno un controllo diverso sotto il suo nome: {pairs}. "
            "Se sia stato modificato o sostituito, i due documenti non possono "
            "dirlo."
        ),
        "fact.unpaired.many": (
            "{count} controlli non sono stati confrontati, perché il riferimento "
            "e questa esecuzione hanno un controllo diverso sotto ciascun nome: "
            "{pairs}. Se ciascuno sia stato modificato o sostituito, i due "
            "documenti non possono dirlo."
        ),
        "fact.unpaired.step": (
            "Se il cambiamento era voluto, rendi questa esecuzione il riferimento "
            "per confrontarli di nuovo: digline promote --suite <suite> --run "
            "{run} --replacing {reference}."
        ),
        "fact.unpaired.pair": (
            "{case} · {check}, {before} nel riferimento e {after} qui"
        ),
        "fact.unpaired.moved": ", {field} {before} → {after}",
        "fact.unpaired.field.threshold": "soglia",
        "fact.unpaired.field.tolerance": "tolleranza",
        "fact.unpaired.state.pass": "superato a {score}",
        "fact.unpaired.state.fail": "non superato a {score}",
        "fact.unpaired.state.error": "in errore a {score}",
        "fact.unpaired.state.pass.unscored": "superato senza punteggio",
        "fact.unpaired.state.fail.unscored": "non superato senza punteggio",
        "fact.unpaired.state.error.unscored": "in errore senza punteggio",
        "fact.denominator_moved.one": (
            "1 controllo di run è stato misurato su un numero di casi diverso "
            "dal riferimento: non è un confronto."
        ),
        "fact.denominator_moved.many": (
            "{count} controlli di run sono stati misurati su un numero di casi "
            "diverso dal riferimento: non sono confronti."
        ),
        "fact.noise.one": "1 controllo si è mosso entro il rumore.",
        "fact.noise.many": "{count} controlli si sono mossi entro il rumore.",
        "fact.nothing_judged": (
            "Nessuno dei casi che questa suite misura è stato giudicato: questa "
            "run non può dire se qualcosa è peggiorato."
        ),
        "fact.session_not_green": (
            "{suite}: digline esce con {code}, quindi questa sessione non "
            "finisce verde."
        ),
        "fact.row_missing.case": "la suite non dichiara più questo caso",
        "fact.row_missing.check": "la suite non dichiara più questo controllo",
        "fact.row_missing.unrecorded": (
            "l'esecuzione archiviata non ha un verdetto per questo controllo: "
            "ripeti l'esecuzione, o passa --digline-run"
        ),
        "fact.errored_checks.one": "1 controllo non ha potuto essere eseguito.",
        "fact.errored_checks.many": (
            "{count} controlli non hanno potuto essere eseguiti."
        ),
        "fact.contradicted.one": (
            "il giudice ha contraddetto una persona su 1 risposta rivista"
        ),
        "fact.contradicted.many": (
            "il giudice ha contraddetto una persona su {count} risposte riviste"
        ),
        "fact.contradicted.steps.one": (
            "un controllo sui passi ha contraddetto una persona su {answers}: {checks}"
        ),
        "fact.contradicted.steps.many": (
            "dei controlli sui passi hanno contraddetto una persona su "
            "{answers}: {checks}"
        ),
        "fact.contradicted.answers.one": "1 risposta rivista",
        "fact.contradicted.answers.many": "{count} risposte riviste",
        "fact.contradicted.step_check": "{check}, sul caso {case}",
        "fact.unjudged.none": "Tutti i casi sono stati giudicati.",
        "fact.unjudged.one": "1 caso non è stato possibile giudicarlo.",
        # A label and a colon rather than "{judged} casi giudicati": the
        # participle would have to agree with the number, and "1 casi" is the
        # sort of thing a reader stops trusting the rest of the page for.
        "fact.unjudged.of.one": (
            "Casi giudicati: {judged} su {total}; 1 non è stato possibile giudicarlo."
        ),
        "fact.unjudged.of.many": (
            "Casi giudicati: {judged} su {total}; {count} non è stato possibile "
            "giudicarli."
        ),
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
        "fact.pinned.one": ("Di questi, 1 era dichiarato immutabile, ed è cambiato."),
        "fact.pinned.many": (
            "Di questi, {count} erano dichiarati immutabili, e sono cambiati."
        ),
        "fact.pinned.unchecked.one": (
            "1 file dichiarato immutabile non è incluso qui, quindi non è "
            "stato verificato se sia cambiato."
        ),
        "fact.pinned.unchecked.many": (
            "{count} file dichiarati immutabili non sono inclusi qui, quindi "
            "non è stato verificato se siano cambiati."
        ),
        "fact.pinned.unreferenced.one": (
            "1 file dichiarato immutabile non ha un riferimento con cui "
            "confrontarlo, quindi non è stato verificato se sia cambiato."
        ),
        "fact.pinned.unreferenced.many": (
            "{count} file dichiarati immutabili non hanno un riferimento con cui "
            "confrontarli, quindi non è stato verificato se siano cambiati."
        ),
        "fact.pinned.withdrawn.one": (
            "1 file che il riferimento dichiarava immutabile qui non è dichiarato tale."
        ),
        "fact.pinned.withdrawn.many": (
            "{count} file che il riferimento dichiarava immutabili qui non sono "
            "dichiarati tali."
        ),
        "fact.pinned.lost": (
            "Un file che il riferimento dichiarava immutabile non c'è più, e un "
            "file dichiarato immutabile qui non ha un riferimento, quindi non si "
            "è potuto stabilire se l'uno sia diventato l'altro."
        ),
        "fact.modules_unchecked.one": (
            "1 modulo era già caricato altrove in questo processo, quindi non si "
            "sa se corrisponda al file su disco."
        ),
        "fact.modules_unchecked.many": (
            "{count} moduli erano già caricati altrove in questo processo, quindi "
            "non si sa se corrispondano ai file su disco."
        ),
        "fact.modules_unchecked.unrecorded": (
            "Questa esecuzione non registra la lettura da sorgente dei moduli che "
            "ha misurato, quindi non si sa se corrispondano ai file su disco."
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
        "fact.canary.beyond": (
            ", fuori dall'intervallo dei singoli campioni del riferimento ({interval})"
        ),
        "fact.canary.beyond.mean": (
            ", fuori dal pavimento di rumore del riferimento ({interval})"
        ),
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
        "fact.reviewed.one": "{said}, e il caso fallisce: {cases}.",
        "fact.reviewed.many": "{said}, e ciascuno di quei casi fallisce: {cases}.",
        "fact.unreconciled.one": (
            "L'esecuzione non torna con ciò che la suite ha chiesto, in 1 "
            "controllo: {gaps}. Non è una regressione: non si sa che cosa "
            "l'esecuzione abbia misurato."
        ),
        "fact.unreconciled.many": (
            "L'esecuzione non torna con ciò che la suite ha chiesto, in {count} "
            "controlli: {gaps}. Non è una regressione: non si sa che cosa "
            "l'esecuzione abbia misurato."
        ),
        "fact.unreconciled.capped": (
            "L'esecuzione non torna con ciò che la suite ha chiesto, in {count} "
            "controlli, fra cui {gaps}. Non è una regressione: non si sa che "
            "cosa l'esecuzione abbia misurato."
        ),
        "fact.reference_unreconciled.one": (
            "Il riferimento non torna con ciò che la sua suite ha chiesto, in 1 "
            "controllo: {gaps}. Non si sa che cosa il riferimento abbia "
            "misurato, e questo confronto è fatto contro di esso."
        ),
        "fact.reference_unreconciled.many": (
            "Il riferimento non torna con ciò che la sua suite ha chiesto, in "
            "{count} controlli: {gaps}. Non si sa che cosa il riferimento abbia "
            "misurato, e questo confronto è fatto contro di esso."
        ),
        "fact.reference_unreconciled.capped": (
            "Il riferimento non torna con ciò che la sua suite ha chiesto, in "
            "{count} controlli, fra cui {gaps}. Non si sa che cosa il "
            "riferimento abbia misurato, e questo confronto è fatto contro di esso."
        ),
        "fact.misnamed.one": (
            "1 controllo ha restituito un verdetto con un nome che non è quello "
            "della sua asserzione, ed è stato rifiutato: {gaps}. Il difetto è "
            "dell'asserzione, non del sistema sotto esame."
        ),
        "fact.misnamed.many": (
            "{count} controlli hanno restituito un verdetto con un nome che non "
            "è quello della loro asserzione, e sono stati rifiutati: {gaps}. Il "
            "difetto è dell'asserzione, non del sistema sotto esame."
        ),
        "fact.misnamed.capped": (
            "{count} controlli hanno restituito un verdetto con un nome che non "
            "è quello della loro asserzione, e sono stati rifiutati, fra cui "
            "{gaps}. Il difetto è dell'asserzione, non del sistema sotto esame."
        ),
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
        "fact.target_config.withheld.one": (
            "Il sistema in prova ha risposto con la stessa configurazione "
            "dichiarata; 1 dei suoi campi è trattenuto, quindi non si sa se sia "
            "cambiato."
        ),
        "fact.target_config.withheld.many": (
            "Il sistema in prova ha risposto con la stessa configurazione "
            "dichiarata; {count} dei suoi campi sono trattenuti, quindi non si "
            "sa se siano cambiati."
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
        "config.title": "Com'era configurato",
        "config.judge.title": "Com'era configurato il giudice",
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
        "config.change.new.recorded": (
            "{field} {after}, non registrato per il riferimento"
        ),
        "config.change.missing.recorded": "{field} {before}, non più registrato",
        "config.judge.added": "{judge} è stato aggiunto come giudice",
        "config.judge.removed": "{judge} non giudica più",
        "config.coincides": " Questo calo coincide con {changes}.",
        "rules.title": "Quali erano le regole",
        "rules.note": (
            "Solo le regole che si sono mosse. Un'asticella più bassa lascia "
            "passare un'esecuzione dove il riferimento non sarebbe passato; le "
            "regole in vigore sono nel documento dell'esecuzione."
        ),
        "rules.column.rule": "Regola",
        "rules.column.moved": "Che cosa si è mosso",
        "rules.column.direction": "In che direzione",
        "rules.cell.moved": "{field} {before} → {after}",
        "rules.cell.new": "aggiunta",
        "rules.cell.missing": "rimossa",
        "rules.cell.unknown": (
            "nessun valore unico su uno dei due lati, quindi non si sa se si sia mosso"
        ),
        "rules.cell.unknown.width": (
            "dichiarato in modo diverso dai casi di un lato o di entrambi, quindi "
            "non si sa se si sia mosso"
        ),
        "rules.direction.loosened": "più larga",
        "rules.direction.tightened": "più stretta",
        "rules.terminal": "regole",
        "rules.field.threshold": "soglia di",
        "rules.field.tolerance": "tolleranza di",
        "rules.field.samples": "campioni di",
        "rules.field.floor_standard_errors": "larghezza del pavimento di",
        "rules.moved.loosened": "{field} {name} {before} → {after} (più larga)",
        "rules.moved.tightened": "{field} {name} {before} → {after} (più stretta)",
        "rules.moved": "{field} {name} {before} → {after}",
        "rules.new": "{name} aggiunta",
        "rules.new.new_group": (
            "{name} aggiunta, su un gruppo che il riferimento non aveva"
        ),
        "rules.new.now_grouped": ("{name} aggiunta, questo aggregato ora è per gruppo"),
        "rules.missing": "{name} rimossa",
        "rules.unknown": (
            "{name} non ha un valore unico su uno dei due lati, quindi non si sa "
            "se si sia mosso"
        ),
        "rules.unknown.width": (
            "{name} è dichiarato in modo diverso dai casi di un lato o di "
            "entrambi, quindi non si sa se si sia mosso"
        ),
        "rules.unnameable": (
            "la soglia di accordo non è registrata, quindi non è confrontabile"
        ),
        "rules.cell.unnameable": (
            "non registrata in un'esecuzione, quindi non confrontabile"
        ),
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
        "artifacts.pinned.marker": "dichiarato immutabile",
        "artifacts.pinned.one": "Di questi, 1 era dichiarato immutabile.",
        "artifacts.pinned.many": "Di questi, {count} erano dichiarati immutabili.",
        "artifacts.pinned.unchecked.one": (
            "1 file dichiarato immutabile non è incluso, quindi non è "
            "stato verificato se sia cambiato."
        ),
        "artifacts.pinned.unchecked.many": (
            "{count} file dichiarati immutabili non sono inclusi, quindi non "
            "è stato verificato se siano cambiati."
        ),
        "artifacts.pinned.unreferenced.one": (
            "1 file dichiarato immutabile non ha un riferimento con cui "
            "confrontarlo, quindi non è stato verificato se sia cambiato."
        ),
        "artifacts.pinned.unreferenced.many": (
            "{count} file dichiarati immutabili non hanno un riferimento con cui "
            "confrontarli, quindi non è stato verificato se siano cambiati."
        ),
        "artifacts.pinned.withdrawn.one": (
            "1 file che il riferimento dichiarava immutabile non è dichiarato "
            "tale in questa esecuzione."
        ),
        "artifacts.pinned.withdrawn.many": (
            "{count} file che il riferimento dichiarava immutabili non sono "
            "dichiarati tali in questa esecuzione."
        ),
        "artifacts.pinned.lost": (
            "Un file che il riferimento dichiarava immutabile non c'è più, e un "
            "file dichiarato immutabile in questa esecuzione non ha un "
            "riferimento, quindi non si è potuto stabilire se l'uno sia "
            "diventato l'altro."
        ),
        "artifacts.pinned.marker.unreferenced": (
            "dichiarato immutabile, senza riferimento con cui confrontarlo"
        ),
        "artifacts.pinned.marker.withdrawn": "era dichiarato immutabile",
        "modules_unchecked.marker": "già caricato, non letto da sorgente",
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
        "denominator.whole.none": "Nessun caso da contare.",
        "denominator.whole.one": "L'unico caso è stato contato.",
        "denominator.whole.many": "Contati tutti i {seen} casi.",
        "denominator.partial.one": "Casi contati: {considered} su 1; {excluded}.",
        "denominator.partial.many": (
            "Casi contati: {considered} su {seen}; {excluded}."
        ),
        "denominator.errored_excluded.one": "1 non giudicabile",
        "denominator.errored_excluded.many": "{count} non giudicabili",
        "denominator.suspended_excluded.one": "1 sospeso",
        "denominator.suspended_excluded.many": "{count} sospesi",
        "denominator.unlabelled_excluded.one": "1 senza etichetta",
        "denominator.unlabelled_excluded.many": "{count} senza etichetta",
        "denominator.canary_excluded.one": "1 canary",
        "denominator.canary_excluded.many": "{count} canary",
        "denominator.calibration_excluded.one": "1 caso di calibrazione",
        "denominator.calibration_excluded.many": "{count} casi di calibrazione",
        "denominator.reviewed_excluded.one": "1 risposta rivista",
        "denominator.reviewed_excluded.many": "{count} risposte riviste",
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
        "section.reviewed": "Che cosa ha detto il giudice delle risposte riviste",
        "section.incomparable": (
            "Che cosa non è stato confrontato: misurato su un numero di casi diverso"
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
        "column.person": "La persona ha detto",
        "reviewed.yes": "sì",
        "reviewed.no": "no",
        "reviewed.agrees": "d'accordo",
        "reviewed.contradicts": "contraddice la persona",
        "column.detail": "Che cosa è successo",
        "column.reason": "Perché",
        "detail.dropped": "Il punteggio è sceso da {before} a {now}.",
        "detail.rose": "Il punteggio è salito da {before} a {now}.",
        "detail.unchanged": "Punteggio invariato a {now}.",
        "detail.incomparable": (
            "Misurato su {considered} casi qui e {reference_considered} nel "
            "riferimento: {before} e {now} non sono un movimento l'uno "
            "dell'altro."
        ),
        "noise.interval": "{low}–{high} su {count} campioni",
        "noise.mean": (
            "{low}–{high}, {width} errori standard del movimento attorno al "
            "punteggio del riferimento: deviazione standard {sd} su {count} "
            "campioni giudicati ({values}), un errore standard della media di "
            "{mean_se}, e √2 volte quello, {movement_se}, per il movimento"
        ),
        "noise.mean.asked": (
            "{low}–{high}, {width} errori standard del movimento attorno al "
            "punteggio del riferimento: deviazione standard {sd} su {count} "
            "campioni giudicati dei {asked} chiesti ({values}), un errore "
            "standard della media di {mean_se}, e √2 volte quello, "
            "{movement_se}, per il movimento"
        ),
        "promote.unjudged_samples": (
            "{case} · {check}: giudicati {judged} campioni su {asked}, quindi il "
            "riferimento poggia su meno campioni di quelli che la suite ha chiesto"
        ),
        "detail.within_noise": (
            "Il punteggio si è spostato da {before} a {now} — dentro "
            "l'intervallo dei singoli campioni del riferimento ({noise}); non "
            "conta come peggioramento."
        ),
        "detail.within_noise.mean": (
            "Il punteggio si è spostato da {before} a {now} — dentro il "
            "pavimento di rumore del riferimento ({noise}); non conta come "
            "peggioramento."
        ),
        "detail.dropped.beyond_noise": (
            "Il punteggio è sceso da {before} a {now} — fuori dall'intervallo "
            "dei singoli campioni del riferimento ({noise})."
        ),
        "detail.dropped.beyond_noise.mean": (
            "Il punteggio è sceso da {before} a {now} — fuori dal pavimento "
            "di rumore del riferimento ({noise})."
        ),
        "detail.rose.beyond_noise": (
            "Il punteggio è salito da {before} a {now} — fuori "
            "dall'intervallo dei singoli campioni del riferimento ({noise})."
        ),
        "detail.rose.beyond_noise.mean": (
            "Il punteggio è salito da {before} a {now} — fuori dal pavimento "
            "di rumore del riferimento ({noise})."
        ),
        "detail.flipped.worse": "Da superato a non superato ({before} → {now}).",
        "detail.flipped.better": "Da non superato a superato ({before} → {now}).",
        "detail.threshold_moved": (
            " La soglia si è spostata da {before_threshold} a {now_threshold}, "
            "quindi è un cambio di regola e non di comportamento."
        ),
        "detail.threshold_moved.score_moved": (
            " La soglia si è spostata da {before_threshold} a {now_threshold}, e "
            "anche il punteggio si è mosso oltre la tolleranza del controllo, "
            "quindi sono cambiati sia la regola sia il comportamento."
        ),
        "detail.new": "Controllato qui, assente nel riferimento.",
        "detail.reviewed.passed_no": (
            "{check} ha promosso la risposta a cui la persona ha detto no."
        ),
        "detail.reviewed.failed_yes": (
            "{check} ha bocciato la risposta a cui la persona ha detto sì."
        ),
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
        "reason.error_kind.raised": (
            "Il caso non ha potuto essere misurato: il codice che interroga il "
            "sistema in prova, o quello che ne legge la risposta, ha sollevato "
            "un errore."
        ),
        "reason.error_kind.shape": (
            "Il caso non ha potuto essere misurato: il codice che interroga il "
            "sistema in prova ha restituito qualcosa che non è una risposta."
        ),
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
        "view.nav.where": "Dove sei",
        "view.title.where_tenant": "Dove sei — tenant {tenant}",
        "view.where.tenant_label": "tenant {tenant}",
        "view.where.nothing_recorded.tenant": (
            "digline non ha registrazioni del tenant {tenant}. Registra quello "
            "che l'applicazione chiede al modello, dal suo linguaggio, e le "
            "chiamate diventano il materiale di una suite."
        ),
        "view.where.unassigned.declare": (
            "Prima dichiara dove vanno i casi catturati della suite, una tabella "
            "[capture] o capture=: l'import rifiuta --from _unassigned per una "
            "suite che non ne dichiara."
        ),
        "view.where.suites": "Le suite del tenant {tenant}",
        "view.where.suite_found": (
            "{suite}: {recordings} registrazione/i, {runs} esecuzione/i"
        ),
        "view.title.where": "Dove sei — {suite}",
        "view.where.idle_checks": "Controlli che non giudicano nessun caso: {checks}",
        "view.where.command": "Il comando",
        "view.where.docs": "La pagina che dice di più",
        "view.where.open": "Aprila qui",
        "view.where.language": "Registrare, nel linguaggio dell'applicazione",
        "view.where.lines": "Tre righe da {page}, come stanno lì.",
        "view.where.shapes": "Le registrazioni, per forma dell'output",
        "view.where.never": "nessun import ancora",
        "view.where.nothing_recorded.title": "Ancora nessuna registrazione",
        "view.where.nothing_recorded.say": (
            "digline non ha registrazioni del tenant {tenant}, e questa suite non "
            "ha mai girato. Registra quello che l'applicazione chiede al modello, "
            "dal suo linguaggio, e le chiamate diventano il materiale di una suite."
        ),
        "view.where.recording_off.title": "La registrazione è spenta",
        "view.where.recording_off.say": (
            "L'interruttore del tenant {tenant} dice spento, e le {count} "
            "registrazioni che tiene sono già passate tutte da un import. "
            "Accendilo per tenere le chiamate che l'applicazione fa da ora in poi."
        ),
        "view.where.unassigned.title": "{count} chiamata/e senza suite",
        "view.where.unassigned.say": (
            "Ogni registrazione del tenant {tenant} viene da una chiamata che non "
            "ha nominato una suite, quindi nessuna suite la legge. Nomina la suite "
            "dove la chiamata è fatta, o elenca queste chiamate come di una suite "
            "con --from _unassigned."
        ),
        "view.where.no_suite_yet.title": (
            "{count} registrazione/i in {suite}, nessuna suite ancora"
        ),
        "view.where.no_suite_yet.say": (
            "Le registrazioni nominano la suite {suite}, e nessuna suite dichiara "
            "dove vanno i suoi casi catturati, quindi niente le legge come casi. "
            "Scrivi la suite con una dichiarazione di capture, o lascia che un "
            "agente ne proponga una con il metodo di digline."
        ),
        "view.where.to_import.title": "{count} dall'ultimo import",
        "view.where.to_import.say": (
            "La suite {suite} ha {count} registrazione/i che nessun import ha "
            "ancora letto. Elencale, e nomina le risposte a cui diresti sì o no."
        ),
        "view.where.never_run.title": "La suite non ha mai girato",
        "view.where.never_run.say": (
            "La suite {suite} tiene {count} risposta/e rivista/e e nessuna "
            "esecuzione. Falla girare per leggere che cosa dicono i suoi "
            "controlli: questa pagina mostra il comando e non lo lancia mai."
        ),
        "view.where.judge_disagrees.title": (
            "Il giudice non è d'accordo con una persona su {count}"
        ),
        "view.where.judge_disagrees.say": (
            "L'esecuzione più recente ha {count} risposta/e rivista/e che il "
            "giudice ha contraddetto o caso/i di calibrazione fuori dalla banda. "
            "Leggili prima di ogni altro numero: il sì o il no di una persona è "
            "il verdetto atteso."
        ),
        "view.where.green_without_red.title": "Verde senza un rosso",
        "view.where.green_without_red.say": (
            "L'esecuzione più recente esce 0, e nessuna esecuzione della suite "
            "{suite} ha mai fatto fallire un controllo. Una suite che non può "
            "fallire non misura niente: aggiungi un caso su cui deve fallire."
        ),
        "view.where.new_setup.title": "{count} risposta/e da un setup nuovo",
        "view.where.new_setup.say": (
            "Il setup in vigore ha risposto per la prima volta dopo l'esecuzione "
            "più recente, e {count} delle sue risposte sono a casi a cui ha "
            "risposto anche un setup precedente. Leggile fianco a fianco prima "
            "che la suite giri di nuovo."
        ),
        "view.where.nothing_to_do.title": "Niente da fare",
        "view.where.nothing_to_do.say": (
            "{count} caso/i, l'esecuzione più recente esce 0, e l'ultimo import "
            "ha letto le registrazioni fino a {last_import}. Torna quando "
            "l'applicazione cambia."
        ),
        "view.where.last_run_red.title": "L'esecuzione più recente esce {exit_code}",
        "view.where.last_run_red.say": (
            "L'esecuzione più recente della suite {suite} esce {exit_code}, per "
            "un motivo che nessuno degli stati prima di questo nomina. digline "
            "explain dice quale."
        ),
        "view.nav.runs": "Esecuzioni",
        "view.nav.report": "Rapporto",
        "view.nav.recordings": "Registrazioni",
        "view.nav.setups": "Fra i setup",
        "view.nav.recorder": "Registratore",
        "view.nav.proposal": "Proposta",
        "view.title.proposal": "Proposta — {suite}",
        "view.where.no_suite_yet.proposal": (
            "digline suggest ha scritto una proposta, non ancora adottata: {proposal}."
        ),
        "view.where.proposal.open": "Leggi la proposta",
        "view.proposal.heading": (
            "La proposta che digline suggest ha scritto per {suite}"
        ),
        "view.proposal.lead": (
            "Una proposta, non una suite: nessun comando di digline la legge, "
            "niente in essa è un verdetto, e nessuna risposta è stata marcata. "
            "Questa pagina legge il file e non scrive niente; adottarne le righe "
            "nella tua suite tocca a te."
        ),
        "view.proposal.file": "Il file",
        "view.proposal.declaration": "Cosa dichiara",
        "view.proposal.notes": "Cosa dice il file accanto",
        "view.proposal.checks": "I check, nell'ordine del file",
        "view.proposal.key": "Chiave",
        "view.proposal.value": "Valore",
        "view.proposal.mark": "Marcato",
        "view.proposal.mark.placeholder": "un segnaposto: tocca a te scriverlo",
        "view.proposal.mark.assistant": "dall'assistente, non misurato",
        "view.proposal.mark.draft": "dall'assistente: una bozza, da leggere",
        "view.proposal.said": "L'assistente ha detto",
        "view.proposal.counterexample": "Il controesempio",
        "view.proposal.calibration": "Lo scheletro di calibrazione",
        "view.proposal.unread": (
            "Righe che questa pagina non ha saputo collocare, così come stanno"
        ),
        "view.proposal.none": (
            "Nessuna proposta per {suite} dove digline suggest la scrive. Questa "
            "pagina ha guardato in:"
        ),
        "view.proposal.invalid": "Il file c'è e non si è potuto leggere: {error}",
        "view.proposal.commands": (
            "Il comando che la scrive, senza assistente e con. Un modello che "
            "[suggest] nomina nel suite.toml è chiamato solo con --assist, e "
            "--model vince su di esso. Qui è mostrato e mai eseguito: quanto "
            "costa un modello si dice prima della chiamata."
        ),
        "view.proposal.overwrite": (
            "digline suggest non sovrascrive una proposta: sposta o cancella "
            "{path} prima."
        ),
        "view.writes.behind": (
            "Questa pagina non scrive niente: l'import e l'interruttore del "
            "registratore li serve solo digline view --allow-record."
        ),
        "view.title.recordings": "Registrazioni — {suite}",
        "view.recordings.column.id": "Risposta",
        "view.recordings.column.when": "Prima registrazione",
        "view.recordings.column.setup": "Setup",
        "view.recordings.column.answer": "Testo",
        "view.recordings.column.times": "Risposte uguali",
        "view.recordings.column.state": "Stato",
        "view.recordings.whole": "mostra tutto",
        "view.recordings.earlier": "precedente",
        "view.recordings.undated": "senza data",
        "view.recordings.attached": "{count} chiamata/e collegate",
        "view.recordings.from_first_call": "caso dalla prima chiamata",
        "view.title.answer": "Risposta {answer} — {suite}",
        "view.answer.input": "Input",
        "view.answer.response": "Testo",
        "view.answer.back": "Torna alle registrazioni",
        "view.answer.missing": (
            "{answer} non è una risposta che le registrazioni della suite "
            "{suite} contengono."
        ),
        "view.title.setups": "Fra i setup — {suite}",
        "view.setups.lead": (
            "Le risposte registrate per la suite {suite} nel tenant {tenant}, "
            "per caso e per setup, dalla più vecchia. Mostrate, mai giudicate."
        ),
        "view.setups.setups": "I setup, nell'ordine della loro prima risposta",
        "view.setups.pick": "Affianca",
        "view.setups.and": "e",
        "view.setups.go": "Mostra",
        "view.setups.side": "A {a}, B {b}",
        "view.setups.keys": "Chiavi in cui i due setup differiscono ({same} uguali)",
        "view.setups.keys.none": "I due setup hanno le stesse {same} chiavi.",
        "view.setups.absent": "assente in {side}",
        "view.setups.chars": "{chars} caratteri",
        "view.setups.messages.one": "{count} messaggio",
        "view.setups.messages.many": "{count} messaggi",
        "view.setups.episode": (
            "chiamate al modello per episodio: {calls} · modelli: {models}"
        ),
        "view.setups.unrecorded": "non registrati",
        "view.setups.case": "Caso {case_id} · {kind}",
        "view.setups.digest": (
            "setup {digest}: mostrato dai suoi primi 8 caratteri, come lo stampa "
            "digline record compare; il file dei casi lo tiene intero"
        ),
        "view.setups.over_time": "solo questo caso, nel tempo",
        "view.setups.every_case": "tutti i casi",
        "view.setups.column.when": "Registrata",
        "view.setups.column.setup": "Setup",
        "view.setups.column.digest": "Digest",
        "view.setups.column.answer": "Risposta",
        "view.setups.column.times": "Volte",
        "view.setups.through": "fino a {last}",
        "view.setups.nothing": "niente di registrato",
        "view.setups.chart": (
            "La lunghezza di ogni risposta registrata, in caratteri, per setup, "
            "nel tempo. La stessa risposta registrata di nuovo è un punto alla "
            "stessa altezza; la tabella dice quale risposta era."
        ),
        "view.setups.chart.label": "caratteri",
        "view.setups.empty": (
            "Niente di registrato per la suite {suite} nel tenant {tenant}."
        ),
        "view.setups.only": "Solo: {filters}",
        "view.not_shown.orphans": "orfane",
        "view.not_shown.detached": "chiamate il cui episodio non è fra i file",
        "view.not_shown.interrupted": "episodi interrotti",
        "view.not_shown.oversize": "oltre il tetto di una registrazione",
        "view.not_shown.unreadable": "file che non sono registrazioni leggibili",
        "view.not_shown.undated": "senza recorded_at",
        "view.not_shown": "Non mostrate",
        "view.title.recorder": "Registratore — {tenant}",
        "view.recorder.size": "Registrazioni, come scritte",
        "view.recorder.size.note": "byte; sul disco occupano di più",
        "view.recorder.ceiling": "Tetto",
        "view.recorder.ceiling.none": "nessuno letto",
        "view.recorder.held": "Registrazioni tenute",
        "view.recorder.held.note": "chiamate {calls} · episodi {episodes}",
        "view.recorder.to_import": "Da importare",
        "view.recorder.to_import.since": "suite {suite}, dall'ultimo import",
        "view.recorder.to_import.never": "suite {suite}, mai importata: tutte",
        "view.recorder.not_read": "non letto",
        "view.recorder.not_read.note": (
            "si legge per una suite che dichiara il suo file di cattura"
        ),
        "view.recorder.state.absent": "nessun file dell'interruttore",
        "view.recorder.state.invalid": "file dell'interruttore non valido",
        "view.recorder.state.on": "registrazione accesa",
        "view.recorder.state.off": "registrazione spenta",
        "view.recorder.switch": "Interruttore",
        "view.recorder.writes_to": "Scrive in",
        "view.recorder.values": "Valori",
        "view.recorder.default": "predefinito",
        "view.recorder.declared": "dichiarato",
        "view.recorder.refused": "Rifiutato",
        "view.recorder.absent": (
            "Senza file, un'applicazione registra solo con DIGLINE_RECORD=1, e "
            "solo in sviluppo."
        ),
        "view.recorder.stopped": "Il registratore si è fermato al tetto.",
        "view.recorder.unreadable": "{count} file che non sono registrazioni",
        "view.recorder.from_gate": (
            "suite {suite}: {count} da esecuzioni del gate, tenute a parte: non "
            "elencate, importate né confrontate"
        ),
        "view.recorder.uncounted": (
            "Non contato: {count} processo/i hanno registrazioni e nessun "
            "conteggio, quindi non si sa cosa non vi è stato registrato."
        ),
        "view.recorder.column.suite": "Suite",
        "view.recorder.column.calls": "Chiamate",
        "view.recorder.column.inside": "In un episodio",
        "view.recorder.column.orphans": "Orfane",
        "view.recorder.column.episodes": "Episodi",
        "view.recorder.column.interrupted": "Interrotti",
        "view.recorder.column.since": "Dall'ultimo import",
        "view.recorder.column.not_recorded": "Non registrate",
        "view.recorder.never": "mai importata, {count} in tutto",
        "view.recorder.no_suite": "Nessuna suite ha registrazioni in questo tenant.",
        "view.recordings.column.elect": "Nominala",
        "view.import.by": "Il tuo nome, il marchio di ogni caso (--by)",
        "view.import.button": "Scrivi le risposte nominate",
        "view.command.note": (
            "Il comando che fa quello che fa il bottone. Segue il form mentre lo "
            "compili dove lo script della pagina gira, e altrimenti mostra il "
            "form come è stato servito."
        ),
        "view.switch.title": "Accendi o spegni il registratore",
        "view.switch.on": "Accendi",
        "view.switch.off": "Spegni",
        "view.switch.production": "produzione (--production)",
        "view.switch.sample": "campione (--sample)",
        "view.switch.redact": "redazione (--redact)",
        "view.switch.ceiling": "tetto, byte (--ceiling)",
        "view.switch.interval": "intervallo, secondi (--interval)",
        "view.write.refused": "Non è stato scritto niente. {why}",
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
        "view.chip.crossing": "artefatto trattenuto",
        "view.promote.crossing": (
            "Un file che questa suite dichiara non può uscire dal perimetro, e un "
            "riferimento porta il testo di ogni artefatto in baselines/, che è "
            "versionata. Cambia la suite prima di promuovere."
        ),
        "view.chip.nothing_judged": "nulla giudicato",
        "view.promote.nothing_judged": (
            "Questo run non ha giudicato nessuno dei casi che la sua suite misura: "
            "non ha misurato niente, quindi non può diventare un riferimento."
        ),
        "view.chip.unmeasured": "non misurato",
        "view.promote.unmeasured": (
            "Non si può dire che cosa abbia misurato questo run: un controllo non "
            "si riconcilia con la sua suite, o un controllo sull'intero run non si "
            "è potuto calcolare. Un errore non è un riferimento."
        ),
        "view.chip.uncalibrated": "scala persa",
        "view.promote.uncalibrated": (
            "Un caso di calibrazione è uscito dalla sua banda dichiarata: in questo "
            "run il giudice ha perso la scala, quindi non può diventare un "
            "riferimento. Promuovi un run in cui la calibrazione ha tenuto."
        ),
        "view.chip.contradicted": "contraddice una persona",
        "view.promote.contradicted": (
            "Il giudice ha contraddetto il sì o il no di una persona su una "
            "risposta rivista, e la risposta della persona è il verdetto atteso, "
            "quindi questo run non può diventare un riferimento. Promuovi un run "
            "il cui giudice ha dato ragione a ogni persona."
        ),
        "view.chip.pinned": "pin spostato",
        "view.promote.pinned": (
            "Un file dichiarato immutabile si è spostato, o ha perso il suo "
            "percorso, rispetto al riferimento. Questa pagina non porta "
            "autorizzazioni: confronta il run e, se il cambiamento era voluto, "
            "promuovilo dalla riga di comando nominando ogni percorso con "
            "--accepting-pin."
        ),
        "view.chip.refused": "rifiutato",
        "view.promote.unnamed": (
            "Lo store rifiuterebbe di promuovere questo run, per un motivo per cui "
            "questa pagina non ha ancora un marcatore: digline promote lo nomina."
        ),
        "view.chip.replayed": "replay",
        "view.promote.replayed": (
            "Questo run ha giudicato di nuovo le risposte registrate di "
            "{run_key} e non ha interrogato il target, quindi non può diventare "
            "un riferimento: il suo intervallo è solo l'oscillazione del "
            "giudice. Promuovi un run che ha misurato."
        ),
        "view.read_only": ("sola lettura — riavvia con --allow-promote per promuovere"),
        "view.read_only.why": (
            "Questo server non promuove: nessun pulsante su nessuna riga, e "
            "POST /promote non è una rotta. Fermalo e avvia "
            "digline view --allow-promote per abilitare la promozione di ogni "
            "esecuzione nell'archivio, finché il server resta acceso."
        ),
        "view.action.compare": "Confronta",
        "view.action.compare.title": ("confronta questa esecuzione con il riferimento"),
        "view.action.open": "Apri",
        "view.action.open.title": (
            "questa esecuzione da sola: non c'è ancora un riferimento con cui "
            "confrontarla"
        ),
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
        "left_out.ignored": "ignorate: {parts}",
        "left_out.schema": "run allo schema {version}: {count}",
        "left_out.unreadable": "file illeggibili: {count}",
        "left_out.migrate": "esegui `digline migrate` per aggiornarle",
        "left_out.upgrade": "aggiorna digline per leggere le più recenti",
        "left_out.refused": "rifiutate: {count} run: {keys}",
        "left_out.more": "e altre {count}",
        "left_out.unnamed": (
            "lasciati fuori senza nome: {count} file il cui nome non è una "
            "chiave di run"
        ),
        "left_out.misfiled": (
            "lasciati fuori per il nome: {count} file il cui nome non è la "
            "chiave della loro run"
        ),
        "left_out.baseline_refused": "la baseline non si è potuta leggere: {why}",
        "left_out.baseline_missing": (
            "la run da cui è stata promossa la baseline, {run_key}, non è tra le run "
            "lette"
        ),
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
        "view.promote.refused": "Rifiutato: {why}",
        "view.list.unavailable": (
            "L'elenco delle esecuzioni non si può mostrare: {why}"
        ),
        "view.baseline.promoted": (
            "Il riferimento è {run_key}, impostato il {promoted_at}."
        ),
        "view.baseline.is": "Il riferimento è {run_key}.",
        "view.baseline.none": "Questa suite non ha ancora un riferimento.",
        "view.baseline.unreadable": (
            "Nemmeno il riferimento si è potuto leggere: {why}"
        ),
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
        "explain.tally.unjudged.of.one": (
            "Casi valutati: {judged} su {total}; 1 non lo è stato."
        ),
        "explain.tally.unjudged.of.many": (
            "Casi valutati: {judged} su {total}; {count} non lo sono stati."
        ),
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
        "judged.floor": (
            "; misurato su risposte registrate, che non sono un campione di ciò "
            "che produce una run dal vivo, quindi questo è un limite inferiore "
            "all'intervallo del giudice in produzione"
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
        "explain.tally.unreconciled.one": (
            "1 controllo non torna con ciò che la suite ha chiesto. Non è una "
            "regressione: non si sa che cosa l'esecuzione abbia misurato. È "
            "nominato sotto, tra i controlli non valutati."
        ),
        "explain.tally.unreconciled.many": (
            "{count} controlli non tornano con ciò che la suite ha chiesto. Non "
            "è una regressione: non si sa che cosa l'esecuzione abbia misurato. "
            "Sono nominati sotto, tra i controlli non valutati."
        ),
        "explain.tally.reference_unreconciled.one": (
            "1 controllo del riferimento non torna con ciò che la sua suite ha "
            "chiesto. Non si sa che cosa il riferimento abbia misurato, e il "
            "confronto è fatto contro di esso."
        ),
        "explain.tally.reference_unreconciled.many": (
            "{count} controlli del riferimento non tornano con ciò che la sua "
            "suite ha chiesto. Non si sa che cosa il riferimento abbia "
            "misurato, e il confronto è fatto contro di esso."
        ),
        "explain.tally.misnamed.one": (
            "1 controllo ha restituito un verdetto con un nome che non è quello "
            "della sua asserzione, ed è stato rifiutato. Il difetto è "
            "dell'asserzione, non del sistema sotto esame. È nominato sotto, tra i "
            "controlli non valutati."
        ),
        "explain.tally.misnamed.many": (
            "{count} controlli hanno restituito un verdetto con un nome che non "
            "è quello della loro asserzione, e sono stati rifiutati. Il difetto "
            "è dell'asserzione, non del sistema sotto esame. Sono nominati sotto, "
            "tra i controlli non valutati."
        ),
        "explain.tally.calibration.one": (
            "1 caso di calibrazione è fuori dalla banda dichiarata: {cases}. I "
            "punteggi giudicati in questa esecuzione non stanno sulla scala su "
            "cui vengono confrontati. Non entra in nessun aggregato, e al "
            "sistema sotto esame non è stato chiesto nulla per esso."
        ),
        "explain.tally.calibration.many": (
            "{count} casi di calibrazione sono fuori dalla banda dichiarata: "
            "{cases}. I punteggi giudicati in questa esecuzione non stanno sulla "
            "scala su cui vengono confrontati. Non entrano in nessun aggregato, "
            "e al sistema sotto esame non è stato chiesto nulla per essi."
        ),
        "explain.tally.calibration.case": (
            "{case} per {check} a {score}, {side} {low}–{high}"
        ),
        "explain.side.above": "sopra",
        "explain.side.below": "sotto",
        "explain.tally.reviewed.one": (
            "{said}, e il caso fallisce: {cases}. Non entra in nessun "
            "aggregato, e al sistema sotto esame non è stato chiesto nulla per "
            "essa."
        ),
        "explain.tally.reviewed.many": (
            "{said}, e ciascuna fallisce: {cases}. Non entrano in nessun "
            "aggregato, e al sistema sotto esame non è stato chiesto nulla per "
            "esse."
        ),
        "explain.tally.reviewed.passed_no": (
            "{case} per {check}, promossa dove la persona ha detto no"
        ),
        "explain.tally.reviewed.failed_yes": (
            "{case} per {check}, bocciata dove la persona ha detto sì"
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
            "Il sistema sotto esame era configurato con {name} {after}; il "
            "riferimento con {before}."
        ),
        "explain.setting.target.changed.observed": (
            "Il sistema sotto esame ha riportato {name} {after}; il "
            "riferimento ha riportato {before}."
        ),
        "explain.setting.target.changed.recorded": (
            "Il sistema sotto esame ha registrato {name} {after}; il "
            "riferimento ha registrato {before}."
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
            "Il giudice era configurato con {name} {after}; il giudice del "
            "riferimento con {before}."
        ),
        "explain.setting.judge.changed.observed": (
            "Il giudice ha riportato {name} {after}; il giudice del "
            "riferimento ha riportato {before}."
        ),
        "explain.setting.judge.changed.recorded": (
            "Il giudice ha registrato {name} {after}; il giudice del "
            "riferimento ha registrato {before}."
        ),
        "explain.setting.judge.new": (
            "Il giudice ha registrato {name} {after}, che il riferimento non "
            "registrava."
        ),
        "explain.setting.judge.missing": (
            "Il giudice del riferimento registrava {name} {before}; questa "
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
        "explain.setting.rule.changed.loosened": (
            "{name} è passato da {before} a {after}, un'asticella più bassa di "
            "quella con cui è stato approvato il riferimento."
        ),
        "explain.setting.rule.changed.tightened": (
            "{name} è passato da {before} a {after}, un'asticella più alta di "
            "quella con cui è stato approvato il riferimento."
        ),
        "explain.setting.rule.changed": "{name} è passato da {before} a {after}.",
        "explain.setting.rule.new.tightened": (
            "{name} è un controllo a cui questa esecuzione è sottoposta e il "
            "riferimento no."
        ),
        "explain.setting.rule.new.new_group": (
            "{name} controlla un gruppo che il riferimento non aveva. "
            "L'aggregato era già controllato per gruppo, quindi è stato "
            "etichettato un caso, non riscritta una regola."
        ),
        "explain.setting.rule.new.now_grouped": (
            "{name} è qui perché questo aggregato ora è controllato per gruppo, "
            "mentre nel riferimento non lo era."
        ),
        "explain.setting.rule.missing.loosened": (
            "{name} non si applica più; il riferimento vi era sottoposto."
        ),
        "explain.setting.rule.unknown": (
            "Se {name} sia cambiato non è noto: un lato non l'ha registrato."
        ),
        "explain.setting.rule.unnameable": (
            "La soglia di accordo non è registrata in un'esecuzione, quindi da "
            "queste due non si può dire se sia cambiata."
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
            "Il sistema sotto esame era configurato con {name} {after}."
        ),
        "explain.setting.target.alone.observed": (
            "Il sistema sotto esame ha riportato {name} {after}."
        ),
        "explain.setting.judge.alone": (
            "Il giudice era configurato con {name} {after}."
        ),
        "explain.setting.judge.alone.observed": (
            "Il giudice ha riportato {name} {after}."
        ),
        "explain.setting.target.alone.recorded": (
            "Il sistema sotto esame ha registrato {name} {after}."
        ),
        "explain.setting.judge.alone.recorded": (
            "Il giudice ha registrato {name} {after}."
        ),
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
        "explain.check.incomparable": (
            "{where}: misurato su {considered} casi qui e "
            "{reference_considered} nel riferimento, quindi {before} e {now} "
            "non sono un movimento l'uno dell'altro."
        ),
        "explain.check.unchanged": (
            "{where} si è spostato da {before} a {now}, entro la tolleranza "
            "dichiarata dalla suite."
        ),
        "explain.check.within_noise": (
            "{where} si è spostato da {before} a {now}, entro l'intervallo "
            "misurato dal riferimento."
        ),
        "explain.check.within_noise.mean": (
            "{where} si è spostato da {before} a {now}, entro il pavimento di "
            "rumore dato dai campioni del riferimento, {noise}."
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
        "explain.check.contradicted.no": (
            "{where} è promosso a {now}, e una persona ha detto no alla "
            "risposta: il giudice contraddice la persona, e il caso fallisce."
        ),
        "explain.check.contradicted.yes": (
            "{where} è bocciato a {now}, e una persona ha detto sì alla "
            "risposta: il giudice contraddice la persona, e il caso fallisce."
        ),
        "explain.check.contradicted.steps": (
            "{where} è bocciato a {now}, e una persona ha detto sì al turno: i "
            "suoi passi contraddicono la persona, e il caso fallisce."
        ),
        "explain.check.suspended": (
            "Il caso {case} è stato messo da parte, quindi su di esso non è "
            "stato misurato nulla. Il motivo dichiarato non viaggia qui."
        ),
        "explain.where.run": "l'intera esecuzione",
        "explain.bar": " La soglia è {threshold}.",
        "explain.noise.beyond": (
            " È fuori dall'intervallo misurato dal riferimento, {noise}."
        ),
        "explain.noise.beyond.mean": (
            " È fuori dal pavimento di rumore dato dai campioni del "
            "riferimento, {noise}."
        ),
        "explain.nothing": "Niente in questo gruppo.",
        "log.heading": (
            "tenant {tenant} · {suite} · {count} esecuzioni lette in questo "
            "archivio, da {first} a {last}"
        ),
        "log.empty": (
            "tenant {tenant} · {suite} · nessuna esecuzione letta in questo "
            "archivio, in questa finestra."
        ),
        "log.window": "Finestra: da {since} a {until}.",
        "log.window.open": "…",
        "log.not_read.schema": (
            "{count} esecuzioni allo schema {version} non sono state lette."
        ),
        "log.not_read.unreadable": "{count} file non si sono potuti leggere.",
        "log.not_read.refused": (
            "{count} esecuzioni sono state rifiutate dall'archivio e non lette: "
            "`digline list` le nomina."
        ),
        "log.not_read.on_record": (
            "{count} esecuzioni nominate dal riferimento o dal registro non sono "
            "state lette qui: {before} prima della prima letta, {after} dopo "
            "l'ultima."
        ),
        "log.not_read.on_record.none_read": (
            "{count} esecuzioni nominate dal riferimento o dal registro non sono "
            "state lette qui."
        ),
        "log.span.unread": (
            "; {count} esecuzioni registrate al suo interno non sono state lette"
        ),
        "log.roll.unread": (
            "{count} esecuzioni registrate tra le due non sono state lette, quindi "
            "non si sa cosa abbiano registrato."
        ),
        "log.side.target": "Sistema",
        "log.side.judge": "Giudice",
        "log.span": (
            "  {sighting} — da {first} a {last}, {runs} esecuzioni{environments}"
        ),
        "log.environments": " ({environments})",
        "log.sighting.answered": "{who}, ha riportato {answered}",
        "log.sighting.absent": "{who}: {absence}",
        "log.absence.declared_nothing": "nessuna configurazione dichiarata",
        "log.absence.several_judges": (
            "più giudici; nessun singolo modello che ha risposto"
        ),
        "log.absence.projected": (
            "la configurazione è proiettata, quindi a chi è stato chiesto e chi "
            "ha risposto sono token che solo la tabella dei nomi può leggere"
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
        "log.rolls.none": "Nessun avvicendamento registrato.",
        "log.roll": (
            "{side}: {sent} ha riportato {before} l'ultima volta a "
            "{last_before}, e {after} la prima volta a {first_after}."
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
        "log.spread.heading": "Scarto fra run",
        "log.spread.none": (
            "  Questa suite non dichiara controlli di run, quindi non c'è nulla "
            "da leggere fra run."
        ),
        "log.spread.no_runs": (
            "  Nessuna run letta in questo store, in questa finestra, quindi "
            "non c'è nulla da leggere fra run. Se questa suite dichiari un "
            "controllo di run questa lettura non può dirlo: legge le run, e "
            "non ce ne sono."
        ),
        "log.spread.flipped": (
            "  {count} controlli di run hanno cambiato esito rispetto al "
            "riferimento, quindi per loro non viene letto nessun intervallo: "
            "un esito cambiato non porta un intervallo."
        ),
        "log.spread.scoreless": (
            "  {count} controlli di run non hanno registrato un punteggio, "
            "quindi per loro non c'è nessun intervallo da leggere."
        ),
        "log.spread.projected": (
            "  Il riferimento è proiettato, quindi i suoi controlli di run hanno "
            "per nome dei token e non si possono accoppiare con questi {count}. "
            "Se uno abbia cambiato stato rispetto a esso non è noto, quindi per "
            "loro non si legge nessun intervallo: un cambio di stato non porta "
            "un intervallo."
        ),
        "log.spread.set": (
            "  Su {count} run confrontabili in questo store, in questa "
            "finestra — l'ultima non è fra queste{excluded}."
        ),
        "log.spread.excluded": "; escluse: {excluded}",
        "log.spread.excluded.rejudged": "{count} rigiudicate",
        "log.spread.excluded.unjudged": "{count} non giudicate del tutto",
        "log.spread.excluded.scale_lost": "{count} non calibrate",
        "log.spread.excluded.config_hash": "{count} che misurano altre regole",
        "log.spread.excluded.population": "{count} che contano altri casi",
        "log.spread.excluded.artifacts": "{count} che provano un altro prompt",
        "log.spread.excluded.target_config": (
            "{count} che interrogano un altro sistema"
        ),
        "log.spread.excluded.judge_config": (
            "{count} che giudicano con un altro strumento"
        ),
        "log.spread.excluded.config_unrecorded": (
            "{count} in cui solo una delle due run ha registrato la configurazione"
        ),
        "log.spread.excluded.identity": (
            "{count} in cui è stato riportato un altro modello"
        ),
        "log.spread.unidentified": (
            "  {count} run su {total} non hanno identificato il modello che ha "
            "risposto."
        ),
        "log.spread.commits": "  Le run contate sono state scritte da {count} commit.",
        "log.spread.versions": "  Scritte da digline {versions}.",
        "log.spread.range": (
            "  {name}: l'ultima run ha ottenuto {latest} contro {reference} del "
            "riferimento, una differenza di {difference}. {name} è andata da "
            "{low} a {high} nelle run contate."
        ),
        "log.spread.range.alone": (
            "  {name}: l'ultima run ha ottenuto {latest}. {name} è andata da "
            "{low} a {high} nelle run contate."
        ),
        "log.spread.no_comparable": (
            "  {name}: nessuna run in questo store è stata misurata allo stesso "
            "modo, quindi non c'è un intervallo da leggere."
        ),
        "log.spread.within": (
            "    Dentro l'ultima run, lo stesso aggregato per campione è andato "
            "da {low} a {high} — un'altra misura, non confrontabile con "
            "l'intervallo qui sopra."
        ),
        "log.spread.floor": (
            "  Se il punteggio dell'ultima run stia dentro questo scarto non "
            "viene detto: un intervallo descrive le run che ha letto e non può "
            "portare quella frase. Un valore sotto il minimo o sopra il massimo "
            "allarga l'intervallo, quindi restare fuori indica un punteggio non "
            "ancora visto, non un cambiamento."
        ),
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
        raise RefusedError(f"unknown locale {locale!r}; available: {available}")
    return table


def phrase(locale: Locale, key: str, **params: object) -> str:
    """One localized string. A missing key is a programming error and says so
    with the key, rather than rendering an empty cell nobody notices."""
    table = strings(locale)
    template = table.get(key)
    if template is None:
        raise KeyError(f"no text for {key!r} in locale {locale!r}")
    return template.format(**params) if params else template
