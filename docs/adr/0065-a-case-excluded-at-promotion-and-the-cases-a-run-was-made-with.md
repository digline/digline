# ADR 0065 — A case excluded at promotion, by name, and the cases a run was made with

- Status: accepted 2026-11-13, by Alessandro Prandini, proposed the same day
  by a first use outside the project, on a Java application with a judged
  suite. Part of decision B was ruled on 2026-11-13, in the conversation of
  the session that wrote this record: the cases are read **beside**
  `config_hash` and never inside it. It is stated here in this record's own
  words. Accepted as proposed, with the points this record left to acceptance:
  the three limits of §1, and no new field in §2. Not built yet: the
  construction is a pull request of its own.
- Shipped: unreleased
- Date: 2026-11-13
- Opens: `SCHEMA_VERSION`, by one key on the reference (§1), under
  [ADR 0014](0014-what-may-ride-a-schema-bump.md) §1's passenger rule. No
  `OUTPUT_VERSION`: every key this record adds to `--json` and to an MCP
  response is an added key, under the rule `src/digline/wire/contract.py`
  writes beside each one. No `RECORDING_VERSION`, and no entry in the layout of
  `.digline/<tenant>/`
- Amends, by a dated note beside the place it amends, which points here, the
  text kept as written: [ADR 0002](0002-three-worlds-and-where-the-data-lives.md)
  §8, which gains a thirteenth condition (§2)
- Leaves as written: [ADR 0014](0014-what-may-ride-a-schema-bump.md) §1, cases
  outside `config_hash`; [ADR 0017](0017-the-journal-and-the-resumed-run.md)
  §6, `cases_digest` a journal field that *"never joins `config_hash`"* and is
  never written to a run; [ADR 0036](0036-the-name-table-and-the-process-that-owns-it.md),
  the run key `key_of(created_at, config_hash)`
- Assumes: fixed decision 3, no vacuous green; [ADR 0023](0023-capture.md)
  §1, `promote` on the *approve* side of the line, where a person decides;
  [ADR 0053](0053-promote-refuses-a-pin-nobody-named.md),
  the precedent for a promotion that accepts something by name;
  [ADR 0059](0059-a-reviewed-answer-a-grouped-listing-a-source-as-data.md) §1,
  the reviewed answer and the person's mark, `--by NAME`

## Context

A first use outside the project removed a case from its suite after a run.
The case was a reviewed answer the judge had contradicted, and the person
decided the case itself was wrong, not the judge. The run could no longer be
promoted, and nothing the person could type would promote it.

**Measured at `7264c725`, with a saved script**: a suite of two cases,
`kept` and `said-no`, the second a reviewed answer, a no, that the judge
passed. The suite was run. Then `said-no` was removed from `suite.py`, and the
run was promoted. Promote exited 64:

> run …-e0d667532bb3c666: the judge contradicted a person on 1 reviewed
> answer, by answer said-no (passed a no). […] Promote a run whose every check
> agreed with every person

It names a case the suite no longer declares. Four facts make that so.

1. **The refusals about verdicts read the run alone.**
   - `promote` reads two things from the suite: the configuration in force,
     through `config_hash`, and the declared case ids, `Declared`.
   - The ids serve condition 10 alone ([ADR 0049](0049-a-run-that-judged-nothing-does-not-pass.md)
     §3, `src/digline/core/declared.py:66`).
   - Conditions 3 (an errored case), 5 (a calibration case out of band) and 12
     (a contradicted reviewed answer) read the run's results, every case the
     run carries, declared or not (`src/digline/store/promotion.py:89`).
   - So a case the suite dropped still refuses the run it was measured in.
2. **There is no way to leave a case out of a reference.** `promote` takes a
   run and writes all of it, by design: a reference is a measurement somebody
   can state ([ADR 0002](0002-three-worlds-and-where-the-data-lives.md) §8).
   The remedy every refusal names is *"run the suite again"*. Here that costs a
   whole judged run to drop one case the person had already ruled out.
3. **The command line cannot ask whether a run is promotable.** `digline view`
   can: its page asks `promotion_refusal` before a person promotes
   (`src/digline/cli/view.py:880`). The command line asks by promoting.
4. **A run made with other cases than the suite's is not told apart.**
   `config_hash` (`src/digline/core/run.py:2390`) covers the checks, their
   thresholds and tolerances, the samples, the declared price and the floor
   widths. It does not cover the cases, on purpose, by its own docstring and by
   ADR 0014 §1. Measured with the same script: a run of `{kept}`, then `added`
   declared in `suite.py`, then the run promoted. Exit 0, with the same hash
   before and after. The reference does not cover a case the suite declares,
   and nothing said so.

**What the run already records.** The run document carries the id of every
case it ran, in `results`. In the measurement it was `['kept', 'said-no']`. And
`compare` already pairs two runs case by case. A case on one side only is
`new` or `missing`, listed under *What was added or removed*. So the case ids
are already in every run and every reference. What is missing is a reading of
them **against the suite in force**, at `promote` and in `where`.

## Decision

### 1. A: `promote --exclude CASE`, by name, recorded in the reference

*Decided.* `digline promote` takes `--exclude CASE`, which may be repeated.

- **The reference is written without that case's result.** The run file is not
  touched: the run records everything it measured, and stays the measurement.
- **The reference records the exclusion** as one key,
  `excluded_at_promotion`. It is a list of `{case_id, by, at}`:
  - `case_id` is the case left out;
  - `by` is `--by NAME`, mandatory whenever `--exclude` is given and never
    read from git's configuration or the environment, for ADR 0059 §1's
    reason: the mark is the person's own;
  - `at` is the promotion's `promoted_at`.

  The key is absent where nothing was excluded, and that is what absent means
  on a document written before this record.
- **The refusals read the run without the excluded cases.** Conditions 3, 5,
  6, 10 and 12 are asked of the results the reference will hold, never of the
  ones left out.
- **`compare` says it as a fact** while that reference is in force:
  *"1 case excluded at promotion: said-no, by NAME, 2026-11-13"*.
  - In the text, the run report, `compare --json`, `explain` and the MCP
    server's `compare`.
  - It is a fact about the reference, beside `promoted_at`. It is not a
    movement, and it changes no exit code.

*Decided here, beyond the brief, and accepted with the record.* Three
limits on what `--exclude` accepts, each refused by name:

1. **A case the run does not carry** is refused, as a typo would be.
2. **A case the suite still declares** is refused. Excluding a case that
   still gates would get round conditions 3, 5 and 12 for a case the suite
   still asks about. A person who means it no longer counts removes it from
   the suite, and that change is reviewed where the suite is.
3. **A run with run-level verdicts** is refused when anything is excluded. An
   aggregate was computed over every case the run carries, the excluded one
   among them, and a reference must not hold a figure its own cases did not
   produce. The remedy is to run the suite again. Recomputing the aggregate
   over the remaining cases is *not decided here*.

### 2. B: the cases a run was made with, read beside `config_hash`

*Ruled 2026-11-13: beside `config_hash`, never inside it.* The run keys, the
existing references and ADR 0014 §1 do not move.

*Decided, on what was measured:* **no new field.** The fingerprint is the set
of case ids the run already carries in `results`. *Alternatives considered*
gives the reason, and lists the form the ruling named, a digest over those
ids. *Corrected at acceptance, 2026-11-13: this sentence said "§3 gives the
reason", which it never did; the reason is in* Alternatives considered.

What is read, and where:

- **`promote`: a thirteenth condition, `CasesChangedError`.** Promote compares
  the run's case ids, less the excluded ones, with the suite's declared ids,
  `Declared.subject | Declared.watching`, and refuses where they differ.
  - It names each case the suite no longer declares, with the remedy
    `--exclude CASE --by NAME`.
  - It names each case the suite declares and the run lacks, with the remedy
    *run the suite again*.
  - It is asked **before** conditions 3, 5 and 12. In the measured case, the
    person is told first that the run holds a case the suite dropped, and
    which flag says so. They are not sent to the judge first.
  - ADR 0002 §8 takes a dated note.
- **`compare` between two runs** is unchanged in what it pairs. Today it does
  not compare a case present on one side only: it lists it as `new` or
  `missing`. It gains one fact where the two case sets differ: *"cases
  changed: 1 added, 1 removed"*, naming them. The fact goes in the text and,
  as an added key, in `--json` and over MCP. It never makes the run *"suite
  changed"*: the checks did not change, and the cases both sides share are
  compared as before.
- **`where`: a state `cases_changed`**, asked after `never_run` and before
  `judge_disagrees`. The newest run's case ids differ from the suite's
  declared ids, and the next step is to run the suite again, or to exclude at
  promotion.
  - Without it, a contradiction on a case the suite dropped would hold the
    page at `judge_disagrees`, about a case that no longer exists.
  - The order lives in `src/digline/host/where.py`'s docstring, which no ADR
    rules. It is amended there, with this record cited.
- **Existing references.** Each carries its own case ids. It reads, compares
  and promotes as it did, with no migration of its own and no double
  fingerprint during a transition: there is nothing new to fill in. The
  schema step in §1 is the exclusion's, and it invents nothing.

### 3. What stays out

- **No `--exclude` on `run`.** The run records every case it was asked, and a
  run that left a case out by choice would be a measurement of a suite nobody
  declared.
- **No silent exclusion, anywhere.** A case leaves a reference only by
  `--exclude`, with a name, a person and a time. It is said by every
  `compare` against that reference. Nothing infers an exclusion from the suite
  file, a refusal, or a missing case.

## Alternatives considered

- **Ignore, at `compare`, a case the suite no longer declares.** Rejected.
  - `compare` reads two documents and is pure: reading the suite would make the
    same two runs compare differently on two checkouts.
  - It is silent: the reference would keep a contradiction nobody approved,
    and nobody would read that it was dropped.
  - It does nothing for `promote`, where the use was stuck.
- **`promote` re-reads the suite and drops the cases it no longer declares.**
  Rejected.
  - It is the silent exclusion §3 refuses.
  - A case deleted by mistake, or a checkout of another branch, would quietly
    shrink the reference a person signs.
  - The person would sign a reference without being told it was smaller than
    the run.
- **The case ids inside `config_hash`.** Rejected by the ruling.
  - ADR 0014 §1 keeps cases outside the hash, and ADR 0017 §6 keeps
    `cases_digest` out of it, *"or it would unpromote every baseline the first
    time somebody fixed a typo in a case"*.
  - Ids alone avoid the typo. But any case added, removed or reordered would
    still move the hash, and with it every run key (ADR 0036).
  - Every added case would make each run *"suite changed"* against its
    reference, which is the outcome ADR 0014 §1 was written to prevent.
- **A digest over the case ids, written beside `config_hash`.** The form the
  ruling named. *Not adopted*, on the measurement above:
  - the ids it would digest are already in every run and every reference;
  - every reading this record needs, promote's, `compare`'s and `where`'s,
    has to name the cases, and a digest names none;
  - it would be one more string for the projection gate to classify
    (`tests/test_projection_gate.py`, ADR 0034 §4), and a second schema key
    with nothing to fill in on the documents already written.

  Accepted without it.
- **A `promote --dry-run`.** Not adopted. With §1 and §2, every refusal
  `promote` can raise about the cases names its own remedy, and a refused
  promotion writes nothing, so a refusal is already a dry run. It is said here
  so it is not read as forgotten. `digline view`'s page keeps asking
  `promotion_refusal` as it does.

## Compatibility: a minor, and why

By `RELEASING.md`'s *Choosing the version*, from 1.0.0:

- **No public Python signature breaks.**
  - `digline.host.promote` gains two optional keyword parameters, the
    excluded cases and the person's name, each with a default that excludes
    nothing.
  - `ResultStore.promote_baseline` gains the same pair. It is the shape
    `accepting_pins` took under ADR 0053.
  - No name is removed or renamed, and no parameter becomes required.
  - **Declared cost:** an implementation of `ResultStore` outside digline must
    accept the two parameters to keep satisfying the protocol, as it had to
    for `accepting_pins`.
- **`SCHEMA_VERSION` moves**, with `digline migrate` as the way through. Its
  step invents nothing: absent is *nothing excluded*. The stored document's
  shape may move in a minor.
- **The command line changes, and may in a minor**, which the criterion says
  by choice:
  - a new option;
  - a new state in `where`;
  - a new refusal, `CasesChangedError`, exit 64 as every promotion refusal.

  A script that promoted a run made before a case was added now gets a refusal
  where it got exit 0. That is the change, and it is the point.
- **No `OUTPUT_VERSION`:** the keys are added keys.

## Not decided here

- Recomputing a run-level aggregate over the cases a reference keeps (§1,
  limit 3).
- Which schema train the key rides: the cut's, by ADR 0014.
- How a projected reference carries `by`. `case_id` becomes a token, as every
  case id does (ADR 0034 §4). `by` is a person's name, and the projection gate
  classifies it with the change that builds this. The proposal is a token,
  resolved only where the store is.

## Test plan

- The measured case, as a test: run, remove the reviewed answer, promote.
  - Today it is refused by 12. Under this record it is refused by 13, naming
    the case and `--exclude`.
  - With `--exclude said-no --by NAME` it promotes: the reference lacks the
    case and records the exclusion, and the run file is byte-identical.
- The three limits of §1, each refused by name, each with a control that
  promotes.
- The mixed case, first: a run with one dropped case
  and one added case. Both are named by 13.
- `compare` against a reference with an exclusion says the fact in every
  front end, and its exit code is the one it was without it.
- `where`: `cases_changed` before `judge_disagrees`, and its control, a run
  whose ids equal the declared ones, still reaching `judge_disagrees`.
- A run written carries every declared case: held by a test, because this
  record's §2 rests on it. Measured on the one shape above, not proven.
- Every assertion mutated once, the mutation caught, as `CONTRIBUTING.md`
  says.
