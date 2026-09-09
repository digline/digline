# ADR 0009 — Boundary semantics

- Status: accepted — drafted on `docs-boundaries` during the 0.5.0 sequence,
  parked, and redecided against the code as it stands after 0.6.0.
  Implementation on `boundaries-0009`; ships in 0.7.0
- Date: 2026-09-09
- Assumes: [ADR 0001](0001-verdict-not-score.md) §3 (a `Verdict` may not
  contradict itself: `status` and `score >= threshold` are one fact),
  [ADR 0006](0006-repeated-samples-and-the-noise-floor.md) §5 and §6 (the
  measured noise floor, and the rule order that puts a flip above it),
  [ADR 0008](0008-the-two-run-report.md) §2 (a difference is swap-invariant)
- Touches: fixed decision 3 (no vacuously green assertion) and fixed decision 4
  (a declared ceiling fails the run). Both are **upheld** rather than amended —
  §6 is where decision 4 stops being true in the letter and is repaired
- Extends: nothing. No stored document changes shape or value; `SCHEMA_VERSION`
  stays 9 and `OUTPUT_VERSION` stays 1 (§8)

## Context

Seventeen places in this codebase compare a number against a limit. Sixteen of
them decide something a reader acts on: whether a check passed, whether a run
regressed, whether two runs differ, whether the samples agreed. Until this
record, no sentence anywhere said how any of them behaves at the edge, and the
answer was not the same in all seventeen.

The draft this record replaces argued the wrong thesis. It said the edges
disagreed in **direction** — "noise floor inclusive, absolute threshold
inclusive, tolerance exclusive". That was never true, and it is not true now.
Every one of the seventeen is inclusive: the value sitting exactly on the limit
passes, or stays `unchanged`. The draft's own table said so and its prose
contradicted it.

What actually disagrees is **what each site compares**.

> Some sites compare two numbers that have each been rounded to
> `FLOAT_PRECISION`. Others compare a **difference** of two such numbers, or two
> raw quotients, and the subtraction and the division are not themselves
> rounded. So the edge is settled by a residue in the last bits, which no reader
> of the document can see.

The consequence, on real numbers from the `brief` fixtures:

```
0.761905 - 0.714286 = 0.04761900000000008   >  0.047619   -> reported
0.714286 - 0.666667 = 0.04761899999999997  <=  0.047619   -> not reported
```

Both movements are one case in twenty-one, against a tolerance declared as
`"1/21"`. All four numbers print, and are stored, as six decimals. One is a
finding and the other is not, and nothing on the page explains the difference.

### The two silent precedents

**The ruling nobody recorded.** Commit `55e9d2f` — "Decide an aggregate's status
from the score it stores", shipped in 0.6.0 — gave `RunAssertionBase._graded`
the rounding that `AssertionBase._graded` and `combine_samples` already had. It
was written as a crash fix, and it was one: an accuracy of 14/21 against a
threshold of `0.666667` was `fail` unrounded and `pass` once both sides were
rounded, so `Verdict.__post_init__` refused to build the verdict at all and the
run's gate became a traceback. But it was also a decision about a boundary, made
in passing, recorded nowhere. **Four of the five sites that decide a verdict now
round, and three of them arrived there separately, each with a comment naming
the same hazard.** The rule was already being discovered, one call site at a
time, by whoever was standing there when it bit.

**The cost of not having the rule.** `digline diff` shipped in the same release
(ADR 0008). Its `_difference` computes `delta = right.score.score -
left.score.score` and tests `abs(delta) <= tolerance` — the same unrounded
subtraction as `compare()`, in a new file, with the same behaviour at the edge:

```
diff  0.761905 -> 0.714286   ('differs', 'left')
diff  0.666667 -> 0.714286   ('same',    'neither')
```

Nobody copied it deliberately. It was written the obvious way, which is the
point: **the defect doubled while the record that would have prevented it sat
parked in a stash.** A rule that exists only as three comments at three call
sites is a rule the fourth call site does not inherit.

### What the corpus says

Across the eleven committed baselines and fixtures, 280 scored verdicts:

| | count |
|---|---|
| verdicts sitting **exactly on their threshold** | **112** (40%) |
| of those, at `0.0` or `1.0` — exact in binary, rounding is a no-op | 112 |
| at a value where **rounding is load-bearing** | **1** |

The single one is a per-sample aggregate: the `brief` baseline's precision at
sample index 1 scores exactly `0.600000` against a threshold of `0.600000` and
passes.

That ratio is the argument, and it points both ways at once:

- **Direction is load-bearing for two fifths of everything we have committed.**
  A `>=` quietly becoming a `>` would turn 112 green verdicts red across every
  example in the repository. Inclusivity is not a preference to be revisited; it
  is a fact the corpus is already resting on.
- **Rounding is load-bearing for one value.** Which is exactly why it drifted:
  nothing that mattered ever failed because of it, so four sites acquired the
  rounding and three did not, and no test named the difference.

A rule is cheap to state here precisely because so little currently depends on
it. It will not stay cheap.

## Decision

### 1. One rule, one sentence, no exceptions

> **Every limit in digline is compared at `FLOAT_PRECISION`, and every limit is
> inclusive.**

The rule binds all seventeen sites in §2, including the ones where it is already
true and the ones where it is a no-op. That is the point of a rule with no
exceptions: an eighteenth comparison added next year inherits it without anyone
remembering this record exists.

Two halves, and each is load-bearing for its own reason:

- **at `FLOAT_PRECISION`**, because what a comparison reads must be what the
  baseline stores. `Verdict.__post_init__` already rounds for this reason: a
  verdict and its round-tripped copy must be indistinguishable, or the same two
  runs answer differently depending on whether one of them has been through the
  disk.
- **inclusive**, because a threshold a score exactly meets must pass. The
  alternative inverts fixed decision 3 rather than upholding it, and it would
  redden 112 committed verdicts (§ *Alternatives*, option 4).

### 2. The seventeen sites

Recorded in full, because "no exceptions" is only checkable against a list. The
last column is what a value sitting exactly on the limit does — after this
record, in every row.

| # | limit | site | op | at the limit |
|---|---|---|---|---|
| 1 | per-case threshold | `core/assertions.py` `AssertionBase._graded` | `>=` | passes |
| 2 | per-run aggregate threshold | `core/aggregate.py` `RunAssertionBase._graded` | `>=` | passes |
| 3 | per-group aggregate threshold | same `_graded`, via `expand_by_group` | `>=` | passes |
| 4 | per-sample aggregate (ADR 0006 §7) | `core/aggregate.py` `_at` | `>=` | passes |
| 5 | the `Verdict` invariant | `core/types.py` `Verdict.__post_init__` | `>=` | consistent, `pass` |
| 6 | sampled mean vs threshold | `core/sampling.py` `combine_samples` | `>=` | passes |
| 7 | **declared tolerance, `compare`** | `core/compare.py` rule 4 | `<=` | `unchanged` |
| 8 | **declared tolerance, `diff`** | `core/diff.py` `_difference` | `<=` | `same` |
| 9 | measured noise floor | `core/compare.py` `_Noise.covers` | `<=` … `<=` | within noise |
| 10 | interval overlap | `core/diff.py` `_overlap` | `<=` ∧ `<=` | intervals overlap |
| 11 | **`min_agreement`** | `core/sampling.py` `combine_samples` | `>=` | agrees (§7) |
| 12 | **cost budget cap** | `core/assertions.py` `CostBudget` | `<=` | within budget (§6) |
| 13 | **latency budget cap** | `core/assertions.py` `LatencyBudget` | `<=` | within budget (§6) |
| 14 | length minimum / maximum | `core/assertions.py` `Length` | `>=` / `<=` | passes |
| 15 | tolerance selection | `core/diff.py` `_tolerance` | `max` | no edge — swap-invariant |
| 16 | the run gate | `wire/contract.py` `exit_code` | — | no numeric limit |
| 17 | agreement reachability | `core/ratio.py` `as_agreement` | `==` | reachable (§7) |

Rows 14–17 carry no edge to move: 14 compares integers, 15 selects rather than
tests, 16 reads counts, 17 already rounds. They are listed because a rule with
exceptions is a rule with an argument in it, and the next reader should be able
to check the claim rather than trust it.

### 3. The rule lives in `core`, not at the call sites

`round(x, FLOAT_PRECISION)` is currently spelled out at seven places, three of
them carrying a comment explaining the same hazard in different words. That is
how the fourth site missed it. The rule gets one home:

```python
# core/types.py, beside FLOAT_PRECISION

#: One unit at storage precision: the smallest step either side of a limit that
#: survives being written to a baseline and read back.
STORAGE_STEP = 10.0**-FLOAT_PRECISION


def at_precision(value: float) -> float:
    """A number as the document stores it. Every limit is compared here first."""


def meets(value: float, limit: float) -> bool:
    """`value >= limit` at storage precision — the inclusive direction of §1."""


def within(value: float, limit: float) -> bool:
    """`value <= limit` at storage precision — the same rule, other way round."""
```

Two named predicates rather than one, because `meets` and `within` read as what
the call site means — a score meets a threshold, a delta is within a tolerance —
and a single `compare_at_precision(a, op, b)` would read as neither.

### 4. The tolerance compares a rounded delta

Rows 7 and 8. `delta` is rounded where it is computed, not where it is tested,
so that the number the rule reads is the number the document prints and the wire
carries:

```python
delta = at_precision(now.score.score - before.score.score)
...
if within(abs(delta), now.tolerance):
```

Rounding at the point of subtraction rather than inside the comparison is
deliberate: `AssertionDelta.delta` and `CheckDifference.delta` are public fields.
A delta that tested as `0.047619` and serialized as `0.04761900000000008` would
have moved the inconsistency from the verdict into the JSON.

### 5. Which control speaks first, and what that costs

One recorded outcome changes, and it is worth being exact about which. On the
`brief` fixtures — the two runs ADR 0006 was written about — `accuracy` falls
from `0.761905` to `0.714286`, one case in twenty-one, against a tolerance
declared as one case in twenty-one:

| | before | after |
|---|---|---|
| `outcome` | `unchanged` | `unchanged` |
| `within_noise` | `true` | **`false`** |
| `reason` | "within the noise of this check (0.666667-0.809524 across 5 samples)" | "delta -0.047619 within tolerance 0.047619" |

**The verdict a reader acts on does not move.** What moves is which of the two
controls answered first — and `compare()` checks the declared tolerance before
the measured floor precisely so that a reader is never left to guess. The
movement was always inside the declared tolerance; it reached the noise floor
only because it missed the tolerance edge by 7.6e-17.

ADR 0006 does not lose its argument. Its example is now caught one rule earlier,
and the measured floor still exists for every movement wider than the declared
tolerance, which is what it was for. A footnote there says so.

This is a **compare-time note, not a migration**. No stored document changes:
`within_noise` is computed by `compare()`, never recorded in a run or a
baseline. Anyone who compares those two particular runs sees a different
`reason` and a different `within_noise` in `--json` and over MCP; nobody's files
change, and no baseline needs re-promoting. Documents do not move — only
judgments about them.

### 6. A budget has one comparison, not two

Fixed decision 4 says a declared ceiling fails the run. It did not, quite:

```
cost_usd = 1.000002, max_usd = 1.000000  ->  status = pass
reason:  "1.000002 USD against a 1.000000 cap (over budget)"
```

`CostBudget` computed the word in its reason from `measured <= cap` on the raw
values, and its **status** from `round(budget_score(...), 6) >= 0.5`. Two
comparisons of the same fact, and near the cap they disagree: `budget_score` is
`cap / (cap + measured)`, which is exactly `0.5` at the cap and rounds to `0.5`
for any overrun below about 2e-6 relative. The band is thin — $0.000002 on a $1
cap, 0.06 ms on a 30 s cap — and its width is not the point. **The document
contradicted the gate**, and a reader shown "over budget" beside a green check
has been told two things.

The repair is not to round the budget comparison. It is to have one comparison:

```python
score = budget_score_at_precision(measured, cap, self.threshold)
met = meets(score, self.threshold)  # the same test `_graded` will make
```

`budget_score_at_precision` rounds the score for storage and then keeps it on
the side of the threshold that `within(measured, cap)` puts it on — one
`STORAGE_STEP` below when the cap was exceeded. The score is a comparability
aid, deliberately non-linear and documented as such; where a compressed proxy
cannot express a difference at storage precision, **the proxy yields to the
fact**, not the other way round. `met` is then derived from the score itself, so
the reason and the status are one statement by construction and cannot drift
apart again.

A budget declared with `threshold=0.0` stays vacuously green. That is fixed
decision 3's problem and not this record's; it is named here so the next reader
does not mistake the silence for an oversight.

### 7. `min_agreement` compares rounded quotients, and the string form is the spelling

The reachability guard in `as_agreement` refuses any value the sample count
cannot produce, and it checks reachability **at `FLOAT_PRECISION`**. The gate in
`combine_samples` then compared the raw quotients. With three samples:

| declared | the guard | two of three agreeing |
|---|---|---|
| `"2/3"` | accepted | **passes** |
| `0.666667` — the printed form | **accepted** | **`error`** |
| `0.666666` | refused as unreachable | — |

The error reads *"the samples did not agree: 0.67 of them share the majority
verdict, below the required 0.67"*, which is a sentence that refutes itself.
There was no float spelling of "two of three" that worked: the guard said
reachable, the gate said it was not, and a check the user declared correctly
became an `error` — which, by ADR 0006 §2, is a check that cannot be promoted
to a baseline.

Under §1 the gate rounds both sides, and the guard and the gate now agree by
construction — they are the same comparison at the same precision.

**The reference page recommends `"2/3"`.** Both forms work after this record,
and the string is still the better one to write: it says what it means. An
agreement is a count of samples over a count of samples, `"2/3"` is that
sentence, and `0.666667` is a rendering of it that a reader has to decode and
that only survives because the two ends now round to the same place. The
recommendation is documentation, not a refusal — a float that names a reachable
agreement stays valid.

### 8. Compatibility

Nothing in a stored document changes shape or value. `SCHEMA_VERSION` stays
**9**, `OUTPUT_VERSION` stays **1**. No run needs migrating, no baseline needs
re-promoting, and the `brief` fixtures are not regenerated — they are evidence,
their SHA-256 pins hold, and the README's red line ("a change that makes
`12-29-17` read *got worse* at the aggregate again is a change that undoes ADR
0006") is not crossed: it still reads `unchanged`.

Three behaviours change, all of them in the direction of the document already
written:

| | before | after |
|---|---|---|
| a delta exactly at the declared tolerance, where the subtraction left a residue | reported | `unchanged` / `same` |
| a budget over its cap by less than ~2e-6 relative | `pass`, reason "over budget" | `fail`, reason "over budget" |
| `min_agreement` declared as the printed float of a reachable agreement | `error` | passes |

## Consequences

- The rule is checkable. `tests/test_boundaries.py` holds every row of §2 that
  has an edge, each with three values — on the limit, one `STORAGE_STEP` inside,
  one outside — so a `>=` becoming a `>` fails by name rather than by an example
  noticing years later.
- `docs/api.md` gains the rule as one sentence and stops describing three edges
  that were only ever one. Its previous "Boundaries" paragraph, written on the
  parked branch and never shipped, was wrong in both of its worked examples; the
  correction ships with this record.
- Seven spellings of `round(x, FLOAT_PRECISION)` collapse into `at_precision`,
  and the three comments explaining the hazard collapse into this record.
- The thin band in §6 means a budget that was passing at 2e-6 over its cap now
  fails. Any run that close to a ceiling was reporting "over budget" in its own
  reason string already.

## Alternatives considered

**1. Document the current behaviour and change nothing.** The parked draft's
option 1, and the cheapest. Rejected on the evidence of its own two precedents:
`diff` copied the defect *while the document describing it existed*, which is
the strongest available demonstration that a described boundary and a ruled one
are not the same thing. It also leaves the reference page unable to say anything
shorter than three paragraphs, one of which has to explain that a subtraction is
not rounded.

**2. Align the tolerance only.** Two lines, two files, and it fixes the case
this record was opened about. Rejected because it leaves rows 11, 12 and 13
outside the rule — and rows 11, 12 and 13 are where the two genuinely
user-visible defects were found. A rule that covers the sites we already
inspected is the rule we already had.

**3. Make the tolerance edge exclusive**, so that "exactly at the tolerance" is
a finding. Recorded so nobody re-proposes it: the default tolerance is `0.0` and
the ordinary delta is `0.0`, so a run compared with itself would report every
assertion as a regression.

**4. Make the thresholds exclusive.** Never seriously on the table, and the
corpus says why: 112 of 280 committed verdicts sit exactly on their threshold.
It would redden two fifths of every example in the repository, and it would
invert fixed decision 3 — which asks that no assertion be *vacuously green*, not
that a met threshold be treated as unmet.

**5. Raise `FLOAT_PRECISION`.** Moves the edge without removing it: the residue
of a subtraction is a property of binary floating point, not of the number of
decimals. It would also change every stored document, which is the one cost this
record does not pay.

## Test plan

`tests/test_boundaries.py` is the file, and it exists already — written on the
parked branch to pin the edges *as they were*, which is what made this record
decidable. It grows rather than moves:

- every row of §2 with an edge gets the three values: on it, one `STORAGE_STEP`
  inside, one outside;
- `test_the_tolerance_edge_is_the_subtraction_and_not_the_printed_numbers`
  inverts. It was written to pin the defect and is the one test this record is
  meant to break; it becomes the assertion that both 1/21 movements now read the
  same way, and keeps the `brief` numbers that produced them;
- `diff` gets the same pair, because the defect existed twice and a test that
  covers one file would let it come back in the other;
- `test_the_run_that_cried_wolf_is_within_noise_at_the_aggregate` is rewritten to
  assert what the run reports now — `unchanged`, by tolerance, `within_noise`
  false — **with the fixtures untouched**. They are evidence, and evidence is not
  adjusted to agree with a test;
- a comparison of a run with itself stays `unchanged` at `tolerance=0.0`;
- §6: a budget one `STORAGE_STEP` over its cap fails, and its reason and its
  status say the same thing; exactly at the cap it passes, scoring `0.5`;
- §7: `min_agreement` declared as `"2/3"` and as `0.666667` reach the same
  verdict on the same three samples, and `0.666666` is still refused as
  unreachable.
