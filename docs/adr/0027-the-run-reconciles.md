# ADR 0027 — The run reconciles with what it was asked

- Status: accepted — the text first, then the implementation written against
  it on `denominator-sentence`
- Shipped: 0.17.0
- Date: 2026-09-19
- Opens: nothing. No schema bump, and not a passenger on one. The run document
  gains no field. §3 says where the fact is written instead
- Assumes: [ADR 0012](0012-the-reading.md) §3 (the reading's closed tally
  list, amended here once more); [ADR 0016](0016-the-canary-case.md) and
  [ADR 0024](0024-the-judge-as-an-instrument.md) §4.4 (the canary and the
  calibration case, which are left out of every aggregate);
  [ADR 0017](0017-the-journal-and-the-resumed-run.md) §4 and §6 (what a resume
  reuses, and what it refuses before the first call)
- Touches: nothing in `CLAUDE.md`'s *fixed* section. Decision 3 (*no vacuously
  green assertion*) is what this serves. Decisions 1 and 7 are why the check is
  a pure function and not a feature of the offline driver
- Turns into surface: `docs/explain.md` (the new tally line)
- Credit: the pressure in §Context was named by **nitish-kmr**, on the Reddit
  thread about the denominator article

## Context

The denominator article (GHSA-8c38-f965-cgww, 0.15.3) ended in a hard refusal.
A case that could not be judged makes the run exit 2, and a run with an
errored verdict cannot be promoted. That refusal is right. **nitish-kmr pointed
out what it rewards.** A team that needs a green run learns to wrap the
exception so that the run finishes. The error becomes a skip one level down,
inside their own code, where digline sees a case that answered. That is the
denominator defect again, in a new form, and our own cure is what pushes people
towards it.

**That is the reason for this record, not the feature.** Nothing digline does
can see an exception the user's code caught (§2 says so plainly). But the
pressure raises a question that digline *can* answer, and had never asked:
**did every question the suite put to the run come back as a verdict?** A run
that cannot say yes does not know what it measured, whether it is green or red.

Three findings came from asking it.

1. **The obvious form proves nothing.** `build_matrix` puts every outcome into
   exactly one bucket, so *counted + exclusions = cases* holds by construction.
   A lost case lands in `suspended`, and the sum still adds up. A check that
   subtracts each exclusion by name from a case count has the same flaw one
   level up. It is also a list to keep in step with every exclusion somebody
   adds later, which is the failure the check exists to catch.
2. **A case could be counted as set aside when nobody set it aside.**
   `_outcomes` found the verdict an aggregate counts by `score.name`. `Suite`
   validates `over` against the assertion's *declared* name. A third-party
   assertion whose `Score` is named differently had its cases counted as
   `suspended_excluded`, with zero cases suspended. If only its failing
   verdicts carried the different name, the failures left the count and
   accuracy read 1.0. Reproduced; no shipped assertion does this.
3. **A resumed case can arrive with no verdicts and no suspension.** A journal
   entry, or a `done` entry built by hand, of that shape was accepted, and the
   aggregate counted it as suspended.

This is the eighth defect of the same family found this week: **a case that
vanishes, rather than a number that fails to declare itself.**

## Decision

### 1. Two checks, reading the driver's own dispatch back

After the last case runs and before any aggregate is computed, the driver asks
two questions of the results it is about to record:

1. **Every declared case has exactly one result.** The declared case ids are
   compared with the `CaseResult` ids.
2. **Every result answers exactly what it was asked.** The verdicts a result
   carries are compared with what the driver asks of that case, matched by
   `assertion_id`:
   - a **suspended** case is asked nothing;
   - a **calibration** case is asked its one check;
   - **every other case, canary included**, is asked every declared assertion.

The expected set is the driver's own dispatch, read back from the same
conditions that choose the branch. It is not a list of exclusions subtracted
from a total. So it cannot go stale when an exclusion is added: a new kind of
case is a new branch in the dispatch, and the check reads that branch.

`cases × assertions` would be the simpler statement, and it is false by design.
A suspended case carries no verdict, and `CaseResult` refuses to carry one. A
calibration case carries exactly one. Making them "emit rows" would mean
recording verdicts about questions nobody asked, which digline refuses
everywhere else.

What the checks do not count: the exclusions an **aggregate** makes
(`unlabelled_excluded` and the rest). Those are decisions about a figure, and
they are stated beside it (see the sentence released beside this record).
This checks what was recorded, not what a figure chose to count.

### 2. What it cannot see, and the record has to say so

A target that catches its own exception and returns `""` or an error string
produces a case that **was** scored. Every verdict came back, so both checks
pass, and that is correct: the run really did judge what it was given. No check
on counts can ever see it. Only a check on content can, such as `includes`,
which fails on silence (`docs/selection.md`), or a target that reports its
error instead of swallowing it.

So this record does not close the pressure it was written for. It closes the
losses digline could cause itself, and it leaves the reading honest about which
one this is.

### 3. On failure: named, exit 2, never promotable, and not a regression

Every gap becomes a **named errored verdict**, for the case and the check it
names. It carries `Score.metadata["unreconciled"] = True`, and its reason reads
*"this check was asked of case c3 and no verdict came back"*. The run file is
kept.

- **Named, not counted.** "3 verdicts short" sends somebody hunting. Naming
  case and check ends the question. The names are case ids and check names,
  which the reading already names for every errored check. The reason is
  payload, like every reason.
- **Exit 2, never promotable.** Both follow from paths that already exist,
  with no new ones: an errored verdict makes `unjudged_cases` non-zero, and
  `promote_baseline` refuses a run with one. Promotion names the unreconciled
  checks in its refusal before any other error, because this is the stronger
  statement.
- **Not a regression.** The headline says what the fact is: *the run does not
  reconcile with what the suite asked; this is not a regression, and what the
  run measured is not known.* It comes first, before any count, for the reason
  a lost calibration comes first: it qualifies every number after it.
- **Why not refuse the run.** A refusal inside `execute` throws away calls
  already paid for, and a resume would fail again the same way. The run is
  kept, and it is marked.
- **Why the verdict and not a new field.** The marker rides the verdict's own
  metadata, which is a boolean and so travels under `travels()` like every
  other measurement. It survives `redact()` and the round trip without a schema
  bump. It is written by the driver rather than by an assertion. An assertion
  that set the key itself could only make its own run redder, never greener,
  and the reader requires `status == "error"` beside it.

Extra rows are gaps too: a verdict nobody asked for, or two for one question.
Each extra verdict is replaced by a marked errored copy, so the run cannot keep
an answer to a question it did not ask. Three shapes cannot be repaired
without inventing something: a missing result whose case was suspended, a
second result for one case, and a result for a case the suite does not
declare. They are refused as programming errors in the driver. The loop that
builds the results makes all three unreachable, and `execute` already refuses
a reused id the suite does not declare.

### 4. Where it lives

- **The comparison is a pure function in the core**
  (`digline.core.reconcile`). It takes what was asked and what came back, and
  returns the gaps, named. It does no I/O, so the online driver will call it
  unchanged (decisions 1 and 7).
- **The driver calls it**, because the driver is the only place that holds the
  declared cases, their groups and the dispatch. It is **not in the store**:
  a stored run records neither the declared case count nor the groups, so a
  load-time check could only reconcile a whole-run aggregate against
  `len(results)`, which proves little. Recording the declared count would be a
  schema change, and this record does not board a train.
- **It is not a `RunAssertion`.** Those are declared by users and optional,
  and this has to hold for everybody, with no configuration.

### 5. The resumed case with no verdicts is refused where resume is read

A journal entry with no verdicts and no suspension is refused in
`host/measure.py`, beside the refusal of reused ids the suite does not declare
(ADR 0017 §6). It is refused before the first call, and the journal is left
where it was. A suite cannot declare a case with no questions, because a suite
with no assertions is already refused. So an empty entry is a damaged record,
not data, and inventing an errored row for it would be a verdict about a
question nobody asked. A library caller that passes such an entry to `execute`
by hand is still caught, by §3's check, as a named gap.

### 6. An aggregate finds its verdict by identity

`_outcomes` now matches the `over` check by the `assertion_id` of the one
assertion `Suite` resolved `over` to, not by `score.name`. For every shipped
assertion the two are the same verdict. For a third-party assertion whose
score is named differently, cases are no longer counted as set aside when
nobody set them aside. This closes finding 2. §1's check could not: that
verdict was recorded with the right identity, and it was lost afterwards,
when the aggregate went looking for it.

### 7. The reading

- **Headline.** A new clause, first, naming every gap as *case · check*.
  `Headline.unreconciled` holds the count.
- **`explain`.** A new `TallyKind`, `unreconciled`, amending ADR 0012 §3 by
  that section's own test: the headline says it, and a reading that left it
  out would describe a run whose exit code it could not account for. The
  checks it names already appear, one per line, among the errored checks.
- **The single-run document** carries the same clause above its tally.
- **The wire.** `unreconciled` on `compare --json`'s headline, and the new
  tally kind on `explain --json`. Both are added keys under
  `OUTPUT_VERSION = 2`'s rule, and neither is a bump.

## Consequences

- A run that reconciles, which is every run the shipped driver produced before
  this record, is byte for byte what it was. No clause, no key value, and no
  exit code moves.
- A third-party assertion whose score name differs from its declared name now
  has its cases counted, which can move an aggregate that was flattered. That
  is the fix, not a side effect.
- The pressure nitish-kmr named is still there. §2 says where it goes, and the
  answer is a check on content, not on counts.
- **The marker is a self-declaration, and exit 2 is not tamper-evidence.**
  §4 puts the check at write time and rejects a load-time one, so `reconcile()`
  runs in the driver and nowhere else: a **stored** run is never reconciled
  again. Every reader afterwards — the headline, the reading, the report, the
  promotion refusal — reads back a marker the document carries about itself.
  Deleting the errored verdict that carries it removes the gap, the exit code
  and the refusal together, and the run then reads green and promotes. That is
  the price of §4's decision rather than a defect in it, and the alternative
  stays rejected for the reasons given there; what is written down here is what
  the decision leaves open, so that a red exit is not read as proof the file
  was not edited. The one place this price was never meant to be paid is a
  **reference**, whose document is the one versioned in git: `compare()` now
  reads the baseline's gaps too, and the headline and the reading both name
  them. (the second 0.17.0 delta-pass)

## Alternatives considered

**Count every exclusion by name, and reconcile against the case count.**
Rejected in §1. It proves nothing about `build_matrix`, and it is a list that
has to stay in step with every future exclusion.

**`emitted == cases × assertions`.** Rejected in §1: false by design for
suspended and calibration cases, and made true only by inventing verdicts.

**Refuse the run.** Rejected in §3: it throws away paid calls and gives a
resume nothing to resume.

**A load-time check in the store.** Rejected in §4: it cannot see groups or
the declared count, and recording the count would board a schema train.

## Not decided here

- **An errored aggregate blocks nothing, and that is this record's own family
  one level up.** Promotion and the exit code read per-case verdicts only, so a
  run whose only run-level figure errored — precision over nothing kept, say —
  exits 0 and can be promoted. **An errored figure is a number we do not have**,
  and exiting 0 asserts that nothing got worse on the strength of a measurement
  that is missing. Where §1 catches a case that vanished, this is a gate that
  vanished, and the run says nothing either way.

  It is held back rather than open: it changes the exit code of suites that
  have one today, which nothing in this record does. **It belongs in the next
  minor, with a changelog line of its own.** It is not a question waiting for
  an answer.
