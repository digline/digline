# ADR 0048 — The versions a suite holds, and the one in force

- Status: proposed 2026-10-10 — the text first, checkpointed before any code,
  the way [ADR 0035](0035-the-record-of-a-deletion.md) was. Nothing in it is
  implemented. **What §1 states was settled before it was written**, in
  discussion: the pointer, and the form of a version, a string compared for
  equality with no order. It is recorded here as settled. **§2 to §6 are
  decisions this record takes itself**, marked *decided here* where they are
  made, so that acceptance can rule on them one by one. **The rulings are not
  transcribed verbatim in *Context*, as [ADR
  0046](0046-a-widening-is-a-declared-class.md) and [ADR
  0047](0047-what-a-case-in-clear-contains.md) transcribe theirs.** That is not
  a choice of style. A public record cites only public records, and the
  rulings behind this one quote records that are not public. Transcribed, they
  would carry those citations into this text. So this record states their
  content in its own words, and it is the register of what it states
- Shipped: unreleased
- Date: 2026-10-10
- Opens: **nothing on landing.** No `SCHEMA_VERSION`, no `OUTPUT_VERSION`, no
  `REGISTER_VERSION`, no `JOURNAL_VERSION`, no migration. A run does not record
  a version (*Not decided here*), so no document digline writes today changes.
  The documents of §6 are a new format, born at implementation, not here
- Requires, at implementation: **a new entry in the tenant's layout**, per
  suite, holding the versions and the pointer, behind the `ResultStore`
  protocol (§6). **The sentence at
  `src/digline/store/file_store.py:134-135` extended**, or it becomes false:
  *"Nothing digline writes can land here, because every other path in the
  layout goes through `baselines/`, `runs/` or `register/`."* **A listing that
  loads no suite** (§6)
- Assumes: [ADR 0002](0002-three-worlds-and-where-the-data-lives.md) §1 (the
  tenant is the perimeter) and §8 (a baseline is an approved reference, and
  promotion is the gesture that makes one); [ADR
  0034](0034-the-store-outside-and-the-reference-that-names-nothing.md) §1 (the
  store lives in the end company's perimeter) and §3 (no git at the data
  owner's side); [ADR 0036](0036-the-name-table-and-the-process-that-owns-it.md)
  §1 and §6 (one table per (tenant, suite), held by the process that owns it)
  and §2 (an entry added to fixed decision 2's list);
  [ADR 0037](0037-the-review-interface-and-the-election-recorded-where-the-text-is-not.md)
  *Not decided here* (accepted with *"who may make"* a world-2 promotion left
  open, after [ADR 0033](0033-the-server-that-promotes-for-one-browser.md) §6)
- Amends, **at acceptance**: `CLAUDE.md`'s fixed **decision 2**, by an
  **addition to the list** of what `.digline/<tenant>/` holds, in the shape of
  *"Added to the list 2026-09-29 (ADR 0036 §2)"*: the held versions and the
  pointer, per suite, behind the `ResultStore` protocol (§6). **It is an
  addition and not an exception.** ADR
  0035's *"Excepted"* is the shape of what sits outside the layout, and these
  sit inside it. The decision's reason stays whole: nothing in a home
  directory, no global state, everything addressed by the tenant
- Names, and does not amend: the `OLDER SUITE` marker's text, in
  `docs/view.md:46` and under `view.chip.older_config`, which §2 reads and
  does not change; and the layout in `src/digline/store/file_store.py:1-8`,
  which lists a file no code reads and leaves out two directories (#514). §6
  adds to that layout; it does not repair the docstring
- Touches, in `CLAUDE.md`'s *fixed* section: **decision 2** gets an addition
  to its list (*Amends*). **Decision 8** is upheld: one pointer per (tenant,
  suite), inside the tenant's directory (§3, §6). **Decision 9** is read and
  not edited. This record decides where the versions and the pointer sit and
  what form they take, not what crosses a boundary, and §1 keeps the pointer
  out of the sentence decision 9 corrected on 2026-10-02 by giving it no digest
- Number: 0048. Swept on 2026-10-10, before a line was written, across
  `origin/main` (`3cc30b8`), every local and remote branch and tag, the
  `docs/adr/` of every sibling worktree (none has one), the stash (empty), the
  open pull requests (none), the site repository's refs at `06c63e6`, and the
  working notes that claim a number before a record exists (none claims 0048).
  The highest number taken anywhere is 0047

## Context

**Today a suite has one state.** A tenant's suite has one set of rules, which
`config_hash` names, and one baseline, the reference its runs are compared
against: one file per (tenant, suite), `<tenant>/baselines/<suite>.json`
(`baseline_path`, `src/digline/store/file_store.py:429-430` at `3cc30b8`).
Neither `Suite` nor `Run` carries a version of the suite. What runs is the
suite as it was loaded, and what a run is measured against is the reference
taken under the rules in force.

**So preparing a change means changing what is compared against.** A change
to the rules is made by changing the suite. Once it is changed, the suite that
runs is the new one, and the old baseline no longer describes the rules in
force: it *"has to be re-taken"* (`docs/guide.md:343-345`), and a run made
under the old rules cannot be promoted, because *"promoting it would record
scores obtained under a configuration other than the one in force"*
(`docs/guide.md:1006`, a `ConfigMismatchError`). There is no second
state in which a change can be tried, run and read while the rules in force
keep being the ones that run. Trying a change and putting it in force are the
same act.

**Where the store lives with the end company, that act is not the software
house's to make in passing.** [ADR
0034](0034-the-store-outside-and-the-reference-that-names-nothing.md) §1 puts
the store inside the end company's perimeter. A candidate set of rules that
can be tried only by putting it in force is tried on what the end company
relies on.

**This record separates the two acts.** A suite's store holds more than one
version of the suite, and one of them is marked in force. It decides what that
mark is, what moving it does to the baseline, and where the versions and the
mark sit in the layout. It does not decide how a version arrives, how one
leaves, who may move the mark, or what reads it (*Not decided here*).

**No public text speaks of the in-force pointer or of the held versions.**
`docs/` at `3cc30b8` was searched with line breaks folded, for *pointer*,
*in-force*, *in force*, *held version*, *declared version*, *suite's version*
and *version of a/the suite*. The hits on *pointer* are a model alias (ADR
0016, `docs/api.md`) and cross-references between records. The hits on *in
force* are about the configuration, the baseline or a record being in force,
never about a version. The one hit on *version of the suite* means something
else, and §2 is about it. **So this record is the place where the pointer and
the held versions are written**, and what it states about them is stated here
and not elsewhere.

**One measurement bears on where the versions sit.** Two suites whose
application modules share a name, loaded in one process, both call the first
one's application, silently and with exit 0 (#513, measured at `3cc30b8`).
Two versions of one suite are exactly that case. §6 is shaped by it.

## Decision

### 1. The pointer

> **A suite's store holds every version of the suite it has received, and one
> of them is marked in force. Receiving a version adds it; it does not replace
> the one there. What moves the mark is a promotion.**

**A version** is the suite as one string declared by the suite identifies it.
Two versions are the same version when the two strings are equal. No order
between them is assumed: no version is *newer* or *lower* than another, and a
promotion may mark any version held. This record uses the string only as an
identity. Where it sits on `Suite`, and when it is required, are not decided
here.

**The pointer** is the mark: it **declares** which held version is the one in
force. That declaration is all it is. What consumes it, who reads the pointer
and what being in force causes, is not decided here.

**The pointer names a version and carries no digest.** Fixed decision 9, in
the sentence corrected on 2026-10-02, holds its ruling on digests *"only while
no document that carries a digest can reach a place the suite does not"*, and
lists the documents that do. A pointer that named the in-force version's
`config_hash`, or any other digest, would join that list. This record does not
put it there: the pointer names a version by its declared string, and nothing
else.

**What holding more than one version is for:** a version that is held and not
in force can be tried without changing the one in force. That is the purpose
of holding it, not a capability that exists. Nothing at `3cc30b8` runs a
version or reads a pointer.

**Moving the pointer is a promotion**, as making a run the baseline is (ADR
0002 §8): a gesture that changes what counts as the reference, made by a
person. This record fixes the **kind** of the gesture. Who may make it, and
what conditions it checks, are not decided here.

### 2. Two meanings of "version", kept apart

> **This record keeps two notions apart, and gives each its own words.**

**Decided here.** **The collision already exists in public text.**
`docs/view.md:46` marks a run `OLDER SUITE`, *"produced under an earlier
version of the suite"*, and `docs/guide.md:1010` says the same run is
*"marked `OLDER SUITE`"*. The chip's key is `view.chip.older_config`
(`src/digline/report/text.py:671`, `:1844`), and the key says what the marker
means: a run whose `config_hash` is not the one in force. There, *version of
the suite* means **a set of rules**.

**Under §1 the two part.** A version with the same rules as the one in force
is a different version and not an older suite: `config_hash` does not move
when only the declared string changes. And a change of rules is an older suite
even inside one declared version.

**The words, from here on:**
- **a version**, **a held version**, **the version in force**: §1's notion,
  identified by the declared string;
- **the rules**, **the configuration in force**, **an older suite**: what
  `config_hash` names, as the `OLDER SUITE` marker already uses it.

This record never writes *version* for a set of rules, and never writes
*older suite* for a version. The marker's text is not changed here. A reader
meeting *"an earlier version of the suite"* in `docs/view.md` meets the second
notion, and the difference is this section's to state.

### 3. Per suite. Derived, not chosen

> **There is one pointer per (tenant, suite).**

**Decided here, and derived rather than chosen.** It follows from what exists.
A version is something a suite declares (§1). Everything digline writes is
keyed by (tenant, suite): the baseline, the register, the runs and the journal
under them (`src/digline/store/file_store.py:1-8`, `:429-430` at `3cc30b8`),
and every method of the store's protocol takes a tenant and a suite, or a
`RunRef` that carries both. So is the name table, which digline does not
write: *"One table per (tenant, suite)"* ([ADR
0036](0036-the-name-table-and-the-process-that-owns-it.md) §1).

**A pointer per tenant would point at an object nothing defines**: a set of
versions of more than one suite. It is not an alternative weighed and
declined. There is nothing for it to name.

### 4. In the store, moved by a promotion, with the process running

> **The pointer is state of the store, not configuration. Moving it is a
> write to the store, and needs no restart.**

**Decided here.** **The precedent is the baseline.** A promotion writes the
baseline into the store, and nothing restarts (`promote_baseline`,
`src/digline/store/file_store.py:641-682` at `3cc30b8`). §1 makes moving the
pointer a promotion, so it has the baseline's place: the store.

**Moving it changes nothing a process is keyed by.** The process that owns
the name tables *"holds one table per (tenant, suite)"* (ADR 0036 §6). Moving
the pointer changes neither the tenant nor the suite. Whether two versions of
one suite share that suite's table is not decided here.

**This holds under a condition, and the condition is part of the decision.**
It holds **as long as the process that serves the pointer loads no suite.**
Serving a pointer reads which version is declared in force; it does not run
one, and the loading measured in #513 is not reached. **If running a suite is
built into the same process that serves the pointer, this section is to be
read again**: a pointer moved with that process running would then load a
second version into a process that already loaded the first, which is #513's
case. The constraint #513 imposes, a process per version or a loader that
isolates one, belongs to whatever loads versions. Which of the two is not
decided here.

### 5. One gesture: moving the pointer does not touch the baseline

> **Moving the pointer and promoting a run are two gestures, and neither
> makes the other. Moving the pointer leaves the baseline as it is.**

**Decided here.** **The rules a run is checked against stay what they are
today.** `expected_config_hash` is computed from what the suite was loaded as
(`src/digline/host/promotion.py:1-15` at `3cc30b8`: *"the public route is
`promote`, which takes what the suite was loaded as and computes the hash
itself"*). Nothing in this record moves it.

**The other way is refused, and on its own account.** Taking the expected
configuration from the version in force would refuse every run made under a
held version whose rules differ. Its baseline could then be taken only after
the pointer moved, and the version would come into force **with no reference
taken under its rules.** Holding more than one version exists to prepare one,
and that way prevents preparing.

**A second ground, from §2.** `config_hash` does not move when only the
declared string changes, so it cannot tell two versions with the same rules
apart. A tie from the baseline to a version could not be read from it.

**Where a version also changes the rules, the rule that exists applies.** The
baseline is re-taken under the new rules: a run, then a promotion
(`docs/guide.md:343-345`). That is not new with this record.

### 6. Inside `.digline/<tenant>/`, per suite, listable without loading

> **The held versions and the pointer sit inside `.digline/<tenant>/`, per
> suite, the pointer beside the versions. They are versioned documents, one of
> them marked as the reference, and never a copy that is overwritten.**

**Decided here.** **Inside the layout, under the tenant.** The versions are the
tenant's suite and nothing else's (fixed decision 8), and the layout is where
a tenant's state lives (fixed decision 2). They are a new entry in that
layout, beside `baselines/`, `register/`, `runs/` and the name table's
reserved name. The entry's name is the implementation's.

**Behind the `ResultStore` protocol.** What this record decides goes through
the protocol. Listing the versions and the pointer is a read of the store, and
moving the pointer is a promotion, and promotion is already a member of the
protocol (`promote_baseline`, `src/digline/store/protocol.py:612` at
`3cc30b8`). No process outside digline owns these things. The name table is
the opposite case: its writers run in a process that is not digline's, and
[ADR 0036](0036-the-name-table-and-the-process-that-owns-it.md) §2 keeps it out
of the protocol for that reason (*"The table is not a capability of the
store"*). **How a version arrives is not decided here.** It belongs to another
gesture, outside this record, and this record does not say through what that
gesture writes.

**Why this could not be left open.** Fixed decision 2 puts the layout behind
the protocol: *"Behind the `ResultStore` protocol, file-based implementation by
default."* An entry that said nothing would sit behind it by that sentence, so
leaving the question open would have answered it without saying so. ADR 0036's
line in fixed decision 2 exists because the name table is a declared exception
to it; these entries are not one.

**Versioned documents, never an overwritten copy, because an overwritten copy
keeps no history.** The baseline is a copy: a promotion overwrites one file per
(tenant, suite), and its history is whatever the repository keeps. Where the
store lives with the end company there is no git ([ADR
0034](0034-the-store-outside-and-the-reference-that-names-nothing.md) §3), so a
copy kept the baseline's way would keep the version in force and lose every
version tried and not chosen. So what carries over from the baseline is the
**shape**, documents with one marked as the reference, and not the
**mechanism**, which overwrites.

**Listable without loading.** Which versions are held, and which one is
declared in force, can be known without reading the content of a suite and
without loading one. Loading a suite executes it, and two versions of one
suite loaded in one process do not stay apart (#513). Listing is reading the
layout.

**Committed or ignored is a question only in the developer's repository.**
Where the store lives with the end company there is no git, and the
distinction means nothing there. Which of the two the entry is, in a
developer's repository, is the implementation's.

## Consequences

- **Trying a change and putting it in force become two acts**, once the
  versions are built. Until then nothing changes: no document digline writes
  today is touched (*Opens*).
- **Fixed decision 2's list gains an entry, at acceptance**, inside the
  layout, with the decision's reason kept whole (*Amends*).
- **The layout gains an entry, and one sentence in the store must follow it.**
  `src/digline/store/file_store.py:134-135` says every path digline writes goes
  through `baselines/`, `runs/` or `register/`; the implementation extends it.
  The docstring's own defect is #514's, apart from this record.
- **Two words for two notions** (§2). Text written after this record uses
  *version* for the declared string and *older suite* for a change of rules,
  and never the one for the other.
- **One baseline per (tenant, suite) remains.** With more than one version
  held, promoting a run made under a version not in force overwrites the
  reference of the version that is. This is not a defect while one version is
  held, which is every case today; it is the first question of a later reading
  (*Not decided here*).
- **A standing condition on whoever builds a process that serves the pointer**
  (§4): if that process also runs suites, §4 is read again before the pointer
  moves in it.
- **The pointer stays out of fixed decision 9's list of documents that carry a
  digest** (§1). A later change that adds a digest to it reopens decision 9,
  and is not a detail of implementation.

## Alternatives considered

- **Two slots, one in force and one on trial.** Refused. A second slot needs
  rules for what happens when a third version arrives and for what promoting
  out of it leaves behind; a pointer needs one rule, which version it names.
  And a trial slot overwritten by the next trial loses every version tried and
  not chosen (§6).
- **The pointer in configuration.** Refused (§4). Moving the pointer is a
  promotion, and a promotion writes to the store and restarts nothing.
- **`expected_config_hash` taken from the version in force.** Refused (§5): it
  prevents preparing a version, which is what holding one is for.
- **The baseline's mechanism for the versions**: one file, overwritten, with
  its history kept by git. Refused (§6). At the data owner's side there is no
  git, and the overwrite is what loses the history holding versions exists to
  keep.

A pointer per tenant is not among them. §3 says why: there is nothing for it
to name.

## Not decided here

- **What consumes the pointer's declaration**: who reads the pointer, and what
  being in force causes. This record says which version is declared in force
  and nothing about what follows from it (§1).
- **Whether a version's declared string is a *name*** in the sense of fixed
  decision 9's line of 2026-10-01 (ADR 0038): a served projection carries
  *"digline's own vocabulary, never a name"*. Whoever serves the pointer meets
  this question first.
- **Who may move the pointer, and what conditions that promotion checks.** Left
  open on [ADR
  0037](0037-the-review-interface-and-the-election-recorded-where-the-text-is-not.md)'s
  precedent, accepted with *"where a world-2 promotion is reviewed, and who may
  make one"* open, after ADR 0033 §6.
- **Whether what a review of a promotion must guarantee binds the pointer as it
  binds a baseline.** No public text states those guarantees. ADR 0033 §6 names
  two neighbours of them as questions. The question comes back when they have
  a public form, and the nearest place for one is whatever answers ADR 0033
  §6.
- **Whether the baseline becomes per (tenant, suite, version).** Today there
  is one per (tenant, suite), and with more than one version held a promotion
  under a version not in force overwrites the in-force version's reference
  (*Consequences*). It is the first thing a later reading has to answer.
- **What a run records about the version it was made under.** It travels with
  the first code that runs under a version, and it is a schema bump. With it
  goes the tie between a baseline and a version, which today has nothing to
  name (§5).
- **A process per version, or a loader that isolates one** (#513). The choice
  belongs to whatever loads versions, under §4's condition.
- **Whether two versions of one suite share a name table.** The table is per
  (tenant, suite), and no text says.
- **How a version arrives, whether one can be removed, and whether one can be
  held and never promoted, and for how long.** None of them is needed to say
  what the pointer is and where it sits. One crossing is named so it is not
  found late: removing a version is in neither of [ADR
  0035](0035-the-record-of-a-deletion.md)'s two ledgers, and if a held version
  carries the end company's cases, an erasure must reach it. *[reasoning, not
  verified]*

## What this record does not claim

- **That a version, a pointer, receiving a version, running one, or a
  promotion that moves a pointer exists.** None does, at `3cc30b8`.
- **That anything reads the pointer or acts on it** (§1).
- **That #513 is fixed**, or that a listing protects a process that loads
  versions. A listing loads nothing; a process that loads is #513's case.
- **That moving the pointer is safe in a process that runs suites.** §4 holds
  under its condition only.
- **That the `OLDER SUITE` marker is wrong.** It is right for the notion it
  names (§2).
- **Anything about what crosses a boundary.** The declared string's status
  under fixed decision 9 is open (*Not decided here*).

## Test plan

**Nothing at merge.** This record carries no code, and what it governs does
not exist (*What this record does not claim*), so there is nothing a test
could exercise.

**Owed with the code, and written with it.** Each test must also fail against
the code without the rule it tests, or it proves nothing.

1. **Listing without loading (§6):** a layout whose held versions each hold a
   suite file that raises when imported. Listing the versions and the pointer
   succeeds. Control: a listing that loads a suite fails it.
2. **Receiving adds, and does not replace (§1):** after a second version is
   received, the first is still held and the pointer has not moved.
3. **Moving the pointer leaves the baseline as it was (§5):** the baseline
   file is byte-identical before and after. Control: a move that rewrites the
   baseline fails it.
4. **The pointer carries no digest (§1):** every field of the pointer checked
   against §1. Control: a pointer that carries a `config_hash` fails it.
5. **The pointer is per (tenant, suite) (§3):** moving one suite's pointer
   leaves another suite's, and another tenant's, as they were.
6. **The layout's sentence holds (§6):** nothing digline writes lands under the
   name table's reserved name once the new entry exists, and the new entry's
   name does not collide with it.
