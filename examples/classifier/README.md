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

```console
$ uv sync && uv run digline run --suite suite.py
$ uv run digline promote --suite suite.py --run latest
$ uv run digline compare --suite suite.py --run latest
```

No API key: the classifier here is a stand-in. Replace `app.classify` with your
model and nothing else changes.
