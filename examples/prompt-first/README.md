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
$ uv run digline promote --suite suite.py --run latest
# edit prompts/system.txt, then
$ uv run digline compare --suite suite.py --run latest
```

No API key: the provider and the judge are stand-ins. `DIGLINE_LIVE=1` uses the
real ones.

**And under `DIGLINE_LIVE=1` the rubric currently fails all five cases**, where
the stand-in judge passes them. Measured 2026-09-22 on `claude-haiku-4-5`: the
five scored 0.3667 to 0.6333 against a threshold of 0.7. That is a fact about
this example and not about digline — the baseline was promoted from a run the
stand-in judged, and a real judge reading the same rubric is harsher than the
arithmetic standing in for it. Two honest ways to read it: the prompt has room
the stand-in could not see, or the threshold was set against a judge that was
never asked. Either way the pair *baseline + live judge* has never been
reconciled here, so do not read a red live run as a regression.

Two things that run is good for regardless. The judge's raw scores sit in the
middle of the scale — **none of the fifteen at 0 or 1** — which is what a judge
that still discriminates looks like. And `Run.usage` reports `judge: 0 calls,
$0.0` for it, which is **wrong rather than absent**: `_live_judge` calls the
SDK directly instead of going through `digline-anthropic`, so nothing reports
what it spent. Copy the target's shape, not the judge's.
