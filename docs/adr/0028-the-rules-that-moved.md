# ADR 0028 — The rules that moved

- Status: accepted — the text first, then the implementation written against
  it on `suite-deltas`, the way
  [ADR 0014](0014-what-may-ride-a-schema-bump.md),
  [ADR 0024](0024-the-judge-as-an-instrument.md) and
  [ADR 0027](0027-the-run-reconciles.md) were
- Date: 2026-09-21
- Opens: **nothing.** No schema bump, and not a passenger on one. The run
  document gains no field. §1 is why it does not need to: everything
  `config_hash` fingerprints is already written down, bar one value, and §5
  leaves that one unrecorded
- Assumes: [ADR 0005](0005-the-configuration-of-the-system-under-test.md) §5
  (named by value, reported and never a refusal) and §7 (`unknown` rather than
  a fabricated `new`); [ADR 0003](0003-artifacts-travel-only-when-the-suite-says-so.md)
  §4–5 (withheld rather than absent, `unknown` rather than a guess);
  [ADR 0006](0006-repeated-samples-and-the-noise-floor.md) §4 (what a sampled
  verdict records, and that it records nothing at one sample);
  [ADR 0008](0008-the-two-run-report.md) §5 (a delta computation moves out from
  behind its underscore when it acquires a second consumer);
  [ADR 0010](0010-per-group-aggregates.md) §1 (group membership stays in the
  repository), §3 (`[group=…]` is a public string) and §6 (the expansion moves
  `config_hash`); [ADR 0014](0014-what-may-ride-a-schema-bump.md) §1 (the
  passenger rule, applied and then declined in §5);
  [ADR 0022](0022-the-declared-price.md) §3 (the declared price joined the hash)
- Touches: nothing in `CLAUDE.md`'s *fixed* section. Decision 3 — *no vacuously
  green assertion* — is what §4 serves: a bar quietly lowered is how a green run
  stops meaning anything, one release at a time
- Turns into surface: [`AGENTS.md`](../../AGENTS.md) §1 (which is why §4 reports
  and never gates), `docs/diff.md` (§7's refusal), `docs/explain.md` (§8's tally)
- Credit: the gap was found while reading EvalSeal's work

## Context

Two runs are held against each other and something about the suite moved. The
reader gets one boolean, `Comparison.config_changed`, and one sentence:

> The suite changed since the reference, so these numbers compare different
> rules.

Which assertion was added, which threshold moved, whether `samples` went from
three to five, whether an aggregate gate joined — named nowhere, on any surface.

This is the exact opposite of what the *other* side of the same comparison has
done since ADR 0005. `config_deltas` names the system under test per field, per
side, with an outcome and a `withheld` marker, and it reaches the terminal, the
report, `--json`, MCP and `explain`. That ADR's own argument was that *"the
configuration differs" sends a reader off to reconstruct what differed, while
`temperature 0.3 → 0.7` is a sentence they can act on.* Every word of it applies
here, to the rules that judge, and it was never said here.

The two are disjoint by accident of history, not by decision. `config_hash` was
built first and as an identity — something to compare for equality and to key a
stored run on. Nothing asked it to explain itself, because until ADR 0005 there
was no precedent for a delta that explains.

**What the asymmetry costs has a name.** Somebody who lowers a threshold from
0.6 to 0.5 and re-promotes produces a report indistinguishable from somebody who
added a test case. Both move `config_hash`; both print that one sentence. This
is the side a silent weakening of the gates lives on, and today it is the side
with no reading at all.

There is one partial exception and it is narrower than it looks.
`detail.threshold_moved` names a moved bar — but only inside the sentence for a
check whose **status also flipped**. A threshold lowered under a check that was
already passing is silent, and so is the quieter one:

**The tolerance is worse than the threshold.** `compare()` judges movement
against *the current run's* tolerance, by a deliberate decision its own
docstring states. A raised tolerance therefore never produces a flip — it
produces an `unchanged` where there would have been a `regressed`. So the one
place a moved bar is named today is structurally unable to see the edit that
hides a regression most completely.

## Decision

### 1. The rules are already in the document

This is the finding that decides every section after it, and it went the
opposite way to the expectation. **No new recording is required.**
`config_hash` fingerprints five things. Four and a half of them are already
written into every run file and every promoted baseline:

| in `config_hash` | in the document? | where |
|---|---|---|
| assertion identities | **yes** | `assertion_id`, on every verdict |
| per-assertion threshold | **yes** | `threshold` |
| per-assertion tolerance | **yes** | `tolerance` |
| aggregate identity, threshold, tolerance | **yes** | `aggregate[]`, already the *expanded* list, so a per-group gate is one row of its own |
| `samples` | **yes** | `metadata["samples"]`; absent means one |
| `min_agreement` | **no** | nowhere — see §5 |
| the declared price digest | **yes, already named on the other side** | `pricing` and the rates, in `target_config` |

Three structural facts make that a reconstruction rather than a sample:

1. The driver asks **every** declared assertion of every case that is neither
   suspended nor a calibration: `verdicts` is built by iterating
   `suite.assertions`. The union over the cases is the declared set.
2. A case whose target or mapper raised carries it too. `_failed` builds one
   `error_verdict` per assertion, and that function takes name, identity,
   threshold and tolerance off the `Assertion` protocol — *"nothing has to be
   invented"*, as its docstring puts it. A run where every call failed still
   states its rules in full.
3. `_required` refuses a document missing `assertion_id`, `threshold` or
   `tolerance`. They have been mandatory at **every schema version ever
   written**, so this reads a baseline promoted a year ago as well as one
   promoted today. There is no legacy-document problem here at all, which is a
   real asymmetry with ADR 0005 and the first time one has fallen our way.

Two derivations in it are not obvious and are worth pinning, because each is a
place where a plausible reading would be wrong:

**`samples` is unambiguous, but only on a paired row.** Two mechanisms write a
sample count: `Suite.samples`, and a `Repeated` wrapper. They are told apart for
free, by identity: `Repeated` is a frozen dataclass whose `samples` and
`min_agreement` are ordinary fields, so they are *in* its identity, and editing
a wrapper produces a `new` plus a `missing` rather than a paired row. Therefore,
for an `assertion_id` present on **both** sides, a change in
`metadata["samples"]` can only have come from the suite. Read on an unpaired
row it would be a guess; read only on paired rows it is a derivation.

**It survives redaction, completely.** `threshold`, `tolerance` and
`assertion_id` are already what `compare()` reads through a redacted run, and
`metadata["samples"]` is an `int`, so `travels()` passes it on its own merit as
a measurement. A redacted run compared against a complete baseline yields the
**full** set of rows. That is not a detail: world 2 — the software house holding
the signal and none of the payload — is precisely where a quietly lowered bar is
invisible today, and it is the world this serves best.

**And the price is the proof that the two sides were never truly disjoint.**
ADR 0022 put a declared rate into `config_hash` because *a rate is the ruler a
`CostBudget` reads cost on*, and the same rate is recorded in `target_config`,
where `config_deltas` has named it by value ever since. One ruler, in the hash
and named beside it. This record does for the other rulers what that one did for
the price.

### 2. Derived at comparison time, never recorded

`suite_deltas(run, baseline) -> tuple[SuiteDelta, ...]`, in
`digline.core.compare`, beside `config_deltas` and built the same way: a pure
function of two documents, no I/O, no clock, no suite in hand. It is a **field**
on `Comparison`, not a render-time computation, on `config_deltas`' precedent —
a value the wire and both documents read from one place cannot drift between
them.

Keyed on `(scope, assertion_id)`, unioned across the cases, with the readable
name carried alongside for the sentence — the same shape as `index_verdicts`,
and for the same reason: position is not identity.

`SuiteDelta` is a frozen value, and its fields are chosen to borrow rather than
invent:

    rule: str              # the readable name: `precision[group=hotel]`
    assertion_id: str      # what it was paired on
    scope: Scope           # "case" or "run" — the two already in Comparison
    outcome: ConfigOutcome # the same five words as a config or an artifact
    direction: Direction   # "loosened" | "tightened" | "" — see §4
    field: str             # "threshold", "tolerance", "samples", or "" for a
                           #   rule that arrived or left whole
    before: float | int | None
    after: float | int | None

`outcome` is deliberately the **five-word vocabulary** `ConfigDelta` and
`ArtifactDelta` share, for the reason ADR 0012 §3 gives for their sharing it: a
reader who has learnt what `unknown` means in one table has learnt it in all of
them. The direction is §4's business and is a field beside the outcome, never a
sixth word in it.

One row per *moved value*, not per rule: a check whose threshold and tolerance
both moved produces two rows, because they moved in possibly opposite
directions and a single row would have to pick one verb.

Where it is **not**:

- **Not in the store.** A stored run is what it reads; a store that computed it
  would be a store with an opinion about two files.
- **Not in the host.** The host holds the current suite, and that is exactly the
  temptation §6 refuses. A derivation available only where a suite was loaded
  would be absent from `pytest-digline`, from a library caller, and from
  anything reading two documents off disk — and the three would disagree about
  what a comparison says.
- **Not a field on the document.** That is the whole economy of this record.
  There is no migration, no re-promotion, no churn through the nine committed
  example baselines, no dependency caps to move, and no place in a schema
  train. It costs a function.

`diff.py` imports it, as it already imports `config_deltas` and
`index_verdicts` (ADR 0008 §5). Written in `compare.py` and public from the
start, rather than private and promoted later, because it has two consumers on
the day it is written.

### 3. Four rules, three of them inherited

`config_deltas`' three rules exist to keep it from reporting a change nobody
established. They govern here unchanged:

1. **Neither side recorded anything → say nothing.** A run whose every case is
   suspended carries no verdict anywhere, and the answer is `()`, never *every
   rule was removed*.
2. **One side recorded nothing → `unknown`, never `new` or `missing`.** In
   practice unreachable, for §1's third fact, and the rule is written down
   anyway: the day somebody adds an optional field to a verdict, this is the
   rule that stops its absence in a year-old baseline from rendering as an
   edit.
3. **Withheld → `unknown`.** Nothing this reads is ever withheld. That is a
   claim, so it is **pinned by a test** rather than asserted here: a redacted
   run compared against a complete baseline must produce the same rows as the
   unredacted one. If a field added later breaks it, the test says so instead
   of the boundary saying nothing.

And one this needs that `config_deltas` does not:

4. **`min_agreement` is never named, and never inferred.** The measured
   `agreement` is in the metadata of every folded verdict. The *floor* it was
   judged against is not. Deriving one from the other would be the guess wearing
   the clothes of a finding that rule 3 exists to forbid. See §5.

**A case is not a rule.** The derivation is keyed on assertion identity and
unioned across the cases, so adding a case, removing one or suspending one
produces **no row here at all**. That is not a convention to be careful about,
it is the shape of the key. The case set is already named, per case, by the
`new` and `missing` deltas `compare()` has always produced. Adding a test is the
most ordinary edit in the product and it stays silent on this surface. §6 is the
one shape that looks like an exception, and it is not one.

### 4. The direction is named. The rules are never gated

**It reports and it never gates.** A threshold is a human's declaration of where
the bar sits, and this product's whole thesis is the one `AGENTS.md` §1 opens
with: the agent proposes, the instrument measures, **the human approves**. An
instrument that refused a bar because the bar had moved would be an instrument
with an opinion about the approval. The gate for this already exists and it is
the right one: `promote_baseline` refuses across a changed `config_hash`, so a
lowered bar cannot become the reference without a person signing it. The
signature is the gate. This record supplies the sentence the signer reads.

**But down and up must not read alike.** A row that said *threshold 0.6 → 0.5*
in the same voice as *threshold 0.5 → 0.6* would have named a value and hidden
the fact.

The direction is **a fact beside the outcome, not a sixth word inside it** —
the shape `within_noise` and `canary` already take on `AssertionDelta`, and
chosen here for the same stated reason: the five-word vocabulary is shared
across configurations, artifacts and now rules, and a reader who has learnt it
must not have to learn a variant. Three words, and only three:

- **loosened** — a threshold lowered, a tolerance raised, a rule removed. Fewer
  or weaker gates than the reference was approved under.
- **tightened** — a threshold raised, a tolerance lowered, a rule added.
- **changed** — everything else, printed with both values and **no verb**.

Three things about that vocabulary are load-bearing:

**The word describes the rule, never the outcome.** A threshold lowered under a
check that scores 1.000000 loosened nothing that happened. The row says the bar
moved down; it does not say the run got easier, and the reading must not add
that. *Loosened* is a fact about what was declared, in the register *coincides*
was chosen in for ADR 0005 §5 — the strongest word the data supports, and not
one syllable past it.

**`samples` takes no verb, and this is the line a later reader will want to
'fix'.** It reads like a tightening — more samples, a better measurement — and
half of that is true. The other half runs the opposite way: the interval a
sampled check records is **measured**, so more samples usually means a *wider*
noise floor, and a wider floor is exactly what `compare()` then forgives more
movement inside. `samples 3 → 5` therefore raises the confidence in the score
and lowers the bar the next comparison judges it against, in one edit. Neither
half dominates the other, and no arithmetic here can weigh them, so the row
prints `samples 3 → 5` and stops. **A future release that gives this a
direction is making a claim this record examined and refused**; if it is made,
it is made in an amendment that says which half it decided wins, and why.

**The two directions are not summed.** A suite that tightened three bars and
loosened one is not *tightened on balance*: there is no such quantity, and
computing one would let three cosmetic tightenings bury the edit that matters.
The loosened rows get the headline; the tightened ones are in the table. That
asymmetry is the one `compare()` already chose for a flip it cannot fully
justify — *red is the side this product chooses to be wrong on* — applied one
register up.

### 5. `min_agreement` stays unnamed, and the record says why

It is the one thing in `config_hash` the document does not hold. It passes the
passenger rule of ADR 0014 §1 on all three counts, and that is worth writing
down because it is the argument somebody will want on the day it boards:

1. **It leaves `config_hash` untouched** — it is already *inside* the hash.
   Recording it beside the hash moves nothing, unpromotes nothing, renames no
   stored run.
2. **It migrates additively without inventing.** Absent is *not recorded*, on
   the rule `digline_version = ""` already follows. It is never read as `1.0`,
   which is the value that would make an unrecorded floor look like the
   strictest one there is.
3. **It does not widen what travels.** A float the suite author wrote about our
   own instrument, in every respect a threshold's twin, and thresholds have
   travelled since schema 1.

**It does not board.** Recording a float only so that a delta may name it is a
train with no friction behind it — nobody has yet been bitten by a
`min_agreement` that moved unseen, and a passenger whose whole justification is
the completeness of a table is how a schema becomes a collection of what was
convenient, which is the thing ADR 0014 exists to prevent. It boards the day
somebody is bitten, and that day it will pass a rule it has already been
measured against.

Meanwhile the reader is told, but not everywhere. A standing `unknown` row on
every comparison of every suite would be noise on the great majority that never
sampled at all, and rule 1 already says absent is not a change. So: **the
`unknown` row appears only where either side sampled** — where some verdict
carries a `metadata["samples"]` above one, which is exactly where a floor
existed and actually gated something. A suite that never sampled never sees the
row. A suite that did sees, once, that this one value cannot be compared.

### 6. A gate that appeared over a group, and the case nobody can name

`run_assertions` is the **expanded** list: `Suite` runs `expand_by_group` over
the groups its *cases* declare. So a case labelled into a group that did not
exist adds an aggregate, and **moves `config_hash`**. The statement in §3 —
adding a case produces no rule row — has this one shape standing against it, and
it has to be written down rather than met in a pull request.

The ruling this section was given was to name the gate and put **the case that
introduced it** beside it, so that a new gate could not read as somebody
rewriting the rules. That ruling was right about the danger and wrong about the
remedy, and **the derivation below replaces it.** Two reasons, and the second is
the one that matters:

1. **Neither document holds the membership.** `CaseResult` records no group,
   `Verdict` has no field for one, and `case_to_dict` writes neither — not an
   omission but ADR 0010 §1 deliberately keeping group membership in the
   repository, where the cases are. `split_grouped_name` exists *because* of
   that decision, and says so in its own docstring: a stored run carries the
   group only inside the name.
2. **The case would often be the wrong answer even if it were held.**
   **Re-labelling an existing case creates a group with no new case behind it.**
   On that path — the most ordinary one, since a group usually arrives by
   labelling what is already there — there is no case to point at, and pointing
   at the nearest new one would be the fabricated causation the whole of §3
   forbids. Naming a case here would be wrong more often than absent.

So the case is not named, and what replaces it answers the same question
better, needing no suite and no case. `grouped_name` writes `precision[group=hotel]` as a public
string and `split_grouped_name` reads it back — which exists, as its own
docstring says, precisely because a stored run carries the group only inside the
name. So, for a new `[group=…]` row over base aggregate *A*:

- **The baseline carried other `[group=…]` rows for *A*, and not this one.**
  Then `by_group` was already set and the **group itself is new** — and a group
  exists only where a case declares it. The row reads *a new gate over a new
  group*: somebody labelled a case, and the rules were not rewritten.
- **The baseline carried no `[group=…]` row for *A* at all.** Then `by_group`
  was set on the aggregate. The row reads *this aggregate is now gated per
  group*: a rule change, and the author's.

Both causes are named, neither is guessed, and no case is accused of anything.
That is what the original ruling wanted — a new gate that does not read as a
rewritten rule — delivered by the one fact both documents actually carry. The
gate is a `new` rule in the table either way, because suppressing it would hide
a real new gate; it is the sentence beside it that differs.

Recording `group` on the `CaseResult` would settle it exactly, name the cases,
and cost a schema passenger. It does not board here, for §5's reason. When it
does, this section is the friction it was waiting for.

### 7. `diff()` takes the better refusal

`diff()` refuses two runs whose `config_hash` differs, and the message ends
*"re-run one side under the other's suite"* without ever saying what differs.
It is the cheapest win in this record: at the moment it refuses, `diff()` is
holding both documents, which is the only thing `suite_deltas` needs.

**The refusal names the rules that differ**, in the message, in the same three
words §4 gives them. Nothing else about `diff()` moves: it still refuses, and
the refusal is still right — a difference measured across two sets of rules
compares the rulers, not the systems.

It does **not** gain the rows on a `Difference`. `diff()` refuses before it
builds one, so carrying them there would mean not refusing.

The message is **capped** — the first few rows and a count of the rest, the way
`SUMMARY_LIMIT` caps the terminal. A suite rewritten wholesale must not print a
hundred rows into an exception, and a refusal nobody can read is a refusal that
does not say what differs after all.

### 8. The reading

- **Terminal `compare`.** Beside the artifact and configuration lines and
  **above** the deltas, for the reason ADR 0003 §5 put them there: what changed
  comes before what it did. The loosened rows first.
- **The report.** A section beside *What answered* and *What judged*, with its
  own keys in `report/text.py` in **both locales** — the localisation rule of
  `CLAUDE.md`, not an English string that happens to be in a document.
- **`explain`.** The tally already carries `suite_config` as a boolean, and it
  keeps it: no `TallyKind` joins that closed list, because nothing new is being
  counted. What joins is a **`SettingKind`**: `"rule"`, beside `"target"`,
  `"judge"` and `"artifact"`, and `SettingFact` gains the `direction` field.
  That widens ADR 0012 §3's second shape — *one named thing under examination*
  — to hold a thing that is not under examination but is the ruler held against
  it. The widening is the small one available: the alternative was a fourth
  fact type for data whose shape is already `SettingFact`'s, and the
  discriminator is what keeps a rule from reading as a configuration. It passes
  that section's own test — the headline states that the rules moved, and a
  reading that named no rule would describe a comparison it could not account
  for.
- **`--json`.** `suite_deltas` under **`full`**, where `config_deltas` and
  `judge_config_deltas` already live — an added key under `OUTPUT_VERSION = 2`'s
  rule, and not a bump.
- **MCP.** Arrives with no work of its own: the server returns the same
  `compare_json(..., full=True)`. That is the `wire/` rule paying out — one
  rendering of the truth, so two front ends cannot drift.
- **`config_changed` stays exactly as it is.** It is a parsed contract on the
  headline, and ADR 0005 §5 set the precedent when it hit the same problem: the
  field names did not move, the copy did.

## Consequences

- **A comparison whose suite did not move is byte for byte what it was.**
  `suite_deltas` returns `()`, nothing renders, no key changes value, no exit
  code moves. Which is every comparison in the ordinary case, because the
  ordinary case is a suite that did not change.
- **Nothing is migrated and nothing is re-promoted.** Every baseline ever
  written, at every schema version, is read by this — the three fields it needs
  have been mandatory since the first one.
- **A redacted run gets the complete reading.** The gap this closes is widest in
  world 2, and world 2 is where it closes fully.
- **A per-group gate now carries a sentence** in every report of every suite
  that sets `by_group`. That is a visible change to existing reports, and it is
  the point of §6 rather than a side effect.
- **Two things stay unsayable, and the reading must not pretend otherwise.**
  `min_agreement` (§5), and *why* an identity moved: `assertion_id` is a digest
  of an assertion's fields, so a check whose needle changed reads as one rule
  gone and another arrived. That is already what `Assertion.name`'s docstring
  promises about a rename, and it is the right limit — a needle is
  payload-shaped, and this table never holds payload.
