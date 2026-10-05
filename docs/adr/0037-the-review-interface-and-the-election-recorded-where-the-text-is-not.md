# ADR 0037 — The review interface, and the election recorded where the text is not

- Status: proposed 2026-09-29 — the text first, checkpointed before any code,
  the way [ADR 0034](0034-the-store-outside-and-the-reference-that-names-nothing.md),
  [ADR 0035](0035-the-record-of-a-deletion.md) and
  [ADR 0036](0036-the-name-table-and-the-process-that-owns-it.md) were. Nothing
  in it is implemented. **What it states was ruled before it was written**, in
  discussion, on 2026-09-28, as three questions in an order: where the label is
  given (§2), who elects and signs (§4), and the shape (§5). It is recorded
  here as ruled. **Its acceptance waits on a record that is itself
  proposed**: [ADR 0023](0023-capture.md), whose sections it supersedes and
  amends and which cannot be superseded in part before it is in force. It
  also waited on ADR 0036, the name table, without which the shape in §5 has
  nothing to resolve against; ADR 0036 was accepted on 2026-09-29, and is not
  built
- Shipped: unreleased
- Date: 2026-09-29
- Opens: **nothing on landing.** No `SCHEMA_VERSION`, no `OUTPUT_VERSION`, no
  `REGISTER_VERSION`, no `JOURNAL_VERSION`, no `LEDGER_VERSION`, no migration.
  At implementation §3's kind is a field of a case and a reason in the
  aggregate, and is priced in *Requires*
- Requires, at implementation: **a served page** at the data owner's side,
  where a person reads flagged answers and elects (§4, §6). **A kind on a case**
  that says its expected was written at review, and **one more reason** in
  `Matrix`'s list of exclusions, carried through every counting site the way
  ADR 0016 §2's canary was (§3). **A line at the software house** per elected
  case, which nothing writes today (§5). **The name table** of ADR 0036, which
  is accepted and unbuilt (§5). **Deliberately not read off ADR 0023's
  *Requires* line**, which prices world 1's command and not this — the same
  refusal ADR 0034's *Requires* makes
- Assumes: [ADR 0002](0002-three-worlds-and-where-the-data-lives.md) §1 (the
  tenant is the perimeter) and its three worlds;
  [ADR 0016](0016-the-canary-case.md) §2 (a case excluded from metrics and
  included in everything that reports what happened) and §5 (a canary moved is
  exit 1); [ADR 0023](0023-capture.md) §2 to §11, for everything this record
  does not name; [ADR 0033](0033-the-server-that-promotes-for-one-browser.md)
  §6 (where a world-2 promotion is reviewed comes before who may make one);
  [ADR 0034](0034-the-store-outside-and-the-reference-that-names-nothing.md)
  §1 (the store and execution are in the end company's perimeter), §3 (no git
  there, as a condition; one approval, which the software house's commit
  records rather than signs again), §4 (an unclassified field is refused) and
  §12 (*nobody in particular*, because no reader of a digest lacks its inputs);
  [ADR 0036](0036-the-name-table-and-the-process-that-owns-it.md), accepted 2026-09-29,
  §4 (a token is stable across every document of its suite), §5 (random, not
  derived), §6 (look-up-or-mint is atomic because one process owns the table)
  and §7 (the election is one of the table's three writers)
- Supersedes, **in part and at acceptance**, [ADR 0023](0023-capture.md) —
  **wherever the election is made at a served page at the data owner's side**,
  and nowhere else (§1):
  - §1, two clauses of its sentence: *"the apps collect — capture asks no
    question and has no UI"* and *"the commit signs — the diff is the review"*;
  - §2's *"split in the application, not in digline"*, for the review
    interface;
  - §4's **mechanism** — *"two invocations and not a dialogue"* — and not its
    reason (§6 below says exactly which is which);
  - §5's *"Capture asks nothing"* and *"never one in digline"*;
  - §7's *"no review screen"*, and *"the diff is the review, the commit is the
    signature"*, which splits in two;
  - §11, item 2 (*"no label in the log, no case"*) and item 5 (*"touches
    anything outside the draft"*). §11 calls its list closed, and this reopens
    it, declared;
  - the *Touches* line's *"nothing it writes reaches the wire"*, and the *Turns
    into surface* line, which names a command only
- Amends, **at acceptance**: ADR 0023 §6 (the id that leaves is a token, and
  the id minted inside must never leave) and §8 (its *"not ruled here"* about
  an election reaching the software house's repository is ruled, and its
  consequence 3's second path has no instance)
- Carries: what ADR 0036 §7 and its *Names* line assign to *"ADR 0023's own
  rewrite"*. The same text is here, in a record of its own instead of a
  rewrite; §*Why a record and not an amendment* says why
- Touches, in `CLAUDE.md`'s *fixed* section: **decision 9**. An elected case
  now produces a line at the software house, and a line that crosses is what
  decision 9 governs. Its token is covered by ADR 0034's narrowing; its date is
  not payload; **its approver is a field no record has classified yet**, and
  ADR 0034 §4 refuses an unclassified field — so nothing may write the line
  until it is (§5, *Not decided here*). **Decision 1** is upheld: the kind in
  §3 is data on a case, and an assertion stays a pure function of its inputs.
  **Decision 2** is upheld: everything an election writes at the data owner's
  side is in the tenant's directory there, under ADR 0034 §1. **Decision 3** is
  upheld: a case whose expected was written at review can fail, and §3 keeps it
  in the gate so that it does
- Number: 0037. Swept on 2026-09-29, before a line was written, across
  `origin/main` (`68af296`), every local and remote branch, and the
  `docs/adr/` of every worktree, the stale capture worktree's included. The
  highest number taken anywhere is 0036

## Context

**ADR 0023 was written for one world, and it is true of that world.** Both
applications it was built against are owned, maintained and judged by one
person: the one who labels an answer is the one who wrote the suite and owns
the text. Its Context says so, and every section leans on it. §5's *"the
expected is the answer given in the application, in context, when the item was
in front of the person"* is a sentence about somebody who was there. §7's
*"the diff is the review"* is a sentence about a repository where the diff
shows the text to the person entitled to read it.

**ADR 0034 moved the store, and capture with it, into a world ADR 0023 did not
describe.** Where the cases are the end company's, the store — cases, runs,
recorded responses — lives in its perimeter, execution happens there, and the
software house commits a key and a projection that names nothing. ADR 0034
names *material entering the perimeter* as ADR 0023's question and leaves it
open. ADR 0023 §8's amendment of 2026-09-28 met the new layout with its own
definition of `"private"`, and left open whether an election reaches the
software house's repository at all.

**What was missing is the review interface**: an interface inside digline,
running in the client's perimeter, that turns only flagged answers into cases,
with a human signature. ADR 0023 has no place for it. Its first clause says
capture has no UI; §5 forbids the question in digline by name; §7 refuses a
review screen. Those were right for one person reading their own log. They are
not right for an end company whose people did not write the suite, whose text
cannot leave, and whose answers were flagged by somebody who may not be the
person who decides what they should have said.

**Three questions, ruled in an order.** They were four names in ADR 0023 —
§2 and §5, §7, the election, §6 — and one of them hid under three of the four:

1. **Where and when the label is given** (§2 here). Independent, and first:
   its answer decides whether the signature has to carry a kind.
2. **Who elects, and how it is signed** (§4). Ruled second, although it hangs
   on the shape, and it moved the shape without ruling it.
3. **The shape** (§5): where the election happens and where it is recorded.
   Ruled last, on what the other two had left of it. ADR 0023 §6 then follows
   almost mechanically.

### Why a record and not an amendment

Seven sections of ADR 0023 and its header move. The series has two precedents,
and it has written down the test between them. ADR 0005 took its amendments in
place because each *"changes no decision above it"* and *"overturns nothing —
that is what makes it an amendment rather than a new ADR"*. ADR 0023 §8's
amendment of 2026-09-28 passes that test: its definition was *"met, not
widened"*.

**These rulings do not pass it.** §2 below overturns §5's *"capture asks
nothing"* and the clause of §1 the whole record is organised under. §5 below
splits §7's *"the diff is the review"* in two. That is a decision overturned,
not an open point closed.

**And the deciding reason is the one in the paragraphs above: two worlds.**
Where one person labels, elects and owns the text, ADR 0023 stays true as
written — the command, the diff that shows the text, the hash that never needs
to leave. Amended in place, each of its sections would carry two worlds at
once. As a record of its own, this one says where ADR 0023 stops, and ADR 0023
keeps saying what it says for the world it describes. ADR 0034 did the same to
ADR 0002: a world-2 shape over a world-1 record, a record of its own, and dated
notes beside the text it moved.

**The rewrite ADR 0036 §7 assigns to ADR 0023 is this record.** 0036 was
written before this form was chosen, and its *"written into ADR 0023 §6 and §7
by ADR 0023's own rewrite"* names the content correctly and the container not.
Nothing in 0036 depends on the difference.

## Decision

### 1. Where this record applies

> **Wherever an election is made at a served page at the data owner's side.**
> Everywhere else ADR 0023 stands as written.

**World 1 is unchanged.** One person, their own log, `digline capture --elect`
on a command line, a diff they read and a commit they make: ADR 0023's §4, §7
and §6 hold there word for word. Nothing here removes the command, and nothing
here requires a served page where the person who labels owns the text.

**The line is where the election happens, not who owns the repository.** A
software house working on its own cases is world 1 for this purpose. An end
company electing its own answers at a served page in its own perimeter is under
this record, whoever maintains its suite.

### 2. An expected written at review can become a case

> **An expected written at review can become a case.** It is a different kind
> of case, and digline knows it, not only records it.

**Refusing it was considered and refused.** An expected that exists in context
is one the application already holds: a thumbs-down, a correction, a rejected
answer. Those are the cases where the user already knew what they wanted. The
cases that need a person to work out *why* an answer is wrong are exactly the
ones with no expected at the time. Refusing them would leave capture nearly
nothing to capture.

**A flagged answer is two acts, and only one of them can be given in
context.** The **flag** selects: this answer deserves a look. It can be given
by whoever sees the answer when it is produced, and it becomes nothing in the
case. The **expected** decides what the answer should have been, and in a
review interface it is written later, by construction. ADR 0023 §3 already
draws this line for the application's own verdict — *"`verdict` selects,
`label` decides"* — and the flag is the same division one step earlier.

**What this supersedes, in ADR 0023's words.** §5's *"Capture asks nothing"*
and *"the remedy for a missing label is a question in the app, never one in
digline"*: at a served page, digline asks. §2's *"split in the application,
not in digline"*, for the same reason. §11's item 2, *"no label in the log, no
case"*: an answer with a flag and no label becomes a case once a person writes
its expected at review. §1's clause *"capture asks no question and has no
UI"*.

**What it does not supersede.** §11's item 1 stands: capture still never
writes an expected it inferred. The expected is written by a person at the
page, or there is no case. §2's rule on historical ambiguous labels stands:
capture never reads one as either answer. A person at review writing an
expected is the deliberate act §2 leaves to a person, performed at a page
rather than by hand in a file.

### 3. The recalled kind: in the gate, out of the aggregate

> **A case whose expected was written at review counts as a case and stays in
> the gate: if it regresses, the gate fails. It does not enter the aggregate
> accuracy.**

**"Not to be pooled" is an instruction about how things sum, not about how
they are labelled.** ADR 0023 §10's amendment of 2026-09-22 says of recalled
labels that they are *"not to be pooled with"* observed ones. A field that
says *recalled* and that nothing reads is a fact that changes nothing. So the
kind is read, and where it is read is the aggregate.

**The mechanism exists, and the precedent is exact.** `Matrix` already carries
denominators that exclude a case for a stated reason — `suspended_excluded`,
`errored_excluded`, `unlabelled_excluded`, `canary_excluded`,
`calibration_excluded` — and this is one more reason in that list, not a new
device. ADR 0016 §2 says a canary is *"excluded from **metrics** and included in
everything that reports what happened"*, and §5 that a canary moved is exit 1.
That is this split, already shipped for a different reason.

**"No new device" does not mean nothing is touched.** ADR 0016 counted eleven
counting sites for its own exclusion, and a recalled kind goes through the same
inventory, with the canary's table as the checklist. **One row is not to be
copied**: a canary is exempt from the suite's label requirement, and a case of
this kind carries a label by definition.

**Refused: a separate suite for these cases.** It takes them out of the gate,
and a case of this kind that regresses has to fail it.

### 4. Who elects: a person at a served page, of either party, and the record says which

> **An election is made by a person at a served page at the data owner's
> side, never over a channel.** **Either party's person may elect** — the end
> company's or the software house's — **and the record of the election says
> which.**

**Why a page and not a channel.** An election has no upstream ceremony: the
label is born at the data owner's side, in that moment. And an election is a
write there. It sits with promotion, which ADR 0033 keeps to a person at a page,
and away from anything that arrives already reviewed. ADR 0023 §9 already keeps
`--elect` from the operator and from the MCP server; this is the same line,
drawn for a channel.

**Why either party.** Refusing the software house's person leaves capture with
nobody to perform it on the first day, because no end company elects on its own
from the start. Refusing the end company's person removes the hand that owns
the text and the one that knows the domain: an operator at an insurer knows
whether an answer about a claim is wrong, and a developer at a software house
often does not.

**What tells them apart is the identity's source, recorded on the election.**
Which party's person approved is a fact of the election, written where the
election is, and not a convention. **The identity protocol that supplies the
source is not decided here**, and ADR 0034 lists it among what it does not
decide: this record rules what the election records, not how an identity is
established.

**The kind is recorded where the election is.** §3's kind is a fact about the
election, so it is written at the same place. *How* it is written on a case, and
whether it survives redaction, is not decided here.

**Elect comes before promote, and the reason is direction.** An election is
material entering the perimeter; a promotion is material leaving it. This
record rules where an election is made. It does not answer where a world-2
promotion is reviewed, which ADR 0033 §6 orders before who may make one, and
which is still owed.

**The consequence that must be written: this allows the third hand.** A
software house's person electing inside the end company's perimeter writes a
case whose `vars` are the end company's text, where the end company keeps it.
ADR 0023 §8's amendment says, of a software house's hand writing inside the
owner's perimeter, that it *"is not ruled here"* — and that sentence was about
the case written **by hand**. **This record allows the hand for an election,
and does not settle it for a case written by hand.** The two are now in
tension, and the tension is left standing on purpose: the record that owes the
answer is ADR 0023 §8, whose sentence it is. Either the permission extends to
the hand-written case, or §8 says why a case written by hand differs from an
election. Neither is ruled here.

### 5. The shape: elected at the data owner's side, recorded at the software house

> **The election happens at the data owner's side, and it is recorded at the
> software house.** The data owner's store holds the text. **The software
> house's repository holds one line per elected case — a token, a date, and
> who approved it. No word of the text.**

**This is ADR 0034 §3's pattern for promotion, applied to an election.** One
approval, made where the value is; the software house's commit records it and
does not approve again. A second signature at the software house would be a
second approval in fact, whatever it was called.

**Why not the election's material at the data owner's side and nothing
crossing.** ADR 0023 §7 says *"the diff is the review, the commit is the
signature"*. With nothing committed at the software house, that sentence
disappears: there is no diff and no commit, and an elected case is a row that
appeared in a store. **With a line committed, it survives, in a narrower
sense.** The diff exists, on tokens, and whoever reviews it sees **that** a
case entered without seeing what it says.

**Why not a tokenised case file at the software house.** ADR 0023 §8 refuses a
software house's repository holding the client's text, and its amendment of
2026-09-28 kept that refusal. A case file is text, whatever its ids are.

**The one thing this shape has to guarantee: the line never carries text.**
Whatever it comes to carry beyond a token, a date and an approver, it stays
inside that condition. **The approver is the part that has not been checked
against it**: if it names a person on the end company's side, it is a string
to classify under ADR 0034 §4, and until it is classified nothing may write
the line. ADR 0036's *Not decided here* names the same gap from the table's
side.

**The cost, stated and not softened: this shape needs the name table, and the
table is not built.** A token at the software house means nothing unless
something at the data owner's side resolves it, and a token is idempotent
across the software house's branches only by keeping state: two branches that
record the same election must record one token, and ADR 0036 §4 and §6 give
that — stable per suite, minted by look-up-or-mint inside one process. **ADR
0036 is accepted and not built**, and until it is built, this shape has nothing
under it. A shape where nothing crosses would have needed no table. That is
the cost, and it was accepted on purpose.

**How the line reaches the software house is not decided.** The data owner's
side has no git (ADR 0034 §3, stated there as a condition). What produces the
line there and how it arrives at a commit is the same unanswered question as
how a projection arrives, and it is left with it.

### 6. ADR 0023 §4 at a served page: the mechanism falls, the reason stands

> **This record supersedes §4's mechanism and not its reason.** The mechanism
> is *two invocations and not a dialogue*, which ADR 0023 took from its ruling
> 6 against an interactive ceremony. **At a served page there is a dialogue,
> and that is what falls.** Everything §4's mechanism was protecting is
> required of the page, word for word.

**Written out, because a page built from *"§4's mechanism is superseded"*
alone would rank.** The page:

- **ranks nothing, scores nothing, stars nothing.** Its order is of the kind
  ADR 0023 §4 gives — *"a fact about the person and not an opinion about the
  case"*. Which fact, for an answer flagged and not yet labelled, is not
  decided here;
- **pre-selects nothing.** Every election starts from nothing chosen. A
  suggested exemplar is an election the tool made and the person ratified,
  which ADR 0023's *Alternatives considered* already refuses;
- **groups by direction of error** — the pair of the application's verdict and
  the expected — as the listing does;
- **refuses more than `max_per_pattern` from one direction in one election**,
  by name and with its reason — two by default, raisable only in the suite, in
  a diff a reviewer sees;
- **has no *elect all*, no *elect this pattern*, and no threshold under which
  it elects on its own.** ADR 0023 §4's *"There is no flag that makes the
  person optional, because a flag that could is the flag that would be used"*
  applies to a button exactly as it applies to a flag.

**What falls, then, is one sentence of §4**: *"It is two invocations and not a
dialogue on purpose"*, with the clause of ruling 6 it rests on. The rest of §4
is the page's specification.

### 7. ADR 0023 §7 at a served page: the review splits in two

> **The review of *what* a case says is the page, at the data owner's side.
> The review of *that* a case entered is the committed diff at the software
> house.** In world 1 they were one act, because the diff showed the text.
> Here they separate, and each has its own place.

**What this supersedes in §7.** *"No staging area, no review screen, no file
nobody loads"*, in its second clause: the page is a review screen, and it is
where the text is read. *"The diff is the review, the commit is the
signature"*: the diff at the software house reviews only that a case entered,
and the commit there records an approval already made (§5).

**What stands.** Capture's own case file, named by the source and loaded by the
suite beside whatever an exporter produces. *Append, never rewrite.* *An
elected exemplar is permanent*, and retirement is `suspended` with its reason.
*A grown case file is a promotion owed*. The file now sits in the data owner's
store, under ADR 0034 §1, which is ADR 0023 §8's own definition of
`"private"`.

**What has no replacement, stated.** ADR 0023 §7's `-dirty` stamp is how a run
made before the signature says so. At the data owner's side there is no git,
so there is no dirty tree. **Nothing yet tells a run made after an election
and before its record at the software house.** The candidate is comparing a
run's `cases_digest` against the elections recorded, and it is undesigned.

### 8. ADR 0023 §6, amended: the id that leaves is a token, and the hash never leaves

> **A captured case has two ids.** The one minted inside the perimeter is ADR
> 0023 §6's hash of `vars`, and it stays there. **The one that leaves is a
> token from the name table**, and it is random (ADR 0036 §5).

**What §6 keeps.** Inside the perimeter its recipe costs nothing and its
dedup-by-input argument holds: two elections of one item mint one id, and a
second label on an input already held is refused by id. Scout's crossposts are
the same finding under every shape.

**What §6 loses, and why.** §6 accepted its id being a verifier, because
*"a hash of public text lets whoever holds a candidate text confirm it is a
case"*, and the text it had in mind was public threads. An end company's
`vars` are not public, and ADR 0034 §12's *nobody in particular* does not
reach them: that ruling holds because no reader of a digest lacks its inputs,
and these inputs are not in the suite's repository. **So the hash must never
leave**, and the only thing that would stop it is the projection, which is not
built. Until it is, every surface that carries a `case_id` carries this one in
clear.

**Where §6's first argument goes.** *"Two elections of one item on two
branches mint one id"* was an argument about git branches. At the data owner's
side there are none. At the software house there are, and there only a token
may go, and a random token is the same on two branches only because the table
remembers it (§5). The idempotence §6 got from the hash is now kept by the
table's state.

**Not decided here, and already named in ADR 0036:** whether an elected case's
token is the `case_id` kind or a kind of its own, and whether the id minted
inside follows ADR 0036 §5's rule instead of §6's hash.
*Ruled 2026-10-05, in ADR 0036 §7: the token is of the `case_id` kind, so the
election and a later projection name one case with one token. The inside id's
rule is still open. The sentence above is kept as written.*

### 9. ADR 0023 §8, amended: the election reaches the software house as a line

**§8's *"whether an election reaches the software house's repository at all,
are not ruled here"* is ruled**: it does, as the line of §5, and as nothing
else.

**§8's consequence 3 keeps an open path for *"an election committed to the
software house's repository, if that shape is chosen and what it commits
carries any of the owner's text rather than identifiers alone"*.** The shape is
chosen and commits identifiers alone, so that path has no instance — **for as
long as the line carries no text** (§5). The day it does, the path is open
again, and the question it asks — what would authorise the software house to
hold the text — is back with it, unanswered.

**§8's consequence 2 is not settled here** (§4, the third hand).

### 10. ADR 0023 §11: the closed list is reopened, declared

ADR 0023 §11 says *"The list is closed."* This record reopens it, in two items
and at a served page only:

- **Item 2**, *"captures an item it did not read a label for"*, gives way to
  §2: at a served page the label may be written at review.
- **Item 5**, *"touches anything outside the draft"*, gives way to §5: an
  election also mints a row in the name table, at the data owner's side
  (ADR 0036 §7), and produces a line at the software house. Nothing else
  outside the draft is touched — not the baseline, not the register, not the
  journal, not an application's own case file — and capture still makes no
  commit at the data owner's side, where there is no git.

**The other six items stand as written**, item 4 among them: capture groups
and lists, and a person names what is written.

## Consequences

- **ADR 0023 keeps its world.** For one person electing from their own log,
  nothing moves.
- **digline asks a question, at a page, at the data owner's side.** That is
  new surface, and it runs in the client's perimeter.
- **A second kind of case**, in the gate and out of the aggregate (§3).
- **Either party's person may elect**, and the election says which (§4). The
  third hand is allowed for an election and is still unruled for a case written
  by hand, in ADR 0023 §8 (§4).
- **The software house's repository gains a second kind of committed line**
  besides the projection: an election's token, date and approver (§5).
- **Capture waits on the name table**, as the projection does (§5).
- **The hash of `vars` becomes an id that must never leave**, and nothing built
  stops it from leaving today (§8).
- **ADR 0023 §4's ruling 6 falls as a mechanism and stands as a reason** (§6).

## Alternatives considered

- **Amending ADR 0023 in place.** Refused in *Why a record and not an
  amendment*: the rulings overturn decisions, and every section would carry two
  worlds.
- **Refusing an expected written at review.** Refused in §2: it leaves capture
  the cases the application already answered.
- **A separate suite for recalled cases.** Refused in §3: it takes them out of
  the gate.
- **Election over a channel.** Refused in §4: an election is a write at the
  data owner's side, with no upstream ceremony.
- **Only one party's person may elect.** Refused both ways in §4.
- **Nothing crosses to the software house.** Refused in §5: *the diff is the
  review* disappears with it. It would have needed no table.
- **A tokenised case file at the software house.** Refused in §5, by ADR 0023
  §8.
- **A second signature at the software house.** Refused in §5, by ADR 0034 §3:
  a second approval in fact.
- **Superseding ADR 0023 §4 whole.** Refused in §6: its reason is the page's
  specification.

## Not decided here

- **What a flag carries**, and who flags, and when. The contract of flagged
  answers is where §2's question lives in practice, and no record defines it.
- **A label from a person who never saw the answer in context.** It is neither
  observed nor recalled. It is not named here, on purpose: naming it is the
  first act of designing it. §4 makes it more likely, since a software house's
  person electing is a non-participant.
- **Whether the review writes the expected through the suite's declared
  mapping** (ADR 0023 §5) or in some other form.
- **How the kind is recorded on a case, and whether it survives redaction**
  (§3, §4).
- **Whether the same split applies to calibration.** Measuring a judge against
  cases written at review says how far it agrees with the reviewer, not how
  accurate it is.
- **What the line carries beyond a token, a date and an approver**, including
  whether it carries §3's kind, and **what class the approver is** under ADR
  0034 §4 (§5).
- **Whether the software house's commit needs a second identity** beside the
  data owner's. Something is committed there for an act performed elsewhere, so
  the question has a subject.
- **How the line reaches the software house** (§5).
- **A replacement for `-dirty`** at the data owner's side (§7).
- **Where a world-2 promotion is reviewed, and who may make one** (§4, ADR
  0033 §6).
- **The hand-written case by a software house's person** inside the owner's
  perimeter (§4, ADR 0023 §8).
- **The token's kind, and the inside id's rule** (§8, ADR 0036 §7).
  *The kind was ruled on 2026-10-05, in ADR 0036 §7: `case_id`. The inside
  id's rule is still open. The bullet is kept as written.*

## What this record does not claim

- **That the page exists.** Nothing here is built, and the table it rests on is
  accepted and unbuilt.
- **That a case written at review is as good as one observed.** §3 is the
  opposite claim: it is kept out of the sum because it is not.
- **That the line identifies nobody.** It carries identifiers and no text. What
  it carries about the approver is unclassified (§5), and a pseudonymised record
  is still personal data.
- **That the hash of `vars` is safe to leave.** §8 says it is not, and that
  nothing stops it today.
- **That any of this is access control.** Which party's person elected is
  recorded, not enforced by anything this record builds.
