# ADR 0040 — A run's key, and the two answers the store gives

- Status: proposed 2026-10-01. The text comes first, checkpointed before any
  code, the way [ADR 0038](0038-the-projection-of-a-run-nobody-promoted.md)
  was proposed. **Nothing in it is ruled.** It sets out the facts and the
  options #332 asks for, each with its cost, and **chooses none**. The one
  thing already ruled about this question is the local repair (§*Context*),
  and it is recorded as ruled
- Shipped: unreleased
- Date: 2026-10-01
- Opens: **nothing on landing.** No `SCHEMA_VERSION`, no `OUTPUT_VERSION`, no
  migration. §3 says which options would open which
- Requires, at implementation: depends on the option. §3 prices each
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

### A. Keep the split; B is the remedy

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

### C. One key, enforced by the store

`scan_runs` and `read_run` refuse a file whose stem is not the `key_of` of its
document. The `Listing` counts it.

**A file renamed by hand:**
- **It is listed nowhere.** Every reader stops seeing it, loudly where the
  listing's note is shown, and only there.
- **Reading it by its stem is refused**, by name, saying what its key should
  be.
- **`latest` resolves to the newest run that is not refused.** If the renamed
  run was the newest, `latest` is now the run before it. The listing's count
  says something was left out. It does not say that what was left out was
  newer. `resolve_key` names a newer run only where the baseline or the
  register remembers one.
- **It cannot be promoted or compared** until it is renamed back.

**What C needs settled before it can be built,** each one open:
- **How a store that already holds a renamed file is repaired.** Three
  candidates, each with a cost:
  1. **a refusal that says how**: rename the file to `<key_of>.json`. It costs a
     person at the store, which may be the end company's, acting by hand;
  2. **a `migrate` step that renames it back.** It is a write in the store, and
     it meets a collision when a file named `<key_of>.json` already exists,
     for example a copy;
  3. **a migration at a schema bump.** It costs the bump, and a renamed file
     carries no schema change.
- **Where the count goes.** A new `Listing` field reaches MCP's `runs_json`
  (ADR 0011 §4), which moves `OUTPUT_VERSION`. Counting it under `unreadable`
  moves nothing and calls a readable file unreadable.
- **What each front end says**: `list`, `view`, `compare --run`, `latest`,
  MCP's tools and `pytest-digline`.
- **What `scan_runs` reads.** Today it reads only `schema_version` from each
  document. C needs `created_at` and `config_hash` too, from the same parsed
  object.
- **The protocol's first sentence.** *"`key` is a string chosen by the store"*
  becomes false and needs rewording.
- **Whether B is kept or withdrawn.** Under C a projected list can meet no
  mismatched stem, so B's branch would be dead code. Keeping it as a second
  guard is a choice.

### D. The read derives the key from the content

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

## What this record does not cover

- **The baseline's key.** The baseline is one file per suite, not addressed by a
  stem, and its key is already derived from its content. §2.3 is about the
  *runs* it is compared with.
- **The register**, and **any place that records a key instead of deriving
  it**: `compare --json`'s output, `promote --replacing`'s argument, a register
  line in git, a link a person saved. Each holds a string that was `key_of`
  when it was written. Whether a recorded key can still be read under each
  option follows from the option. Whether any of them must change is not
  examined here.
- **`journal_key` and resumed runs.** They write, and the rule already holds for
  writing.
- **Removal** (ADR 0034 §14) and **the deletion ledger** (ADR 0035), which
  names a removed run by its `created_at` alone.
- **Whether `is_run_key` stays internal.** It exists for B.

## Not decided here

- **Which option holds.** A, C or D, or none of them.
- **Under C**: the repair of an existing store, where the count goes, what each
  front end says, the protocol's wording, and B's fate.
- **Under D**: the stem as a second address, the rule for a collision, and how
  `read_run` finds a file without an index.
- **Whether a renamed file is a defect to refuse or a name to tolerate.** The
  three options answer that differently, and no record says which it is.

## What this record does not claim

- **That a renamed file is common.** The probe renamed one on purpose. F-1
  stated that renaming is an ordinary mistake, made by whoever can put a file
  in the store. It did not observe one. How often it happens is not measured
  (§*Context*, the correction of 2026-10-04).
- **That the option list is complete.** These are the three #332 and the
  delta-pass named.
- **That any option is free.** §3 prices each against one case, a file renamed
  by hand in an existing store. Other cases may cost more.
