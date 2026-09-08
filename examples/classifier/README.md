# I have a classifier: how do I keep it under control?

This one decides whether an expense report needs a human to look at it. Twenty
reports in `cases.json`, each with the decision a human actually made.

The gate is not "did case 14 pass". Near its own boundary a classifier answers
differently when asked twice, so `samples=5` asks five times and keeps the
majority. What decides a release is **precision over the whole set**: of the
reports it sent to a human, how many should have gone.

Thresholds and tolerance are measured, not chosen. Eight runs of an untouched
classifier gave precision `0.667 … 0.800` (median `0.727`) and accuracy
`0.800 … 0.900` (median `0.850`) — so the thresholds sit at `3/5` and `7/10`,
below the worst run seen, and the tolerance is the three cases the aggregate
moved by. Promote the median run, never the first green one.

`report.html` is a comparison where exactly that happened: `dinner_client`
changed its mind and **neither run-level figure moved** — precision went 0.727
to 0.800, inside the declared tolerance. One case is a diagnosis; the aggregate
is the gate.

## Two controls, and only one of them was chosen

The tolerances above are **declared**: someone measured eight runs, decided
three cases of movement is acceptable, and wrote it in `suite.py` where a
reviewer sees it. Since ADR 0006 there is a second control beside them, and it
is **measured**: the baseline records the five raw votes behind every score and
the interval they spanned, and `compare` treats a movement inside that interval
as noise rather than as a finding.

Look in `.digline/northwind/baselines/expense-triage.json` — `lunch_team` has
`"samples": [1.0, 0.0, 1.0, 1.0, 1.0]` beside its score of `0.8`. That case
already disagreed with itself once out of five, and now the baseline says so in
a form a rule can read.

The two are checked in that order and both report `unchanged`, with the reason
saying which one spoke. Nothing here changed to get it: the numbers in this
example, its baseline and its `report.html` are the ones it always had, because
the fold still records the mean.

Three things the measured floor does not do, and `hotel_over` is where you can
see the first:

- **It never rescues a flip.** `0.8 → 0.4` crosses the threshold, so it is
  reported however wide the votes were — and here they were as wide as votes
  get. A drop through the bar is a flip, and a flip is never noise.
- **It reads the baseline's interval, not this run's.** A run that got noisier
  cannot widen its own excuse.
- **It has nothing to say about a case decided 5/5.** Zero width is no
  interval, so a case that was unanimous and now is not is still a finding.

One wrinkle worth knowing after `digline migrate`: the per-case intervals come
straight out of the `scores` an older run already recorded, so they work the day
you upgrade. The **aggregate** intervals cannot — sizing them needs the marks
and the declared assertion, and a run file carries neither — so precision and
accuracy report their noise as not known until you promote a run produced under
this release.

## The third act: which class is it wrong about?

An aggregate over the whole set is an average, and an average carries a class
that is broken. Here it has been carrying one since the first commit.

`by_group=True` on both aggregates says: keep the two figures that gate the
release, and give me the same two per class of expense as well. The classes are
declared in `cases.json`, one `"group"` per case — a field of its own, because a
class is not always something the application was given. Nothing else changes:
same thresholds, same tolerance, same noise floor, computed over a subset.

This is what the committed baseline says:

| Class | Cases | Precision | Accuracy |
|---|---|---|---|
| whole run | 20 | 0.727 | 0.850 |
| `hotel` | 3 | 1.000 | 1.000 |
| `meal` | 7 | 0.800 | 0.857 |
| `taxi` | 4 | 1.000 | 1.000 |
| `tools` | 3 | 0.500 | 0.667 |
| `travel` | 3 | 0.000 | 0.667 |

The bars are 0.600 and 0.700. **The classifier does not work on travel
expenses**, it is not much better on tools, and it has never been: those two
rows are red in every run of this example, at the thresholds it always
declared. Seventeen cases it gets right were enough to carry three it does not.

**And the noise floor certifies it.** Every other figure in the baseline has an
interval of some width — the whole-run precision spans `0.667–0.800`,
`accuracy[group=hotel]` spans `0.667–1.000`. The four failing rows span nothing:
`0.000–0.000` and `0.500–0.500` and `0.667–0.667`, at five samples each. The
control whose whole job is to say "that could have been the wobble" has, here,
nothing to say. These are not unlucky runs. This is what the classifier does.

Nothing was tuned to produce that. Lowering the bars until the table went green
was the alternative, and it is the vacuously green assertion shipped as the
thing people copy first — a demo that cannot fail teaches the one habit this
tool exists to prevent.

Three things to read in the table, and then in `report.html`:

- **`compare` still exits 0, and that is not a bug.** It gates on *movement*:
  those rows failed in the reference too, so nothing got worse. The threshold
  says the system does not meet the bar; the comparison says it has not moved.
  Both are true, and the report says so under the figures.
- **The class is where a change becomes visible.** In `report.html` one case
  changed its mind. Whole-run precision moved 0.727 → 0.800 and was called
  unchanged, inside the declared tolerance of three cases;
  `precision[group=meal]` moved 0.800 → 1.000 and was not. Seven cases instead
  of twenty: the same flip is a fifth of the class.
- **The declared tolerance goes quiet on a small class, and the measured floor
  does not.** `3/20` was measured over twenty cases. On three it means nothing —
  one case is a third of the group. Look at `accuracy[group=hotel]` in the
  baseline: its interval is `0.667–1.000`, against `0.800–0.850` for the whole
  run. The control that sizes itself to the denominator is the one that was
  sized by measuring — which is also why the zero-width rows above are a
  finding and not an artefact of looking too closely.

A class too small to answer gets `error`, not a flattering number: `Recall` over
a class marked negative throughout has an empty denominator. That is the suite
asserting something the class cannot answer, and it is reported rather than
guessed.

```console
$ uv sync && uv run digline run --suite suite.py
$ uv run digline promote --suite suite.py --run latest
$ uv run digline compare --suite suite.py --run latest
```

No API key: the classifier here is a stand-in. Replace `app.classify` with your
model and nothing else changes.
