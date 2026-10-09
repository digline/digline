# ADR 0035 — The record of a deletion

- Status: proposed 2026-09-29 — the text first, checkpointed before any code,
  the way [ADR 0021](0021-the-register.md), [ADR 0023](0023-capture.md) and
  [ADR 0034](0034-the-store-outside-and-the-reference-that-names-nothing.md)
  were. Nothing in it is implemented. **Most of what it states was settled
  before it was written**, in discussion, and is recorded here as settled. The
  rest are **decisions this record takes itself**. They are marked *decided
  here* where they are made, so that acceptance can rule on them one by one
- Shipped: unreleased
- Date: 2026-09-29
- Opens: **nothing on landing.** No `SCHEMA_VERSION`, no `OUTPUT_VERSION`, no
  `REGISTER_VERSION`, no `JOURNAL_VERSION`, no migration. The ledger is a new
  format with a version of its own (§4), and it is born at implementation, not
  here
- Requires, at implementation: **a new artifact** outside the tenant's
  directory, at a path the data owner configures (§2). **Two configuration
  keys** that are set together or not at all: the path and the retention
  (§2, §8). **A writer**, which is the process that performs a removal (§6).
  **Two notices**, whose words are fixed here (§9). **A refusal** for two
  tenants configured onto one path, classified in `host.REFUSALS` or
  `tests/test_refusals.py` will not see it (§2). **No new reader anywhere in
  digline** (§10)
- Assumes: [ADR 0002](0002-three-worlds-and-where-the-data-lives.md) §1 (the
  tenant is the perimeter), §2 (the payload stays where it is born, and a flag
  is verified rather than believed) and §6 (retention is mandatory, not a
  setting with a default); [ADR 0003](0003-artifacts-travel-only-when-the-suite-says-so.md)
  §4 (a digest is a verifier over a guessable space); [ADR
  0014](0014-what-may-ride-a-schema-bump.md) §3 (a ledger has its own reason to
  exist, its own retention question and its own boundary question, and a name
  is payload in a way a timestamp is not); [ADR 0021](0021-the-register.md) §1
  (a disposition is a person's), §5 (nothing rewrites a committed line) and §6
  (absence is stated, never read as zero); [ADR
  0034](0034-the-store-outside-and-the-reference-that-names-nothing.md) §1 (the
  store lives in the end company's perimeter), §5 (a token and not a digest),
  §6 (the name table, rewritable row by row, and a restored backup
  re-identifies), §12 (who the digests protect against, and what reopens it)
  and §14 (a delete, a removed run absent from every reader, and a delete is
  not an erasure)
- Amends, **at acceptance**: `CLAUDE.md`'s fixed **decision 2**, by an
  **exception** to its sentence *"Everything lives in `.digline/<tenant>/`"*
  (§2). **It is an exception to that sentence and not an entry in the list** of
  what the end company's store holds, and §2 says why the two must not be
  merged
- Names, and does not amend: **ADR 0021 §6**'s journal paragraph, whose premise
  *"a record of the journal's existence held somewhere that does not expire —
  which is a committed file"* this record makes false for deletions (§1). The
  correction belongs to ADR 0021. Its wording must say *nobody can rewrite* and
  never *does not expire*, which §8 makes false of this ledger. It also has to
  say whether it reopens the expired-journal case or is confined to deletions,
  and this record does not decide that. **The name table's own place in fixed
  decision 2**, which is an **addition to the list**, a different amendment
  from this record's, and not made here (§2)
- Closes: ADR 0034 §14's unstated half. §14 requires that a removed run be
  absent from every reader. It does not say where the fact of the removal is
  kept, and a reader who owes an authority that fact had nowhere to find it.
  **This is that place.** ADR 0034 §*Not decided here*'s *"erasure as a
  procedure"* is **not** closed: this record keeps the record of a removal, not
  the procedure that decides one (§*Not decided here*)
- Touches, in `CLAUDE.md`'s *fixed* section: **decision 2** gets an exception
  (§2), and keeps its stated reason whole: nothing in a home directory, no
  global state, and the ledger's location is configured per tenant by the
  owner of the data. **Decision 5** is upheld: the ledger is a path, never a
  service that digline calls (§2). **Decision 8** is upheld by making the path
  per tenant and refusing a shared one (§2). **Decision 9** is upheld: no
  field of an entry is a digest, and §5 is where that is measured rather than
  assumed
- Number: 0035. Swept on 2026-09-29, before a line was written, across
  `origin/main` (`4a4fe17`), every remote ref, every local branch and tag, every
  sibling worktree's `docs/adr/`, the one stash, the open pull requests (none),
  and the site repository's refs. The highest number taken anywhere is 0034

## Context

**ADR 0034 §14 gave the product a delete, and with it a question it did not
answer.** Before §14, nothing in digline removed anything. The retention of a
run document was *forever, by omission*. §14 adds the verb and states its
contract: *"A removed run must be absent from every reader — `scan_runs` and
`read_run` included."* ADR 0034 §6 adds the other removal, a row of the name
table: *"an erasure needs a writer that removes a row."*

**Neither says where the fact of a removal is kept.** The one party that needs
it is the end company, when it owes an authority proof that it erased what it
was asked to erase. The gate's exit code does not depend on it: an absent run
is an absent run. Promotion's conditions begin with `read_run` and do not
depend on it. The register's reading does not depend on it. **One consumer,
at administrative time, needing a record that a removal happened**, and three
constraints that leave that record no home among the artifacts that exist:

1. **The store may not hold it.** §14 forbids a marker a reader could meet: a
   tombstone in the run store is an erasure left incomplete. A tombstone that
   carried the run's key would carry `created_at` and `config_hash`, which may
   be exactly what had to go.
2. **A committed file is on the wrong side.** Under ADR 0034 the repository
   that commits is the software house's, and the removal runs in the end
   company's perimeter. Giving the end company a committed side would put git
   there, and ADR 0034 §3's division between the side that produces and the
   side that commits holds *"for as long as there is no git there"*.
3. **The register is not it** (§3).

**What ADR 0021 §6 said about the one similar case.** Meeting an expired
journal, it declined to record the journal's existence because *"solving it
would take a record of the journal's existence held somewhere that does not
expire — which is a committed file, which is the thing §1 says the journal is
not."* The rule of §6 stays true: *absence is stated, never read as zero;
rotation is allowed for ignored files only; a committed file's retention is
git.* What this record makes false is the premise in that sentence: that only a
committed file can hold a record nobody rewrites. **The property was never
git. Git was the only thing that had it**, and git never had it from the writer
alone. A commit on a protected `main` cannot be rewritten because of the other
holders: the clones, the remote, the ruleset that blocks force pushes. §7 says
where the property comes from here.

## Decision

### 1. A ledger of removals exists, at the data owner's side

> **A removal from the store, of a run or of a name-table row, is recorded in
> a ledger that lives at the data owner's side, is written only by appending,
> and sits apart from the data whose removal it records.**

**What it is for, and it is the whole of it:** a controller showing an
authority that it performed the erasures it owed. That use is rare, it is
deliberate, and it is aimed at someone outside both the software house and
digline. Every other decision below is measured against it.

**What it protects, and against whom.** **Not against the end company.** The
end company is the controller, and the data is theirs. The ledger protects the
end company **towards an authority**, by showing that the gesture was made. A
ledger its keeper could alter is still its keeper's evidence, the way a book
of accounts kept by the company it describes is falsifiable and is still the
basis of those accounts. A dishonest keeper can alter it. A dishonest keeper
can also simply not erase.

### 2. Where it lives: a path the data owner configures, one per tenant

**The ledger lives at a path the data owner configures. The process that
writes it does not choose the path.**

**Why a configurable path, and not a place digline picks.** It is the only
shape that lets the data owner point the ledger at a volume with a backup
regime of its own, or at storage that refuses modification (§7). A path
digline chose would sit wherever digline chose it, under whatever regime that
place already had, and a constraint the data owner configures cannot be given
to a place the data owner did not pick.

**Two shapes refused:**
- **A sibling directory under `.digline/`, outside `<tenant>/`.** It solves
  nothing. It is on the same volume, under the same backups, and a data owner
  cannot give a subdirectory a regime of its own. *Apart from the data* (§11)
  would be met in wording and not in fact.
- **A service digline calls.** It removes the storage problem and adds a worse
  one. Fixed decision 5 refuses any network call the user has not configured,
  and a ledger that needed one would make every erasure depend on it.

**This is an exception to fixed decision 2's sentence, not an entry in its
list.** Decision 2, as ADR 0034 §1 widened it, says *"Everything lives in
`.digline/<tenant>/`"* and then enumerates what the end company's store holds.
A configurable path is outside `.digline/<tenant>/` by construction, so it is
an **exception to the sentence**. The amendment, at acceptance, says so, and
keeps the decision's stated reason whole: nothing in a home directory, no
global state on a machine, and a location set by the owner of the data for
one tenant.
**The name table is a different amendment.** It lives inside the store's
layout, beside the data, and it is missing from decision 2's **list**, so its
amendment is an **addition to the list**. The two artifacts are met in the
same paragraph of decision 2, and they need two different changes. **They
must not be merged into one amendment**, and this record makes only its own.

**Per tenant, and a shared path is refused. Decided here.** Fixed decision 8
makes the tenant the perimeter, and it enforces **addressing** by putting the
tenant in the directory layout: filing one client's history as another's is a
refused mistake. A path outside `.digline/<tenant>/` loses that addressing, so
the configuration carries it instead. **The ledger's path is configured per
tenant**, and the writer **refuses to start** when two tenants are configured
onto the same path. A ledger shared by tenants would hold several perimeters'
removals in one place, with nothing in its location to tell them apart.

**Set at the data owner's side, and nowhere else.** The path is configuration
the data owner writes where the store is. Nothing the software house sends can
set it or change it. If it could, the software house would decide where the
controller's record of its own erasures lives, which is the opposite of this
section's first sentence.

### 3. It is not the register

The register ([ADR 0021](0021-the-register.md)) is append-only, typed, and
already a ledger. **It cannot be this one, for four reasons, and they
accumulate rather than compete:**

1. **It lives at the software house, in git.** This ledger lives at the data
   owner's side (§1).
2. **It is already on a read path.** `digline log` has a register section, and
   the wire carries it (`wire/log.py`, `register_entry_json`). A removal
   recorded there would land where a reader meets it, which §10 forbids.
3. **Git's retention would decide §8 by placement.** A committed file's
   retention is git (ADR 0021 §6), so a ledger in the register would never
   expire, and nobody would have chosen that.
4. **Its outcome counts include what was removed.** A register entry counts
   the cases of the comparison it records. The record of a removal would sit
   in the file whose counts the removal made stale.

**And three things the separate ledger has that the register lacks**, which
is why this is a choice and not only the last option standing. It is off every
read path (§10). It sits apart from the data's backups (§11). It has storage of
its own, which the data owner can make refuse modification (§7).

### 4. What an entry carries, and what it never carries

**One line per removal, in a format of its own**, `LEDGER_VERSION = 1`,
independent of every other version in the tree, never migrated. A line this
digline cannot read is refused by name and left where it is, as ADR 0021 §5
does for the register.

**An entry is written by the process that performs the removal:** for a
name-table row, the process that owns the table (ADR 0036 §9); for a run,
digline.

**An entry carries:**
- **what was removed, named without its content:**
  - for a **name-table row**, the row's **token**. A token carries no text
    (ADR 0034 §5). Where the token was handed out in a document meant for a
    commit, the software house's git may also hold it, for as long as it keeps
    that document; where it was not, nothing outside the table and this entry
    ever named it. The entry says which of the two holds (below);
  - for a **run**, the run's **`created_at`** and nothing else of its key
    (§5). Where nothing readable carried it, a run with no document whose
    every journal leg was refused, the entry is still written, and names the
    run with an explicit value, `created_at-not-readable`: the name was not
    readable, and that is stated, not left out;
- **when** the removal was made;
- **for a row, who decided it**: the identity the owning process records for
  the person who decided, with its **kind**, a person or a machine, and
  **where that identity came from**. **The identity is recorded so that it
  cannot mean two people:** a name freed by one person and given to another
  must not make an older entry name the newcomer. The form that guarantees it
  is not decided here. It is the requirement every record of a person's act
  carries, and an entry takes the form that requirement is given;
- **for a run, no identity.** digline records no person. A required field
  nobody can fill is not a requirement. It is a block written by mistake;
- **for a row, whether its token was handed out:** `handed_out`, with two
  values, always written and never left out:
  `in-a-document-meant-for-a-commit` or `not-handed-out-for-a-commit`.

**Two documents hand a token out for a commit:** a projection committed at the
software house, and an election line (ADR 0037 §5). **The first path that
hands a token out in either marks the row when it hands it out.** Whoever
removes a row reads the mark before removing it, and a row without a mark has
not been handed out, by construction. The mark, and where it is kept, arrive
with that first path: at the time of this record no path hands a token out
for a commit, so every row is unmarked, and that is known from the code, not
from anything a row carries. **If a path ever hands a token out without
marking the row, a third value is owed.**

**What the mark cannot tell, and so what `handed_out` never claims:** that the
document was committed; that the commit was not rewritten; that a person did
not copy a token by hand from a served page into a commit. Its name says what
is known, and never asserts a commit.

**An entry never carries:**
- **what the row said**, or anything the run contained;
- **which request caused the removal.** A request identifier names the person
  who asked to be erased. That is the reason it is excluded. ADR 0014 §3's
  *"a name is payload"* would exclude the decider's identity too, and at the
  data owner's side payload is where it belongs.

**What it says, in its own words:** *"this row was removed from this store"*
and *"this run was removed from this store"*. **Never *"this data no longer
exists"*.** ADR 0034 §14 already rules that a delete is not an erasure on a
filesystem somebody backs up: the old blocks survive until reused, a
copy-on-write filesystem keeps them, a snapshot holds the removed row. **No
entry can prove the data is gone. It can prove the gesture was made**, and the
gesture is what a controller has to show. A ledger that claimed more would
announce a guarantee nothing provides, which ADR 0002 §2 calls worse than no
flag.

**A journal leg has no entry of its own. Decided here.** A leg belongs to a
run, and a leg has no key of its own. The run's `created_at` is in the
journal's header, so an entry for a run names it **whether the run was removed
as a document, as legs, or as both.** One run, one entry.

**`created_at` is not unique by construction, and this record does not
assume the practice. Decided here.** `utc_now_iso` keeps microseconds because
two runs in the same second once collided. But that collision needed the same
suite as well, and `created_at` alone needs only the same microsecond, for any
two runs within the tenant's ledger. And `created_at` is a wall clock: a clock
stepped backwards, by NTP or by hand, repeats a microsecond with no coincidence
at all. **So the ledger never treats `created_at` as a key.** An entry is the
record of one gesture. Two removals that name the same `created_at` are
**two entries**, not a conflict. Each entry carries its **position in the
segment it was appended to** (§7), which is a sequence number, not a digest.
A position is a place in one segment of one ledger, and is compared with
nothing outside it.

**A matching yields a count, and a unique correspondence is never assumed.**
The rule binds whoever matches a run key to the ledger (§5), which is the data
owner at administrative time. **No tool of digline does the matching** (§10).
An entry whose run was named `created_at-not-readable` is matched by no key, by
construction, and no count includes it: what it keeps is that a removal
happened, which is what an authority is shown, not a correspondence anyone can
recover.

### 5. No digest in an entry — measured, not assumed

**The run's key would have been the obvious name, and it is refused.**
`key_of(created_at, config_hash)` is `created_at`, slugged, then `config_hash`,
in clear. `config_hash` is not a digest of configuration in the sense of a
model and a temperature. It digests each assertion's **identity**: its type
and its parameters, meaning the needle, the pattern, the schema and the
rubric. It also digests their thresholds and tolerances, `samples`,
`min_agreement` and the declared price. **A rubric is exactly the text ADR
0003 §4 keeps from travelling**, and ADR 0034 §12 already calls `config_hash`
*"the most widely travelling digest in the tree"*.

**ADR 0034 §12 answered who that digest protects against: nobody in
particular.** The reason is that the committed reference and the suite live
in one repository, so whoever reads the digest already holds its inputs.
Its status line says what would reopen that answer: *"a backup taken apart
from the source, a handover to a third party, or a later design that ships a
reference on its own."* **This ledger has both properties.** It sits apart,
with backups of its own (§2, §11), and its use is to be shown to an authority
that holds no suite (§1). **A `config_hash` in an entry would be a digest
reaching a place its inputs do not.**

**Measured on 2026-09-29, at `4a4fe17`, with ADR 0003 §4's loop pointed at
`config_hash`.** The attacker is modelled as holding one string, a
`config_hash`, and nothing else. There are two controls, because without them
*not recovered* cannot be told from *not searched well*:

| Case | Space | Result |
|---|---|---|
| **Control, must recover.** `[IsJson()]`, default values, `samples=1` | four built-ins that take no argument, subsets of one to three, × samples 1–5 | recovered after 6 candidates |
| **ADR 0003 §4's own model.** The software house wrote the template, the end company tuned the numbers: an `LlmRubric` *"Escalate the ticket when the refund exceeds {X} EUR and the account is older than {Y} days."* beside a `PiiAbsent`, with a declared list price | X 100–5000 by 50, Y in six values, threshold 0.50–0.95 by 0.05, samples 1–5: **29,700** | **recovered after 14,523 candidates, in 0.56 s**, returning the rubric with **2500** and **90** in it, threshold 0.7 and samples 3 |
| **Control, must not recover.** The same template with X = 2537, off the grid | the same 29,700 | not recovered, space exhausted in 1.16 s |

**What decides it is the template, not the hash.** A template shared across a
software house's clients makes the recovery a loop of seconds, and that is the
ordinary case, not the rare one. **And a recovery returns text, not more
digests.** Identities are 64-bit digests and nobody enumerates those. The loop
enumerates candidate suites, and a hit confirms the whole guess.
*The loop was run from a working note and is not in this repository. The
table gives its three cases and its grid so that it can be rebuilt. An
unknown price multiplies the space, to about two billion candidates for ±20%
to the cent on two rates. That figure is computed, not run. An unknown
template is beyond this loop, and it is not shown to be safe.*

**So a removed run is named by `created_at` alone.** It is a timestamp, and it
digests nothing. **It is a weaker name, taken against a measured leak.** It
also breaks the correspondence with the run key used everywhere else, but in
one direction only. Whoever holds a key can slug an entry's `created_at` and
match the key's prefix, so key → entry works, with the count §4 requires.
Entry → key does not. For this ledger's use that costs nothing: the authority
it is shown to holds no keys, and the holders of keys never read it (§10).

**Every field of an entry, checked against the same question:**
- a **token** is not derived from its text, by ADR 0034 §5;
- **`created_at`** and **when** are clocks;
- **who decided**, in a row's entry only, is an identity, its kind and its
  source;
- **`handed_out`** takes one of two fixed values, and
  **`created_at-not-readable`** is a stated absence: neither is derived from
  anything;
- a **position** is a sequence number in its segment (§4).

**None of them is a digest, so ADR 0034 §12's condition has nothing to fire
on here.** That is the property this rests on, and it is written as a
condition: **any digest in an entry reopens §12 for this ledger.** It would
reopen it for a digest of a run, of a suite, of a row or of a request. It
would also reopen it for a token, if the name table's design ever made
tokens derivable from their text. A count or a delta in an entry is not a
digest. It would raise a different question, what may be counted about a
data owner's removals, and that question is not this record's either.

### 6. The removal first, the entry after

**The removal is made, and then the entry is appended. Never the other way
round.** The two torn states are not equally bad:

- **Removed, and the entry not written:** a removal with no record. The ledger
  says less than happened, and none of what it says is false.
- **Entry written, and the removal not made:** the entry says *"this row was
  removed from this store"* and it was not. The ledger says more than
  happened, which is the failure ADR 0002 §2 calls worse than no flag.

**With the removal first, the only torn state possible is the first.** A crash
can leave the ledger short. It cannot leave it lying.

**The writer is the process that performs the removal, at the data owner's
side, and it is the ledger's only writer.** Written as the condition it rests
on: **the ledger needs no exclusion for as long as nothing else appends to its
path.** A second writer would need one. A lock file is not one, and ADR 0031
records why: a stale lock blocks everything behind it. This record provides no
exclusion, and it does not claim the condition is enforced.

### 7. Where "nobody can rewrite" comes from, and what the ledger says about it

**The property comes from the storage, not from a second holder.** Storage
that lets the writing process add and neither modify nor remove gives *nobody
can rewrite* without anyone else holding anything. **The data owner configures
that storage. digline does not.** Where the data owner configures nothing, the
process appends to an ordinary file, and the property is a promise rather than
a fact.

**So the ledger declares what it knows about its storage, instead of asserting
immutability**, and what it knows is what it was told:
- **It is a source, not a flag.** A `redacted` flag is verified by digline at
  construction (ADR 0002 §2). A claim about storage that came from
  configuration can be verified by nobody. So the ledger records **where its
  knowledge came from**, and does not state a property.
- **The default declaration is *"I was not told"*, not *"ordinary"*.**
  *Ordinary* would be a claim about the storage that the process has not
  verified. *I was not told* is exactly what it knows.

**How the process learns: from configuration, and only from configuration.
Decided here.** The data owner may declare, beside the path, that the storage
refuses modification and removal, and the period for which it holds what it
is given. The process records that it was **told** so, and by configuration.
**It does not probe.** The only probe that could tell append-only storage from
an ordinary file is an attempt to modify or remove an entry. That is the one
act the ledger exists to refuse, and on storage that allows it the probe would
damage the thing it tested. Nothing turns on the answer anyway, because the
process writes in either case.

**On ordinary storage the process writes, and declares. It does not refuse.**
A ledger on an ordinary disk does not prove immutability, but it proves
something: that the gesture was recorded, with its date and who decided it.
Altering it takes somebody reaching the disk with intent. **Append-only
storage is a strengthening that a data owner with tighter obligations
chooses. It is not a requirement.**

**The ledger is written in segments, and the declaration belongs to the
segment. Decided here.** A segment is one file, covering one calendar day of
removals in UTC. Its first line records what the process was told about the
storage **when the segment was opened**. The storage under a ledger can change
while the ledger lives: a data owner can move it to append-only storage, or
back. A declaration made once for the whole ledger would say nothing true
about entries written before the change. A declaration per entry would repeat
itself on every line. A segment is also the unit that storage holding objects
for a period can hold, and the unit §8 expires.

### 8. Retention: mandatory, configured by the data owner, and without a default

**The ledger's retention is configured by the data owner. The ledger expires.**
§1's *written only by appending* is immutability. It is not permanence: a
ledger can refuse rewriting and still have an end. The use (§1) has a window.
Its length depends on the data owner's obligations, which vary by sector and
jurisdiction. That is the same shape as the data's own retention: the data
owner sets it, and digline cannot read it. **So nothing about the ledger's
retention is decided by where it is placed.** Placing it in the register would
have decided it, and §3's third reason is that refusal.

**ADR 0002 §6's shape, taken. Decided here.** §6 says of the production store:
*"A production store without a declared deletion policy is not compliant and
digline must not allow creating one: the window is a mandatory constructor
parameter, not a setting with a generous default."* **The ledger takes the same
shape.** Its retention is **mandatory whenever a path is configured**, and a
path without a retention is refused at start. **There is no default.**
- **Why §6 applies here, when ADR 0034 §1 declined it for the reference.**
  §1's reason was that *"a reference that can expire is a reference that can
  vanish from under a gate."* Nothing gates on this ledger (§10), so that
  reason has no ground here.
- **Why it costs nothing.** A ledger exists only when the data owner
  configures its path (§9), and at that moment asking for the retention in the
  same place is one more line. A default would make *not chosen* the ordinary
  outcome, which is the gap §6 was written to close.
- **A default was considered and refused**, and §*Alternatives considered*
  says why: a number nobody can source is worse than no number, and this
  record found no source that fixes one. It does not claim that none exists.
  Nothing here is legal advice.

**What expires, and what happens to it. Decided here: whole segments are
dropped.** When a segment's last day is older than the retention, the segment
is removed as a whole. It is not rolled up into a count and it is not moved.
A count of removals per period would be a new derived record with a question
of its own (§5's last paragraph). A move would put the entries in a second
place with a retention of its own, and the question would start again there.

**The ledger says from when it holds anything. Decided here.** ADR 0021 §6's
rule already covers this: *absence is stated, never read as zero.* So:
- **The first segment written to a new path opens with the ledger's own
  start.** It records the moment the ledger began, and states that removals
  before it are not recorded here. A ledger configured late would otherwise
  look like the whole history.
- **Each expiry appends a line** to the current segment, saying that segments
  before a date have expired and when. A ledger that has expired entries says
  so rather than looking young.

**When the storage holds objects for a period of its own.** Storage that
refuses modification commonly does it by holding each object for a set
period, and refusing to remove it until that period ends. **Where the data
owner has configured such storage, the storage's period decides when a
segment can actually go**, and the ledger's configured retention cannot shorten
it. That is the same shape as git deciding retention by placement, one layer
down, and it is a **condition, not a caveat**. What the process does about it
is decided here: **if the data owner has declared a storage period and it
differs from the configured retention, the process says so at start, beside
§9's start notice**, naming both periods. It does not refuse, because
both periods are the data owner's.

**A token that has expired from the ledger is not reused, and no rule is
needed for it.** A token is not derived from anything, and minting a new one
never consults the ledger. Once an entry has expired, nothing at the data
owner's side records that its token existed, while the software house's git
still carries it in old projections. A resolver meeting it reads what it reads
for any token it cannot resolve. **This holds for as long as tokens are not
derived** (§5's condition), and it is the name table's design that keeps it
so.

### 9. No path configured: nothing is written, and it is said out loud

**With no path configured, the process does not write the ledger, and it says
so, at start and at every removal.** The other two options are refused, and
the reason is the same for both: **they lie.**
- **Writing beside the store** is §2's refused sibling directory. It would
  claim a ledger apart from the data while having none.
- **Refusing to remove** would mean not erasing, and not erasing is worse
  than an imperfect record of erasing.

**Empty is a state the data owner can see and repair. *Apart in name only* is
not.**

**Saying it out loud is part of the decision, not a courtesy.** A controller
who finds out afterwards that there was no ledger has already lost the proof,
and the point of the ledger is to have it at the moment it is needed. **The
notices never name what was removed**: no token and no `created_at`.
Otherwise the process's own log becomes a record of removals, beside the
store, under whatever backups the logs share, chosen by nobody. That is the
*apart in name only* ledger this section refuses, arriving through logging.

**Their words, decided here:**

    no deletion ledger is configured for this tenant: removals will be made and not recorded

at start, and

    removed, and not recorded: no deletion ledger is configured for this tenant

at each removal, printed where the removal is performed. **The second is an
ordinary line, not refusal-shaped.** The removal succeeded, and a refusal's
shape would say that it had not. The two reach different readers. The first
reaches whoever starts the process and can configure the path. The second
reaches whoever is removing, at the moment of the gesture.

**Nothing harder to ignore than the notice. Decided here.** A confirmation,
or a flag the operator must pass, is the next thing somebody will propose. It
is refused for two reasons. A gesture repeated at every removal is learned
and passed without reading. And a flag moves the decision to whoever writes
the script that passes it, away from the person the second notice reaches.
The start notice repeats at every start, for as long as the path stays
unconfigured.

### 10. Off every read path, and nothing reads it to decide anything

**The ledger is not consulted by any reader in digline.** It is not read to
resolve a token. It answers no reader's question about a run. No exit code,
refusal or promotion condition depends on it. **It is a record somebody goes
to, deliberately, to answer *did this removal happen*. It is never a marker a
reader meets while doing something else.** That distinction is what ADR 0034
§14 is about: §14 requires a removed run to be absent from every reader **of
the store**, not that no artifact anywhere may name what went.

**This holds only for as long as nothing in digline reads it, and one repair
would break it.** After a removal, two messages are wrong:
- `latest` says *"… so there is no latest one. Run it first."*
  (`host/resolve.py`), and re-running restores nothing;
- `view`'s runs page says *"No run has been recorded yet."*
  (`report/text.py`, key `view.no_runs`), when a run was recorded and then
  removed.

**Repairing either by reading the ledger, and saying *removed*, puts the ledger
on the read path.** It would become the marker a reader meets, and the
distinction above collapses. **Whatever repair those messages get must not
consult the ledger.** Which repair they get is not decided here.

**The ledger does not reach the software house.** Nothing that serves the
software house's reads returns it, and nothing the software house sends can
set its path (§2). It is the controller's record, kept towards an authority.
That is exactly why it has no business crossing.

### 11. What the ledger concentrates, and does not remove

**A ledger of removals is, beside a restored backup, a list of the people who
asked to be erased.** This section says so in its own place, because it is the
cost the design carries rather than a risk it removes.

**The ledger does not create the risk. It concentrates it.** Without a ledger,
whoever restores a backup of the name table has everything anyway. The table
comes back whole, removed rows included, and ADR 0034 §6 already says *"a
restored backup re-identifies every orphaned token in every committed file."*
The ledger adds no data. **What it adds is an index**: these are the rows, and
these are the runs, whose removal somebody asked for. Those are the people with
the strongest claim not to be re-identified.

**And the index comes grouped by person, at no cost.** A row's entry carries
when and who decided (§4). A removal is one person naming what goes, at one
sitting. So the entries that share a decider and a time band are the rows of
one request, which means one subject's rows grouped together. **This holds for
the entries of rows:** a run's entry carries no decider (§4), so runs are not
grouped by it. **Refusing the request's identifier stops the ledger from naming
the subject. It does not stop it from grouping the subject's rows**, and the
grouping needs no field of its own: it falls out of two fields this record
requires.

**What this record does about it: the ledger sits apart** (§2). It is outside
the store's backup regime, at a path with a regime of its own. The
concentrate is worth the proof it buys, but not beside the data. The use is
rare, deliberate and aimed at an authority, and it has no need to sit where the
data is restored.

**What that does not do, stated plainly: it reduces the concentrate. It does
not remove it.** A ledger anywhere is still a grouped list of who asked to be
erased. **Somebody who holds both the ledger and a restored backup has what
this section describes.** Sitting apart makes the two harder to hold together.
It does not make it impossible. And a ledger whose retention outlives the
table's backups points into nothing, while one that does not points into
them. The backups' retention is the data owner's, and digline cannot read it.

## Consequences

- **A removal can be shown.** An end company that removed a row or a run can
  show an authority when, by whom, and in what words, without showing what was
  removed.
- **A new artifact outside `.digline/<tenant>/`**, the first one. It is an
  exception to fixed decision 2's sentence, made at acceptance, with the
  decision's reason kept whole (§2).
- **Two configuration keys that exist together or not at all**: the path and
  the retention. Two notices whose words are fixed (§9). One refusal: a shared
  path (§2).
- **A weaker name for a removed run**, taken against a measured leak (§5). A
  reader matching a key to the ledger gets a count, not an assumption.
- **A permanent condition on digline's readers:** none of them may read the
  ledger (§10), and the obvious repair of two wrong messages is the one that
  is forbidden.
- **A concentrate that is reduced and not removed** (§11). It is the cost of
  having a record at all, and it is stated rather than hidden.
- **ADR 0021 §6's journal premise is false for deletions**, and its correction
  is owed to ADR 0021 (*Names*).

## Alternatives considered

- **A tombstone in the run store.** Refused by ADR 0034 §14: a marker every
  reader of the store would meet, and an erasure left incomplete.
- **A committed file at the data owner's side.** Refused because it puts git
  where ADR 0034 §3's division holds only while there is none.
- **The register.** Refused, for the four reasons in §3.
- **The name table itself.** Refused: the table is rewritable row by row, and
  the ledger is append-only. They have opposite properties, and the table is
  the very data whose removal the ledger records.
- **A sixth item inside the store.** Refused by §11: inside the store, the
  ledger shares the store's backups.
- **A sibling directory under `.digline/`, or a service digline calls.**
  Refused in §2.
- **The full run key in an entry.** Refused on a measurement (§5).
- **A default retention.** A figure of three years was considered: shorter
  than ordinary limitation periods, longer than the practical window of a
  complaint, and derived from neither. **It was refused in favour of ADR 0002
  §6's shape** (§8). A default no source fixes is still a number the product
  chose for the data owner, and §6 exists because a convenient default is how
  a policy nobody chose becomes the policy. The three statements that placed
  the figure are not sourced in this record, and none of them is needed once
  there is no default.
- **Probing the storage.** Refused in §7: the only probe that could tell the
  storages apart is the act the ledger refuses.
- **Refusing to write on ordinary storage, or refusing to remove when no path
  is configured.** Refused in §7 and §9: each makes not erasing the price of an
  imperfect record.
- **One declaration for the whole ledger, or one per entry.** Refused in §7 for
  one per segment.
- **Rolling expired entries up into a count, or moving them.** Refused in §8.
- **One path for several tenants.** Refused in §2 by fixed decision 8.
- **A confirmation or a flag when no path is configured.** Refused in §9.

## Not decided here

- **The procedure that decides a removal**: who may perform one, how a person
  is recognised in the rows, and what happens to cases whose shared label is
  removed. This record keeps the record of a removal. It does not design the
  act.
- **Whether a record of the gesture is what a controller owes.** That is
  counsel's question. This record's position is that it records the gesture
  honestly and claims nothing more (§4).
- **The name table's own amendment to fixed decision 2**, which is an addition
  to its list (§2).
- **ADR 0021 §6's correction** (*Names*), including whether it reopens the
  expired-journal case.
- **The repair of `latest`'s and `view`'s messages after a removal**, beyond
  the one repair §10 forbids.
- **Who may read the ledger at the data owner's side, and how it is handed to
  an authority.** Access is the operator's, as fixed decision 8 says of every
  perimeter, and the handing over is not digline's act.

## What this record does not claim

- **That a removal is an erasure.** ADR 0034 §14, and §4's wording.
- **That the ledger cannot be rewritten.** It cannot be, where the data owner's
  storage refuses it. Where it does not, the ledger says it was not told (§7).
- **That the ledger is safe.** §11: it reduces a concentrate and does not
  remove it.
- **That `config_hash` is safe elsewhere.** §5 measures it for a place its
  inputs do not reach. ADR 0034 §12's answer for the committed reference, where
  its inputs sit beside it, is untouched.
- **That an unknown template protects a `config_hash`.** Unmeasured (§5).
- **That `created_at` is unique.** §4 says what the ledger does because it is
  not.
- **That it is lawful, or sufficient.** Nothing here is legal advice.
