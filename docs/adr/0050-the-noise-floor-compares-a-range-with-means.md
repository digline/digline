# ADR 0050 — The noise floor compares a range of single samples with a movement of means

- Status: proposed 2026-10-15. **What it decides was ruled before it was
  written:** the maintainer ruled the decision below on 2026-10-15, on #496.
  The text is not yet accepted, and nothing in it is implemented. #496 stays
  open: this record answers its question, and the issue closes when the code
  lands. After it landed, and before acceptance, the maintainer added a fourth
  item to *Four things this carries* on 2026-10-17: whatever prints the floor
  prints what it was computed from, which answers ADR 0006's third reason. The
  same day the third item named the page its sentence will live on and the test
  that will hold it; until that code lands, nothing holds it
- Shipped: unreleased
- Date: 2026-10-15
- Opens: **nothing on landing.** No code, no `SCHEMA_VERSION`, no
  `OUTPUT_VERSION`. The code that implements it is a break, said under *Four
  things this carries*
- Amends: [ADR 0028](0028-the-rules-that-moved.md) §4, which left a direction
  for `samples` to an amendment that says which half wins and why; the
  amendment is there, in its own words. [ADR 0006](0006-repeated-samples-and-the-noise-floor.md)
  §5, §6 and the variance alternative under *Alternatives considered* carry
  dated notes pointing here
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

## The decision

*Ruled 2026-10-15.* The measured floor stays, and two things change.

1. **It compares means with means.** The quantity on the baseline's side becomes the
   dispersion of the mean of the judged samples, estimated from those samples, instead of
   the range of the samples themselves. The floor then narrows as K grows, which is what a
   floor is for. This is the direction ADR 0028 §4 left open, and the amendment there says
   which half wins and why.
2. **It applies only where an assertion declares it.** Today every assertion is given a
   widened `unchanged` zone whether or not its author asked for one. After this, an
   assertion that declares no floor is decided by its tolerance alone.

**The answer ADR 0006 is owed.** ADR 0006 refused variance and standard deviation because
*"it assumes a distribution, and five samples are not enough to earn the assumption"*. That
is right, and it is not an argument for the floor as built: the range of five draws is
itself an assumption, that it bounds where their mean can be, and it is a worse one, because
it widens with K. So the choice is not between assuming and not assuming. It is between an
assumption that is declared, with a width written down, and one that is silent and runs
backwards. What makes a poor estimate acceptable is that it is **asked for**: whoever
declares a floor at K=3 is declaring that they accept an estimate made from three numbers,
and digline is not imposing it on anyone.

**Four things this carries.**

- **A break.** A check with `tolerance=0` and a baseline that is not unanimous will begin
  reporting movements it used to call `unchanged`. That is the point of the change, not a
  side effect, and it needs a release note and a version decision by `RELEASING.md`'s rule.
- **A new declared quantity.** A dispersion-based floor needs a width — one standard error,
  two — and that width is declared, never inferred. Whoever writes it owns the number.
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

*Added 2026-10-17, by the maintainer, before acceptance.* The fourth item answers ADR
0006's third reason, which the paragraph *The answer ADR 0006 is owed* leaves to it. As
landed in #579, the list read *"Three things this carries"* and held the first three. The
same day, the third item gained its last two sentences, which name the page its sentence
will live on and the test that will hold it. Nothing holds it yet. As landed, it ended at
*"rather than leaving each author to find it out"*.

**Not decided here.** The migration: whether a suite keeps the floor by default for one
release with a warning, or loses it at once. That is a release question.

## Test plan

The fourth point's figures come from an enumeration, and a figure in a public text
regenerates from an artifact that runs in CI:
`tests/test_noise_floor_concedes_every_same_side_move.py`. For a binary check at K=5 and a
threshold of `0.5`, it folds every count of passes, fails and samples that could not be
judged with `combine_samples` at each `min_agreement` five samples can produce, and puts
every same-side pair through `compare()` at tolerance `0`. It holds the coincidence — the
widest same-side movement and the widest the floor excuses are the same number — at each
`min_agreement`, that at unanimity no baseline is divided and nothing is excused, and the
five figures above.
