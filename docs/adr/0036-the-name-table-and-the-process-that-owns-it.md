# ADR 0036 — The name table, and the process that owns it

- Status: accepted 2026-09-29, by Alessandro Prandini — the text first,
  checkpointed before any code, the way
  [ADR 0034](0034-the-store-outside-and-the-reference-that-names-nothing.md)
  and [ADR 0035](0035-the-record-of-a-deletion.md) were. It landed on `main`
  as proposed earlier the same day; nothing in it is implemented. **Most of
  what it states was settled before it was written**, in discussion, and is
  recorded here as settled. The rest are **decisions this record takes
  itself**, marked *decided here* where they are made so that acceptance could
  rule on them one by one. **Acceptance ruled all four as written**: the table
  outside the store, reached through two callables (§2); its place, a reserved
  name in the tenant's directory (§2); the token as the key and the kind as a
  check (§3); tokens per (tenant, suite), with the run key joining nothing in
  the table (§4). **One of them overturns a sentence of an accepted record**:
  ADR 0034 §6 puts the table behind an optional protocol of the store, and §2
  below refuses that. Before acceptance, the same day, **§6's condition gained
  one table per (tenant, suite)**, and **§9 stopped saying it added nothing to
  ADR 0035**, since whose code writes a row's ledger entry is open. Both are
  dated in their sections. The status named no condition of acceptance, and
  none was added: the conditions the design rests on are written where they
  are made (§5, §6, §9). **What it amends is made in the change that accepts
  it**, as ADR 0034's acceptance found it should have been
- Shipped: 0.24.0
- Date: 2026-09-29
- Opens: **nothing on landing.** No `SCHEMA_VERSION`, no `OUTPUT_VERSION`, no
  `REGISTER_VERSION`, no `JOURNAL_VERSION`, no `LEDGER_VERSION`, no migration.
  The table is not a digline format (§2), so it opens no version of digline's
- Requires, at implementation: **no method and no protocol on the store**
  (§2). **Two callables** that digline's code is handed rather than a table it
  opens: one that returns a token for a (kind, text), and one that returns the
  row a token names (§2, §3). **A reserved name** in the tenant's directory,
  which digline keeps and never writes (§2). **Two refusals** — a document in
  which no token resolves, and a row whose kind is not the kind of the place
  its token sits in — each classified in `host.REFUSALS`, or
  `tests/test_refusals.py` will not see it (§3, §8). **Nothing else is
  digline's:** §7's three writers and §9's erasure surface run inside the
  owning process, whose code is not digline's. *Added 2026-09-30, when the
  qualifier came off `Shipped:`: §2's directory shipped in 0.24.0, the
  resolver and the two callables in 0.25.0, and a bare version must not read
  as the whole record built by digline.*
- Assumes: [ADR 0002](0002-three-worlds-and-where-the-data-lives.md) §1 (the
  tenant is the perimeter, enforced as addressing and not as access) and §5
  (the `case_id` crosses, so it cannot be payload, and a generated id has no
  way to be copied in); [ADR 0003](0003-artifacts-travel-only-when-the-suite-says-so.md)
  §4 (a digest is a verifier over a guessable space);
  [ADR 0017](0017-the-journal-and-the-resumed-run.md) §5 (a capability the store is
  asked for rather than required); [ADR 0021](0021-the-register.md) §5 (a store
  that cannot hold a register implements no `SupportsRegister`) and §6 (a
  committed file's retention is git); [ADR 0023](0023-capture.md) §6 (the id
  minted inside the perimeter is a hash of `vars`, on purpose);
  [ADR 0028](0028-the-rules-that-moved.md) §6 (`compare()` needs group-token
  equality across two documents); [ADR 0031](0031-the-reference-promote-replaces.md)
  (the check and the rename are two system calls, and closing that needs a
  lock); [ADR 0034](0034-the-store-outside-and-the-reference-that-names-nothing.md)
  §1 (the store lives in the end company's perimeter), §3 (the projection is
  produced where the whole value and the table are), §5 (six strings become
  tokens, and hashing is not one of the options), §6 (the table's skeleton,
  its costs, and a restored backup re-identifies), §13 (the tenant is a typed
  flag when the suite is not loaded) and §14 (a removed run is absent from
  every reader, and a delete is not an erasure);
  [ADR 0035](0035-the-record-of-a-deletion.md) §4 (an entry names a removed
  row by its token), §8 (an expired token is not reused, for as long as tokens
  are not derived) and §10 (the ledger is off every read path)
- Amends, **at acceptance** — made on 2026-09-29, in the change that accepted
  this record: [ADR 0034](0034-the-store-outside-and-the-reference-that-names-nothing.md)
  §6, in three places — *"behind its own optional protocol — the
  `SupportsRegister` precedent"* (§2 below), *"(kind, token) ↔ text"* as the
  key (§3), and *"The join key is the run key"* (§4). And ADR 0034 §3's
  *"produced where the whole value and the name table are"*, which §7 narrows
  to *inside the process that owns the table*. And `CLAUDE.md`'s fixed
  **decision 2**, by an **addition to its list** of what the end company's
  `.digline/<tenant>/` holds. **It is an addition to the list and not an
  exception to the sentence**: the exception is ADR 0035's, for the ledger,
  which lives outside the directory, and ADR 0035 §2 says why the two
  amendments must not be merged. This record makes only its own
- Names, and does not amend: **ADR 0023 §6 and §7**, whose election record at
  the software house becomes a token line resting on this table (§7). The
  rewrite belongs to ADR 0023, which is still proposed, and waits for it.
  *Noted 2026-09-29: there is no rewrite of ADR 0023. The text this line
  sends a reader to is in
  [ADR 0037](0037-the-review-interface-and-the-election-recorded-where-the-text-is-not.md),
  proposed, a record of its own that supersedes and amends ADR 0023 in part;
  ADR 0023 keeps its text, with a dated note at each place that moves. 0037
  says why it took that form, in its Context. The line is kept as written*
- Closes: ADR 0034 §6's *"what is undesigned"*: the rules that make its
  skeleton work — the token's form, look-up-or-mint, who writes, what a
  resolver refuses. And **ADR 0035 §8's condition**, *"for as long as tokens
  are not derived"*, which §5 turns from a condition on a future design into a
  property of this one
- Touches, in `CLAUDE.md`'s *fixed* section: **decision 1** is upheld: the
  core treats a kind as an opaque string and never opens a table (§3).
  **Decision 2** gets an addition to its list, and keeps its stated reason
  whole: no database in a home directory, no global state (§2). **Decision 5**
  is untouched: the table is a file the owning process reads, never a service
  digline calls. **Decision 8** is upheld by a token form that has no row in
  another tenant's table (§5). **Decision 9** is upheld: a token is not derived
  from its text, so nothing about a token is a digest (§5)
- Number: 0036. Swept on 2026-09-29, before a line was written, across
  `origin/main` (`554b384`), every local branch and tag, every remote ref, the
  `docs/adr/` of all four worktrees (capture's included, whose highest is
  0023), the one stash, the five open pull requests (#212 to #217, none
  touching `docs/adr/`), and the site repository's refs and three worktrees.
  The highest number taken anywhere is 0035, and no ref or working tree
  mentions 0036

## Context

**Two things rest on the table, and neither works without it.** ADR 0034
tokenises the committed reference: six kinds of string become tokens, and the
software house commits a projection in which they stand. A token in the
software house's repository means nothing unless something at the data owner's
side resolves it. And capture's election, settled in discussion for ADR 0023
and not yet written into it, is recorded at the software house as one line per
elected case — a token, a date, and who approved it, never a word of the text.
**That line resolves through the same table**, so capture now waits on it as
the projection does.

*Noted 2026-09-29: "not yet written into it" is still true to the letter, and
it will stay true — the election is not written into ADR 0023 and will not be.
It is written in
[ADR 0037](0037-the-review-interface-and-the-election-recorded-where-the-text-is-not.md)
§5 and §8, proposed, a record of its own; ADR 0023 carries dated notes
pointing there. The sentence above is kept as written.*

**ADR 0034 §6 gives the table a skeleton, and every rule that makes it work is
missing.** The skeleton: one table per (tenant, suite), at the data owner's
side, behind its own optional protocol of the store, holding
(kind, token) ↔ text, rewritable row by row, never committed, joined by the run
key, and carrying its own costs — retention, an erasure obligation, a place in
the layout, and being the re-identification key. What it does not say is what
a token is, whether one can be minted twice, what happens when two hands mint
at once, who the hands are, what a reader does with a token it cannot resolve,
and how a person erases.

**And the skeleton contradicts itself and the tree in three places, found when
the rules were written against it:**

1. **The protocol it cites as precedent is one nothing asks for.**
   `SupportsRegister` is exported from `digline.store` and absent from
   [`docs/api.md`](../api.md), which is the list of what is public. The two
   callers of the register — the reading in `host/reading.py` and the append in
   `host/register.py` — both take a `FileResultStore`, not a store that
   supports a register. **And digline itself has no use for a name table**: the
   process that owns the table is not digline's (§7). So §6 as written asks
   digline to define and document a protocol that nothing in digline would
   implement or call.
2. **Its key carries a part the token form makes idle.** A token unique across
   every table (§5) names one row by itself.
3. **Its join cannot be both things it says.** *"The join key is the run key"*
   sits beside tokens that are stable across documents, which `compare()`
   needs. If tokens are stable per suite, a look-up needs no run key. If the
   join is per run, tokens are not stable across documents.

## Decision

### 1. What the table is

> **One table per (tenant, suite), at the data owner's side. A row is a
> token, a kind and a text. It is rewritable row by row, and it is never
> committed.**

This is ADR 0034 §6's skeleton, kept where it holds. **Never committed**
because a committed file's retention is git (ADR 0021 §6), and a table whose
retention is git is a table nobody can shorten. **Rewritable row by row**
because an erasure is the removal of a row (§9).

**The table is the re-identification key.** ADR 0034 §6 says so and this
record keeps it in the first section, not in a footnote: whoever holds the
table and a committed projection holds the names. A restored backup of the
table re-identifies every token whose row was removed. Nothing here changes
that, and §*What this record does not claim* repeats it.

### 2. It lives outside the store: digline is handed it, and never opens it

> **The table is not a capability of the store.** There is no
> `SupportsNames`, no method on `ResultStore`, and no member of any protocol
> in `digline.store` that reads or writes a row. **digline's code reaches the
> table only through two callables it is handed**: one that returns the token
> for a (kind, text), minting if there is none, and one that returns the row a
> token names, or nothing. *Decided here.*

**The precedent is in the tree, and it is not `SupportsRegister`.** The
journal's own protocol says of the driver: *"`execute()` is handed `append` as
a callback and learns nothing about where the record lands."* The projection
and the resolver take the same shape. They are handed a function, they call
it, and they learn nothing about where the table is, what format it has, or
what lock guards it. The two callables are parameters of the functions that
call them, typed where those functions are. They are not a store capability
and not an extension point for backends.

**Why not the protocol ADR 0034 §6 names, and what that side would have
cost.** Four costs, and they accumulate:

1. **A public protocol with no implementer and no caller in digline.** A
   protocol in `digline.store` is part of what a backend may be asked for. To
   be public it has to be in `docs/api.md`, and to be kept honest it has to be
   called by something the test suite drives. Nothing in digline would call
   it: the three writers run in a process that is not digline's (§7). A
   protocol that only an outside program implements and only that same program
   calls is that program's interface, documented in the wrong repository.
2. **The precedent does not carry what it was cited for.** `SupportsRegister`
   is exported and undocumented, and its callers ask for the concrete store.
   ADR 0021 §5's reason for it — *the planned production store is not obliged
   to write an append-only file in a repository* — is a reason for a store to
   be allowed to lack a capability. It is not a reason for a capability that
   no store in digline has.
3. **A store without it would not be a working store under the split.** A
   store that cannot journal is used as it is used today (ADR 0017 §5). A
   store that cannot hold the table could neither project nor resolve, so
   *optional* would be optional in type and mandatory in fact. ADR 0034 §6
   does not state that cost.
4. **Concurrency would become a question for the protocol.** Look-up-or-mint is
   atomic because one process owns the table (§6). Behind a store protocol, the
   atomicity would have to be each backend's, as every other race on the store
   is. The process's shape would stop being the answer.

**What this side costs, stated and not discounted:**

- **ADR 0034 §6 is wrong as written, and an accepted record is amended.** The
  clause is struck at acceptance, with a dated note in 0034 beside it, the way
  every earlier correction to 0034 was made. *Made 2026-09-29, in the change
  that accepted this record.*
- **ADR 0034 §14's delete does not reach the table by construction.** It would
  have, as a sixth item behind the store. §4 says why that is right rather
  than a loss: a run's removal must not remove rows. But it means nothing in
  digline removes a row, ever. Removal is the owning process's (§9).
- **A file in digline's layout whose format digline does not define.** The
  table sits in the tenant's directory, so decision 2's list names it. Its
  format, its lock and its code are the owning process's. That is a first: every
  other file under `.digline/<tenant>/` is written by digline.
- **The seam is untyped at the table's side.** digline types the two callables
  it takes. Whether the owning process's table meets them is checked where it
  hands them over, not by any `isinstance` in digline.

**The table's place: a reserved name in the tenant's directory, which digline
keeps and never writes.** *Decided here.* This is the addition to decision 2's
list, and it is what keeps decision 2's reason whole: the table is not in a
home directory and is not global state, and it is addressed by the tenant like
everything else in the perimeter. **digline reserves the name** — nothing
digline writes may land there, and nothing that walks a tenant's directory
treats what is there as its own — **and reads and writes nothing under it.**
The spelling of the name is fixed at implementation, not here.

**What `read_run` and `scan_runs` need to know about the table: nothing.** At
the data owner's side they return whole documents. Only the projection and the
resolver meet tokens, and each is handed its callable.

### 3. The key is the token; the kind is a check

> **A row is found by its token alone.** The kind stays in the row, because
> look-up-or-mint is keyed by (kind, text) (§6). **At resolution the kind is a
> consistency check**: a row whose kind is not the kind of the place its token
> sits in is refused, by name. *Decided here.*

**Why the token alone.** A token has no scope (§5). It is unique across every
kind and every table, so the kind adds nothing to what makes the key unique.
ADR 0034 §6's (kind, token) is amended to the token.

**Why the kind stays anyway, and what it is for.** Minting needs it: the same
string used as a group label and as a configuration value gets two tokens, not
one (§6). So every row has a kind whatever the key is. At resolution the place
a token sits in implies a kind — a `case_id` field, a group inside an expanded
name, a configuration key — and the check compares the two.

**Why a mismatch is refused, and not read.** With 128 random bits, a token
whose row has another kind is not a collision (§5). It is a document or a table
that somebody edited by hand, or a writer with a defect. Either way the
resolution would put one kind's text where another kind's belongs, and read
green. A refusal is the only answer that does not.

**The core treats a kind as an opaque string.** It compares two kinds for
equality and knows no list of them. ADR 0034 §5 names six kinds today and
capture may add one (§7). The core does not change when that list does.

*Noted 2026-10-05; the paragraph above is kept as written.* **The kinds are
ten, not six.** ADR 0034 §5 names six *strings*. The code has ten *kinds*
(`TokenKind` in `src/digline/core/tokens.py`, measured at `7b130c3`). The
sixth string, configuration keys and values, is five kinds there: a key kind
and a value kind on the target's side and on the judge's, and the judge's
`provider/model` identity. They are separate so that an equality between two
places does not tell the software house what it must not have. The Context's
*"six kinds of string"* and §5's *"all six"* count the same way. Capture adds
no kind: an elected case's token is of the `case_id` kind (§7, ruled
2026-10-05).

### 4. Tokens are per (tenant, suite); the run key joins nothing in the table

> **A token is stable for the life of its row, across every document of its
> suite.** The run key addresses documents. **It is not a column of the
> table, and it joins nothing in it.** *Decided here.*

**Which half of ADR 0034 §6's sentence gives way, and why that one.**
`compare()` pairs two documents by `case_id` and by the group inside an
expanded name, and ADR 0028 §6's `_expansion` needs group-token equality across
two documents to tell `new_group` from `now_grouped`. A token minted per run
would give the same case two tokens in two runs, and every comparison would
read *everything new, everything missing*: exit 0, green, with nothing paired.
**Stability across documents is required, so the join by run falls.**

**What §6's paragraph got right, and where it belongs.** Its reasoning — the
run key is `key_of(created_at, config_hash)`, *"Nothing here ever sees a case"*,
so the key already carries nothing and survives a case being erased — is true.
It is true of **the link** the software house commits beside a projection (ADR
0034 §1), which names which reference a commit was judged against. It was
never a property of the table's rows.

**The consequence for a removal.** A row is shared by every run of the suite
that names it. **So removing a run removes no row**: other runs, and every
committed projection of them, still name it. A row goes only by erasure (§9).
ADR 0034 §14's delete is run-grain and stays that way.

**The consequence for capture.** An election mints a row before any run
exists (§7). With tokens per suite, a later projection of a run containing
that case finds the same row and the same token, and the software house's
election line and its projection name one case with one token.

### 5. The token: 128 random bits, 22 characters, no scope

> **A token is 128 bits from a cryptographic source, written in url-safe
> base64 without padding: 22 characters. It has no scope — unique across every
> kind and every tenant's table, not within one.**

**Random, not derived.** A token is not a function of its text, of its kind,
of a counter or of a position. ADR 0034 §5 refuses a digest outright —
*"Hashing is not one of the options"* — on ADR 0003 §4's ground: a digest of a
group label or a case id is a verifier over a small space. That ground reaches
the kinds whose text is the end company's. It does not reach the kinds the
suite declares — a band's `check`, an artifact path, a verdict's name equal to
its assertion's — because the software house already holds that text, and a
digest would hide nothing from it. **The refusal holds there for a different
reason: one rule and one table for every kind.** What separates a random token
from a digest is that nobody can derive it, and uniformity is what extends
that to all six.

**No scope.** ADR 0034 §13 says that, on a store holding several tenants, a
typed flag is the tenant's source, and a typo can name another tenant. A token
unique only inside its table would, against the wrong tenant's table, find a
row — another client's text — and read green. **A token unique everywhere has
no row in any other table**, so the wrong table finds nothing, and §8 refuses.
This is fixed decision 8's addressing carried into the token: filing one
client's names as another's becomes a refused mistake, not a silent one.

**Never minted twice, and the condition it rests on.** A random token is
minted twice only by a collision. At 128 bits the chance of any collision
among a billion tokens is about one and a half in a thousand billion billion,
computed and not measured.
**Nothing handles a collision, and nothing needs to.** Written as the
condition it rests on: *"never minted twice"* holds **for as long as the token
space is large enough that a collision is not a case anyone has to handle** —
**unhandleable, rather than handled**. A shorter token chosen for readability,
or 128 bits from a seeded or non-cryptographic generator, is the same length
and not the same property, and it reopens reuse without anybody noticing. In
Python the source is `secrets`, never `random`.

**Why that is the whole of non-reuse, and no memory is kept.** A committed
projection lives in the software house's git for good. If a token whose row
was erased could be minted again for new text, every old projection would
resolve to the new text: wrong, silent, green. The alternative to a large
random token is a memory of every token ever issued, kept after its row is
gone. **That memory is refused**, and the line is the read path. A memory
consulted when minting or resolving is a marker a reader meets, and it
confuses *erased* with *never minted here*. ADR 0034 §14 requires a removed
run to be absent from every reader of the store, and ADR 0035 §10 keeps the
ledger off every read path for the same reason. **The table and the run store
remember nothing of what was removed.** The ledger records removals, off the
read path, and neither minting nor resolving consults it.

**This closes ADR 0035 §8's condition.** 0035 §8 says an expired token is not
reused *"for as long as tokens are not derived"*, and that it is *"the name
table's design that keeps it so"*. This is that design.

### 6. Look-up-or-mint: keyed by (kind, text), and atomic because one process owns the table

> **Minting is one act: look the (kind, text) up, and mint only if it is
> absent.** It is keyed by (kind, text), not by text. **It is atomic because
> one process owns the table, and holds one table per (tenant, suite)**, and
> an in-process lock closes the window between the look-up and the mint.

**Why (kind, text).** Keyed by the text alone, one string used as a group
label and as a configuration value would get one token, and a projection would
disclose that two fields of different kinds carry equal text. The leak is real
and closing it costs nothing.

**Why it must be atomic.** Two minters at once — two promotions, two reviewers
at a served page, a projection and an election — with a look-up that is not
atomic give one text two tokens. The two tokens pair as `new` plus `missing`,
which is exit 0. That is the case-id hazard that fails green. **The other
half of the hazard, two texts one token, is not a race under §5**: it is a
collision, and §5 makes it unhandleable.

**Why one process is the answer, and nothing is added.** The process that owns
the table is one process per data owner, never one for several. With one
process holding one table per (tenant, suite), there are never two writers at
once, and an in-process lock closes the window completely. The process's shape removes a named hole instead of adding
work, as it would for ADR 0031's check-then-rename window, which 0031 leaves
open in its own words: *"Closing that needs a lock."* A single owning process
holds that lock for free.

**Written as the condition it rests on:** the lock is sufficient **for as long
as nothing outside the owning process writes the table, and the process holds
one table per (tenant, suite)**. Two processes on one store, or any outside
program touching the file, and the lock guards nothing.
**Nothing detects a second writer outside the process today**, and this record
provides no detection. A lease on the table, the obvious detector, is the stale
lock ADR 0031 refuses — a lease left by a killed process blocks everything
behind it — and what clears one is not decided here.

*Ruled 2026-09-29.* **Inside the process, a second table for a (tenant, suite)
it already holds is refused.** The first half of the condition does not cover
it. Two tables for one (tenant, suite) in the owning process are two locks,
each sufficient for its own table and neither for the other. The same (kind,
text) gets one token from each, and the two pair as `new` plus `missing`, exit
0 — the hazard this section closes. It is not a race and not an outside
writer. Once the table is on disk it becomes a second writer inside the
process, with the first half of the condition still met. **The section already
assumed one table; the condition now says so, and the refusal enforces it.**
The refusal is the owning process's, not digline's: digline never holds a
table (§2), so `host.REFUSALS` does not carry it.

### 7. Three writers, and all three run inside the owning process

> **The table has three writers — the projection, the election, and the
> erasure — and all three run inside the process that owns it.**

**This is one consequence applied three times, not three decisions.** §6's
condition says nothing outside the owning process writes the table. The
projection mints, the election mints, and the erasure removes. A writer run as
a separate command, by the data owner's staff or by a script, would be exactly
the outside writer the condition excludes: the design would fire its own
condition without needing an accident.

- **The projection** mints the tokens of a reference. ADR 0034 §3 places it
  *"where the whole value and the name table are, which is the data owner's
  side"*. That is no longer enough: it runs **inside the process that owns the
  table**. The amendment to §3 is made at acceptance. *Made 2026-09-29, in
  the change that accepted this record.*
- **The election** mints the token of a case elected at a served page at the
  data owner's side. **The software house records it as one line: a token, a
  date and who approved it, never a word of the text.** That is capture's
  shape as settled in discussion. It is written into ADR 0023 §6 and §7 by
  ADR 0023's own rewrite, not here. *Noted 2026-09-29: it is written in
  [ADR 0037](0037-the-review-interface-and-the-election-recorded-where-the-text-is-not.md)
  §5 and §8, proposed, and not in a rewrite of ADR 0023, which does not
  exist; ADR 0023 §6 and §7 carry dated notes pointing there.* **Whether an elected case's token is the
  `case_id` kind or a kind of its own is not decided here.** Under §4 either
  works: the line resolves by token alone, without carrying a kind.

  *Ruled 2026-10-05; the bullet above is kept as written.* **An elected
  case's token is of the `case_id` kind.** The two sentences contradict each
  other. §4 already states the outcome as a consequence it wants: *"a later
  projection of a run containing that case finds the same row and the same
  token, and the software house's election line and its projection name one
  case with one token."* Look-up-or-mint is keyed by (kind, text) (§6), so
  that holds only if the election mints under the kind the projection mints
  a case's id under, which is `case_id`. Under a kind of its own, the same
  case has two rows and two tokens. *"Either works"* is true of the
  mechanism, because the line resolves by token alone. It is false of that
  outcome. **§4 prevails, because it states a consequence, and this bullet
  speaks only of the mechanism.**
  Written as the condition the outcome rests on: one case, one token **for
  as long as the election mints the same text the case carries as its
  `case_id` in a run**, whichever rule makes that id (below).
- **The erasure** removes rows (§9).

*Amended 2026-10-01: the sentence
[ADR 0038](0038-the-projection-of-a-run-nobody-promoted.md) §4 named as owed
here. The section above is kept as written.* **The projection also mints the
tokens of a run nobody promoted, whenever a page served at the data owner's
side shows that run** (ADR 0038 §1). It is still the projection, and there are
still three writers. What changed is what the projection projects, and when it
runs.

**What this section said about *when*, and what it did not say.** It names who
writes and where, and never when. The projection's bullet ties the writer to
its object, a reference, and a reference is projected once, when it is
promoted. So until ADR 0038 the table grew only when somebody promoted or
elected. A round that ran and was never promoted wrote nothing to it.

**So the table now grows with reading, not only with promoting and electing.**
Look-up-or-mint (§6) mints only for a (kind, text) the table does not hold. A
page shown twice therefore writes once. The table grows with the distinct names
in the runs somebody looked at, not with the number of views. Some of those
names no reference will ever carry:
- a case added and dropped before any promotion;
- a check renamed between two rounds;
- a configuration value one round reported and the next did not.

Until now, a row named something that had been in a promoted reference or in an
election. **Now a row may name something that was only ever on a screen.**

**Nothing in this record assumed the table stops growing. One of its
conditions now reads differently.** No size is set anywhere here: §9 says
*"nothing counts toward one"*. But §9's condition, that assisted erasure holds
*"for as long as a suite stays small enough to be read in full by the person
erasing"*, is measured in the suite, while the person erasing reads the table's
rows.
- **While only references were projected**, every row named something
  promoted from the suite or elected into it.
- **Rows minted by viewing are bounded by what was viewed.** For the
  configuration kinds, the suite's size does not bound that.

**Written as the condition it rests on:** this is the projection writer inside
the owning process, **for as long as the process that serves the page is the
process that owns the table**. A page served by any other process that minted
tokens would be the outside writer §6's condition excludes. Inside the process,
§6 already counts *"two reviewers at a served page"* among the minters its
lock serves.

**The erasure path, owed to [ADR 0035](0035-the-record-of-a-deletion.md) and not
resolved here.** An erasure removes rows (§9), and ADR 0035 records each
removal by the row's token.
- **ADR 0035 §4 rests that on a ground a row minted by viewing may not meet.**
  It says the committed projections *"already hold it for as long as git keeps
  them"*. A row minted by viewing can have a token that no committed document
  carries: it was on a page, and it is in the table.
- **For such a row, an entry naming its token is the only record digline knows
  of** that the token existed outside the table.
- **Owed to ADR 0035:** whether an entry still names such a row by its token,
  and what the ledger says about a token that never left.
- **ADR 0035 §8's paragraph on an expired token makes the same assumption.**
  It says *"the software house's git still carries it in old projections"*, and
  it is owed the same reading.

**Whether the three are one component or several is not decided.** Where they
run is.

**The two ids of a captured case.** ADR 0023 §6 mints the id a captured case
carries inside the perimeter as a hash of `vars`, on purpose: two elections of
one item mint one id. That id never leaves. The token is the id that leaves,
and it is random. **This record does not decide whether the inside id follows
§5's rule**, and ADR 0023 §6 is unchanged by it.

### 8. The resolver refuses a document in which no token resolves

> **A resolver refuses a document in which not one token resolves.** Token by
> token it distinguishes nothing: a token with no row is read as unresolved,
> whatever the reason.

**Zero resolved is the wrong table, not a document erased whole.** Under §5 a
token has no row in another tenant's table, and none in another suite's. A
document read against the wrong table therefore resolves nothing at all, and
the refusal is §5's no-scope carried to its end: loud where it would have been
green. A document read against the right table with some rows erased resolves
the rest, and is read.

**Why token by token nothing is told apart.** An unresolvable token can mean
erased, never minted here, the wrong table, or a hand edit. Telling *erased*
from *never minted* would need a memory of erasures on the read path, which §5
refuses and ADR 0035 §10 forbids. The resolver has no need of it: the whole
document already answers the only question that matters, which is whether this
is the right table.

**Written as the condition it rests on:** it holds **for as long as every
projected document carries at least one token that no erasure has removed**.
If a person erases every row a document names, the resolver refuses a
legitimate document. **That fails loud, never green**, and it is the direction
chosen.

**A document with no token at all** — zero resolved of zero — is refused by
the rule as worded. Whether a projection can carry no token is not checked
here.

*Ruled 2026-09-29; the paragraph above is kept as written.* **A document with
no token at all is read, not refused.** Zero tokens is not the wrong table: it
is an empty document, and there is nothing in it that another tenant's table
could resolve. The refusal is for a document that carries tokens of which none
resolves, and only for that one. Whether a projection can carry no token is
still not checked; it no longer needs to be, because the answer changes
nothing the resolver does.

### 9. Erasure is assisted: the surface shows the cases, with every row beside them

> **Erasure is an assisted act, not an automatic one.** digline knows cases,
> not people. It does not find a person. **The erasure surface shows the cases
> with their content, and every row of the table beside them**, and a person
> decides row by row which go.

**Why every row, and not only a case's own.** An erasure request names a
person, and nothing in digline maps a person to cases. A `case_id` row belongs
to one case, but a group label and a reported configuration value are shared
across cases. A group label reading like an agent's surname is seen and
removed; one naming a line of business is left. No rule could make that
decision. A person reading the rows can.

**Why the cases' content, and not only the rows.** A generated id names nobody.
A captured case's id is a hash (ADR 0023 §6), and looking for a person among
tokens and hashes is impossible. **What a person reads is the case** — its
input, and the recorded responses where there are any — and the rows sit
beside it.

**Refused: declaring that group labels and configuration values must carry no
personal data.** A label is free text, so that rule is one nobody can verify.
It would move the problem to the data owner and then trust the data owner to
have solved it.

**Written as the condition it rests on:** assisted erasure holds **for as long
as a suite stays small enough to be read in full by the person erasing.** A
suite is chosen examples, not an archive, and that is what makes reading it
possible. **No size is set here, and nothing counts toward one.**

**The surface runs where the eraser runs: inside the owning process** (§7).

**What an erasure records.** The removal of a row is recorded in the ledger by
the row's token, removal first and entry after (ADR 0035 §4, §6). **The process
that performs that removal, and so appends that entry, is the owning process,
which is not digline's** (§7). ADR 0035 describes its writer as digline's: its
configuration, its format, its notices and its refusal in `host.REFUSALS`.
**Whose code appends the entry for a row's removal is not decided here.**

*Ruled 2026-09-29.* **Removing a token that has no row is refused, not read as
done.** Otherwise two removals of one row at once would both read as a
success, and nothing would tell the one that removed it from the one that found
it already gone.

## Consequences

- **The projection and capture have something to resolve against.** The rules
  that make ADR 0034 §6's skeleton work are written, and capture's election
  line has a table under it.
- **ADR 0034 §6 is amended in three places**, one of them a reversal: the
  table is outside the store's API, not behind an optional protocol of it
  (§2). ADR 0034 §3 is narrowed (§7).
- **`digline.store` gains nothing.** No method, no protocol, no documentation
  of a capability nothing in digline uses.
- **The tenant's directory gains a reserved name that digline never writes**,
  the first file in the layout whose format is not digline's (§2).
- **A run's removal never removes a row** (§4). Only an erasure does, and only
  inside the owning process.
- **Two refusals**: a document in which no token resolves, and a row of the
  wrong kind (§3, §8). And one refusal that is the owning process's, not
  digline's: a second table for a (tenant, suite) it already holds (§6).
- **Three conditions this design rests on**, each written where it is made:
  the token space is too large for a collision to be handled (§5); nothing
  outside the owning process writes the table, and the process holds one
  table per (tenant, suite) (§6); a suite can be read in full by the person
  erasing (§9).

## Alternatives considered

- **The table behind an optional protocol of the store**, as ADR 0034 §6
  wrote. Refused in §2, with its four costs.
- **The table as a sixth item on `ResultStore`.** Refused for the same
  reasons, and more strongly: a store without the table would stop being a
  store at all, not only lose a capability.
- **A memory of issued tokens, kept after their rows are gone**, as the
  mechanism of non-reuse. Refused in §5: it is a marker on the read path.
- **A counter, or any structured token.** Refused in §5: a counter's next
  value is a reused one after an erasure, and a structure discloses what it
  encodes.
- **A digest of the text as the token.** Refused in §5, by ADR 0034 §5 for the
  end company's kinds and by uniformity for the suite's.
- **A token scoped by kind or by tenant.** Refused in §5: against the wrong
  table it resolves, and reads green.
- **A short token, for readability.** Refused in §5: it reopens reuse quietly.
- **Look-up-or-mint keyed by text alone.** Refused in §6: it discloses equal
  text across kinds.
- **A lock file or a lease, for atomicity.** Not needed with one process (§6),
  and refused by ADR 0031 as a stale lock where it would be.
- **An eraser run as a separate command.** Refused in §7: it is the outside
  writer §6's condition excludes.
- **Tokens minted per run, to honour *"the join key is the run key"*.**
  Refused in §4: every comparison would read everything new and everything
  missing, and pass.
- **A resolver that tells *erased* from *never minted*, token by token.**
  Refused in §8: it needs the ledger on the read path.
- **Declaring shared fields free of personal data, instead of an assisted
  erasure.** Refused in §9: a rule nobody can verify.

## Not decided here

- **The table's own retention.** ADR 0034 §6 names it as a cost and nobody
  sets it here.
- **Whether the three writers are one component or several** (§7).
- **Whether an elected case's token is the `case_id` kind or a kind of its
  own** (§7), and **whether capture's inside id follows §5's rule** — ADR 0023
  §6 is unchanged.
  *Ruled 2026-10-05, in §7: the token is of the `case_id` kind. The inside
  id's rule is still open. The bullet is kept as written.*
- **What clears a lease left by a killed process**, if a detector for a second
  writer is ever built (§6).
- **Whether the party that produces a projection keeps a copy of it** at the
  data owner's side. If it does, a pseudonymised copy and its key share one
  perimeter. Nothing that writes a projection exists yet, and nothing here
  rules on it.
- **Who resolves, and through which reader**: the resolver's refusal is
  decided (§8), its home and its callers are not.
  *Decided 2026-09-30, in #236: its home is `digline.core`, beside the
  projection, as `resolve_tokens(run, lookup)`. It reads the same map from
  place to kind that the projection writes by. Its caller is the owning
  process. digline itself has none, because it never holds the table and so
  never holds a lookup to pass (§2). A row is a structural type, `NameRow`
  (token, kind, text), which the owning process's rows satisfy without
  importing it. The bullet is kept as written.*
- **The spelling of the reserved name, and the table's format** (§2). The
  format is the owning process's.
  *Spelled 2026-09-30, in #234: the reserved name is a directory,
  `name-table/`, so a table kept in SQLite covers its `-journal`, `-wal` and
  `-shm` beside it. It is reached through `FileResultStore.name_table_dir`,
  and the generated `.gitignore` ignores it. The format stays the owning
  process's. The bullet is kept as written.*
- **What happens to the cases whose shared group label a person removes** (§9).
  It changes what every case that carried it is grouped by.
- **How a person is expected to recognise a row as personal** (§9). The
  assisted erasure assumes it and does not provide it.
- **Whose code appends the ledger entry for a row's removal** (§9). The
  writer is the owning process, which is not digline's. The code it uses may
  be digline's, published and called the way the resolver is, or the owning
  process's own. If it is the owning process's own, ADR 0035's format, notices
  and refusal do not reach it. Also open: **whether a run's removal and a
  row's removal append to one ledger**. If they do, that is two writers on one
  path, the case ADR 0035 §6's condition excludes.
- **What the approver in capture's election line is.** If it names a person on
  the data owner's side, it is a string to classify, and the line's one
  guarantee — it never carries text — has not been checked against it.
- **A document with no token at all** (§8). *Ruled 2026-09-29, in §8: it is
  read, not refused. The bullet is kept as written, and the question is no
  longer open.*

## What this record does not claim

- **That the table is safe.** It is the re-identification key (§1). Whoever
  holds it and a projection holds the names, and a restored backup
  re-identifies every token whose row was removed.
- **That removing a row is an erasure.** ADR 0034 §14 rules that a delete is
  not an erasure on a filesystem somebody backs up, and it applies to a row as
  it does to a run.
- **That the lock is enforced.** It is sufficient under §6's condition, and
  nothing detects the condition failing.
- **That a collision is impossible.** It is too improbable to be a case
  anyone handles, and that is the claim, at 128 bits from a cryptographic
  source (§5).
- **That an assisted erasure satisfies what a controller owes.** That is
  counsel's question, and it is not answered here.
- **That any of this is access control.** Addressing, not access, as fixed
  decision 8 says of every perimeter: a token with no row in another table
  refuses a mistake, not an adversary.
- **That it is lawful.** A pseudonymised record is still personal data.
  Nothing here is legal advice.
