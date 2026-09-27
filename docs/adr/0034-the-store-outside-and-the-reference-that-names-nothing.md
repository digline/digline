# ADR 0034 — The store outside the repository, and the reference that names nothing

- Status: accepted — the text first, checkpointed before any code, the way
  [ADR 0021](0021-the-register.md) and [ADR 0023](0023-capture.md) were; nothing
  in it is implemented. Landed on `main` as proposed on 2026-09-27 and accepted
  the same day. **It said acceptance waited on two answers. One is answered and
  the other is sidestepped, and the two are not the same act.**
  **Answered — who the digests protect against: nobody in particular** (§12).
  The committed file and the suite live in one repository, so whoever obtains
  one obtains the other, and a digest of text they already hold gives them
  nothing. `assertion_id` and `config_hash` stay as they are.
  **Sidestepped, not answered — counsel's question** (§6): whether a record of
  structural identifiers and no text, left in a repository's history, is still
  personal data once the mapping that resolves it is destroyed. It is still
  counsel's and still open. This record is accepted on the branch where
  destroying the mapping is enough, **and that is a premise, not a finding.**
  **What reopens acceptance:** counsel answering the other way. §2's committed
  shape then falls, the design becomes compare-at-the-owner (§*Alternatives
  considered*), and this record is proposed again. Nothing is committed until
  the projection is built, so the first committed file is where a wrong premise
  stops being cheap: a projection already in history stays there. **What
  reopens §12:** a committed file reaching a place the suite does not — a fork,
  a backup, a handover — because that removes the reason, and the ruling goes
  with it. **Its amendments are made in the same change as this acceptance**,
  as *Amends* said they would be: ADR 0002 §6 and its *Consequences*, ADR 0005
  §9, and `CLAUDE.md`'s decisions 2 and 9
- Shipped: unreleased
- Date: 2026-09-27
- Opens: **nothing on landing.** No `SCHEMA_VERSION`, no `OUTPUT_VERSION`, no
  `REGISTER_VERSION`, no `JOURNAL_VERSION`, no migration — nothing is
  implemented. At implementation §8 is a field in the run document and
  therefore a schema bump with the whole ritual
  [ADR 0014](0014-what-may-ride-a-schema-bump.md) §1 asks for. *Requires*
  prices that here rather than leaving it to be discovered by whoever builds it
- Requires: **a schema bump** (§8's regime field, with its migration, its
  `RELEASED` row, the committed baselines and the example caps that move with
  it); **a reading change**, which is the expensive kind — the body of the
  report loses four header rows, three columns of the check table, both columns
  of the suspended table, the whole artifacts section and `view`'s column
  headers, and there is **no machinery for it**: `_row` has no branch where
  `case_id` and `assertion` are anything but printed, and there is no
  `names_available` beside `reasons_available`; **a new artifact** at the data
  owner's side, with its own retention and its own place in the layout (§6);
  **a new writer** (§3), and **a sixth method** on `ResultStore` (§14); **a
  refusal** that is classified in `host.REFUSALS`, or `tests/test_refusals.py`
  will not see it. **Deliberately not read off ADR 0023's *Requires* line**,
  which prices that record's own work in world 1 and is not transferable here
- Assumes: [ADR 0002](0002-three-worlds-and-where-the-data-lives.md) §1 (the
  tenant is the perimeter), §2 (the payload stays where it is born, the verdict
  travels, and the flag is verified rather than believed), §4 (`Comparison`
  inherits the payload of its inputs, and nobody writes a transport for one),
  §5 (the `case_id` has to cross, so it cannot be payload, and the bridge's id
  has no entry point), §6 (a store outside the repository, inside the end
  company's perimeter, with mandatory retention), §8 (promotion's conditions,
  collected because they are one rule) and §9 (git is read before importing
  ours); [ADR 0003](0003-artifacts-travel-only-when-the-suite-says-so.md) §3
  (artifacts are outside `config_hash`), §4 (a digest is a verifier over a
  guessable space, and a digest that travelled would defeat the withholding it
  travelled beside) and §5 (a redacted run reports `unknown` and stays honest
  about it); [ADR 0005](0005-the-configuration-of-the-system-under-test.md) §2
  (the perimeter rule, by type), §3 (recorded beside the hash and never inside
  it) and §9 (what the provider said answered);
  [ADR 0007](0007-the-declarative-suite-format.md) §4 (cases are a file
  reference, always), §5 (the target has two forms) and §7 (a data suite cannot
  widen a boundary); [ADR 0010](0010-per-group-aggregates.md) §1 (`group` is
  descriptive and does not reach a run file), §3 (the expanded name is the
  identity and it is a public string) and §4 (neither the flag nor the group
  enters the identity); [ADR 0011](0011-the-mcp-server.md) §6 (one rendering of
  the truth, two front ends) and §7 (nothing imports `cli/`);
  [ADR 0014](0014-what-may-ride-a-schema-bump.md) §1 (the passenger rule) and
  §3 (`promoted_at` is the caller's, and the store reads no clock);
  [ADR 0015](0015-the-recorded-output-and-the-declared-re-judge.md) §4 (a
  recorded response never travels and no `Disclosure` releases it) and §5
  (promotion strips them, removed rather than withheld);
  [ADR 0021](0021-the-register.md) §3 (the entry is counts and keys, by type),
  §6 (a committed file's retention is git) and §7 (naming inside the
  perimeter); [ADR 0027](0027-the-run-reconciles.md) §3 (a reference nobody can
  say that of is no reference) and §6 (an aggregate finds its verdict by
  identity); [ADR 0028](0028-the-rules-that-moved.md) §6 (a gate that appeared
  over a group); [ADR 0029](0029-the-artifact-that-must-not-drift.md) §3 and
  its exit 2, which is not a regression;
  [ADR 0031](0031-the-reference-promote-replaces.md) §1 (the key is derived,
  `key_of` lives in the core) and §2 (where the key is carried);
  [ADR 0033](0033-the-server-that-promotes-for-one-browser.md) §6 (world 2
  stays out, and what it needs first)
- Amends, **at acceptance and not on landing** — made on 2026-09-27, in the
  change that accepted this record:
  [ADR 0002](0002-three-worlds-and-where-the-data-lives.md) §6 — its carve-out
  widens from *the production stream* to *offline runs against the end
  company's own cases*, which is §1 below and the whole of what fixed decision
  2 has to give; and ADR 0002 §8, in its *Consequences* only — a reference may
  be a projection of one, with every condition unchanged (§2).
  [ADR 0005](0005-the-configuration-of-the-system-under-test.md) §9 — **owed as
  a consequence of §4's enumeration, not as its prerequisite**: once an
  unclassified field is refused, `resolved_model`, `fingerprint` and every
  reported value either classify or do not cross, and §9's rule that they are
  recorded beside the hash needs one sentence about what happens to them at
  this boundary (§7, route 6)
- Names, and does not amend — each is owed to the record that carries it, and
  §*Not decided here* says why none of them belongs in this one: **ADR 0010
  §1**'s broken premise (the rule §5 implements lands before this record's
  first committed file, in its own amendment, for the reason in §5); **ADR 0027
  §6**'s tolerance of a differently-named score (§7, route 4); **ADR 0014
  §3**'s refusal of a promotion history (§3, and it belongs to the record that
  decides identity); **ADR 0002 §1**'s *"enforced by the filesystem"*, which is
  true of addressing and false of access (§13); **ADR 0022 §6**'s list of
  harmless `config_hash` inputs, one entry of which is no longer harmless
  (§12); **ADR 0023**'s own header, rewritten at *its* acceptance and not here
- Closes: [ADR 0033](0033-the-server-that-promotes-for-one-browser.md) §6's
  third bullet — *"A store outside the repository reaches fixed decision 2,
  which puts everything in `.digline/<tenant>/` inside the user's repository.
  That needs its own ADR first."* **This is that record.** That bullet predates
  the reading in §1 below, which finds the move is a widening of ADR 0002 §6's
  carve-out rather than a second home for the data, and the two halves of this
  record's title are one decision: where the store lives is *why* the reference
  can name nothing
- Turns into surface, at implementation and not on landing: a projection in
  `digline.core`, beside `redact`; a writer in `digline.host`; a sixth method
  on `ResultStore`; a second artifact under `.digline/<tenant>/` that is never
  committed (§6); one field in the run document (§8); one refusal in
  `host.REFUSALS`; and the two places that read a committed file with no names
  in it — `digline compare`'s terminal lines and the `--json` and MCP forms of
  the same facts (§15)
- Touches, in `CLAUDE.md`'s *fixed* section: **decision 2** is widened by §1
  and keeps its stated reason whole — no database in the home directory, no
  global state, everything still addressed by the same key; **decision 8** is
  upheld and §13 says which half of it this record may lean on and which it may
  not; **decision 9** is narrowed, and §8 is the declaration of that narrowing
  rather than a silent exception to it; **decision 5** is untouched, and §*Not
  decided here* says that nothing in this record configures a network call;
  **decision 3** is reaffirmed by §16, which refuses a check that cannot fire
- Number: 0034. Swept on 2026-09-27 across `origin/main`, every remote ref,
  every local branch and all six sibling worktrees, and the working notes that
  claim a number before a record exists; 0033 was the highest claimed

## Context

**The situation, and it is not hypothetical.** A software house builds an LLM
application for an end company. The repository is the software house's; the
application runs in the end company's infrastructure. In development the cases
are synthetic and live in the repository, which is world 1 and works today.
With real cases the material is the end company's, and it may not leave: not
into the software house's repository, and not into its history.

**Nothing in the product refuses this shape.** What it lacks is a place to put
the cases and a reference the software house can hold. World 2 — *"maintains N
customers, must see the signal **without holding the production data** of any
of them"* — is already in `CLAUDE.md` and already in ADR 0002. This record is
where the second half of that sentence becomes a mechanism.

**And the market context, because it decides whether this is worth building
rather than how.** No evaluation platform audited for this project documents a
mode in which the reference stays with the data owner while a team elsewhere
develops against it; two of them require reading the data in order to read the
results.

### What reading the code found

Eight facts, each read at the commit this record was written against. They are
listed first because five of them are better than the design assumed and three
of them are the work.

1. **The cases are the obstacle, and the results are not.** A TOML suite
   **opens its cases while loading**, and a `.py` suite is **imported, which
   executes it** and pulls in the application under test. So a suite in the
   software house's repository would name a case file that exists only on the
   other side. That is a requirement to redesign, not an assumption to move.
2. **`--root` means four things at once** — the suite's read perimeter, the
   store root, the git repository, and a document field, since artifact keys
   are relative to root. A suite in one place and a store in another is two
   roots, and it is the first concrete obstacle.
3. **`git_commit` is read by whichever machine runs.** Where there is no git, a
   run records `None`. ADR 0002 §9 fixes the order — git is read before any
   import of ours — and nothing in that order supplies a commit that is not
   there.
4. **A redacted document is not a stringless document.** Measured: after
   `redact(run, NOTHING_EXTRA)` a document still carries text by six routes,
   and §7 enumerates all six. Two of them reach the rendered page and not only
   the file.
5. **Nothing refuses promoting a redacted run, and every promotion condition
   survives redaction.** There is no `redacted` guard in `store/`, and every
   condition reads a field redaction keeps. What the engine lacks is not a
   check but a **producer**, and it has none: the only callers of `redact`
   render HTML and write no document.
6. **`ResultStore` has five methods and none of them removes anything.**
   `write_run`, `scan_runs`, `read_run`, `read_baseline`, `promote_baseline` —
   and `SupportsRegister` beside them. There is no `retention`, no `expire` and
   no `purge` anywhere under `src/`. The retention of the heaviest thing in the
   system is *forever, by omission*.
7. **The renderer is already pure and already served.** `pages.compare_page`
   wraps `render_html`, and `render_html` is a pure function of two documents
   with no lookup and no I/O. What is in the way is that `report`'s
   **composition** lives in `cli/`, which nothing may import (ADR 0011 §7): the
   single-run fallback and the redacted form with its artifact rescue sit
   there. About twenty lines to move.
8. **Eleven signatures take `FileResultStore` and none takes the protocol**,
   with direct construction in three places. Typing them is a refactor with no
   design in it, and it is a prerequisite for anything else here.

**One measurement that reorders the rest.** A run document with recording on is
**88.3% recorded responses** — measured on twelve archived documents of one
real suite, 2.90–2.95 MB each, every recorded answer carrying its own input.
Three things this record treats separately are therefore one field: what a
store at the data owner's side grows by, what an erasure has to reach, and what
a page load costs over a link. And turning it on is cheap where it should be
expensive: it does not enter `config_hash`, so it costs no baseline and no
re-promotion, and the run document carries no flag saying it was on.

**What this record is, said plainly.** It decides where each artifact lives and
**what may cross back**. It does not decide who signs, what a channel is, how
anything is installed, or what happens when material travels in the other
direction. Those are named in §*Not decided here*, each with the record that
owes it, because a reader of this one will otherwise assume they were settled
here.

## Decision

### 1. Where each artifact lives

**The store lives in the end company's perimeter.** Cases, runs, recorded
responses, the journal and the full reference are there, addressable by the
same key they have today. Execution happens there too, because the system under
test is there and because a suite is loaded — and, in its `.py` form, executed
— where its cases are.

**The software house's repository holds two things and no third.** The **key**
— the link between a commit and the reference it was judged against — and the
**projection**, which is the reference with every string that is not digline's
own vocabulary replaced by a token or absent. §4 is the enumeration that
decides which.

**This widens ADR 0002 §6's carve-out and does not move fixed decision 2.** §6
already put a store outside the repository — *"inside the end company's
perimeter"* — and already drew the line this record needs: *"The repository is
the system of record for the **verdict**; the production payload has a
different volume, life cycle and owner."* What §6 carved out was the
**production stream**. What this record adds to the carve-out is **offline runs
against the end company's own cases**, which have the same volume, the same
life cycle and the same owner. Fixed decision 2's stated reason survives whole:
nothing goes in a home directory, nothing becomes global state on a machine,
and the layout is still `.digline/<tenant>/` — it is the perimeter the
directory sits in that changes.

**What that buys, and it is the reason the title has two clauses.** Because the
whole value is at the data owner's side, the file that crosses can be a
derivative rather than the thing itself. A record that moved the store and left
the reference as it is would have gained nothing: the reference is where the
reasons are. A record that tokenised the reference without moving the store
would have had nowhere to resolve the tokens. **Where the store lives is why
the reference can name nothing**, and they are one decision.

**ADR 0002 §6's mandatory retention is not inherited here.** §6's retention is
a property of the production store, whose purpose is a stream. A reference that
can expire is a reference that can vanish from under a gate, and §14 says what
forgetting means for this store instead.

### 2. The committed file is a projection of a promotion that already happened

**The promotion happens where the store is**, and the committed file is derived
from its result. `promote_baseline` takes an address, reads the run from its
own store, writes the reference, and **returns the `Run` it wrote** — so the
caller holds the reference as a value the moment the promotion succeeds.
Projecting it is one call on a value already in hand.

**Nothing re-implements promotion's conditions.** What makes a run a reference
is the conditions ADR 0002 §8 collects — collected *"because they are one rule
seen from several sides"* — plus the ones records after it added, ADR 0031 §1's
moved reference among them. A producer that built a projection straight from a
stored run would have to repeat them or skip them, and skipping them is how *"a
comparison that runs anyway and returns numbers anyway"* gets committed.
Deriving from the returned reference inherits every refusal for free.

**It cannot be produced from a `Comparison`, and that is refused three ways.**
The run envelope is absent — `Comparison` carries `config_changed` as a bool
where promotion needs the hash itself, and carries no `created_at`, no
`config_hash`, no `results`, no `aggregate`, no `artifacts`, no `pinned`, no
`usage`, no `promoted_at`. **Suspended cases produce no deltas at all**, so a
rebuild would silently drop every set-aside case, which is the coverage-shrank
signal suspension exists to carry — the report already reads the *run* for its
suspended section for this reason. And `missing` deltas carry baseline-only
verdicts, so a rebuild would import rows that were never in the run. ADR 0002
§4 ruled on this in advance: *"Whoever writes a transport for `Comparison` is
going down the wrong road."*

**The order is forced, and the reason is a defect found while reading.**
`without_responses` applied to an already-projected run drops the response
*count* as well as the responses, because withheld placeholders are truthy. So
it is **promote, then project**, and never the reverse.

### 3. Who produces the file, who commits it, and how many approvals there are

**The projection is produced where the whole value and the name table are**,
which is the data owner's side. It cannot be produced anywhere else: the
substitution needs the table, the table is the end company's text, and
redaction is a function of the whole value rather than of a serialized form of
it.

**The software house commits it and puts the key beside it.** A document
produced where there is no git makes no claim about which commit it belongs to,
because that side does not know. The link is the software house's, and it
always was.

**These are two gestures and not one, and conflating them is the mistake this
section exists to prevent.** *Producing the file* is a function of a value.
*Carrying the link* is a claim about a commit. What the absence of git refuses
is the second.

**Written as the condition it is, so that whatever removes the premise fires
the consequence:** the producing side does not carry the link **for as long as
there is no git there**. If the suite arrives by a clone of the software
house's repository, git exists on that side, its runs record the commit they
were measured on, and this paragraph no longer holds — at which point the
division above rests on ADR 0002 §6's ownership line alone and is owed a
re-reading. How the suite arrives is not decided here (§*Not decided here*).
ADR 0022 §6 is the counter-example that makes this wording mandatory rather
than fussy: it stated its list of harmless inputs as a **fact**, and when one
of them stopped being harmless nothing in the record could catch it (§12).

**One approval, and the commit records it rather than signing again.**
`promoted_at` is the human signature's own time, stamped by the caller and
never by the store (ADR 0014 §3). The reference the commit carries is a
derivative of a promotion that already happened, so it already holds
`promoted_at` — projection keeps it — and the commit therefore has the
approval's own time in the document it commits. **A second signature would be a
second approval in fact, whatever it was called**, and there is one act of
approving.

**The consequence for `CLAUDE.md`'s *fixed* decision 9 and for the principle
under it.** *Reading to work is not residency; writing a copy is.* A committed
projection **is** a local write of a copy, and this record is the one declared
exception to that sentence. The exception is declared here rather than carried
silently, which is the whole of §8's argument applied to this record's own
wording.

### 4. What crosses, by enumeration — and an unclassified field is refused

**The check that cannot lie is a check by enumeration, and the enumeration is
the schema.** *"No string crosses"* is checkable. *"No dangerous string
crosses"* requires knowing which ones are. So every serialized field is
classified, and there are three classes and no fourth:

- **(a) digline's own vocabulary, or derived from it** — `schema_version`,
  `redacted`, the `status` literals, `config_hash`, the run key, ISO
  timestamps, `digline_version`, `assertion_id`, the `withheld` names, and
  `canonical`'s `"nan"` and `"inf"`;
- **(b) the committing party's own strings** — `tenant`, `suite`,
  `environment`, `git_commit`. They are the software house's by construction,
  and §13 says what that does and does not buy;
- **(c) a token, or absent.** §5 says which, and why a token rather than
  something cheaper.

**A field in none of the three is refused, not passed.** The refusal is the
point: a projection that met an unclassified field and let it through would be
a filter, and a filter has to know what it is looking for. The gate is a test
that walks the serializer and fails when an unclassified field appears — the
shape `tests/test_wire_boundary.py` already has for the wire.

**Route 6 is enumerated here rather than excepted.** `target_config` and
`judge_config` carry keys and values written by the provider *or by the end
company's own application*, reported through a shipped target; they cross in
clear today, in the document and on the rendered page, and they are class (c).
**The ADR 0005 §9 amendment follows from that**, as a consequence rather than a
prerequisite: §9 records what the provider said answered, beside the hash and
never inside it, and once an unclassified field is refused that recording needs
one sentence about what survives this boundary. Naming the amendment here and
making it at acceptance is deliberate — the enumeration does not wait on it.

### 5. What becomes a token, and why a token

**Six strings are irreducibly not digline's**, and all six are class (c): the
`case_id`; the group label inside an expanded aggregate's name; a verdict's
`name`; the calibration band's `check` word; artifact paths; and reported
configuration values and their keys.

**Why a token and not an index.** An index is unstable — add or drop a group
and positions shift, silently re-pairing different groups — and `compare()`
needs more than a label: `_expansion` needs **group-token equality across two
documents** to tell `new_group` from `now_grouped` (ADR 0028 §6), and
`checked_denominator` needs to know only *whether this is grouped*. A stable
token answers both and keeps `grouped_name`'s `family[group=…]` parseable. And
an index would lose the grouping **structure** and not only the label, because
a stored run carries the group nowhere else.

**Why a token and not a digest.** ADR 0003 §4 settles it and this record does
not re-argue it: *"Fourteen thousand candidates is not an attack, it is a
loop."* A digest of a group label, a case id or a rubric is a verifier over a
small space. Hashing is not one of the options.

**Why a token and not compare-at-the-owner.** Comparing where the data is would
let the names never leave at all, and it costs the thing the committed file is
for: the software house could no longer pair **two projections it holds**, so
the file would stop being a gate input and become a receipt. §*Alternatives
considered* keeps that shape, because it is what this design becomes if §6's
counsel question goes the other way.

**The `case_id` is the one that needs ADR 0002 §5 read carefully.** §5 says the
`case_id` *"has to cross the boundary: it is the key `compare()` pairs on"*,
and that it therefore cannot be payload — and for the bridge it already rules
the id is **generated by digline**, with *"no way to copy one"*. A token pairs
exactly as the id does, and it is generated. So the projection extends §5's
mechanism from the bridge to the reference; what it must not do is claim §5
already said so. §8 is where that is declared.

**The group label depends on a rule this record does not carry.** ADR 0010 §1's
premise is *"Which cases were in it stays in the repository"* — true when the
cases were the developer's, and broken here, because the label on a case is the
end company's text. The amendment says *the label resolves where the cases
are*, not *the label is withheld*, and **it lands in its own record, before the
first file this one commits.** The reason is this record's own status line: an
amendment with a deadline must not sit inside a record whose acceptance waits
on counsel. §5 implements the rule; it does not make it.

*2026-09-27, at acceptance: acceptance no longer waits on counsel, so the
reason above has gone. The placement stays, for a reason of its own.* The rule
corrects ADR 0010 §1's premise, so it belongs in ADR 0010. Its deadline is the
first committed file, and acceptance does not move that.

### 6. The name table

**One table per (tenant, suite), on the data owner's side, behind its own
optional protocol** — the `SupportsRegister` precedent, so a store without one
keeps working. It holds (kind, token) ↔ text. It is rewritable row by row,
because an erasure needs a writer that removes a row, and it is **never
committed**: ADR 0021 §6 says a committed file's retention is git, and a table
whose retention is git is a table nobody can shorten.

**The join key is the run key, which sees no case.** `key_of(created_at,
config_hash)` is the address today, and `config_hash`'s own docstring settles
what it carries: *"It does not cover the test data… Nothing here ever sees a
case."* So the key already exists, already carries nothing, and already
survives a case being erased.

**The table is a new artifact with its own costs, and they are named rather
than discounted:** its own retention, its own erasure obligation, its own place
in the layout — *of which ADR 0002 says nothing* — and, the sharpest one, **it
is the re-identification key**. A restored backup re-identifies every orphaned
token in every committed file. So an erasure is a two-party procedure inside
the end company too, and that is a sentence for whoever runs the store before
the first byte is written, not a footnote here.

**And the question this record cannot answer, stated with both branches because
its answer decides whether §2 stands.** If destroying the mapping is enough,
this design is as written and the committed file is a file of tokens that point
at nothing. If a record left in history counts whatever it resolves to, the
committed shape falls and the design becomes compare-at-the-owner
(§*Alternatives considered*). **It blocks accepting this record. It does not
block writing it.** Nothing here is legal advice.

*Accepted 2026-09-27 without this answer.* The sentence above was true when it
was written, and it is kept. Acceptance did not make it false; it went around
it. The record is accepted on the first branch, as a premise, and the second
branch is what reopens it (*Status*). The question is still counsel's and is
still open.

### 7. The six routes, and which of them this record closes

The routes are mechanisms by which text reaches a document that has been
redacted. All six are measured or read; none is hypothetical.

1. **Group labels**, in the redacted JSON *and* on the rendered page. Built-in,
   no third-party code involved. Class (c) by §5; the rule it needs is ADR 0010
   §1's amendment, which this record cites and does not make.
2. **A number copied out of the answer.** `travels()` tests the Python type and
   nothing else, so a number crosses on the premise that only assertions write
   it — which is true of *who* writes it and says nothing about *where the
   number came from*.
3. **A metadata key made of the answer's words.** Redaction filters by the
   value's type; the key is never inspected.
4. **A verdict whose name is not its assertion's.** `Score.name` is copied
   verbatim and nothing compares it to the name of the assertion that produced
   it. Refusing the mismatch is an **amendment to ADR 0027 §6**, which met this
   exact shape and tolerated it on purpose and tests the tolerance; it is named
   here and made there.
5. **Tool names through a declared `Disclosure`.** A declared key bypasses the
   value-type check entirely, so lists and mappings cross too. First-party in
   both halves, and not the default: it takes a line in a `.py` suite.
6. **Reported configuration values** — `target_config` and `judge_config`, keys
   and values, in the JSON and on the redacted page. **First-party with shipped
   code alone**, because the writer is the end company's own application
   reporting through a shipped target. Of the six this is the one a first
   deployment meets, and §4 enumerates it.

**Routes 2 and 3 are one channel entered from two sides.** Measured: a name
encoded as an integer under a **declared constant key** survives the verdict
filter, `canonical` — integers pass unrounded — and a JSON round-trip, and
decodes back to the name. So a check that lets only declared keys through
shrinks the **alphabet** and leaves the **channel**: it moves route 3 into
route 2 rather than closing it, and route 2 needs the provenance of a number,
which a type test cannot see.

**What §4's enumeration closes, and what it does not.** It closes every route
that carries a **string**, by type rather than by audit — which is why it is a
check that cannot lie. **It does not close route 2.** A stringless rule admits
an integer, because an integer is not a string. The type-shaped answer
available is a **declared range** rather than a declared key — an integer
crosses only inside a bound its assertion declares, which built-ins can all
state, and an 88-bit integer fails any plausible bound. It narrows the alphabet
again and does not close the channel: a length bounded at a million still
carries twenty bits per case.

**And the hole the three refusals share, stated once and cited where it
matters:**

> **The declaration ties the key to the code, not the code to the software
> house's own text.**

A name the suite declares from the end company's data passes route 4's check; a
pattern the suite built from that data produces a declared key and crosses; and
a provenance check on numbers would pass whatever its writer vouches for,
because only the writer can. Each refusal checks that what crossed matches what
was declared. **None checks who declared it, or from what** — which is §10.

### 8. The narrowing is declared, never silent

**Two things on the list of what may cross are withheld here, and that is a
narrowing rather than a contradiction.** ADR 0002 §2's verdict is *"name,
`assertion_id`, status, score, threshold, tolerance, and the metadata measured
by an assertion"*. A verdict's `name` is on that list and the projection
replaces it with a token; the `case_id` is not on that list, and ADR 0002 §5
says it has to cross. Nothing forces a thing that **may** cross to cross. But a
narrowing nobody declares is indistinguishable from a policy nobody applied,
so:

**The projected document says that it is one.** A field, beside `redacted`,
naming the regime the file was produced under. The precedent is exact and
shipped: ADR 0002 §2's `redacted` flag is *"verified, not believed"* —
`Run.__post_init__` refuses a run marked redacted whose verdicts still carry a
reason, because *"the flag would announce a guarantee that nothing provides,
which is worse than no flag."* The same rule applies to this one: a document
that declares itself projected and carries a string outside the enumeration is
refused at construction.

**Why this is not optional.** A run records no policy it was redacted under
today, so a document redacted by a fallback is indistinguishable from one whose
suite declared nothing. The general rule stands on its own and is the reason
this section exists:

> **A refusal is a fact about the file. A silent narrowing is a guess that
> happens to be safe.**

Both disclose less rather than more, so neither leaks. **The difference is not
safety; it is whether the reader is told.**

### 9. Promoting a projected run: refused, or a declared regime

**Nothing refuses it today, every promotion condition survives projection, and
§2 creates the first producer.** So the guard and the producer are owed
together, and this is where the choice is made rather than left to whoever
writes the code:

- **Refused** — a projected document is not a reference, and promoting one is a
  mistake with no legitimate instance;
- **A declared regime** — a projected reference is deliberately what gets
  committed, in which case the refusal is wrong and what is needed is §8's
  field plus a reading that says so.

**They are not symmetrical, and the asymmetry decides it.** What a promoted
projection silently carries is: no `reason` on any verdict, `suspended` masked,
artifacts with neither text nor digest — so artifact drift against that
reference answers `unknown` from then on (ADR 0003 §4, ADR 0029) — run-level
metadata emptied, and `reasons_available` false in every report. **A regime
that is declared is a fact; a reference that quietly cannot answer is the
defect ADR 0029 gave exit 2 to avoid.** This record takes the declared regime,
and §16 is the test that the undeclared case is refused.

### 10. ADR 0007 §7's premise, ruled here

**The premise, and it was never examined.** ADR 0007 §7 refuses a boundary
widening from a data suite because *"widening it requires writing Python, in a
repository, under review — which is exactly the ceremony the decision was
supposed to carry"*, and it names world 2 in as many words: *"That is a real
cost for world 2's software house, and it is the right one."*

**In world 1 the reviewer and the perimeter's owner are one party. Here they
are two**: the review is the software house's, the perimeter is the end
company's, and world 3 does not read code. So **the ceremony that guards one
party's boundary is performed entirely by the party that benefits from widening
it.**

**The ruling: the ceremony is necessary and is not sufficient, and this record
says which half it keeps.** It keeps the ceremony — a widening is still written
in a reviewed file, and §7's refusal for data suites stands unchanged. It does
**not** claim the ceremony protects the perimeter it guards, because the review
that performs it belongs to the other side. What that costs is stated rather
than repaired: every `Disclosure` line in a suite that runs inside somebody
else's perimeter is a declaration about their data, reviewed by us, and the
enumeration in §4 is the only thing in this design that does not depend on who
reviewed it.

**Two things this does not do, said because each looks like it follows.** It
does not require a declaration to be legible without a parser: *"declared in
code"* means the ceremony — written in a reviewed file — and not the execution,
so a static read of a reviewed suite satisfies fixed decision 9 outright and a
declaration constructed at run time stays valid. A static reader is therefore
**permitted and optional**, and where a declaration cannot be read statically,
loading the suite remains correct. And it does not make the declaration
**delivered**: legibility removes the ability to hide a declaration behind code
the other party could not read, and it does not put the declaration in front of
them. **How the end company comes to hold the file it would be able to read is
not answered here, and no candidate is named**, because naming one would be
designing it.

### 11. What the key claims, and what checks it

**The key is a claim, not a fact read off the document.** Where there is no git
a run records no commit, so the link between a commit and the reference it was
judged against is asserted by the side that commits.

**It is checkable, and in a shape already shipped.** Recompute `config_hash`
from the checkout at the named commit and compare it with the run's — which is
`ConfigMismatchError`'s own comparison, and the same question `view` already
answers when it supplies the hash in force — then ask whether that commit is an
ancestor of the default branch, which is exactly what this repository's own
release gate asks of a tag before anything is built or published.

**What the check forbids is the right thing.** Not promoting from a branch —
**promoting a run measured on code nobody merged.** A reference approved for
behaviour that never landed judges code that does not exist. It is a property
of **the run**, not of where the promotion commit is made: on a protected
default branch a promotion is itself a commit and cannot land without a pull
request, and ADR 0031's Context treats two people promoting from the same
default branch, each on a branch, as the normal case.

**Its honest limit.** `config_hash` identifies the rules — assertion
identities, thresholds, tolerances, `samples`, `min_agreement`, the aggregates,
the pricing digest — and deliberately not the cases. So the claim is verified
**for the code that judged and not for the data it judged**. Whether digline
refuses a bad claim or records it is not decided here: nothing in the code
checks it today, it is not among promotion's conditions, and turning it into a
refusal is a decision of its own.

### 12. The two digests: no string is not no content

**`assertion_id` holds a rubric inside its hash, and it is ADR 0003 §4's case**
— a rubric is as low-entropy as a prompt, and §4's loop is the general
refutation of a digest over a guessable space. **`config_hash` recovers what
`assertion_id` would stop carrying**, because it hashes each assertion's raw
identity, and it is not one more field: it is the second half of `key_of`. It
names every run file, the register, `list`, `log`, `compare --json` and the MCP
surface, and a promotion names the reference it replaces by it. **It is the
most widely travelling digest in the tree.**

**So the enumeration in §4 leaves this standing, and the record says so where
the result is reported:**

> **A green check by §16 says *no string*. It does not say *no content*.**

**The options, costed and unranked, because the answer they need is not in this
record.** Excluding free-text fields from identity costs the pairing — two
rubric checks on one case would share an identity and order would decide which
is which, which is the fabricated `regressed`-plus-`improved` that
`index_verdicts` refuses by construction — and it moves the verifier into
`config_hash` rather than removing it. A keyed hash costs the pairing nothing
and introduces a secret with a lifecycle: every party that computes an identity
needs it, including `reconcile`, which recomputes identities from the suite and
matches them against the recorded ids; fixed decision 2 puts configuration in
git, which is the one place a secret cannot live; and ADR 0022 §6 already
priced a committed salt — runs stamped `-dirty`, two clones disagreeing until a
merge picks a winner, and a key from the root commit failing on a shallow
clone. **Those costs carry over. Its reason does not**: ADR 0022 §6 refused a
salt because the value was *"not a secret"*, and a rubric is not that value.
**A third refusal has to argue its own case.**

**And ADR 0022 §6 is owed a sentence for a second reason.** It names the
declared rate as *"the one unknown"* in `config_hash`, because every other
input *"crosses the same boundary on its own merit: the assertion identities,
the thresholds and tolerances…"*. One entry of that list is no longer harmless.
Its conclusion — that the rate is a latch and not salted — is either right for
a different reason or incomplete, and the ADR cannot say which because the
question did not exist when it was written.

**What has to be answered before any option can be priced**, and it is the
second thing this record's acceptance waits on:

> **Who are we protecting against, when the software house holds the suite?**

A keyed hash protects against somebody who holds the file without the key. It
does nothing against somebody who holds the suite, because they can compute any
identity from the source — and in this shape the software house wrote the
suite. The records answer this differently for every field that has faced it:
ADR 0003 §4 answers *anybody who gets the document*; ADR 0023 §6 answers
*whoever holds the text can verify it anyway*; ADR 0022 §6 names no adversary
at all. **The honest reading available today is that this structure protects
the artifact — a leak, a later maintainer, the repository host — and not the
party.** Until that is ruled, this section states the question and §16 reports
the green with the sentence above beside it.

**Ruled 2026-09-27, at acceptance: nobody in particular.** This is an answer,
not a deferral: **no adversary is addressed by these digests.** The reason
stands on its own. The committed file and the suite live in one repository, so
whoever obtains one obtains the other. The loop above recovers a rubric from
`assertion_id`, and anybody who could run it can open the suite and read the
rubric. The *honest reading* above named a leak, a later maintainer and the
repository host. Each of them obtains the repository, and so the suite with it.

**`assertion_id` and `config_hash` stay as they are.** The three options are
recorded as refused, and they are refused for this reason, not for their
costs. All three will be proposed again, and a proposal should meet the reason
it was refused for:

- **Excluding the free-text fields from identity.** Refused: it removes from a
  digest a text the digest's reader already holds. Its costs to the pairing make
  it worse; they are not why it is refused.
- **A keyed hash.** Refused: a salt protects against somebody who holds the file
  without the key, and nobody holds the file without the suite. This is the
  third refusal of a salt in these records, and it argues its own case, as the
  paragraph above required. It does not rest on ADR 0022 §6's *"not a secret"*.
  The costs ADR 0022 priced still apply, and they are not the reason either.
- **Comparing only at the owner, as a remedy for the digests.** Refused: it
  would give up the software house's ability to pair two files it holds, to
  protect against a reader who holds the suite anyway. The same shape is still
  what this design becomes if §6's question goes the other way, and this ruling
  does not touch that branch.

**What reopens it, written as a condition:** **a committed file reaching a place
the suite does not.** A fork or a partial copy that carries `.digline/<tenant>/`
without the suite, a backup of the baselines taken apart from the source, or a
file handed to an auditor or a new supplier without `suite.py` each removes the
reason, and the ruling goes with it. So does any later design that ships a
reference on its own, and that is the first thing to check such a design
against.

**This is consistent with the sentence this section began with, and does not
weaken it.** *No string* is not *no content*: the digests carry content, and this
record never claimed otherwise. The ruling says who that content reaches, which
is a reader who already has it.

**The pricing digest inherits the ruling.** The declared rate is written in the
suite (`[target.pricing]`, ADR 0022), so a reader who could narrow it from
`config_hash` can read it from the file. ADR 0022 §6's conclusion, a latch and no
salt, is right for this reason and not for the one it gives. Its amendment is
owed to ADR 0022 and made there.

### 13. What decides the tenant when the suite is not loaded

**Today the suite decides and the flag only verifies.** Every command loads a
suite and takes the tenant from it; `--tenant` is refused when it differs.
Reading without loading the suite removes the verifier and makes the flag the
**source**.

**On a store that holds one tenant, that is answered by the endpoint**: there
is nothing else in the store to mistype into. **On a store that holds more than
one, a typo that happens to name another tenant reads that tenant's history**,
which is ADR 0002 §1's own sentence arriving from a direction it did not
anticipate. This record answers it for the shape it builds and **not in
general**, and it does not create the failure: the failure exists today.

**What this record may lean on in fixed decision 8, and what it may not.** It
may lean on **addressing**: one store per end company is physical separation
where a directory is one typo away. It may **not** lean on access — digline
never sets or inspects a mode, reads no uid and calls no `stat`, and
`compare()` refusing across tenants is a refusal on its own API and not a wall
around files. A software house holding N clients' projections holds N
directories of readable JSON, and opening two of them is outside anything the
tool can refuse. **A stringless document does not give a stringless
repository:** `tenant` and `suite` are directory names, and the guarantee stops
at the file boundary. ADR 0002 §1's *"enforced by the filesystem"* is owed the
correction that it is true of addressing and false of access; that amendment is
named here and made in its own record.

### 14. What the store must gain, and the two side-cars

**A delete. Five methods become six.** There is no forgetting primitive
anywhere in the product, so the retention of the heaviest artifact in the
system is *forever, by omission*. A removed run must be absent from every
reader — `scan_runs` and `read_run` included — and that is the contract, stated
as a requirement here and written in the record that designs it.

**Two files on the data owner's side are named as conditions, because what they
are decides what `delete` has to reach and neither is settled in this record:**

- **run documents carrying recorded responses**, which are the lasting
  `case_id` → input map: a recorded response holds the rendered prompt, the
  store never removes a run, and promotion strips the responses, so the
  baseline is not the map — the runs are. Measured at 88.3% of a document's
  bytes, which is what turns three separate concerns into one field;
- **the journal**, whose lifetime is short by comparison — every leg goes once
  the run is written, and the legs of a killed run go once its run file exists
  — but which holds un-redacted results keyed by case while it is there.

**Both are side-cars on that side, never on the channel, and both are reached
by the delete.** If a later ruling places either of them differently, this
section is what changes, and `delete`'s contract changes with it. **A delete is
also not an erasure** on a filesystem somebody backs up: the old blocks survive
until reused, a copy-on-write filesystem keeps them by design, and every
snapshot holds the row that was just removed. §6 says what follows for the name
table, and it is the same sentence one artifact along.

### 15. What a reader loses, declared in words

**The gate survives whole.** `exit_code` reads counts and booleans — what got
worse, whether a canary moved, what was unjudged, whether a calibration band
was lost, whether a pinned artifact drifted — and nothing else. *"Check 3 of 7
got worse"* is still a gate, and it is the whole gate.

**The report does not survive at the software house, and the code argues
against pretending otherwise in four places.** `render_html` is a pure function
of two documents with no lookup, so **the join happens before rendering**,
which means where the data is. Offline the software house holds every number,
threshold, tolerance and count, the whole authored sentence table, the entire
`detail` column — and no name for anything.

**Every absence is declared in words, and never substituted in silence.** The
precedent is exact and it cuts this way: the headline already prints a
**count** instead of artifact paths, because *"a list of paths describes a
customer"*, and it declares the absence rather than printing an index. The same
pattern governs here, and the reason it must is the tree's own sentence about
the opposite case — *"'1 check got worse' without naming it sends the reader to
open an HTML file to learn a fact that fits on one line."* An index would be
that failure one step further: there would be no file to open that could
resolve it. **There is a committed-file reader that can resolve it, and it is
on the other side of the link.**

**What this costs the one cap already in the tree, stated because it inherits a
premise this record removes.** The unreconciled clause names its gaps and caps
them, on the ground that *"the count travels with them and the run file has all
of them"*. Under a projection the run file is not where the reader is. The cap
stays correct; its justification is now the served page rather than a local
file.

### 16. What holds it

- **A test that walks the serializer and fails on a field in none of §4's three
  classes.** It must fail on `main` before the projection exists, or it is a
  test of nothing.
- **A test that a document declaring itself projected and carrying a string
  outside the enumeration is refused at construction** — §8's flag verified,
  not believed, on the `redacted` precedent.
- **A test that `promote` then `project` keeps the response count**, which is
  the order §2 forces and the defect that forced it.
- **A test that a projected document is accepted as a reference only under §9's
  declared regime**, and that the undeclared case is refused.
- **A test that the calibration band still binds after substitution.** The band
  binds by **free-text name equality** today, and when nothing binds the result
  is empty — which reads identically to *nothing was lost*. That is a check
  that cannot fire reporting the same value as a check that passed, it removes
  one of the three causes of exit 2 in silence, and it is reachable **today**,
  without any of this record. Fixed decision 3's rule against a vacuously green
  assertion is the reason it is listed here.
- **The refusal is classified.** A new exception must be in `host.REFUSALS` or
  `tests/test_refusals.py` cannot see it — and the freshest instance in the
  tree is a bare `ValueError` at the one boundary every stored document
  crosses, which reached an agent as an untranslated tool error precisely
  because the classification test walks the classes digline defines.

## Consequences

- **The gate the software house runs is unchanged in kind and poorer in
  vocabulary.** It exits on counts, and it can no longer say which case. The
  sentence a reader acts on moves to a page served where the data is.
- **`compare` at the software house pairs two projections**, which is what
  makes the committed file a gate input rather than a receipt — and the reason
  a token was chosen over comparing at the owner's side.
- **Artifact drift against a projected reference answers `unknown`**, and this
  record does not repair it: the path is the pairing key, an index cannot tell
  a renamed file from a new one, and the one leg of the gate this shape cannot
  carry is the leg digline already declines to turn into an exit code.
- **A schema bump with its whole ritual**, and eleven committed baselines that
  move with it.
- **Two new artifacts on the data owner's side**, each with a retention
  question that did not exist before, and one of which is a re-identification
  key.
- **The first declared exception to *writes nothing locally*.** The principle
  survives; the sentence now has an exception with a record behind it.
- **World 3 gets a door rather than a document somebody sent them**, which is
  what makes a locale per reader a question rather than a preference. Not
  decided here.
- **`main` still requires a pull request for a promotion**, because a promotion
  at the software house is a commit. What moves is that the approval it records
  was made elsewhere.

## Alternatives considered

- **Close the routes one by one and keep the reference as it is.** Four
  refusals, four owners, and the measurement that decides it: the hole all of
  them share (§7). Route-closing is *"no dangerous string crosses"*, which
  requires knowing which ones are. Rejected as the primary shape and **kept as
  work**: §7's route 4 and the group label are each owed anyway.
- **Compare at the data owner's side and commit nothing.** Names never leave,
  the gate is untouched, and the software house receives deltas and counts.
  Rejected *for now* and **named as what this design becomes** if §6's question
  is answered the other way: it costs the software house the ability to pair
  two references it holds, and reopens what the committed file is for.
- **An index instead of a token.** Rejected: unstable under a group being added
  or dropped, and it cannot answer the one question `_expansion` asks across
  two documents.
- **A digest instead of a token.** Rejected by ADR 0003 §4, which this record
  does not re-argue.
- **Anonymisation at the boundary.** Rejected because it cannot be met:
  removing the text destroys the case, since the input is what a judge judges.
  What is in force instead is pseudonymisation with the mapping held by the
  data owner — already amended into ADR 0002's *Consequences* — and
  **pseudonymised data is still personal data**. What it buys is narrower and
  is the whole claim: the committed record alone identifies nobody.
- **A summary method on the store, to stop reading whole documents over a
  link.** Rejected here rather than designed: six readers want six different
  sets, and the half that is a caller question — every document being parsed
  and discarded before being read again — changes no promise the store makes.
  Its size is unmeasured, and §*Not decided here* says what would decide it.
- **Tokenising at birth rather than in the projection.** Rejected: it would
  reach the journal, the cases digest, resume, the suspended snippet and every
  reader, for no gain, because the only artifact that leaves is the projection.

## Not decided here

Each of these is a record of its own, and a reader who expects it in this one
should find it named rather than assume it was settled.

- **Who signs, and with what identity.** An identity protocol, what a signature
  records about where the identity came from, whether an identity is
  **required** in order to promote or only **recorded when present** — a gate
  and a field are two different products — and the append-only record of
  approvals, which is the thing ADR 0014 §3 refused and which this record
  therefore may not add in passing.
- **Who may promote.** ADR 0033 §6 orders it behind a question about material
  entering the perimeter, so it cannot be settled here without settling that
  first.
- **Authentication and authorisation on the way in, and the channel itself.**
  Which machine may speak, which verbs exist — reading is the only one this
  record grants, and promote, delete and configuration change are unruled
  rather than forbidden — transport, and whose perimeter it crosses. ADR 0032
  §4 filed the `--host` question under fixed decision 9 and ADR 0033 §6 says a
  per-start key still serves one operator. **Nothing here configures a network
  call**, and fixed decision 5 is untouched by this record.
- **How the suite reaches the side that runs it.** §3's condition names the one
  answer that would fire a consequence, and rules none of them.
- **Material entering the perimeter** — turning a flagged answer into a case,
  with a human signature, inside the perimeter. ADR 0023 owns it, its own rule
  confines it to `.py` suites, and the committed election it would need is the
  symmetric twin of this record's projection. **The twin is why a reader
  arrives here expecting it**, and it is why it is named: this record decides
  what **leaves**.
- **Retention as a policy, and erasure as a procedure.** §14 asks for a delete
  and states its contract; how long anything is kept, and who performs an
  erasure across backups, are not settled here.
- **Files or a database**, and the network cost. The measurement that would
  decide it is the cost of a page load over a real link at a real number of
  runs, and nobody has one. What is known is that a page load reads whole
  documents, and that 88.3% of a document can be one field.
- **The reading, per reader.** A locale for a reader who is not a developer,
  whether a served page may carry the rule the end company is judged by, and
  whether a read is recorded. All three arrive with the door in §1 and none is
  answered.
- ~~**Whether the identities and the pricing digest change recipe** (§12)~~ —
  **decided at acceptance: they do not** (§12, *Ruled 2026-09-27*). And
  **whether digline refuses a bad co-versioning claim or records it** (§11).

## What this record does not claim

- **That the promise of a text-free document is true today.** It is not:
  measured, six routes carry text out of a redacted document. The projection is
  unbuilt, so *carries no text* is a property of a file that does not exist
  yet.
- **That the refusals in §7 close the class.** They share one hole, and the
  hole is §10's premise rather than a fourth refusal.
- **That §4 closes route 2.** A name inside an integer under a declared key
  crosses every filter redaction has — measured — and a declared range narrows
  the alphabet rather than closing the channel. **A green by §16 says *no
  string*, not *no content*.**
- **That the empty-identity fallback is closed.** A verdict whose
  `assertion_id` is empty pairs by its **name**, which is route 4 inside the
  pairing key, and it survives every option in §12. §4 refuses such a verdict
  in the projection; that is not the same as closing it.
- **That a stringless document gives a stringless repository** (§13).
- **That any of this is access control** (§13). A refusal changes which
  artifact would show a decision, not whether the decision was made.
- **That an agreement about wording closed a route.** Where a party has agreed
  that a particular count may cross, what closed is a question about that
  sentence. The six mechanisms stand.
- **That legibility repairs §10.** Legible is not delivered, and nobody has yet
  asked how the end company comes to hold the file it could read.
- **That a delete is an erasure** (§14), or that the name table's backups are
  reached by anything in this record.
- **That it is lawful.** The question in §6 is counsel's, both branches are
  stated, and nothing here is legal advice.
- **That the split is safe.** What is still open is listed in §*Not decided
  here* and in §7, §10, §12 and §13. A reader who finishes this record should
  be able to name every one of them.
