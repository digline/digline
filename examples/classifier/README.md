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

`report.html` is a comparison where exactly that happened: `hotel_over` flipped
and **neither aggregate moved**. One case is a diagnosis; the aggregate is the
gate.

## Two controls, and only one of them was chosen

The tolerances above are **declared**: someone measured eight runs, decided
three cases of movement is acceptable, and wrote it in `suite.py` where a
reviewer sees it. Since ADR 0006 there is a second control beside them, and it
is **measured**: the baseline records the five raw votes behind every score and
the interval they spanned, and `compare` treats a movement inside that interval
as noise rather than as a finding.

Look in `.digline/northwind/baselines/expense-triage.json` — `lunch_team` has
`"samples": [0.0, 1.0, 1.0, 1.0, 1.0]` beside its score of `0.8`. That case
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

```console
$ uv sync && uv run digline run --suite suite.py
$ uv run digline promote --suite suite.py --run latest
$ uv run digline compare --suite suite.py --run latest
```

No API key: the classifier here is a stand-in. Replace `app.classify` with your
model and nothing else changes.
