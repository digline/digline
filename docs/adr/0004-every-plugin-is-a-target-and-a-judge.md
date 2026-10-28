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
- Amended: 2026-10-27, **accepted 2026-10-27** — §8, a cost that cannot be
  computed, accepted in the pull request that lands its code (#569). It
  widens §6's record by one field and §3's counters by one, and overturns
  nothing above it, so it is an amendment by the same test. **Schema-free**:
  what it adds lives in the process, the run document already carries
  `every_cost_known`, and no version of a format moves
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

### 8. A cost that cannot be computed

*Amendment, 2026-10-27, from #569. **Status: accepted 2026-10-27**, in the
pull request that lands its code; proposed until then. §1–§7 stand. It widens §6's `Completion` by one field and §3's
judge by one counter, and it records the seven rulings of 2026-10-27 on what
the draft left open.*

#### 8.0 Not decided here

Three things, each found in the writing and ruled on by none of the seven.

1. **The unknown-model branch of `Pricing.cost`.** §8.4 moves the refusal of
   a token kind with no rate. The other refusal in the same method, a model
   the list does not know, is not moved by this section, and the two sides
   reach it differently:
   - **The target never reaches it after an answer.** The driver calls the
     target's `preflight(cases)`, which refuses the model before the first
     call.
   - **The judge does.** `JudgeBase.preflight()` is not called by the driver:
     a plugin's tests call it, and so can a suite. So a judge whose model has
     no price answers, and its price raises in `_ask`, which is §8.6's false
     line. §8.6's repair covers it: the line becomes true and the check stays
     `error`.

   Whether that refusal also becomes an unpriced call, or the driver calls
   the judge's `preflight()` before the first case, is not decided here.
2. **Where the sentences go when the bill is not printed.** §8.3 prints them
   on standard error after the bill line. Two front ends print no bill line
   there:
   - `digline run --json`, where the bill rides the document on standard
     output and standard error carries nothing of it;
   - `digline-mcp`, which prints no bill line at all.

   On both, the outcome still arrives as `every_cost_known: false`. The
   sentence does not, and where it should is not decided here.

   *Added 2026-10-28; the item above is kept as written.* The enumeration is
   incomplete, and `digline rejudge` is the third front end. It prints neither
   the bill line nor the sentences on standard error. With `--json` it builds
   its document without `usage`, so not even the markers arrive. And it calls
   the judge, whose replies can be unpriced. Read in `src/digline/cli/main.py`
   at `8ab47910`, without running it.
3. **The target side of §8.6's repair.** The false line was measured on the
   judge (§8.6). A target whose price list raises after an answer was not
   measured, and what its line says is not decided here.

#### 8.1 Two facts, and one of them had no word

A call that answered can leave digline holding three things about its cost:

| | counts | cost | what carries it today |
|---|---|---|---|
| **priced** | read | computed | `Completion(text, usage)`; `Response(usage=…, cost_usd=…)` |
| **counts not recorded** (#629, #739) | not read | not known | `Completion.usage = None` |
| **cost not computable** | read | not known | nothing: the price raises, and the check or the case errors |

The third is #569. digline-anthropic reads `usage.inference_geo`, knows a rate
for `None`, `"global"` and `"us"`, and raises `UnknownModelError` on any other
value, `"not_available"` included. The call was made, answered and paid for,
and the case is lost to a problem of accounting.

Two ways out are closed:
- **A plugin overriding `ProviderTarget.__call__`** to hand over
  `cost_usd=None` itself. `test_every_plugin_inherits_the_reading` refuses it,
  for the reason its docstring gives: one reading of a reply, not three. It
  would also have left the judge refusing the same reply. That shortcut was
  reverted in #744.
- **`usage=None`.** It already means *counts not recorded*, and this call's
  counts were read. A `None` meaning both *we could not read the tokens* and
  *we read them and cannot price them* would lose the tokens, and it would
  make one value mean two things. `every_call_seen` and `every_cost_known`
  are two markers, not one, for the same reason.

#### 8.2 `Completion` gains `unpriced`

| field | type | |
|---|---|---|
| `unpriced` | `str \| None`, default `None` | why this reply's cost cannot be computed, though its counts were read |

- **`None` is the ordinary case**, and it is what every plugin written before
  this amendment returns. The pair `(text, usage)` reads as `None` too. So, by
  the guarantee in §6, *third-party plugins are unaffected, by construction*.
- **Refused with `usage=None`.** A reply whose counts were not read is the
  second row of 8.1, and it already says its cost is not known.
  `Completion(usage=None, unpriced=…)` would say it twice, under two names, so
  it is refused at construction, and an empty sentence is refused with it. The
  refusal is the plugin's bug surfacing in the plugin's call.
- **A sentence, not a flag**, because the refusals it replaces told the
  operator what to do: *"Pin the request or the workspace to one of the two"*,
  *"Use the 5-minute cache"*. A flag loses that, and §8.3 says who reads it.

#### 8.3 Who reads the sentence: the person who ran the command

*Ruled 2026-10-27.* **The run prints each distinct sentence on standard error,
after the bill line.** The reader is the person who ran the command. The
refusal this replaces was addressed to that person, and standard error is
that person's perimeter (fixed decision 9, as amended by ADR 0043). Moving a
case from *errored* to *judged* must not silence what the operator used to be
told to do. So the field is read, which is the answer §6's rule asks of it: a
field no assertion reads is a dead field, and this one is read by the run.

The sentences reach the front end beside the run, in the process, and never in
the run document. One sentence repeated on every call is printed once.

Two ways were refused:
- **`Response.metadata` for an assertion.** It hides the sentence from the
  person, and hands it to an assertion nobody wrote.
- **A `bool`.** It loses the actionable text, which is the one reason the
  field is a sentence.

#### 8.4 Four refusals move, and the premise is what changed

| where | what it refuses today | after |
|---|---|---|
| digline-anthropic, `geo_multiplier` (#392) | an `inference_geo` with no rate | an unpriced call |
| digline-anthropic, `_one_hour_writes` (#368) | tokens written to the 1-hour cache | an unpriced call |
| digline-bedrock, `_refuse_unpriced_writes` (#368) | a cache write at a TTL other than `5m` | an unpriced call |
| core, `Pricing.cost` | cached-read or cache-write tokens with no rate in the list | an unpriced call |

*Ruled 2026-10-27, for #368's two.* **The premise changed, not the
conclusion.** #368 refused these writes because there was no way to say *this
cannot be priced*, and now there is: §8.2. What #368 protected was that a
write nobody has a rate for is never priced at another rate, and that stands.
Left refusing, these would be two identical facts treated two ways, the
incoherence #735 removed between `_graded` and `_ratio`.

*Ruled 2026-10-27, for the core's.* **The core's refusal moves too.** It is
the same fact, counts read and a rate missing, decided in the core instead of
a plugin. Left refusing, it would be two behaviours for one fact inside the
core.

**How the core tells it apart: a predicate, `Pricing.why_unpriced(model,
usage) -> str | None`.** `None` says the list can price these counts. A
sentence says why it cannot. The reading asks it before it calls `cost`, and
the sentence it returns is the call's `unpriced`. `Pricing.cost` still raises
when it is called on counts it cannot price, so a caller outside the reading
that does not ask first still gets no number nobody stated.
- **Why a predicate, and not a catch.** `UnknownModelError` is raised for a
  model the list does not know as well as for a rate it lacks. Catching it
  would turn a typo in a model's name into *cost not known*: two things under
  one name.
- **Its default answers for the list's own rates**, under the condition on
  which `Pricing.cost` raises today: tokens of a kind whose rate is `None`.
  `Pricing` is a concrete class, and users build their lists from it, never
  by implementing it: `ANTHROPIC_PRICING.override(…)` (`docs/api.md`), `free(…)`,
  `[target.pricing]`, or `Pricing(per_model=…)`. Each is an instance of the
  base class, so each inherits the default. **A user enters by doing
  nothing**: a list of theirs with no cached-read rate moves exactly as one
  of ours does.
- **Not a default that says *I don't know*.** With that default nobody moves,
  not even digline's own lists, which are instances of the same class. A
  repair the user has to ask for is not a repair.
- **The risk, named.** A subclass that overrides `cost` to price what its list
  has no rate for would inherit the predicate, and be read as unpriced
  **before** its `cost` is called. For it, that is a regression. None is known
  today. `_WhereServed` in digline-anthropic overrides `cost`, and only to
  multiply the base price by the geography, so it prices nothing the list has
  no rate for.
- **The obligation: whoever overrides `cost` overrides `why_unpriced` too.**
  It is held on this project's repositories by a test (§8.9), which also
  binds `_WhereServed`. There the override has work of its own: it answers
  with the base's predicate, and where that returns a sentence, `cost` will
  not be called and `take` will not run, so it takes the factor itself
  (§8.8). Nothing can bind a third party to the obligation. The test
  documents the rule with an instance.

In each plugin, `_complete` returns its `Completion` with `unpriced` set to
the sentence the refusal carried, less the refusal, on the target and on the
judge.

#### 8.5 The two readings of a reply

**The target.** `ProviderTarget.__call__` stays the only reading, and plugins
keep inheriting it:

    unpriced = reply.unpriced or (
        None if usage is None else self.pricing.why_unpriced(self.model, usage)
    )
    cost_usd = None if usage is None or unpriced is not None
               else self.pricing.cost(self.model, usage)

The `Response` it builds carries `usage` (the counts, read), `cost_usd=None`
and the sentence. **The first two are not a new pair.** `Response` has carried
them apart since ADR 0025 §5, and the driver's `CallTotals.plus(tokens=…,
spent_usd=None)` already reads that as one call seen and counted, its tokens
on the line, its money not, and `every_cost_known` false (#563). The sentence
is new on `Response` and on `EvaluatorInputs`, both in the process, for §8.3
and for §8.7.

**The judge gains `unpriced_calls`.** §3's judge accumulates `calls`,
`spent_usd` and `latency_ms`. ADR 0025 §4 added `tokens`. #563 added
`raised_calls`, and #629 added `uncounted_calls`. Neither of those two was
recorded in an ADR, and this records them beside the new one:

| | which calls | in `calls` | in `tokens` | in `spent_usd` |
|---|---|---|---|---|
| `raised_calls` (#563) | raised | no | no | no |
| `uncounted_calls` (#629) | answered, counts not read | yes | no | no |
| **`unpriced_calls`** | answered, counts read, cost not computable | yes | **yes** | no |

`uncounted_calls` cannot carry the new case. It already means *counts not
recorded*, and counting an unpriced call there would take its tokens off the
line, which is the loss 8.1 refuses. In `_ask` the three are exclusive:

    if reply.usage is None:   self.uncounted_calls += 1
    elif unpriced is not None: self.unpriced_calls += 1
    else:                     self.spent_usd += self.pricing.cost(...)

The judge keeps the distinct sentences beside the counter, for §8.3. Each
count is monotone and never reset, like the rest (§3).

**The driver reads both counters, and never assumes `True`.** `judge_totals`
reads both with a default, as it reads `raised_calls`, so a judge written by
hand still satisfies `Billable`. The judge's `every_cost_known` is the least
complete of two readings:

- `uncounted_calls`: `False` where it is above zero, `True` at zero, and *not
  recorded* where the judge keeps no such count;
- `unpriced_calls`: the same.

They are summed by the rule the line already sums by: `False` over `None`
over `True`. **A judge that keeps one count and not the other is *not
recorded*, unless the count it keeps is above zero.** Nothing established that
it priced every call it answered. `True` is reached only by reading two
zeros, never by default. That is the rule #629 restored for
`uncounted_calls` (*"Read off the judge, not assumed"*), applied to the second
counter.

`counted` stays `calls - uncounted_calls`. An unpriced call's counts were
read, so it is counted. The run's share is the difference of two readings, as
in ADR 0025 §4.

#### 8.6 The false line, measured and repaired here

*Ruled 2026-10-27: repaired by this amendment, which gives it the words, and
not left to an issue.*

**What it says today**, measured at `80b70b7e` with an injected judge and no
key. The judge's price list had input and output rates and no cached-read
rate, and the reply reported 50 cached-read tokens. In `JudgeBase._ask`,
`pricing.cost` raises **after** `self.calls += 1` and outside the `try` that
counts `raised_calls`. The check errored, and the line read:

| judge calls | `calls` | `counted` | tokens on the line | `spent_usd` | `every_cost_known` |
|---|---|---|---|---|---|
| one, with cached reads | 1 | 1 | 0 in / 0 out | 0.0 | `true` |
| one priced, then one with cached reads | 2 | 2 | 100 in / 10 out, one call's | 0.00012 | `true` |
| control: two priced | 2 | 2 | 200 in / 20 out | 0.00024 | `true` |

The second row has the shape of the control. The line says every call counted
and every cost known, and it carries one call's money and tokens fewer than
were made.

**After §8.4** that reply is an unpriced call and does not raise. **A price
that still raises**, from a price list digline did not write, is read by the
same rule as an unpriced call: the call is counted, its tokens are on the
line, its money is not, and `every_cost_known` is `false`. The check stays
`error`, because nobody declared the call unpriced, and its reason stops
blaming the judge.
- **Today:** *"the judge raised UnknownModelError: …"*.
- **After:** the judge answered, and pricing its reply raised. The sentence
  names the exception, and the call answered.

#### 8.7 A `CostBudget` over an unpriced cost: the error stays, the word moves

*Ruled 2026-10-27.* **A declared ceiling that cannot be verified is not a
ceiling met**, and `error`, with exit `2`, is the honest answer (fixed
decision 4). That stays. The word does not. *"cost_usd is missing"* is false
where the cost was not missing but could not be computed: the distinction
between absent and zero, applied to a message.
- **No cost and no sentence:** as today, *"cost_usd is missing: an
  unverifiable budget is not a budget met"*.
- **A sentence:** the message says the cost is *not computable*, and carries
  the plugin's sentence.

The reason of a check is payload under fixed decision 9, and it is where these
sentences were before §8.4 moved them, as the reason of an errored check.
Nothing reaches a boundary that did not reach it before.

#### 8.8 `_WhereServed`: a requirement, no longer a detail

*Ruled 2026-10-27.* `_WhereServed`'s docstring guarantees that *"a cost is
never priced at another call's geography"*. The guarantee rests on every reply
being priced: `_complete` sets the factor, and the next `pricing.cost` takes it
and resets it. An unpriced reply calls no `pricing.cost`, so the factor it
would set is left for the next call. **digline-anthropic leaves no factor set
on an unpriced reply**, whether the sentence is its own or the price list's
(§8.4).

**The requirement is held by asking the price list directly.** After an
unpriced reply, `target.pricing.cost(...)` is asked with no call between, and
answers at the listed rate. Leaving the factor set turns it red. A second call
in a known geography does not: its own `_complete` sets its own factor before
anything is priced, so it is priced right whether or not the first left one.
That test is kept beside the first, as what a reader would write first, and it
is not what holds this.

#### 8.9 What it changes, and how that is held

**The acceptance criterion, in four directions.** Each is tested with an
injected client, so that it runs with no key. The first three run on the
target and on the judge, and the first on each row of §8.4. The fourth runs on
the target alone: `CostBudget` reads the target's cost, and no judge's.

1. **Cost not computable.** The reply reports `inference_geo:
   "not_available"`, a 1-hour cache write, or cached reads with no rate. In a
   suite with no `CostBudget`:
   - the case is **judged**: its checks are `pass` or `fail`, none is `error`,
     and no `error_kind` is set;
   - the line reads `every_cost_known: false`, with `counted` equal to `calls`
     and the reply's tokens on it;
   - standard error carries the bill's *cost not known for every call* and,
     after it, the sentence, once.
2. **Counts not recorded.** The plugin hands back `usage=None`, as today, and
   it reads as *not recorded* (#629, #739):
   - `counted` is below `calls`;
   - `every_cost_known` is `false`;
   - the call's tokens and cost are not on the line;
   - the judge's `unpriced_calls` does not move, and no sentence is printed.
3. **Cost known.** The reply reports `"global"` or `"us"`, as today, and the
   figure is on the line at the multiplier `GEO_MULTIPLIERS` gives:
   - `every_cost_known` is `true`;
   - standard error says neither *cost not known for every call* nor a
     sentence.

   This is the control: the sentences above appear only where their fact
   holds.
4. **A `CostBudget` over an unpriced cost.** The first direction's reply, in a
   suite with a `CostBudget`:
   - the budget is `error`, and its reason says *not computable* and carries
     the plugin's sentence;
   - the content checks of the same case are judged;
   - three exit codes, which are not one: `run_exit_code` gives `2`, for an
     unjudged check beside judged ones, and so does `compare`; `digline run`
     exits `0`, because ADR 0049 §3 keeps its `2` for a run that judged
     nothing.

**Beside the four:**
- **The geography of the next call** (§8.8). After an unpriced reply,
  `target.pricing.cost(...)` answers at the listed rate. Beside it, two calls
  in sequence, the first unpriced and the second in a known geography, the
  second priced at its own multiplier; that one does not go red when the
  factor is left set, for the reason §8.8 gives.
- **The false line.** The second row of §8.6's table, with a price list that
  raises: `every_cost_known` is `false`, both calls' tokens are on the line,
  and the check's reason does not say *"the judge raised"*. It is red on
  `80b70b7e`, measured before it is written, and that is how it is believed.
- **Whoever overrides `cost` overrides `why_unpriced`** (§8.4). Every subclass
  of `Pricing` defined under `src/` and `packages/*/src` that overrides `cost`
  overrides `why_unpriced` too. Today that is `_WhereServed`. The test
  carries a fake subclass that does both, as the rule's example. **Its
  mutation:** take the predicate off the fake subclass, and the test goes
  red. It binds this project's repositories and no third party.
- **The default predicate, both ways.** A list built with `Pricing(…)` or
  `override(…)` and no cached-read rate gives an unpriced call with no
  `error`. A list with the rate gives the figure.

**The four are believed by mutation:**
- **`ProviderTarget.__call__` ignoring `unpriced`** makes the first red,
  because the cost is computed.
- **`_ask` counting an unpriced call in `uncounted_calls`** makes the first
  red on the judge, because the tokens leave the line.
- **`_knew_every_cost` defaulting a missing `unpriced_calls` to zero** makes
  the hand-written judge's test red. That judge keeps `uncounted_calls = 0`
  and no `unpriced_calls`, and it must read *not recorded*.
- **`_WhereServed`'s factor left set on an unpriced reply** makes the
  geography test red: the price list, asked directly after that reply,
  answers at the first call's geography (§8.8).

**`examples/prompt-first`.** *Ruled 2026-10-27: its documentation, not its
measurement.* Since #417 (2026-10-03), its live path has errored every case
on a workspace whose replies report `inference_geo: 'not_available'` (#569,
run of 2026-10-14).
- **The documentation:** a reader whose workspace reports that geography is
  told, in the example's documentation, why its costs are not known.
- **Not the measurement:** a run of the example is not §8.9's measurement,
  which takes an injected client and no key. So #651's dependence on a key
  does not enter here.

**What does not move:**
- `SCHEMA_VERSION`, `OUTPUT_VERSION` and `JOURNAL_VERSION`;
- any document, and any key of `--json`.

Every field this adds lives in the process, and the document's
`every_cost_known` already carries the outcome. `every_cost_known` keeps its
meaning: it already read *false* for a call whose cost digline does not know.
A third-party plugin behaves as before, because it never sets `unpriced`, and
a third-party price list behaves as before unless it lacks a rate for tokens
a reply reports.

**What the versions are**, by *Choosing the version* in `RELEASING.md`, whose
enumeration names *"an exit code changed"*. #642 is the precedent that moves a
minor for one input's exit; #735 (#738), whose exit did not move, is a patch.
- **digline: a minor.** Whoever has a price list with no rate for tokens a
  reply reports gets an exit that moves, from `2` to a judged case, **without
  doing anything**. That holds whether the list is one of ours or theirs,
  because the predicate's default is inherited by every list built from
  `Pricing` (§8.4). Through §8.4's last row, that includes every plugin's
  users and digline-openai's. One user who moves is enough for *"an exit code
  changed"*. The cost of this is nil, because digline's next release is
  already a minor for #642.
- **digline-anthropic: a minor.** A run over an unpriced geography or a
  1-hour cache write exits `2` today. After, `digline run` exits `0`, and
  `digline compare` exits `0` or `1` by its verdict. Its floor rises to the
  core that carries `unpriced`.
- **digline-bedrock: a minor**, for the same reason, over a cache write at a
  TTL other than `5m`. Its floor rises the same way.
- **digline-openai: no release.** Its code has no path of its own that cannot
  be priced. It returns no cache-write count while
  `CACHE_WRITES_ARE_INSIDE_PROMPT_TOKENS` is `None`. Its one refusal over
  usage, *"the provider returned no usage"*, is the second row of 8.1 and
  not this. What moves for its users moves in the core.

  *Added 2026-10-28, by the ruling of 2026-10-27 on #629's half in the
  plugins; the bullet above is kept as written.* That second row now reaches
  the plugins. A reply with no usage block, refused by digline-openai and
  digline-bedrock unless the model is declared `free()`, and an
  `AttributeError` in digline-anthropic, is handed over as
  `Completion(usage=None)`, and its case is judged. A count the SDK types as
  required and the reply lacks is the same row, never `0`, and the counts that
  were read go with it. One the SDK types as optional, omitted, stays `0`.
  `thinking_tokens` stays per field. **So digline-openai has a release after
  all, a minor**, because an exit code changes. The minors of the other two
  carry it beside §8.4's. A model declared `free()` reads a missing usage
  block as zero, ruled 2026-10-28: `free()` is the user's declaration, so it
  falls under the second half of the rule, where a count omitted by
  declaration means there was nothing to count.

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
