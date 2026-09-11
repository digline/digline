# ADR 0016 — The canary case

- Status: accepted — the text first, the implementation written against it on
  `release-schema`, the way
  [ADR 0006](0006-repeated-samples-and-the-noise-floor.md),
  [ADR 0011](0011-the-mcp-server.md),
  [ADR 0012](0012-the-reading.md) and
  [ADR 0013](0013-the-pytest-plugin.md) were
- Date: 2026-09-11
- Assumes: [ADR 0001](0001-verdict-not-score.md) §1 (three states, and an error
  is neither green nor a regression);
  [ADR 0005](0005-the-configuration-of-the-system-under-test.md) §4 (a judge
  that moved is louder), §9 (what the provider said answered, and where it is
  not said at all);
  [ADR 0006](0006-repeated-samples-and-the-noise-floor.md) §5 (the interval is
  the baseline's), §6 (where the noise floor does not reach), §7 (the
  aggregate's own interval);
  [ADR 0008](0008-the-two-run-report.md) §2 (the exit code is the contract);
  [ADR 0010](0010-per-group-aggregates.md) §1 (`group` is descriptive), §7 (the
  filter sits in the driver);
  [ADR 0013](0013-the-pytest-plugin.md) §1 (one item per check, four states);
  [ADR 0014](0014-what-may-ride-a-schema-bump.md) §1 (the passenger rule)
- Amends: [ADR 0012](0012-the-reading.md) §3 — one member joins the closed
  `TallyKind` list, with the sentence that earns it (§8)
- Turns into surface: [`AGENTS.md`](../../AGENTS.md) §3 (one bad run is a draw
  until it repeats) and §6 (the exit codes are the contract) — §5 below is the
  one place where a single run is *not* a draw, and it says why
- Touches: nothing in `CLAUDE.md`'s *fixed* section. Decision 3 is upheld: the
  canary's checks are checks, with mandatory thresholds, and the flag removes
  none of them

## Context

A suite measures a system. The system it measures is named by an alias —
`claude-sonnet-5`, `gpt-6-astra`, a deployment name on a gateway — and an alias
is a pointer. It rolls. When it rolls, every number in the suite is measured
against a different model than the baseline was, and the suite has no way to
know: the scores move a little, as scores do, and the reader attributes the
movement to the prompt they edited that morning.

digline already has half an answer, and it is the declared half. ADR 0005 §9
records what the provider *said* answered — `resolved_model` — so an alias that
rolled from `claude-sonnet-5` to a dated snapshot shows up as a named delta, and
0.8.0 measured exactly that on Anthropic. The half that is missing is the half
where nobody says anything. Bedrock does not return a resolved model. A
customer's own gateway returns whatever that gateway's author chose to write. On
those, the plate is silent and today the suite is silent with it.

The other half of the answer has to be **behavioural**: a case whose whole job is
to be sensitive to the model behind the alias, watched for movement rather than
counted toward a metric. That is what this record adds, and the two halves are
complementary in the strict sense — the plate declares, the canary observes, and
neither is a substitute for the other. Where the plate speaks and the canary
moves, you have confirmation. Where the plate is silent and the canary moves, you
have the only signal there is.

There is one hazard, and it is the reason the floor in §6 is not optional. A
canary that fires on ordinary noise is a canary people learn to ignore, and a
gate people learn to ignore is worse than no gate, because it is still red when
the real thing happens.

## Decision

### 1. `canary` is a field on `Case`, and it is a declaration

    Case.canary: bool = False        ->  CaseResult.canary: bool = False
                                    ->  CaseOutcome.canary: bool = False

The flag says *this case is here to watch the model, not to measure it*. Nothing
in the mechanics depends on what the case contains: whether a fixed question with
a near-deterministic answer makes a good canary is the author's craft, and an
engine that tried to check it would be inventing a judgement nobody asked for.

It is **case data**, which is what puts it outside `config_hash` under ADR 0014
§1, and it rides through the declarative form for free — the loader builds cases
from their declared fields, so `"canary": true` in the cases file needs no line
of its own.

Two refusals at construction, both of them the kind that is cheaper to meet in a
sentence than in a number:

- **A canary declares no `group`.** It is excluded from every aggregate (§2), so
  a group it named would either count nothing or — where it is the group's only
  member — produce a per-group aggregate with an empty denominator, which is an
  `error` gate nobody declared, appearing because a case was flagged.
- **A canary needs no `label`,** and is exempt from the requirement that every
  case carry one as soon as an aggregate counts a confusion matrix. It is not in
  the population being measured, so a mark for it would be a mark nobody counts.

The flag is read from the run being judged. If somebody flips it between runs,
the case moves into or out of the counted population and the aggregates move
accordingly — visible as aggregate deltas, which is what it is.

### 2. Excluded from every aggregate, and the list is exhaustive

"Excluded from the aggregates" is four words that touch eleven counting sites,
so here they are, with what each one does:

| site | canary |
|---|---|
| `build_matrix` → `tp/fp/tn/fn`, `considered`; precision `tp+fp`, recall `tp+fn`, f1 `2tp+fp+fn` | **excluded**, and counted — §3 |
| the per-group instances of the same, filtered in the driver (ADR 0010 §7) | excluded by the same flag: one rule, both scopes |
| `per_sample_outcomes`, which sizes the aggregate's interval (ADR 0006 §7) | **excluded from the length check**, and passed through — §4 |
| `Suite._check_aggregates`' label requirement | exempt — §1 |
| `Suite.groups()` | contributes nothing: a canary declares no group |
| `planned_calls` / `CallPlan.cases` | **counted.** It is called, and the announced bill has to match the invoice |
| `run_tally`'s cases and checks | **counted.** It ran, and the canary has its own row so it is not read as coverage |
| `unjudged_cases`, `errored_verdicts` | **counted.** A canary that cannot be judged is a broken instrument: exit 2, by ADR 0001 §1 |
| `promote_baseline`'s errored check | **counted.** A run that could not judge its canary is not an approved reference |
| `Headline.counts`, the `within_noise` tally, every delta table | **counted.** They are real deltas about a real check and removing them from the table would hide the thing this ADR exists to show |
| `wire.runs_json`'s `cases` | counted |

The shape of the list is the decision: a canary is excluded from **metrics** and
included in **everything that reports what happened**. It is not a hidden case.
It is a case whose verdicts are not evidence about the population.

### 3. The exclusion is counted, and the count travels

`Matrix` gains `canary_excluded`, beside `suspended_excluded`,
`errored_excluded` and `unlabelled_excluded`, and it goes into `as_metadata()`
with them: all integers, all crossing a boundary, so world 2 sees the shape of
what was left out without seeing a case.

A number that is excluded silently is a number you cannot check. `precision
0.800000 = 12/15 (15 counted, 0 suspended, 0 could not be judged)` is a sentence
a reviewer can reconcile with a case file; the same sentence over a suite whose
case file holds sixteen cases, with nothing accounting for the sixteenth, is one
they cannot.

The clause renders **only when the count is non-zero**. Silence at zero is the
rule the headline's noise clause already follows, and here it has a second
reason: rendering it always would rewrite the `reason` string of every aggregate
verdict in every committed baseline, in every suite that has no canary at all.

### 4. The canary must not cost the run its noise interval

`per_sample_outcomes` gives up — returns nothing, so no aggregate records an
interval — unless every judged case carries the same number of samples. That is
correct and deliberate: reading across cases sampled differently would align
sample 2 of one with sample 3 of another and call it a measurement.

It is also a trap this flag walks straight into. A canary sampled differently
from the rest of the suite would silently delete the noise interval of **every
aggregate in the run**, and the loss would look exactly like a suite that had not
been sampled.

So canary outcomes are left out of the length check and passed through to
`build_matrix`, which excludes them anyway — the treatment suspended and errored
cases already get in that function, for the same reason: they carry no samples to
align, and they are not in the count that is being aligned.

### 5. A canary moved is exit 1, and it is not `worse` by another name

`Headline` gains `canary_moved: bool`, and `exit_code()` returns `EXIT_WORSE`
when either that or `worse` is true, with a regression keeping precedence in the
sentence.

It cannot ride `worse`, and the reason is not tidiness. `worse` is `regressed >
0`, and a canary that **improved** is a changed model just as loudly as one that
got worse — the whole point of the case is that its score is a fingerprint, not a
quality. Folding it into `worse` would make the headline say *one check got
worse* about a check that got better, which is the report telling a reader
something untrue in order to produce the right exit code.

So: two facts, one number. A changed model is a reason to stop, and the reason
the pipeline stops is legible in the field beside the code.

This is the one place in the product where a single run is not a draw
(`AGENTS.md` §3). The asymmetry is deliberate: a wobbling score is evidence about
a noisy system, while a canary outside its measured interval is evidence about
*which system answered*. Re-running cannot settle the second question, because
the second run asks the same alias the same thing.

### 6. What counts as moved, and the floor that makes it mean something

Moved is the movement, not the direction:

    regressed | improved   ->  moved
    unchanged (by tolerance or by noise)  ->  not moved
    errored     ->  not moved; it is unjudged, exit 2
    new | missing  ->  not moved; a case was added or removed

And the floor: **a suite that declares a canary declares `samples >= 2`**,
refused at `Suite.__post_init__` with a sentence. The shape is the one
`min_agreement` already has — mandatory as soon as `samples > 1`, because a
threshold on a noisy value that nobody chose is a green light nobody gave. Here
it is the mirror image: a canary with no measured interval turns every wobble
into a stop, which is a red light nobody chose.

With an interval, the sentence a reader gets is worth acting on: *the canary
moved from 0.910000 to 0.640000, beyond the noise of this check (0.880000–0.930000
across 3 samples)*. Without one, the report can only say the score changed, and
ADR 0006 §5's third branch — the interval is not known — is exactly the branch a
canary cannot afford to be in.

The cost is stated rather than buried: `samples` is suite-wide, so a canary in a
forty-case suite multiplies **every** case's calls. That is the honest price of
the floor at this release, and it is the reason §"Not decided here" hands
per-case sampling its brief instead of improvising one here.

The floor also inherits ADR 0006 §5 unchanged: the interval is the **baseline's**,
so a canary cannot widen its own excuse by being unstable today.

### 7. The sentence, and where it sits

One clause, in both locales, placed immediately after the target-configuration
clause and before the judge's:

> **the model under this alias likely changed** — the canary `alias-probe` moved
> from 0.910000 to 0.640000, beyond the noise of this check (0.880000–0.930000
> across 3 samples)

*Likely*, and the word is chosen. The canary observes behaviour; it cannot read a
model id, and a suite whose canary moved because somebody edited the prompt it
shares with the rest of the suite is a suite that has told the truth about a
change with the wrong cause. The report states the observation and the
consequence and stops short of the diagnosis — which is the line ADR 0012 drew
for `explain` and is the same line here.

The placement follows the meaning. The target-configuration clause says what the
system *declared*; the canary says what the system *did*, which is the stronger
statement of the two and belongs immediately after it. The judge clause stays
last, because a moved scale makes even the canary's own numbers less comparable.

Where the plate and the canary agree — `resolved_model` changed **and** the
canary moved — both clauses print. Neither is redundant: one is what the provider
said, one is what the suite saw, and a release where they disagree is a release
somebody should look at closely.

### 8. The front ends

**`explain`** gains one `TallyKind`, `canary`. The list is closed by ADR 0012 §3,
so this is an amendment, declared in the header, and it earns its place by that
section's own test: it says something the report says, and a reading that omitted
it would describe a run whose exit code it could not account for.

**`pytest-digline`** needs no new state and one new rule. A canary check is an
item like any other, and a canary that moved is **FAILED** — including when its
`Outcome` is `improved`, which is the one place the plugin's per-row mapping
cannot be read straight off `outcome == "regressed"`. The rule goes beside the
existing one in the same order `exit_code()` applies it, and the reason string
says which fact produced the failure. It ships in the plugin release that
follows this one; the plugin's floor rises to the digline that carries the field.

**The wire** gains `canary_moved` on the headline and `canary` on each delta, so
a pipeline can tell which row produced the exit code. `OUTPUT_VERSION` stays at
`1`: added keys, no byte of change to what an existing consumer parses.

**`Headline`'s docstring** says eight facts today and will say ten, counting this
one and ADR 0015 §8's. Each of the two records its own addition, which is how the
count has grown every time.

### 9. Compatibility

`SCHEMA_VERSION` 9 → 10, as the second passenger of the bump ADR 0014 governs.
The flag is written to the document **only when true**, so the migration writes
nothing at all and a case from before the idea existed reads as what it was: not
a canary. That is also what keeps the promise below — a suite with no canary
produces the file it produced before, rather than the same file with
`"canary": false` added to every case of every committed baseline.

No baseline needs re-promoting. `config_hash` does not move, by §1 and ADR 0014
§1 — and the consequence that *does* follow is stated there rather than hidden
here: flagging an existing case changes every aggregate's value, because its
denominators lose that case, and that arrives as a delta against its tolerance
exactly as removing the case would.

A suite that declares no canary sees no behavioural change: no clause in the
sentence, no row in the tally, no new refusal at construction, and
`canary_excluded` silent at zero.

## Consequences

**A rolled alias becomes visible on providers that do not name the model.**
That is the whole gain, and it is the half of ADR 0005 §9 that no amount of
recording could reach.

**The floor makes a canary cost something.** Two samples is a doubling of a
suite's calls, and some users will decline. Declining is a legitimate answer —
the flag is opt-in — and it is better than a canary that fires on noise and
teaches its owner to ignore a red line.

**Two facts now produce exit 1, and the headline says which.** A pipeline that
reads only the number sees no change in kind; a reader sees the reason in a
field.

**A canary that moved when the prompt moved will be misread at least once.**
Both clauses print in that case — the artifact clause and the canary clause — and
the word *likely* is doing the work. The failure mode is a person looking at a
prompt change instead of a model change, which is a cheap mistake to make and an
obvious one to correct.

**Somebody will want the canary to exit 2 instead of 1.** It is not an error:
nothing failed to run, and `EXIT_UNJUDGED` means the harness could not answer. A
changed model is an answer, and it is the one that should stop a release.

## Alternatives considered

**Compare `resolved_model` and be done.** Rejected: it is already there, and it
is silent on exactly the providers this is for. Bedrock does not return one, and
a customer's gateway returns whatever it chose to write.

**A separate canary suite.** Rejected. It would be a second suite to run, a
second baseline to promote and a second exit code to reconcile, and it would
measure the model under a configuration nobody uses. The canary has to be in the
suite, under the same target, the same sampling and the same judge, or it is
watching a different system.

**A canary counted in the aggregates like any other case.** Rejected: it is a
case chosen for its sensitivity, so it would drag precision and accuracy around
for reasons that have nothing to do with the population being measured. The
number that gates a release must count the cases the release is about.

**Excluding the canary from the delta tables too.** Rejected: then the run that
exits 1 has no row explaining why, which is the report withholding the fact it
was built to carry.

**Folding `canary_moved` into `worse`.** Rejected in §5. It would make the
headline say a check got worse about a check that got better.

**A dedicated `canary` threshold or a special assertion.** Rejected: the canary's
checks are ordinary assertions with mandatory thresholds, and a special one would
be a second way to declare a bar — with fixed decision 3 to re-establish for it.
What is special about a canary is which denominators it is in and what its
movement means, and both are properties of the case.

**No floor, with a louder sentence instead.** Rejected in §6. The sentence cannot
distinguish noise from a rolled alias if nothing measured the noise, and the
first false alarm is what teaches a team to stop reading the clause.

## Test plan

Beyond a failing case for every new rule, which the conventions already require:

**The denominators, one assertion per row of §2's table.** A fixture suite with
one canary and a known matrix asserts every figure: precision, recall, accuracy
and f1 unchanged by the canary's verdict, `canary_excluded` at one, `considered`
short by one, the per-group instances likewise, `CallPlan.cases` including it,
`run_tally` including it, `Headline.counts` including its delta.

**The interval survives the canary.** A suite at `samples=3` with one canary
records an aggregate noise interval; the same suite is asserted to still record
one when the canary's own verdict errors. This is the §4 trap and it is the test
that would catch it silently reappearing.

**Moved, in both directions.** A canary whose score dropped and a canary whose
score rose both produce `canary_moved` and `exit_code() == 1`; a canary inside
its baseline interval produces neither; a canary that errored produces
`exit_code() == 2`; a canary that is `new` or `missing` produces neither.

**The floor refuses.** `Suite(..., samples=1)` with a canary raises, and the
message names the flag and the floor. A suite with no canary at `samples=1`
still constructs, which is the assertion that proves the refusal is scoped.

**The two refusals of §1.** `Case(canary=True, group="travel")` raises;
a suite whose aggregates require labels constructs with an unlabelled canary and
raises for an unlabelled ordinary case, in the same test, so the exemption is
visibly narrow.

**Both locales**, and the no-advice gate of ADR 0012 §5 over the new strings:
*likely changed* is an observation, and the gate is what keeps the next edit of
that sentence from turning it into advice.

**The default is byte-identical.** A suite with no canary produces the run file
the previous release produced, modulo `schema_version` and `digline_version`.

## Not decided here

**Per-case sampling** — `Case(samples=N)`, which would let a canary carry its own
floor without multiplying the suite's bill. It is the companion question to §6
and it is deferred with its brief written, because it collides with a rule rather
than merely extending one:

- `min_agreement` is a `Ratio` over `Suite.samples` and is validated against it;
  a per-case count leaves `"2/3"` with no denominator.
- `samples` is in `config_hash` **because it changes how confidently every check
  is judged**, and cases are deliberately outside `config_hash`. A per-case
  sample count is case data that changes judging confidence, and the two rules
  meet head-on.
- `planned_calls` stops being one product, and the announced sentence with it.
- `per_sample_outcomes` meets §4's problem in general rather than for one flagged
  case.
- The report's "across N samples" sentences stop being one number per run.

That is an ADR, not a flag.

**Multiple canaries, and whether they should agree.** Nothing here forbids two,
and two that disagree is interesting rather than contradictory. A rule about
quorum would be inventing a statistic before anybody has run two.

**A canary that carries its own alias.** The suite has one target, so the canary
watches the model the suite uses. Watching a *second* alias — a model you are
considering rather than using — is a matrix question, and the matrix is a loop
above the driver.
