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
