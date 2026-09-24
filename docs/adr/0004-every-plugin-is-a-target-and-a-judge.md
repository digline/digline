# ADR 0004 — Every plugin is a target *and* a judge

- Status: accepted
- Shipped: 0.1.3
- Date: 2026-08-28
- Amended: 2026-09-10 — §6, the completion record. Added rather than a new ADR:
  it widens the one method §2 gives a plugin and overturns nothing above it,
  which is the test ADR 0005 §8 was added under
- Amended: 2026-09-19 — §7, the judge's abstention. It changes the judge
  contract this record owns — `SCORE_SYSTEM`, `CLAIM_SYSTEM` and what a reply
  may say — and overturns nothing above it, so it is an amendment by the same
  test. **Schema-free**: no field reaches the run document, no version moves,
  no baseline is re-promoted
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
| `tools` | `tuple[str, ...] \| None` | the tools the model called, in order — `None` where none were reported |
| `model` | `str \| None` | what the provider said answered |
| `fingerprint` | `str \| None` | the backend build, where a provider names one |

A record and not a longer tuple, and not because seven is more than two: **a
tuple's meaning is positional, and every plugin author would have had to
count.** Everything after `usage` defaults, so a provider that can say none of
it writes `Completion(text, usage)` and is done — which is not a hypothetical,
it is `digline-bedrock` on two of the five.

`tools` carries the absent/empty distinction on the same rule §1 of ADR 0005
reads an unset parameter by: `()` is *the model called nothing*, `None` is
*nobody reported*. They are different facts and only one of them is judgeable.

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

### 7. A judge may say it cannot answer

*Amendment, 2026-09-19. §1–§6 stand unchanged. It widens what a reply may say,
and nothing that reads a reply today reads it differently.*

**It ships with its twin.** 0.16.0 already carries the fix that stopped
`LlmRubric` and `Faithfulness` blaming the judge for a prompt it was never
shown. That one stops the instrument being accused when it is innocent; this
one gives the instrument a way to say it cannot answer. Both are about the same
sentence — the one somebody reads to decide whether to **re-run** or to
**investigate** — and neither needs a schema.

#### 7.1 What a judge can say today, and what it cannot

A judge has exactly two ways to end: return a `JudgeReply` it validated, or
raise. So *"I cannot score this"* has to arrive as an exception, and the
assertion reports it as **`the judge raised …`** — the same sentence as a
timed-out HTTP client, a decoding failure, or a bug in the plugin. The judge's
only declared answer is a number, and a model that is genuinely unable to score
an output — a refusal, an empty answer, text in a language the rubric does not
cover — must either invent a number or crash.

Inventing is the worse of the two and it is the one models do. A score of `0`
for *"I could not read this"* is a **fail**, and a fail is a statement about the
system under test. That is the measured thing being marked down for the
instrument's inability, which is the failure mode this whole record exists to
keep apart from a real one.

#### 7.2 Not a fourth status

`Verdict` has three states and ADR 0001 fixed them. An abstention does **not**
add a fourth, and it does not need one: `error` is already *"a judgement that
could not be given"*, which is precisely what an abstention is.

What changes is the **reason**. Today an unjudged check carries our sentence
about the judge; after this it can carry **the judge's own sentence about the
output** — *"the answer is a refusal to help, so there is nothing to score
against the rubric"*. That is more information than today at the same status,
which is the cheapest kind of improvement this project can buy.

An abstention is also a **paid call**. `JudgeBase._ask` counts `calls`,
`spent_usd` and `tokens` before it parses anything, so an abstaining judge is
billed exactly like a scoring one — correctly, because the model was asked and
answered. Only a call that *raises* goes uncounted, and that rule is unchanged
(ADR 0025 §4).

#### 7.3 The declared form: unreachable by accident

The reply shape gains one key, and the rule about it is the whole of this
section:

    {"abstain": true, "reason": "<why this output cannot be scored>"}

**Never `{"score": null}`, and never a missing `score`.** Those are what a
confused model produces, and they must keep meaning *this reply is broken*. An
abstention that could be reached by omitting a key would be reached by
omission — and then every malformed reply in the world becomes a judge
declining, which is the one reading that cannot be told from the truth.

Three rules make it declarative rather than accidental:

1. **`abstain` must be present and true.** Absent is not an abstention. A
   `false` is not an abstention. A string, a number or `null` under that key is
   a **malformed reply**, not an abstention — the same refusal `_number` already
   gives a `score` that is not a number, and for the same reason: a key that
   accepts anything is a key that means nothing.
2. **`reason` is mandatory, and it is refused when empty** — by `_reason`,
   which already exists and already says the sentence a debugger needs. An
   abstention with no reason is refused as a broken reply, because an
   abstention whose whole value is the judge's sentence is worth nothing
   without one. This is the one place where abstaining is *stricter* than
   scoring: a score can be checked by arithmetic, a declining can only be read.
3. **It is checked before the score.** The parser looks for a declared
   abstention first; only if there is none does it require a `score`. A reply
   carrying both is an abstention — a judge that declined and then supplied a
   number has not scored, it has decorated, and reading the number would be
   reading a value nobody stood behind.

#### 7.4 How it reaches the core: an exception, not a wider reply

The mechanism is a dedicated exception, `JudgeAbstained`, declared in
`digline.core` beside the reply types, raised by the judge and caught by the
assertion **before** the generic `except Exception` that reports a raise.

    try:
        reply = self.judge(prompt)
    except JudgeAbstained as declined:      # the judge answered: it cannot score
        return self._error(f"the judge declined to score: {declined}")
    except Exception as exc:                # the judge failed
        return self._error(f"the judge raised {type(exc).__name__}: {exc}")

It lives in `core` because the *assertion* catches it and `core` may not import
`targets`; plugins and hand-written judges import it from there, which is one
import and no signature change.

**Two alternatives were weighed and refused.**

*`JudgeReply.score: float | None`.* Rejected. It makes the score optional for
every consumer of every reply in order to express a state that occurs rarely,
and the first consumer that forgets the `None` reads an abstention as a zero —
the exact confusion §7.1 is about, reintroduced one layer down. It would also
weaken the type that exists to be the strictest boundary in the system.

*A union return type, `JudgeReply | Abstention`.* Rejected on compatibility: it
changes the `Judge` protocol's return type, so every hand-written judge in
every suite — and the six test doubles in this repository — stops satisfying it
until its annotation is edited. An exception is invisible to a judge that never
raises it, which is what §7.5 needs to be true.

*Why control flow is honest here.* An abstention ends where an exception ends —
in an errored verdict — and it is the unusual path by construction. The
objection to exceptions is that they hide an ordinary outcome; this outcome is
not ordinary, and the handler that catches it is three lines from the handler
that catches a raise, so a reader meets both at once.

#### 7.5 Backward compatibility, in one line

**A judge that never abstains behaves exactly as today** — because the parser
goes on refusing a missing or null `score` as a broken reply, and nothing reads
the new key unless the judge wrote it deliberately.

That line is true only under §7.3's first rule. If absence ever came to mean
abstention, every existing judge would begin abstaining the first time a model
dropped a key, and this section would be false. It is therefore tested in that
direction: a reply with no `score` is still an error and is **not** an
abstention.

#### 7.6 `CLAIM_SYSTEM`, and the zero that means two things

`Faithfulness` has the one unattributable row in the product that this
amendment can reach. Today, `total == 0` errors with *"the judge found no
claims in the output"*, and that sentence is true of **two different worlds**:

- the output genuinely asserts nothing — a refusal, a clarifying question, an
  empty answer. The **target** produced something with no claims in it;
- the judge could not decompose it — the text is in a language it handles
  badly, or the context is unreadable to it. The **instrument** failed.

Nothing in the data tells them apart, which is why the instrument-versus-target
reconnaissance listed this site as unattributable in advance.

**What a claim judge abstains on.** Not on finding zero claims — that is a
count, and a count is an answer. It abstains on being unable to **do the
decomposition at all**: it cannot determine what the output asserts, so it has
no counts to report, supported or total. `CLAIM_SYSTEM` gains the instruction in
those words, so the distinction the model is asked to make is the distinction
the core reads.

**What `Faithfulness` reports then.** Two errored verdicts where today there is
one, still `error`, still no `side` field:

| what happened | what the verdict says |
|---|---|
| the judge declined | the judge's own sentence, under *the judge declined to count the claims* |
| `total == 0` with no abstention | *the judge counted the claims in this output and found none* — one world, not two |

The second sentence is rewritten by this amendment, and the rewrite is the
point: it may only be said once the first is available. Until a judge can
decline, *"found no claims"* cannot honestly claim the judge counted.

**This is the strongest argument for the feature**, and it should be stated as
what it is: the abstention does not relabel rows we already understand — it
turns a row nobody could attribute into one that can be. It does not *record*
the attribution (§7.8); it makes it exist.

#### 7.7 What the reader sees, confirmed from the code

Nothing here needs a new surface, and one surface will not show it. Both were
read rather than assumed:

- **The report shows it.** `render.py` renders `verdict.reason` in the *Why*
  column of the unjudged block, gated on `reasons_available`, which is
  `not (run.redacted or baseline.redacted)`. So the judge's sentence reaches an
  ordinary reader unchanged, and a **redacted** document shows
  `reason.unavailable` instead — correct and unchanged: the reason is payload
  (ADR 0002 decision 9), and a judge quoting an output is quoting the output.
- **The terminal shows it.** `summary_lines` prints one line per unjudged check
  through the same `check_line()` the report column uses, so the two cannot
  describe one verdict in two ways.
- **`pytest-digline` shows it.** The ERROR row's `longrepr` carries the reason
  verbatim.
- **A `Repeated` fold keeps it.** `_all_errored` groups the samples' own
  sentences by cause with counts, so *"2 of 3: <the judge's sentence>; 1 of 3:
  the judge raised …"* is what a folded abstention reads as. A judge that
  declines twice and fails once is visible as both.
- **`explain` will not show it, and that is deliberate.** `CheckFact` carries
  no `reason` **by ADR 0012 §4** — *"absent rather than emptied, because a field
  that exists is a field a later edit fills"*. So the one surface built for a
  machine to read will say a check could not be judged and not why. This
  amendment does **not** change that: the rule is about a boundary, not about
  this feature, and a field added here for one sentence is the edit that rule
  predicts. A reader who needs the sentence reads the report or the run
  document.

Nothing truncates it: `MAX_FAILURE_CHARS` clips reasons the *driver* builds
from exceptions, and an assertion's `_error` is not clipped.

#### 7.8 What this does not do

Said plainly, because the feature is easy to oversell:

- **It attributes no side.** No field on the verdict, nothing in the document,
  nothing in `compare()`. The instrument-versus-target distinction stays a
  sentence a human reads, and the field that would make it machine-readable
  waits for the friction that names it.
- **It moves no exit code.** An abstention is `error`, and an errored check
  already exits 2. A suite whose judge declines everywhere exits exactly as a
  suite whose judge raised everywhere.
- **It changes no threshold, tolerance or denominator.** An abstaining check is
  excluded from an aggregate under `errored_excluded`, which is where an
  errored check has always gone.
- **It leaves the other unattributable rows unattributable.** The aggregate's
  empty denominator and both `combine_samples` exits are not reached by this
  and are not helped by it. `total == 0` is the only one it closes.

#### 7.9 The prompt moves, and nothing records that it did

`SCORE_SYSTEM` and `CLAIM_SYSTEM` gain the instruction that tells a model it may
decline. Two questions follow, and the answers are not symmetrical.

**Does it change `artifacts_changed` for anyone? No.** `Run.artifacts` holds the
files *the suite declares* — the prompt under test, keyed by the path the suite
gave (ADR 0003). These constants are digline's own source. No suite declares
them, so no artifact digest moves and no comparison reports a changed file.

**Is a stored baseline affected? No.** The judge's system prompt is in neither
`config_hash` — which covers assertion identities, thresholds, tolerances,
`samples`, `min_agreement`, the aggregates and a declared price — nor
`judge_config`, which records provider, model, `max_tokens`, temperature and the
observed identity. `AssertionBase.identity` contributes a judge's **type name**
and never its value. So nothing is unpromoted, nothing needs re-promoting, and
`judge_config_changed` stays false.

**And that last answer is the finding, not the reassurance.** The instrument's
instruction changed and **no document records it**. Scores may move across this
upgrade — a model told it may decline will sometimes decline where it used to
guess — and a comparison across it will report that movement with
`judge_config_changed` false, which reads as *the instrument is the same*. The
only trace in the document is `digline_version` (ADR 0014 §3), which says which
digline wrote it and not what that digline asked.

ADR 0005 §4 exists to catch exactly this class — *the instrument moved, so the
scores are less comparable than their difference suggests* — and it cannot
catch this instance, because it watches the fields a plugin reports and not the
words we send. This amendment does not close that; it is the first change to
make it concrete rather than theoretical, and it is recorded here so the next
person meets it as a known gap; it belongs with the record that gives the two
sides names, on the day that friction names itself, and not with this one.

The release note carries what a user can **act** on, which is more than the
honest half: *if judged scores move on this upgrade, it is neither your system
nor your model — it is our instruction to the judge. Read the movement, and
re-promote if it is acceptable.* Honesty alone would leave a reader with a
changed number and no next step, which is the shape of report this project
refuses everywhere else.

#### 7.10 Measured, 2026-09-23: a judge declines less when given more context

The first measurement of abstention against a variable that has nothing to do
with whether the output is true. It is recorded here rather than left in the
suite that found it, because it is a property of the instrument and it will
outlive that suite.

A `Faithfulness` check over one-sentence Italian descriptions of RSS items. Six
recorded descriptions, each judged twice, **the same text both times and only
the context changed** — twelve calls, about a penny and a quarter:

| context given to the judge | declined |
|---|---|
| the item alone — everything the model that wrote the description was given | **4 of 6** |
| the item plus an unrelated system prompt describing a reader's taste | **1 of 6** |

**The second context cannot make a description truer.** It is a paragraph about
what somebody likes to read; the descriptions are about what an article is.
Every claim supported under one is supported under the other. What the extra
text changes is the judge's willingness to answer at all — four times over.

**The next paragraph is the one untested part of this section.** The effect is
measured, the mechanism is a guess, and nothing in the section rests on it.

The mechanism this section's own design invites: §7.3 makes declining a
deliberate act with a stated reason, and the reasons these judges gave were of
the form *"it is impossible to verify which claims are
supported versus inferred from external knowledge."* More context means more
surface to relate a claim to, so the judge finds a foothold rather than a
reason to abstain. Sparse context reads to it as insufficient grounds.

**What follows for a suite author**, and it is uncomfortable: the honest context
— what the system under test was actually given, which §7 and ADR 0024 both
assume — is the one that draws the most abstentions. Padding it makes the
instrument more compliant without making it more correct, and a suite that
quietly does so is buying answers rather than measuring. There is no rule here
that would stop it, and this paragraph is the only place that says it happens.

**Not a decision, and nothing changes.** Six pairs is enough to see a four-fold
difference and not enough to size it, the descriptions came from one prompt and
one model, and no threshold, refusal or default should be built on it. It is
written because the next person to see a suite abstain will reach for the
prompt or the model, and the context is a third thing to check and the cheapest
of the three.

**The same shape, on another input.** [Adding a field to a judge's
reply](https://digline.dev/blog/added-field/) — the same text, one more thing
asked for — loosened the judge, and moving the field after the score did not
undo it. Here the judge was given more; there it was asked for more. In both, a
change to what the judge is given that has nothing to do with the truth of the
output moved what it does. Two measurements, one shape, and neither explains the
other: that post names no mechanism either, and says so.

#### 7.11 Test plan

Beyond a failing case per rule, which the conventions already require:

**Abstention is unreachable by malformation.** A reply with no `score`, a reply
with `"score": null`, and a reply with `"abstain": false` each stay an error and
none produces an abstention. This is §7.5's line as a test, and it is the one
that must never be weakened.

**A declared abstention is one.** `{"abstain": true, "reason": "…"}` produces an
errored verdict whose reason is the judge's sentence, for `LlmRubric` and for
`Faithfulness`.

**An abstention with no reason is refused as broken**, not accepted as an
abstention.

**Both at once is an abstention.** A reply carrying `abstain` and a `score` does
not score.

**The judge that never abstains is byte-identical.** An existing suite's run
document is unchanged across this release — the compatibility line, asserted on
the document rather than on a message.

**The call is counted.** An abstaining judge raises `calls`, `spent_usd` and
`tokens`, and the run's judge line bills it (ADR 0025 §4).

**`Faithfulness` distinguishes the two zeros.** A judge that returns
`total == 0` and one that abstains produce different sentences, and the first
says the judge counted.

**The fold keeps both.** A `Repeated` check whose samples abstain twice and
raise once reports both causes with their counts.

**The report prints it and `explain` does not.** Asserted in both directions, so
the deliberate absence in `explain` cannot be closed by accident later.

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
