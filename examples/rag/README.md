# I have a RAG: how do I check it doesn't make things up?

Ten documents in `corpus.py`, a keyword retriever, six questions. The retrieved
passages are frozen into each `Case`, so what is measured here is the
**generator**: if retrieval changes, that is a different experiment and a
different baseline.

`Faithfulness` asks a judge to decompose rather than to score — how many claims
the answer makes, how many the passages support — and digline does the division.
A model asked for a fraction returns a number nobody can check; two counts are
something arithmetic can contradict.

`app.EMBELLISH` is shipped **on**, so `compare` against the committed baseline
shows the point immediately: one plausible extra sentence — *"The library has
been on this square since 1898"* — and six checks go from `1.000` to `0.500`.
Turn it off and the suite is green again. `report.html` is that comparison.

Beside it, `PiiAbsent` guards what leaves the building, and `CostBudget` is
graded so a cost creeping up inside the budget is visible before it breaches.

```console
$ uv sync && uv run digline compare --suite suite.py --run latest
```

No API key: retriever, generator and judge are all stand-ins.
