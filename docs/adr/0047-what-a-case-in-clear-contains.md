# ADR 0047 — What a case in clear contains

- Status: accepted 2026-10-08, by Alessandro, before any code, as [ADR
  0046](0046-a-widening-is-a-declared-class.md) was. **What it decides was
  ruled before this text was written**, on 2026-10-07, and the reading of its
  condition with two consequences (§6) on 2026-10-08 (*Context*). It owes no
  code at landing (*Test plan*). No part of it waits for acceptance to rule on
  it one by one. **The field-by-field enumeration is not missing from it: it
  sits where ADR 0046's rule puts it.** A case in clear is a class, and ADR
  0046 §2 rules that a class is declared in reviewed code: a change someone
  writes and a reviewer sees. So the enumeration is written as that code, when
  the code of a disclosure is written, and reviewed there. This record decides
  what the class holds and what it never holds; the code states it field by
  field
- Shipped: unreleased
- Date: 2026-10-08
- Assumes: [ADR 0046](0046-a-widening-is-a-declared-class.md) §2 (a widening
  is a class declared in reviewed code; a recorded act selects within it). The
  dependency runs one way: ADR 0046 stands alone, and this record uses its
  rule. Also [ADR 0002](0002-three-worlds-and-where-the-data-lives.md) §2 (the
  payload does not cross); [ADR 0015](0015-the-recorded-output-and-the-declared-re-judge.md)
  §4 (a recorded answer never travels);
  [ADR 0023](0023-capture.md) §3, §6 and §8 (capture, the regime, and reading
  at a served page); [ADR 0034](0034-the-store-outside-and-the-reference-that-names-nothing.md)
  §3 (no git at the data owner's side, as a condition) and §4 (an
  unclassified field is refused); [ADR 0036](0036-the-name-table-and-the-process-that-owns-it.md)
  §4 (a token is stable for the life of its row);
  [ADR 0037](0037-the-review-interface-and-the-election-recorded-where-the-text-is-not.md)
  §5 and §7 (the line committed at the software house, and the election at a
  served page)
- Touches:
  - [ADR 0039](0039-disclosure-on-request.md), proposed, whose *Not decided
    here* asks *"What a case in clear contains"*, and whose §7 leaves open
    whether a shared row is handed over. This record answers both. ADR 0039's
    text is not edited here;
  - [ADR 0037](0037-the-review-interface-and-the-election-recorded-where-the-text-is-not.md),
    whose *Not decided here* asks *"Whether the input can be disclosed"*. This
    record answers it (§5). ADR 0037's text is not edited here;
  - in `CLAUDE.md`'s *fixed* section: **fixed decision 9**, read and not
    edited. The ruling of §5 reads what it protects (*Context*), and no ruling
    asks for a change to its text. The precedent for a reading written in a
    record while the fixed text stays as it is: ADR 0043 §1, amended on
    2026-10-06 with #451. There the change to the text is declared owed; here
    no ruling owes one
- Number: 0047. Swept on 2026-10-08, before a line was written, across
  `origin/main` (`a8df980`), every local and remote branch and tag, the
  `docs/adr/` of every sibling worktree (none has one) and the open pull
  requests (none). The highest number taken anywhere is 0046. No working note
  claims 0047

## Context

[ADR 0039](0039-disclosure-on-request.md) lets a person at the software house
see one case in clear, at a page served at the data owner's side, with a
reason and a trace. What that case contains it leaves open, under *Not
addressed by any ruling*:

> - **What a case in clear contains.** Its input, the recorded answers, the
>   judge's reasons, and its names, or a subset of these.

**No code of a disclosure on request exists**, at `a8df980` as on 2026-10-07,
when this was ruled. This record fixes what a thing that does not exist yet
will contain. It does not describe a behaviour in use.

### What was read on 2026-10-08: how far ADR 0002 §3 reaches

ADR 0002 §3's rule, *"widening what leaves a perimeter must be a change someone
writes and a reviewer sees"*, names `Score.metadata` and `Run.metadata`. ADR
0003 carries it to the files under test: *"So the rule from ADR 0002 §3 holds
without an exception"* (ADR 0003 §4), and ADR 0002 §2 records it at its head,
*"**Extended by ADR 0003**"*. **No text carries it to cases**, that is to a
case's input and its answers. ADR 0003 §4's *"the same route by which every
other widening of a perimeter is decided"* is a reason given, not a declared
extension. ADR 0046 leaves the question in its *Not decided here*, and this
record does not close it.

**What follows for this record.** It cannot derive from §3 that a case in
clear is a class declared in code. That comes from its own ruling 2, below,
which applies ADR 0034 §4 by analogy and says so. What it takes from ADR 0046
is the rule, not a reach: a recorded act selects within a declared class and
is never a widening. And for a captured case it needs no reach at all, because
reading at the page is not a crossing (§5): nothing leaves for §3 to govern.

### What was ruled before this text, on 2026-10-07

*Ruled in discussion, transcribed verbatim, each without its opening label.
Where a ruling is quoted in part, it says which part. Where a step is a reading
and no text states it, it is marked as a reading.*

**Ruling 1.**

> The question as 0039 poses it cannot be answered in its own terms. Not decided
> here offers "its input, the recorded answers, the judge's reasons, and its
> names, or a subset of these": a flat list to pick a subset from. "Its input" is
> not a field. In the suite's case it is vars; in the run it is
> RecordedResponse.input, the rendered prompt, where the artifact's text and the
> vars are already one string. Picking "the input" therefore picks either the end
> company's data alone, or that data fused with the artifact's text. The question
> is re-posed as a field in a form: every field of every named form of a case
> answers, and the forms are the six this reading named — Case, CaseResult, the
> run file, the MCP wire, the served projection, and ward's page.

It is incomplete, by a correction of the same evening: the suite's form has two
input fields, `Case.vars` and `Calibration.input`.

**Ruling 2.**

> A case in clear is a form of its own, and its content is a classification in
> code. Neither the suite's cases file nor the unredacted run file is that form:
> the first has no verdicts and no recorded answers; the second has what a run
> knows of a case, the judge's reasons included, which is not the case entire —
> vars, expected, context, the case's metadata and its label have no field in
> CaseResult, and the vars reach a run only fused inside
> RecordedResponse.input, and only where responses are recorded. In clear does not
> mean unredacted. The form is defined by enumeration, under the rule ADR 0034
> already fixed and decision 9 already carries: every field is classified, and an
> unclassified one is refused. The consequence is the point: the class of what may
> ever cross under a disclosure sits in reviewed code, and the gesture at the page
> chooses only which instance crosses, inside a class a reviewer has already seen.
> The what is code. The which is the trace.

*A reading, marked:* ADR 0034 §4 rules its enumeration for a **projected
reference**. Applying it to a case in clear is an analogy. Neither ADR 0034 nor
fixed decision 9 says it of a disclosure.

**Ruling 3.**

> The judge's reasons are not in a case in clear, and neither is the case's
> metadata. These two are the only things inside a case that the fixed decisions
> forbid outright rather than leave unnamed. Decision 9 reads: "These do not: the
> reason and any metadata not covered by a Disclosure" (CLAUDE.md, decision 9).
> ADR 0002 §2 says the same without the word any: "The payload — the reason, and
> metadata not covered by a Disclosure — is, or contains, what the system
> processed. It does not cross." And Disclosure has no key for a case's metadata:
> its metadata keys are score_metadata and run_metadata, and its third field is
> artifacts (core/types.py:101-104). ADR 0039 does not need either of them: its own
> note of 2026-10-06 under §6 says that what a person must have read to write an
> expected is, in every case, the input, and the reasons are nowhere named as
> needed. Leaving them out costs 0039 nothing it claims to want. Taking them in
> costs the amendment of a sentence that forbids and offers no method.

Its line numbers are those of `aec611e`, where it was ruled.

*A reading, marked:* that the rule covers **the case's** metadata, and not
only a score's or a run's. Fixed decision 9 says *"any metadata"* and ADR 0002
§2 says *"metadata"*; neither names the case's.

**On the recorded answers.** Its first leg, quoted here. Its second leg
rested on the judge's reasons being out, and fell on 2026-10-08; the first is
ADR 0015 §4's and stands on its own.

> The recorded answers are not in a case in clear. ADR 0015 §4's body says of
> an output that "nothing in a suite's review can make it the software house's
> to send": a place where the reviewed-code form is explicitly not sufficient,
> because the thing does not cross at all.

**On the input's source.** Its first paragraph, quoted here. The rest named
what stayed open that evening, and the captured case below closed it.

> The input cannot come from the run's form. RecordedResponse.input is a field of
> a recorded response, and ADR 0015 §4's body says redact() "drops every recorded
> response, unconditionally". The input in the run's form is therefore already
> inside that outright prohibition, not a candidate that might one day meet it.

**On the names.**

> A disclosure resolves the rows that belong to the case alone. It does not
> resolve a row whose token is shared with other cases: a group label and a
> verdict name stay tokens.
>
> ADR 0039 §7 says that a case shown in clear also shows its group labels and its
> verdict names, that their tokens are shared with other cases (ADR 0036 §4), and
> leaves open whether those are rows a disclosure hands over. They are not. By ADR
> 0036 §4 a token is stable for the life of its row, across every document of its
> suite. A shared row, once resolved, stays resolved for every case and every
> document that carries it. Resolving it is therefore a widening of the class, not
> the selection of an instance within it, and the ruling on debt A holds that a
> recorded act selects an instance and is never a widening. ADR 0039 fixes a
> bounded unit, and both of its readings are bounded. §1 says "The unit is one
> case. A disclosure is never a run, and never a suite", and its note of
> 2026-10-06, at ADR 0037's acceptance, says that at a served review page the
> unit is the opening of the page and not one case. A row shared across the suite
> is bounded by neither: it spans cases that are not on that page and documents
> that do not exist yet. A gesture that permanently resolves such a row therefore
> exceeds the unit on either reading, and it is a disclosure of the suite, one
> gesture at a time.
>
> What a disclosure does hand over stays as ADR 0039 §7 writes it: one row of the
> table, the text a token stands for, for the case disclosed.
>
> The cost, stated beside the ruling. The software house reads a case in clear
> whose group label and verdict names are still tokens. For the verdict names the
> cost is close to nothing: in world 2 the suite is the software house's own code
> and it wrote those names, so the row would hand back what it already holds. For
> a group label the cost is real wherever the label was not written by the
> recipient, and it is accepted for the reason above.

*A reading, marked:* that resolving a shared row is a widening and not a
selection. It is ADR 0046's rule applied to ADR 0036 §4, and no text makes that
application. *"The ruling on debt A"* is the ruling ADR 0046 declares.

**On the captured case.**

> A case in clear shows the input, and the answers written beside it, at a
> served page at the data owner's side, and nowhere else.
>
> Why it is not a crossing. ADR 0023 §3: "At a served page at the data owner's
> side there is no commit and nothing crosses the boundary." ADR 0034 §3, quoted
> twice in ADR 0023 §8: "reading to work is not residency; writing a copy is." ADR
> 0037 §5: the data owner's store holds the text, and the software house's
> repository holds "one line per elected case — a token and a date. No word of the
> text." ADR 0037 §10: "capture still makes no commit at the data owner's side,
> where there is no git." So the input is read where it was born, and no copy is
> made. What decision 9 protects is that the payload stays where it is born, not
> that nobody from outside reads it there.
>
> Why refusing would protect nothing. ADR 0023 §8's consequence 2 already writes
> the asymmetry and declines to repair it: a software house's person may write a
> case by hand inside the owner's perimeter, and "to write the case, that person
> reads the owner's text, which is payload in front of the software house. Where
> no page serves the case, that reading leaves no trace." And: "Where the gesture
> is governed it cannot be done today, and where it is not, it can." Refusing the
> disclosure does not prevent that reading. It moves it to the untraced route. The
> only thing the refusal produces is the same reading without a person, without a
> reason and without a trace, which is the opposite of what ADR 0039 §3 bought
> with the client's preventive authorisation.
>
> The answers written beside the input fall under the same rule and for the same
> reason, and not under a rule of their own: whatever answer sits beside the
> input in the owner's store is read at the page, and reading it moves nothing.
> For a captured case that answer is the label a person gave (ADR 0023 §5).
> Whether such a file ever carries a Calibration is said nowhere, and this ruling
> does not assume it: Calibration is a field of Case, so a calibration answer
> would sit beside the expected, and where one is there it falls under the same
> rule for the same reason.
>
> What the ruling requires, and what it does not permit. The page shows; nothing
> carries. No document, no --json and no MCP response carries the input or the
> answers written beside it — the sentence ADR 0023 §6 already writes of
> Case.metadata holds for these too. The line committed at the software house
> keeps ADR 0037 §5's guarantee unchanged: a token and a date, no word of the
> text. And the reading is a disclosure in ADR 0039's sense, with its person, its
> reason and the source of that person's identity: an untraced reading of the same
> text is the thing this ruling exists to replace, not to legalise.
>
> Not ruled here. What a software house's person may elect at the page once the
> input is disclosable. ADR 0037 §7 says the election was blocked by this
> question and that "how much of it becomes possible once the input is decided is
> ADR 0039's to say." The condition it named is lifted. What it unlocks is a
> separate ruling, and this is not it.

*Readings, marked:* that ADR 0034 §3's rule and ADR 0023 §3's sentence apply to
the disclosure of a case's input; that refusing moves the reading to the
untraced route (the asymmetry is ADR 0023 §8's, the inference is the
ruling's); and that the answers written beside the input fall under the same
rule.

### On the `reason`, ruled again on 2026-10-08

Rulings of 2026-10-02 and 2026-10-04 had held that fixed decision 9 is amended,
and that a disclosure shows the judge's `reason`. On 2026-10-08 the amendment
was declined: *"The reason stays out of a case in clear."* Its ground is ADR
0015 §4, which forbids the output with no exception, and *"reaches a quotation
of the output as it reaches the output"*. This record states ruling 3 and does
not argue it again.

## Decision

### 1. The question is a field in a form

A case has six forms: `Case`, `CaseResult`, the run file, the MCP wire, the
served projection, and ward's page. *"Its input"* is not a field, and the
question is answered field by field, in each form (ruling 1). The suite's form
has two input fields, `Case.vars` and `Calibration.input`.

### 2. A case in clear is a class, declared in reviewed code

A case in clear is a form of its own, and in clear does not mean unredacted
(ruling 2). Its content is a classification in code: every field is
classified, and an unclassified one is refused, by analogy with ADR 0034 §4
(marked above). **This is ADR 0046 §2's rule applied:** the class of what may
ever be shown is declared in reviewed code, and a disclosure only selects the
instance, inside a class a reviewer has already seen. *"The what is code. The
which is the trace."* The enumeration field by field is that code (*Status*).

### 3. What a case in clear never contains

- **The judge's `reason`.** Ruling 3, held on 2026-10-08 (*Context*).
- **The case's metadata.** Ruling 3. So the hash kept there as a key, and the
  application's `source_id` that ADR 0023 §6 writes to it, do not cross. It is
  the direction ADR 0037 §8 preferred: *"Out of the row, "never leaves" holds
  without forbidding a disclosure."*
- **The recorded answers.** ADR 0015 §4.
- **The input taken from the run's form**, `RecordedResponse.input`. It is a
  field of a recorded response, and ADR 0015 §4's `redact()` *"drops every
  recorded response, unconditionally"*.

### 4. The names: a case's own rows, and never a shared one

A disclosure resolves the rows of the name table that belong to the case
alone: one row, the text a token stands for, as ADR 0039 §7 writes it. A row
whose token is shared with other cases, a group label or a verdict name, stays
a token. Resolving it would widen the class for every case and every document
that carries it (ADR 0036 §4), and a recorded act is never a widening (ADR 0046
§2). The cost is stated beside the ruling: for verdict names it is close to
nothing, and for a group label it is real wherever the recipient did not write
the label.

### 5. The captured case: shown at the page, carried by nothing

A case in clear shows the input, and the answers written beside it, **at a
served page at the data owner's side, and nowhere else.** The input is the one
that lives in the data owner's store, `Case.vars` and `Calibration.input`, not
`RecordedResponse.input`, which §3 excludes.
- **It is not a crossing.** ADR 0023 §3: *"At a served page at the data
  owner's side there is no commit and nothing crosses the boundary."* The input
  is read where it was born, and no copy is made.
- **What fixed decision 9 protects** is that the payload stays where it is
  born, not that nobody from outside reads it there. That is a reading of the
  fixed text, and the text is not edited (*Touches*).
- **The page shows; nothing carries.** No document, no `--json` and no MCP
  response carries the input or the answers written beside it.
- **The line committed at the software house is unchanged:** one line per
  elected case, a token and a date, no word of the text (ADR 0037 §5).
- **The reading is a disclosure** in ADR 0039's sense, with its person, its
  reason and the source of that person's identity.

### 6. The condition: no git at the data owner's side

§5 rests on *"no commit at the data owner's side"*. ADR 0037 takes that from
ADR 0034 §3 and states it as a condition: its *Assumes* names ADR 0034 §3 with
*"no git there, as a condition"*. **If git appears at the data owner's side,
the premise of §5 is to be looked at again.** This is a condition, written so
that whatever removes the premise fires the consequence, not a doubt about the
ruling.

**One trigger, two consequences, and they are not the same condition.**
- For what is protected: **fixed decision 9**, the payload staying where it is
  born, on which §5's reading rests.
- For who carries the link: **ADR 0034 §3**, which writes its own condition on
  the same trigger: *"the producing side does not carry the link **for as long
  as there is no git there**. If the suite arrives by a clone of the software
  house's repository, git exists on that side, […] and this paragraph no longer
  holds"*.

A change that brings git to the data owner's side reopens both, and each is
read in its own text.

## Consequences

- **This record assumes ADR 0046, in an `Assumes` line, and the dependency
  runs one way.** ADR 0046 declares a rule of method and stands alone; this
  record declares the content of a mechanism and uses that rule.
- **Two open points of ADR 0037 are closed.** *"Whether the input can be
  disclosed"*: it can, at the page, and nothing carries it (§5). And, in the
  other direction, whether the hash kept in a case's metadata crosses through a
  disclosure: it does not, because the case's metadata is out (§3).
- **ADR 0039's question is answered**, together with its §7: a shared row is
  not handed over (§4).
- **Nothing changes in the line committed at the software house** (§5).

## Alternatives considered

- **Picking a subset of ADR 0039's flat list.** Declined by ruling 1: *"Its
  input"* is not a field, and a subset of a list that names no field answers
  nothing.
- **Showing the judge's `reason`.** Held on 2026-10-02 and 2026-10-04, and
  declined on 2026-10-08, with ADR 0015 §4's ground (*Context*).
- **Refusing the captured case's input.** Declined: the same reading stays
  possible by hand, inside the owner's perimeter, and a refusal moves it to the
  untraced route (ADR 0023 §8, consequence 2).

## Not decided here

- **What a software house's person may elect at the page once the input is
  disclosable.** *"What it unlocks is a separate ruling, and this is not it."*
- **Whether a captured case's file ever carries a `Calibration`.** *"Whether
  such a file ever carries a Calibration is said nowhere, and this ruling does
  not assume it."*
- **Whether ADR 0002 §3's rule reaches cases**, as in ADR 0046's *Not decided
  here*. This record does not close it (*Context*).
- **Whether showing the vars shows what the verdict judged, when the target adds
  something to them.** A question for whoever builds the page, ruled on
  2026-10-07 as blocking nothing.
- **The election's line.** Whether fixed decision 9's text gains the line an
  election commits at the software house, a token and a date. It does not
  travel with this record. Ruled on 2026-10-08, translated from the Italian it
  was given in: *it first needs a ruling of its own, and the single pull
  request carries the application of rulings already made*.

## What this record does not claim

- **That ADR 0002 §3 covers cases.** No text says so (*Context*).
- **That a reading at the page is a crossing.** It is not (§5).
- **That the class exists in code.** It does not, at `a8df980`.
- **That ADR 0034 §4 speaks of a disclosure.** Ruling 2 applies it by analogy,
  and says so.

## Test plan

**Nothing at merge.** This record carries no code, and the class it governs
does not exist (*Context*), so there is nothing a test could exercise.

**Owed with the code of a disclosure on request**, when it arrives, and written
with that code:
- no document, no `--json` and no MCP response carries a case's input or the
  answers written beside it;
- a row whose token is shared with other cases stays a token in a case in
  clear;
- the judge's `reason` and the case's metadata are absent from a case in
  clear;
- the line committed at the software house carries a token and a date, and
  nothing else (ADR 0037 §5).
