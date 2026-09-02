# My pipeline is LangChain: what changed when I upgraded it?

A two-step chain over seven local handbook pages — a retrieval step in plain
Python, then `ChatPromptTemplate | model | StrOutputParser()` — and digline
holding what comes out of it against a baseline committed here. The target is
**a function**: digline imports `app.py` and calls the chain in process. No
server, no HTTP, no port.

Tested against **langchain 1.3.18** and **langchain-core 1.6.1**.

```console
$ uv sync && uv run digline run --suite suite.py
```

No API key, no network. The default path puts LangChain's own
`FakeListChatModel` under the chain, so every run answers the same way and CI
can run the whole cycle for nothing.

## 1. What is under test

The chain returns the model's **text**, not a parsed object. That is the
decision the rest of this example rests on: what moves when langchain or the
model moves is the *shape* of that text, and a chain that parses before it
returns turns all of it into an exception — which is a far worse thing to
compare than a string.

So four checks, in `suite.py`:

````python
JsonSchema(schema=SCHEMA)  # the record the caller downstream unpacks
Contains(needle="handbook/")  # it still cites the page it answered from
NotContains(needle="```")  # the JSON still arrives with no code fence
LlmRubric(rubric=RUBRIC, judge=JUDGE, threshold=0.8, tolerance=0.1)
````

The third one is not a curiosity. A new model version starts wrapping its JSON
in a fence and every consumer downstream breaks, while the answer still reads
perfectly in a log. Flip the stand-in to fence its replies and this suite says:

```
14 checks got worse. 7 cases could not be judged.
  … · not_contains · Went from passing to failing (1.000000 → 0.000000).
  … · json_schema  · The check could not run.
```

`json_schema` reports **error**, not fail: an undecodable output is a different
problem from a schema violation, and digline refuses to blur the two.

And the one no string comparison reaches. Add a single plausible sentence the
handbook never states — *"Riverbend has offered a fourteen day exchange since
1998"* — and the three deterministic checks stay green while one moves:

```
1 check got worse.
  return-worn-boots · llm_rubric · Went from passing to failing (0.875000 → 0.731000).
```

There is deliberately **no `CostBudget` and no `LatencyBudget` here**. A fake
model costs nothing and answers in a millisecond, so a ceiling on this path is
green by construction — which is the vacuously green check digline exists to
refuse. Add both when you switch the path below.

## 2. The switch, and what the default path does not test

One line in `suite.py`:

```python
LIVE = os.environ.get("DIGLINE_LIVE") == "1"
```

Set it and the chain runs on `init_chat_model("anthropic:claude-haiku-4-5")`
and the rubric is graded by `AnthropicJudge` from `digline-anthropic` — a plugin
is a target *and* a judge, so the twenty lines of SDK-and-JSON never enter this
file, and the run records which model graded.

Unset, be honest about what you have: `FakeListChatModel` returns the replies it
was handed and **never looks at the prompt**. On the default path the prompt is
not under test — the chain around it is. That the template renders, that the
parser still hands back a string, that the shape the caller depends on still
arrives: those are exactly the things a langchain upgrade breaks, and they are
worth a gate that costs nothing.

The replies are keyed on the page the retrieval step selected, not on the case,
so step one is under test too: change the keywords in `app.py` and the answers
this example sees change with them.

The two paths are two systems. Each keeps its own baseline; do not promote one
over the other.

## 3. The cycle

```console
$ uv run digline run --suite suite.py
2026-09-02T13-02-18-377128-00-00-d33c133e4379cf89

$ uv run digline report --suite suite.py --run latest --locale en --out report.html
$ uv run digline promote --suite suite.py --run latest
```

Read the report before you promote. `promote` means *these answers are the ones
we stand behind* — a decision, not a build step, which is why nothing does it
for you and why the result is a file you commit:
`.digline/riverbend/baselines/handbook.json`. Runs go to `.digline/riverbend/runs/`
and are gitignored. `report.html` in this directory is the one this example
produced; `--locale it` renders the same run in Italian, and the dates and the
numbers do not move.

Both prompt files are declared as artifacts, so every run records them and the
report shows the diff of the prompt above the scores it moved.

## 4. The gate

`.github/workflows/check.yml` — `run`, then `compare`, and nothing else:

```yaml
- run: |
    KEY=$(uv run digline run --suite suite.py)
    uv run digline compare --suite suite.py --run "$KEY"
```

`compare` exits **0** when nothing got worse, **1** when something did, **2**
when a case could not be judged. No parsing of output, no threshold in the
workflow. Note what is not there: `promote`. A job that promotes and then
compares is comparing a run with itself and passes whatever happened.

It also runs weekly. `langchain>=1.3.18,<2` means a minor release lands under
this chain with nobody merging anything — which is the question in the title,
and the run nobody triggered is the one that answers it.

## 5. What it costs you

Honestly:

- **`uv` and Python 3.12+ on the CI runner.** One `uv sync`, cached. langchain
  and its dependency tree are the heavy part, not digline.
- **One Python file in review.** `suite.py` is about seventy lines and somebody
  on the team has to be able to read it. That is the real cost and it is not
  zero.
- **The stand-in's replies.** One per handbook page in `fake.py`, quoting the
  page. A stand-in that invented freely would leave the rubric measuring
  nothing, so these are written with the same care as the cases.

And what it does not require:

- **No key, no account, no network** on the default path.
- **No server and no port.** The chain is imported and called; digline is a
  command that reads and writes files in your repository.
- **No data leaves.** Baselines, runs and reports stay here.
- **No rewrite.** `app.py` is the chain you already have.
