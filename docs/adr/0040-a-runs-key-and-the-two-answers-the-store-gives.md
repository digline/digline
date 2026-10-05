# ADR 0040 — A run's key, and the two answers the store gives

- Status: proposed 2026-10-01. The text comes first, checkpointed before any
  code, the way [ADR 0038](0038-the-projection-of-a-run-nobody-promoted.md)
  was proposed. **The option was ruled on 2026-10-04, in discussion: C,
  checked in `scan_runs` (§4).** Four questions the ruling leaves open are
  set out in *Not decided here*, each with what is known about it, and **none
  of them is chosen**. The record stays proposed until they are ruled. The
  local repair ruled before this record (§*Context*) is recorded as ruled
- Shipped: unreleased
- Date: 2026-10-01
- Opens: **nothing on landing.** No `SCHEMA_VERSION`, no `OUTPUT_VERSION`, no
  migration. At implementation, C opens no `OUTPUT_VERSION` either: a key it
  adds to a response is an added key (§3, C, the correction of 2026-10-04)
- Requires, at implementation:
  - `scan_runs` reads `created_at` and `config_hash` from each document it
    already parses, and leaves out a file whose stem is not their `key_of`
    (§4);
  - `read_run` refuses the same file when it is addressed by its stem (§4);
  - the protocol's first sentence on `RunRef.key` reworded (§1);
  - whatever the four open questions are ruled to need (*Not decided here*)
- Assumes: [ADR 0011](0011-the-mcp-server.md) §4 (what was left out of
  a listing is a field, and a count rather than a list of paths);
  [ADR 0017](0017-the-journal-and-the-resumed-run.md) §8 (a resumed run writes
  the file the killed run was going to write); [ADR 0021](0021-the-register.md)
  (the register commits keys to git);
  [ADR 0031](0031-the-reference-promote-replaces.md) §1 (a promotion names the
  reference it replaces by its key);
  [ADR 0034](0034-the-store-outside-and-the-reference-that-names-nothing.md)
  §1 (the store can sit in the end company's perimeter);
  [ADR 0038](0038-the-projection-of-a-run-nobody-promoted.md) (a projected list
  names nothing)
- Touches, in `CLAUDE.md`'s *fixed* section: nothing. **It touches the store
  protocol's contract**, which is why #332 asks for a record before code: two
  sentences of `store/protocol.py` disagree about whose the key is (§1)
- Closes, at implementation: #332, and #429's own case (§4). Not #429's other
  refusals, which #349's ruling covers (§4)
- Number: 0040. Swept on 2026-10-01, before a line was written, across
  `origin/main` (`b3f991b`), every local and remote branch and tag, the
  `docs/adr/` of every sibling worktree, the stash (empty), the open pull
  requests (none), and the site repository's refs. The highest number taken
  anywhere is 0039

## Context

**digline answers *"what is a run's key"* in two ways.** The two answers agree
only while every file in a suite's `runs/` directory was written by `write_run`
and never renamed. #332 records the split, and F-1 of the delta-pass over
0.25.2 is how it was found.

**The two answers, at `b3f991b`:**
- **The file's stem.** `FileResultStore.list_runs` and `scan_runs` build each
  `RunRef` with `key=path.stem` (`store/file_store.py`). That feeds
  `digline view`, MCP's `list_runs`, `host.history` and `host.suite_runs`,
  and which runs `digline list` shows, though not the key it prints.
  `read_run` addresses the file by the stem, and never compares the stem with
  the document.
- **`key_of(created_at, config_hash)`.** `write_run` files a run under it.
  `resolve_key` returns it for `latest`. `compare --json` prints it,
  `promote --replacing` takes it back, `suite_runs` marks the baseline with it,
  `journal_key` restates it over a journal header, and the register commits it
  to git.

*Corrected 2026-10-04, on two points, measured at `33409a6`.*
- **`digline list` prints `key_of`, not the stem.** The text above said the
  stem feeds `digline list`. It feeds only which runs are listed: `cmd_list`
  prints `key_of(run.created_at, run.config_hash)` on every row
  (`cli/main.py`). So for a renamed run, `list` prints a key that `read_run`
  does not answer to. It marks that row `*` as the baseline, and below the
  table it says *"the run the baseline was promoted from, … is not among the
  runs read"*. `digline view`, over the same store, lists the run under its
  stem, with no baseline mark. So the split shows up inside `list`'s own
  output, as well as between the two front ends.
- **F-1 stated that renaming is an ordinary mistake. It did not observe one.**
  The text below said F-1 *found* it. Run files are gitignored, so git cannot
  record a rename, and no run file has ever been tracked. The 64 local run
  files swept on this date have no stem that differs from its `key_of`: 42 in
  `examples/`, the other 22 in the stores of two other projects. No record,
  friction or issue reports a rename met in use. Every renamed file in the
  records was made on purpose by a probe. **So the case §3 prices every
  option against is hypothetical.**

**What is already ruled: B, the local repair.** It was built for F-1 and merged
as #333. On a projected list, a readable run is listed only if its stem is its
`key_of`. A refused file is named only if its stem has a run key's form
(`is_run_key`). Everything else is counted in `SuiteRuns.unnamed`. **B repairs
the projected page and leaves the split as it is.** #332 is the question of the
split itself.

**A second door into the same split: #429.** `resolve_key` reads every run the
scan lists, with nothing between the scan and the read. `scan_runs` lists every
`*.json` under its stem and never checks the stem against the name rule, and
`read_run` checks it first, through `run_path` and `_check_name`. So one file
whose name is not a safe segment fails `--run latest` for the whole suite.
#429 measured it with a Finder copy, `<key> copy.json`, on `33409a6`. It was
found while gathering material for this record, not by a user.

## 1. What the store protocol says today

`RunRef`, in `store/protocol.py`:

> `key` is a string chosen by the store, not a path: a store backed by a
> database or by remote object storage must be able to use this same type.

`ResultStore.write_run`, in the same file:

> **The key is the document's, not the backend's:**
>
>     write_run(run).key == key_of(run.created_at, run.config_hash)
>
> Stated here because nothing checks it. It held while one store existed and
> computed the key itself; a second backend is free to file the run wherever
> it likes, and not free to name it something else.

**What the two sentences say together.** The invariant is stated for **writing**,
and it holds there by construction: `write_run` computes the key itself.
**Nothing states it for reading.** `scan_runs` and `read_run` say nothing about
the key, and the file store answers them with the stem. So the protocol
already says the key is the document's. What it does not say is that a key
read back has to be the key written. And its first sentence, *"chosen by the
store"*, reads as the opposite of its second.

`write_run`'s docstring names three things that depend on the rule:
- `compare --json` prints the key, and a person passes it back to
  `promote --replacing`;
- `journal_key` restates it, so a resumed run writes the file the killed run
  was going to write (ADR 0017 §8);
- the register commits keys to git, where they outlive whichever backend wrote
  them.

All three depend on the key **written**. None of them reads a stem.

## 2. Three symptoms, re-measured

**Measured on `b3f991b`**, with a probe outside this repository. It builds a
store with two runs written by `write_run`, renames the newest
`rossi-mario.json`, and calls the functions below. #332 measured the same three
on v0.25.2 (`89a4219`). **They are unchanged apart from the second, which B
repaired.**

**1. `latest` names a run it cannot read.** `resolve_key(store, suite,
"latest")` returns `2026-10-01T10-00-00-00-00-c0ffee00c0ffee00`, which is the
newest run's `key_of`. `read_run` on that key raises `RunNotFoundError`. The
run is in the store, and `latest` names it by a name the store does not
answer to. **This predates 0.25.2.**

**2. A projected list named the file (F-1).** B now holds:
- **in clear**, the list carries `rossi-mario` beside the other run's key;
- **projected**, it carries only the other run's key, with `unnamed` = 1.

The stem is not on the projected page. **The run is not on it either**, and
it is the newest one.

**3. The baseline is reported missing when it is there.** The renamed run was
promoted, addressed by its stem, which is accepted. The baseline then
remembers it by `key_of`. `suite_runs` marks the baseline by comparing that
`key_of` with the listed keys:
- **in clear**, the note says *"the baseline was promoted from run
  2026-10-01T10-00-00-00-00-c0ffee00c0ffee00, which is not in this list, so no
  run is compared with it"*. The run is in the list, as `rossi-mario`;
- **projected**, the note says the same, after *"left out without a name: 1
  file(s) whose name is not a run key"*.

**One more fact, observed while measuring.** A promotion of the renamed run,
refused for another reason, named it in its refusal by `key_of`, not by the
stem it was addressed with. So the split runs **inside one call**, not only
between two of them.

## 3. The options, and what each costs

Three options: one is the status quo, the other two are the options #332 and
the delta-pass named. **For each, the case that decides its cost is the same:
a file renamed by hand in a store that already exists.** Under ADR 0034 §1 that
store can be the end company's, where nobody at the software house can rename
anything back.

**That case has never been observed.** Every renamed file this record measures
was made on purpose by a probe. No rename has been met in use, and git cannot
record one, because run files are gitignored. So each cost below is the cost of
a hypothetical case, and that holds for all three options alike. The sweep
behind this is in §*Context*, in the correction of 2026-10-04.

### A. Keep the split; B is the remedy

*Not adopted (§4).*

Nothing changes in the store. B stays the projected page's guard.

**A file renamed by hand:**
- **In clear**, it is listed under its stem. Reading, promoting and comparing it
  by the stem work.
- **On a projected list**, it is counted in `unnamed` and not shown.
- **`latest` fails** with `RunNotFoundError` when the renamed run is the newest
  (§2.1).
- **The baseline mark misses**, and the note says the baseline's run is not in
  the list (§2.3).

**Cost:** nothing to build. The three symptoms stay, and every new reader of a
listing inherits the split. The protocol's two sentences keep disagreeing.
#429 stays as it is.

### C. One key, enforced by the store

*Adopted, with the check in `scan_runs` (§4).*

`scan_runs` and `read_run` refuse a file whose stem is not the `key_of` of its
document. The `Listing` counts it.

**A file renamed by hand:**
- **It is listed nowhere.** Every reader stops seeing it, loudly where the
  listing's note is shown, and only there.
- **Reading it by its stem is refused**, by name, saying what its key should
  be. Where the stem is not a safe segment, `_check_name` refuses it first,
  before the file is opened (§4).
- **`latest` resolves to the newest run that is not refused.** If the renamed
  run was the newest, `latest` is now the run before it. The listing's count
  says something was left out. It does not say that what was left out was
  newer. `resolve_key` names a newer run only where the baseline or the
  register remembers one. **That holds for a rename, not for a copy:** see
  *Not decided here*, question 1.
- **It cannot be promoted or compared** until it is renamed back.

**What C needs settled before it can be built.** The ruling in §4 settles
where the check sits. The rest is open, and *Not decided here* sets out the
four questions the ruling named:
- **How a store that already holds a renamed file is repaired.** Three
  candidates, each with a cost:
  1. **a refusal that says how**: rename the file to `<key_of>.json`. It costs a
     person at the store, which may be the end company's, acting by hand;
  2. **a `migrate` step that renames it back.** It is a write in the store, and
     it meets a collision when a file named `<key_of>.json` already exists,
     for example a copy;
  3. **a migration at a schema bump.** It costs the bump, and a renamed file
     carries no schema change.
- **Where the count goes.** A new field of `Listing` is a new key wherever a
  response carries it, such as MCP's `runs_json` (ADR 0011 §4). Counting it
  under `unreadable` instead adds no key and calls a readable file unreadable.
- **What each front end says**: `list`, `view`, `compare --run`, `latest`,
  MCP's tools and `pytest-digline`.
- **What `scan_runs` reads.** Today it reads only `schema_version` from each
  document. C needs `created_at` and `config_hash` too, from the same parsed
  object.
- **The protocol's first sentence.** *"`key` is a string chosen by the store"*
  becomes false and needs rewording.
- **Whether B is kept or withdrawn.** Under C a projected list can meet no
  readable run with a mismatched stem, so one of B's two branches would be
  dead code (§4). Keeping it as a second guard is a choice.

*Corrected 2026-10-04.* The item on the count said a new `Listing` field
*"reaches MCP's `runs_json` (ADR 0011 §4), which moves `OUTPUT_VERSION`"*.
**Both halves were false.** `wire/contract.py` rules that an added key is an
entry in `_ADDED` with no bump, and that is how `refused` and
`baseline_unreadable` (#314) and `on_record_not_read` (#287) went in. And a
`Listing` field does not reach `runs_json` on its own: `runs_json` writes the
keys it names, so somebody adds the key. **So C carried a cost it does not
have.** It is the second claim found false in this record's text, after the
two corrected in §*Context*.

### D. The read derives the key from the content

*Not adopted (§4).*

`scan_runs` lists each run under `key_of` of its document, whatever its stem.
`read_run(key)` finds the file whose document has that key.

**A file renamed by hand:**
- **It is listed under its `key_of`.** `latest` reads it, and the baseline mark
  finds it.
- **Reading it by its stem** either stops working, because the stem is no longer
  a key, or keeps working as a second address. That is a choice, and the second
  answer keeps a form of the split.
- **A copy of a run file collides.** `rossi-mario.json` beside
  `<key_of>.json`, or a backup copy, gives two files with one key. That needs a
  refusal, or a rule for which one wins. Under A and C a copy is simply a
  second name.

**What D costs:**
- **`read_run(key)` can no longer open one path.** Where the stem is not the
  key, finding the file needs a scan of the directory, opening every document,
  or an index. The store keeps no index today.
- **A second backend** would have to do the same. That matches the protocol's
  *"not free to name it something else"*, and it is work for every backend.
- **Anything that addressed a run by its stem** stops finding it. That
  includes a `view` address carrying `/compare?run=<stem>`, which `view` builds
  from the listed key today, and a person who typed the file name.
- **The `Listing` gains no field for the case**, because nothing is left out.
  The collision would need one.
- **B** becomes unreachable for readable runs, as under C, and stays relevant
  for refused files, whose name is still their stem.

## 4. Ruled: C, checked in the scan

*Ruled 2026-10-04, by Alessandro, settled by discussion.*

**Option C is adopted. The check sits in `scan_runs`, not only in `read_run`.**
A file whose stem is not the `key_of` of its document is left out of the
listing, and `read_run` refuses it when it is addressed by its stem.

**With the check in the scan, #429's own case closes there.** For every
document digline writes, `key_of` gives a name that passes the name rule
(`_NAME_RE`): `created_at` is an ISO time, its slug is letters, digits and
dashes, and `config_hash` is a hex digest. So a stem that fails the name rule
is necessarily different from its `key_of`, and the scan leaves it out before
`resolve_key` reads anything. With the check in `read_run` alone, `latest`
would still die where #429 measured it: `resolve_key` reads every listed run
in one `max(...)`, and one refusal stops the whole expression.

**Two refusals stay distinct for `--run <name>`, and that is accepted.** They
protect different things:
- **`_check_name`** protects the path segment. It is raised in `run_path`,
  before the file is opened, and it holds for every input, `--run` and the
  view's `?run=` included;
- **C** protects the identity between the name and the content. It has to
  open the document.

A typed `--run "<key> copy"` meets the first and never reaches the second. The
scan meets the second. So one file can be refused in two different words from
two doors, and each refusal is true.

**Why not A.** It leaves a contradiction measured on one screen: `digline list`
prints `key_of` on every row and marks the baseline's row `*`, and below the
table it says the run the baseline was promoted from is not among the runs
read (§*Context*, the correction of 2026-10-04).

**Why not D.**
- **`read_run(key)` could no longer open one path.** It would need a scan,
  every document opened, or an index the store does not keep.
- **A copy collides with its original.** Two files carry one key. That is the
  defect #429 found, reached through another door.
- **The baseline is not a precedent for D.** Its key is derived from its
  content, but it is never looked up by key: it is one file per suite.

**What this ruling does not close.**
- **#429's other refusals.** `DocumentRefusedError`, `SuiteMismatchError`,
  `TenantMismatchError`, `_inside`'s `PathRefusedError` and a file removed
  between the scan and the read (`RunNotFoundError`) still stop `latest`. They
  fall under the ruling of #349 (`docs/migrate.md`), which keeps `latest`
  refusing past a run it cannot read. C does not change them.
- **B's two branches.** Under C, branch (a), a readable run whose stem is not
  its `key_of`, becomes unreachable on the file store. It would remain a guard
  only against a second backend, and none exists. Branch (b), a refused file
  whose stem has no run key's form, stays reachable: C guarantees that the
  stem is the `key_of`, not that the `key_of` has `is_run_key`'s form
  (question 4).

## What this record does not cover

- **The baseline's key.** The baseline is one file per suite, not addressed by a
  stem, and its key is already derived from its content. §2.3 is about the
  *runs* it is compared with.
- **The register**, and **any place that records a key instead of deriving
  it**: `compare --json`'s output, `promote --replacing`'s argument, a register
  line in git, a link a person saved. Each holds a string that was `key_of`
  when it was written. Under C each such string still opens the run it names,
  as long as the file was not renamed. Whether any of them must change is not
  examined here.
- **`journal_key` and resumed runs.** They write, and the rule already holds for
  writing.
- **Removal** (ADR 0034 §14) and **the deletion ledger** (ADR 0035), which
  names a removed run by its `created_at` alone.
- **Whether `is_run_key` stays internal.** It exists for B.

## Not decided here

**Four questions the ruling of §4 names and leaves open.** Each is set out with
what is known about it, read at `becffc3` and deduced from the code, not
measured. None is chosen.

### 1. A copy against a rename

Neither this record nor #429 drew the distinction before the ruling.
- **A copy** has the same `key_of` as a file the scan lists: the original. It
  is the same run, so `latest` picks correctly, and nothing newer is lost.
  #429's measured case, `<key> copy.json`, is a copy.
- **A rename** leaves no listed file with that `key_of`. **Only there can the
  file left out be newer than the run `latest` picks.** The defect §3 names
  under C, *"`latest` is now the run before it"*, exists only for a rename.

**What is known:**
- Telling the two apart needs the scan to keep, for each file it leaves out,
  its `key_of`, and to look it up among the listed stems. A count alone cannot
  tell them apart.
- **Equal `key_of` is not equal content.** C compares a name with two fields,
  not two documents. A copy that was edited afterwards has its original's key
  and different content, and C would call it a copy.
- **Two left-out files can share one `key_of`** with no listed file under it:
  a renamed run and a copy of the renamed file. That is D's collision, inside
  the set C leaves out.
- **The order of checks in the scan matters.** Today a file at another schema
  is counted in `skipped` before anything else is read from it. Whether C
  checks such a file's name too, and so whether a copy of a schema-5 run is a
  copy or a skipped file, is part of the question.

### 2. What `latest` says about a file it left out, and where

**Three forms are possible:**
- **a note**, as `_newer_on_record` writes for the baseline and the register
  (#286): *"… newer than {key}, and that run was not read here"*;
- **a refusal**, as `latest` already makes past a run `read_run` refuses
  (#349, `test_latest_still_refuses_past_a_refused_run`);
- **a count**, which says something was left out and not that it was newer.

**What is known:**
- **The `created_at` of a left-out file is present, not trusted.** `scan_runs`
  parses the whole document but reads only `schema_version` from it. A
  `created_at` read from that object comes from a document `run_from_json`
  never validated, and outside a projection `created_at` is not checked as a
  time at all. #349's ruling rests on that difference: *"a document that
  cannot be read has no `created_at` anyone can trust"*. To trust the value,
  the scan would build a `Run` from each file it leaves out. `scan_runs`'s
  docstring avoids building a `Run` from every file. Building one only for
  the left-out files is a narrower act, and nobody has ruled on it.
- **`Resolved.note` reaches one front end of three.**
  - The CLI prints it on stderr (`_resolve`, `cli/main.py`).
  - `digline-mcp` drops it in `named()` (`server.py`), behind `get_run`. Its
    comment says `list_runs` reports it, but `list_runs` reports
    `SuiteRuns.note()`, which is built without any pick, so it cannot say
    *newer than the pick*.
  - MCP's `explain` and `pytest-digline`'s `latest` take `.key` and nothing
    else.
  
  So a note written only in `Resolved.note` reaches nobody outside a terminal.
  The same holds today for `_newer_on_record`'s sentences.
- **A promoted rename is already noted.** If the renamed run was promoted, the
  baseline remembers it by `created_at`, and `_newer_on_record` already says
  the baseline's run is newer than the pick and was not read. The same holds
  for a run the register names. The open case is a rename nothing recorded.

### 3. Which repair route is written

The three candidates are listed under C in §3. As read at `becffc3`:
1. **A refusal that says what to do** can be written today, without touching
   the schema. It is reached through the scan, and through `read_run` only
   for a stem that is a safe segment. An unsafe stem is refused by
   `_check_name` before the file is opened (§4).
2. **A `migrate` step that renames** can technically be written without the
   schema, but it changes what `migrate` means. `migrate_file` returns
   *already current* for every document at the current schema, and a renamed
   file is one. `migrate` lists paths through `FileResultStore.stored_paths`,
   and the `SupportsMigration.migrate(...)` member ruled on 2026-09-28 is not
   on `main`. It is a write in a store that may be the end company's.
3. **A migration at a schema bump** touches the schema by construction. Its
   steps also rewrite a document's content and write it back to the same
   path. A rename is not an operation of that kind.

**A constraint on any of them: the message says whether `<key_of>.json`
already exists.** If it does, the file is a copy (question 1), and *rename it*
would produce a collision. The instruction that is true there is a different
one.

**And a constraint from B:** in clear, the message can name the file. On a
projected page a stem may not be shown (F-1), so there it is a count.

### 4. Where `key_of` is not a safe name

`key_of` slugs `created_at` and appends `config_hash` unchanged. On a run that
is not projected, `config_hash` need only be non-empty (`Run.__post_init__`),
and `created_at` is not checked as a time. So `key_of` fails `_NAME_RE` when:
- `config_hash` holds a character outside letters, digits, dot, dash and
  underscore, for example a space or a slash;
- `created_at` has no letter or digit, so its slug is empty and the key begins
  with `-`.

**No document digline writes reaches either case.** Both need a document made
or edited by hand.

**What is known:**
- **There is no name to propose.** A refusal that says *rename it to
  `<key_of>.json`* has nothing safe to say.
- **It is #429's residue under C.** A hand-made document whose unsafe stem
  equals its `key_of` passes C and dies on `_check_name` in `read_run`, so
  `latest` stops as #429 measured.
- **It is where B's branch (b) stays live** (§4).

### Also open, beyond the four

The ruling named four questions. These items from §3's list under C are open
too, and the ruling did not name them:
- **what each front end says**;
- **the protocol's new wording**;
- **whether B's dead branch is kept** as a guard;
- **where the count goes**, a new key or `unreadable`.

**One item of this list before the ruling is not carried forward as open or
as closed:** whether a renamed file is a defect to refuse or a name to
tolerate. C refuses it. Whether that settles the question was not said when C
was ruled.

## What this record does not claim

- **That a renamed file is common.** The probe renamed one on purpose. F-1
  stated that renaming is an ordinary mistake, made by whoever can put a file
  in the store. It did not observe one. How often it happens is not measured
  (§*Context*, the correction of 2026-10-04).
- **That the option list is complete.** These are the three #332 and the
  delta-pass named.
- **That any option is free.** §3 prices each against one case, a file renamed
  by hand in an existing store. Other cases may cost more.
- **That the four open questions are all that C needs.** They are the ones the
  ruling named.
