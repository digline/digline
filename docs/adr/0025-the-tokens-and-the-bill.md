# ADR 0025 — The tokens, and the bill the run could not state

- Status: accepted — the text first, the implementation written against it on
  `usage-on-the-document`, the way
  [ADR 0014](0014-what-may-ride-a-schema-bump.md),
  [ADR 0018](0018-the-recorded-trajectory-and-the-agent-under-test.md) and
  [ADR 0024](0024-the-judge-as-an-instrument.md) were
- Shipped: 0.16.0
- Date: 2026-09-18
- Opens: **schema 14**. It is the first passenger of that train, and it is
  written before the train is coupled: what else may ride is decided against
  [ADR 0014](0014-what-may-ride-a-schema-bump.md) §1, not against convenience
- Assumes: [ADR 0014](0014-what-may-ride-a-schema-bump.md) §1 (the passenger
  rule) and §6 (what a bump costs downstream);
  [ADR 0015](0015-the-recorded-output-and-the-declared-re-judge.md) §4 (a
  recorded answer is payload and no `Disclosure` releases it);
  [ADR 0022](0022-the-declared-price.md) (a declared price is the ruler a
  `CostBudget` reads cost on);
  [ADR 0004](0004-every-plugin-is-a-target-and-a-judge.md) §6 (`Completion`,
  which already carries `Usage` and is where the counts arrive);
  [ADR 0005](0005-the-configuration-of-the-system-under-test.md) §4 (the judge
  is an instrument and is recorded as one)
- Touches: nothing in `CLAUDE.md`'s *fixed* section. Decision 4 (*cost and
  latency are budgets, not metrics*) is **not** amended: this record adds no
  gate and no threshold, and §11 says why a `TokenBudget` is not here
- Turns into surface: `docs/api.md` (the new fields), `docs/rejudge.md` (what a
  replay can and cannot restate about the bill)

## Context

The question that opened this was *where does digline record the token counts*,
on the premise that `digline-openai` already recorded them and the other two
did not. **The premise was wrong, and the correction is the whole reason this
record exists.**

No provider records them. The counts arrive, are used once, and are dropped —
identically for all three plugins, because the dropping does not happen in a
plugin at all. It happens twice in the core:

1. `ProviderTarget.__call__` (`targets/provider.py`) receives
   `Completion.usage`, prices it with `Pricing.cost(...)`, keeps the **money**
   on `Response.cost_usd`, and copies the four counts into
   `Response.metadata` — under a comment that states the consequence plainly:
   *"`Response.metadata` is not persisted, so this costs nothing in any
   document."*
2. `execute()` carries that mapping into `EvaluatorInputs.metadata`, where an
   assertion may read it while the run is in memory. Nothing copies it onward:
   `CaseResult` keeps verdicts, and `RecordedResponse` — the one record that
   survives, and only where the suite asked for it — keeps `output`, `input`,
   `cost_usd`, `latency_ms` and the trajectory. **There is no field anywhere in
   the document that holds a token count.**

So what a user saw was real and was not a recording: the counts exist in the
provider's reply and in the live `Response`, and the document is written from
neither. *Seen in a raw reply* and *kept* are different claims, and this record
exists because they were run together for long enough to plan a release around.

**Why that matters beyond tidiness.** `Pricing.cost` turns four counts into one
float and the counts are gone, so every question downstream of the money is
unanswerable from the document:

- *Why did this run cost 2.4× the last one?* — more output, a cache that stopped
  hitting and a longer prompt are three different problems with three different
  fixes, and the run says only that the number moved.
- *Does our bill agree with the provider's?* — reconciliation is per-token, and
  a run that reports only USD can be checked against nothing.
- *What did the judging cost?* — `JudgeBase` accumulates `spent_usd` and
  `calls`, and **no document has ever carried either.** The instrument's bill
  has been invisible since the first release, which is the sharper half of this
  finding: not that a detail was lost, but that one of the two lines of the bill
  was never written down.

And an absent count cannot be reconstructed later. The answer is paid for once;
a document that did not keep what it paid for has lost it.

## Decision

### 1. The counts are recorded, on the document, at two grains

**The totals, always.** `Run.usage` holds two lines — what the **target**
consumed and what the **judge** consumed — on every run, whether or not the
suite records responses.

**The detail, where the suite already asked for it.**
`RecordedResponse.usage` holds one call's counts, under the existing
`Suite.record_responses`. It does not get a switch of its own: the switch that
governs a stored answer governs the counts belonging to that answer, and a
second flag would be a second thing to forget.

### 2. Why both, and not one of them

A single grain fails on one of the two questions this exists to answer.

**A bill is a total.** *What did this run cost, and in what* is a run-level
question, and it is the ordinary one. It must be answerable on the ordinary
run — which does **not** record responses, because a recorded answer is the end
company's data and recording is opt-in for exactly that reason (ADR 0015 §4).
Totals conditional on recording would make the bill available only to the
configuration least free to look at it.

**A discrepancy is found in the detail.** *Why* is per-call. A total that moved
names no case; the case that sent a 9 000-token prompt does. The detail is also
what makes a total checkable at all: a sum nobody can decompose is a claim, and
the whole posture of this project is that a claim with nothing under it is not a
measurement.

They are two grains of one fact and neither substitutes for the other, so both
are recorded, under the rules each grain already has.

### 3. What a line holds

```python
@dataclass(frozen=True, slots=True)
class Usage:  # moved to digline.core — see §5
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0


@dataclass(frozen=True, slots=True)
class CallTotals:
    """One line of the bill: what was asked, and how much of it was counted."""

    calls: int = 0  # calls this line covers
    counted: int = 0  # of those, how many reported usage
    tokens: Usage = Usage(0, 0)
    spent_usd: float = 0.0


@dataclass(frozen=True, slots=True)
class RunUsage:
    target: CallTotals
    judge: CallTotals
```

`Run.usage: RunUsage | None = None`. `None` is **not recorded** — a migrated
document, a `Run` built by hand in a test, a library caller who built one
directly — and is never read as zero, on the rule `digline_version = ""`
already follows.

**`counted` is the field that keeps this honest, and it is not bookkeeping.**
A total with no count of what it totals is exactly the undercount that reads as
good news, and there are two ordinary ways to get one:

- **A target that reports no usage.** `HttpTarget` reads a cost out of a JSON
  path and has no token counts at all; a plain-function target has whatever its
  author built. Their calls are real and their counts are absent, and a bill
  that silently summed them as zeros would state a number that is not the bill.
- **A resumed leg (ADR 0017).** ~~A journal line holds `case_to_dict(...)`, so
  a resumed run recovers the earlier legs' counts **only where responses were
  recorded**.~~ **Corrected 2026-09-18, before this ever shipped: the journal
  carries a bill line of its own**, so a resumed run recovers every leg's calls
  whatever the suite records, and this is no longer a way to get a partial
  total. See §11. What remains is the first cause alone, plus a library caller
  who resumes by hand and declares `CallTotals(calls=n)` with no counts.

Both produce the same fact — *this total covers `counted` of `calls`* — and a
reader acts on it identically: do not read this as the whole bill. So one field
carries both, and the reading says so where they differ (§9). Making the journal
keep totals of its own, so a resume could restate the whole bill, is §11.

**A replay is a third case and is not a partial total: it is a zero.** A run
judged from recorded answers (ADR 0015 §6) calls no target, so its target line
is `calls=0, counted=0` — nothing was asked and nothing was spent — while its
**judge** line is real, because the judging is what a replay actually pays for.
The recorded `cost_usd` the replay carries per case still feeds `CostBudget`,
which is what made it ride the record in the first place; what it must not do is
become a run total, because that would restate as this run's spending money that
a previous run spent. `rejudged_from` is on the document to tell the two apart,
and the reading has it.

**`spent_usd` is on the line and not left to be summed.** Today a run's total
cost is reconstructable only by adding up `RecordedResponse.cost_usd`, which
exists only when recording is on — so the run's own money is unavailable in
exactly the ordinary case. It is the same field the same call already computed,
at the grain the question is asked in. On the judge line it is the
`JudgeBase.spent_usd` that has never reached a document.

**Four counts and not a `total_tokens`.** Providers publish four rates and
digline already prices four counts; a sum would have to pick which of the four
to hide, and the one that hurts is `cache_write` (friction 25, and §11).

### 4. The judge's line needs its own answer, and this is it

The target's counts are one line change away: `Completion.usage` reaches
`ProviderTarget`, which is already holding them. **The judge's are not**, and
this section exists because extending `JudgeBase` silently would be exactly the
kind of quiet widening this project makes people argue for in writing.

`JudgeBase` accumulates three things today — `calls`, `spent_usd`,
`latency_ms` — all monotone for the life of the object, never reset, documented
as *what this judge has spent since it was built* with the note that a caller
wanting a per-run figure **reads twice and subtracts** (ADR 0004 §3). It gains a
fourth of the same kind:

    self.tokens: Usage     # monotone, never reset, summed in _ask

filled in `_ask` beside `self.spent_usd += ...`, from the same `reply.usage`
that is already in hand — so a judge that raises is not counted, on the rule
already written there: *its cost is unknown, and counting it at zero would be
the undercount that reads as good news.*

**`execute()` reads twice and subtracts.** It already asks `judges(...)` before
the first case and after the last (ADR 0005 §9). The judge line of `RunUsage` is
the difference between those two readings, which is the only shape that is
correct when a suite reuses a judge object across runs — the shape ADR 0004 §3
prescribed and nothing had yet needed.

**Judges are deduplicated by object identity.** One judge instance bound to two
assertions is one instrument and one bill, and counting it twice would double the
judging cost of every suite that shares a judge — which is most of them. This is
a `dict` keyed on `id()` at the one place that walks them, and it is stated here
because it is the kind of thing that is obvious in the writing and invisible in
a review.

**And the edge of that rule, said out loud rather than met as a strange
number.** Two *distinct instances* configured identically — same provider, same
model, same `max_tokens`, one bound to each of two assertions — are **two
objects and two bills, and their totals add**. That is correct: each one made
its own calls and each one was paid for, and the suite's bill is what the suite
spent. But it looks wrong from the outside, because `judge_config` records those
two instances as **one identity** (ADR 0005 §4 records the instrument, not the
instance), so a reader sees one judge in the configuration and a total that
reads like two. Nothing here collapses them: equal configuration is not the same
instrument, digline cannot tell a deliberate pair from an accidental one, and
merging the bill would hide a suite that is paying twice for what it thinks is
one judge. The reading owes that reader the sentence, not a smaller number.

**A judge that reports no usage still reports calls.** `counted` on the judge
line carries the same meaning as on the target line, for the same reason.

### 5. Where the type lives, and why no plugin changes

`Usage` is defined in `digline.targets.pricing` today, and `targets` sits
**above** `run` and `core` in the dependency chain. A document field whose type
lives up there would invert the chain, and `tests/test_layering.py` would refuse
it — correctly.

So `Usage` **moves to `digline.core`**, and `digline.targets.pricing` re-exports
the same object:

```python
# digline/targets/pricing.py
from digline.core import Usage  # re-exported: the plugins' import is unchanged
```

`from digline.targets.pricing import Usage` — what all three published plugins
write — keeps working, byte for byte, and keeps working against the *same class*,
so an `isinstance` in a plugin's tests stays true. **No plugin release is forced
by this bump**, which is the same promise ADR 0014 §6 makes about the floors
gate being name-based.

The class arrives in the core with its `__post_init__` intact (no negative
count) and gains one operation it now needs — addition, for accumulating a line.
Addition on a frozen value returns a new one; nothing mutates.

`Response.usage: Usage | None = None` joins `Response` in `digline.run.driver`,
which may import from `core`. `ProviderTarget` fills it from the `Completion` it
already reads.

**The four metadata keys stay where they are.** `ProviderTarget` keeps writing
`input_tokens` and its three neighbours into `Response.metadata`: that mapping
reaches `EvaluatorInputs.metadata`, assertions in the wild read it, and removing
it would break them for no gain. But the **document is written from the typed
field only** — the driver never reads a count out of a free-form mapping by
name. A recorded fact whose source is a string key is a fact one typo away from
absent.

### 6. It is not a gate, and it moves no exit code

`Run.usage` gates nothing. No status turns on it, no `compare()` outcome reads
it, no exit code moves. `CostBudget` keeps reading `EvaluatorInputs.cost_usd`
and is untouched — a check that measured a case's money still measures a case's
money.

This is deliberate and it is the reason fixed decision 4 is not amended. *Cost
and latency are budgets, not metrics* says a **declared ceiling fails the run**;
it does not say every number must be a ceiling. A recorded total with no
threshold is not a vacuously green assertion (decision 3), because it is not an
assertion: it is a fact on the document, like `latency_ms` on a recorded
response and like `digline_version`.

### 7. The passenger rule (ADR 0014 §1), answered in full

| | 1 — the hash | 2 — the migration | 3 — the boundary |
|---|---|---|---|
| `Run.usage` (the two totals) | untouched. `config_hash` is the identity of the *suite configuration* — assertion identities with thresholds and tolerances, `samples`, `min_agreement`, the aggregates, and since ADR 0022 a **declared price**. A declared price enters because it is the ruler a `CostBudget` is read against; a *consumption* is the thing measured, never the ruler. Nothing about what a run consumed can change what the run was asked to do | the 13 → 14 step writes **nothing**. `None` is the only honest value: the counts of a run measured last month are gone, and no field in the document derives them. Writing `0` would state that a paid run consumed nothing — an invention, and one in the good-news direction | a measurement, and it travels. Every field is a number, produced by our own instrument out of a provider's report, about what the *software house's* run consumed. It survives `redact()` in clear, beside `digline_version`, `promoted_at` and `resumed_at`, and `digline.wire` emits it. §8 is the one thing that argues against, and why it does not win |
| `RecordedResponse.usage` (the detail) | untouched: a recording field inside `RecordedResponse`, and what the suite records has never been in the hash (ADR 0014 §1's second passenger made exactly this argument) | absent, and absent is what it means at 14 too for a response recorded by a target that reported nothing. The migration invents nothing because there is nothing to invent from | **payload.** It rides `RecordedResponse`, so `redact()` drops it with the response, `promote_baseline` strips it through `without_responses`, and `digline.wire` never learns its name. No `Disclosure` releases it, on ADR 0015 §4's rule |

### 8. The one boundary argument that had to be answered, not assumed

A token count is a number, and `travels()` lets numbers cross because they are
measurements. But a count of input tokens is also, coarsely, **a measure of how
much text the end company sent** — an aggregate over their payload rather than
a fact about our instrument. That is not nothing, and `Disclosure`'s strict half
exists because `1499.00` copied out of a customer's request is their data wearing
a measurement's clothes.

It is answered by the grain, which is why the two grains are ruled differently
and not together:

- **The run total crosses.** *This run consumed 412 000 input tokens across 120
  calls* is the software house's own bill for its own run. It identifies no
  case, no request and no person, and it is the number the software house pays.
  Withholding it would withhold the software house's invoice from the software
  house — world 2 is defined by needing the signal **without** holding the data,
  and a total is signal with no data in it.
- **The per-call count does not.** *This case's prompt was 9 214 tokens* is a
  fact about one request of theirs, and it lands on a record that is already
  payload for a stronger reason. It stays with the answer it belongs to, and it
  leaves only where the answer does, which is nowhere.

That is decision 9 applied without an exception: the payload stays where it is
born, the verdict — and the software house's own total — travels.

### 9. What reads it

A field nothing reads is a field that drifts (ADR 0014 §3), so:

- **`digline.wire`** carries `usage` in the run projection, so `--json` and the
  MCP `get_run` answer it identically. `OUTPUT_VERSION` stays at `1`: an added
  key breaks no consumer, which is the rule its own comment states.
- **The CLI's run summary** prints one line per side, in the terminal's `en`,
  and prints the `counted` gap **only when it is one** — *target: 120 calls,
  412 000 in / 38 100 out, 4.12 USD (counted 118 of 120)*. A parenthesis that
  appears on every run is one nobody reads; a parenthesis that appears when the
  total is partial is the one thing a reader must not miss.
- **The HTML report is not touched by this record.** The report is the document
  for world 3, and world 3 is owed an understandable verdict — not the software
  house's invoice. A bill has a different recipient from a verdict, and putting
  it on the same page would be answering a question nobody in that world asked.
  If it earns a line there it earns it in its own record.

### 10. The old reader, and what justifies the bump

**Nothing is misread without this bump, and that is the honest position.** A
reader that meets an unknown `usage` key ignores it, as every reader ignores
every key it does not know — and ignoring it changes **no verdict, no status, no
denominator and no comparison**, because nothing in the system reads it (§6).

That is the opposite of `sample_means` (ADR 0024 §6.4), where a reader ignoring
the key read means as judgements — a silent misreading of a score. It is also
unlike the nameless call (ADR 0018 §3.4), whose second and third arguments —
*a named refusal instead of one that reads like corruption*, and *the inner
refusal is the journals' only protection* — have **no counterpart here**. There
is no refusal to protect, because there is nothing to refuse: an absent `usage`
is a legitimate document at every schema.

So the bump rests on that ADR's **first** argument alone, and rests on it
squarely: **the train.** A new field on a stored document is a schema change and
not a patch — `run_from_dict` refuses any version that is not exactly its own,
in both directions, so the constant moves or the field does not exist. ADR 0014
§1 wants a bump, once paid, to carry what it honestly can; this passenger costs
the migration nothing and passes all three conditions. It opens schema 14 and
the train stays open for other passengers to be argued against the same rule.

`_NON_ADDITIVE` gains no row. No document is refused by this step.

### 11. What this record does not do

**No `TokenBudget`.** A ceiling on tokens would be a gate, and a gate is
decision 4's territory: it needs a threshold, a tolerance, a `compare()`
behaviour and an exit code. `CostBudget` already gates the number a budget is
actually written in, and the first person who needs tokens capped separately
from money can have this data to argue from — which is more than they have
today.

**No repair to the cache-write rate.** `ModelPrice` declares **one**
`cache_write_per_mtok`, and a provider that bills cache writes at 1.25× base
input for a short cache lifetime and 2× for a long one cannot be priced by a
single rate: a long-lived write costs 1.6× what digline reports. It is friction
25's family exactly — an undercount, in the good-news direction. It is not fixed
here because it is a **pricing** decision and this is a **recording** one, and
because what is unproven is narrower than it first sounds. **Cache writes
themselves are not in doubt**: the count is reported, and was observed in a
live reply on 2026-09-18 by a user on an OpenAI-compatible endpoint. What no
measurement covers is a **long-lived** write through digline's own path —
`ProviderTarget` sends no cache-control of any kind, so the lifetime a write of
its own would be billed at should be the short one. That is an argument about
our target and not about a user's, and it is not one the price list makes.
Either way, digline separates `cache_write_tokens` from the rest and now
records them, so the document will show the count the money was computed from —
which is the first thing anyone needs to notice the money is wrong. Written up
in the findings file.

**Journal totals — parked here, then ruled the same day. Corrected
2026-09-18.**

What this section said, and it is left in the record rather than tidied away:
*a resumed run restates the earlier legs' counts only where responses were
recorded; giving the journal a totals line of its own would move
`JOURNAL_VERSION`; it waits for somebody to be bitten by a partial total that
`counted` already declares.*

**The bite was immediate, and it came from a committed gate rather than from a
user.** `tests/test_journal.py::test_the_resumed_run_is_the_document_the_kill_prevented`
asserts a resumed run is byte for byte the document the kill prevented — the
assertion that, in its own words, makes ADR 0017 §10 true rather than intended.
The first implementation of this ADR failed it on one field: a six-case run
killed at case four reported `spent_usd: 0.03` where the uninterrupted run
reported `0.06`. The money of the legs that were not re-run was simply gone,
because a journal line holds `case_to_dict(...)` and that carries responses only
when `record_responses` is on — which is off in the ordinary case.

So a parked decision was not available. Either the journal keeps its own bill,
or ADR 0017 §10 stops being true the day this ships; and a record that leaves
two of its own decisions contradicting each other is not a record. **The journal
keeps its own bill**:

1. **Every `case` record carries what that case's target calls consumed**, and
   it is written **regardless of `record_responses`.** That flag governs the
   *answer* — payload, the end company's data, opt-in for that reason. A bill
   line is the journal's own fact about work already paid for: four integers and
   a figure in dollars, about our own calls. A suite that records no answers
   still spent the money, and a resume that could not say so would write a
   document under-billing every leg it did not run.
2. **`JOURNAL_VERSION` goes 1 → 2, and the refusal is what justifies the
   move.** An added key alone would be *ignored* by a 0.15.x reader — it would
   resume, write a run whose totals omit whole legs, and say nothing. That is
   the `sample_means` shape exactly (ADR 0024 §6.5): where a reader that ignores
   a key would **misread** rather than merely miss, the version moves so the
   refusal is by name. A journal has no migration (ADR 0017 §2): the leg is
   refused, named, and left on disk, because it holds paid work.
3. **`calls` stops being derived.** The first implementation reconstructed a
   reused case's calls from the suite's `samples`, and the correction removes
   that arithmetic: the journal states what was called. A number reconstructed
   by arithmetic is one that eventually disagrees with the calls that were made,
   and the one place it would have disagreed — a case that errored before its
   last sample — is exactly where a bill is read most carefully.
4. **The carry is a run-level figure, not a per-case map.** `Pending.spent` sums
   **every** `case` record in every leg, not the last one per case: `done` keeps
   one outcome because a case has one, while a case retried after an error was
   paid for twice and cost twice. `execute(spent=…)` starts the target line from
   it, and a reused case adds nothing of its own — its calls are already inside
   that figure, and reading them again out of its recorded answers would bill
   them twice.
5. **A caller who resumes by hand must say what it spent.** `execute()` refuses
   a non-empty `done` with no `spent` beside it, rather than defaulting to zero:
   the default would be a silent undercount in the one direction this whole
   record is about. A caller that genuinely kept no figures declares
   `CallTotals(calls=n)` — *n calls, none counted* — which is a statement
   somebody made rather than one digline invented.

**Two format versions move inside one train, and they stay uncoupled.**
`SCHEMA_VERSION` goes to 14 and `JOURNAL_VERSION` to 2 for the same ADR, and
that is a **coincidence of one release, not a new rule**. They are independent
by design (ADR 0017 §2): the journal stood still through schemas 11, 12 and 13,
and nothing here makes it move for 15. They move together now because one
decision happened to touch both files, and each move is justified on its own
ground — the document's by the passenger rule (§7), the journal's by the
refusal above. Anyone reading this later should not infer a habit: if a future
bump moves both again, it needs its own two reasons.

**The rest of what this section parked stands.** No `TokenBudget`, and no repair
to the cache-write rate.

### 12. What the bump costs downstream, in order

ADR 0014 §6's ritual, unchanged and not negotiable — it is red until it is
finished:

1. `pyproject.toml` → the version that will carry schema 14.
2. A row in `RELEASED` in `tests/test_example_caps.py`.
3. `digline migrate` over every document under `examples/*/.digline/`.
4. Every example's cap raised to admit that release.
5. The example report pages regenerated, in the established order: commit the
   example first, render, then commit the report on top.
6. The window, stated rather than hidden: between the bump and the release
   reaching the index, a reader cannot resolve the examples at all.

And one entry in another repository: the site's `nav`, plus its product and
description entries, or `mkdocs build --strict` fails after PyPI.

## Consequences

**A run can state its own bill, and it is two lines.** *What did this cost* has
a target answer and a judge answer, and the judge's has never existed in any
document digline has written.

**A cost that moves can be explained without re-running anything.** Where
responses are recorded, the four counts per call say which of the four moved.
Where they are not, the totals say it at the run's grain, which is enough to
know whether to look.

**A partial total announces itself.** `counted` is the difference between a bill
and a number that looks like one, and it is visible in the terminal, in `--json`
and over MCP.

**`Usage` becomes a core type without any plugin knowing.** The move is a
re-export, and the floors gate is name-based, so no plugin release is forced.

**Schema 14 is open and this is its first passenger.** Anything else that wants
to ride answers ADR 0014 §1 in its own words, in its own record, before the
train is coupled.

## Alternatives considered

**Record the counts through `CostBudget` — `Score.metadata` on the check.**
Rejected, for two reasons that are each sufficient.

*First, it makes the bill conditional on a gate.* A suite that declares no
`CostBudget` would record nothing, so *what did this run consume* would be
answerable exactly for the suites that already declared they cared, and blank
for everyone else. The bill is a property of a run that was paid for, not of a
check somebody chose to write.

*Second, an assertion cannot see the bill and must not learn to.* An assertion
is a pure function of one `EvaluatorInputs` (fixed decision 1) and has no route
to a run total, to a second sample or to the judge's spending — the judge's line
is unreachable from an assertion by construction. Teaching one to reach out for
it would make it callable only inside a runner, which is the one thing fixed
decision 1 says is wrong. And `Score.metadata` is what an assertion **measured**;
what the instrument consumed on the way to measuring is not a measurement about
the case.

**`Run.metadata["usage"]`, with no new field.** Rejected on ADR 0014 §3's
argument for `digline_version`, which applies here unchanged: `metadata` is
payload-governed, so nothing in it crosses a boundary unless the suite's
`Disclosure` names the key — the bill would vanish at exactly the boundary where
the software house needs it — and it would collide with a key the user chose.

**One combined total instead of target and judge.** Rejected. They are two
lines of the same bill and they move for different reasons: a judge's spending
is the *instrument's* cost, and a change in it means something entirely
different from a change in the target's. A sum hides the one substitution
ADR 0005 §4 exists to catch.

**Per-response detail always, with no `record_responses`.** Rejected: it would
put a per-call fact about the end company's requests on every document by
default, and the default must disclose less, never more.

**Totals only, and no detail at all.** Rejected by §2: a total nobody can
decompose is a claim, and reconciliation with a provider's invoice is per-call.

**A `total_tokens` convenience field.** Rejected: it would be a fifth number
derived from four, with nothing to stop it drifting from them, and its most
likely use is to hide the cache-write count that §11 says is the one that hurts.

## Test plan

Beyond a failing case for every new rule, which the conventions already require:

**The step invents nothing.** A schema-13 fixture — one with recorded
responses, one without, one redacted — migrates to 14 and is asserted to carry
`usage is None` and no per-response usage. A migrated document and one written
fresh by a target that reported nothing are asserted to be distinguishable:
`None` versus `CallTotals(calls=n, counted=0)`.

**Round trip at 14.** A run with both totals and per-response detail
serializes, parses back and compares equal; a document with neither parses to
the defaults the migration produces.

**The hash did not move.** Every example suite's `config_hash()` is asserted
byte-identical across the bump, and a schema-13 baseline migrated to 14 is
asserted to promote against the current configuration without re-promotion.

**The boundary, both halves.** `redact()` keeps `Run.usage` intact and drops
`RecordedResponse.usage` with its response; `without_responses` strips the
detail and keeps the totals; the wire projection emits the totals and is
asserted — by key, not by eye — never to emit a per-response count. A run that
is `redacted=True` and still carries per-response usage is refused at
construction, the way a redacted response that carries a cost already is.

**`counted` is what it says.** A suite of three cases against a target that
reports usage on two of them records `calls=3, counted=2`, and the CLI prints
the parenthesis; with all three counted, it does not print it. A resumed run
whose first leg was journaled without recorded responses is asserted to report
`counted` below `calls` rather than a total that looks whole.

**The judge line is a difference, not a reading.** One judge object is used for
two consecutive `execute()` calls and each run is asserted to carry only its own
judging, with the second run's totals asserted **not** to include the first's —
the failing case that a single reading of a monotone counter would pass.

**A shared judge is billed once.** Two assertions holding the same judge
instance produce one judge line; two instances of the same model produce the
sum. Both directions, because the identity dedupe is invisible when it is right.

**A judge that raises is not counted.** A judging call that fails leaves
`calls`, `tokens` and `spent_usd` where they were, on the rule `_ask` already
follows for money.

**`Usage` is importable from both names and is one class.**
`digline.targets.pricing.Usage is digline.core.Usage`, asserted, so the
re-export cannot quietly become a copy. `tests/test_layering.py` is asserted to
still refuse a `core` import of `targets`.

**The document reads the typed field only.** A `Response` carrying token counts
in `metadata` and nothing in `usage` is asserted to record `counted=0` — the
test that keeps the string keys from becoming a second source of truth.

## Not decided here

**Whether the production and online sides record the same two lines.** Both are
planned packages (`digline.production`, `digline.online`) and a stream of
production responses has no run to total. The field is on `Run`, which the
online driver does not yet build.

**A token ceiling.** §11.

**Cache-write lifetimes.** §11, and the findings file.

~~**Whether the journal keeps totals of its own.**~~ Ruled 2026-09-18, the same
day: it does. §11.
