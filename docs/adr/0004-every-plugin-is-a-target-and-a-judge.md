# ADR 0004 — Every plugin is a target *and* a judge

- Status: accepted
- Date: 2026-08-28
- Amended: 2026-09-10 — §6, the completion record. Added rather than a new ADR:
  it widens the one method §2 gives a plugin and overturns nothing above it,
  which is the test ADR 0005 §8 was added under
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

### 6. `_complete` returns a record, not a pair

*Amendment, 2026-09-10. §1–§5 stand unchanged. This widens the one method a
plugin writes, and it is the oldest contract debt in the project.*

The pair was decided when the only question asked of a provider was *what did
it say and what did it cost*. Two needs have arrived that the pair cannot
carry, and this repository already names the first one against itself, in the
docstring of `_no_text`:

> What is *not* here is the provider's own `finish_reason` / `stop_reason`.
> That would say which of the two it really was rather than which it looks
> like, and it cannot reach this function: `_complete` returns `(text, Usage)`
> and nothing else, in every plugin and in the abstract method. The numbers
> below are what this layer holds, so they are what it may claim.

`_no_text` is the sentence an operator reads when a judge produced nothing. It
**infers** — *"likely truncated"*, *"a non-text reply or a refusal"* — from a
token count against a cap, because inference is all the pair leaves it. All
three providers return the answer as a field, and have all along.

The second need is the **trajectory**. An agent that was supposed to call
`search` and answered from memory is a regression digline cannot see: the tool
call is a content block, and `text_of` drops it on purpose — joining it in would
put a repr into the output the assertions read. So the one fact that says
whether the agent did the work is discarded one line before the `Response` is
built.

**So `_complete` returns a `Completion`.**

| field | type | |
|---|---|---|
| `text` | `str` | as before |
| `usage` | `Usage` | as before |
| `finish` | `Finish \| None` | how the turn ended, in one closed vocabulary |
| `finish_raw` | `str \| None` | the provider's own word, verbatim and uninterpreted |
| `tools` | `tuple[str, ...]` | the tools the model called, in the order it called them |
| `model` | `str \| None` | what the provider said answered |
| `fingerprint` | `str \| None` | the backend build, where a provider names one |

A record and not a longer tuple, and not because seven is more than two: **a
tuple's meaning is positional, and every plugin author would have had to
count.** Everything after `usage` defaults, so a provider that can say none of
it writes `Completion(text, usage)` and is done — which is not a hypothetical,
it is `digline-bedrock` on two of the five.

The last two fields are passengers rather than cargo: what they are for is
[ADR 0005](0005-the-configuration-of-the-system-under-test.md) §9, and they are
here because this is the vehicle. Widening `_complete` twice for two facts that
arrive in the same reply would be two plugin releases and two floor bumps for
one journey.

#### Third-party plugins are unaffected, by construction

`_complete` is typed `Completion | tuple[str, Usage]` and the base normalises
what it gets. A plugin written against this ADR as it stood returns the pair,
the pair is read as a `Completion` with every new field at its default, and
nothing about its behaviour moves. This is the shape ADR 0005 §6 chose and the
sentence it chose it with: *the protocol did not gain a mandatory member, so
nothing anyone has written stops satisfying it.*

The union is **permanent, not a deprecation window.** There is no release at
which the pair becomes wrong: it is the honest return for a provider that has
nothing to report beyond text and tokens, and such a provider exists — every
OpenAI-compatible server that answers with neither a finish reason nor a model
id, which is most of the small ones.

#### One vocabulary, and the provider's own word beside it

The three name the same events three ways. Measured by reading the shipped
SDKs, not recalled:

| `finish` | Anthropic `stop_reason` | OpenAI `finish_reason` | Bedrock `stopReason` |
|---|---|---|---|
| `stop` | `end_turn`, `stop_sequence` | `stop` | `end_turn`, `stop_sequence` |
| `length` | `max_tokens`, `model_context_window_exceeded` | `length` | `max_tokens`, `model_context_window_exceeded` |
| `tool_use` | `tool_use` | `tool_calls`, `function_call` | `tool_use` |
| `filtered` | `refusal` | *(see below)* | `guardrail_intervened`, `content_filtered` |
| `other` | `pause_turn` | — | `malformed_model_output`, `malformed_tool_use` |

`finish` is normalised because an assertion that had to spell `"stop"` against
one provider and `"end_turn"` against another would not be one assertion, and
fixed decision 1 is that there is one assertion engine with two drivers.

`finish_raw` is kept beside it because the normalisation is **lossy exactly
where a regulated reader cares**. `refusal`, `content_filtered` and
`guardrail_intervened` all become `filtered`, and which of the three fired is a
fact somebody will be asked for; `max_tokens` and `model_context_window_exceeded`
both become `length`, and *your cap* and *the model's window* are two different
things to go and fix. Recorded, never interpreted, never the subject of an
assertion — an assertion on it would be unportable by construction, which is
the argument for the normalised field one row up.

A word the table does not know maps to **`other`, and keeps the word**. It does
not map to `stop`: calling an unrecognised ending "it finished normally" is
fixed decision 3's vacuously green assertion arriving through a different door,
and a provider that adds a stop reason next quarter must not turn a truncated
run green on upgrade.

**OpenAI has no refusal value in `finish_reason`.** The refusal arrives one
level down, as `message.refusal`, while `finish_reason` stays `stop`. So the
OpenAI plugin is the one place a plugin **composes** an answer rather than
translating one: a present `message.refusal` is reported as
`finish="filtered"`, `finish_raw="refusal"`. Declared here rather than
discovered in the code, because it is the single case where the record says
something the provider did not say in one field.

#### The names, not the arguments

`tools` holds names. The three disagree about what an argument even *is* —
OpenAI returns a JSON **string** whose own SDK docstring warns that the model
"does not always generate valid JSON", while Anthropic and Converse return a
parsed object — so normalising means either parsing what may not parse, or
re-serialising what was already structured and letting two identical calls
differ by whitespace.

They are left out for the harder reason too: **nothing would read them.** The
assertion below checks names. *A field no assertion reads is a dead field*, and
an argument that some later suite might want it is the argument that fills a
contract with dead weight. When an assertion needs the arguments it brings
their shape with it, and adding the field then costs nothing at all — see
"where the record lands" below.

#### `_no_text` stops guessing

The judge's sentence becomes a **read** cause instead of an inferred one, in
the one case where the two disagree most: a model that answered with a tool
call and a model that was cut off at the cap look identical to a token count
when the cap was also reached, and they need opposite fixes.

With `finish` in hand the sentence names what happened — *"the judge returned
no text: the provider reported `length` (`max_tokens`), so it was truncated
before the first character"* — and falls back to today's inference, word for
word, when `finish` is `None`. **The fallback is not a courtesy**: a judge on a
compatible endpoint that reports no finish reason is the ordinary case, and the
sentence that serves it is the one that is there now.

The status does not move. A judge that returned no text did not judge, and that
is `error` before and after — ADR 0001's third outcome, unchanged.

#### The consumer: `ToolsCalled`

A record whose fields nothing reads is a record nobody maintains, so the
trajectory gets its assertion in the same change:

```python
ToolsCalled(expected=["search", "cite"], threshold=1.0)
```

Pure, in `digline.core`, reading `inputs.metadata["response"]` — which is what
the mapper carries in from the driver, and the one route an assertion has to a
fact about the *response* rather than the output.

- `expected` is **mandatory and has no default.** A trajectory assertion with
  nothing to check is fixed decision 3's vacuously green assertion, and a
  default of `()` that passes on every response is the shape it would take.
- The check is the sequence of names, in order, binary: 1.0 or 0.0 against a
  threshold of 1.0. Not a set, not a ratio, not an "at least these" — every one
  of those is a second semantics, and a reader who has to look up which one is
  in force cannot read the verdict.
- **A response that carries no trajectory errors.** A plain-function target and
  a provider that reports no tool calls both give `tools=()`, and `()` is
  indistinguishable from *the model called nothing*. Reporting `fail` there
  would be a finding nobody established; reporting `pass` would be the same
  thing in the direction of good news. The record therefore distinguishes *no
  trajectory reported* from *an empty trajectory*, and only the second is
  judged. This is the same third outcome the judge gets when it cannot answer.
- **`finish` gets its second consumer here**, and it is not decoration: a
  provider that reports `finish="tool_use"` alongside an empty `tools` has
  contradicted itself — a compatible endpoint that emits the call as text is
  the common way — and the assertion errors with that sentence rather than
  reporting that the model called nothing. The pair of fields catches what
  neither catches alone.

`Score.metadata` carries what the assertion **measured**, which is the only
metadata that crosses a boundary (fixed decision 9): the count as a number and
the names as strings. Under `travels()` the count crosses and the names do not
— a tool name is a string, and no string crosses `Score.metadata` on its own
merit. That is the rule working rather than a gap in it: a suite that wants the
names in a redacted document declares them, exactly as it would a model name,
and a reader who gets no disclosure still learns that three tools were called
where two were expected.

#### Where the record lands, and what it costs

Almost nothing, and the reason is worth stating because it is what makes this
release small:

- `Response.metadata` gains the fields — and **`Response` is not persisted.**
  `CaseResult` keeps `case_id`, `verdicts` and `suspended`, so nothing here
  reaches the run document, `compare()`, the report or `SCHEMA_VERSION`. What
  reaches the document is what an assertion measured, through `Score.metadata`,
  under the rule that already governs it.
- `model` and `fingerprint` do reach the document, and they reach it through
  `target_config` — the record, not the hash. That is ADR 0005 §9, and the
  reason it is over there is that *what a plugin returns* and *what a run
  records* are two contracts with two readerships.

`Usage` is untouched, `Pricing` is untouched, and no cost anywhere changes
value.

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

- `_complete` can answer the question it is asked. The judge's sentence about a
  silent reply stops being an inference and becomes a reading, in the one case
  where inference and reading disagree.
- An agent's trajectory is assertable for the first time. Before this, a suite
  could tell that the answer was wrong and never that the model skipped the
  tool that would have made it right.
- Every first-party plugin ships a release and the floor moves with them; a
  third-party plugin ships nothing and behaves identically, because the pair it
  returns is still a return this contract accepts and always will be.
- The core gains one assertion and the six test doubles across this repository
  gain nothing — a fake that returns a pair keeps working, which is the same
  guarantee the third-party plugins get, tested by the fakes not changing.
- `Response.metadata` is a wider bag than it was, and it is still a bag nothing
  persists. Anyone reading a run file for a finish reason will not find one:
  the trajectory travels as a verdict, through an assertion that measured it.

## Not decided here

**The arguments a tool was called with.** Left out above, and left out on the
two grounds that would each be enough: three providers disagree about the
shape, and nothing on day one would read them. The record can gain the field
without a schema bump, a migration or a re-promotion — it never enters the run
document — so the assertion that needs them may bring them, and should bring
its own answer about whether an argument check is exact, a subset, or a
predicate.

**Whether `pause_turn` deserves its own value.** It maps to `other` today,
which is honest and unhelpful: a paused turn is one to be continued, not one
that ended oddly. It gets a value the day a suite runs long-running turns, and
`finish_raw` carries the word in the meantime.

Whether the judging cost belongs in `Run`, in `compare()` and in the report —
§3. Whether a judge should be **async**: `AsyncJudge` is declared in the core
and used by nothing, and the online driver will not be able to score a stream
with a blocking judge. `JudgeBase` is deliberately shaped so that the async
variant is one more `_complete` rather than a second hierarchy, but which of the
two protocols the online driver gets is ADR territory for `digline.online`.
