# ADR 0039 — Disclosure on request: the software house sees a case, and the trace replaces the permission

- Status: proposed 2026-10-01. The text comes first, checkpointed before any
  code, the way [ADR 0034](0034-the-store-outside-and-the-reference-that-names-nothing.md)
  and [ADR 0038](0038-the-projection-of-a-run-nobody-promoted.md) were.
  Nothing in it is implemented. **What it decides was ruled before it was
  written**, in discussion, on 2026-09-30, and is recorded here as ruled (§1
  to §5). **Everything else in it was found afterwards.** The three problems it
  names (§6 to §8) are **not resolved here**, and *Not decided here* lists what
  is open without choosing. This record adds no ruling of its own
- Shipped: unreleased
- Date: 2026-10-01
- Opens: **nothing on landing.** No `SCHEMA_VERSION`, no `OUTPUT_VERSION`, no
  `REGISTER_VERSION`, no `JOURNAL_VERSION`, no `LEDGER_VERSION`, no migration
- Requires, at implementation, each as far as it is ruled and no further:
  - **a gesture at a page served at the data owner's side**, by which a person
    at the software house asks to see one case in clear (§1);
  - **a reason** that the gesture cannot be made without, with **a default the
    data owner's side computes** (§4);
  - **a trace** of every disclosure that names the person, with the source of
    their identity (§3, §5). **Where the trace lives is not decided** (*Not
    decided here*)
- Assumes: [ADR 0002](0002-three-worlds-and-where-the-data-lives.md) §2 (the
  payload stays where it is born), §3 (widening what leaves a perimeter is a
  change somebody writes and a reviewer sees) and §4 (a `Comparison` does not
  cross a boundary); [ADR 0034](0034-the-store-outside-and-the-reference-that-names-nothing.md)
  §1 (the store is in the end company's perimeter) and §6 (the name table is
  the re-identification key); [ADR 0035](0035-the-record-of-a-deletion.md)
  §4 and §11 (a record of a removal, and what such a record concentrates);
  [ADR 0036](0036-the-name-table-and-the-process-that-owns-it.md) §7 (the
  process that owns the table serves the pages);
  [ADR 0037](0037-the-review-interface-and-the-election-recorded-where-the-text-is-not.md)
  §4 and §7 (who elects, and the page where the text is read);
  [ADR 0038](0038-the-projection-of-a-run-nobody-promoted.md) §2 and §3
  (a served projection, and shape C of the comparison)
- Touches, in `CLAUDE.md`'s *fixed* section: **decision 9**, and §8 says how.
  A disclosure puts a case's payload in front of the software house. That
  payload is what decision 9 keeps where it is born, and nothing in the
  suite's code declares the crossing. **This is why the ruling needs a record
  and cannot be implemented as an issue.** The tension is named in §8 and is
  not resolved here
- Number: 0039. Swept on 2026-10-01, before a line was written, across
  `origin/main` (`aadf75f`), every local and remote branch and tag, the
  `docs/adr/` of every sibling worktree, the stash (empty), the open pull
  requests (none), and the site repository's refs. The highest number taken
  anywhere is 0038

## Context

**ADR 0038 stated one ruling and left its other half for later.** Its status
line records a ruling made in discussion on 2026-09-30. Pages served to the
software house show **projected** documents by default. *"Seeing a case in
clear is a disclosure that is asked for, seen and recorded."* ADR 0038 built on
the first half. Its §2 says *"'no more without the act of disclosure' is
already ruled"*, and its *Not decided here* leaves the act itself open: where
its record lives, whether a disclosed case stays disclosed, and whether the
client is told. **This record is that act.**

**What the software house may see did not narrow, and what it is shown unasked
did.** The ruling that stands behind both halves, made in discussion and
amended on 2026-09-30, is this: **the software house *can* see everything, and
disclosure on record is how.** What it is shown by default is the projected
document. A case in clear is a second act, separate from reading, and it is
recorded.

**It repaired an earlier ruling, made the same day, that described a loop that
cannot run.** The earlier ruling allowed and declared a *telephone loop*: the
software house sees a case degrade on a projected page, calls the client, and
the two talk about it. **The correction came the same day.** To telephone, the
software house has to be able to *say* the question and the two answers, and
the projection removes exactly those (ADR 0034 §4, §5 and §8). With a token
alone, the call is *"case `cap-7f2a` degraded"*, and nobody at the client
knows what that is. Disclosure on request is what replaced it.

**One word, two meanings, and this record uses only one.** `Disclosure` is
already a type: what a suite declares, in code, that may cross a boundary (ADR
0002 §3, ADR 0003). **Disclosure on request is not that type.** It is an act a
person makes at a served page, for one case, with a reason. Where this record
means the type, it writes `Disclosure` in code. Where it means the act, it
writes *disclosure* or *a disclosure*.

## Decision

§1 to §5 were ruled on 2026-09-30, in discussion. They are recorded here, not
decided here.

### 1. The software house can ask to see one case in clear, and it sees it

> **A person at the software house can ask, at a page served at the data
> owner's side, to see one case in clear. The case is shown.**

The unit is **one case**. A disclosure is never a run, and never a suite.

*Noted 2026-10-06: amended in part by [ADR
0037](0037-the-review-interface-and-the-election-recorded-where-the-text-is-not.md),
proposed, at its acceptance and at a served review page only (0037's
*Amends* and §7's note).* **§1:** at the review page the unit of a disclosure
is the opening of the page, not one case; a list of N flagged answers is not N
disclosures. **§6:** of the two alternatives §6 names and does not choose,
neither is taken: the review page is not an exception to the projected
default, and it is where a disclosure happens, a software house's person
opening it being the recorded act. §6's default reason, which has no subject
at review, is not touched. The text here is kept as written.

### 2. The end company does not authorise case by case

> **No person at the end company approves a disclosure before it is made.**

**The reason is availability, not trust.** Authorising in advance needs
somebody at the client to be available at the moment the software house needs
them. If nobody is there to answer the phone, nobody is there to authorise
either. A permission that waits for a person who is not there is a disclosure
that does not happen, or that happens by some other route that leaves no
record.
*The ruling compares this with **the link** and finds the same defect in both.
Which link is not written down with the ruling. So this record states the
defect, and does not name the other half of the comparison.*

### 3. The control moves from permission to trace

> **The end company cannot stop a disclosure. It can read every disclosure
> that was made.**

**What the trace is for:** it is what a controller shows an authority. *My
supplier saw these eleven cases, on these dates, for these reasons.* The client
gives up preventive authorisation, and it receives the trace in exchange. **A
trace that cannot say who looked is worth nothing as a trace**, and §5 is what
makes it say so.

### 4. The reason is a required field, with a default the data owner's side computes

> **A disclosure cannot be made without a reason.** The reason has a default,
> and the default is **a fact about the case, computed where the data is**:
> *"worse in the run of <date> against the reference"*.

- **Not a generic sentence.** A default that fits every case is the value
  nobody changes, and then the reason stops informing.
- **The data owner's side knows whether the case degraded against the
  reference**, so the default *is* that fact. The software house changes it
  only when its reason is something else.
- **The consequence that makes it work.** If the software house asks for a
  case that did **not** degrade, the default does not apply, and it has to
  write a reason. So the obligation to explain falls exactly on the cases
  somebody might want to look at without an obvious reason.

### 5. A disclosure names a person, with the source of their identity

*Ruled later the same day, 2026-09-30, repairing a gap in §3.*

> **A disclosure is attributed to a person, not to a caller's key. The record
> says where that person's identity came from.**

**Why the repair was needed.** A machine at the software house authenticates
with a credential of its own. A disclosure attributed to that credential would
name a party and no person, and §3's trace would lose the one thing it gave the
client in return.

**What attributes it.** A person at the software house signs gestures as a
**local user** of the process that serves the page. That is the default
identity, which cannot be turned off. The record carries **the source**: *a
local user*, and not *the client's directory*.

**The cost, stated beside the ruling.** **A local user cannot be revoked by the
client**, because only an identity from the client's own directory can. So a
software-house person's identity is, by construction, one the client cannot
withdraw. The source says so on every line that person signs, which is the
reason the source is recorded at all: the client reads what kind of identity
signed the line, and does not have to assume.

*Noted 2026-10-06: "by construction" no longer holds as written. Ruled
2026-10-05: whether the client can revoke a local user is not read off the
identity's source alone, and `source="local"` does not say which case holds.
A client-directory identity is still revocable by the client; it is no longer
the only one that may be. Who can revoke a local user is the question the
next paragraph leaves open, and it stays open here. The paragraph is kept as
written.*

**What it does not say: who creates that local user and who can revoke it.**
That is open (*Not decided here*), and under this ruling it decides who can
disclose.

## Problems this record names and does not resolve

Each of these was found after 2026-09-30. Each is written as a problem. **None
of them is resolved here.**

### 6. The default reason has no subject at review

§4's default, *"worse in the run of <date> against the reference"*, presumes a
**case** that was **compared** against a **reference**. ADR 0037's review
interface shows **flagged answers**. A flagged answer is not yet a case, and it
has no reference. **So the default never applies there, by construction**, and
under §4's own rule a reason would be written by hand for every answer a
software-house person reads at review.

This meets ADR 0037 at two places, and neither of them says anything about
disclosure:
- **§4** lets the software house's person elect.
- **§7** says *"the page is a review screen, and it is where the text is
  read."*

A person cannot write an *expected* without reading the answer. A page served
to the software house is projected by default. Either an election by the
software house's person is a disclosure, case by case, with a reason the
default never fills, or the review page is an exception to the projected
default. **Neither is written anywhere, and this record does not choose.**

*Noted 2026-10-06: ADR 0037 chooses, at its acceptance — the note under §1
says how. The paragraph is kept as written.*

*Noted 2026-10-06, on the paragraph's first sentence: it claims more than the
design supports.* What a person must have read to write an expected is, in
every case, the **input**. The answer is needed only when the expected judges
a generated answer; otherwise the application's verdict stands in for it. So
the conflict this section names is over the input, which is what a projected
page removes, and not over the answer. The sentence is kept as written.

**The default needs a comparison in clear, even where a case exists.** *"Worse
… against the reference"* is a fact only a comparison of the case in clear,
made at the data owner's side, can establish. ADR 0038 §3 left exactly that
comparison open as **shape C**, *"new material, not a corollary"*, and said so
of this default by name. **§4's default rests on shape C, and shape C is not
ruled.**

### 7. The perimeter is not broken; it is consumed

*Recorded 2026-09-30 as a consequence of §1, and left unruled by choice.*

ADR 0034 §6 calls the name table **the re-identification key**. Its acceptance
sidestepped counsel's question: *"the committed file carries no text, so there
is nothing in it to erase; erasure happens here, in this table, and what
history keeps is tokens that point at nothing."* Under the ruling on what the
software house is shown, **it no longer holds the whole table by default.**

- **A disclosure hands the software house one row of the table**: the text a
  token stands for. *n* disclosures hand it *n* rows.
- **The perimeter does not break. It is consumed.** The question the
  pseudonymisation ruling and counsel's question need answered is no longer
  *whether the software house holds the means*. It is **how much of them it has
  accumulated**, one recorded row at a time.
- **How many rows one disclosure hands over is not counted here.** The ruling
  says one row. A case shown in clear also shows its group labels and its
  verdict names, and their tokens are shared with other cases (ADR 0036 §4).
  Whether those are rows a disclosure hands over is not ruled.

### 8. Fixed decision 9 and ADR 0002 §2–§3: payload crosses, and no code declares it

**Decision 9 and ADR 0002 §2:** the payload does not cross a boundary. ADR
0002 §3 adds that widening what leaves a perimeter *"must be a change someone
writes and a reviewer sees"*, in the suite's code, never read from the data.
**A disclosure shows a case's payload to the software house, and no change in
the suite's code declares it.** The widening is a gesture at a page, with a
reason and a trace (§3, §4). It is not a line in a reviewed file.

**What the rulings did instead.** They put the control in the trace (§3), and
the attribution in a person with a source (§5). **Whether that satisfies the
property decision 9 protects, or amends decision 9, is not decided here.**
Accepting this record cannot happen without deciding it. Decision 9's amendment
of 2026-10-01 for ADR 0038 names the served projection. It does not name a
disclosure.

## What it touches

- **[ADR 0037](0037-the-review-interface-and-the-election-recorded-where-the-text-is-not.md)
  §4 and §7.** An election by the software house's person reads text that a
  projected page withholds (§6). ADR 0037 has no place for disclosure, and
  this record does not amend it.
- **[ADR 0034](0034-the-store-outside-and-the-reference-that-names-nothing.md)
  §6.** The table is the re-identification key, and a disclosure hands it out
  one row at a time (§7). §6's acceptance, *"tokens that point at nothing"*,
  was written about the committed file. It is unchanged for that file. It does
  not reach a token whose row was disclosed: that token points at text the
  software house now holds.
- **The ruling on what the software house may see**, as amended on
  2026-09-30. *What the software house may see* does not narrow; *what it is
  shown unasked* does. This record is the second act that the amendment names.
- **[ADR 0035](0035-the-record-of-a-deletion.md) §11.** That section names what
  a record of removals concentrates: beside a restored backup, a list of the
  people who asked to be erased. **A trace of disclosures is a record of the
  same shape**: an index of the cases the software house looked at, with dates,
  persons and reasons. Whether it concentrates in the same way, and where it
  should sit because of it, is not decided here. **And a case that was
  disclosed and then erased:** ADR 0035 §4 already says an entry never claims
  that the data no longer exists. A disclosure is one more place where that
  data survives, and it is outside the data owner's perimeter.
- **[ADR 0038](0038-the-projection-of-a-run-nobody-promoted.md) §2 and §3.**
  §2's *"no more without the act of disclosure"* points here. §3's shape C is
  what §4's default rests on (§6).
- **`CLAUDE.md`'s fixed decision 9** (§8).

## Alternatives considered

Each of these was weighed in the 2026-09-30 discussion. This record records
the weighing; it does not reopen it.

- **The telephone loop.** Allowed and then corrected the same day: it describes
  a loop that cannot run, because the projection removes what would have to be
  said (*Context*).
- **Authorisation case by case at the end company.** Refused in §2: it needs
  somebody available at the moment it is needed.
- **A generic default reason.** Refused in §4: a default that fits every case
  is the value nobody changes.
- **Attributing a disclosure to the caller's key.** Refused in §5: it names a
  party and no person, and the trace loses its worth.

## Not decided here

**The three left open by the ruling itself:**
- **Where the disclosure's record lives.** The ruling says it is not the
  deletion ledger of ADR 0035. Whether it is a third artifact is open, and so
  are where it sits, its retention, and who may read it.
- **Whether a disclosed case stays disclosed**, or whether the clear text is
  shown once.
- **Whether the client is told, and when.**

**Opened by what came after:**
- **The default reason at review** (§6), and whether an election by the
  software house's person is a disclosure.
- **Shape C** of ADR 0038 §3, on which §4's default rests (§6).
- **Consumption** (§7): how much of the table the software house may
  accumulate, and how many rows one disclosure hands over.
- **Decision 9** (§8): whether the trace satisfies it, or whether it is amended.

**Not addressed by any ruling:**
- **What a case in clear contains.** Its input, the recorded answers, the
  judge's reasons, and its names, or a subset of these.
- **How the record names the disclosed case**: by its token, or otherwise.
  And what that name means once the case's row is erased.
- **Who creates and revokes the local user** that a software-house person signs
  with (§5), which decides who can disclose.
- **How the gesture is protected against a request forged by another page.** A
  disclosure is a gesture, and no gesture at a served page has that protection
  written down yet.
- **A disclosure through a snippet.** ADR 0038 names #279: a line that hands
  over a case id in clear is either a disclosure or a token that no suite
  reads. This record does not rule which.

## What this record does not claim

- **That a disclosure can be prevented.** §3 says the opposite: the end company
  reads disclosures, and it does not stop them.
- **That the trace is access control.** It records who looked. It enforces
  nothing, and access to the page is the operator's, as fixed decision 8 says of
  every perimeter.
- **That the default reason is correct for every case.** §6 says where it has
  no subject, and that it rests on a comparison not yet ruled.
- **That decision 9 is satisfied.** §8 says the question is open.
- **That any of this is lawful, or sufficient towards an authority.** Nothing
  here is legal advice.
