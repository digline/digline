# ADR 0002 — Three worlds, and where the data lives

> **Note on the name (2026-08-26).** «prompteval» was the project's working
> name; it became **digline** because the name was already taken in the
> category. The text below has been updated to the new name: this note is the
> only place where the old name remains written.

- Status: accepted
- Shipped: 0.1.0
- Date: 2026-08-25
- Introduces: fixed decisions 8 (tenant) and 9 (payload/verdict) of `CLAUDE.md`
- Assumes: [ADR 0001](0001-verdict-not-score.md)

## Context

ADR 0001 was written assuming a single world: a developer evaluating their own prompts in
their own repository. The assumption was wrong, and not at the margins.

digline's typical customer is not a single team. It is a **software house** that builds
and maintains AI solutions for end companies that do not develop software. Three distinct
roles follow, with different interests in and rights over the same data:

**World 1 — the developer.** Works in the repository, writes the assertions, reads the
code. Sees everything they produce, because they produce it on data they chose.

**World 2 — the software house.** Maintains N customers at once. Must be able to answer
"did customer A's solution get worse after Tuesday's release?" **without holding customer
A's production data**, and without A's and B's data ever ending up in the same place by
inattention.

**World 3 — the end company.** Owns the production data and does not read code. Is
entitled to an understandable verdict about a system it cannot inspect, and is entitled to
its data not leaving.

The conflict is real and cannot be solved with a permission: the software house needs the
signal, the end company cannot hand over the content. The rest of this document exists to
separate the two so that the type guarantees it, not discipline.

## Decision

### 1. The tenant is the perimeter, and it is mandatory

`Run.tenant: str`, mandatory, non-empty. A tenant is a perimeter — an end customer of the
software house, a team's project. Not a label: a boundary.

- `compare()` **raises** if the two `Run`s have different tenants.
- `promote_baseline` **raises** if the run's tenant is not the one it is addressed with.
- The on-disk layout is `.digline/<tenant>/baselines/<suite>.json`, and tenant and suite
  names are validated as single path segments: `..` and `/` are refused.

The tenant is a **directory** and not only a field inside the file, because that way the
separation is enforced by the filesystem instead of being described by a document. A
software house with twelve customers must not be one typo away from reading one's history
as another's.

*Corrected 2026-09-26, after measuring what the layout enforces. The paragraph above says
the **separation** is enforced by the filesystem. What the filesystem enforces is
**addressing**, and the two are different claims: the directory makes filing or reading one
client's history as another's a **refused mistake**, not an impossible act. Everything the
paragraph's own justification asks for lives in that first claim, and it holds — a tenant
name is validated as one path segment, so `..` and `/` cannot climb out; a symlink leading
out of the store is refused; and `read_run` and `read_baseline` raise `TenantMismatchError`
when a document's declared tenant differs from the directory it was addressed through. The
typo is caught.*

*What the sentence claimed beyond that, and no longer does: **access**. digline creates a
tenant's directories with whatever mode the process has and never sets or inspects one; it
reads no uid, calls no `stat`, and checks no credential. The only explicit modes anywhere are
two `os.open` creation flags on a register append and a journal leg, and neither is read back
— the `O_EXCL` on the second is the resume race, not privacy. One OS user who can read one
tenant's directory can read them all, and in a single repository every tenant's committed
baselines share one history, so a clone brings all of them. **Separating access is the operator's
job** — one repository per client, filesystem permissions, or separate hosts — and the
per-tenant directory is what makes each of those possible without restructuring anything.
That is what the directory is worth, and it is worth stating as what it is rather than as a
guarantee nothing here provides.*

*Where the perimeter is enforced, named because "the filesystem" was the wrong answer: in
the **front ends**, where the suite picks the tenant and the flag only verifies it —
`_check_perimeter` in the CLI and the same check in the MCP server, under the sentence "the
suite decides; this flag only verifies"; and in **the operations that pair two runs**, where
`compare()`, `diff()` and replay each raise rather than return a number about two perimeters,
and promotion inherits the refusal from the `read_run` it begins with — §8 of this record says
so, and it is why the bullet above naming `promote_baseline` describes where the condition
holds rather than where it is written. **Not in the store's API**, which takes a tenant as a string by design
and answers for whichever one it is handed.*

*And the one place a front end of ours crosses it, named rather than left to be found:
`pytest-digline` takes `--digline-suite` repeatably, collects every suite's rows into one
session, and prints every headline under a single `digline` separator — and nothing there
compares the suites' tenants, while `headline()` names neither the tenant nor the suite. Two
clients' sentences can arrive one after the other, under one exit status, with nothing saying
which client each is about. Recorded here as **unruled**: a record that describes a perimeter
may not be silent about the one place its own front end walks through it, and whether that is
refused or declared acceptable is not decided in this note.*

*Two more places make the same claim and are owed the same correction, named here so that
correcting one does not leave the others reading as measured: `store/file_store.py`'s module
docstring — "the separation between perimeters is something the filesystem enforces rather
than something a document merely describes" — and [ADR 0011](0011-the-mcp-server.md) §8,
"`.digline/<tenant>/` puts the perimeter in the filesystem precisely so that it is not a field
in a document somebody could get wrong". Both are true of addressing and neither is corrected
by this note.*

*Corrected 2026-10-01 (#140). Both now say addressing, and so do three more that this list
did not name: `tests/test_store.py`'s module docstring, `ResultStore`'s class docstring in
`store/protocol.py`, and `examples/operator/journal.py`. "Two more places" was a count of
what one search found, not of the repository, and the last two were missed in two different
ways. `protocol.py` says *"the filesystem then enforces"*, which no pattern of the sweep
matched; `CONTRIBUTING.md`'s sweep bullet records it. `journal.py` was matched: replayed at
the commit that reported it (`6ef90d4`), ADR 0034 §13's sweep returns it for *enforced by
the filesystem*, and §13 lists three sites without it. Why it was dropped is not known.*

*The decision itself does not move. The tenant stays a directory, for the reason the
paragraph above gives. What changes is the claim made for it.*

Two runs from different perimeters produce numbers on the same scale: a wrong comparison
would be arithmetically valid and factually meaningless. It is the kind of mistake that is
never noticed, so it has to be made impossible.

`SCHEMA_VERSION` goes to 3: a file without a tenant cannot be placed in a perimeter, and
one without the redaction flag is indistinguishable from a complete document. Both must be
refused, not guessed.

### 1-bis. No sub-perimeter: the environment is a field, not a hierarchy

The tenant does **not** break down into sub-perimeters. Production, staging and acceptance
for the same customer live in the same perimeter, because the perimeter is a property **of
the data**: it is the same data, of the same owner, under the same contract. Treating
staging as a perimeter of its own would suggest its data belongs less to someone, and it
does not.

`Run.environment: str` is mandatory, non-empty, with no default, and **does not enter the
on-disk layout**: a suite has one baseline per tenant, not one per environment.

`compare()` reports it — `Comparison.environment` and `Comparison.baseline_environment` —
and constrains nothing. The reason is that **comparing staging against the production
baseline is the pre-release check**, that is, the thing the product exists for: making it
an error would have prevented the main use case in order to defend a symmetry nobody had
asked for. Reporting it serves the reader, who must be able to see what was compared with
what; enforcing it serves nobody.

No default, because an implicit `environment` is the premise of a comparison in which
nobody knows any more what they are looking at.

`SCHEMA_VERSION` goes to 4: a comparison that cannot say whether it read staging or
production is one nobody should act on.

### 2. The payload stays where it is born, the verdict travels

> **Extended by [ADR 0003](0003-artifacts-travel-only-when-the-suite-says-so.md)
> (2026-08-26):** a run also records the files that *are* the thing under test.
> They are neither verdict nor measurement, and they do not cross a boundary
> unless the suite declares `Disclosure(artifacts=True)`.

This is the rule that makes the three worlds compatible.

**The verdict** — name, `assertion_id`, status, score, threshold, tolerance, and the
metadata *measured by an assertion* — describes how a system behaved. It does not contain
the data it behaved on. It may cross a boundary.

**The payload** — the `reason`, and metadata not covered by a `Disclosure` — is, or
contains, what the system processed. It does not cross.

The `reason` is payload and not a label because **a judge quotes what it judges**: that is
its usefulness, and it is exactly what makes it unpublishable outside the perimeter.

**Redaction is a function on the value.** `redact(run, disclosure) -> Run` is the
primitive; `run_to_json(run, redacted=True)` is built on top, not the reverse. A redaction
living only in the serializer would be an opt-out that every future transport — the
Postgres store, an HTTP push, an export — would have to remember to switch on: the exact
shape of promptfoo's `#9968` defect, where the beacon fired anyway. With the primitive on
the value, any transport redacts first and serializes afterwards.

In the document the payload fields are **absent, not emptied**: not even the length of the
original survives. The document carries `"redacted": true` at the top level, and
`Run.redacted` travels with the value, so no reader can mistake a redacted run for a
complete one in which the judge was terse.

**The flag is verified, not believed.** `Run.__post_init__` refuses a run marked
`redacted` whose verdicts still carry a `reason`. Without the check, one could hand-build
a run that *declares* itself redacted with the contents intact, and the serializer would
omit the reasons on trust: the flag would announce a guarantee that nothing provides,
which is worse than no flag. It is the same family as the `status` that cannot contradict
its own threshold (ADR 0001).

The check covers the reasons and not the metadata: whether a metadata value should have
survived depends on the `Disclosure` that produced that run, and a `Run` does not carry it
along. Using `redact()`, the flag is correct by construction.

What survives is enough for `compare()`: **an end company can send a verdict without
sending its own data**, and the software house sees the regression.

### 3. `Disclosure` is asymmetric, and the asymmetry is the point

    Disclosure(score_metadata: frozenset[str], run_metadata: frozenset[str])

- `Score.metadata` is written **only by assertions**. Numbers and booleans travel on their
  own merit (`travels()`); strings only if the key is declared.
- `Run.metadata` is what an integration annotated from production. **Nothing travels by
  default, numbers included.**

The reason for the asymmetry: `0.01` written by `CostBudget` is a measurement; `1499.00`
copied from a customer's request is their data dressed up as a measurement. Both are
`float`, but only the first has a provenance one can trust. "Numbers pass" is true of the
producer, not of the type.

The mapper **has no route** to `Score.metadata`: an assertion writes its own metadata from
what it measured, and what the mapper brings in through `EvaluatorInputs.metadata` does
not get there. It is structural, not a convention.

The allowlist is declared **in the suite's code, never read from the data**: widening what
leaves a perimeter must be a change someone writes and a reviewer sees. The default is
empty, so whoever redacts without knowing the suite's policy discloses *less*, never more.

### 4. `Comparison` inherits the payload of its inputs, and that is correct

`compare()` works between a redacted run and a complete baseline: everything it reads
survives redaction. But the `Comparison` it returns **contains the verdicts it received**,
so it carries the payload of what it was given.

This is not a defect to fix. Inside the end company's perimeter — where world 3's report
is generated — the comparison *must* carry the `reason`, because that is what makes a
failure understandable and actionable. An always-redacted `Comparison` would make the
report useless exactly where it is needed.

The operational consequence, which stands as a rule: **a `Comparison` does not cross a
boundary.** What crosses is a redacted `Run`, and the comparison is redone on the other
side. Whoever writes a transport for `Comparison` is going down the wrong road.

### 5. The `case_id` is not payload, and there is no way to copy one

> **Amendment owed by [ADR 0023](0023-capture.md) (2026-09-28):** that record
> amends this section, and its header rules that the edit waits for its
> acceptance. It is proposed, so nothing here has moved yet. **What is owed is
> the bridge bullet's recipe and nothing else** — the structural half does not
> wait, and world 1 is untouched. *Consequences*, the bridge bullet, says where
> the drafted text is parked: it is **written**, dated 2026-09-16, on the
> unmerged `capture` branch.

The `case_id` has to cross the boundary: it is the key `compare()` pairs on, and without
it there is no comparison. So it cannot be payload.

It follows that it must never *contain* payload, and the guarantee is structural:

- **World 1.** The developer chooses the `case_id` and answers for it. It is their test
  data, chosen by them.
- **Production → repo bridge.** The id is **generated by digline** — date, sequence
  number, short hash of the *already redacted* response — and **there is no parameter to
  pass one in**. It is not that the application's identifier must not be copied: there is
  no way to copy it.

The difference between the two formulations is the whole decision. A rule that can be
skipped in a hurry will be skipped in a hurry; one that has no entry point does not need
to be remembered.

*__What exactly is owed, since the note at the top of this section says only that something
is.__ Added 2026-09-28, beside that note and not instead of it. **Owed:** the
**Production → repo bridge** bullet's recipe — *date, sequence number, short hash of the
already redacted response* — which [ADR 0023](0023-capture.md) §6 refuses on both real
histories and replaces with an id derived from the input. **Not owed, and not waiting:** the
structural half this section is named for. The id is generated by digline, there is no
parameter to pass one in, and **world 1 is untouched** — a developer still chooses their own
ids and answers for them. A reader who takes the note above as putting the whole section in
doubt has read it too widely, and the recipe is the only sentence in question.*

*__Why the pointer and not the edit.__ ADR 0023 is `proposed`, and its own status line rules
that what it amends is edited **at its acceptance and not when it lands**: an amendment
reading as in force while the record that makes it is undecided would be a ruling and not a
landing. So the drafted text stays where it was written — on `capture`, dated 2026-09-16 —
and this section says it is coming rather than pretending it is here. Before 2026-09-28 it
said neither, and **a section with no dated note reads as a section with nothing to
correct**, which was the one thing this one could not claim: §1 carries its correction, and
so does the bridge bullet of *Consequences*, corrected twice on its own account (2026-09-26,
and again 2026-09-27 on pseudonymisation). This was the only one of the three that read as
settled.*

*__Named and not counted, for the reason §8 of this record gives.__ Both notes above say **the
bridge bullet** where the first draft of each said *the second bullet*. It was second when
ADR 0023's *Amends* line named it that way, and ADR 0034 inserted a bullet above it at 16:29
on 2026-09-27 (`3aeb53d`), making it the third — without anybody touching the thing the
ordinal points at. **This record has already paid for that twice, in one section:** §8
stopped counting its conditions and started naming them — *"that is the argument for naming
conditions rather than counting them, made by the correction of a count"* — and §8 carries a
numbering note saying it is the eighth and not the sixth, because inserting §1-bis moved it.
An ordinal is a claim about the neighbours, and the neighbours are not yours.*

### 6. Production store: Postgres, and retention is mandatory

Production data does not live in the repository. The repository is the system of record
for the **verdict**; the production payload has a different volume, life cycle and owner.

**First implementation: Postgres**, inside the end company's perimeter. Decided now
because the decision informs the protocol, not because it has to be written now.
Reasons: it is the thing an end company already runs, it does not require a new service to
get approved, and it holds up under the per-case and per-time-window queries the report
needs. No dependency on a service run by us — not being able to exfiltrate is a selling
point only if it is true for paying customers too.

**Retention is mandatory, not freely configurable.** A production store without a declared
deletion policy is not compliant and digline must not allow creating one: the window is a
mandatory constructor parameter, not a setting with a generous default. An archive that
grows forever is an incident waiting to happen, and the convenient default is how you get
there.

*Amended 2026-09-27, by [ADR 0034](0034-the-store-outside-and-the-reference-that-names-nothing.md)
§1, at its acceptance. **The carve-out widens.*** This section put the **production stream**
outside the repository. It now also puts **offline runs against the end company's own
cases** there, because they have the same volume, life cycle and owner as the stream, which
is the line the first paragraph drew. So cases, runs, recorded responses, the journal and the
full reference live inside the end company's perimeter, addressed by the same key they have
today. The repository holds two things: the key, which links a commit to the reference it
was judged against, and a **projection** of that reference (ADR 0034 §2). Fixed decision 2's
reason is untouched: nothing goes in a home directory, nothing becomes global state on a
machine, and the layout is still `.digline/<tenant>/`. What changes is the perimeter that
directory sits in.

*Two things in this section do not extend to the widened part, so that nobody reads them as
inherited:*
- **Postgres** is this section's choice for the stream. It says nothing about the form of
  the offline store, and ADR 0034 leaves files or a database open.
- **Mandatory retention** belongs to a store whose purpose is a stream. A reference that can
  expire is a reference that can vanish from under a gate, so the offline store takes
  ADR 0034 §14's contract for forgetting instead.

### 7. A single way in: `EvaluatorInputs` via a mapper

Whatever is evaluated — an offline matrix, a production stream, a single response —
enters the core **only** as `EvaluatorInputs`, built by a mapper. The core does not know
what a trace, a matrix or a stream is.

It is the boundary that makes the three worlds the same engine, and it has to be defended:
if one day the driver needed to know `EvaluatorInputs` in a way other than "a mapper hands
it to me", that is the sign the boundary has broken.

**How production data reaches the mapper — in-process or over OTLP — is deferred to a
later ADR.** It is a choice with heavy operational consequences for the end company (an
OTLP receiver is one more service to run; in-process is a dependency inside their
application) and must not be taken by inertia. All that is recorded here is that the core
does not prejudge it.

### 8. Promotion's conditions

`promote_baseline` refuses whenever the run it is handed is not a reference. The
conditions are collected here because they are one rule seen from several sides:
**a baseline is an approved reference**, and each condition prevents approving something
that is not one. Each exists because violating it produces a comparison that runs anyway
and returns numbers anyway — the worst way to be wrong.

*Amended 2026-09-22. This section said **three** — in its heading, and twice in the
paragraph above — while `promote_baseline` refused on more than three. Conditions were
added after this record was written, each by the record that decided it, and none came
back to say so here. Every one of them is now named below, and the count is gone from the
heading and from the paragraph rather than corrected: a section that lists its conditions
underneath itself does not need to say how many, and saying so is what let this one be
wrong in its own title for two releases. (ADR 0012 §3 and `digline.wire.contract` state
the general form of that rule — no total, and no enumeration where the thing can be found
by looking. A record's conditions cannot be found by looking, which is why they are
enumerated here; what must not be written beside the enumeration is a number.)*

*Amended again the same day, and the second pass is the instructive one: the first one
corrected three to **five**, named five, and still missed one. `unreconciled` (6 below)
was the most recently added and the easiest to miss, because it is the only condition that
does **not** bring an exception type of its own — it raises `ErroredRunError`, like 3 does.
Anyone counting exception types finds five and stops. That is the argument for naming
conditions rather than counting them, made by the correction of a count.*

*Where each is enforced, since it is not all one function, and three places because they
answer three different questions (`store/promotion.py`'s docstring gives the reasons).
**1 and 7 belong to the reading**: a run addressed through the wrong tenant, or one whose
document declares another suite, is refused by `read_run`, which `promote_baseline` calls
first, so the two hold on promotion without appearing in it. **2 to 6 answer from the
document alone**: they are `refusals_for`, which returns them in the order 2, 4, 6, 3, 5
and which every store calls rather than restating them. **8 belongs to the write**: each
backend checks it beside its own write, last. They are all listed here because they are
conditions on promoting, and a reader who went looking for all of them in
`promote_baseline` would not find them.*

*Corrected 2026-10-05 (#437), and the error was about **where**, not only how many. The
paragraph above said 2 to 6 "are raised by `promote_baseline` itself" and named 1 as the
one exception. That was false from 2026-09-28, when `a5ee760` moved 2 to 6 into
`refusals_for`. And 1 had not been the only exception since 2026-09-24: 7 is a second
refusal of `read_run`, and 8 is checked in each backend. 7 and 8 were also missing from
the list below. Both arrived on 2026-09-24, and neither came back to add itself here. That
is the cause the first amendment of 2026-09-22 named and left standing: it took the count
out of the heading, and nothing held the list to the code. Since this correction,
`tests/test_promotion_list.py` holds the list below equal, number for number and type for
type, to the one in `ResultStore.promote_baseline`'s docstring. That copy sits beside the
code, and it is the one 7 and 8 did reach. The test also requires every type in
`PromotionRefusal`, and the type `refusal_for_a_moved_baseline` returns, to appear in the
list. What the test cannot see is stated in its own docstring.*

1. **`TenantMismatchError`** — the run's tenant does not match the one it is addressed
   with. A perimeter is not crossed because of a wrong copy (§1).
2. **`ConfigMismatchError`** — the `config_hash` does not match the configuration in
   force. Otherwise the baseline would record scores obtained under thresholds different
   from the current ones (ADR 0001 §5).
3. **`ErroredRunError`** — one or more verdicts are in `error`, and the exception lists
   the cases. An error means the suite **could not judge**: there is nothing to measure a
   future run against. Promoting it would freeze a permanent red row that no reader could
   tell apart from a new failure — and the reader, in world 3, does not have the code to
   work it out for themselves.

   The remedy for an unstable case is to fix it or take it out of the suite, not to
   enshrine it. It is the natural sequel to ADR 0001's rule that `error` is not green and
   is not a regression: it is not a reference either.
   *Read as written since 2026-10-02 (#374). "One or more verdicts" was implemented as
   case verdicts only, so a run whose only error was a run-level figure — an aggregate
   over an empty denominator, say — was promoted. A run-level verdict is a verdict: the
   refusal now names it beside the cases, as a run-level check. The exit code still
   counts cases only, which is ADR 0010 §8's ruling and is not changed here.*

4. **`ReplayedRunError`** — the run declares `rejudged_from`. The answers must have been
   *measured*, or the interval promoted with them was measured without the target in it.
   *Added by [ADR 0015](0015-the-recorded-output-and-the-declared-re-judge.md) §7, which
   calls it "the fourth condition on promotion" and sits it "with the other three" — while
   its own `Assumes:` line, 255 lines up in the same file, still cited this section as
   "promotion has three conditions".*
5. **`UncalibratedRunError`** — a calibration case scored outside its declared band. The
   numbers exist and are not measurements.
   *Added by [ADR 0024](0024-the-judge-as-an-instrument.md) §4.5, which calls it "the
   fifth condition, beside tenant, configuration, errored".*

6. **`ErroredRunError`, for a run that does not reconcile** — the run recorded a gap
   between what its suite asked and what came back, so what it measured is not known. It
   is raised **before** 3, because it is the stronger statement about the same document:
   3 says a verdict errored, this says the record is incomplete, and the refusal names the
   case and the check rather than only the case.
   *Added by [ADR 0027](0027-the-run-reconciles.md) §3, which states the refusal and the
   reason — "a reference nobody can say that of is no reference" — and did not come back
   to add itself here. It shares an exception type with 3, which is why the amendment
   above found five conditions by counting types and missed this one.*

7. **`SuiteMismatchError`** — the stored run declares a suite other than the one it was
   addressed through. A document that contradicts itself is refused, not filed where it
   claims to belong. Raised by `read_run`, beside 1.
   *Added on 2026-09-24 by `b3735a5`, shipped in 0.19.2, with no record of its own. It
   reached `ResultStore.promote_baseline`'s list and not this one. Brought here on
   2026-10-05 (#437).*
8. **`BaselineMovedError`** — the baseline present now is not the one the run was compared
   against, which the person promoting names. Promoting would replace a reference nobody
   compared the run against: the lost update. Checked **last**, because every refusal
   above is about the run and holds whatever the reference, and beside the write, which
   is as narrow as the window gets without a lock.
   *Added by [ADR 0031](0031-the-reference-promote-replaces.md), accepted 2026-09-24
   and shipped in 0.20.0: §1 for the key the person supplies, §4 for the type. Like 6,
   it did not come back to add itself here. Brought here on 2026-10-05 (#437).*
9. **`CrossingRefusedError`** — the run records an artifact under `.digline` or `.git`,
   in any case and at any depth, or one keyed outside the perimeter. A baseline carries
   every artifact's full text into `baselines/`, which is versioned, so promotion is an
   exit and this holds **whatever the `Disclosure`**. Answered by `refusals_for`, after 5.
   *Added by [ADR 0042](0042-the-two-boundaries-of-an-artifact.md) §3, and brought here
   by the change that implements it.*

*Numbering note: this section is the eighth, not the sixth, because inserting §1-bis
shifted the numbering after the initial draft. §6 remains the `case_id`.*

### 9. The suite is compiled from source, and git is read before importing it

The suite is Python code, not data (§7 and the decision on the configuration surface: a
`Judge` is an object, a `Target` a function, a `Disclosure` is declared in code by
construction). Two constraints on how the CLI loads it follow, **non-negotiable**, both of
which emerged running the CLI on a real repository and neither of which is visible
in-process.

**The suite is compiled from source, without reading or writing bytecode.** It does not go
through the ordinary import machinery.

1. *Writing* bytecode leaves `__pycache__` in the user's repository, and a repository with
   new untracked files is **dirty**: our own import would have made every run declare
   itself non-reproducible. A defect digline attributed to the user and was its own.
2. *Reading* bytecode can execute a stale suite. Python's freshness check is
   `(mtime, size)` with one-second granularity: a file modified within the same second and
   at the same length is served from the cache. **It is the only defect met in the whole
   project that could have let a test meant to fail pass** — and for a tool whose premise
   is reproducibility, the only acceptable answer to "what was executed" is "what is on
   disk".

**The suite's directory goes on `sys.path` before execution.** A suite imports the
application it evaluates: `from brief import judge` is the normal case, not the exception.
Without this, the first real suite fails on its first line with `ModuleNotFoundError`, and
the tool looks broken because it is. It is what `python file.py` and pytest from its own
rootdir do. It holds **only** for a spec that is a path: a `package.module:attr` is
already importable, and widening the path for it would mean reaching into the caller's
environment for no reason. The insertion is guarded against duplicates.

**What resolves inside the suite's directory is also read from source**, through a
`FileFinder` built with a `SourceOnlyLoader` — a derived `SourceFileLoader` that overrides
`get_code` to always compile from disk — registered in `sys.path_hooks` and in
`sys.path_importer_cache` **for that one directory only**. On top of that,
`sys.dont_write_bytecode` is true for the whole CLI process: we leave no debris.

The previous constraint covered the suite file; it did not cover what the suite imports,
that is, **the user's application — the only thing that really changes between two runs**.
The concrete case, reproduced and now in `tests/test_cli.py`: a `brief.py` next to the
suite, modified at the same length and within the same second, with a `__pycache__`
already left by an ordinary `python -c "import brief"`. The resulting `.pyc` looked fresh
to Python's `(mtime, size)` check, the application ran in its old version, and `compare`
answered **"nothing got worse"** while something had. The test was verified by disabling
the finder: without it, it fails.

The scope is a single directory, deliberately. A loader for every module would slow down
every import in order to protect files that do not change during an evaluation — stdlib
and site-packages — and would reach far beyond what this tool has the right to alter. Like
the other two, it holds only for a spec that is a path.

**Git status is read before any import of ours.** Otherwise the answer would depend on
what our loading had just done rather than on the state the user left the repository in.
The `-dirty` marker describes the user, not us.

A corollary recorded here because it is of the same family: `created_at` keeps the
microseconds. Truncating it to the second was an aesthetic choice, until listing the runs
showed the cost — a run's key derives from the timestamp and the configuration, so two
runs in the same second on the same suite produced the same key and **the second silently
replaced the first**.

### 10. The aggregate, and the one number you improve by doing less

`Run.aggregate` carries verdicts **on the run** — precision, recall, accuracy — alongside
those on the cases. They are `Verdict`s like any other: mandatory threshold, hence a gate
by construction, and `compare()` says whether they regressed. No new mechanism.

The reason is measured, not aesthetic. Four executions of one unchanged prompt agreed with
the human marking on **14, 14, 15, 15 cases out of 21**, while individual cases jumped by
three votes. `15/21 − 14/21 = 0.0476`: within a tolerance of one case. **The aggregate is
the gate, the per-case is the diagnosis.**

Three constraints, each for a real path to error:

1. **`over` names exactly one assertion.** A missing name aggregates over an empty set; an
   ambiguous name — two `contains` in the same suite are the ordinary case, and it is the
   reason `compare()` pairs by identity and not by name — aggregates over whichever comes
   first. They are the same mistake seen from two sides, and `Suite` refuses both, listing
   the candidates.
2. **Empty denominator → `error`.** If the system kept nothing, precision is not `1.0`: it
   is undefined. `1.0` would be the most dangerous possible answer.
3. **Mandatory labels** if an aggregate counts a confusion matrix. No implicit
   denominators.

**The note that must outlive this document.** `suspended_excluded` is the only number in
the product that **can be improved by removing work instead of doing it better**:
suspending a failing case raises the ratio without anyone lying. We do not forbid it — an
unstable case should be suspended, that is the reason suspension exists — but the two
exclusions travel *next to* the figure wherever it goes: in the `reason`, in the metadata,
in the report's table. **That number is never read on its own.**

**And where to put the threshold.** An aggregate is a contract about **present
behaviour**, not a target: the threshold is set where the system is — measured — and the
comparison protects against getting worse. A threshold set where you *wish* you were makes
the gate red by construction, hence useless for CI and soon ignored by whoever reads it.
With the numbers from the brief: measured precision ≈ 0.62, hence a threshold of **0.60**,
not 0.70. You reach 0.70 by improving the system and then raising the threshold, which is
a change to the configuration — visible in `config_hash` and in a pull request.

`SCHEMA_VERSION` goes to 6.

## Consequences

- `compare()` and `promote_baseline` have one more error path, and it is right that it is
  an exception and not a return value: crossing a perimeter is not an outcome.
- **A committed reference may be a projection of one.** *Added 2026-09-27, by
  [ADR 0034](0034-the-store-outside-and-the-reference-that-names-nothing.md) §2, at its
  acceptance.* Where the store lives inside the end company's perimeter (§6 as amended),
  the promotion happens there. The file the repository commits is then derived from the
  reference `promote_baseline` returned: promote first, then project. **Every condition in
  §8 is unchanged.** None is re-implemented and none is relaxed, because the projection is
  made from a promotion that has already passed them. What §8 approves is still the
  reference, and the committed file is its derivative.
- The production → repo bridge is the point where anonymization is **mandatory**: it is
  the only place where payload and verdict touch, and the only one where a mistake is
  irreversible — once committed, it is in git's history.

  *Corrected 2026-09-26: the requirement as written above cannot be met, and this note says
  so and stops there. **Anonymising the input destroys the case.** The input is what a judge
  judges, so a case whose input has been anonymised is not the same case weakened — it is a
  different case, and the verdict recorded against it answers a question nobody asked. The
  choice the material leaves is the text or no case, which is not a choice "mandatory
  anonymization" admits. The second half of the bullet is untouched and remains true: this is
  the one place payload and verdict touch, and once committed a mistake is in git's history.
  What is wrong is only the requirement, and it has been wrong since this record was
  accepted.*

  *__What this note does not do, deliberately.__ It does not say what should replace the
  requirement. [ADR 0023](0023-capture.md) §8 has a remedy — the regime becomes declared
  rather than mandatory — and taking it here would be that record's amendment made by another
  hand while it is still proposed, which is what its own header refuses: an amendment reading
  as in force while the record that makes it is undecided would be a ruling and not a landing.
  So the problem is stated and the remedy is left where it was decided, unaccepted.*

  *__Why now rather than at 0023's acceptance.__ ADR 0023 promised two edits to this record —
  §5's generated-id recipe and this bullet. The first was **written**: it sits, dated
  2026-09-16, on the unmerged `capture` branch, and was deliberately not carried when 0023
  landed on `main` as proposed. **This one was never drafted at all**, on any branch. So the
  two are not in the same state, and only one of them is parked: waiting for 0023 protects a
  text that exists, and for this bullet it protected nothing while a fixed-section record went
  on stating a requirement its own successor had already shown could not be met. A record that
  cannot be met should say so in its own voice, which needs no other record's status.*

  *__Corrected again 2026-09-27: what replaces the requirement.__ The first note stated the
  problem and left the remedy to ADR 0023, which is still proposed. The remedy does not need
  that record. It stands on the ground the first note already stands on: the input is what a
  judge judges. Anybody can check that without reading ADR 0023, and so this record now says
  the remedy in its own voice.*

  *__What the bullet said:__ the production → repo bridge is the point where anonymization is
  mandatory.*

  *__What it says now:__ the bridge's regime is **pseudonymisation, with the mapping held by
  the data owner**.*
  - *What the bridge writes into the repository carries structural identifiers and no text,
    so it identifies nobody on its own.*
  - *The mapping from an identifier back to its case exists, is kept separately from what is
    committed, and is held by the end company inside its own perimeter.*

  *__Why not anonymisation:__ anonymisation means that no such mapping exists anywhere. A case
  cut from its link and stripped of its text is not a case, which is the first note's point.*

  ***Pseudonymised data is still personal data.** This does not take data-protection law off
  the bridge, and nothing here claims it does. What it buys is narrower, and it is the whole
  claim: the committed record alone identifies nobody.*

  *__What still stands:__ the rest of the bullet. This is the one place payload and verdict
  touch, and once committed a mistake is in git's history. Under this regime that mistake has
  a sharper description: any string in the committed record that is not a structural
  identifier.*

  *__What this note supersedes:__ the paragraph "What this note does not do, deliberately"
  above, which left the requirement with no replacement until ADR 0023 was accepted. It is
  kept, because it was right on 2026-09-26, and a reader who cites it should meet this.*

  *__A disagreement this leaves open, named here and not resolved.__ ADR 0023 is proposed.
  Its* Amends *line says this bullet "becomes a declared regime", and its* Touches *line says
  `CLAUDE.md`'s `bridge/` line follows its §8. From today this bullet says something else, so
  the two records visibly disagree. Rewriting ADR 0023's header waits for that record's
  acceptance, which is where its own status line says its amendments are decided. Until then,
  where they disagree about this bullet, this record is in force: ADR 0023 is proposed, and by
  its own rule what it amends waits for its acceptance.*
- Three planned packages, in the order they will be built after the offline driver:
  `digline.report` (the document for world 3), `digline.production` (the Postgres store
  with mandatory retention), `digline.bridge` (production → repo, with anonymization and a
  generated `case_id`).

  *Corrected 2026-09-27. "With anonymization" is now: **with pseudonymisation, the mapping held
  by the data owner**. Anonymization cannot be met, because the input is what a judge judges.
  Pseudonymised data is still personal data. The Consequences bullet above gives the
  correction in full; this is the same correction, at the second place the word was
  written.*

  *Owed to ADR 0023, 2026-10-01. "A generated `case_id`" is superseded in substance by
  [ADR 0023](0023-capture.md) §6, which amends this record's §5 with the identifier's
  recipe. ADR 0023 is proposed, and by its own rule what it amends waits for its
  acceptance, so these words stand until then and are rewritten when it is accepted.*
- The build order is deliberate: **nothing online before the report.** The report is what
  world 3 sees, and it is the only one of the three artifacts that today exists in none of
  the audited competitors.

## Not decided here

- The production → mapper transport (in-process or OTLP), as above.
- The form of the report: whether it is HTML, PDF or both, and how much of the
  `Comparison` a non-technical reader should see.
- Which `environment` values are canonical. The string is free on purpose: end companies
  name their own environments as they like, and imposing an enumeration would have
  produced an `other` that half the real world falls into.
- **Whether the unreconciled condition earns an exception type of its own.** Conditions 3
  and 6 of §8 both raise `ErroredRunError`, so a caller that catches it cannot tell which
  of the two fired: *a verdict errored* and *the record is incomplete* arrive under one
  name, and they ask for different things — the first says re-run or fix the case, the
  second says the run does not know what it measured. The refusal messages differ and name
  the case and the check, so a person reading stderr can tell; a program catching the type
  cannot. **Two facts under one name**, in the exception hierarchy this time. Recorded as
  a finding rather than fixed, because a new exception type is a change to what every caller may catch — it
  belongs to whoever decides the store's error surface, not to a cleanup, and the
  `TRANSLATED` table in `digline-mcp` would move with it. (Found 2026-09-22, while
  correcting §8's count for the second time — the shared type is *why* the count was wrong:
  five is what you get by counting exception types.)
