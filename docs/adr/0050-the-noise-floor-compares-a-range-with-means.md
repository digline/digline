# ADR 0050 — The noise floor compares a range of single samples with a movement of means

- Status: accepted 2026-10-20, by Alessandro Prandini, the text first and before
  any code, the way
  [ADR 0048](0048-the-versions-a-suite-holds-and-the-one-in-force.md) was.
  Nothing in it is implemented. The release question left open at the end of
  this record — whether a suite keeps the floor for one release with a warning
  or loses it at once — is answered with the second: no flag and no window, on
  the argument ADR 0031 §3 makes against a flag as a standing permission, and
  because the one deprecation this project allowed, `SuiteRuns.listing` in
  0.26.0, is still here. Amended 2026-10-21, decision 1: the floor is a
  multiple of the standard error of the movement, not of one mean.
  Proposed 2026-10-15. **What it decides was ruled before it was
  written:** the maintainer ruled the decision below on 2026-10-15, on #496.
  The text is not yet accepted, and nothing in it is implemented. #496 stays
  open: this record answers its question, and the issue closes when the code
  lands. After it landed, and before acceptance, the maintainer added a fourth
  item to *Four things this carries* on 2026-10-17: whatever prints the floor
  prints what it was computed from, which answers ADR 0006's third reason. The
  same day the third item named the page its sentence will live on and the test
  that will hold it; until that code lands, nothing holds it. On 2026-10-18,
  still before acceptance, the maintainer added a fifth item, and the heading
  became *Five things this carries*: the floor is a lower bound when its samples
  come from a replay. The same day *What this ADR does not claim* gained two
  limits, on the one measurement of variation between runs this project has:
  what it covers, and what it does not say. On 2026-10-20, still before
  acceptance, the maintainer corrected the break's description in the first
  item, named in the second item the two things `docs/guide.md` must withdraw,
  carried the aggregates' exclusion from *Context* into the second decision,
  gave a tied graded sample set to the tolerance in the first decision and the
  fourth item, and noted two sentences of *Context* superseded by digline#635.
  *The block above is the proposed phase's own text, kept as written, and speaks
  from that phase.* The start of this status carries what is true now, and
  `Shipped:` below says that no release carries it yet
- Shipped: unreleased
- Date: 2026-10-15
- Opens: **nothing on landing.** No code, no `SCHEMA_VERSION`, no
  `OUTPUT_VERSION`. The code that implements it is a break, said under *Five
  things this carries*
- Amends: [ADR 0028](0028-the-rules-that-moved.md) §4, which left a direction
  for `samples` to an amendment that says which half wins and why; the
  amendment is there, in its own words. [ADR 0006](0006-repeated-samples-and-the-noise-floor.md)
  §5, §6 and the variance alternative under *Alternatives considered* carry
  dated notes pointing here. [ADR 0014](0014-what-may-ride-a-schema-bump.md) §1,
  whose first condition a declared width cannot satisfy as written and which is
  extended there
- Assumes: [ADR 0006](0006-repeated-samples-and-the-noise-floor.md) §5 (the
  floor is the baseline's, never the current run's), §7 (the aggregate's
  interval) and §12 (agreement counts an errored sample against itself)
- Touches: nothing in `CLAUDE.md`'s *fixed* section
- Number: 0050. Swept on 2026-10-15, before a line was written, across
  `origin/main` (`2549e97`), every local and remote branch and tag (81 refs,
  after a fetch with `--prune`), the worktrees of this repository and the open
  pull requests (none). The highest number taken anywhere is 0049

## Context

*digline#496.*

**What the code does.** `_noise`, in `src/digline/core/compare.py`, builds the interval
`[sample_min, sample_max]` of the *baseline's individual samples*, and `Score`, in
`core/types.py`, refuses to exist unless those two are the minimum and the maximum of its
rounded samples. The value tested against that interval is the current run's score, which
for a case's check is the mean of its **judged** samples, not of all K. `Noise.covers` is
inclusive at both ends, at storage precision. `compare()` reaches the floor last: a verdict
present on one side only, an error, a flipped outcome, a moved denominator and the declared
tolerance are all decided before it.

*Amended 2026-10-20.* Since digline#635 (`bc84f52`), `_noise` does not build that interval
when it would be a point sitting on the baseline's own score: it hands over no interval at
all, because ADR 0006 §6 says an interval of zero width is not a floor. The description
above holds for every other case.

**First consequence: the floor can only widen the invisible zone.** `unchanged` is *within
the tolerance* **or** *within the floor*, a disjunction tried in that order. The floor can
only add movements to `unchanged`, never take one away. It is not a filter; it is an
enlargement.

**Second consequence: the two sides are not the same quantity.** On one side, the observed
range of single draws. On the other, a mean. The range of draws does not shrink as K grows —
more draws can only find a wider minimum and maximum — while the spread of their mean
shrinks with K. **So as K rises the floor widens while the quantity it judges becomes
steadier.** A noise floor should narrow as the measurement improves. This one does the
opposite, by construction, and no particular suite is needed to see it.

**Third consequence: for a binary check the floor is either nothing or everything.** When a
check's samples are 0 or 1 — which is not so when `Score.sample_means` is true, where each
sample is already a mean — `sample_min, sample_max` is `(0,0)`, `(1,1)` or `(0,1)`. A
unanimous baseline gives a point, with no effect. A baseline that is not unanimous gives
`[0, 1]`, which covers every possible score. For a check whose declared tolerance is `0`,
**the whole side of the threshold the baseline sits on becomes invisible**: every movement
that does not flip the outcome is reported `unchanged`, with no tolerance to appeal to. A
check written with `tolerance=0` to say *this must not move at all* is the check the floor
silences.

*Amended 2026-10-20.* Since digline#635 a unanimous baseline gives no interval rather than
a point. The consequence is unchanged — a point on the score never excused anything,
because a delta of zero is decided by the tolerance first — and what changed is what gets
printed.

**Fourth: for a binary check, below unanimity the floor concedes every same-side movement
there is.** Unanimity is a property of the outcomes, not of the scores: a binary check's
samples are 0 and 1, so a baseline divided on outcomes has the interval `[0, 1]`, which
covers every score, and the floor then excuses the largest same-side movement the
configuration permits. Measured at K=5 and a threshold of `0.5`, the largest same-side
movement and the largest the floor excuses are the same number in every case below
unanimity: `0.5` at `min_agreement` 2/5 and below, `0.4` at 3/5, `0.2` at 4/5, and nothing
at unanimity, where a baseline divided on outcomes cannot exist.

So the question is not how much the floor adds. It is how large a same-side movement the
configuration permits, and that is set by `min_agreement`, which has no default: a suite
that samples must declare it or it is refused, because *"the answer would default to
'any'"*. `min_agreement` is measured over all samples, errors included, so it errors the
verdicts whose agreement falls below it — those nearest the threshold, and those with too
many samples that could not be judged — and that is what bounds the movement.

What makes the floor unreachable for such a check, then, is a declared tolerance at or above
that number, and nothing else. One suite can run for months with the floor affecting no
comparison, and another, differing only in two numbers somebody chose by hand, can have
every same-side movement excused by it.

**For a check that is not binary this says nothing.** A baseline divided on outcomes there
has the interval of the scores it saw, not `[0, 1]`, and the floor concedes only what that
interval covers: a rubric baseline whose samples span `0.45` to `0.6` does not excuse a
same-side movement of `0.33`. What holds for every check, binary or not, is the second
consequence.

**Out of scope, and named.** A run-level aggregate's floor. `with_noise_interval` in
`core/aggregate.py` takes its interval from aggregates computed index by index while the
recorded score comes from already-combined verdicts (ADR 0006 §7), so there the compared
value is not a mean at all, and a committed baseline has been shown whose recorded score
sits outside its own interval. Nothing here decides that, and it is not the same defect.

**What this ADR does not claim.** How often each case occurs in practice, and what
`min_agreement` real suites declare. Neither is measured here.

Nor that the variation between runs is what the noise inside one run predicts, beyond a
single measurement. The only one in this project that sets the variance of the mean between
runs against the prediction from internal noise alone — 21 runs, two assertions, `0.000027`
against `0.000031` and `0.00132` against `0.00107`, one below the prediction and one above —
spans 27 minutes, and says so: *"they say nothing about drift over days or model
versions"*. Its author also records that K=3 is far from the K much greater than 1 that
Miller's appendix C asks for, *"so the floors above inherit the noise"*. That is [*The more
samples I took, the less my noise floor could see*](https://digline.dev/blog/more-samples-less-floor/),
lines 31, 50, 187 and 191 at `0d9edb5` of `digline/digline.dev`. Its scripts live in a
private repository, and nobody can re-run them, as the post itself says at line 213.

And that measurement does not say whether the outputs were fixed or generated again at each
run, so whether its variance between runs includes the target's is not known.

## The decision

*Ruled 2026-10-15.* The measured floor stays, and two things change.

1. **It compares means with means.** The quantity on the baseline's side becomes the
   dispersion of the mean of the judged samples, estimated from those samples, instead of
   the range of the samples themselves. The floor then narrows as K grows, which is what a
   floor is for. This is the direction ADR 0028 §4 left open, and the amendment there says
   which half wins and why.
   The dispersion of a tied sample set is zero, so a graded check whose judged samples
   happen to coincide would get a floor of zero width — the object ADR 0006 §6 refuses,
   and the one digline#635 stopped `_noise` handing over when its point was the baseline's
   own score — and a declared width does not rescue it, because any multiple of zero is
   zero. A tied sample set is the tolerance's business too, on the same ground the third
   item below gives binary checks.
   *Amended 2026-10-21.* The dispersion of one mean understates what the floor has
   to cover. What `compare()` judges is the **difference** between two means, and
   the dispersion of a difference of two means of K samples each is `√2` times the
   dispersion of one of them. So the floor is `w · √2 · s / √K`, and
   `floor_standard_errors` is standard errors **of the movement**, which is what
   `√2 · s / √K` is. ADR 0006 §5 is untouched: `s` still comes from the baseline's
   samples alone, so a noisy new run still cannot widen its own excuse, and the
   assumption this adds is only that the run is as noisy as the reviewed baseline.
   Without the `√2`, a width of 2 covers 1.414 standard deviations of the movement
   rather than 2, which under a normal reports an unchanged check worse about 16%
   of the time. In a simulation of this project's home-page scenario, with a jitter
   of ±0.005 seeded from the prompt, 6 of 12 rewordings of one guidance line within
   three characters of its length reported a check worse while only that jitter had
   moved.
2. **It applies only where an assertion declares it.** Today every assertion is given a
   widened `unchanged` zone whether or not its author asked for one. After this, an
   assertion that declares no floor is decided by its tolerance alone.
   A run-level aggregate is outside this, as *Context* says above: nothing here decides
   what its floor becomes, and it is not the same defect. An aggregate's recorded score
   need not be the mean of its slices, so emptying its floor moves verdicts, and
   `test_an_aggregate_whose_slices_tie_away_from_its_score_keeps_its_floor` holds that it
   is not emptied.

**The answer ADR 0006 is owed.** ADR 0006 refused variance and standard deviation because
*"it assumes a distribution, and five samples are not enough to earn the assumption"*. That
is right, and it is not an argument for the floor as built: the range of five draws is
itself an assumption, that it bounds where their mean can be, and it is a worse one, because
it widens with K. So the choice is not between assuming and not assuming. It is between an
assumption that is declared, with a width written down, and one that is silent and runs
backwards. What makes a poor estimate acceptable is that it is **asked for**: whoever
declares a floor at K=3 is declaring that they accept an estimate made from three numbers,
and digline is not imposing it on anyone.

**Five things this carries.**

- **A break.** Every movement the floor called `unchanged` and the tolerance does not
  cover will begin to be reported. The first consequence above is why that is the whole
  of it: `unchanged` is the tolerance *or* the floor, tried in that order, so taking the
  floor away takes back exactly what only the floor was granting. A check with
  `tolerance=0` is the sharpest case and not the condition — its author asked for no
  movement at all, and for a binary baseline that is not unanimous the floor covers every
  possible score whatever the tolerance says. That is the point of the change, not a side
  effect, and it needs a release note and a version decision by `RELEASING.md`'s rule.
- **A new declared quantity.** A dispersion-based floor needs a width — one standard error,
  two — and that width is declared, never inferred. Whoever writes it owns the number.
  That is the sentence `docs/guide.md` currently
  denies: section *The second control: what the check measured about itself* says of the
  floor that "Nobody chose it and nobody can widen it by hand" (lines 533-535), and the
  section closes by telling the reader a tolerance can be tightened back "because the
  measured floor is now doing the other job" (lines 555-558) — advice that puts whoever
  followed it in the path of the break above. Both are withdrawn by the change that
  implements this, in the same landing as the sentence the third item asks for.
- **Binary checks stay the tolerance's business.** For a binary check the dispersion of the
  mean is `sqrt(p(1−p)/K)`, about `0.179` at `p=0.8` and K=5: still wide. The documentation
  should say that a binary check is served by its declared tolerance, rather than leaving
  each author to find it out. The change that implements this lands with that sentence in
  `docs/guide.md`, section *The second control: what the check measured about itself*,
  and a test that fails when the page stops saying it, run by the three `gates` checks
  `main` requires. Until then the sentence is a commitment of this record, and nothing
  holds it.
- **A reader can no longer check the floor by eye.** ADR 0006's third reason for the
  observed interval was that the min and the max *"are what a reader can check against the
  raw samples printed beside them"* (ADR 0006, lines 496-497 at `2fedf3e`). A dispersion
  with a declared width cannot be checked that way. So whatever prints the floor prints
  what it was computed from — the judged samples, their standard deviation, K, and the
  declared width — or the floor becomes a number the reader takes on trust, which is the
  one thing ADR 0006 was right to refuse.
  A tied sample set has no floor to print, by the first decision above, so nothing here
  asks for a standard deviation of zero to be rendered as a width.
- **The floor is a lower bound when its samples come from a replay.** ADR 0024 §5.6
  measured an abstention rate of 2.0% over a stored run against 8–10.5% live — on brief's
  `brief-reason`, 21 cases, a `Faithfulness` check judged by Haiku — and argues from it
  that *"`judge_samples` reports a lower bound… a replay can only be kinder, because it
  cannot serve an answer nobody has written"* (ADR 0024, lines 1056-1070 at `51349aa`). No
  dispersion of score between a replay and a live run is measured there. A dispersion
  estimated from replayed samples is therefore a lower bound on the variation the next live
  run will show, and a floor built from it forgives less than the live noise warrants. The
  error falls on the side of calling a movement real when it was noise, which is the side
  ADR 0028 §4 says this product chooses — *red is the side this product chooses to be wrong
  on* — and it is declared here rather than discovered.

*Added 2026-10-17, by the maintainer, before acceptance.* The fourth item answers ADR
0006's third reason, which the paragraph *The answer ADR 0006 is owed* leaves to it. As
landed in #579, the list read *"Three things this carries"* and held the first three. The
same day, the third item gained its last two sentences, which name the page its sentence
will live on and the test that will hold it. Nothing holds it yet. As landed, it ended at
*"rather than leaving each author to find it out"*.

*Added 2026-10-18, by the maintainer, before acceptance.* The fifth item, and with it the
heading, which read *"Four things this carries"* until then. The fifth item says which way
a floor estimated from a replay errs. The same day *What this ADR does not claim* gained its
second and third paragraphs, on the one measurement of variation between runs this project
has: what it covers, and what it does not say. *The answer ADR 0006 is owed* is unchanged.

**The passenger rule (ADR 0014 §1).** *Added 2026-10-20, after acceptance.* Schema
20 carries one passenger, and the first condition is the one that needed amending
rather than satisfying:

| passenger | 1 — the hash | 2 — the migration | 3 — the boundary |
|---|---|---|---|
| `floor_standard_errors` (the second of *Five things this carries*) | a declaration about how a rule is read, like a tolerance, so it joins the hash — but only where a suite declares it, and a suite that declares none hashes exactly as before: ADR 0014 §1, extended here the way ADR 0022 §3 extended it for a price | absent — a baseline written before this could not have declared a width, and inventing one would hand a check a floor nobody chose | a declaration the suite's author wrote, like a tolerance; travels |

One consequence of the first column is worth saying out loud rather than
discovering: changing a declared width moves `config_hash`, so the baseline stops
being promotable against the new suite and the report says the rules changed. That
is right — the width is one of the rules a movement is read against — and it is the
same cost a changed tolerance carries today. A suite that declares none pays none
of it.

**Not decided here.** The migration: whether a suite keeps the floor by default for one
release with a warning, or loses it at once. That is a release question.

*Answered 2026-10-20.* At once, with no flag and no window: the argument ADR 0031 §3 makes
against a flag as a standing permission, and the one deprecation this project allowed,
which is still here.

## Test plan

The fourth point's figures come from an enumeration, and the enumeration runs in CI:
`tests/test_no_same_side_move_is_excused_for_a_binary_check.py`. For a binary check at K=5
and a threshold of 0.5, it folds every count of passes, fails and samples that could not be
judged with `combine_samples`, at each `min_agreement` five samples can produce, and puts
every same-side pair through `compare()` at tolerance 0, with no width declared and with
one. It holds two things: the five figures of the fourth point, as the widest same-side
movement those folds permit, which is what the range floor excused in full and the evidence
that justified this decision; and that `compare()` now excuses none of them, because a
binary check is the tolerance's business.

*Amended 2026-10-21:* the file was `tests/test_noise_floor_concedes_every_same_side_move.py`,
which held the coincidence through the range floor.
