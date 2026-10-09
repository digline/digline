# ADR 0038 — The projection of a run nobody promoted

- Status: accepted 2026-10-01, by Alessandro Prandini. It was proposed on
  2026-09-30, the text first and before any code, the way
  [ADR 0034](0034-the-store-outside-and-the-reference-that-names-nothing.md)
  and [ADR 0037](0037-the-review-interface-and-the-election-recorded-where-the-text-is-not.md)
  were. **Unlike ADR 0037, nothing in its decision was ruled before it was
  written.** The proposal recorded what reading found and the options the
  reading left open. The ruling came the next day and is written into §1 to §4.
  The findings under *Context* are kept as they were proposed, except where a
  sentence said the question was unruled. Nothing in it is
  implemented. **One ruling it rests on is older**, made in discussion on
  2026-09-30: pages served to the software house show **projected** documents
  by default, and seeing a case in clear is a disclosure that is asked for,
  seen and recorded. No other record in this repository carries that ruling
  yet, so it is stated here, where it is used
- Shipped: 0.25.2
- Date: 2026-09-30
- Opens: **nothing on landing.** No `SCHEMA_VERSION`, no `OUTPUT_VERSION`, no
  migration
- Requires, at implementation: **a projection that starts from a run** that
  was not promoted, beside the one that starts from a reference (§1).
  `project` keeps its refusals for the committed file
- Amends, at acceptance: ADR 0034 §2. **Narrowed**: its refusal to start from
  anything but a promotion is the committed file's. *Made 2026-10-01, in the
  change that accepted this record.*
- Owes: ADR 0036 §7 a sentence about **serving a page writes the table** (§4).
  It is named here, not resolved here. *Written 2026-10-01, as a dated
  amendment under [ADR 0036](0036-the-name-table-and-the-process-that-owns-it.md) §7, which in turn names what it owes ADR 0035*
- Assumes: [ADR 0002](0002-three-worlds-and-where-the-data-lives.md) §4 (a
  `Comparison` does not cross a boundary) and §8 (promotion's conditions);
  [ADR 0015](0015-the-recorded-output-and-the-declared-re-judge.md) §5 (a
  baseline carries no answers);
  [ADR 0034](0034-the-store-outside-and-the-reference-that-names-nothing.md)
  §2, §3, §4, §8, §9 and §12;
  [ADR 0036](0036-the-name-table-and-the-process-that-owns-it.md) §4, §6 and
  §7; [ADR 0037](0037-the-review-interface-and-the-election-recorded-where-the-text-is-not.md)
  (a served page at the data owner's side)
- Touches `CLAUDE.md`'s fixed decision 9 as ADR 0034 narrowed it, which is why
  this is a record and not an issue
- Read at digline `main` = `26cdc9c` (#296). Code and records were read, and
  nothing was run or measured. At acceptance, `main` was `6772ee7` (#301). No
  file under `src/digline/core/`, `src/digline/store/` or `docs/adr/` changed
  between the two

## Context

A page served at the data owner's side to a person at the software house shows
six kinds of document:
- the list of a suite's runs;
- one run;
- a run against its baseline;
- a run against another run;
- one case across runs;
- the suspension snippet.

Under the ruling above, each one is shown projected.

**`digline.core.project` refuses every run on those pages except one.** It
refuses a run with no `promoted_at` (`core/projection.py:85`) and a run that
still carries recorded answers (`:91`). The one document it will project is
the reference the run is compared against. **It cannot project the run under
review**, and showing what the last round did is the whole job of those pages.

The refusal is ADR 0034 §2's, and §2 was written for **the committed file**:
the reference the software house keeps in its repository. Until this record,
nobody had ruled whether it binds a page that is served and not committed.
That question touches what a projected document carries, which is fixed
decision 9 as ADR 0034 narrowed it, so the rule is text before code.

### What reading found

**1. §2 makes two arguments, and its "three" belongs to the second.** A first
reading, on 2026-09-30, counted three reasons and found that two still apply.
The three it counted were not one list.
- **Argument A, §2's second paragraph: start from a promotion.** *"Nothing
  re-implements promotion's conditions … A producer that built a projection
  straight from a stored run would have to repeat them or skip them, and
  skipping them is how 'a comparison that runs anyway and returns numbers
  anyway' gets committed. Deriving from the returned reference inherits every
  refusal for free."*
- **Argument B, §2's third paragraph: a `Comparison` is refused "three
  ways".**
  1. *"The run envelope is absent"*: a `Comparison` has no `created_at`,
     `config_hash`, `results`, `aggregate`, `artifacts`, `pinned`, `usage` or
     `promoted_at`, and it carries `config_changed` as a bool where promotion
     needs the hash.
  2. *"Suspended cases produce no deltas at all"*, so a rebuild drops every
     case that was set aside.
  3. *"`missing` deltas carry baseline-only verdicts"*, so a rebuild imports
     rows that were never in the run.
- **§2's fourth paragraph, on order.** *"`without_responses` applied to an
  already-projected run drops the response count … it is promote, then
  project."*

The two that were said to still apply are B2 and B3. The third was argument A,
which is not one of B's three ways, and B1 was not counted. **This matters,
because only argument A bears on projecting a run.** B1, B2 and B3 are about
building a document out of a `Comparison`. They say nothing about projecting a
`Run` that exists. §3 takes them up.

**2. Promotion changes two fields, and refuses five states.**
`promote_baseline` writes `replace(without_responses(run),
promoted_at=promoted_at)` (`store/file_store.py`). Before it writes, it refuses
five states that a run carries in the document itself (`refusals_for`,
`store/promotion.py`):
- a `config_hash` that is not the current one;
- a run judged from recorded answers (`rejudged_from`);
- a run that does not reconcile with what its suite asked;
- a run with errored verdicts;
- a run whose calibration lost its band.

**Those five are the runs a reviewer most needs to see.** Argument A keeps them
out of a reference. A served page is not a reference, and it shows them for
the reason promotion refuses them.

**3. The ten `TokenKind`s cover a current run as fully as a reference.**
`rename` maps by place in the document, and promotion adds no named place. The
two places no kind covers are the same for both:
- a target-side identity, which `project` refuses;
- the keys of a verdict's metadata, which ADR 0034 §4 has not classified
  (`_check_projected`'s docstring).

What a current run adds, run through `redact(run, NOTHING_EXTRA)` and then
`rename`:

| In a run, not in a reference | What a projection would carry | Covered? |
|---|---|---|
| Recorded answers | `RecordedResponse(withheld=True)` placeholders: **the number of answers per case crosses**. A projected reference never carries it, because its list is empty. Per-call usage goes with the answers | No name is involved. **The count is a number**, and numbers are the axis ADR 0034 §4 does not decide |
| No `promoted_at` | Absent | Nothing to cover. `_check_projected` treats empty as absent |
| Errored verdicts | The `error` status. The reason is redacted. String metadata is dropped by `travels()`, which lets through only `bool`, `int` and `float`. So nothing a string check could refuse reaches `_check_projected` | The name is `verdict_name` |
| An unreconciled run | `unreconciled()` reads a case id, a verdict name and the `UNRECONCILED` marker, which is `True` on an errored verdict. The marker is a `bool` and travels, and the two names become tokens | Yes. **A projected run still says it does not reconcile, in tokens** |
| `rejudged_from` | A run key | Class (a). Its form has been checked on a projected document since #296 |
| An old `config_hash` | A digest | Class (a), and form-checked since #296 |

Carried by both kinds of document, and worth stating once so that nobody reads
it as new:
- a suspension reason masked to the marker;
- artifacts withheld, so artifact drift reads `unknown` (ADR 0034 §9);
- `reasons_available` false;
- no run-level metadata;
- `usage` totals in clear.

**4. The table would gain a writer on page views.** ADR 0036 §7 describes the
projection writer as the one that *"mints the tokens of a reference"*. A page
that projects a run mints a token for every name no earlier projection met, so
**serving a page writes the table**. It stays inside the owning process, which
is §7's condition, and it satisfies that condition only if the process that
serves the page is the process that owns the table. §7's sentence names a
reference, and a served run is not one.

**5. ADR 0002 §4 already speaks to the comparison.** *"A `Comparison` does not
cross a boundary. What crosses is a redacted `Run`, and the comparison is redone
on the other side. Whoever writes a transport for `Comparison` is going down the
wrong road."* Its reason is that a `Comparison` *"contains the verdicts it
received, so it carries the payload of what it was given."*

## Decision

### 1. ADR 0034 §2's refusal narrows to its reason: a served page may project a run nobody promoted

> **§2's refusal to start from anything but a promotion is the committed
> file's.** A page served at the data owner's side may project a run that was
> not promoted, and one that still carries recorded answers.

**Why.** Argument A's reason is to inherit promotion's refusals for free, so
that a non-reference is not committed. A served page commits nothing, so the
reason does not reach it. And binding the sentence as written would cost what
finding 2 measured. The runs promotion refuses are errored, rejudged, not
reconciling, out of their calibration band, or on an old `config_hash`, and
those are the runs a reviewer most needs to see. Read as written, the refusal
would keep out exactly what the served pages exist to show.

**What does not change.** `project` keeps both refusals. They are the committed
file's, and that file is still a projection of a promotion that already
happened. The run nobody promoted is projected by a second way in, which this
record requires and does not shape (§*Not decided here*).

**What follows from it, stated so that it is not read as ruled here:**
- **A served projection must not become a reference.** `promote_baseline`
  reads from its own store by address, and that store holds runs in clear. So
  a served projection reaches promotion only if something writes it into a
  store. **That is a condition, and it is written as one:** if a served
  projection is ever written where a promotion can read it, this paragraph
  stops holding, and ADR 0034 §9's question of regime reopens for it.
- **ADR 0034 §8's rule is *verified, not believed*.** So a served projection
  and a projected reference must be distinguishable on the document, and
  checkably. The document already carries the field §2's check reads,
  `promoted_at`, whose form has been checked since #296. **Whether that field
  is the declaration §8 asks for, or something more is owed, is not decided
  here.**

  *Ruled 2026-10-01; the bullet above is kept as written.* **`promoted_at` is
  the declaration, and no field is added.** A projected reference carries
  `promoted_at` and no recorded answer. A served projection of a run nobody
  promoted carries no `promoted_at`, and may carry answers as withheld
  placeholders. Both facts are on the document and both are verified there:
  the stamp for its form since #296, a withheld answer by `Run`'s check of a
  redacted document.
  - **A field of its own was refused, for three reasons.** It would be a claim
    where the distinction can already be read off verified fields. It would
    cost a schema bump. And it would invite `compare()` to treat the two as
    regimes, which would break §3's shape B, a served run held against the
    projected reference.
  - **What enforces it is the place a reference is read.** `read_baseline`
    refuses a projected document that is not a reference, as
    `NotAReferenceError`. So the condition in the bullet before this one now
    notices when it is broken.
  - **Its limit, declared:** it reads what the document says. A document built
    by hand with a stamp and no answers passes, as it does `project`'s own
    check.

### 2. A served projection carries the same as a committed one: no more, no less

> **A served projection of a run carries what a projected reference carries,
> plus what a current run has that a reference does not.** Finding 3 lists
> that difference, and none of it needs a kind. It is a number and digline's
> own vocabulary, not names.

**Why not more.** *"Ephemeral"* buys nothing:
- it describes the reader's intention, not the bytes, and `render_html`
  produces a self-contained document that anybody can save;
- the tokens on a page are the vocabulary that stays. ADR 0036 §4 and §6 give
  one token per (kind, text) per (tenant, suite), so a page's tokens join with
  every committed reference's tokens;
- the table grows with every page served (finding 4).

And *"no more without the act of disclosure"* is already ruled: projected by
default, clear on request and on the record.

**Why not less.** Nothing in the records says that a served projection must
carry less than a committed one.

**The response count crosses as every number crosses a projection today.**
Under this ruling it is on the page. It crosses under ADR 0034 §4's open axis,
like a score, a threshold or a count in a projected reference, and this record
does not decide numbers.

### 3. The comparison: shape A stays refused, shape B is permitted, shape C stays open

The three shapes apply in the same way to a run against another run (`diff`)
and to one case across runs.

- **(A) Rebuilding a run document from a `Comparison` stays refused.** B2 and
  B3 hold for a page as they do for a file. A page shows the cases a rebuild
  drops and the rows it imports as surely as a file stores them.
- **(B) Projecting the two runs and comparing the projections is permitted.**
  It is the same question as §1, so §1's ruling permits it. It is ADR 0002
  §4's own shape: redacted runs cross, and the comparison is redone.
  - **With ADR 0034 §9's condition: one table.** Both projections are minted
    from the same table.
  - **Two projections minted from different tables stay ADR 0036's open
    question.** Nothing on a projected document says which table minted it,
    and nothing checks this.
  - **It answers less than a comparison in clear**, which is declared, not
    repaired. Artifact drift reads `unknown`, and no reason is available.
- **(C) Computing the comparison in clear and tokenising it afterwards is not
  ruled here.** No ADR speaks to it except ADR 0002 §4, whose sentence refuses
  a `Comparison` crossing a boundary. The default reason a disclosure carries
  (*"worse in the run of <date> against the reference"*) already needs a
  comparison in clear at the data owner's side. **So C is new material, not a
  corollary of this record**, and it is left for one of its own.

### 4. Serving a page writes the name table, and ADR 0036 §7 does not provide for it

**This record names the consequence and does not resolve it.** Under §1, a page
that projects a run mints a token for every name no earlier projection met
(finding 4). ADR 0036 §7 lists three writers, and its projection writer
*"mints the tokens of a reference"*. A served run is not a reference.
**The sentence that settles it is owed to ADR 0036**, which owns the table and
its writers. This record makes no amendment there.

*Noted 2026-10-01: the sentence is written, as a dated amendment under
[ADR 0036](0036-the-name-table-and-the-process-that-owns-it.md) §7.
It adds what this section did not see. The table grows with the distinct
names in the runs somebody looked at, not with the number of views. And ADR
0035's ledger names a row by a token that, for a row minted by viewing, no
committed document may carry, which it leaves owed to ADR 0035. The section
above is kept as written.*
*Answered 2026-10-09 by [ADR 0035](0035-the-record-of-a-deletion.md), at its
acceptance: such an entry still names the row by its token, and says whether
the token was handed out in a document meant for a commit (§4 there,
`handed_out`). The note above is kept as written.*

## Consequences

- **ADR 0034 §2 carries the narrowing beside the sentence it narrows**, as a
  dated note, so that a reader who meets the refusal meets its limit in the
  same place.
- **`CLAUDE.md`'s fixed decision 9 names the served projection** in one dated
  line that points here. Nothing the decision said was false. It governs a
  thing it did not name, and a reader of that file alone would not know the
  thing exists.
- **ADR 0036 §7 is owed a sentence** (§4). *Written 2026-10-01.*
- **Issues #277 and #278 can now be answered in substance.** Each renders a run
  that public digline could not project, and §1 permits the projection. They
  still wait on the second way in.
- **#279's snippet hands over a case id in clear.** On a projected page that is
  either a disclosure or a token that no suite reads. This record does not
  rule which.

## Alternatives considered

- **Binding §2 as written (the proposal's option (a)).** Under it, a served
  page would project the reference and nothing else, and the run under review
  would reach the software house only through a disclosure, one case at a
  time. It needed nothing new in digline. It was refused for §1's reason: it
  keeps out the five states of finding 2, and those are what the pages exist to
  show. In practice, *projected by default* would have meant *not shown by
  default*.
- **A served projection that carries more, because a page is not kept.**
  Refused in §2: a page's bytes can be kept, its tokens are kept anyway, and
  the table grows.
- **An issue beside #276 to #279.** Refused on 2026-09-30. Those four ask for
  something that exists to be made public. This asks for a function that did
  not exist, whose nearest relative an ADR refused in the case it was written
  for, and it touches fixed decision 9.
- **Serving documents as they are.** Refused by the ruling this record rests
  on. That would make the served page a step towards a client who agrees to
  show their data, which is a different product from the one the records
  describe.

## Not decided here

- **The shape of the second way in**: a function beside `project`, a parameter
  on it, or something else. *Decided 2026-10-01: a function,
  `project_served(run, mint)`, in `digline.core` beside `project`. `project` is
  its two refusals in front of `project_served`, so for a reference both give
  one document. A parameter was refused because it would make the committed
  file's refusals a default. The bullet is kept as written.*
- **Whether `promoted_at` is the declaration ADR 0034 §8 asks for**, so that a
  served projection is told apart from a projected reference (§1). *Ruled
  2026-10-01, in §1: it is, and `read_baseline` enforces it. The bullet is
  kept as written.*
- **Shape C** of §3.
- **What ADR 0036 §7 says about the table's writer on page views** (§4).
  *Written 2026-10-01 in ADR 0036 §7. The bullet is kept as written.*
- **Numbers**, the response count included: ADR 0034 §4's open axis.
- **The keys of a verdict's metadata**, which are in no class yet.
- **Two projections minted from different tables**: ADR 0036's question.
- **How `render_html` renders a document whose names are tokens.** It reads
  `redacted` and says so in its header. Nothing else about it was measured.
  *Written 2026-10-01 (#313): both renderers now read `projected` too, and a
  projected document says in its header, beside the redacted line, that its
  names were replaced and that the data owner keeps them. The withheld
  configuration keys are #323. The bullet is kept as written.*
- **Where the disclosure's record lives, whether a disclosed case stays
  disclosed, and whether the client is told.** These are open in the ruling of
  2026-09-30, and this record does not reach them.

## What this record does not claim

- **That anything was run.** Every finding above is a reading of the code at
  `26cdc9c` and of the records. None of it was measured.
- **That a served page is not kept.** Nothing in digline marks a page as not a
  copy, or enforces that it is not kept. That is part of why §2 gives a served
  projection no more than a committed one.
- **That shape B needs nothing beyond §1.** It needs one table per (tenant,
  suite). That holds because of how the owning process is arranged, and
  nothing checks it.
