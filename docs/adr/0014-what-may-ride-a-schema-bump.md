# ADR 0014 — What may ride a schema bump

- Status: accepted — the text first, the implementation written against it on
  `release-schema`, the way
  [ADR 0006](0006-repeated-samples-and-the-noise-floor.md),
  [ADR 0007](0007-the-declarative-suite-format.md),
  [ADR 0008](0008-the-two-run-report.md),
  [ADR 0011](0011-the-mcp-server.md),
  [ADR 0012](0012-the-reading.md) and
  [ADR 0013](0013-the-pytest-plugin.md) were
- Date: 2026-09-11
- Assumes: [ADR 0002](0002-three-worlds-and-where-the-data-lives.md) §8
  (promotion has three conditions, and one of them is the configuration);
  [ADR 0003](0003-artifacts-travel-only-when-the-suite-says-so.md) §3
  (artifacts are not part of `config_hash`);
  [ADR 0005](0005-the-configuration-of-the-system-under-test.md) §3 (beside the
  hash and not inside it), §7 (keys added, nothing re-promoted);
  [ADR 0006](0006-repeated-samples-and-the-noise-floor.md) §11 (a migration
  that derives rather than invents)
- Carries: [ADR 0015](0015-the-recorded-output-and-the-declared-re-judge.md)
  and [ADR 0016](0016-the-canary-case.md), which are the two passengers this
  bump was opened for
- Turns into surface: [`AGENTS.md`](../../AGENTS.md) §8 (when upgrading digline
  itself, migrate before you promote)
- Touches: nothing in `CLAUDE.md`'s *fixed* section. Decision 3 and decision 9
  are reaffirmed by §1's third condition rather than amended

## Context

`SCHEMA_VERSION` has moved eight times and every move was reasoned about in a
code comment, a migration docstring and a test's opening paragraph. Those are
good places to record *what* a version added; none of them is a place to record
**what a version is allowed to add**, and by 0.10.0 that question has started to
decide releases.

It decides them because a bump is not one line. `run_from_dict` refuses any
`schema_version` that is not exactly the one it knows, in both directions, so
the day the constant moves every stored document in the world is unreadable
until it is migrated — including the nine baselines committed under
`examples/*/.digline/`, which `tests/test_example_caps.py` requires to be at
exactly the version this tree writes, and whose dependency caps must admit a
release that can read them. The gate globs the working tree rather than the
index, so a run artifact left beside a baseline is checked too, and fails the
same way. The bump is therefore a ritual with a release in the
middle of it, and the examples are unresolvable for as long as the ritual is
unfinished.

Something that expensive should be paid for once and carry as much as it
honestly can. 0.10.0 carries three things: the version that wrote the document
(§3 here), the recorded output of ADR 0015, and the canary flag of ADR 0016.
Three unrelated fields riding one bump is either good economics or the beginning
of a schema that accumulates whatever was convenient, and the difference between
those two is a rule. §1 is that rule.

The second reason this record exists is smaller and sharper. Until now 9 was the
highest schema ever written, so no released digline had ever met a **newer**
document. 0.10.0 is the first release that will produce one, and §5 is about
what the version behind it does when it does.

## Decision

### 1. The passenger rule

A field may ride a schema bump only if all three of these hold. They are checked
in the ADR that proposes the field, and the ADR says so in its own words:

1. **It leaves `config_hash` untouched.** The hash is the identity of the
   *suite configuration* — assertion identities with their thresholds and
   tolerances, `samples`, `min_agreement`, the aggregates — and nothing else has
   ever been in it. A field that entered it would unpromote every baseline on
   the day of the release, rename every stored run (the key is
   `{slug}-{config_hash}`), and print *the rules changed* over a run where no
   rule changed.
2. **It migrates additively, without inventing.** There has to be a value the
   old document already justifies: `false` for a flag that did not exist,
   `{}` for a record nobody kept, a derivation from something already written
   (ADR 0006 §11). A field whose honest migrated value is a guess does not ride;
   it goes in `_NON_ADDITIVE` and costs its holder a decision, which is what
   that table is for.
3. **It does not widen what travels.** A new field is either a measurement that
   crosses on its own merit, or it is payload and `redact()` drops it and
   `digline.wire` never learns its name. There is no third answer, and "we will
   decide at the boundary later" is the answer that ships the leak.

The three passengers of schema 10 pass for three different reasons, and stating
them here is the point of having the rule:

| passenger | 1 — the hash | 2 — the migration | 3 — the boundary |
|---|---|---|---|
| `digline_version` (§3) | the identity of the *tool*, and `Suite.config_hash()` never sees a run | `""`, meaning **not recorded** | a fact about the software house's own instrument; travels in clear |
| the recorded output (ADR 0015) | a recording decision, and `Suite.disclosure` has never been in the hash either | absent — last month's answers are gone | payload, and **no `Disclosure` releases it** |
| `canary` (ADR 0016) | case data, and cases are deliberately outside | `false` — a case that predates the idea was not one | a boolean the author wrote; travels |
| `promoted_at` (§3) | a fact about the *promotion*, and the hash is the identity of the suite | absent — a baseline promoted before it existed recorded no time, and inventing one would date a signature nobody dated | a timestamp of our own process, like `digline_version`; travels |

A fourth passenger boarded late, from a read-only analysis of the scout's
history: `promote_baseline` overwrote the reference with the *run's*
`created_at`, so the human signature had no time of its own. It passes all three
conditions, so it rides — and §3 is where it is written down, beside the other
field that describes the document rather than the measurement.

One consequence of the first column is worth saying out loud rather than
discovering: marking a case `canary` **does** change every aggregate's value,
because its denominators lose that case. That arrives as a delta judged against
its tolerance, exactly as adding or removing a case does today. It is not a
configuration change, and reporting it as one would be the report describing an
edit to the case file as an edit to the rules.

### 2. Schema 10, and the step that invents nothing

One entry joins `_STEPS`, `9 -> 10`, and it is called `_add_schema_ten` because
it is the first bump no single field can name. It is also the first step that
**writes nothing**, and that is the shape of the three defaults rather than an
omission:

- `digline_version` → absent, and absent is the only honest value. **Never the
  migrating version's own:** a document rewritten by 0.10.0 was not produced by
  0.10.0, and stamping it would be the invention `_add_configs` already refuses
  about the model that answered.
- `responses` → absent. A run from last month recorded no answers and none are
  recoverable.
- `canary` → absent, which the document already reads as *not a canary*: the
  flag is written only when true, so a case that predates the idea of being one
  is not one without a key saying so.
- `promoted_at` → absent, which is *not recorded* and never a date. A baseline
  promoted last month was promoted at a time nobody wrote down, and the one
  thing a migration must not do is put a plausible date on a human signature.

Every key the step could add would therefore mean exactly what its absence
already means, and adding them would churn every committed baseline in the world
to say nothing. The step still has to **exist**: a version with no entry in
`_STEPS` is one whose bump was not additive, and that statement about 9 would be
false. `_NON_ADDITIVE` gains no row, and no document is refused here.

**Migration stays a rewrite, not a read.** `digline migrate` rewrites files in
place after re-reading them with the current reader; reads refuse. Migrate-on-
read has been proposed at every bump and is rejected again here for a reason
that has only got stronger: `<tenant>/baselines/` is **committed**, and a
`compare` that silently rewrote a git-tracked file would make the bytes of the
reference depend on who last looked at it. A comparison that edits its own
reference is not a comparison.

### 3. `digline_version`: the document says what wrote it

`Run.digline_version: str = ""`, at the top level of the document, beside
`schema_version` — the document saying what shape it is, then the document
saying what wrote it.

**Not in `Run.metadata`,** which is the obvious cheap place and the wrong one.
`metadata` is payload-governed: nothing in it crosses a boundary unless the
suite's `Disclosure` names the key, so a version recorded there would vanish at
exactly the boundary where *which digline wrote this* is most worth knowing, and
it would collide with a key the user chose.

**Not a configuration either.** `target_config` describes the system under test
and `judge_config` the instrument that graded; digline is neither. It is the
ruler, not the thing measured, and the document header is where a ruler signs.

`execute()` stamps it from `digline.__version__`, beside `created_at` and
`git_commit` and for the same reason those are passed in: the driver produces
the document, and what the document claims about its own provenance has one
author. `""` means *not recorded* — a migrated file, a `Run` built by hand in a
test, a library caller who built one directly — and it is never read as
"version zero".

It survives `redact()`. Everything in the field is a fact about the software
house's own tooling, and a redacted document that could not say which digline
wrote it would be harder to support for no gain in secrecy.

**And `promoted_at`, by the same rule.** `promote_baseline` writes the run
document as the reference, and until now that document carried one time:
`created_at`, which is when the run was **measured**. A promotion happens once
somebody has read the run — commonly days later, which is the whole of
`AGENTS.md` §2 — and the reference could not say when. So the baseline gains
`promoted_at`, stamped at write time, absent where it was not recorded.

Minimal, and deliberately so: **one field**. Not a sequence, not a list of past
promotions, not who promoted it. A history of the reference is a ledger, and a
ledger is a decision with its own retention question, its own boundary question
— a name is payload in a way a timestamp is not — and its own reason to exist.
This field answers one question that has no answer today; the ledger can be
written when something needs one.

It is **passed in, not read** — `promote_baseline(..., promoted_at=…)`,
mandatory and keyword-only. The store may not read the clock: `digline.host` and
the front ends are the layers allowed to, which is why `created_at` is passed
into `execute()` and why `utc_now_iso()` lives in the store as something callers
use rather than something the store calls. Mandatory rather than defaulted
because a default would make *not recorded* the ordinary outcome, which is the
gap the field exists to close; empty stays legal and means exactly that. It is a
`ResultStore` protocol change, which is the one thing this passenger costs beyond
the bump itself.

Two readers, because a field nothing reads is a field that drifts: the
comparison's header names it beside the reference it belongs to — *Reference
approved · 2026-09-11T09:14:02+00:00* — and `run_document` carries it, so
`get_baseline` over MCP can answer the same question. It is not a `Comparison`
outcome and gates nothing: when a reference was approved is a fact about the
process, not about whether anything got worse.

### 4. The installed-behind warning, and the trap inside it

The trigger is **newer**, not different:

    release(document.digline_version) > release(installed)   ->   warn
    anything else, or an empty value                         ->   silence

Two things about that line are worth the record.

**It is not the schema check wearing another hat.** If the schema moved, the
reader already refused and named the file. This warning covers the case the
refusal cannot see: *same schema, newer writer* — 0.11 writes schema 10, you run
0.10, the document parses, and fields written under rules you do not have are
read by rules you do. That is the only case it exists for, and it is why it is a
warning: never an exit code, never a refusal. The exit codes are the contract
(`AGENTS.md` §6) and a tooling mismatch is not a verdict on a suite.

**String comparison is wrong here and would look right for a year.**
`"0.10.0" < "0.9.0"` lexically, so the first release after this one would
silently stop warning. The comparison is a tuple over the leading numeric
release segment, written once as a pure function beside the document, with a
failing case on exactly that pair. `packaging` is not a runtime dependency of
digline and does not become one for this: digline has one runtime dependency and
this is not where it takes a second.

Where it surfaces: the *fact* is computed in `digline.wire`, so `--json` and MCP
carry it as a field and the CLI prints it to stderr, beside the note the listing
already writes there. `OUTPUT_VERSION` stays at `1` — an added key breaks no
consumer, which is the rule that comment already states.

### 5. The refusal is symmetric; the advice was not

`run_from_dict` refuses in both directions and always did. What only exists in
one direction is the sentence the CLI prints after a scan:

    ignored: 1 run(s) at schema 10
    run `digline migrate` to bring them up to date

Told to a digline that is *behind*, that advice is wrong: nothing migrates a
document backwards, and `upgrade_document` says so correctly — "Upgrade digline
instead" — but the listing never reaches it. The line was written when 9 was the
ceiling of the world, so it had never been pointed the other way.

0.10.0 fixes it where it can: the listing compares the counted version with its
own and prints the sentence that matches the direction. What it cannot fix is
the reader who is still on 0.9.0 and meets a schema 10 file, because that
sentence is printed by their binary. So the release notes say it in words, and
this section is why that paragraph exists rather than being tidied away as
release-day noise.

### 6. What the bump costs downstream, in order

The ritual, because it is red until it is finished and the order is not
negotiable:

1. `pyproject.toml` → the version that will carry the schema.
   `test_the_schema_this_workspace_writes_belongs_to_a_release` fails the moment
   `SCHEMA_VERSION` moves while the tree still names the last release.
2. A row in `RELEASED` in `tests/test_example_caps.py` — `"0.10.0": 10`.
3. `digline migrate` over every document the gate can see under
   `examples/*/.digline/` — the nine committed baselines, and any run artifact
   sitting in the tree beside them — so all of them are at the version this tree
   writes.
4. Every example's cap raised to admit that release.
5. The examples' rendered report pages regenerated, in the established order:
   commit the example first, render, then commit the report on top.
6. The window, stated rather than hidden: between the bump and the release
   reaching the index, a reader cannot resolve the examples at all. That is what
   the caps gate says out loud, correctly, once per example.

The plugin floors gate is **name**-based, not schema-based, so a bump forces no
plugin release: `pytest-digline`'s `digline>=0.9.0` and `digline-mcp`'s
`digline>=0.6.0` stay true statements about the names those packages import.

## Consequences

**The next bump has a checklist and a rule, and both are citable.** The question
at the top of every future release — "can this field ride?" — has three
conditions and a table to fill in, rather than an argument re-had from memory.

**A field that fails condition 2 now has a visible price.** It does not ride;
it goes to `_NON_ADDITIVE` and costs every holder of old runs a decision. That
is the correct price and it was always the price — what changes is that it is
quoted before the code is written rather than discovered by the person whose
baselines stopped being readable.

**`digline_version` makes support answerable.** "Which digline wrote this
document" has been unanswerable from the document since the first release, and
every support question about a strange file began by asking the user to
remember.

**Three passengers make this bump cheap and the next one expensive.** Nothing
here reserves a field for later use, and a reserved field nothing writes would
fail condition 2 by being a promise instead of a value. The next schema-shaped
idea waits for the next bump, and this section is the reminder that waiting is
the intended behaviour.

## Alternatives considered

**Migrate on read.** Rejected in §2: the baseline is a committed file, and a
comparison that rewrites its own reference is not one. The secondary reason is
that the store would then have no single answer to "what version are these
files at", which is precisely the question `digline list` exists to answer.

**`digline_version` in `Run.metadata`.** Rejected in §3. Payload-governed,
collides with the user's keys, and absent at the boundary where it matters.

**A `written_by` object with the version, the Python version and the platform.**
Rejected: two of the three are the machine's business and none of the three
except the version has ever answered a support question. A field that is a bag
grows by accretion, and every element of it then has to be argued about at the
boundary.

**Warning on any mismatch rather than on newer-only.** Rejected: a document
written by an *older* digline is the ordinary case — it is what every migrated
store is full of — and a warning that fires on the ordinary case is one the
reader learns to skip, taking the rare one with it.

**Bumping `OUTPUT_VERSION` alongside `SCHEMA_VERSION`.** Rejected, and the
comment on `OUTPUT_VERSION` already argues it: two contracts, two lifetimes. A
consumer of `compare --json` sees added keys and no byte of change to what it
already parses.

## Test plan

Beyond a failing case for every new rule, which the conventions already require:

**The step invents nothing.** A schema 9 fixture — one with sampled verdicts,
one redacted, one with artifacts — migrates to 10 and is asserted to carry
`digline_version == ""`, no responses, and `canary` false on every case. The
version assertion is explicit: the migrating build's own version must not appear
anywhere in the output document.

**Round trip at 10.** A run built with all three fields serializes, parses back
and compares equal, and a document with none of them parses to the same defaults
the migration produces — so a migrated file and a freshly written one are
indistinguishable where they should be.

**The hash did not move.** A suite's `config_hash()` is asserted byte-identical
across the bump for every example suite in the repository, and a schema 9
baseline migrated to 10 is asserted to promote against the current
configuration without re-promotion. This is the test that makes §1's first
condition real rather than intended.

**The promotion stamps what it was given.** A promoted baseline carries the
caller's `promoted_at` and a `created_at` that is still the run's; a migrated
schema 9 baseline carries none; and the comparison's header shows it in both
locales. The store is asserted to read no clock: promoting twice with the same
argument produces the same bytes.

**The version comparison.** `("0.10.0", "0.9.0")` is a parametrized case and it
is the first one. Pre-release and post-release suffixes are asserted to be
ignored rather than crashed on, and an empty value is asserted silent.

**The listing's advice matches the direction.** A store holding one schema 10
file, read by a build at 9, prints the upgrade sentence; the reverse prints the
migrate sentence. Both are asserted on the exact line, because the line is what
a user acts on.

## Not decided here

**Whether a future bump may be non-additive at all.** `_NON_ADDITIVE` holds
three entries and all three predate any published release. The rule for a
non-additive bump against a store with years of history in it is a decision for
the release that first wants one, and it will be a harder record than this one.

**A store-wide `digline migrate` across every tenant and suite at once.**
Migration is per suite today because that is the unit a person holds in their
head. A whole-store form is a convenience, not a semantics change, and it waits
for somebody to ask.
