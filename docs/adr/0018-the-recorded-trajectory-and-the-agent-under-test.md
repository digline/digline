# ADR 0018 — The recorded trajectory, and the agent under test

- Status: accepted — the text first, the implementation written against it, the
  way [ADR 0014](0014-what-may-ride-a-schema-bump.md),
  [ADR 0015](0015-the-recorded-output-and-the-declared-re-judge.md),
  [ADR 0016](0016-the-canary-case.md) and
  [ADR 0017](0017-the-journal-and-the-resumed-run.md) were
- Date: 2026-09-13
- Amended: 2026-09-15 — §1, what a provider does not report. The plugin track
  §"Not decided here" left open arrived, and met a status and a result the
  providers do not report; §1 gains a status that names that absence, a
  declared absence for the result, and the reading rule for both, and §6's
  `Completion` widens. Added rather than a new ADR: it fills in fields §1
  already declared and overturns nothing, which is the test ADR 0004's
  amendment was added under
- Amended: 2026-09-17 — §1, the call a provider does not name. `tool` is
  omitted and `tool_absence: "not_reported"` says so; `ToolsCalled` never passes
  over such a call, fails where the mismatch is settled without it, and errors
  otherwise; `called` carries `null` at its position; the second passenger of
  schema 13, justified by the train, not by the refusal. digline-anthropic
  0.5.1 shipped the plugin half first. Added rather than a new ADR on the first amendment's
  test: it fills in what §1's `tool` never said and overturns nothing
- Assumes: [ADR 0002](0002-three-worlds-and-where-the-data-lives.md) §2 (the
  payload stays where it is born, the verdict travels);
  [ADR 0004](0004-every-plugin-is-a-target-and-a-judge.md) §6 ("the names, not
  the arguments") and its *Not decided here*, which named the condition under
  which the arguments arrive;
  [ADR 0006](0006-repeated-samples-and-the-noise-floor.md) §5 (the interval a
  movement is judged against);
  [ADR 0014](0014-what-may-ride-a-schema-bump.md) §1 (the passenger rule, which
  both fields below are checked against), §6 (what a bump costs downstream);
  [ADR 0015](0015-the-recorded-output-and-the-declared-re-judge.md) §1 (a
  re-judge without a field **errors** the check), §4 (no `Disclosure` releases a
  recorded answer), §6 (the refusals)
- Carries: `resumed_at` ([ADR 0017](0017-the-journal-and-the-resumed-run.md)
  §11), pre-vetted there and boarding here
- Amends: [ADR 0012](0012-the-reading.md) §3 — the fact list is closed by that
  section, and §8 below adds to it with the sentence that justifies it
- Turns into surface: `AGENTS.md` (a check that is *on the line* is not a check
  that moved), `docs/metrics.md`, `docs/api.md`, `docs/declarative.md`
- Touches: `CLAUDE.md`'s fixed decision 9 — **reaffirmed in a second literal
  case**. A tool argument is the end company's data by construction; it is
  recorded only where it is born and no disclosure releases it. Decision 3 is
  reaffirmed by §5's mandatory matcher. Nothing in the *fixed* section is
  amended

## Context

[ADR 0004](0004-every-plugin-is-a-target-and-a-judge.md) §6 left the arguments
of a tool call out of the record, on two grounds it stated plainly: the three
providers disagree about what an argument *is*, and **nothing would read them**.
It also wrote down the condition for reversing itself, and it is worth quoting
because this record is that reversal:

> The record can gain the field without a schema bump, a migration or a
> re-promotion — it never enters the run document — so the assertion that needs
> them may bring them, and should bring its own answer about whether an argument
> check is exact, a subset, or a predicate.

An agent under gate is that assertion's case. Which tool, with what arguments,
in what order *is* the behaviour of an agent, and a suite that can only say
*it called `search` then `cite`* is blind to the half of the trajectory that
carries the meaning.

**But the argument for recording them is not the one it looks like.** "The
example asserts on them, therefore they are verdict material, therefore they
enter the document" does not survive contact with this codebase. Every assertion
here asserts on payload — `Contains` asserts on the output, `PiiAbsent` asserts
on the PII — and ADR 0015 §4 exists precisely to rule that the output still
never travels. If *asserted on* implied *verdict material*, ADR 0015 would be
incoherent. And the assertion does not need the document at all: it reads the
trajectory live out of `Response.metadata`, which is not persisted. A working
argument check costs no schema move.

What does cost one is a defect found while scoping this, which is not about
arguments and would outlive them:

    Replay.__call__  ->  Response(output=…, input=…, cost_usd=…, latency_ms=…)

`Response.metadata` is not reconstructed, because `RecordedResponse` has no
field it could be reconstructed from. So a replayed `ToolsCalled` reads an empty
mapping, takes its *nobody reported* branch, and returns **error**. Any suite
holding a trajectory assertion cannot be re-judged today; it can only be
re-judged into a row nobody gated on. That is, word for word, the failure
ADR 0015 §1 named when it decided that `cost_usd` and `latency_ms` had to ride
the record:

> a suite holding a `CostBudget` or a `LatencyBudget`, re-judged without them,
> does not fail those checks — it **errors** them, silently turning a declared
> gate into a row nobody gated on.

ADR 0015 fixed that for the budgets and missed it for the trajectory, because
budgets arrive as fields on `EvaluatorInputs` and a trajectory arrives through
metadata. Same defect, one door over, and nothing in the test suite pairs
`ToolsCalled` with `rejudge` to notice.

So the ground for the bump is **re-judge parity**, not the assertion. That
ordering decides where the field goes, which is §2.

## Decision

### 1. What is recorded

`RecordedResponse` gains a sequence, beside the answer it belongs to:

    RecordedResponse.tool_calls: tuple[RecordedToolCall, ...] = ()

    RecordedToolCall:
        tool:      str                          the name, as the target reported it
        arguments: str | None                   canonical JSON of the arguments
        result:    str | None                   what the tool returned, as text
        status:    Literal["success", "error"]  whether the tool itself failed

`arguments` is canonical JSON by the rule `record_output` already follows —
`canonical()`, sorted keys, tight separators — so the same call always produces
the same bytes and a run file stays diffable. `None` where the target reported a
call without them, which is not the same fact as an empty object and is not
written as one.

**`result` and `status` are recorded, and they are not padding.** A tool that
ran and *failed* is invisible to a names-only trajectory: the model called the
right tool, the call raised, and the agent answered from nothing. That is a
regression every other assertion in this repository is blind to, and it costs
one enum to see. `status` is also the one field here that a fake cannot forge
into vacuity — a tool that raises reports `error` whether or not the model is
real, which is fixed decision 3 holding on the offline path.

**Under the existing ceiling, not a new one.** `MAX_RECORDED_CHARS` applies to
the trajectory exactly as it applies to `output` and `input`, and over the
ceiling the whole entry is `oversize` and records neither. Whole or nothing, for
ADR 0015 §3's reason: a clipped argument re-judged produces a score that looks
like every other score, measured on evidence the document does not admit is
partial.

**`()` is a fact and `None` is not available.** The tuple is empty where the
target reported no calls, and a target that says nothing about tools records an
empty tuple too — the distinction *nobody reported* versus *called none* lives
on `Completion.tools`, where `ToolsCalled` already reads it, and is not
duplicated here. §4 is what carries it across a replay.

> **Corrected 2026-09-13, in 0.12.1.** The paragraph above is wrong, and the
> release delta-pass found it. `tool_calls` is now
> `tuple[RecordedToolCall, ...] | None`, absent in the document where the target
> said nothing and `[]` where it said the model called none.
>
> The error was in the last sentence. The distinction does live on
> `Completion.tools` — and **the replay is exactly the reader that cannot see
> it there**, because a `Replay` reads the document and never the live record.
> Collapsing both facts into `()` meant `_reported_trajectory` had one shape for
> two situations: rebuild `tools: []` and claim *the model called nothing* about
> a target that never said so, or rebuild nothing and make a real zero-call
> measurement unreadable. It did the second, so an honest run in which the agent
> answered from memory scored `fail` when it was measured and was **refused**
> when it was replayed — with a sentence saying the target reported none, which
> was false of the one run it was describing.
>
> §4's fifth refusal now turns on `RecordedResponse.replayable_trajectory`
> rather than on emptiness, so it refuses only the genuinely unreadable case and
> does so *before* the metadata is rebuilt. No schema bump: `[]` is a shape
> 0.12.0 never wrote, so absent still reads as *not reported* in every document
> that already exists.

#### Amendment, 2026-09-15: what a provider does not report

§1 was written against a plain-function target, which runs its tools itself and
so knows how each one ended. A provider plugin does not. Read off the shipped
SDKs — anthropic 1.5.0, openai 3.13.0, botocore 1.43.92 — not recalled:

| | arguments | result | status |
|---|---|---|---|
| Anthropic `tool_use`, OpenAI `function` and `custom`, Bedrock `toolUse` | reported (an object; OpenAI's a string the model wrote) | **not in the reply** | **not in the reply** |
| Anthropic `server_tool_use` | reported | a `*_tool_result` block in the same reply, joined by `tool_use_id` | an `*_error` content with the provider's `error_code`, or a result |
| Bedrock `toolUse` of type `server_tool_use` | reported | a `toolResult` block the service model admits in the output | `toolResult.status`, which AWS documents for Nova and Claude 3 and 4 only |

The first row is the ordinary case on all three, and it is structural: the
plugin makes one call, the model asks for a tool, and the reply ends there. The
tool runs afterwards, in the application, where no digline is watching. §1's
`status` had two values and a default of `success`, so recording that call
would have written *the tool succeeded* about a tool that had not yet run — the
absence read as a fact, the defect this project found twice in the same week (a
withheld answering model read as *the same configuration*, an echoed id read as
an identity).

**1. `ToolStatus` gains `"not_reported"`.** Its meaning, in one sentence: *the
provider never reports a status for a client-side call; the call may have
succeeded or failed, and the document does not know.* A plugin writes it
explicitly for every call whose status its provider does not report. The
document writes it explicitly too — absence keeps meaning `success`, which is
what every 0.12 document already says with it — and nothing reads it as
success: `status == "success"` remains the only reading of success.

A plain-function target that leaves `status` out of `metadata["tool_calls"]`
still records `success`. That is the contract it was given in 0.12.0, and
changing the default would reinterpret every trajectory such a target has
reported; a target that does not know writes `not_reported`, the way a plugin
does.

**2. The result's absence is declared, never inferred.**
`RecordedToolCall.result_absence: Literal["not_reported", "not_recorded"] | None`
says why `result` is empty, so a reader never has to tell *the tool returned
nothing* from *nobody kept it* by looking at a `None`:

- **`not_reported`** — the reply carries no result for this call: a client-side
  tool, which runs after the reply.
- **`not_recorded`** — the provider reported a result and digline did not keep
  it: a server tool's successful payload. Search pages and encrypted code output
  are bulky, and `MAX_RECORDED_CHARS` is whole-or-nothing, so recording the
  payload would drop the model's own answer with it. The payload is the noise;
  the compact signal is whether it failed, and that is kept.

A server tool that **failed** records `status="error"` and, as `result`, the
provider's `error_code` — a closed string the provider defines, which rides the
trajectory's existing boundary (`redact()` drops it, `promote_baseline` strips
it) with no new exception. Where the provider reports a failure with no code —
Bedrock's `toolResult` carries content, not a code — the result is **the error
text**, the only diagnostic that call produces. Without it a Bedrock failure
would be indistinguishable from an unexplained one, while the other two
providers hand over a code for exactly that purpose.

**Bulk is the criterion, not category.** What is left out is left out because it
is large, not because it is a tool's output: a success payload is noise, and
recording it would drop the model's own answer with it; an error is signal, and
short. An error text rides under the same `MAX_RECORDED_CHARS` ceiling as
everything else in the entry, which already turns the pathological case into
`oversize` rather than a clipped message.

`result_absence` set means `result` is `None`, checked where the value is built.
A `None` result without it keeps its 0.12 meaning: the target reported no result.

**3. The reading rule.** An assertion may assert on what is recorded — the tool
and its arguments — and never on a status or a result nobody reported. An
assertion that asks about the status of a `not_reported` call, or about the
result of a call with `result_absence` set, **errors, and never fails**, and
says which absence it met: *the provider reports no status for a client-side
call*, *the payload of a server tool is not recorded*. `ToolCalledWith` reads
neither field today; it judges the tool and arguments of a `not_reported` call
exactly as any other, and is tested doing so. The rule binds whichever parameter
first reads them.

**4. The passenger rule, answered again.**

| | 1 — the hash | 2 — the migration | 3 — the boundary |
|---|---|---|---|
| `status: "not_reported"`, `result_absence` | untouched: recording changes no score | no step: no 0.12 document can contain either, and absent still reads `success` and `None`, as it meant | rides `RecordedResponse`, as §2 |

**No schema bump**: a new value in an existing field and a new optional key,
additive, over documents that cannot already hold them. The load-bearing part is
the **old reader**, and it holds by name: 0.12.x builds `RecordedToolCall`
through its own check, so a document carrying `not_reported` is refused with
*recorded response: recorded tool call: RecordedToolCall.status must be
'success' or 'error', got 'not_reported'* — never read as success. That refusal
is tested in both directions: this reader reads 0.12 documents unchanged, and
the 0.12.1 reader, taken from its tag where the history is present, refuses a
document carrying the new value.

The asymmetry, stated: 0.12.x ignores keys it does not know, so a server tool's
**successful** call — `status="success"`, `result_absence="not_recorded"` —
reads there as a success with no result. It loses the reason and invents
nothing: the status is one the provider reported. The value that would be read
as a fact that is not one is the value the old reader refuses.

**5. `Completion` widens** (§6). `Completion.tool_calls` carries the live
record beside `tools`, names in the same order, and `as_metadata()` puts it
under its own key. A plugin that fills it raises its floor by hand, per §9.

#### Amendment, 2026-09-17: the call a provider does not name

§1 declared `tool: str`, and every writer since refuses `""`. It never said what
a call the reporter **did not name** is, and three readers answered for it,
differently and each wrongly. Parked on 2026-09-15 when 0.13.1 shipped only the
half that stops such a call contaminating the others (`ToolCalledWith` counts
it unreadable and judges the rest); this is the half that says how it is
**recorded**. It rides schema 13, the second passenger of that train.

**What the three SDKs surface.** Measured through each SDK's own response path
— a mocked transport for anthropic 1.5.0 and openai 3.13.0, botocore 1.43.92's
own `rest-json` parser for Converse — with the name left out and with
`"name": null`, beside a named second call. Not recalled:

| | the contract | what the SDK hands over | what the plugin did with it |
|---|---|---|---|
| Anthropic `tool_use` | `ToolUseBlock.name: str`, required | `block.name is None`, both shapes: responses are not validated (`_strict_response_validation=False`) | 0.5.0: `str(block.name)` → **a tool named `"None"`, silently**, in `tools` and `tool_calls` alike. 0.5.1 (2026-09-17) raises like the other two |
| OpenAI `function` / `custom` | `name: str`, required | `function.name is None`, both shapes, for the same reason | `str(name or "")` → `ToolCall(tool="")` raises: **the whole case errors**, the named call with it |
| Bedrock `toolUse` | `name` in the service model's `required` | the key is **absent**, both shapes: the parser drops a `null` member | `.get("name", "")` → the same raise, the same whole-case error |

None of the three providers produces this shape under its own contract; every
one of them hands it through when a server does not honour that contract. That
is not hypothetical here: the OpenAI plugin exists for compatible endpoints
behind `base_url`, and the Anthropic SDK reads `ANTHROPIC_BASE_URL` from the
environment, so a gateway in front of either reaches the plugin unvalidated.
Two more readers already misread it on the core side: `record_trajectory` does
`str(item.get("tool", ""))`, so a plain-function target's `"tool": None` is
recorded as `"None"`; and `ToolsCalled` does `str(name)` over `tools`, so the
live `[None]` is judged as a call to `"None"`. The 0.14 document reader is the
fifth: `str(_required(entry, "tool", …))` reads `"tool": null` as `"None"`.

**1. The value, and its sentence.** `tool` is **omitted, never `null`** — `null`
is exactly the value every reader above turns into a name — and the absence is
carried by its own key, in the vocabulary §1's first amendment already
declared:

    {"tool_absence": "not_reported", "arguments": …, "status": "not_reported", …}

*The reporter handed over a call and did not name the tool it called; the
document does not know which tool it was.* The reporter is the provider, for a
plugin, and the target, for a plain function — never digline, which records
every name it is given. That is why `not_reported` is the only value:
`not_recorded`, digline's own omission, has no case here and is refused.

In memory the absence is `tool=None` on `ToolCall` and on `RecordedToolCall`,
and `Completion.tools` becomes `tuple[str | None, ...]`, its consistency rule
comparing `None` to `None`. There is no second field to disagree with it: `None`
had no earlier meaning (it was refused), so it is the absence, and the document
writes `tool_absence` exactly where `tool` is `None`. `""` stays refused
everywhere — a writer that does not know says `None`. A plugin reads the SDK's
`None`, a missing key and `""` alike as not reported: none of the three APIs
admits an empty tool name, so an empty one is not a name either.

The reader accepts an absent `tool` only beside `tool_absence: "not_reported"`,
and refuses by name `"tool": null`, a `tool` beside `tool_absence`, and any
other `tool_absence` value. `record_trajectory` takes a mapper's `"tool": None`
as the absence; a mapping with no `tool` key at all stays a malformed entry and
raises, by its *strict about shape* rule.

**2. What the assertions do.** `ToolCalledWith` does not change: 0.13.1 already
counts a nameless call unreadable, steps over it, and errors only where nothing
readable matched. It is now tested on a call recorded as `tool_absence`, not
only on a live `None`.

`ToolsCalled` **never passes** over a nameless call: the sequence it checks
cannot be known equal to the expected one. Whether it errors or fails is
0.13.1's rule, written here rather than inherited: *a nameless call decides a
verdict only where the verdict turns on it.* `ToolsCalled` returns one verdict
over the whole sequence, so there is no *only that call* to error: the rule is
applied to the check, and gives

- **`fail`** where the mismatch is established without the nameless call: the
  number of calls differs from `expected`, or a named call sits at a position
  whose expected name is different. Both are findings the reply does establish,
  and erroring them would hide a real regression behind a reporter's gap.
- **`error`** otherwise — every named call matches its position, so the
  nameless one is what decides — saying that *the provider reported a call
  without naming it*, and at which position.

The `reason` renders the position as *an unnamed call*, never as a name.

**The one `null` this amendment writes is in `called`.** In `Score.metadata`,
`tool_calls` counts every call, the unnamed one included. `called` keeps the
positions, with `null` where the reporter gave no name:

    {"tool_calls": 3, "called": ["search", null, "cite"]}

It is a `null` and not an omission because `called` is a sequence: dropping the
entry would shift every name after it into a position it did not hold. This is
the value rule 1 forbids for `tool`, so the list is not read the same way.
`null` in `called` means *this call was not named*. A reader never
`str()`s an entry, and never takes the list's length as the number of named
calls. No reader under `src/` reads `called` today. The first one will meet this
`null` through `--json`. `digline.wire` emits a verdict's metadata only for the
keys in `Disclosure.score_metadata`, so that reader will be one whose suite
declared `called`, and the `null` reaches it exactly as written. The sentence
therefore goes into `docs/api.md` beside the key, rather than waiting for that
reader to find it.

A non-string, non-`None` entry in `tools` becomes unreadable, not `str()`ed. The replay rebuilds `tools` with `None` at the same
position, so a replayed `ToolsCalled` judges what the live one judged.

**3. The passenger rule (ADR 0014 §1).**

| | 1 — the hash | 2 — the migration | 3 — the boundary |
|---|---|---|---|
| `tool_absence` (omitted `tool`) | untouched: a recording field inside `RecordedResponse`, and `config_hash` is the suite's configuration | the 12 → 13 step writes **nothing** for it: no schema-12 document holds an omitted `tool`, because every 0.14 writer refuses one, and an absent `tool_absence` means *named*, which every call in such a document is | payload: it rides `RecordedResponse`, so `redact()` drops it with the response, `promote_baseline` strips it through `without_responses`, and `digline.wire` never learns its name. On a `ToolsCalled` verdict the count travels by `travels()` and `called` does not |

**The residue the step cannot reach, stated.** A schema-12 document may already
hold `"tool": "None"` that was an unnamed call — written by digline-anthropic
0.5.0 or earlier behind a non-conforming endpoint (0.5.1 errors the case
instead), or by `record_trajectory` from a
mapper's `None`. It cannot be told apart from a tool really named `None`, which
both the Anthropic and the OpenAI name patterns admit. So the step does not
rewrite it, since that would be a guess, and does not refuse the document, since
that would refuse a legitimate name. Rewriting would be guessing; refusing
would break valid documents. It is left alone and named in the schema-13
release's changelog entry, in these words:

> **Not repaired: a `"None"` already recorded.** A run written before this
> release may hold a tool call recorded as `"None"` that was really a call the
> provider did not name: digline-anthropic 0.5.0 or earlier behind an endpoint
> that omitted the name, or a plain-function target that reported
> `"tool": None`. It cannot be told apart from a tool really named `None`, so
> `digline migrate` neither rewrites it nor refuses the document.

**4. The old reader, and what justifies the bump.** The bump does not create
the refusal. A 0.14.x reader already refuses an omitted `tool` by name, at any
schema: it reads a call through `_required(entry, "tool", …)` and says
*recorded tool call: recorded tool call is missing the mandatory field 'tool'*.
It ignores `tool_absence`, as it ignores every key it does not know, but that
cannot produce *a call with no tool*, because the call cannot be built without
`tool`. The silent misread exists only for `"tool": null`, and rule 1 closes it
by omitting `tool` instead of writing null.

The bump is justified by three things, in this order:

1. **The train.** Schema 13 moves for the `Repeated`-fold stamp regardless
   (ADR 0024 §6.2), and this passenger costs it no migration. ADR 0014 wants a
   bump to carry what it honestly can.
2. **A named refusal instead of one that reads like corruption.** At schema 13,
   0.14.x refuses the run file on `schema_version` before a call is read,
   saying *a newer schema* and pointing its holder at an upgrade. Without the
   bump, the only refusal would be *missing the mandatory field 'tool'*. That is
   true, but it reads as a damaged file, not a newer one.
3. **Above all: the inner refusal is the journals' only protection.**
   `JOURNAL_VERSION` is independent of `SCHEMA_VERSION` (ADR 0017 §2) and does
   not move with this bump, and journal lines are read through the same
   `case_from_dict`. A journal carrying a nameless call gets no outer lock. The
   refusal by `'tool'` is all it has, so that refusal is tested as a property in
   its own right, not left as a side effect of the reader's code.

Tested in both directions, on the 0.12.1 test's pattern: 0.14.1's source taken
from its tag, and skipped where the tags are absent. This reader reads every
schema-12 document, migrated, unchanged. 0.14.1 refuses a schema-13 document on
its version. 0.14.1 refuses a document **stamped 12** that carries a nameless
call, and the test asserts the refusal names `'tool'`, not merely that it exits
non-zero: that is the property a journal relies on. The same refusal is
asserted on a journal leg read by 0.14.1's `case_from_dict`. And this reader refuses
`"tool": null`, `tool` beside `tool_absence`, and `tool_absence:
"not_recorded"`, each by name.

### 2. It rides `RecordedResponse`, because that is where the boundary already is

Not a free-standing field on `CaseResult`, and not `Score.metadata`.

`RecordedResponse` is the one structure in the document already classified as
payload, and every sentence it has earned is the sentence a trajectory needs:
`redact()` replaces it with `RecordedResponse(withheld=True)` and keeps only the
count; `digline.wire` does not know its name; `promote_baseline` strips it
through `without_responses`, so the one committed artifact in this product stays
payload-free. A trajectory placed there inherits all of it and **adds no
mechanism**. There is no new flag, no new disclosure, and no new question to get
wrong at a boundary.

`Score.metadata` is the wrong home for the mirror-image reason. It is the bag
that *is* projected onto the wire, filtered by `disclosure.score_metadata`, so
argument values there would be the end company's data one declaration away from
leaving — and the declaration would look, to whoever wrote it, exactly like
disclosing a model name. §5 keeps that bag numeric.

The recording stays gated behind `Suite.record_responses`, unchanged and still
off by default. A suite that does not opt in stores nothing, and its argument
assertions keep working, because they never read the document.

### 3. The passenger rule (ADR 0014 §1)

Two passengers, and they pass for different reasons, which is the point of
filling the table in rather than asserting the result:

| passenger | 1 — the hash | 2 — the migration | 3 — the boundary |
|---|---|---|---|
| `tool_calls` (§1) | recording changes no score, pairs no verdict differently and moves no bar; `record_responses` and `disclosure` have never been in the fingerprint | `()` — a run that recorded no trajectory had none, and none is recoverable | payload, and **no `Disclosure` releases it**: it rides the structure `redact()` already drops whole |
| `resumed_at` (ADR 0017 §11) | a fact about the *process*, not about the suite | absent, which is *not recorded* and is never an invented time | a fact about the software house's own instrument; travels in clear, like `digline_version` and `promoted_at` |

`resumed_at` boards here because ADR 0017 §11 pre-argued it against these three
conditions and then declined to move the schema for it alone — "it does not ride
today because nothing forces the schema to move today". Something does now, and
ADR 0014's economics are explicit that a bump should carry as much as it
honestly can.

`_STEPS` gains `10: _add_schema_eleven`, and it is the second step that **writes
nothing**: `tool_calls` absent already reads as the empty tuple, and `resumed_at`
absent already reads as *not recorded*. Every key it could add would mean what
its absence means, and adding them would churn every committed baseline in the
world to say nothing. `_NON_ADDITIVE` gains no row and no document is refused.

### 4. The replay hands back what it recorded, and refuses when it cannot

`Replay.__call__` reconstructs the metadata a trajectory assertion reads:

    metadata={"tools": [...], "tool_calls": [...]}

`tools` is rebuilt from the recorded names so that `ToolsCalled` re-judges
identically, and `tool_calls` carries the arguments for §5. The key that is
**not** written is the one that would lie: a source run that recorded no
trajectory writes neither key, so the assertion takes its *nobody reported*
branch and errors — which is the honest outcome and is why §6's refusal exists
to catch it first.

A fifth refusal joins ADR 0015 §6's four, and it is checked in `_check` before
the driver starts and before a judge is paid:

> the suite holds a trajectory assertion and the stored run recorded no
> trajectory — refused by name, naming the assertion and the flag.

Refused rather than errored, because an errored check *is* the defect this ADR
exists to close. A replay that quietly produced an unjudged row would be the
gate-that-is-not-a-gate wearing a different hat.

### 5. The assertion: `ToolsCalled` untouched, `ToolCalledWith` added

    ToolCalledWith(tool="lookup", arguments={"id": "…"}, match="exact" | "subset")

**`ToolsCalled` does not change.** It owns the order and the names, and its
docstring already refuses "a second semantics" — re-litigating order inside a
second class is precisely that. The two read the same trajectory and answer
different questions, which is the only arrangement in which a reader can read
either verdict without asking which one is in force.

**One class with a `match` parameter**, not `ToolCalledWithExactly` and
`ToolCalledWithSubset`. They differ by one comparison and every rule around them
— the empty mapping, the missing tool, what the `reason` says — would otherwise
be written and maintained twice. That is `Affix`'s precedent and its argument.

The answers ADR 0004 asked this assertion to bring:

- **`arguments` is mandatory and has no default.** A matcher with nothing to
  match passes on every trajectory, which is fixed decision 3's vacuously green
  assertion.
- **`match="exact"`** is mapping equality after canonicalisation.
  **`match="subset"`** requires every declared key to be present and equal, and
  ignores the rest — which is what a suite wants when a model adds a
  `request_id` nobody declared.
- **A predicate is not in this record.** §"Not decided here".
- **The tool is named**, and a trajectory with no call to it is a `fail`, not an
  error: the model not calling what it was told to call is the finding, not a
  missing measurement.
- **Absent trajectory is `error`**, on `ToolsCalled`'s rule and its wording.
  **Unparseable arguments are `error`, not `fail`**, on `JsonSchema`'s rule: an
  undecodable value is a different problem from a mismatched one, and conflating
  them makes the diff unreadable.

**What reaches `Score.metadata` is a measurement and never a value:**

    {"arguments_matched": int, "arguments_expected": int}

Both cross a boundary on their own merit by `travels()`. No argument text enters
the bag, so no suite has to declare anything and no reviewer has to notice that
they should have. A reader without any disclosure still learns that two of three
declared arguments matched.

### 6. `tools` stays names, and the reason is a silent corruption

The trajectory arrives under its own key, beside `tools` and never inside it.

`ToolsCalled` reads its input as `tuple(str(name) for name in found)`. Had
`tools` widened from names to records, `str({...})` would stringify a mapping
and the assertion would compare rendered dictionaries against expected names —
**failing, not erroring**, on every case, with a `reason` that reads plausibly.
A widening that turns a passing gate into a silently failing one is not a
widening; it is the kind of change that is found a release later by somebody
re-reading a baseline.

So: `Completion.tools` keeps its type and its meaning, and the live trajectory
reaches an assertion as **its own key** in `Response.metadata`, beside `tools`
rather than inside it. Every existing reader stays correct by construction.

`Completion` itself gains nothing in this release, and that is ADR 0004's own
rule applied to this record rather than an omission: no plugin fills such a
field in this scope, and *a field no assertion reads is a dead field*. The
example's target fills `Response.metadata` directly, which is what makes it
independent of the plugins. `Completion` widens when the plugin track ships and
something fills it — §"Not decided here".

### 7. The example: an agent under the gate

`examples/langgraph/` is the tenth example and the real consumer this field
needed. A LangGraph agent with two tools — a lookup and an action — where which
tool, with what arguments, and in what order carry the behaviour.

- **The target is a plain function**, in process, as `examples/langchain`'s is.
  No server and no port. It reports its trajectory by filling
  `Response.metadata` itself, which is what makes this example independent of
  any provider plugin: the plugins' own widening is a separate track with its
  own release (§"Not decided here").
- **The output is the projection, not the message list.** The target returns the
  final text as `output` and the ordered `(tool, arguments, result, status)`
  beside it. This is not a convenience: LangGraph mints `ToolMessage.id` as a
  uuid4 with no public hook to pin it, so the raw message list is not stable
  across processes and a committed baseline built on it would churn on every
  run. The projection was measured byte-identical across separate processes.
  Dropping the id is decision 9 behaving correctly — it is payload-side and
  carries no evaluative meaning.
- **The model is faked and the tools are real.** No stand-in in `langchain-core`
  supports tool calling — all five raise `NotImplementedError` from
  `bind_tools` — so the example ships a three-line subclass that accepts the
  binding and replays scripted messages. The tool bodies execute genuinely, so
  `result` is computed and `status` is earned rather than scripted.
- **Zero telemetry, stated rather than assumed (fixed decision 5).**
  `langsmith` is a hard, non-optional dependency of `langchain-core`. It was
  observed to open no socket with a clean environment, and the example pins it
  shut anyway: `LANGSMITH_TRACING=false` and `LANGCHAIN_TRACING_V2=false`, set
  in the workflow environment and not from inside Python, because the lookup is
  cached on first read and a late assignment is ignored. Four names are live
  across two namespaces; two are pinned and the reason is written down here so
  the next reader does not have to rediscover the cache.

### 8. Five lines the report has been missing

Decisions of record from the triage of 2026-09-11. They ride this release
because it is the first one to touch `report/` and `explain/`, and because
§"Consequences" of ADR 0014 is right that the next bump should be expensive.

Adding to `explain`'s fact list **amends ADR 0012 §3**, which closes it. The
amendment is declared in this record's header and each line below earns its
place by that section's own test: it says something the report says, and a
reading that omitted it would describe a measurement that was not made.

1. **On the line.** A check whose measured interval contains its threshold is
   **named**, in a section of its own, distinct from passing and failing. Its
   pass or fail is an accident of which samples were drawn, and a reader who is
   shown it as a clean pass has been told something the measurement does not
   support. The reading of "the measured band" is the one this codebase already
   has: `sample_min <= threshold <= sample_max`, at storage precision and
   inclusive, by ADR 0009 §1. An unsampled check has no interval and is
   therefore never on the line — an honest absence rather than a computed one.
   **The exit code does not move.** This names a fact; it does not gate.
2. **The judge-changed lead.** Where `judge_config` differs from the reference,
   `explain` **opens** with it, before any number: *the judge changed: scores
   are not comparable to the reference*. The fact has existed since ADR 0005 and
   is reported today in last position, after the counts it qualifies. The
   promotion to the lead is the change, and `rejudged` is the precedent — it is
   first "because it qualifies every count under it", and so does this.
3. **Overlap, therefore no claim.** Where the two intervals overlap, the
   sentence goes at the **head** of the diff's report rather than only on the
   check. Two systems that are not distinguishable by a check is a conclusion
   about the comparison, and a conclusion that appears only in a per-row detail
   is one a reader assembles for themselves or not at all. Silent at zero, on
   the precedent the diff head already sets for its other clauses.
4. **Per-call exceedances.** *N of M judgments exceeded the per-call figure
   (max $X)* — where a `cost_budget` passes on the fold and individual samples
   did not. A ceiling declared per call and checked only on the mean is a
   ceiling that is not the one the suite declared, and the run that surfaced
   this had 9 of 720 over it.

   **Derived, not newly measured**, which is what keeps it out of §3's table.
   `budget_score_at_precision` forces a sample's stored score onto the side of
   the threshold that `within(measured, cap)` puts it on, so
   `meets(sample, threshold)` **is** the within-cap test: N is an exact count
   over `Score.samples`, which the document already carries. The figure itself
   inverts the score — `cap * (1 - s) / s`, with the cap read from `max_usd`,
   which survives the fold unchanged because a constant averaged with itself is
   itself — and the worst call is `sample_min`.

   One honest limit, stated rather than discovered later: a sample within about
   a millionth of the cap is pinned to the threshold by that same clamp, so an
   inverted cost would read as *exactly at the cap*. The line reports such a
   sample as **at the cap** rather than printing a figure the clamp chose.
   Silent where nothing was sampled, on the `diff.exceeds` precedent — *0 of 0*
   reports an absent measurement as a null result.
5. **The three-way spread.** Where a judge's samples fall in more than two
   directions, the spread is reported per category rather than as a single
   number. Two directions is disagreement; three is a judge that is not
   measuring one thing, and a `spread` of max-minus-min reports both as the same
   figure.

   **Derived for a check that scored, and one thing had to change for the check
   that did not.** The raw vector is on `Score.samples`, is serialized and
   survives redaction, so the three counts are available from any stored run
   that produced a score. But the verdict this line exists to explain — the one
   that **errors under the agreement floor** — is built by a branch that
   carried no samples and no metadata at all, so the single check a reader most
   needs explained was the only one holding nothing to explain it with.

   So the refusing verdict now carries the counts the fold has just computed:
   `samples`, `agreement`, `errored_samples` and `scores`. No schema field —
   `Score.metadata` is a free-form bag and this adds no key to the document's
   shape — and all four are numbers, so all four cross a boundary on their own
   merit by `travels()`. A suite that never trips the floor produces the bytes
   it produced before.

   **The category is not decided here.** A group never reaches a run file —
   ADR 0010 §1 keeps it inside the aggregate's *name* and nowhere else, and
   `CaseResult`, `CaseOutcome` and `Verdict` all carry none — so a per-group
   figure is computable where the `Suite` is in hand and not from the document
   alone. Until that is ruled, the line ships **per check**, which is computable
   from the document and says the same thing about the judge.

Every string is added in **both locales**, and the no-advice gate of ADR 0012 §5
runs over them like every other. ISO dates and the decimal point stay
unlocalised, so two readings of one run remain comparable line by line.

### 9. What the bump costs, in order

ADR 0014 §6, unchanged and not negotiable, because the tree is red until it is
finished:

1. `pyproject.toml` to the version carrying schema 11.
2. A row in `RELEASED` in `tests/test_example_caps.py`.
3. `digline migrate` over every document under `examples/*/.digline/`.
4. Every example cap raised — all nine sit at `<0.12` today and admit no
   release that can read a schema 11 document.
5. The rendered report pages regenerated, in the established order: commit the
   example, render, commit the report on top.
6. The window, stated rather than hidden: between the bump and the release
   reaching the index, a reader cannot resolve the examples at all.

The plugin floors gate is **name**-based, so the bump forces no plugin release.
A plugin that later widens a *field* rather than importing a new name is
invisible to that gate and must raise its floor by hand, with a comment saying
why — the precedent is `pytest-digline`'s, written for the same hazard.

## Consequences

**A gate that silently was not one becomes one.** Every suite holding
`ToolsCalled` has been unre-judgeable since `rejudge` shipped, and the failure
mode was an errored row rather than a refusal. It is now one or the other, by
name.

**The arguments arrive where ADR 0004 said they would, at the cost it predicted
plus one it did not.** The record gains them without widening what travels; what
it did not foresee is that the re-judge would have to be taught to hand them
back, and that this is what makes the field a document field at all.

**Two passengers make this bump cheap and the next one expensive.** Nothing here
reserves a field for later use; `resumed_at` boards because it was vetted in
advance and something finally forced the move.

**A check that is *on the line* will be read as a new kind of failure by
somebody.** It is not one, and the exit code says so. What it is is the
instrument admitting that a verdict rests on which samples were drawn.

## Alternatives considered

**Arguments in `Score.metadata`.** Rejected in §2. It is the one persisted bag
that is also projected onto the wire, so this would put customer data one suite
declaration away from leaving, behind a declaration indistinguishable from
disclosing a model name.

**A free-standing `tool_calls` on `CaseResult`.** Rejected: it would need
`redact()`, `wire/`, and `promote_baseline` each taught about it separately,
which is three chances to get a boundary wrong in exchange for nothing that
`RecordedResponse` does not already provide.

**Widening `Completion.tools` to records.** Rejected in §6: `str()` over a
mapping turns a passing gate into a silently failing one.

**Shipping the assertion with no schema move.** Genuinely available, and
rejected on the strength of the defect rather than on the feature: the assertion
works without the document, but the re-judge does not work without the record,
and leaving that open would ship an assertion whose replay silently errors.

**Recording the raw message list in the example.** Rejected in §7: it is not
byte-stable across processes, and a committed baseline that churns is a baseline
nobody reads.

**Making *on the line* a status or an exit code.** Rejected. The exit codes are
the contract (`AGENTS.md` §6), and a third outcome would break every gate in
every user's CI to report something that is not a regression.

## Test plan

Beyond a failing case for every new rule, which the conventions already require:

**The boundary, planted.** `tests/test_wire_boundary.py`'s marker suite gains a
tool-argument marker: a recorded argument whose value is a unique token. The
assertion is that the token appears in the run file written inside the perimeter
and in **nothing** produced by `redact()`, `run_to_json(..., redacted=True)`,
`run_document`, `compare_json`, `delta_json`, `explain_json`, or the rendered
report of a redacted run.

**The fifth refusal, on its sentence.** A suite holding a trajectory assertion,
replayed over a run that recorded no trajectory, is refused by name — asserted
on the line a user acts on, not on the exception type.

**The replay is the same measurement.** A suite with `ToolsCalled` and
`ToolCalledWith`, run against a stubbed target with `record_responses=True` and
then re-judged, produces the same scores case for case. Then the same replay
with a changed `arguments` produces the expected flip, which is the feature.

**Promotion strips, and the count survives redaction.** A promoted baseline
carries no trajectory; a redacted document carries `withheld=True` and the
count, and neither carries an argument.

**The default is byte-identical.** A suite without `record_responses` produces a
run file identical to the one the previous release produced, modulo
`schema_version` — asserted on the bytes, as ADR 0006 §11's test does.

**Both locales, and the gate.** Every string added by §8 exists in `en` and
`it`, the key sets stay identical, and the no-advice gate runs over the new
strings.

**On the line is measured, not asserted.** A check whose interval straddles its
threshold is named; one whose interval clears it is not; an unsampled check
never is. The exit code is asserted unchanged across all three.

## Not decided here

**A predicate matcher for arguments.** A callable fingerprints as its type name
in `AssertionBase.identity`, so two different predicates would be
indistinguishable to `compare()` — which is a real limit and needs its own
answer about how a suite declares what it is checking. `exact` and `subset`
cover the cases in front of us.

**The provider plugins' own widening.** All three already hold the arguments and
drop them one expression later, and each would need its floor raised by hand
(§9). It is a separate track with its own release, and the example deliberately
does not depend on it.

**Arguments crossing a boundary.** The answer is no, by §2, and it will be asked
— an end company asking for its own data back is entitled to it. The route is
the perimeter they already own, not a flag that makes every other suite's
arguments one line from travelling.

**Capture — turning an application's own traffic into cases.** Adjacent and
still unbuilt; it consumes an application's log, not a stored trajectory. It
keeps its own future number rather than reserving one here.
