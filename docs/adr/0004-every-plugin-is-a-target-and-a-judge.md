# ADR 0004 — Every plugin is a target *and* a judge

- Status: accepted
- Date: 2026-08-28
- Refines: fixed decision 6 (`CLAUDE.md`), "providers as plugins"
- Assumes: [ADR 0001](0001-verdict-not-score.md) (the judge returns a reply, the
  core decides the verdict), [ADR 0002](0002-three-worlds-and-where-the-data-lives.md)
  §2 (the payload stays where it is born)

## Context

`digline.core` declares `Judge` and `ClaimJudge` and implements neither: the
judge is the one route an assertion has to the outside world, and it is
injected, which is what keeps an assertion a pure function. That is right and
nothing here changes it.

What is missing is the other side. **No package ships a judge at all.** Every
judge that has ever run against a real model in this repository was written by
hand in a suite — `examples/prompt-first/suite.py::_live_judge` is twenty lines
of SDK call, prefill, JSON decoding and `float(data["score"])`, and it is
copied, not imported. `digline-anthropic` ships `AnthropicTarget` and stops
there. So the plugin boundary, as built, says "a provider is somewhere you send
a prompt to get an answer" and forgets that judging *is* sending a prompt to get
an answer.

Three things follow, and only the third is the reason this is an ADR.

**The parsing is duplicated.** A model asked for JSON returns JSON in a fence,
JSON with a sentence in front of it, or JSON with a trailing comma. Every suite
that judges rediscovers this, and rediscovers it in the place where getting it
wrong turns into a score.

**The judge's cost is invisible.** `Response.cost_usd` is the target's call.
A suite with `samples=5` and `Repeated(n=3)` makes fifteen judging calls per
case and reports the cost of five, so a run's stated cost is not what the run
cost. Fixed decision 4 makes cost a budget; a budget over a number that omits
half the spending is a budget over the wrong number.

**The judge sees the payload.** This is the one that decides the shape. What a
judge is sent is the model's *output* — the thing ADR 0002 keeps on the near
side of the perimeter — and today choosing where to judge is a separate,
unhelped decision from choosing where to generate. A software house running a
customer's model on that customer's own OpenAI-compatible endpoint (Azure in
their tenant, a vLLM in their VPC) has no judge to reach for except somebody
else's API, which sends the output out of the perimeter it was generated in.
Every assertion in the suite is then evaluated on data that has left, and no
`Disclosure` in the suite says so, because disclosure governs what leaves the
*run document*, not what an assertion did while producing it.

A judge that cannot live where the output lives is a hole in decision 9 that no
amount of care in the report can close.

## Decision

### 1. A plugin is a target and a judge, both

Every provider package under `packages/` exports, at minimum:

| | |
|---|---|
| `<Provider>Target` | `(Case) -> Response`, as today |
| `<Provider>Judge` | `(prompt: str) -> JudgeReply` — satisfies `Judge` |
| `<Provider>ClaimJudge` | `(prompt: str) -> ClaimReply` — satisfies `ClaimJudge` |

Both judge protocols, not one. They answer different questions and the core
keeps them apart on purpose (`Judge` decides a score, `ClaimJudge` reports two
counts and the core divides); a plugin that shipped only the first would leave
`Faithfulness` — the assertion with the strongest reason to run inside the
perimeter, since it is handed the retrieved context too — with nothing to run
on.

Choosing a provider is then **one** decision. Whoever can generate can judge,
in the same perimeter, with the same key, against the same price list.

`digline-anthropic` gains the two judges in the same change that introduces
`digline-openai`. A symmetry that holds for one plugin out of two is not a
symmetry, it is a coincidence waiting to be codified wrongly.

### 2. The half that is not the provider lives in `digline.targets`

`ProviderTarget` already carries everything about a provider call that is not
the provider. Judging gets the same treatment: `digline.targets.JudgeBase` and
its two subclasses `ScoreJudge` and `ClaimCountJudge` compose the system prompt,
time the call, price the tokens, parse the reply and build the `JudgeReply` or
`ClaimReply`. A plugin writes `_complete`, which is the same one method a target
writes.

This is `digline.targets` and not `digline.core`: the core stays pure, imports
no SDK, reads no clock and keeps receiving its judge injected. `JudgeBase` sits
where `ProviderTarget` sits — above `digline.run`, below the CLI, with the
layering gate forbidding an SDK import in both.

The system prompt is written once, here, and it is written **against the shape
`judge_prompt()` produces** — instruction, labelled sections, output last behind
`Output to judge:`. That shape is documented in `docs/api.md` because anyone
writing a judge has to parse it; with the judge in the box, the two halves of
the contract are finally in one repository and one test can hold them together.

### 3. What judging cost is counted on the judge, and stays in the process

`JudgeReply` does not grow a cost field. It is a value that crosses into the
core and gets validated there; a cost is not part of a judgement, and putting it
there would make every fake judge in every test carry a number it has no opinion
about.

Instead the judge object accumulates:

| | |
|---|---|
| `calls` | judging calls that returned |
| `spent_usd` | their cost, from the plugin's price list |
| `latency_ms` | their total duration |

**They are never reset.** Not per run, not per case, not per `execute()`. A
judge is constructed by the suite and lives as long as the process, so a reader
of `judge.spent_usd` gets "what this judge has spent since it was built", which
is a fact that needs no lifecycle to interpret. A caller wanting a per-run
figure takes the delta itself — two reads and a subtraction, which is honest
about what it is measuring. The alternative, resetting on some boundary the
judge cannot see, would make the number depend on who called the reset and would
be wrong exactly when a suite is run twice in one process.

A call that raises is not counted: its cost is unknown, and counting it at zero
would be the undercount that reads as good news.

**This is in-process only.** It is not written to the run file, does not enter
`compare()` and does not appear in the report. Said plainly because it is a real
limitation and not an oversight: "what did judging cost" is a number we will
want in the report, and putting it there is a change to the run schema, to
`compare()` and to the document world 3 reads — three things this ADR does not
touch. Today a suite that needs the figure asserts on it or prints it. When it
moves into the run, it gets its own ADR, and the first question that ADR has to
answer is whether a judging cost is a *measurement* (it crosses) or a fact about
the software house's own bill (it does not).

### 4. The reply is parsed leniently, and `response_format` is an optimisation

`base_url` makes one target cover every OpenAI-compatible provider, and those
providers do not agree on structured output: the official endpoint honours
`{"type": "json_object"}`, some vLLM builds honour it, Ollama may reject it
outright. A judge that depended on it would work on the endpoint we tested and
fail on the one a customer runs.

So: it is **sent when it might help and never required.** A provider that
rejects the parameter is retried once without it, and the choice is remembered
for the life of the judge. The reply is then read by a parser that accepts a
bare object, an object inside a ```` ```json ```` fence, and an object with prose
around it — the three shapes a model actually returns.

Lenient about the wrapping, strict about the content: a missing `score`, a
`score` outside `[0, 1]`, a missing `reason`, `supported > total` all raise, and
`LlmRubric` turns the exception into **`error`**. Neither green nor a
regression: the judge failed to answer, which is a third thing, and ADR 0001
already decided that a judgement that could not be made is not a passing one.

### 5. No plugin reads the environment, and a sentinel is only for a custom endpoint

The key resolution rule, which is what makes "the same target covers Ollama" a
sentence rather than a special case:

- `api_key` given → it is used;
- `api_key=None` and the official endpoint → **`None` is passed to the SDK**,
  which resolves `OPENAI_API_KEY` itself and raises its own message if there is
  none. The plugin contains no `os.environ`, no `getenv`, and the existing test
  in `digline-anthropic` that enforces exactly that stays true of both plugins;
- `api_key=None`, a custom `base_url`, and the SDK found no key in the
  environment → the client is built with the sentinel `"digline-no-key"`, a
  value that is obviously not a credential and is documented as one. A local
  server does not look at it; a remote one rejects it with an authentication
  error, which is the right error.

The order matters and is the whole trick: the sentinel is only reached *after*
the SDK has looked, so pointing at OpenRouter with `OPENAI_API_KEY` set still
authenticates. The plugin never learns whether a key exists.

**The key never appears in a `Response`, in `Score.metadata`, in an artifact, in
an error message, or in the `repr` of a target or a judge.** It is credential,
which is the one category of payload that has no `Disclosure` that can release
it. Tested, not asserted.

## Consequences

- A suite on any OpenAI-compatible endpoint can generate *and* judge inside one
  perimeter, with one key and one price list. That is the hole in §Context
  closed, and it is closed by construction rather than by a warning in a
  document.
- Twenty lines of SDK-and-JSON leave every suite that judges. `_live_judge` in
  `examples/prompt-first` can become an import — once 0.1.3 is on the index,
  since the examples install digline from PyPI rather than from the workspace.
- A plugin is a bigger object than it was: two more classes and a system prompt
  per provider. The cost is real and it is paid once per provider, in the
  package whose whole job is knowing that provider.
- The judging spend is now knowable in-process and still absent from the run
  document. Anyone reading a run file for a total cost is reading the target's
  cost, as they were before this ADR — no number changed meaning.
- `digline.targets` grows a second base class, and the layering gate grows the
  obligation to keep an SDK out of it. Same rule, one more file.

## Not decided here

Whether the judging cost belongs in `Run`, in `compare()` and in the report —
§3. Whether a judge should be **async**: `AsyncJudge` is declared in the core
and used by nothing, and the online driver will not be able to score a stream
with a blocking judge. `JudgeBase` is deliberately shaped so that the async
variant is one more `_complete` rather than a second hierarchy, but which of the
two protocols the online driver gets is ADR territory for `digline.online`.
