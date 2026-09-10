# My RAG is LlamaIndex: is it still answering from the right page?

A `VectorStoreIndex` over four local handbook pages, a `VectorIndexRetriever`,
a prompt template read from a file, a `RetrieverQueryEngine` — and digline
holding what comes out of it against a baseline committed here. The target is
**a function**: digline imports `app.py` and queries the engine in process. No
server, no HTTP, no port, and no vector database.

Tested against **llama-index-core 0.14.24**.

```console
$ uv sync && uv run digline run --suite suite.py
```

No API key, no network, and no model download. The default path runs on a local
embedding stand-in and a scripted model, so every run answers the same way and
CI can run the whole cycle for nothing.

## 1. What is under test, and how this differs from `examples/rag`

The other RAG example freezes the retrieved passages into each case and
measures the **generator**: given these passages, does the answer stay inside
them. This one leaves retrieval running. The index is rebuilt and queried on
every run, so a change to the corpus, the chunk size, the top-k or the embedding
moves the numbers here.

Which raises the question that example did not have to answer: if retrieval is
live, what does the answer get compared against? Not what was retrieved — that
would be grading the run against itself. Each case declares **the page that
ought to answer it**, and that page is the case's context:

```python
Case(
    id="brake-failed-mid-ride",
    vars={"question": "A brake failed halfway along. Where should I leave the bike?"},
    context=[app.page("handbook/faults")],
)
```

So four checks, in `suite.py`:

```python
Regex(pattern=CITES_A_PAGE, name="cites_a_page")
NotContains(needle="Question:", name="does_not_echo_the_prompt")
Length(minimum=60, name="says_something")
Faithfulness(judge=JUDGE, threshold=0.8, tolerance=0.1)
```

`cites_a_page` does the work of three: the citation is missing, the citation
names a page that does not exist, or the retriever found nothing and LlamaIndex
returned the literal string `Empty Response`. All three arrive at the same
check, which is why there is not a second one beside it saying the same thing
in a longer diff.

And `faithfulness` is where retrieval is really measured. It asks a judge to
decompose rather than to score — how many claims the answer makes, how many the
declared page supports — and digline does the division. An answer synthesised
from the wrong page is fluent, correctly formatted, correctly cited, and
supported by nothing this case declared.

## 2. The stand-ins, and what the default path does not test

Be honest about what you have. Two of the three parts are faked, and neither
fake is the one LlamaIndex ships.

**The model.** `MockLLM` **cannot be used here.** It has no `responses=[...]`
list: with no `max_tokens` it hands the prompt back verbatim, and with one it
returns the word "text" repeated. An "answer" that is the prompt contains every
grounded fact the question asked about, so every string check would pass
because the *question* contained the answer — the vacuously green check digline
exists to refuse. So `fake.py` subclasses LlamaIndex's own `CustomLLM` and
answers with one canned reply per handbook page, keyed on the page the
retriever selected. Change the corpus or the embedding and the answer this
example sees changes with it, which is what keeps retrieval under test.

**The embedding.** `MockEmbedding` cannot be used either, for a worse reason:
it returns the same constant vector for every text, so every page is
equidistant from every question and the ranking is whatever order the store
happens to hold. `app.HashEmbedding` is a real bag-of-words vector — hashed
stems, L2-normalised — and cosine similarity over it really does put nearer
questions nearer pages. It is deterministic across processes and machines,
which is what makes a committed baseline mean anything.

It is also lexical, and that is the honest cost: it matches words, not meaning.
Two consequences a reader should know before copying this file. Short words in
a handbook about bike hire are the furniture — *bike*, *dock*, *ride*, *hire* —
and they are on every page, so with them counted *"a brake failed, where do I
leave it?"* retrieved the hire page, which says nothing about brakes; `SHORTEST`
in `app.py` is the line that fixes it. And 256 hash buckets were not enough for
a four-page corpus: one question in five landed on the wrong page through a
collision alone, at 1024 none do.

A real embedding model has neither problem, having read the rest of the
language first. What the default path therefore does **not** test is whether
retrieval understands a question phrased in words the page does not use. What
it does test — and what a framework upgrade breaks — is that the index still
builds, the retriever still ranks, the template still renders, the synthesizer
still returns a string, and the shape the caller depends on still arrives.

**The switch.** One line in `suite.py`:

```python
LIVE = os.environ.get("DIGLINE_LIVE") == "1"
```

Set it and the synthesizer runs on `Anthropic(model="claude-haiku-4-5")` from
`llama-index-llms-anthropic`, and `faithfulness` is graded by
`AnthropicClaimJudge` from `digline-anthropic` — a plugin is a target *and* a
judge, so the twenty lines of SDK-and-JSON never enter this file, and the run
records which model graded. The embedding stays local on both paths: Anthropic
serves no embedding endpoint, so a real one here means either a second vendor's
key or several hundred megabytes of PyTorch, and neither belongs in an example
about wiring.

The two paths are two systems. Each keeps its own baseline; do not promote one
over the other.

## 3. What it catches

Three failures, each reproduced before it was written down here.

**Retrieval drifts.** Change one line of the tokenizer in `app.py` — `SHORTEST`
from 5 to 4 — and one question starts reaching the hire page instead of the
faults page. Every string check stays green. It is well written, it is two
sentences, it cites a real page:

```
1 check got worse compared with the reference. Every case could be judged.
  brake-failed-mid-ride · faithfulness · Went from passing to failing (1.000000 → 0.000000).
```

This is the failure that RAG monitoring exists for and the one a string
comparison never sees.

**The model invents.** Add a single plausible sentence the handbook never
states — *"The scheme has capped every hire at ten pounds since 2019"* — and
the three deterministic checks stay green while one moves:

```
2 checks got worse compared with the reference.
  how-long-is-included   · faithfulness · Went from passing to failing (1.000000 → 0.666667).
  past-twenty-four-hours · faithfulness · Went from passing to failing (1.000000 → 0.666667).
```

**The synthesizer hands the prompt back.** Put LlamaIndex's own `MockLLM` under
the engine — one line in `suite.py` — and every case reports it at once:

```
15 checks got worse compared with the reference.
  how-long-is-included · cites_a_page             · Went from passing to failing (1.000000 → 0.000000).
  how-long-is-included · does_not_echo_the_prompt · Went from passing to failing (1.000000 → 0.000000).
  how-long-is-included · faithfulness             · Went from passing to failing (1.000000 → 0.300000).
```

Not a curiosity: a model that continues the prompt instead of answering it
produces text that reads perfectly in a log and breaks every consumer after it.

There is deliberately **no `CostBudget` and no `LatencyBudget` here**. A
scripted model costs nothing and answers in a millisecond, so a ceiling on this
path is green by construction — which is the vacuously green check digline
exists to refuse. Add both when you switch the path above.

## 4. The cycle

```console
$ uv run digline run --suite suite.py
2026-09-10T08-57-58-166851-00-00-382ac1c801b55316

$ uv run digline report --suite suite.py --run latest --locale en --out report.html
$ uv run digline promote --suite suite.py --run latest
```

Read the report before you promote. `promote` means *these answers are the ones
we stand behind* — a decision, not a build step, which is why nothing does it
for you and why the result is a file you commit:
`.digline/kestrel/baselines/hire.json`. Runs go to `.digline/kestrel/runs/` and
are gitignored. `report.html` in this directory is the one this example
produced; `--locale it` renders the same run in Italian, and the dates and the
numbers do not move.

The prompt template is declared as an artifact, so every run records it and the
report shows the diff of the prompt above the scores it moved.

## 5. The gate

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

It also runs weekly. `llama-index-core>=0.14.24,<0.15` means a patch release
lands under this engine with nobody merging anything — which is the question in
the title, and the run nobody triggered is the one that answers it.

## 6. What it costs you

Honestly:

- **`uv` and Python 3.12+ on the CI runner.** One `uv sync`, cached. The
  dependency is `llama-index-core`, not the `llama-index` meta-package: a query
  engine over local files needs the core and nothing else, and the meta-package
  would pull the OpenAI bindings and the reader collection, one of which would
  make the default path ask for a key. No PyTorch, no model download.
- **One Python file in review.** `suite.py` is about a hundred lines and
  somebody on the team has to be able to read it. That is the real cost and it
  is not zero.
- **Two stand-ins written with care.** One reply per handbook page in `fake.py`,
  quoting the page, and a ~15-line embedding in `app.py`. A model that invented
  freely or an embedding that ranked at random would leave `faithfulness`
  measuring nothing, so these are written with the same care as the cases.
- **One concession to LlamaIndex's typing.** `index.as_query_engine()` is
  `reportUnknownMemberType` under pyright strict, which this example's own gate
  runs. `RetrieverQueryEngine.from_args(...)` is fully typed and does the same
  thing, so there is not a single `# pyright: ignore` here — but you will meet
  this the first time you type-check LlamaIndex code of your own.

And what it does not require:

- **No key, no account, no network** on the default path.
- **No vector database.** The index is in memory and rebuilt per run, which is
  what makes the run reproducible.
- **No server and no port.** The engine is imported and queried; digline is a
  command that reads and writes files in your repository.
- **No data leaves.** Baselines, runs and reports stay here.
- **No rewrite.** `app.py` is the query engine you already have.
