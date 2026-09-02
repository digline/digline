# ADR 0006 — Repeated samples and the noise floor

- Status: accepted — implemented on `adr-0006`; ships in core 0.4.0
- Date: 2026-09-02
- Amended: 2026-09-02 — §6 records what the implementation does with the
  interval on a flip, and §10's example copy is replaced by the wording that
  shipped. Both are corrections made *by* writing the code: nothing above
  them changes, and neither was a decision taken twice
- Assumes: [ADR 0001](0001-verdict-not-score.md) §3 (three states, and a flipped
  outcome is never noise), [ADR 0002](0002-three-worlds-and-where-the-data-lives.md)
  §2 (the payload stays where it is born, the verdict travels),
  [ADR 0004](0004-every-plugin-is-a-target-and-a-judge.md) §2 (sampling
  multiplies the calls: `samples=5` with `Repeated(n=3)` is fifteen judgements
  per case), [ADR 0005](0005-the-configuration-of-the-system-under-test.md) §5
  (a change is reported, never a refusal, and `unknown` is never a finding)
- Touches: fixed decision 3 (no vacuously green assertion) and fixed decision 9
  (what crosses a boundary), both in `CLAUDE.md`

## Context

A model asked the same question twice answers twice. digline already knows
this: `Suite.samples` calls the target N times per case, `Repeated` asks one
assertion N times about one output, and both fold through `combine_samples`,
which records `agreement` and `spread` beside the score. The machinery to
*observe* the wobble has been there since the classifier example was written.

What is missing is the consequence. `compare()` reads one number against
another and knows nothing about how much either of them moves on its own. So a
suite that sampled five times, measured a spread of 0.20, and then dropped by
0.05 is reported as a regression in the same words as a suite that never
wobbles and dropped by 0.05. The first sentence is false and the second is
true, and the report cannot tell them apart.

The event that forced this is recorded in the fixtures: the same suite, the
same `config_hash`, three runs inside fifteen minutes. One case went 5/5, then
2/5, then 5/5 again, and the run-level accuracy moved by one case in twenty-one
and came back. Nothing changed — not the prompt, not the model, not the
thresholds. digline reported a regression, a developer went looking for it, and
there was nothing there. A tool that cries wolf on its own measurement error
teaches people to promote past it, which is the failure mode that ends with
nobody reading the report at all.

Two further things are missing today.

**A scalar cannot say how far it moves.** `combine_samples` folds the samples
into one number and records `agreement` and `spread` in the metadata beside it,
where nothing reads them. The fold is lossy exactly where it matters: an outlier
sample and a genuinely lower score arrive at `compare()` looking identical, and
the raw values that would tell them apart are not in a form any rule can act on.

**Nothing declares the multiplied bill.** `samples=5` quintuples the calls and
the only place that shows is the invoice. `ProviderTarget.preflight` refuses an
unpriced model before the run and then says nothing about how many calls the
run is about to make.

## Decision

### 1. What is repeated is the target's answer

`Suite.samples` stays what it is: N calls to the target per case, each sample
evaluated by every assertion exactly as one call is today. This ADR settles
nothing about repeating the *judge*. `Repeated` continues to exist, continues
to wrap one assertion around one output, and continues to fold through the same
function — but whether a rubric should be asked three times, and what its own
noise floor would mean, is a separate question and is deliberately left open.

The two are composable and the composition is unchanged: `Repeated` folds its
own samples first and hands one verdict per target-sample to the outer fold.

### 2. The scalar of a sampled check stays the mean

`combine_samples` continues to return the **mean** of the per-sample scores,
rounded at `FLOAT_PRECISION`, with the reason it already writes: `mean of 5
samples (…)`. Nothing about the fold changes. Everything this ADR adds sits
*beside* the scalar, in §4, and that is the whole correction — the defect was
never that the centre sat in the wrong place, it was that one number cannot say
how far it moves.

**The brief's pattern is a special case and not a parallel path.** Where the
samples are binary — the `agrees_with_mark` shape, `_binary` returning 1.0 or
0.0 — the mean of five folds into 0, 0.2, … 1.0, so "3/5" is 0.6, which clears a
threshold of 0.5. A mean over binary samples *is* the majority vote, and a
threshold at one half is what says so. There is no separate majority rule to
write and none to maintain.

**The median was considered and lost**, and the reasoning is kept here because
it is the argument for where robustness actually belongs.

It was proposed against a real defect: one grader returning 0.1 where four
returned 0.9 drags a passing check to 0.74, and the mean lets a single outlier
move a verdict across a bar that four samples agreed was cleared. The median is
immune to that, and on binary samples it is exactly the majority vote — which
made it look like the same rule stated better. It costs three things, and
together they are decisive.

- **It does not preserve status on a graded check.** Five samples of 0.51, 0.51,
  0.51, 0.0, 0.0 are a fail by mean and a pass by median. Every sampled baseline
  in existence records a scalar the new fold would not reproduce, and the honest
  response to that is re-promoting every one of them — a cost paid by every user
  for a change none of them asked for.
- **It deletes the tolerance on a binary check.** `tolerance=0.4` on
  `agrees_with_mark` means "up to two samples changing their mind is noise", and
  that sentence is true only while the score is a mean over five binary votes.
  Under the median the score is 0.0 or 1.0, every change is a flip, and a flip
  ignores tolerance by ADR 0001 rule 3. A declared, measured, documented control
  would have become dead code.
- **It throws away the resolution the noise floor needs.** A median-scored
  binary check has no interior: 5/5 and 3/5 are both 1.0. The very movement §5
  exists to recognise as noise would have stopped being visible in the score.

**Robustness against an outlier sample belongs in the recorded samples, not in
the scalar.** §4 writes down the raw values and the interval they span, so a
reader who wants to know whether four graders agreed and one did not can see
precisely that, and §5 lets `compare()` act on it. The outlier is neither
averaged into invisibility nor silently discarded by a median: it is recorded.
That is the shape of every other decision here — the summary travels, and the
thing it summarises is still there to be checked.

### 3. The folded metadata and the total spent are unchanged

`_folded_metadata` keeps averaging the numeric metadata the samples measured and
keeps dropping the non-numeric values they disagree on; `TOTAL_COST_KEY` keeps
summing `cost_usd`. Stated rather than left implicit, because §2 nearly moved
it: a fold that changed the centre of the score would have had to say whether
the cost moved with it, and the answer would have been no. `CostBudget` judges
what one call cost — which is what the user pays per answer — so raising
`samples` still cannot trip a budget on its own, and the sum recorded beside it
is the bill.

### 4. The run records N, the raw samples and the interval — and they travel

`Score` gains three optional fields, **absent when N is 1**:

| | |
|---|---|
| `samples` | the raw per-sample scores, in the order they were produced |
| `sample_min` | the lowest |
| `sample_max` | the highest |

Fields on the value rather than more keys in `metadata`, because `compare()`
reads them to decide an outcome and a rule that reads a stringly-keyed bag is a
rule one typo disables silently. `agreement`, `spread` and `errored_samples`
stay in `metadata`, where they are reported and not acted on.

They **travel**. Decision 9 lets the metadata *measured by an assertion* cross a
boundary, and these are measurements of the system's own variability in the same
sense that `spread` — which already travels — is one. This is stated rather than
inherited: as `Score` fields they bypass `travels()`, so `redact()` must copy
them explicitly, and the software house seeing how unstable a check is without
seeing what it judged is exactly the arrangement ADR 0002 exists to produce.

A serialized verdict omits all three when N is 1 — absent, never `null` — so a
run file from an unsampled suite is byte-for-byte the file that suite produced
before this ADR.

### 5. The noise floor is a rule of `compare()`, never of `Verdict`

A drop is a regression only when it leaves the interval the **baseline** observed
across its own samples. Concretely, in the numeric branch of `compare()` — rule 4
— after the existing tolerance check:

- the baseline recorded `sample_min` and `sample_max`, and the current score
  falls inside `[sample_min, sample_max]` → **`unchanged`**, with the fact of §9
  attached;
- the baseline's dispersion is **asymmetric** — it varies below its own score
  and not above, or the reverse — and the move is on the side that has it → the
  interval on that side is the floor, and the side without dispersion keeps the
  absolute rule. Noise is not assumed to be symmetric because it usually is not:
  a check that occasionally fails to find the citation drops and never rises;
- **neither side has an interval** — the baseline predates this ADR, or the
  suite runs at `samples=1` → today's absolute rule, unchanged, and the report
  says the noise of this case is not known rather than implying there is none.

The reference interval is the **baseline's**, not the current run's, and the
asymmetry is deliberate: the baseline is the promoted, reviewed measurement, and
letting a noisy new run widen its own excuse is how a regression hides inside a
model that got less stable.

Nothing here touches `Verdict`. A score below its threshold is `fail` whether or
not it is within noise — noise explains a movement, it does not excuse a
result — and the three states of ADR 0001 are untouched, in `--json` too.

### 6. Where the noise floor does not reach

**A flipped outcome is never within noise.** ADR 0001 put rule 3 above rule 4 for
this reason and the noise floor changes nothing about it: pass → fail is
reported as a regression whatever the samples did. This is not a limitation to
work around, it is what makes §5's guardrail true without extra code — a drop
through the threshold *is* a flip.

**So a flip carries no interval either, and the delta does not print one.** The
interval is the floor's evidence, and the floor does not reach a flip — rule 3
decided it before §5 was consulted, so there is nothing the movement was judged
against. Printing one anyway would invite the reader to check the score against
it and find, quite often, that the score is *inside*: `0.800000 → 0.400000`
across a threshold of 0.5, on a check whose baseline votes ran 0.0 to 1.0, is
exactly that shape — reported, and inside. `within_noise` is `false` on a flip
because it is false, and `noise_min` and `noise_max` are absent because nobody
measured this one against them.

**An interval of zero width is not a noise floor.** A check whose baseline
samples were unanimous — five out of five, which is the ordinary case for a case
that is not near the boundary — has `sample_min == sample_max`, so there is no
interval, so the absolute rule holds and every later change of mind is reported.
That is right rather than unfortunate: a case decided five times out of five and
now decided three times out of five has moved, and one case is a diagnosis. The
noise floor earns its keep where the dispersion actually was — on a case that
was already wobbling, and on the aggregate of §7.

### 7. The aggregate gets a noise interval of its own

This does not appear in the brief and the fixture cannot be read without it.

A `RunAssertion` — precision, recall, accuracy — is computed once per run from
the folded per-case verdicts, so it has no samples and §5 would never reach it.
But the fixture's finding *is* an aggregate: accuracy moved by one case in
twenty-one and came back. Under §5 alone that case would still be reported as a
regression, and this ADR would have failed at the one thing it was written for.

So: the driver evaluates each aggregate **once more per sample index** — the
sample-0 verdict of every case, then the sample-1 verdict of every case, and so
on — and records the resulting N values as the aggregate's `samples`,
`sample_min` and `sample_max`. It costs nothing: the samples already exist, a
per-sample status is `score >= threshold` on a verdict that already carries
both, and a `RunAssertion` is a pure function.

**The recorded aggregate score does not change.** It stays what it is today —
computed from the folded per-case verdicts, which are the suite's answers — and
the per-sample aggregates supply the interval and nothing else. They answer a
different question, "what would a single run have said", and that question's
only job here is to size the noise. Keeping the two apart is also what leaves
every threshold measured against the current definition still valid.

`min_agreement` stays out of this. It is a floor on a check that cannot repeat
its own verdict; an aggregate has no verdict to repeat.

### 8. Preflight declares the multiplied cost, the report shows what was spent

Before the first call, the run announces `cases × samples × judge repeats`
calls. It is arithmetic over the declared suite — `Repeated.samples` is already
reachable by the walk `judge_config` performs — so it needs no provider, no
price list and no protocol change, and it is the figure that surprises people:
twenty cases at `samples=5` is a hundred calls, not twenty.

A **money** estimate is not part of this ADR, and the reason is a protocol
boundary. `Pricing.cost` needs a `Usage`, which does not exist before the call,
so an estimate has to come from the target itself — an optional method alongside
`preflight()` and `artifacts()`, something of the shape `estimate_usd(cases,
calls) -> float | None`, declared by the targets that can price a call in
advance and absent from the ones that cannot. That is a change to the
`digline.run` protocols and therefore a release of every plugin: a decision with
its own blast radius, which belongs in an ADR of its own rather than in a
subclause of this one. Deferred, not refused. What is *actually* spent is
already recorded — `TOTAL_COST_KEY` sums it per check, and the report shows it.

### 9. "Within noise" is a fact beside the verdict

`AssertionDelta` gains `within_noise: bool` and the interval it was judged
against. `Outcome` gains no member: a movement within noise is `unchanged`,
which is what it is. The fact rides beside it, in `--json` as in the document,
for the same reason the three states are not four — a reader who has learnt the
vocabulary should not have to learn it again.

### 10. The copy, in both locales

The word is **noise** / **rumore**. New keys in `report/text.py`, present in
`en` and `it`, and `headline()` keeps its mandatory `locale`:

- headline, as its own clause after the one about what got worse:
  `1 check moved within noise.` / `{count} checks moved within noise.` — and
  silent at zero, like the artifact clause, because a sentence about noise
  nobody measured is one the reader learns to skip
- per check, beyond the noise: `Score fell from 0.900000 to 0.600000 — beyond
  the noise of this check (0.850000–0.950000 across 5 samples).`
- per check, within it: `Score moved from 0.900000 to 0.750000 — within the
  noise of this check (0.600000–1.000000 across 5 samples); not counted as a
  regression.`

**"This check" and not "this case"**, which is what the first draft of this
section said. An aggregate is a check and is not a case, and §7 gives it an
interval of its own — so the sentence had to name something true at both scopes.
The row already carries the case in its own column.

ISO dates and the decimal point stay unlocalized, and the interval is rendered
at `FLOAT_PRECISION` like every other score, so two renderings of one run still
diff line by line.

### 11. Compatibility

`SCHEMA_VERSION` goes 8 → 9, additively, and `_STEPS` gains a step:

- a document with no sampled verdict is unchanged but for the version number —
  an old run *is* an N=1 run, and N=1 records nothing;
- a document that already sampled carries `metadata["scores"]`, so `samples`,
  `sample_min` and `sample_max` are **derived from it**, not invented. Reading a
  list that is already in the document is not the guessing `migrate.py` refuses,
  and it is the difference between every promoted baseline being a noise floor
  on the day of the release and being one after everybody re-promotes.

Nothing already recorded becomes wrong. §2 leaves the scalar where it was, so
this release is an addition to every stored run and a contradiction of none: no
baseline needs re-promoting, and no example needs re-recording.

Core goes to 0.4.0. No plugin protocol changes, so no plugin is touched — with
the single exception noted in §8, which is why the money estimate is not in this
ADR.

`Suite.config_hash()` already covers `samples` and `min_agreement`, so a suite
that starts sampling already needs a deliberate re-promotion. Nothing new is
required of the user for the noise floor to begin working.

## Consequences

**No sampled baseline is invalidated.** The scalar every stored verdict carries
is the one this release computes, so nothing has to be re-promoted, no example
has to be re-recorded, and the classifier's measured thresholds and its
`tolerance=0.4` keep meaning exactly what its README says they mean. That is a
consequence of §2 rather than a happy accident: it was the deciding argument
there.

**Two noise controls now exist, and a suite may carry both.** `tolerance` is
*declared* — a reviewer decided this much movement is acceptable. The interval
of §5 is *measured* — this is how much the system moves on its own. They are
checked in that order, both produce `unchanged`, and the reason says which one
spoke, so a reader is never left to guess. A suite that set a generous tolerance
as a hand-rolled noise floor — the classifier's `0.4` is precisely that — can
shrink it once the measured floor exists. Nothing forces it, and nothing breaks
if nobody does.

**Old sampled runs become noise floors without being re-run.** §11 derives the
interval from `metadata["scores"]`, which every sampled run already carries. The
floor works against baselines promoted months ago, on the day of the release.

**A wide-open baseline excuses everything.** A check whose baseline samples ran
0.0 to 1.0 has a noise floor that admits any movement. That is arithmetically
correct and practically useless, and it is the right thing to make visible
rather than to clamp: a check that unstable has nothing to say about
regressions, and `min_agreement` is the control that already refuses it.

**An aggregate costs N extra evaluations per run.** Pure arithmetic over
verdicts that already exist — no call to a target, no call to a judge — so the
cost is real and negligible, and it is the only new work §7 adds.

## Alternatives considered

**The median as the scalar.** Considered at length and rejected in §2, where the
reasoning is recorded rather than summarised: it is the argument for putting
robustness in the recorded samples instead of in the number that stands for
them.

**The variance or the standard deviation instead of the observed interval.** It
assumes a distribution, and five samples are not enough to earn the assumption.
The min and the max are what was seen, which is a fact rather than a model, and
they are what a reader can check against the raw samples printed beside them.

**A fourth `Outcome`, `within_noise`.** Rejected for the reason ADR 0001
rejected a fourth state: the vocabulary a reader learns is the product's
surface, and `unchanged` with a stated reason says the same thing without
widening it.

**Folding the noise floor into `tolerance`.** A tolerance is *declared* — it says
what a reviewer decided is acceptable. A noise floor is *measured* — it says what
the system does. Collapsing them would leave nobody able to tell a judgement
from an observation, and would delete the ability to say "this moved more than
you allowed, and less than it moves by itself".

## Test plan

Beyond a failing case for every new rule, which the conventions already require:

**The canonical within-noise case comes from the fixtures, not from a
hand-written approximation.** `digline/brief` holds two runs under `fixtures/`
with a README: the same suite at the same `config_hash`, twenty-one cases, one
of them going 5/5 → 2/5 → 5/5 inside fifteen minutes, accuracy moving by one
case and returning. When implementation starts, the core test imports those
fixtures — reduced if their size warrants it, never paraphrased — so the case
this ADR was written for is the case the test asserts.

The middle run must read as **moved within noise** at the aggregate, per §7. Its
per-case flip is still reported, per §6, and that is not a failure of the test:
one case is a diagnosis, the aggregate is the gate. The third run must return to
the baseline with no promotion in between. A change that makes the middle run
read "got worse" again is a change that undoes this ADR.

**The other two must keep passing, unchanged.** `examples/langchain` runs at
`samples=1`, so §4's absence rule is what keeps its run files byte-identical;
`examples/classifier` runs at `samples=5` over a mean-folded binary check, so
§2's reversal is what keeps its recorded runs, its baseline and its README's
measured numbers valid.
