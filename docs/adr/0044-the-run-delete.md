# ADR 0044 — The run delete

- Status: accepted 2026-10-06, by Alessandro Prandini, after reading every
  section, the text first and before any code. Eight points it rests on were
  ruled in discussion on 2026-10-06, and are recorded here as ruled: the order of the legs and the document (#289), the refusal for
  the run under the current baseline, the legs-only run, the replays across the
  tenant, the refusal before the first step, the already orphaned baseline, the
  file under a key that cannot be verified, and the absence from the MCP
  server; a ninth, the misfiled replay (§3.4), was ruled on the draft. The
  rest are *decided here*, marked where they are made, and were accepted with
  the record. *More were ruled 2026-10-07, during implementation, each
  marked where it is made:* the replay that declares another tenant or suite,
  which left *Not decided here*, the document on the chain with no key of its
  own and the rule they share (§3.4), `Filing` and `filed_as` (§1), and the
  legs under a key a misfiled replay shares (§5)
- Shipped: 0.30.0
- Date: 2026-10-06
- Opens: **nothing on landing.** No `SCHEMA_VERSION`, no `OUTPUT_VERSION`, no
  `JOURNAL_VERSION`, no `REGISTER_VERSION`, no migration. A delete changes no
  document; it removes some
- Requires, at implementation: **a sixth method on `ResultStore`** and two
  values it returns (§1); **a refusal**, `PromotedRunError`, in
  `host.REFUSALS` (§3), and *since 2026-10-07* a second, `KeylessRunError`
  (§3.4); **a command**, `digline delete` (§2); the two
  docstrings §7 names, rewritten
- Implements: [ADR 0034](0034-the-store-outside-and-the-reference-that-names-nothing.md)
  §14, *"A delete. Five methods become six"*, which says its contract is
  *"written in the record that designs it"*. This is that record
- Amends: [ADR 0017](0017-the-journal-and-the-resumed-run.md) §5 and §12, which
  give `drop_pending` a **single case**, the journal whose run already exists.
  A person's delete is a second one (§4)
- Assumes: [ADR 0031](0031-the-reference-promote-replaces.md) §2 and §3 (no
  lock, and no force flag); [ADR 0015](0015-the-recorded-output-and-the-declared-re-judge.md)
  §7 (a replay is not promotable); [ADR 0040](0040-a-runs-key-and-the-two-answers-the-store-gives.md)
  §4 (one key per run, and a file named otherwise is refused);
  [ADR 0011](0011-the-mcp-server.md) §1 (absent by construction)
- Leaves room for: [ADR 0035](0035-the-record-of-a-deletion.md), **proposed**.
  This record writes no ledger. It keeps what an entry needs within reach of
  the process that removes (§6)
- Touches, in `CLAUDE.md`'s *fixed* section: **decision 2**, whose
  `ResultStore` protocol gains a method. The decision's words do not change:
  everything still lives in `.digline/<tenant>/`, and the delete removes from
  there and from nowhere else
- Number: 0044. Swept on 2026-10-06, before a line was written, across
  `origin/main` (`1eed029`), every local and remote branch and tag, the
  `docs/adr/` of every sibling worktree, the open pull requests (one, a
  Dependabot branch with no record) and `private/` (no claim on 0044). The
  highest number taken anywhere was 0043

## Context

ADR 0034 §14 asks for a delete and states what it must achieve: *"A removed
run must be absent from every reader — `scan_runs` and `read_run` included"*,
and both side-cars, *"run documents carrying recorded responses"* and *"the
journal"*, are reached by it. It also says what a delete is not: *"A delete is
also not an erasure"* on a filesystem somebody backs up. Retention as a policy
and erasure as a procedure stay outside it (ADR 0034, *Not decided here*).

Issue #237 waited on identity from 2026-09-30: ADR 0035 §4 makes a ledger
entry carry *"who decided it"*, and digline has no person to write. That ruling
said the block would not hold *"if 0035 were accepted without its identity
field, or with that field optional"*. On 2026-10-05 the field was ruled
**absent for a run's removal** and required for a name-table row's, and #237
says so publicly. The run delete can be designed, and this record designs it.
ADR 0035 stays proposed; this record does not wait on it.

### What was ruled before this text, on 2026-10-06

1. **The legs go before the document** (#289). Interrupted between the two,
   legs first leaves a run document with no legs, which is the ordinary state of
   every finished run. The other order leaves `finished = False`, and the next
   `digline run` prints an invitation to `--resume <key>`. If a person follows
   it, and the suite has not changed since the run started, the resume writes
   under the same key.
2. **The delete refuses the run from which the suite's current baseline was
   promoted.** The refusal names the baseline and says to promote another
   first. The delete does not reach the baseline. ADR 0034 §1 refuses a
   reference *"that can vanish from under a gate"*, and a delete that reached
   the baseline would be that. A baseline is the complete run without its
   responses (`without_responses`, measured field by field), so a surviving
   baseline over a removed run would keep that run's verdicts, reasons,
   artifacts and configuration.
3. **The refusal comes before the first step of the delete, cascade
   included.** A promoted run can still have legs, when its process was killed
   between `write_run` and `complete()`. A replay can rest on a promoted
   source. Either step taken before the refusal would remove something and then
   refuse.
4. **A run made only of journal legs can be deleted.** No reader can name a
   run with no document, so it has no witness, and nothing the store holds today
   tells a live journal from a killed one.
5. **The delete reaches the replays of the run it removes, following the
   chain across the tenant, not only the suite.** A replay of a recording suite
   carries the source's answers, `input` included (measured), and a replay that
   does not record keeps verdicts that judged them. The library's `rejudge`
   files a replay under another suite of the same tenant (measured), and a
   reader of that suite reads it.
6. **The register is not reached** (ADR 0021 §5 and §6, both accepted), and
   the projection at the software house stays by placement. ADR 0035 §3, which
   says the same about the register, is proposed and is not needed for it.
7. **ADR 0035's ledger is not written by this delete**, and the design must
   not prevent it.

### What reading the code found

At `origin/main` = `1eed029`. Code was read; nothing was run for this record.
The measurements quoted above are those of the 2026-10-06 rulings.

- **Nothing enumerates the suites of a tenant.** Every reader is addressed by
  a `(tenant, suite)` taken from a loaded suite. No method of `ResultStore` or
  of `FileResultStore` lists `runs/<suite>/`. A cascade across the tenant needs
  one.
- **`rejudged_from` is a bare key** (`run/replay.py`, the final `replace`). It
  names no suite. A key is `key_of(created_at, config_hash)`, and `config_hash`
  does not include the suite's name (`Suite.config_hash`), so two suites of one
  tenant with the same configuration and the same `created_at` give two runs
  the same key.
- **`scan_runs` reads three fields** of each document (`schema_version`,
  `created_at`, `config_hash`) and not `rejudged_from`. Finding the replays of a
  run means opening every document of the tenant.
- **Legs belong to `SupportsJournal`**, which a store may not implement (ADR
  0017 §5). `drop_pending` removes the legs of any key and checks nothing.
- **Two docstrings forbid what ruling 4 allows.** `SupportsJournal.drop_pending`:
  *"Never called on a journal that might still be finished — that is paid
  work."* `Journal.complete`: *"A journal that is deleted for any other reason
  is paid work thrown away."*
- **A file named `<K>.json` may hold another run.** `read_run` refuses it
  (`MisfiledRunError`, ADR 0040 §4). A delete that removed by name would remove
  the wrong document.
- **The store keeps no memory of a removal**, and ADR 0035 §10 (proposed)
  keeps the ledger off every read path. After a delete, a key that was removed
  and a key that never existed read the same.

## Decision

### 1. The gesture: `delete_run`, the sixth method

    class ResultStore(Protocol):
        def delete_run(self, ref: RunRef) -> Removal: ...

    @dataclass(frozen=True, slots=True)
    class Filing:                # added 2026-10-07
        tenant: str              # the tenant's directory
        suite: str               # the suite's directory
        name: str                # the file's name, without .json

    @dataclass(frozen=True, slots=True)
    class RemovedRun:
        ref: RunRef              # the run's own key, key_of(created_at,
                                 # config_hash), never a file's name
        created_at: str | None   # read before removing; None where nothing
                                 # readable carried it
        legs: int                # journal legs removed
        document: bool           # whether a run document was removed
        filed_as: Filing | None  # how it was filed, whenever the file's
                                 # name, the address it declares and its
                                 # key do not all agree (§3.4). None only
                                 # where all three agree. Added 2026-10-07

    @dataclass(frozen=True, slots=True)
    class Removal:
        run: RemovedRun                  # the run that was asked for
        replays: tuple[RemovedRun, ...]  # in the order removed: leaves first
        unread: int                      # documents of the tenant the scan
                                         # could not read
        @property
        def nothing(self) -> bool: ...   # no document, no legs, no replay

**`Filing` is not a `RunRef`. Ruled 2026-10-07.** A `RunRef` names a run by its
key, and a store answers to that key alone (ADR 0040). A `RunRef` that carried
a file's name would be a reference that does not refer, and this record exists
to keep the two apart. `filed_as` is set whenever the file's name, the tenant
and suite the document declares, and its key do not all agree, including a
declaration that is missing or not a string. There `ref` takes the directory,
which is all there is to name the run by, and `filed_as` still records the
filing, because that bit is the only thing that tells a reader the store holds
a malformed document.

**The contract.** After `delete_run(ref)` returns, neither `ref` nor any
replay chained from it **through documents the scan could read** is returned by
`read_run`, `scan_runs`, `list_runs` or `pending`, in any suite of
`ref.tenant`. A document the scan could not read is not reached, whatever it
holds. **`unread` counts those documents, not missed replays**: it is a count
of unknowns, and `unread: 3` says that three documents of the tenant were not
read, not whether any of them was a replay of `K` (§5). Every refusal is raised
before the first removal (§3).

**Its reach is the tenant, and no other method's is.** Every other method of
`ResultStore` reaches at most one suite of one tenant: `write_run` files one
run, `read_run` and `promote_baseline` take a `RunRef`, `scan_runs` and
`read_baseline` take a `(tenant, suite)` pair. `delete_run` takes a `RunRef`
like them and acts on every suite of `ref.tenant`, because the replays it must
reach can be filed under any of them (ruling 5). **A backend has to know this
before it is written:** it must be able to list the suites of a tenant and read
every run document in each, and a backend that keeps suites apart, a database
per suite or a store addressed by suite, has to reach across them for this one
method.

**On `ResultStore`, and not composed in `host/`. Decided here.** Composed
above the store, the delete would need two methods more than §14's six: one
that lists a tenant's suites, which does not exist, and `drop_pending`, which
belongs to an optional protocol. And it would put the refusal away from the
store, while it asks what the store holds **now**, as promotion's condition 8
does. That condition sits beside the write for the same reason (ADR 0031 §2).
The store knows its own layout, and a store that does not journal has no legs to
remove, which is the one point where `SupportsJournal` meets this method.

**What it returns when there is nothing to remove. Decided here.** A
`Removal` whose `nothing` is true, and no exception. A delete that already
finished, repeated, has to succeed: that is what makes every interrupted
state repeatable (§4). And the contract holds: the key is absent from every
reader. The cost is stated with it: **a mistyped key and a removed one return
the same value**, because nothing remembers a removal (*Context*).

### 2. Who calls it

**The command line: `digline delete --suite … --run KEY`.** It addresses
the tenant through the loaded suite, as every command does.
- **`latest` is refused, and the key is written out. Decided here.** `latest`
  resolves to the newest readable run, so the same command removes a different
  run each time it is repeated. A delete has to be repeatable on the key it
  started from (§4), and an alias that moves under it is not.
- **It exits 0 when something was removed and when nothing was**, and says
  which in words. For nothing: *"nothing is filed under K in suite S, tenant
  T: no document, no legs, no replay. Nothing was removed."* The sentence never
  says *removed* of something that was not there. A refusal exits 64, as every
  refusal does.
- **No confirmation and no force flag.** The baseline's refusal has no
  override, for ADR 0031 §3's reason: the way past it is to promote another
  run, which is one command, and a flag would become the habit.

**Not the MCP server. Ruled 2026-10-06.** The thesis is already in the
module (`digline_mcp/server.py`, ADR 0011 §1): *"absent by construction … A
refusal is a conversation — it can be argued with, retried, worked around by a
model that has decided the refusal is a bug. An absence is not a
conversation."* `promote` is absent because it writes into a committed file,
which arrives in somebody's diff. A delete is further from review than that:
it removes artifacts that are gitignored, so there is no diff, no review and no
way back. `destructive_hint` would not stand in for the absence, and the
module says why of its own annotations: *"A hint and not enforcement."*

**The library.** `delete_run` is public because it is on the protocol. A
Python caller reaches it as it reaches `promote_baseline`.

### 3. The refusals, and their order

**A delete has two phases. Decided here.** A **plan**, which only reads and is
the one place a refusal can be raised, and a **removal**, which raises no
refusal and can only be interrupted (§4). Everything below is in the plan, in
this order.

1. **The address.** `PathRefusedError` for a tenant, suite or key that is not
   one safe segment (`_check_name`). First, because without valid names the
   baseline cannot be read.
2. **The baseline.**
   - **A baseline that cannot be read refuses the delete**, with the error
     reading it raised: `DirectoryUnreadableError`, `DocumentRefusedError`,
     `NotAReferenceError`, `TenantMismatchError`, `SuiteMismatchError`, or
     `PathRefusedError` for a baseline that is a link out of the store.
     *Could not look* is not *not under the baseline*, which is #365's rule.
   - **A baseline whose key is `K` refuses the delete**:
     `key_of(baseline.created_at, baseline.config_hash) == ref.key`. The new
     refusal is `PromotedRunError`, in the shape of promotion's condition 8, a
     refusal that names the next step:

         run K of suite S is the one its current baseline was promoted from
         (promoted at P). A delete never removes the run under the baseline:
         promote another run first, with `digline promote --suite … --run
         <key> --replacing K`, and delete this one after.

   - **It is a refusal about the key, not about the run. Ruled 2026-10-06.**
     A baseline promoted from a run that is no longer there, removed by hand
     before this delete existed, still names `K`, and the delete of `K` is
     refused with the same sentence. **This closes the point the baseline's
     ruling left open**, the baseline already orphaned: the refusal concerns the
     baseline that rests on that key, not whether the run exists, and it tells
     the person exactly what to do.
   - Where the promoted run is the suite's only run, the refusal holds until a
     new run under the current `config_hash` is made and promoted. Nothing
     removes a baseline without promoting another.
3. **The run asked for.** Its document is verified to be the run `K` names,
   with the scan's light reading (`created_at` and `config_hash`, no `Run`
   built), so a document at an older schema can be removed:
   - `MisfiledRunError`, `TenantMismatchError`, `SuiteMismatchError`, as
     `read_run` raises them;
   - **a file under `K` whose key cannot be verified is refused**: one that is
     not JSON, not an object, or lacks either field. **Ruled 2026-10-06.**
     Removing by name can remove the wrong document, and removing the wrong
     thing is worse than not removing.
     **The reason that gives way**, stated beside it: ADR 0035 §9 (proposed)
     refuses to make a missing ledger a reason not to remove, because *"not
     erasing is worse than an imperfect record of erasing"*. That holds for a
     record of the right removal. It does not cover removing a document nobody
     can show is the one asked for.
   - **Legs are not verified.** They are removed by name, readable or not, as
     `drop_pending` removes them. A leg's name is its key (`<K>.<n>.jsonl`), and
     a refused leg is still `K`'s.
4. **The tenant.** Every `runs/<suite>/` of `ref.tenant` is listed, and each
   document is read for `rejudged_from` from its raw JSON, as `scan_runs` reads
   its three fields. So a replay at an older schema is reached.
   - **A directory that cannot be listed refuses the delete**
     (`DirectoryUnreadableError`): a replay may be in it, and nothing in it was
     looked at.
   - **A path that leads outside the store refuses the delete**
     (`PathRefusedError`, `_inside`), for every path the plan will remove,
     before the first removal.
   - **A single document that cannot be read does not refuse.** It is counted
     in `unread`, and the front end says it in words (§5). That a scan does not
     see what it cannot read was ruled on 2026-10-06, in the same class as the
     misfiled file.
   - **A misfiled replay of `K` is removed. Ruled 2026-10-06.** A document
     filed under a name that is not its key is read for its `rejudged_from`
     like any other. When that names `K`, or a replay on `K`'s chain, it is
     on the plan, and `Removal.replays` names it by its own key, not by the
     file's name. The chain continues from that key.
     **Why this is not §3.3's case.** There the file under `K` cannot be
     verified, so removing it by name risks removing the wrong document. Here
     the document was read: its `rejudged_from` says what it is. A wrong name
     does not change what is inside, and what is inside is the removed run's
     answers, or verdicts on them, which is why ruling 5 exists. Left in place,
     a file filed wrongly would shield those answers from the delete, and
     filing one wrongly would become a way round it.
   - **A replay of `K` that declares another tenant or another suite than
     the directory it was found in is removed. Ruled 2026-10-07.** It was in
     *Not decided here*, and the implementation's scan met it. `read_run`
     refuses such a document, but `scan_runs` reads three fields and lists
     it, so left in place it would still be returned with `K`'s answers.
     **The declaration is a defect, not an address**, so removing it does
     not leave §1's reach, which is the tenant whose directory holds it.
     `RemovedRun.ref` carries what the document declares and its own key,
     and `filed_as` the address it was filed at, so the command names the
     file and what it declared: it is a fact about the store's health, not
     only about the delete.
   - **A document on the chain with no key of its own refuses the delete.
     Ruled 2026-10-07.** One that lacks `created_at` or `config_hash`, or
     holds either as something other than a non-empty string, cannot be
     named, and what cannot be named is not removed. The refusal is its own,
     `KeylessRunError`, naming the file and the field, and not
     `MisfiledRunError`: there the key contradicts the name, here there is
     no key, and the reader needs to know which. It falls in the fourth
     step, so it comes before the first removal like every refusal of §3,
     and nothing depends on whether `scan_runs` would list the document.
   - **The rule the four cases share. Ruled 2026-10-07.** The plan is built
     from a raw reading that trusts neither a file's name nor the address a
     document declares. **What identifies a document is its key and its
     `rejudged_from`.**
     - The run `K` asked for: whatever cannot be verified refuses (§3.3).
       That is not an exception to the rule. It refuses because the key
       cannot be verified, not because the name counts.
     - A document elsewhere in the tenant, identified: removed, however it
       is filed, under the wrong name (§3.4) or in a tenant or suite other
       than the one it declares.
     - A document that puts itself on the chain and has no identity of its
       own: refuses the delete. What cannot be named is not removed.
     - A document that cannot be read at all: counted, never opened (§5).

**What the plan cannot reach, by structure.** The name table
(`.digline/<tenant>/name-table/`, ADR 0036 §2) is outside `runs/`, so the
listing never meets it. The baseline and the register are never on the plan
(rulings 2 and 6). `.pending/` inside a suite's directory is the journal, not a
suite.

### 4. The removal, the order, and an interruption at each point

**The order. Decided here, from the rulings.** Plan, then each replay **from
the leaves towards `K`**, each one's legs before its document, then `K`'s legs,
then `K`'s document.

**Leaves first is a condition, not a preference.** A repeated delete of `K`
finds the replays again by `rejudged_from`, walking down from `K`, and it does
not need `K`'s document to do it. Removing a replay R1 before the replay R2 of
R1 would leave R2 chained to nothing the walk can reach from `K`, and a
repetition would not find it.

**An interruption, point by point.**

| Interrupted | What is left | Repeating `delete K` |
|---|---|---|
| in the plan | nothing removed | the same plan |
| between two replays | the replays not yet removed, each still chained to `K` through the survivors | finds and removes them |
| among `K`'s legs, document present | a finished run with some legs; `pending` marks them `finished`, and the next `digline run` removes them with a note | removes them |
| among `K`'s legs, no document | some legs, which read as a run that was killed: `digline run` invites `--resume K` | removes them |
| between the legs and the document | a run document with no legs, the ordinary state of every finished run (ruling 1) | removes it |
| after the document, before the return | nothing | `nothing` |

**The state left is always repeatable, with three exceptions, each declared:**
- **a document that became unreadable between two attempts** is skipped by the
  second (`unread`);
- **a replay written after the plan** is not on it (§5);
- **the fourth row's invitation.** Between the interruption and the repeat, a
  person who follows it resumes a run whose earliest legs are gone, and pays
  again for their cases. The resume writes `K`'s document; the repeat removes
  it, unless `K` was promoted in between, and then the repeat is refused, which
  is correct.

**ADR 0017 §5 and §12, amended.** `drop_pending`'s *single case* becomes two:
the journal whose run already exists, removed by `digline run`, and a journal a
person deleted, removed by `delete_run`. The two docstrings in *Context* are
rewritten to say so. What they protect still holds for every other caller:
nothing else removes a journal that might still be finished.

### 5. The limits, stated where the rule is

- **A delete racing anything that writes loses.** There is no lock (ADR 0031
  §2), and each of these reads before the removal and writes after it:
  - **a live run** writes its document at the end and comes back whole. Ruled
    with #289, and the resume of a run in flight is #478;
  - **`promote`** reads `K`, the delete passes its baseline check and removes
    `K`, and `promote` writes a baseline from it. That is exactly the state
    ruling 2 forbids, reached through the window;
  - **`rejudge`** reads `K` and files a replay after the plan, and the replay
    survives with `K`'s answers.
- **A replay among the documents the scan cannot read is not reached, and
  nobody learns whether there was one.** With §3's raw reading, *cannot read*
  narrows to a file that is not a JSON object and a link out of the store,
  which is counted and never opened. `unread` counts those documents. It is a
  count of unknowns, not of missed replays (§1). The command says: *"N
  documents in tenant T could not be read. Whether any of them was a replay of
  K is not known, and none of them was removed."* Never silent.
  *Added 2026-10-07:* a JSON document with no key is not an unknown: on the
  chain it is a refusal (§3.4).
- **A misfiled document is not an unknown. Found writing this record.** The
  first draft of this section counted it among the documents the scan cannot
  read. It never belonged there: §3.4's raw reading reads its
  `rejudged_from`, so a misfiled replay of `K` is known, and §3.4 removes it.
  What stays a limit is narrower: a misfiled file whose key is also the name
  of another file is **two documents under one key**. If both are on `K`'s
  chain, both go, and `Removal.replays` names that key twice. If only the
  misfiled one is, only it goes, and `Removal.replays` names a key that
  `read_run` still answers to, with the other document. The command says so
  beside that key rather than reporting it as gone.
  **The legs under that key are not touched. Ruled 2026-10-07.** Legs are
  named by a key, so they belong to the document filed under it, which is the
  one that stays; the legs of the removed document would carry the same name,
  and nothing tells the two apart. The command says that too.
- **Two suites can share a key** (*Context*). The cascade matches
  `rejudged_from` by key across the tenant, so with such a collision it reaches
  the replays of the other suite's run too. It takes the same configuration and
  the same `created_at` to the microsecond; it is not excluded.
- **Git history.** The delete touches nothing committed: not the baseline
  (ruling 2), not the register (ruling 6), not the projection (by placement).
  What git holds, it keeps, including a run somebody committed by overriding the
  store's `.gitignore`.
- **What was never the store's.** A report written with `report --out` is
  recorded nowhere, so nothing can reach it. Backups, snapshots and
  copy-on-write blocks keep what was removed (ADR 0034 §14: not an erasure).
- **No trace of the gesture.** Until a ledger exists, a delete leaves no
  record, and a key removed and a key never filed read the same afterwards.

### 6. What this leaves ADR 0035, proposed

- **The removal first, the entry after** (0035 §6): the store removes, and
  returns; a `host/` writer can append afterwards, as the one process that
  removed.
- **`created_at`, for a run, and one entry per run** (0035 §4): `RemovedRun`
  carries it, read before the removal from the document or from a leg's
  header, whether the run went as a document, as legs or as both. It is `None`
  only for a run with no document whose every leg was refused: a document
  whose `created_at` cannot be read is refused before anything is removed
  (§3). An entry has nothing to name then, which is already 0035 §4's open
  point.
  *Answered 2026-10-09 by [ADR 0035](0035-the-record-of-a-deletion.md), at its
  acceptance: the entry is still written, and names the run with the explicit
  value `created_at-not-readable`; no key matches it (§4 there). The bullet is
  kept as written.*
- **An interruption inside `delete_run` leaves the ledger short**: what was
  removed before it never reaches the return. That is the torn state 0035 §6
  accepts. A callback per removed run would narrow the window, and is not
  proposed here.
- **No identity**, by the ruling of 2026-10-05.

### 7. What holds it

- **The refusal before the first step**, by a test on a store that really
  writes: a promoted run with legs and a replay, deleted, refused, and every
  file still there.
- **Every implementation reaches the baseline check**, by a walk like the one
  `tests/test_promotion_conditions.py` makes for condition 8: a class in this
  repository that defines `delete_run` without reaching the refusal fails it.
  Like that walk, it reaches implementations here and no others.
- **`PromotedRunError` in `host.REFUSALS`**, which a test holds complete.
- **`digline-mcp` has no `delete` tool**, by the test that already asserts
  its tool list from a real client
  (`test_a_real_client_sees_eight_tools_and_no_promote`). It asserts the exact
  list of eight, so a ninth tool fails it whatever its name.

## Consequences

- `ResultStore` has six methods, and a backend that implements the protocol
  must add one, whose reach is the whole tenant (§1). Whether any backend
  outside this repository exists is not known.
- A file filed under the wrong name no longer keeps a replay's answers out of
  a delete (§3.4).
- A suite whose only run is under the baseline cannot have that run deleted
  until another is promoted.
- `docs/api.md` gains `delete_run`, and the command is documented with §5's
  limits beside it. A new page under `docs/` is three entries on digline.dev.
- A delete reads every document of the tenant. Its cost grows with the
  tenant's history, and a document can be 88.3% responses (ADR 0034 §14). Not
  measured on a real store.

## Alternatives considered

- **Compose the delete in `host/`** from `drop_pending`, a new listing of
  suites and a new document removal. Seven methods instead of six, the
  refusal away from the state it reads, and an orchestration every front end
  would have to call in the same order (§1).
- **Raise `RunNotFoundError` when there is nothing to remove.** It would
  tell a mistyped key from a removed one only on the first attempt, and make
  the repeat of a finished delete a failure (§1, §4).
- **Remove `K` first, then its replays.** A repetition still finds the
  first level, by `rejudged_from == K`, but not the levels below it once their
  parent is gone (§4).
- **Remove a file under `K` whose key cannot be verified.** Refused by ruling
  (§3.3).
- **Leave a misfiled replay of `K` in place, named or not.** Refused by
  ruling (§3.4): the document was read, and a wrong name would shield it.
- **A `delete` tool on the MCP server, marked destructive.** Refused by ruling
  (§2).
- **Remove a keyless document on the chain by its file's name.** Refused by
  ruling, 2026-10-07 (§3.4): it contradicts §1's `RemovedRun.ref`, which is
  the run's own key and never a file's name.
- **Count a keyless document on the chain in `unread`.** Refused by ruling,
  2026-10-07 (§3.4): the document was read, so §5's sentence, which says the
  counted documents could not be read, would be false.

## Not decided here

- **Whether the cascade should match `rejudged_from` on more than the key**,
  so that two suites sharing a key (§5) no longer reach each other's replays.
  It is the real fix of that limit. *Added 2026-10-07.*

- **`digline view`.** Whether its server, which has one route that writes,
  carries a delete.
- **A delete of a run whose suite no longer loads.** The command addresses
  the tenant through a loaded suite. What decides the tenant without one is ADR
  0034 §13's question.
- **A refusal for a live run.** It would need something the store does not
  hold today: a hint of time with a threshold nobody has set, or a fact of the
  operating system. Whether ADR 0017 §5's reason against a lock reaches other
  mechanisms is not ruled.
- **What to say about the register's counts**, which include the removed
  cases (ruling 6 leaves it open).
- **Retention and erasure** (ADR 0034, *Not decided here*).

## What this record does not claim

- **That the interruption table was measured.** It was read from the code
  (`FileResultStore.pending`, `_resume`'s notes in `cli/main.py`,
  `host/measure.py`), not run.
- **That a key collision across suites happens in practice.** It is possible
  by construction and was not observed.
- **That a delete is an erasure.** It removes from the store's directory. It
  proves nothing about the blocks, the backups or git.
- **That `unread: 0` means every copy of the answers is gone.** It means the
  scan read every document of the tenant. The races of §5 and what was never
  the store's are outside it.

## Test plan

1. **The refusal before the first step:** a promoted run with legs and a
   replay; the delete is refused with `PromotedRunError`, naming the baseline,
   and the legs, the replay and the document are all still there.
2. **The orphaned baseline:** the baseline names `K` and no artifact of `K`
   exists; the delete is refused with the same sentence.
3. **A replaced baseline:** after another run is promoted, `K` is deleted, and
   the register lines naming it remain byte for byte.
4. **The legs-only run:** legs and no document; all legs removed,
   `RemovedRun.document` false, `created_at` read from a leg's header.
5. **The chain across the tenant:** `K` in suite `s`, R1 of `K` in suite `t`,
   R2 of R1 in `s`; all three removed, R2 before R1 before `K`.
6. **Repeatability:** for each row of §4's table, the store left in that state
   by hand, then the delete repeated; afterwards the contract of §1 holds.
7. **A file under `K` that is not JSON:** refused, and the file is still
   there. **A misfiled file under `K`:** `MisfiledRunError`, file still there.
8. **A misfiled replay of `K`**, filed under a name that is not its key:
   removed, and named in `Removal.replays` by its own key. **And one whose key
   is also another file's name:** with both on the chain, both removed and the
   key named twice; with only the misfiled one on it, the other file still
   there and still read under that key, and the command saying so.
9. **An older schema under `K`:** removed, `created_at` read.
10. **An unreadable directory in the tenant:** refused before any removal.
    **An unreadable document:** skipped, counted in `unread`, and the command
    says §5's sentence, which claims nothing about what it held.
11. **Nothing to remove:** `nothing` true, exit 0, and the sentence does not
    say *removed*.
12. **`--run latest`:** refused.
13. **The name table:** a file under `.digline/<tenant>/name-table/` survives
    a delete of every run in the tenant.
14. **The walk** of §7, with a control: a class defining `delete_run` that
    skips the baseline check fails it.
15. **A replay that declares another address** *(added 2026-10-07)*: a
    document on `K`'s chain that declares another tenant, and one that
    declares another suite; both removed, named in `Removal.replays` by
    their own key, with `filed_as` set, and the command's sentence.
16. **A keyless document on the chain** *(added 2026-10-07)*: one without
    `created_at` and one without `config_hash`, both refused with
    `KeylessRunError` naming the file and the field, and nothing removed.
17. **Two suites that share a key** *(added 2026-10-07)*: `K` in suite `s`,
    a run with the same key in suite `t` and a replay of it; the delete of `K`
    removes that replay and leaves the run in `t`, which `read_run` still
    returns. §5 states the limit, and this holds it as a behaviour.
