# ADR 0012 — The reading (`digline explain`)

- Status: accepted — implementation on `explain`; ships in 0.7.0. The document
  landed first and the code was written against it, the way
  [ADR 0006](0006-repeated-samples-and-the-noise-floor.md),
  [ADR 0007](0007-the-declarative-suite-format.md) and
  [ADR 0008](0008-the-two-run-report.md) were
- Date: 2026-09-09
- Assumes: [ADR 0001](0001-verdict-not-score.md) §1 (three states, and an error
  is neither green nor a regression),
  [ADR 0002](0002-three-worlds-and-where-the-data-lives.md) §2 (the three
  worlds, and what each is entitled to),
  [ADR 0003](0003-artifacts-travel-only-when-the-suite-says-so.md) §4–5
  (withheld rather than absent, `unknown` rather than a guess),
  [ADR 0005](0005-the-configuration-of-the-system-under-test.md) §5 (the named
  delta, and `unknown` is never reported as a change),
  [ADR 0006](0006-repeated-samples-and-the-noise-floor.md) §5–§6, §9–§10 (the
  measured interval, where it does not reach, "within noise" as a fact beside
  the verdict, and the sentence that prints it),
  [ADR 0008](0008-the-two-run-report.md) §1–§2 (a verdict exists only against
  an approved reference; the exit code is the contract; document against
  terminal decides the locale rule),
  [ADR 0010](0010-per-group-aggregates.md) §10 (a failing measure beside an
  answer of "no" has to be explained where it is raised),
  [ADR 0011](0011-the-mcp-server.md) §5–§6 (the boundary projection is a
  decision, and `wire/` is one rendering of the truth per recipient)
- Touches: fixed decision 9 in `CLAUDE.md` — reaffirmed and **sharpened**. §4
  makes the payload boundary a property of a *type* rather than a filter
  applied at a serializer. Nothing else in the fixed section is amended

## Context

digline renders one run three ways, and all three **compress**.

`digline compare` prints a sentence and at most twenty lines. `digline report`
renders the document world 3 reads: an answer of yes or no in a box, a tally,
and tables a reader scans rather than reads. `--json` and the MCP tools emit the
facts a program parses. Each is right for its recipient, and each is a
compression — the report's whole craft is deciding what fits on the first
screen, and `Headline` exists because eight facts had to survive that squeeze.

What has never existed is the **reading**: the same facts at length, in order,
in sentences, for the person who has the report open and wants to know what it
is compressing. Which checks moved, by how much, against which measured
interval, which of them the interval covered, what was set aside and by whom,
what could not be judged at all, and which of the three configurations —
the suite's rules, the system under test, the judge — differed underneath all
of it.

The evidence that the product owes one is in this repository.
[`examples/operator/dossier.py`](https://github.com/digline/digline/blob/main/examples/operator/dossier.py)
builds exactly that document, deterministically, out of
`compare --json full`, because there was nothing to call. It is 250 lines
of an *example* re-deriving the product's own facts into prose — the
intervals, the flips, the configurations that differed, the checks whose
scores moved without changing outcome. Layers 1 and 2 of the operator's
alert are a dossier the engine should have handed it.

There is one hazard, and it is the reason this record exists before the code. A
command called `explain` is one word away from a command that **advises**.
`AGENTS.md` is an entire document about the judgment digline deliberately does
not encode — whether a red run is a regression or a wobble, which run deserves
to be the reference, when to stop re-running. The tool measures and reports; a
human decides. A reading that drifted into "you should re-run this" or "this
looks promotable" would put that judgment back inside the instrument, in prose,
where no test would see it. So the boundary is fixed here, in words, and §5
makes it a gate.

## Decision

### 1. One command, and the presence of a baseline decides its scope

**`digline explain --suite S --run KEY [--locale en|it]`.**

If the suite has a baseline, explain reads the run **and** the comparison. If it
does not, explain reads the run alone. One command, no mode flag: the pattern is
`digline report`'s, settled in 0.6.0, and it is settled for the same reason.
Making the reader name the scope means making them know, before they type, which
of two documents they are entitled to — and the first person to hit that is
always somebody on their first run, who has no baseline and does not yet know
what one is.

A flag would also have to be an error when a baseline is present, or a lie when
it is absent. Presence is a fact the store already knows; asking the user to
restate it is asking them to be right about it.

**There is no diff mode, and there must not be.** ADR 0008 §2 fixed diff's
register: symmetric, perspective-free, no "reference", no "before" and "after",
no direction of travel. Explain's register is the opposite — it speaks
throughout of a run held against a reference, because that is what it is
reading. One command carrying two registers is two commands wearing one name,
and the first sentence that came out with the wrong one would be a report that
is arithmetically correct and rhetorically false. If the two-run reading is ever
wanted, it is `digline diff --explain` or a command of its own, and it is
another record.

### 2. The same-truth rule: explain expands what the report compresses

**Explain consumes the same fact structures `headline()` and the report
consume, and computes no number they do not.** It is an expansion, never a
second calculation of the same thing.

The mechanism is a single intermediate — the **fact list** of §3 — that both
renderings are built from. It is stated as a rule with a shape, so that it can
be a test rather than a convention:

> Every fact explain states must be traceable to an object the report already
> consumes: an `AssertionDelta` in `comparison.deltas`, an `ArtifactDelta` or
> `ConfigDelta`, a field of `Headline`, or one of the run tallies the report
> prints. And every fact explain states must appear, compressed, in the same
> run's report.

Two directions, two gates, and neither substitutes for the other. The first —
**provenance** — proves explain invents nothing; it is structural, exact, and
does not read a rendered string. The second — **visibility** — proves explain
expands only what the report compresses; it is textual, and it holds against
`render_html`, or against `render_run_html` where there is no baseline. It does
**not** hold against `summary_lines`: the terminal summary truncates at
`SUMMARY_LIMIT` and says so, while the document carries every delta in its
collapsible sections. §8's test plan names both.

**A prerequisite, and it lands as its own commit before any of this.** Three
facts the report states today are computed *inline inside render functions* and
are not structures anything can consume:

- the **suspended count**, `sum(1 for case in run.results if case.suspended is
  not None)`, written out twice and independently — once in `headline()` and
  once in `_run_answer()`;
- the **run tally**, cases and checks, in `_run_answer()` and nowhere else;
- **naming the errored verdicts**. `unjudged_cases()` returns a count;
  `_summarized()` names them but only from a `Comparison`, so in the
  no-baseline scope nothing can name them at all.

They are extracted into named pure functions in `digline/report/render.py` —
`suspended_cases(run)`, `run_tally(run)`, `errored_verdicts(run)` — and
`headline()` and `_run_answer()` are repointed at them. Until that is done, §2
is a convention: a fact explain derives from a `Run` by re-implementing a
counter is a fact that can disagree with the report's, and the duplication of
the suspended count is where it would first happen.

### 3. The fact list is the surface; the prose is a render of it

**`explain --json` returns the structured fact list, not the prose.** The prose
is one rendering of that list; the JSON is another. Neither is the source, and
the list is.

**Three types, discriminated by a `kind`**, because the data already has exactly
three shapes:

- **`CheckFact`** — one check, in case or run scope. Carries `case_id`,
  `assertion`, `assertion_id`, the two scores, the delta, the threshold and
  tolerance in force, and the `Noise` it was judged against.
- **`SettingFact`** — one named thing under test that differed: a configuration
  parameter, a judge identity, or a file. Carries the name, the outcome in the
  five-word vocabulary `ConfigDelta` and `ArtifactDelta` deliberately share,
  the two values, `withheld`, and for a file the `+N −M` tally.
- **`TallyFact`** — one run-level count or state: how many cases, how many
  checks, how many could not be judged, how many were set aside, how many moved
  within noise, whether the suite's rules moved, whether comparability is
  reduced.

  *Amended 2026-09-15 by [ADR 0020](0020-the-reading-across-runs.md) §3, the
  fourth time this closed list has moved: `echoed` joins it — the endpoint
  returned the requested id as the model that answered, so what answered is not
  identified. It passes this section's test: the report states it, and a reading
  that omitted it would describe an identity as confirmed that the record does
  not confirm.*

  *Amended 2026-09-18 by the release delta-pass over 0.15.0 — the fifth time this
  closed list has moved, and the first time it moved because a reading was found
  saying something **false** rather than saying nothing. `denominator_moved`
  joins it: a run-level aggregate measured over a different number of cases than
  the reference it is set beside. It passes this section's test twice over — the
  report already prints `N counted · M not judged` under the score, and a reading
  that omitted it described a gate as `unchanged` when it had been computed over
  a smaller suite.*

  *The predicate is `considered` changed — **not** "a case errored".* A case
  leaves the matrix for five reasons and `errored_excluded` is one of them:
  `suspended_excluded`, `unlabelled_excluded`, `canary_excluded` and
  `calibration_excluded` shrink the same denominator and move the same score. A
  rule keyed on the error would leave four doors open and would need rewriting
  the first time somebody suspended a case; a rule keyed on the denominator
  closes all five at once and needs no list. `Matrix.considered` is already the
  number, already crosses as an integer, and is already what the two sides must
  agree on for their scores to be comparable at all.

  *A moved denominator is an **incomparability**, not a regression.* Two scores
  over different case sets are not a movement, because the thing measured is not
  the same thing. So it never counts as *worse*: `worse` stays false on its
  account, no check is reclassified as a regression, and the exit code is
  unchanged by it — a run whose exclusion was an error already exits 2 on the
  errored check, and a suspension already has its own accounting. What it removes
  is `unchanged` as an available answer: a delta whose two sides were computed
  over different denominators may not be reported as `unchanged`, because that is
  an affirmative claim about a comparison that was never valid.

  *The precedent is `config_changed`*, and it is exact. That flag exists for the
  same shape of problem — two runs whose scores are real but whose comparison is
  weakened by something outside the scores — and it answers it the same way: it
  states the condition, it never converts a check into a regression, and it
  leaves the reader to judge what the comparison is worth. `denominator_moved` is
  that idea one level down, applied to a single aggregate rather than to a run.

  *It must be visible in both locales*, by this section's own exhaustiveness
  rule: a `TallyKind` added without a sentence in `TEXT` for every locale and a
  line in the JSON fails at type-check. That is not a nicety here. The defect
  being closed is precisely that the terminal `compare` and `explain` said
  **nothing** while `--json full` said `unchanged`, so a fix reaching only the
  JSON would leave the two surfaces disagreeing in the other direction.*

  *Amended 2026-09-18 by the delta-pass over 0.15.1, which found the paragraph
  above describing behaviour the code did not have.* Three corrections, and the
  third is the only new decision:

  1. *"It never counts as worse" is now enforced rather than stated.* `outcome`
     kept pointing wherever the arithmetic pointed, and `counts` counted it — so
     an incomparability whose score fell was counted as `regressed`, made `worse`
     true and exited 1. `Comparison.counts` and `Comparison.of` now leave these
     deltas out, exactly as they leave out a calibration delta (ADR 0024 §4.4),
     which is the single place `worse` is computed from. The outcome stays on the
     row: a reader who wants to know which way the arithmetic pointed is owed it,
     and what it may no longer do is count.
  2. *The terminal `compare` and the document say it too.* Only `explain` and
     `--json` were reached in 0.15.1, while the clause above names the terminal
     explicitly. `Headline` carries the count and its clause sits next to the
     `worse` clause it qualifies; `summary_lines` names the check in a group of
     its own, selected by the flag and never by an outcome; and the report gives
     it a block rather than a seventh `SECTIONS` entry, because a section renders
     even when empty and a seventh would have rewritten every report ever
     rendered — `calibration_section`'s shape, for `calibration_section`'s
     reason.
  3. *A flip is not an incomparability, and rule 3 keeps precedence over it.* A
     gate that read `pass` and now reads `fail` is failing against **its own
     threshold**, which needs no reference to be true, so it stays a regression
     and still exits 1 with the denominator unmentioned. This is ADR 0006 §6's
     argument about noise, one register over: what a moved denominator withdraws
     is the meaning of a *distance*, and a flip is not one.

  *What this amendment does not do, said so that the gap is declared rather than
  discovered:* the register's line (ADR 0021 §3) is unchanged, so a run whose
  gate was incomparable is recorded in none of its three outcome numbers and
  `digline log` does not mention it. Adding a field there moves
  `REGISTER_VERSION`, which refuses every register written before it — not a
  patch's business. It is the next register move's first passenger. And
  `diff()` still reads two scores over different denominators as `same`: it has
  its own vocabulary and its own closed `DiffOutcome`, and teaching it this rule
  is the same work again rather than the same edit.*

  *Amended 2026-09-19 by [ADR 0027](0027-the-run-reconciles.md) §7:
  `unreconciled` joins the list. It counts the questions the suite put to the
  run that came back as no verdict, or as one nobody asked. It passes this
  section's test: the headline states it, and a reading that left it out would
  describe a run whose exit code it could not account for.*

  *Amended again 2026-09-18 by the delta-pass over 0.15.2, which read correction
  3 and found it true of one direction and false of the other.* That a flip is
  not a distance holds. What does not hold is applying it to `improved`: `fail`
  to `pass` is not only a statement about this run against its own threshold, it
  is the sentence *"the gate got better"*, and that is a claim about the **pair**
  — which is exactly what two different denominators withdraw. So rule 3 keeps
  precedence downward and yields upward:

  - **`pass` to `fail`** stays a regression with the denominator unmentioned, as
    correction 3 said, and the reason is an asymmetry, not a proof.
    Withdrawing it would be this rule making a run *greener*, which nothing
    here may do: red is the side digline chooses to be wrong on. It is **not**
    true that such a gate is failing whatever the reference counted. Below a
    threshold of 1.0 a shrunken denominator can move this reading too, in the
    one direction the rule allows: with the gate at 0.75 and one case failing
    on both sides, three of four is `pass 0.750000`; if the fourth case, which
    passed, errors or is suspended, two of three is `fail 0.666667`, and the
    run reads *"1 check got worse"* and exits 1 although no case got worse.
    That false alarm is accepted, and `tests/test_denominator.py` pins it so
    that it stays a decision rather than a discovery.

    *Corrected 2026-09-18: the first wording of this bullet said the gate was
    red whatever the reference counted and that a shrunken denominator could
    not corrupt it. Both are true only at a threshold of 1.0.*
  - **`fail` to `pass`** carries `denominator_moved` where the predicate holds,
    and therefore leaves `counts` and `of` like every other incomparability. The
    flip itself is untouched: this run's gate did pass, `now.status` still says
    so, and what is withdrawn is the comparison, which was never taken.

  The direction the *denominator* moved is not asked about. A reference that
  counted fewer cases is the same incomparability as one that counted more:
  what is unequal is what the two sides measured, and inequality has no
  direction. Only the flip's own direction is asked about, and the asymmetry
  above is the whole of why.

  *Why this was the half that mattered.* The advisory this rule exists for,
  [GHSA-8c38-f965-cgww](https://github.com/digline/digline/security/advisories/GHSA-8c38-f965-cgww),
  describes a gate raised from `fail` to `pass` by the operator of an endpoint —
  precisely the branch correction 3 exempted. 0.15.1 and 0.15.2 closed the
  reading for every gate whose status held, while the gate that crossed its
  threshold on the way up, the one in the advisory's own table, was still
  counted under `improved` and filed in the report under *"What got better"*. A
  rule that covers every case but the one it was written for is not a partial
  fix. Stating correction 3 as a principle rather than as a measurement is what
  let that through review, and it is the reason this amendment exists.

  *What it changes, and what it cannot.* An upward flip never moved an exit code
  — `improved` has never made a run red — so this converts nothing and closes no
  gate. It removes a count and a sentence, which is the whole of what the defect
  was: the reading. And it writes **no new phrase**. An incomparable flip prints
  what an incomparable movement already prints, in both locales and on all four
  surfaces, because a second wording for one fact is a second fact to reconcile.

Not one wide type with fifteen optional fields, and not ten types with one each.
Three is what the data has, and a union of three discriminated by `kind` is what
lets both renderers dispatch with `match` — Python's structural pattern match,
which pyright strict checks for exhaustiveness, so a `kind` added without a
sentence in both locales and a line in the JSON fails at type-check rather than
in a reader's hands. That exhaustiveness is the only reason "the prose is a
render of the list" is a checkable claim and not a promise.

**Ordering is deterministic and mirrors the document**: tallies first, because
they set the frame a reader needs before any number means anything; then the
settings that differed, because ADR 0003 §5 and ADR 0005 §5 both put what
changed above what it did; then the checks, in `SECTIONS` order — regressions,
unjudged, suspended, changes, improvements, unchanged. Two readings of one run
are identical line by line.

**The JSON carries no prose.** `compare --json` ships `Headline.sentence`, and
the difference is worth stating rather than leaving as an inconsistency: that
sentence is in the wire because a CLI gate and a customer's document must never
say two different things about one run, so the wire is where the one wording
lives. Explain's prose is *derivable from the list by construction* — that is
§2's whole rule — so shipping it would ship a derived value and invite a
consumer to parse English when the facts are right there, typed. The MCP
server's `compare` tool makes the same argument from the other side when it
hardcodes `locale="en"`: an agent is not the document's recipient.

**No total is written for this list, and that is a rule about prose rather than
about code.** This list is closed and it is *amended*, which means it grows: the
chain above is eight amendments long and each one records which release added
which kind. Keep that chain — it says when each fact arrived, and a record of
when something happened cannot go stale. What must not be written beside it is a
**count of the whole**: "eight kinds", "a ninth would be saying something the
report does not". Such a sentence is true on the day it is written and false at
the next amendment, and it goes stale in the direction that reads as complete —
it under-reports, so nobody notices.

This was not hypothetical. Both of this record's own lists carried one, and both
were found contradicting themselves in the same afternoon: `TallyKind`'s note
said a ninth kind would say something the report does not, directly above its
own entries for *the ninth*, *the tenth* and *the eleventh*; and `Headline`'s
docstring opened with "eight facts" and then numbered its way to *the
sixteenth*. `SECURITY.md` had the same shape ("seven so far" for the delta-pass
on every minor release) and `RELEASING.md` had it twice. Removed 2026-09-21,
after v0.17.1.

**The distinction is between a list that grows and a shape that is fixed**, and
it matters because the cure is easy to over-apply. *"Three states — `pass`,
`fail`, `error`"*, *"two counts, never a fraction"*, *"a case leaves the matrix
for five reasons"*, *"the eight MCP tools"*: each of those counts a set that is
closed by a decision rather than extended by a ritual, and each would have to be
**re-decided** to change — at which point the prose around it is rewritten
anyway. Those counts are load-bearing and must stay. The test is not *is there a
number in this sentence* but **does an amendment procedure exist for the thing
being counted**; if it does, the number is a claim that procedure is guaranteed
to falsify.

**And the cure belongs here, at the point of growth, rather than in a gate at
the point of reading.** A mechanical check can look for numbers; it cannot ask
whether a list has an amendment ritual, and asking the question it *can* ask
produced roughly five hundred lines of prose to read by hand for six findings.
So this is a sentence in the procedure that adds a kind, next to the chain that
records the additions: when you amend this list, there is no total to update,
because no total is written.

### 4. No reason travels, and the boundary is a type rather than a filter

**No fact carries a reason. The field does not exist.**

Not omitted at the serializer, not filtered on the way out, not gated on a
`Disclosure` — absent from the type. `CheckFact` cannot hold a `Verdict.reason`,
`TallyFact` cannot hold the stated reason a case was suspended, and neither can
be made to by a caller.

This is fixed decision 9 taken one step further than the product has taken it
before. Today the rule is enforced by functions that decline to emit:
`delta_json` refuses the verdict's reason, `run_document` refuses it along with
the suspension reason and undisclosed `Score.metadata`, and `_detail_text`
refuses to echo `AssertionDelta.reason` because it is English engine text that
would leak into an Italian document. All three are correct and all three are
*decisions a future edit can undo by adding a line*.
`tests/test_wire_boundary.py` exists precisely because that is possible.

Here the value never reaches the boundary, so there is nothing at the boundary
to get wrong. A type that cannot hold a reason cannot leak one, and the marker
suite has nothing to catch on this surface. That is the strongest form the rule
can take, and it is available here only because explain is new: nothing is
being taken away from an existing consumer.

**The trade is real and is stated rather than buried.** The report's tables have
a *Reason* column carrying the judge's own words, gated on `reasons_available`.
Explain does not, and its documentation page says so in the sentence a reader
needs: **for the judge's words, `digline report` is one command away.** The
operator's dossier does not quote them either, for the same structural reason —
it is built from the wire — and it has not been the thing anybody missed.

The rest of the boundary follows the records that already set it:

- **Suspension.** That a case was set aside is a fact about coverage and
  travels, as a count and as the case ids. The stated reason does not, exactly
  as `run_document` carries `suspended` as a boolean. A developer writes things
  like "fails on the Rossi account".
- **Artifacts.** `Disclosure(artifacts=True)` governs, by ADR 0003 §4. Without
  it a `SettingFact` about a file carries the path and the outcome `unknown`,
  and **no digest** — a digest travelling beside a withheld prompt defeats the
  withholding it travelled beside.
- **Configuration values travel**, by ADR 0005 §2: a model id and a temperature
  are measurements of the system, and `SystemConfig.redacted()` has already kept
  back the one field that is topology.

### 5. Depth is the dossier's layers 1 and 2, restricted to one run and its
reference

**What explain says**: what ran, what moved, by how much, inside or outside
which measured interval, what was suspended, what could not be judged, and which
of the three configurations differed. That is
[`examples/operator/dossier.py`](https://github.com/digline/digline/blob/main/examples/operator/dossier.py)'s
layer 1 and layer 2, which is the depth this command was asked for.

**What it must never say, because it cannot know it.** The dossier also states
the seed, the spend against a declared budget, the number of re-runs and the
stopping rule they obeyed — and it classifies: *draw*, *drift*, *structural*.
Every one of those is a fact about a **cycle**, not about a run. A single run
has no second run to not-repeat against, so the whole multi-run vocabulary is
out of reach: "did not repeat", "recurs", "again", "drift", "wobble". Explain
that reached for one of those words would be asserting a measurement nobody
took. The operator's loop keeps those layers, and keeps them because it is the
thing that ran the cycle.

**And no advice.** No sentence aimed at the reader as an instruction. Not "you
should re-run this", not "consider promoting", not "this looks stable". The
reading, not the counsel — `AGENTS.md`'s boundary applies to prose, and prose is
where it is easiest to cross without noticing, because a helpful sentence does
not look like an architectural violation. Where a reader wants counsel it is in
`AGENTS.md` and in the `operating-digline` skill, written for the purpose,
revisable on its own schedule, and marked as judgment.

This is enforced and not merely intended. The `explain.*` keys in
`report/text.py` are asserted, **in both locales**, to contain no
modal-advice token — `should`, `try`, `consider`, `recommend`, `promote`;
`dovresti`, `prova`, `considera`, `consiglia`, `promuovi` — and no multi-run
token. A boundary made of good intentions in a string table is a boundary that
rots on the first sentence somebody writes to be kind.

**Numbers are `fmt_score`, six decimals, everywhere.** The dossier renders at
four; that is an example's choice and must not be copied. Two documents about
one run printing two spellings of one score is precisely what the rule keeping
ISO dates and the decimal point out of localization exists to prevent.

### 6. The exit code gates, like `report`

**With a baseline**, `explain` exits `exit_code(headline(comparison, run,
baseline))` — 1 on a regression, 2 on a case that could not be judged, 0
otherwise, with the precedence `exit_code()` already owns.

**Without a baseline**, `_report_single`'s rule holds unchanged: never
`EXIT_WORSE`, because "worse" is a relation and there is nothing here to be
worse than; `EXIT_UNJUDGED` survives, because a case the suite could not judge
is a fact about the harness rather than about a reference.

Not `diff`'s rule, and ADR 0008 §1 is what decides it rather than a preference.
`diff` exits 0 whatever it reports because **a verdict exists only against an
approved reference** and neither of its runs was approved by anybody. Explain
with a baseline *has* that reference — the same one `compare` gates on, the same
one `report` gates on, signed by the same person. Withholding the gate here
would mean the product exits 1 on a one-line summary of a regression and 0 on
three paragraphs about the same regression, which teaches a reader that the exit
code is decoration.

### 7. A terminal reading, and `--out` is what would change that

**`--locale` defaults to `en`.** `CLAUDE.md` splits the locale rule on
*document* against *terminal*, and ADR 0008 §2 already applied the split to a
command whose name contains the word "report": what decides is the recipient,
not the vocabulary. Explain writes to a terminal, for the developer, so it takes
the terminal rule.

**There is no `--out` in 0.7.0, and that is what keeps the rule honest.** The
moment explain writes a file, that file has a recipient who did not choose
English, and `--locale` becomes mandatory as it is on `report`. Shipping `--out`
with a defaulted locale would bend the distinction quietly and permanently.
Both locales are written now regardless — as ADR 0008 §2 did for diff — so that
a document form, if it comes, takes the mandatory flag and finds its strings
already there.

### 8. Compatibility

**`SCHEMA_VERSION` stays at 9.** Explain reads what is already recorded and
records nothing. No run needs migrating, no baseline needs re-promoting.

**`OUTPUT_VERSION` stays at 1**, by the precedent ADR 0008 §7 wrote for `diff`:
a *new command's* output breaks no existing consumer, because nothing that
parses `compare --json` today sees a byte change.

The word matters and is chosen deliberately: the no-bump case here is **"a new
command"**, not "additive". The fact list is a new top-level shape, not a key
added to an existing document, and calling it additive would license adding
shapes to `compare --json` later under a word that was never about that.
`OUTPUT_VERSION`'s comment gains a line saying `explain --json` is under the
same contract from the start.

**No seventh MCP tool in 0.7.0.** `wire.explain_json` makes one trivial, and
that is exactly the reason to wait: the server's surface is six entries chosen
one at a time, and the sixth is deliberately not `promote`. A tool is added when
something needs it, not when it becomes easy.

## Consequences

**The dossier an example built by hand becomes the product's.**
`examples/operator/dossier.py` keeps the layers explain cannot reach — seed,
spend, the stopping rule, the classification — and those are the layers that
justify it existing separately. What it stops re-deriving is the product's own
facts.

**Three prose renderings of one comparison now exist, and all three are bound to
the report.** `compare`'s summary lines go through `_detail()`, the report's
tables go through the same `_detail()`, and explain goes through the fact list
that §2's visibility gate ties back to the report. There is no path by which two
of them describe one delta differently without a test failing.

**Somebody will ask explain what to do and will not be told.** That is the
design, not a gap, and the documentation page says where the answer lives.
The failure mode being avoided is worse and quieter: an instrument that gives
advice is an instrument whose advice gets followed, and nothing in a run file
knows whether a dip is worth a person's afternoon.

**The no-advice gate will one day fail on a sentence somebody wrote to be
helpful.** That is the gate working, and the fix is to write the sentence
without the modal verb — or to decide, in a record, that the boundary moved.

**A fourth `kind` will be wanted.** When it is, pyright's exhaustiveness check
makes the cost visible up front: a sentence in both locales, a line in the JSON,
a case in each renderer, and a fact that has to survive the provenance gate.
That is the right amount of friction for adding something the report does not
already say.

## Alternatives considered

**`digline report --explain`, or a verbosity flag on the report.** Rejected: the
report is a document with a recipient and a settled shape, and a flag that
tripled its length would make one artifact into two that a reader could not tell
apart by name. The report compresses on purpose.

**Prose in `explain --json`.** Rejected in §3. It ships a derived value and
teaches a consumer to parse English when the typed facts are beside it.

**A model writing the reading.** Rejected flatly. A deterministic document is
comparable, diffable, testable and free; a model's is none of those and is
already provided for — it is layer 3 of the operator's alert, where it is
labelled as the operator's opinion and never as digline's verdict. The
instrument measures; the operator opines; the document keeps them apart, and
this command is on the instrument's side of that line.

**Reusing `Headline` as the fact list.** Rejected: it is eight booleans and
counts with no case or assertion refs, and it is a *compression* — the thing
explain exists to expand. Passing it to explain would mean explain re-deriving
the details from the `Comparison` anyway, which is two sources for one truth.

**One wide `Fact` dataclass with every field optional.** Rejected in §3. It is
the shorter diff and the weaker type: a renderer over it is a chain of `if
fact.case_id is not None`, exhaustiveness is unprovable, and a `kind` added
without its sentence ships silently.

**`--case` and `--check` filters.** Deferred, not rejected: a filter before
there is a reading to filter is a surface invented ahead of its use. When the
reading is long enough that somebody asks to narrow it, the request will say
which axis it wants narrowed.

## Test plan

Beyond a failing case for every new rule, which the conventions already require:

**The provenance gate.** Every fact produced for a fixture run carries a source
that is an object in the `Comparison`, the `Run` or the `Headline` the report is
rendered from. Structural, no strings, and it is the check that would catch
explain quietly computing a number of its own.

**The visibility gate.** For each fixture, every fact's anchors — `case_id`,
assertion name, `fmt_score(before)` and `fmt_score(after)`, the setting's name,
the file path, the count — appear in `render_html(...)` for the same run and
baseline, in both locales. In the no-baseline scope the same assertion runs
against `render_run_html(...)`. Explicitly **not** against `summary_lines`,
which truncates.

**The no-advice gate.** Every `explain.*` key in `TEXT`, in `en` and `it`,
contains no modal-advice token and no multi-run token. The list of tokens lives
beside the test with the reason for each, so that adding one is a decision
somebody reads.

**No reason on the surface.** `tests/test_wire_boundary.py`'s marker suite is
extended to drive `explain_json`, planting the verdict reason, the suspension
reason, the undisclosed metadata, the artifact text and the withheld host. The
expected result is that the markers cannot be constructed into the output —
which, by §4, is a property of the types rather than of the function, and the
test says so.

**Both scopes.** With a baseline and without. The no-baseline reading is
asserted to contain **no comparative sentence at all** — the same discipline
`_run_answer` follows when it refuses to print a tally of outcomes as six
zeroes, because a zero there would say "nothing regressed", which is the one
thing that document must not say.

**The exit codes, all five paths.** 0, 1 and 2 with a baseline; 0 and 2 without;
and never 1 without. The last is the test to read first if §6 ever looks like it
stopped being true.

**Precision.** One fixture score is asserted to render identically in explain
and in the report — the check that would catch the dossier's four decimals being
copied in.
