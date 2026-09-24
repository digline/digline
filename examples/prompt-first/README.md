# I'm writing a prompt and have no application yet

There is no application here: a prompt in `prompts/`, five questions in
`cases.json`, and the answers they ought to get. That is enough to tell whether
an edit made things better or only different — the question you have on day
one, and the one the diff cannot answer.

Two checks, because one is not enough. `Levenshtein` says how far the answer is
from the one you would have written; `LlmRubric` says the part no string
comparison reaches, wrapped in `Repeated` because a judge asked twice does not
answer twice the same.

`report.html` is what happened when one line — *"Always remind the customer of
the returns policy"* — was added to `prompts/system.txt`. The report shows the
**diff of the prompt itself**, above the scores it moved: five answers longer,
ten checks worse. The prompt is recorded in every run, so the baseline carries
the prompt that produced it.

```console
$ uv sync && uv run digline run --suite suite.py
$ uv run digline promote --suite suite.py --run latest --replacing 2026-09-23T07-14-08-579107-00-00-0d99045c0f1639eb
# edit prompts/system.txt, then
$ uv run digline compare --suite suite.py --run latest
```

`--replacing` names the baseline this promotion replaces: here, the one
this example ships, whose key `compare` prints under its verdict and
`digline list` marks with `*`. If the baseline has moved since you
compared, `promote` refuses and names both keys.

**The keyless path runs. It does not compare.**

Without a key the provider and the judge are stand-ins, and `DIGLINE_LIVE=1`
uses the real ones. What the stand-ins are for is the **wiring**: that the
suite loads, the target is reachable, every case is judged, a run is written
and a report renders. That is worth having and it is all it is.

They are not a reference. A stand-in judge here scores by counting sentences
and looking for warm words; it cannot read the rubric, and a baseline of canned
answers scored that way is **a measurement of nothing**. Comparing against one
tells you that two stand-ins agree with each other, which they always will —
and the danger is precise: it looks exactly like a green run, so it teaches a
reader on day one that green means working.

So **the committed baseline here is a live one**, promoted from a real run
against `claude-haiku-4-5`, and `digline compare` is a live-mode gesture. Run
the keyless path to see the shape of the thing; set the key before you believe
a comparison.

This example is also where the judge is watched rather than only used: under
`DIGLINE_LIVE=1` it carries a **calibration case**, a fixed answer whose place
on the scale a judge that still has one has to land inside. It costs judge
calls only — the target is never called for it.

One thing to copy carefully: `Run.usage` reports `judge: 0 calls, $0.0` here,
which is **wrong rather than absent**. `_live_judge` calls the SDK directly
instead of going through `digline-anthropic`, so nothing reports what the judge
spent. Copy the target's shape, not the judge's.
