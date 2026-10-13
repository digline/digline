# ADR 0049 — A run that judged nothing does not pass, and a front end does not say green where digline did not

- Status: proposed 2026-10-13. **What it decides was ruled before it was
  written.** The maintainer ruled the exit code, the promotion and the two
  levels of a suspension on 2026-10-13, on #360 and #374, and the plugin's rule
  the same day, on #484. The three comments carry the rulings verbatim, in
  Italian. The same day he ruled five points of this record's design, and
  corrected one of his reasons from a reading of the code (§4). The parts
  marked *decided here* were not ruled; acceptance rules on them one by one,
  and on the text as a whole
- Shipped: unreleased
- Date: 2026-10-13
- Opens: **an added key on the wire**, recorded in `_ADDED`
  (`src/digline/wire/contract.py`). No `OUTPUT_VERSION` move, by that module's
  rule for an added key. **An added key in the register's `outcome` block**
  with no `REGISTER_VERSION` move, and the reason is §4's. No
  `SCHEMA_VERSION`: an exit code is computed from a run, and nothing digline
  writes into a run document changes
- Requires, at implementation: **a tenth promotion condition** in
  `ResultStore.promote_baseline`'s list and in ADR 0002 §8's, with a new
  refusal type in `REFUSALS` (§5). **A sentence in every locale** of
  `report/text.py`'s `TEXT`, for the new headline fact (§4). **A rule in
  pytest-digline** at the end of a session (§7)
- Assumes: [ADR 0001](0001-verdict-not-score.md) §1 (an error is a third
  state, neither green nor a regression); [ADR
  0002](0002-three-worlds-and-where-the-data-lives.md) §8 (the promotion
  conditions) and §10 (an empty denominator is `error`, never `1.0`); [ADR
  0008](0008-the-two-run-report.md) §2 (the exit code is the contract); [ADR
  0016](0016-the-canary-case.md) and [ADR
  0024](0024-the-judge-as-an-instrument.md) §4 (a canary and a calibration case
  watch the instrument, not the subject); [ADR
  0021](0021-the-register.md) §5 (the register is a format, and nothing
  migrates it); [ADR 0041](0041-the-exit-code-of-a-failure-nobody-anticipated.md)
  (the table of codes)
- Narrows: [ADR 0010](0010-per-group-aggregates.md) §8 (*"nothing here
  should"* holds where something was judged); [ADR
  0027](0027-the-run-reconciles.md), *Not decided here*
  (its exit-code half, kept only where nothing was judged); ADR 0002 §8 (a
  tenth condition); [ADR 0013](0013-the-pytest-plugin.md) §1 (*"it never
  fails, so it disappears into `0`"*, kept at the level of the case) and §7 (a
  session in which digline did not say green is not green). Each carries a
  dated note naming this record, five notes on four records
- Touches, in `CLAUDE.md`'s *fixed* section: **nothing.** It does not amend
  **decision 3**, *no vacuously green assertion*. It carries that decision's
  reason to a place the decision's letter does not reach, as #360 had already
  distinguished: *"The exit code is not an assertion, so the decision does not
  reach it by its letter. The reason behind it does."* **It touches the exit
  code contract**, which `AGENTS.md` §6 states and ADR 0008 §2 makes the
  contract, by adding a fourth cause to `2`
- Number: 0049. Swept on 2026-10-13, before a line was written, across
  `origin/main` (`208e1c1`), every local and remote branch and tag (80 refs,
  after a fetch with `--prune`), the worktrees of this repository (only `main`)
  and the open pull requests (none). The highest number taken anywhere is 0048

## Context

**#360: a run that judged nothing exits `0` and can be promoted.** A first
round whose every case is suspended exits `0`, and `promote` makes it the
suite's reference. The next round then reads every check as *new here* under
*"Nothing got worse compared with the reference."* A run document with no
cases, which digline cannot produce but reads, does the same. Both come from
`exit_code`'s rule. A later round that judged nothing exits `0` against a good
reference too: that needs no promotion and is not limited to a first round.

**#374: an errored run-level figure moved nothing.** A run whose only error is
an aggregate's, for instance an `Accuracy` over an empty denominator, exited
`0` and could be promoted. #375 (`efe7586`) made promotion refuse it, which ADR
0002 §8's condition 3 already said (*"one or more verdicts"*). The exit-code
half stayed open, because two accepted records disagree on it:

- **ADR 0010 §8:** an errored aggregate *"moves no exit code … Nothing here
  alters that, and nothing here should"*, because under `by_group` *"small
  groups will error, routinely"*;
- **ADR 0027, *Not decided here*:** *"An errored figure is a number we do not
  have, and exiting 0 asserts that nothing got worse on the strength of a
  measurement that is missing."* It assigned the change to "the next minor".
  Neither record answers the other's argument.

**#375 left an asymmetry inside #360.** After it, a run whose cases are all
suspended is refused at promotion **only if** the suite declares an aggregate,
because the empty denominator errors the aggregate and condition 3 refuses
that. The same fact, *nothing was judged*, became promotable or not by a
declaration that has nothing to do with it. Measured in #360's comment of
2026-10-02, through `execute()`, `compare()`, `headline()` and `refusals_for()`.

**The rule behind both, read.** *"A suspension never fails: it is a decision
someone already made, not an outcome"* arrived with the first commit
(`ae4a2af`, 2026-08-26) in `exit_code`'s docstring. No ADR deliberates it, and
no commit message discusses it. ADR 0013 §1 builds on it without examining it:
its `SKIPPED` mapping exists because a suspension *"never fails, so it
disappears into `0`"*. **A rule that was never deliberated contradicted one
that was.** With every case suspended and an aggregate declared, ADR 0002 §10
says the figure is `error`, a number nobody has, and the suspension rule said
`0`. The undeliberated one won.

**#484, read again.** pytest-digline exits `0` on a session in which `digline
compare`, on the same store, exits `2` because a pinned file drifted. #484
called it open whether the plugin should gate on a pin. It is not a question of
telling `2` from `1`, which ADR 0013 §7 leaves open. **It is the plugin
discarding a `2` that digline has already emitted.** That is the same defect as
#360's consequence on the plugin: a session in which every row is `SKIPPED`
exits `0` where digline, under §3, does not.

**The rulings, 2026-10-13.** In English, and in the maintainer's order. The
verbatim text is on #360 and #374 (the first six) and on #484 (the seventh).

1. Exiting `0` asserts a measurement. Where the measurement was not made, `0`
   is false.
2. Something judged and something in error: it stays `0`. There is a partial
   measurement, the verdicts say what they say, and the figures in error are
   visible. ADR 0010 §8's argument from cost is honoured where it was made.
3. Nothing judged: the exit is not `0`. Zero verdicts, whatever the cause:
   every case suspended, or a document with no cases. It is ADR 0027's case
   to the letter.
4. The code is not `0`, and it is not the one that means a regression: a run
   that could not be judged is an absence, not a worsening.
5. A run that judged nothing is never promotable, whether or not the suite
   declares an aggregate. It closes #375's asymmetry: a reference is a
   measurement, and what did not measure cannot be one.
6. *"A suspension never fails"* holds at the level of the case and falls at
   the level of the run. A suspension does not fail; a run of suspensions only
   does not pass.
7. The plugin does not say green where digline did not say green. One rule,
   not four cases: it covers `unjudged`, `scale_lost`, `pinned_drifted` and the
   new cause.

## Decision

### 1. Exiting `0` asserts that a measurement was made

`0` says *nothing got worse*, and that sentence is about something that was
measured. Where nothing was, `0` is not a weaker answer: it is a false one.
This is decision 3's reason, *a green that could not have been red*, applied
to the exit code, which decision 3's letter does not reach. Decision 3 is not
amended.

### 2. Something judged and something in error: `0`

**A run-level figure in `error` beside cases that were judged leaves the exit
code where the cases put it.** The verdicts say what they say, and the errored
figure is visible: an `errored` delta, a line in *What could not be judged*, a
field in `compare --json`. ADR 0010 §8 holds here, and its argument is kept
where it was made: under `by_group` a small group errors routinely, and
reddening every such run would make the gate cry wolf about a suite that asked
a question its groups cannot answer.

ADR 0027's general case, *every errored figure moves the exit code*, is
declined. Its sentence stays true where nothing was judged (§3).

**What this section does not change.** A **case** whose verdict is in `error`
still makes the run exit `2`, as it does today through `Headline.unjudged`.
This section is about run-level figures, the aggregates, which #374 was about.
It does not make an errored case pass.

### 3. Nothing judged: `2`

**The definition.** *Decided here, on the maintainer's ruling of the
principle:*

- **A case measures the subject** when it is neither a canary nor a
  calibration case. A canary says the model behind the alias is still that
  model; a calibration case says the judge still reads its scale. Both say the
  apparatus works. Neither says anything about the behaviour the suite is
  about, which is what `0` claims did not get worse.
- **A case is judged** when at least one of its verdicts is `pass` or `fail`.
- **A run judged nothing** when no case that measures the subject was judged.

**Aggregates do not count.** An aggregate is a figure over the cases, so it
cannot be the evidence that the cases were judged. And if it counted, #375's
asymmetry would come back: whether a run judged anything would depend on
whether the suite declared a figure. **Canary and calibration cases do not
count, for the same reason.** One rule: only a case that measures the subject
counts.

The definition covers every cause the ruling names: every case suspended, a
document with no cases, and a run whose every subject case errored. The last
already exits `2` through `unjudged`, and this does not change it.

**The code is `2`, `EXIT_UNJUDGED`.** Its public meaning is already this case's
sentence. `AGENTS.md` §6: *"`2` stop — the run could not be judged, and nothing
downstream of it is meaningful"*. digline-action's README and `action.yml` say
*"2 the run could not be judged"*. It is not `1`, which means a regression (the
ruling's fourth point). It is not a new code, which every consumer would have
to learn.

**It holds for both functions and every round.** `exit_code(head)` returns
`2` when the run being judged judged nothing, at any round and against any
reference. `run_exit_code(run)`, the first round's code, returns `2` for the
same run. The invariant `tests/test_run_exit_code.py` holds, that
`run_exit_code(run)` equals `exit_code` of the run compared with itself, holds
after this as before.

**Precedence.** A run that judged nothing has no check that could have got
worse, so `1` cannot arise from its cases. A canary that moved can still
return `1`, and it outranks this, as it outranks every cause of `2` today: it
is a fact about which model answered, and the louder fact is the one reported.

### 4. Saying which cause

`AGENTS.md` §6: *"the headline says which"*. So the fact is the headline's.

- **`Headline.nothing_judged: bool`**, beside `unjudged`, `scale_lost` and
  `pinned_drifted`. *The name is decided here.* `exit_code()` reads it.
- **On the wire:** the key `nothing_judged` in every headline document, with
  its entry in `_ADDED`. No `OUTPUT_VERSION` move, by that module's rule for an
  added key.
- **In the report and the terminal:** a sentence of its own in every locale of
  `TEXT`. The wording is the implementation's, held by the rule that the
  report and `compare` say the same thing, through `headline()`.
- **`exit_code`'s docstring** enumerates the causes of `2` and gains this one.
- **`AGENTS.md` §6 is corrected in place.** It says *"`2` has two causes as
  well"*, and `exit_code` already enumerates three: the pinned file joined with
  ADR 0029 §6. With this record there are four. No annotation, because it is a
  document that describes current behaviour.

**In the register, the field enters the `outcome` block, and
`REGISTER_VERSION` stays `1`.** Two questions, and two different rules answer
them:

- **Where the field goes** is ADR 0021's to decide: the `outcome` block is
  *"`Headline`'s facts minus the one that is prose"*. `nothing_judged` is a
  fact of the headline and is not prose, so it goes inside `outcome`.
- **Whether the version moves** is decided by the rule written on
  `JOURNAL_VERSION` (`src/digline/store/protocol.py`): *"where a reader that
  ignores a key would misread rather than miss, the version moves."* A reader
  of format 1 reads the `outcome` block by name and ignores a key it does not
  know. It would **miss** this fact, not misread it, because `exit_code` on the
  same line still says `2`. So the version does not move.

*Corrected 2026-10-13, by the maintainer.* His ruling first gave ADR 0021's
rule as the reason for both answers: the field enters `outcome`, so
`REGISTER_VERSION` moves. That rule decides the first question and not the
second. The correction came from this record's reading of the code, before a
line of it was written. The alternative it closes is under *Alternatives
considered*.

**The field is optional, its absence means "not declared", and nothing is
inferred from its absence.** *Ruled 2026-10-13.* A line written before this
record carries no `nothing_judged`. A reader of format 1 that meets such a
line reads the field as absent. **Absent is not `false`**: it does not say that
something was judged. It says the line was written by a digline that did not
record the fact. This is ADR 0014's rule, a migration that invents nothing,
applied within one version instead of between two. Without this decision the
next reader would read the absence as a `false`.

### 5. A run that judged nothing is never promotable

**The tenth condition of ADR 0002 §8: `NothingJudgedError`**, raised for a
run that judged nothing under §3's definition, **whether or not the suite
declares an aggregate.** It closes #375's asymmetry: a reference is a
measurement, and a run that measured nothing cannot be one. *The name is
decided here.*

**A new type, not `ErroredRunError`.** *Ruled 2026-10-13.* This record exists
because a `0` said something false. Reusing `ErroredRunError` would have the
refusal say the run went into error when it did not, the same kind of false
sentence inside the refusal that corrects it.

**What it costs.** The type joins `REFUSALS` (`src/digline/host/refusals.py`),
which `docs/api.md` documents and which digline-ward imports. So the addition
appears on the surface ward reads. It is an addition: a consumer that catches
`REFUSALS` as a tuple catches the new type with no change, and one that
enumerates the types by name meets one more.

**Where it sits in the list.** With the conditions that hold whatever the
reference, before 8 (`BaselineMovedError`), which ADR 0002 §8 checks last
*"because every refusal above is about the run"*. This one is about the run. It is
added to ADR 0002 §8's list and to `promote_baseline`'s by the change that
implements it, as condition 9 was.

### 6. A suspension, at two levels

- **At the level of the case, a suspension never fails.** That stays as it
  was, and from this record on it is a deliberated rule rather than a sentence
  in a docstring. One suspended case among judged cases is a decision on the
  record, and it moves nothing.
- **At the level of the run, a run of suspensions only does not pass.** A run
  in which every case was set aside is a state no single suspension decided.

With the two levels kept apart, ADR 0002 §10 and the suspension rule stop
contradicting each other. Each holds at its own level.

### 7. A front end does not say green where digline did not say green

**pytest-digline does not end a session green when digline, for the same
runs, does not exit `0`.** One rule, for every cause of `2`: `unjudged`,
`scale_lost`, `pinned_drifted` and `nothing_judged`. If digline says the run
could not be judged and that nothing downstream is meaningful, a green pytest
session is a false sentence, as false as the `0` §1 corrects.

**`SKIPPED` stays at the level of the case, and the session's status
changes.** It is §6's separation, in pytest's vocabulary: a suspended case is
still reported as `SKIPPED` with its reason, and a session in which digline
judged nothing does not end green.

**Where the session already fails.** An unjudged case and a lost scale are
already `ERROR` rows (ADR 0013 §1, ADR 0024 §4.7), so a session with either
already exits `1`. That is read in the plugin's code. **Where it does not:** a
pinned file that drifted produces no failing row, and #484 measured the session
at `0`. A session whose every row is `SKIPPED` exits `0`, which is read from
pytest's rule and not run here. These two are what the rule changes.

**With which code.** *Decided here.* `1`, pytest's own *tests failed*, which is
what a session with an `ERROR` row already exits. Whether pytest-digline
should exit something other than `1` where digline exits `2` stays ADR 0013
§7's open question. This rule decides *not green*, not *`2`*.

## Consequences

**Who turns red, and what they do.** Suites where every case is suspended, or
every subject case is suspended beside canaries and calibration cases: `compare`,
`report` and `explain` exit `2`, MCP's `exit_code` reads `2`, and
digline-action fails the job and comments, as it does for any `2`. A pytest
session over such a suite, or over a store whose pinned file drifted, fails.
**There is no escape route and no flag.** A run that judged nothing was not
passing; it was reporting wrongly. The move is the one the suite already had:
judge something, or stop running the suite. The first question the first user
will ask is how to make it green again, and it is answered better by saying so
than by avoiding it.

**The CHANGELOG says it plainly**, in the entry, not in a note beside it:
which runs now exit `2`, which sessions now fail, and that there is no flag.
One line for digline and one for pytest-digline, which ship separately.

**Two pull requests.** The core (§1-§6: the exit code, the condition, the
headline field, `AGENTS.md`) closes #360 and #374. The plugin (§7) closes #484
and carries its own tests. It is not a tail of #360.

**What does not move.** No run document changes, and a run promoted before
this record stays the reference it is. digline-action's mapping already reads
`2`. A suite that judges at least one subject case exits exactly as it did.

**The five notes.**

- ADR 0010 §8, a second note under the one of 2026-10-13: narrowed here, and
  the paragraph holds where something was judged (§2).
- ADR 0027, *Not decided here*, under its note on #374: the exit-code half is
  decided here, and only where nothing was judged (§2, §3).
- ADR 0002 §8: a tenth condition is decided here, and joins the list with the
  change that implements it (§5).
- ADR 0013 §1, under the paragraph that says a suspension *"never fails, so it
  disappears into `0`"*: true of a case and not of a run (§6).
- ADR 0013 §7, under its note of 2026-10-13: a session in which digline did not
  say green is not green, whatever the plugin decides about `2` (§7).

## Alternatives considered

- **A new exit code for a run that judged nothing.** It would keep `2` for a
  case that errored and give this its own number. Rejected: `2`'s published
  meaning already is *the run could not be judged*, and a new code is a new
  thing every consumer has to learn, digline-action first.
- **Refuse the promotion and leave the exit code.** Closes half of #360.
  Rejected by §1: the `0` is still false, at every round, with or without a
  promotion.
- **Leave it, and say on the page why a run of suspensions is green.**
  Rejected by §1: a sentence on a page beside a false `0` does not make the `0`
  true, and a pipeline reads the code, not the page.
- **Every errored figure moves the exit code**, ADR 0027's general case.
  Rejected by §2, on ADR 0010 §8's argument from cost.
- **Four rules in the plugin, one per cause of `2`.** Rejected by §7's ruling:
  four rules can drift apart, and a fifth cause of `2` would arrive with no
  rule at all.
- **Move `REGISTER_VERSION` to 2.** Three costs, read in the code:
  - **A reader of two formats that does not exist.** The register's reader
    accepts exactly one version, `version != REGISTER_VERSION` in
    `src/digline/store/file_store.py`, and ADR 0021 §5 forbids migrating a
    line. Moved to 2, it refuses every line written so far unless it is taught
    to read two formats, which no text provides for;
  - **a value invented for every line in format 1**, against ADR 0014's rule;
  - **a mixed register refused by every older digline.** The register is
    committed and merged by union, so one line in format 2 makes a CI or a
    colleague on an older digline refuse the whole file.

  Rejected: it puts the cost on everyone who already has a register, for a fact
  an older reader does not misread.

## Not decided here

- **Whether pytest-digline should tell `2` from `1`.** ADR 0013 §7's open
  question. §7 decides only that the session is not green.
- **`digline view`'s row chip.** `_errored_cases` in `report/pages.py`
  predicts the promotion conditions from case verdicts only, as #374 left
  open. It does not predict the tenth either.
- **Whether a run document with no cases, written by another program, should
  be read at all.** It is read today, and under §3 it exits `2`.
- **Whether digline-ward reads the register.** Not verified. The names ward
  imports from `docs/api.md` include nothing of the register, but ward's own
  source was not read for it. This is not a no.

## What this record does not claim

- It does not reopen the suspension of a case. One suspended case among judged
  cases moves nothing, as before.
- It does not amend fixed decision 3.
- It does not touch the noise floor (#496) or any reading of a judged score.
- It does not say how many suites turn red. Nothing was measured on a real
  store.

## Test plan

**Nothing at merge.** This record carries no code.

**Owed with the code.** Each test must also fail against the code without the
rule it tests, or it proves nothing.

1. **Every case suspended exits `2` (§3):** at the first round through
   `run_exit_code`, and at a later round against a good reference through
   `exit_code`. Control: the same suite with one subject case judged exits `0`.
2. **A document with no cases exits `2` (§3).**
3. **Canary and calibration do not count (§3):** a run whose subject cases are
   all suspended, beside a judged canary and a calibration case inside its
   band, exits `2`.
4. **An aggregate does not count (§3):** every case suspended with an
   aggregate declared exits `2`, and without one exits `2`. The asymmetry of
   #375 is gone from the exit code.
5. **Something judged and an aggregate in error exits `0` (§2):** this pins
   ADR 0010 §8 where it holds. Control: an errored **case** still exits `2`.
6. **The tenth condition (§5):** `NothingJudgedError` with an aggregate and
   without one, and no refusal for a run with one judged subject case. It is
   in `REFUSALS`.
7. **The headline and the wire (§4):** `nothing_judged` is in `_ADDED`, and
   `tests/test_wire_keys.py` reaches it as true and as false.
8. **The register (§4):** a written line's `outcome` keys include
   `nothing_judged`. A line without it reads as *not declared*, never as
   `false`. Control: a reader that defaults the absence to `false` fails it.
9. **The invariant:** `run_exit_code(run) == exit_code` of the run compared
   with itself, for every fixture, the new ones included.
10. **The plugin (§7):** a session over a drifted pin fails, and a session
    whose every row is `SKIPPED` fails while each row stays `SKIPPED`. Control:
    a session over a suite with one judged subject case and nothing else
    exits `0`.
