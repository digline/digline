# ADR 0046 — A widening is a class declared in reviewed code; a recorded act selects within it

- Status: proposed 2026-10-08. The text comes first, before any code, and no
  code is owed by it at landing: the class it speaks of does not exist yet
  (§3). **What it decides was ruled before it was written**, in discussion, on
  2026-10-07, and is recorded here as ruled (*Context*). The reach of ADR 0002
  §3 (§1) and the line on flags and sources (§5) were read and ruled on
  2026-10-08
- Shipped: unreleased
- Date: 2026-10-08
- Assumes: [ADR 0002](0002-three-worlds-and-where-the-data-lives.md) §2 (the
  payload stays where it is born, and the `redacted` flag is verified, not
  believed) and §3 (the allowlist is declared in the suite's code);
  [ADR 0003](0003-artifacts-travel-only-when-the-suite-says-so.md) §4 (§3's
  rule holds for the files under test, without an exception);
  [ADR 0034](0034-the-store-outside-and-the-reference-that-names-nothing.md)
  §8 (a projected document is refused at construction if it carries a string
  outside the enumeration); [ADR 0023](0023-capture.md) §8 (a regime declared,
  never looked up)
- Touches:
  - [ADR 0039](0039-disclosure-on-request.md) §8, proposed, whose question
    this record answers: the trace satisfies the property decision 9 protects,
    and decision 9 is not amended (§2, §6). ADR 0039's text is not edited here;
  - in `CLAUDE.md`'s *fixed* section: **decision 9**. It is not amended. It
    gains one dated line that states the distinction (§6)
- Number: 0046. Swept on 2026-10-08, before a line was written, across
  `origin/main` (`9b046f4`), every local and remote branch and tag, the
  `docs/adr/` of every sibling worktree (none has one) and the open pull
  requests (none). The highest number taken anywhere is 0045. No working note
  claims 0046

## Context

[ADR 0039](0039-disclosure-on-request.md) lets a person at the software house
ask to see one case in clear, at a page served at the data owner's side, with a
reason and a trace. Its §8 names what that does to decision 9, and does not
decide it:

> **Decision 9 and ADR 0002 §2:** the payload does not cross a boundary. ADR
> 0002 §3 adds that widening what leaves a perimeter *"must be a change someone
> writes and a reviewer sees"*, in the suite's code, never read from the data.
> **A disclosure shows a case's payload to the software house, and no change in
> the suite's code declares it.** The widening is a gesture at a page, with a
> reason and a trace (§3, §4). It is not a line in a reviewed file.
>
> […] **Whether that satisfies the property decision 9 protects, or amends
> decision 9, is not decided here.** Accepting this record cannot happen
> without deciding it.

ADR 0002 §2 is not in question here. What a case in clear contains is a
separate decision, and with the judge's `reason` kept out of it, the tension
that is live is with §3 alone: a rule on the manner of a widening, not a
property of the result. An earlier ruling, of 2026-10-02, had held that decision
9 is amended. That amendment was declined on 2026-10-08, with the judge's
`reason` kept out of a case in clear, which is not this record's matter.

### What was ruled before this text, on 2026-10-07

*Ruled in discussion, transcribed verbatim.*

> The premise of A is false. A asks whether putting the control in the trace
> satisfies the property ADR 0002 §3 protects, assuming the trace replaces a
> control. Read whole, §3 gives the end company no control: the allowlist lives
> in the suite's code, which is the software house's, and the reviewer who sees
> the change is the software house's reviewer. §3 never granted the client a
> preventive authorisation, so ADR 0039 §3's "the client gives up preventive
> authorisation" surrenders nothing §3 had given.
>
> What §3 protects is a method, in three properties: the widening is not derived
> from the data ("never read from the data"); it is visible in a reviewed
> artifact ("a change someone writes and a reviewer sees"); and the default is
> closed ("whoever redacts without knowing the suite's policy discloses less,
> never more"). All three survive a disclosure. A gesture at a page is not read
> from the data: it is an act by a named person with a recorded reason. The
> default stays closed, because without a declared class nothing crosses. And
> the class is declared in reviewed code. The gesture adds what §3 never had: a
> person and a reason per instance. §3's allowlist, once written, lets every
> matching field cross for good and records no one. The trace does not weaken
> §3's method; it narrows it.
>
> Neither half is new. A widening declared in code has its precedent in ADR 0003
> §4: "one line in the suite, which is code, which goes through a review — the
> same route by which every other widening of a perimeter is decided." A
> narrowing by an act has its precedent in ADR 0034's projection and its "there
> is one act of approving". A narrowing has never needed §3, because §3 governs
> widenings. What has no precedent is combining them, and the combination
> breaches nothing: the widening is the creation of the class and sits in code;
> the act chooses an instance inside a class a reviewer has already seen.
>
> So the trace satisfies the property, and decision 9 is not amended. It gains a
> distinction it does not carry today: a declared class is the widening and
> lives in reviewed code; a recorded act selects an instance within it and is
> never a widening.

Two readings in it are marked, and §1 and §4 carry them as readings:
- that the properties §3 protects are exactly those three. §3's text states
  the allowlist's rule and gives the principle as its reason; the three are the
  ruling's reading of that sentence;
- that ADR 0034 is the precedent for a narrowing by an act. ADR 0034 keeps the
  two apart: the projection is *"a function of a value"*, and the act is the
  approval of a promotion. The argument does not rest on that precedent (§4).

## Decision

### 1. What ADR 0002 §3 protects, and how far it reaches

§3's last paragraph, verbatim:

> The allowlist is declared **in the suite's code, never read from the data**:
> widening what leaves a perimeter must be a change someone writes and a
> reviewer sees. The default is empty, so whoever redacts without knowing the
> suite's policy discloses *less*, never more.

**The ruling reads it as a method in three properties**, and that reading is
what this record declares: a widening is **not read from the data**; it is
**visible in a reviewed artifact**; the **default is closed**.

**How far §3 reaches, read on 2026-10-08.** §3 itself names `Score.metadata`
and `Run.metadata`. ADR 0003 carries the rule to the files under test, and says
so in its text, not only in a pointer:

> So the rule from ADR 0002 §3 holds without an exception, which is worth more
> than the convenience: **code that redacts without knowing the suite's policy
> discloses less, never more.** (ADR 0003 §4)

ADR 0002 §2 records the extension at its head: *"**Extended by [ADR
0003](0003-artifacts-travel-only-when-the-suite-says-so.md)** (2026-08-26): a
run also records the files that *are* the thing under test. They are neither
verdict nor measurement, and they do not cross a boundary unless the suite
declares `Disclosure(artifacts=True)`."* No other section of ADR 0002 extends
§3: §9 restates it (*"a `Disclosure` is declared in code by construction"*),
and §4 and §5 are about what crosses, not how a crossing is declared.

**So §3's reach is metadata and artifacts. No text carries it to cases**, that
is to a case's input and its answers. ADR 0003 §4's *"the same route by which
every other widening of a perimeter is decided"* is a reason given, not a
declared extension, and this record does not read it as one (*Not decided
here*).

### 2. The rule

> **A widening is a class declared in reviewed code. A recorded act selects an
> instance within a declared class, and is never a widening.**

This is the sentence other records cite. It holds whatever is put in a class:
it says where a widening sits and what an act may do inside one, not what any
class contains.

### 3. Why a recorded act meets the three properties

- **Not read from the data.** A disclosure is an act by a named person with a
  recorded reason ([ADR 0039](0039-disclosure-on-request.md) §4, §5). Nothing
  in the data decides that it happens.
- **Visible in a reviewed artifact.** The class within which the act selects
  is declared in reviewed code, as every widening is under §3.
- **Default closed.** Without a declared class, nothing crosses, whatever act
  is made.

The act adds what §3 never had: a person and a reason per instance. §3's
allowlist, once written, lets every matching field cross for good and records
no one.

**The class does not exist yet.** No code of a disclosure on request exists at
`9b046f4`. This record fixes where the class will sit when it is written, in
reviewed code. It does not describe a class in use.

### 4. Precedents, and the one this record does not lean on

- **A widening declared in code:** ADR 0003 §4, *"Turning it on is one line in
  the suite, which is code, which goes through a review — the same route by
  which every other widening of a perimeter is decided."*
- **A narrowing by an act:** the ruling names ADR 0034's projection. ADR 0034
  keeps the projection, *"a function of a value"*, apart from the act of
  approving a promotion, so this record does not present it as the precedent.
  **The argument does not need one:** a narrowing does not pass through §3,
  because §3 governs widenings.

### 5. What is verified and what is declared: a flag and a source

This record must not be read as saying that a declared regime is verified. The
corpus already has two words for the two cases, and this record uses them.

**A flag is verified by digline, at construction, against the document's own
contents, and what it verifies is one enumerated property of the form, not the
regime.**
- ADR 0002 §2: *"**The flag is verified, not believed.** `Run.__post_init__`
  refuses a run marked `redacted` whose verdicts still carry a `reason`."* And,
  in the same section, its limit: *"The check covers the reasons and not the
  metadata: whether a metadata value should have survived depends on the
  `Disclosure` that produced that run, and a `Run` does not carry it along."*
- `_check_projected` (`src/digline/core/run.py`, at `9b046f4`):
  *"`projected` is a claim about the contents, so it is checked against them,
  for `redacted`'s reason: a flag that announced a guarantee nothing provided
  would be worse than no flag."* It enumerates what it does not decide:
  *"Numbers: … a number is let through wherever it sits. And the **keys** of a
  verdict's metadata"*.
- Decision 9, as narrowed on 2026-09-27 by ADR 0034: *"A green means *no
  string*, not *no content*"*.

**A source says where a declared fact came from, and nobody verifies it.**
- ADR 0023 §8: *"**Declared, never looked up.** Whether a repository is public
  is a fact about a hosting platform, and learning it would be a network call
  nobody configured — fixed decision 5."* And, by its amendment of
  2026-09-28, for residence: *"learning whose perimeter a machine is in would
  be a network call nobody configured, and *no type can stop a false
  declaration* holds unchanged."*

The two words are not new. [ADR 0035](0035-the-record-of-a-deletion.md) §7
states them for a ledger's storage: *"**It is a source, not a flag.** A
`redacted` flag is verified by digline at construction (ADR 0002 §2). A claim
about storage that came from configuration can be verified by nobody."* ADR
0035 is proposed; it is cited here as a parallel, not as a rule this record
rests on.

**What follows for this record.** A declared class is code, reviewed; whether a
particular act selected within it is recorded with its person and its reason.
Neither is a regime that digline verifies. Where a flag is checked, it checks a
property of a document's form, and says which.

### 6. Decision 9: not amended, and one dated line added

**Decision 9 is not amended.** Its list of what crosses and what does not
stands as written. It gains a distinction it does not carry today, stated in
one dated line in the change that carries this record:

> *Added 2026-10-08 (ADR 0046).* A widening of what crosses is a class declared
> in reviewed code; a recorded act — a person, a reason, at a page — selects an
> instance within a declared class and is never a widening.

**An added line, not an amendment, and the precedent is exact.** ADR 0043 §8:
*"One line is added after the list of what crosses, in the change that carries
this record"*, and decision 9 carries it as *"*Added 2026-10-05 (ADR
0043).*"*. That is a different act from decision 9's *"*Narrowed 2026-09-27
(ADR 0034 §4, §5, §8).*"*, which changed what a projected reference carries
against the list above it. This line changes nothing the list says crosses: it
says where a widening sits and what an act may do.

## Consequences

- **ADR 0039 §8's condition is met.** Its question is decided here. Whether the
  other open points of ADR 0039 block its acceptance is a separate question,
  and it is not decided here.
- **The record that rules what a case in clear contains depends on this one,
  and names it in an `Assumes` line.** The dependency runs one way: this record
  declares a rule of method and stands alone; that one uses it.
- **ADR 0039 §3's exchange is read correctly.** *"The client gives up
  preventive authorisation, and it receives the trace in exchange."* §3 never
  granted the client a preventive authorisation, so the exchange surrenders
  nothing §3 had given.

## Alternatives considered

- **Amending decision 9.** A ruling of 2026-10-02 did; it was declined on
  2026-10-08, with the judge's `reason` kept out of a case in clear. ADR 0002
  §2 is then not touched, and on §3 there is nothing to amend: the widening is
  still declared in code, and the act only selects.
- **Reading the gesture as a suspension of §3.** It would hold if §3 granted
  the end company a control the trace replaced. It does not: the allowlist
  lives in the software house's code and is seen by the software house's
  reviewer. *"The premise of A is false."* Declined.

## Not decided here

- **Whether §3's rule reaches cases**, a case's input and its answers. No text
  carries it there (§1). *"The answer to A does not change with how far ADR
  0002 §3 reaches"*: if §3 covers only metadata and artifacts, or covers cases
  too, the conclusion is the same, because in both readings the widening sits
  in reviewed code.
- **ADR 0042's committed `cases.json`.** ADR 0042's *Not decided here*:
  *"**A committed `cases.json` keeps crossing.** … The question is one of
  content, not of path, and no rule about paths catches it."* A ruling of
  2026-10-07 placed it inside this decision (translated from the Italian it
  was given in): *"it is not a fourth point of its own: it is the same question
  as A, seen from git, and it enters its ruling."* The ruling on A does not
  name it. This text does not establish whether the rule of §2 settles it.
- **A claim outside the artefact that could be checked without a forbidden or
  destructive act.** §5's two cases do not cover it: *"No text covers it, and
  it is not assumed either way."*
- **Where the flag/source distinction gets an accepted public statement.** It
  is stated today in ADR 0035 §7, which is proposed. This record uses the
  distinction and does not establish it.
- **What a case in clear contains**, the judge's `reason` included. It is
  another record's, and this one does not touch it.

## What this record does not claim

- **That a declared regime is verified.** A flag verifies one enumerated
  property of a document's form (§5).
- **That the trace is access control.** ADR 0039: *"It records who looked. It
  enforces nothing."*
- **That the class exists in code.** It does not, at `9b046f4` (§3).
- **That ADR 0034 is the precedent for a narrowing by an act** (§4).
- **That §3's text names three properties.** The three are the ruling's reading
  of §3's sentence, and §1 says so.

## Test plan

**Nothing at merge.** This record carries no code, and the class it governs
does not exist (§3), so there is nothing a test could exercise: a test of a
rule about a class that is not written would pass by construction, and a check
that cannot fail is not one.

**Owed with the code of a disclosure on request**, when it arrives, and
written with that code: a test for each half of §2's rule. An act outside
every declared class lets nothing cross, because the default is closed (§3).
An act within a declared class is recorded with its person and its reason.
