# ADR 0060 — The steps of a trajectory: read live, recorded in the run, collected from the calls a target makes

- Status: accepted 2026-11-03, by Alessandro Prandini, the text first, as it
  stands at `f912e868`: every item marked *decided here* taken, with the
  names it proposes (`steps_of`, `collecting` and `around_target`).
  Proposed 2026-11-03. **Its decisions were ruled before this record
  was written**, by Alessandro Prandini on 2026-11-03, in the conversation of
  the session that wrote it: that the steps of a trajectory enter 1.1, live and
  in the run document, with four assertions on them; and, after a measurement
  of the design against the code, that the collection is opened by `host` and
  priced only where the target declares a price list. They are stated here as
  ruled. **What this record adds is marked *decided here***: the names of two
  functions and of one argument of `execute()`, the refusals a suite meets,
  and the keys each assertion writes. Each was proposed, for acceptance to
  take or remove item by item
- Shipped: 1.1.0
- Date: 2026-11-03
- Opens: **a third passenger on schema 23, when its code lands, and nothing
  before.** This record writes no `SCHEMA_VERSION`, no line of `_STEPS` and no
  code. Schema 23 is on the branch of #869, with
  [ADR 0057](0057-the-replay-reads-the-trajectory-the-live-run-read.md)'s two
  fields; `steps` joins them on the same `WritesNothing()` step (§5).
  `RECORDING_VERSION` stays 1: the recording's format has not shipped, and
  what moves in it moves before it does (§6). No `OUTPUT_VERSION`
- Amends, each by a dated note beside the place it amends, which points here.
  Every text is kept as written:
  - [ADR 0057](0057-the-replay-reads-the-trajectory-the-live-run-read.md) §1
    and §4: schema 23 carries `steps` on a recorded response as well (§5);
  - [ADR 0058](0058-the-recorder-a-call-recorded-where-the-application-makes-it.md)
    *Consequences*, whose first sentence, *"No run document changes"*, no
    longer holds for 1.1 (§5);
  - ADR 0058 §5 and §10: a run of digline collects the calls a wrapped client
    makes, recorder on or off, and the promise of a cost near zero off holds
    for every process that is not a run (§3);
  - ADR 0058 §7, whose *"A single call is one model step"* this record
    confirms and builds on (§1)
- Assumes: [ADR 0001](0001-verdict-not-score.md) (a verdict has
  three outcomes, and `error` is the one for a fact nobody established);
  [ADR 0004](0004-every-plugin-is-a-target-and-a-judge.md) §8 (a cost not known is said, never
  zero); [ADR 0014](0014-what-may-ride-a-schema-bump.md) §1 and §2 (what may
  ride a bump, and absent as *not recorded*);
  [ADR 0015](0015-the-recorded-output-and-the-declared-re-judge.md) §3 and §4
  (whole or nothing, and a recorded response never crosses a boundary);
  [ADR 0018](0018-the-recorded-trajectory-and-the-agent-under-test.md) §1 (a
  call nobody named), §5 (nothing the model sent in `Score.metadata`) and §6
  (`tools` beside `tool_calls`); [ADR 0025](0025-the-tokens-and-the-bill.md)
  §1 (`usage`, counts beside a cost);
  [ADR 0058](0058-the-recorder-a-call-recorded-where-the-application-makes-it.md)
  §5 (the episode and `attach`), §7 (the step), §10 (the cost off) and §11
  (one serializer)
- Touches, in `CLAUDE.md`'s *fixed* section: **decision 1** is upheld: the four
  assertions are pure functions in `digline.core`, callable on their own, and
  the collection lives above the driver, which receives it as an argument.
  **Decision 3** is upheld, and is why a suite whose checks contradict each
  other is refused (§4). **Decision 9** is not edited: a recorded response
  never crosses a boundary (ADR 0015 §4), and the names a check writes into
  `Score.metadata` are tools' names, as `ToolsCalled` already writes them.
  **Decision 5** is upheld: nothing here makes a call of its own
- Number: 0060. Swept on 2026-11-03, before a line was written, across every
  branch on the remote, every worktree of this repository and the two open
  pull requests. `origin/main` (`80cf7557`) holds 0058 at most; 0059 is on
  #888 (`adr-amend-0058-0023`); 0061 is taken by a worktree of its own, and
  is not this record's. The highest number taken anywhere below 0061 is 0059
- Owed: the three lines on digline.dev that every new record needs (the nav,
  and the two tables the site builds its pages from). Until they land, the
  `docs` job reads red on this record's pull request, which is the state the
  site's runbook expects, and no required check reads it

**How to read the clauses.** *Ruled* is a decision taken before this record
and transcribed. *Decided here* is a name or a detail this record proposes,
and acceptance rules on it.

**Lines cited here are at `80cf7557`**, unless a line names another commit.
The measurement in *Context* was made on 2026-11-03 at that commit, by the
session that wrote this record, with a client built in the test's own way and
no network; the script is not part of the repository.

## Context

**A trajectory today is one reply long.** A provider target makes one call per
case: `ProviderTarget.__call__` calls `_complete` once
(`src/digline/targets/provider.py:207`), and the plugin reads that one reply
with `completion_of`. `Completion.as_metadata()`
(`src/digline/targets/completion.py:191`) writes `finish`, `tools` and
`tool_calls` for it, one entry per tool call the reply asked for, and
`default_mapper` (`src/digline/run/driver.py:594`) hands them to every
assertion as `metadata["response"]`.

**An agent under test is several calls, and only the last one reaches the
assertions.** Measured: a plain-function target that makes three calls inside
one case, through `AnthropicTarget` and a client that answers each with
`tool_use` blocks, returns what its author would write without help, the last
`Response`. `metadata["response"]` then holds the third call's one tool, and
the first two calls' three tools are gone; so are their cost and their
latency. An assertion on the order of an agent's tools cannot depend on an
author merging lists by hand.

**The recorder already builds steps, in one place.** When an episode closes
(`src/digline/recorder.py:1971-1983`), each call seen becomes a `model` step
with the finish its reply reported, followed by a `tool` step per tool call it
asked for. Nothing on the live side does the same. Each call's reply is read
by the same function on both sides: each plugin's recording map calls the
`completion_of` its target calls.

**And the only check on order is equality.** `ToolsCalled`
(`src/digline/core/assertions.py:1223`) compares the whole sequence of names.
A limit on the steps, a subsequence, a call that must come before another and
a call that must never happen have no check, and they are the checks an agent
that acts needs: *it looked up the order before refunding it, it never closed
the ticket, it stayed within ten turns.*

## Decision

### 1. One function makes the steps

*Ruled.* A pure function in `digline.core`, *decided here* as `steps_of`,
takes the calls of a trajectory in order, each as the `finish` its reply
reported and the tool calls it asked for, and returns the steps: for each
call, one `model` step with its finish, then one `tool` step per tool call, all
indexed from 0. It is the only place steps are made:

- `Completion.as_metadata()` writes `steps` for its one call, beside `finish`,
  `tools` and `tool_calls`. **A single call is one model step and its tool
  steps**, as ADR 0058 §7 says, so a provider target's steps come from what
  `completion_of` already reads, and **no plugin changes** for them;
- the close of an episode calls it, in place of the loop at
  `recorder.py:1971`;
- the collection of §3 calls it over the calls of a case.

*Noted 2026-11-04, by Alessandro Prandini's ruling, and the list above kept as
written.* A second function, `steps_as_reported` in `digline.core.recording`,
not exported from `digline.core`, lays each tool step over its call in the live
form of §2: `steps_of` decides the order and the indices, and it is still the
only place steps are made.

`RecordedStep` moves from `digline.core.recording` to `digline.core.run`,
beside `RecordedToolCall`. Its docstring says it is in `recording` *"because
the run document does not hold steps"*, and §5 ends that reason.

### 2. Live, the steps are `metadata["response"]["steps"]`

*Ruled.* Beside `tools`, `tool_calls` and `finish`, written by whatever writes
those: a provider target through `as_metadata()`, the collection of §3, and a
function target that fills it itself, as it may fill `tools`. A step is a
mapping with `index` and `actor`, a `model` step's `finish` where one was
reported, and a `tool` step's call in the form `tool_calls` already uses.

**`tools` and `tool_calls` stay, and are not derived from the steps in 1.1.**
They are what `ToolsCalled` and `ToolCalledWith` read, and what a function
target writes by hand today. Where a response reports both steps and calls,
the tool steps must name the same calls in the same order, and the reader that
records them refuses a disagreement, as `Completion` refuses two lists that
disagree (`completion.py:162`).

### 3. A run collects the calls its target makes

*Ruled.* `execute()` takes, *decided here* as `around_target`, a context
manager entered around **each call of the target**, and only that call. Its
type is a `Protocol` in `digline.core`. `host` passes
`digline.recorder.collecting()`, and so the driver imports nothing from above
it.

- **The collection is a `ContextVar` in `digline.recorder`.** The wrapper reads
  it before its check of whether recording is on (`recorder.py:648`). Where a
  collection is open, the wrapper reads the reply with the plugin's map and
  hands the `Completion` to the collection, recorder on or off. Where none is
  open, the call passes as it does today.
- **The mode is opened only by `host`, never by the wrapper on its own.** A
  process that is not a run of digline never opens one, so ADR 0058 §10's cost
  off holds for production as written: one more read of a context variable
  per call, held by the same threshold
  (`tests/test_recorder.py:217`, 25 µs). The test that nothing of
  `digline.core` is imported off (`tests/test_recorder.py:186`) holds as
  written, because the collection lives in `digline.recorder`.
- **Only the target's call.** The collection is closed before the assertions
  run, so a judge whose client is wrapped never adds its calls to the agent's
  trajectory.
- **When the collection is not empty, it wins.** The driver composes
  `metadata["response"]` from it: `steps` by §1, `tools` and `tool_calls` from
  the steps, `finish` from the last model step. A provider target whose
  injected client is wrapped reports its one call twice, through
  `as_metadata()` and through the collection; they are the same `Completion`,
  and the collection's is the one used, so nothing is counted twice.

  *Noted 2026-11-04, by Alessandro Prandini's ruling, and the bullet above
  kept as written: the hook's `settle` composes, in `digline.recorder`; the
  driver applies it.* The calls collected are `Completion`s and their prices
  are a target's list, both in `digline.targets`, which `digline.run` does not
  import. So the context manager `around_target` gives, on entering, a
  `settle` that composes the response, and the driver applies it to what the
  target returned.
- **What a collection sums.** `usage`, summed over the calls. Latency, summed
  over the calls, which is **the time spent waiting for the model and excludes
  the time the tools took**: it is not the duration of the case, and the
  record says so wherever it is written. Cost is **not known**: `cost_usd` is
  `None`, and `unpriced` says why, *"calls collected through a wrapped client:
  counts read, no price list declared by the target"*. A target that declares
  a price list is priced with it. The reason is measured: a recording map
  reads a reply with no price list (`digline_openai/recording.py:76`, an empty
  one), and a function target has none the driver could read.

  *Noted 2026-11-04, by Alessandro Prandini's ruling, and the bullet above
  kept as written: priced at the model each call reports.* A target with a
  price list is every `ProviderTarget`, whether the suite declared its prices
  or the plugin shipped them. Each collected call is priced at the model the
  call reports, its resolved id, and not at the model the target was asked
  for, because an agent may call two. A call whose model the list does not
  have is not priced, and `unpriced` names the model. Bedrock's reply names no
  model, so a call collected through it is never priced. One call not priced
  leaves the case's cost unknown, because a partial cost is not a cost.
- **An episode the application opens inside the target.** Off, it is the empty
  context it is today (`recorder.py:1795`), and its calls reach the case's
  collection. On, it records as it does today, and its calls reach the
  collection as well.
- **A client built inside the call** works where it is wrapped at every call:
  the collection is a context variable, not a property of the client.

**Known limits, written as such.**

- **A thread.** The collection does not cross a `threading.Thread` or a
  `ThreadPoolExecutor` worker, for the reason ADR 0058 §5 gives for the
  episode's id. The way across is the same: `attach(id)`. The driver runs
  cases serially (`driver.py:1230`), so the limit is the target's own threads.
- **A library caller.** Whoever calls `execute()` without `host` has no
  collection until they pass `around_target`.
- **A target that does not wrap its client** stays as it is today: its
  response carries what it reports, the last call's for an agent that returns
  the last one. That absence is readable where it matters: a check that needs
  steps the target did not report errors (§4), and the error names `wrap()`.
  No new line in the report.

### 4. Four assertions on the steps

*Ruled*, with the discipline of `ToolsCalled`
(`assertions.py:1223`): binary, threshold 1.0, deterministic, mandatory
arguments with no default (fixed decision 3), the three outcomes of ADR 0001,
and a call nobody named deciding a verdict only where the verdict turns on it
(ADR 0018 §1, amended 2026-09-17).

```python
Subsequence(tools: Sequence[str])                       # these, in this order, anything between
Before(first: str, then: str)                           # no `then` without a `first` before it
Never(tool: str)                                        # never called
MaxSteps(limit: int, count: Literal["model", "tool"])   # at most `limit` steps of that actor
```

**What each reads.** The three on order read **the names of the `tool`
steps**, from `metadata["response"]["steps"]`; where `steps` is absent they
read `tools`, as `ToolsCalled` does. That fallback loses nothing: the order of
a response's tool steps is the order of its tool calls, which is why ADR 0058
reads schema 23's fields as steps without loss. **`MaxSteps` reads `steps`
and has no fallback.** Counting an agent's turns from its tool calls would
read three calls as one.

**`Before(first, then)`** passes where `then` was never called. It is not
vacuous, because it fails on a `then` with no `first` before it, and its
metadata says `then` was called zero times. *Both, and in order* is
`Subsequence([first, then])`.

**Refused when the check is built.** `Subsequence([])`; an empty name in any
of the four; `Before(a, a)`; `MaxSteps` with a `limit` below 1, or with no
`count`.

**Refused when the suite is built**, *decided here*, because every case that
is not a calibration case is asked every assertion
(`driver.py:972`), so a contradiction fails every case:

- `Never(x)` beside a `Subsequence` that holds `x`, a `ToolsCalled` whose
  `expected` holds `x`, or a `ToolCalledWith(tool=x)`;
- `Never(x)` beside `Before(_, x)`, which could then only pass by default, or
  beside `Before(x, b)`, which would be a `Never(b)` under another name;
- `Before(a, b)` beside `Before(b, a)`;
- `MaxSteps(count="tool")` with a `limit` below the length of a
  `Subsequence`.

*Corrected 2026-11-09 (P-1588):* *"a contradiction fails every case"* holds
for the first item and the last. The second and the third pass both checks
on a turn that calls neither tool, and fail every turn that calls the tool
they disagree on. They are refused all the same, and since this correction
the refusal says on which turn the two contradict each other, where it said
of them too that the suite would fail every case.

**An `error`, never a `fail`:**

- the target reported neither `steps` nor `tools`, or, for `MaxSteps`, no
  `steps`. Absent is not empty, and the sentence names the key, how a function
  fills it, and `wrap()`;
- a `model` step whose finish is `tool_use` with no `tool` step after it: the
  provider contradicted itself, `ToolsCalled`'s rule at `assertions.py:1296`
  applied step by step;
- a call nobody named, where the verdict turns on it.

**`Score.metadata`**, *decided here*, as `ToolsCalled` writes it
(`assertions.py:1345`): counts, and the names of tools where the check is
about names. A name is a string, and does not cross a boundary unless a
`Disclosure` declares it.

- `Subsequence`: `matched`, `expected`, `tool_steps`, `called`;
- `Before`: `violations`, `first_calls`, `then_calls`;
- `Never`: `occurrences`;
- `MaxSteps`: `steps`, `limit`.

**In TOML**, the four are declared as `subsequence`, `before`, `never` and
`max_steps`, beside `tools_called` (`src/digline/host/toml_suite.py:119-120`).
**In a replay**, each joins the trajectory checks `_check` reads
(`src/digline/run/replay.py:163`), and one whose steps or names a recorded
response cannot give back is refused before it runs, as `ToolCalledWith` is.

### 5. In the run document: `steps` on a recorded response

*Ruled.* `RecordedResponse` gains `steps`, last in its field order, beside
ADR 0057's `finish` and `tools`, on schema 23's step, which stays
`WritesNothing()`:

- **written when reported**, under `Suite.record_responses`, with no switch of
  its own: the model is `usage`, as for the other two;
- **absent is *not recorded***, and never `[]`, which would say the target took
  no step;
- **written by `_response_to_dict`**, a tool step's call inline in the form a
  run document writes a call, so a call has one written form wherever it is
  kept (ADR 0058 §11). The size ceiling counts a trajectory once, on its steps;
- **whole or nothing** with the text, under the same ceiling (ADR 0015 §3);
- **read back by the replay**, so a replay judges the steps the live run
  judged, which is the promise ADR 0057 keeps for `finish` and `tools`.

### 6. In a recording, the steps move into the response

*Ruled.* An episode's steps are the steps of its response, and a single call
now has steps too. So `Recording.steps` goes, and an episode is told from a
single call by its own `id`, which only an episode carries. The recording's
format has not shipped, and `RECORDING_VERSION` stays 1.

## Consequences

**A run's document changes in 1.1**, by one optional key on a recorded
response, and only on schema 23's step.

**`execute()` gains one keyword argument**, with no default behaviour change:
without it, a run reads what its target reports, as today.

**The recorder's wrapper gains one read per call**, of a context variable,
and production never sets it.

**No plugin changes** for the steps (§1). The plugins' releases with 1.1 are
owed for ADR 0058's reasons, not this record's.

**`host/toml_suite.py` gains four names**, and `docs/api.md` four entries.

## How it will be known to be repaired

- The measurement in *Context*, run as a test: three calls through a wrapped
  client inside one case, and every assertion reading six steps, the summed
  `usage`, and `cost_usd` `None` with its reason.
- The live-against-replay test of `tests/test_recorded_output.py` holding an
  agent of several calls, its steps judged the same in both.

## Alternatives considered

**The driver opens a recorder episode for each case.** Rejected: the driver is
`digline.run`, and the recorder sits with `digline.host` (ADR 0058 §6). And the
test that nothing of `digline.core` is imported off pins the modules loaded to
`digline` and `digline.recorder`, so the collection's context variable cannot
live below the recorder.

**Steps derived from `tool_calls` alone.** Rejected for `MaxSteps`: an agent's
turns are its model calls, and the calls of three replies concatenated read as
one.

**Summing cost with the plugins' price lists.** Rejected: a recording map
reads a reply with no price list, and the driver would have to guess which
list a function target meant.

## Not decided here

- **`MaxSteps` on steps of kind `engine`.** ADR 0058 §9 foresees a step a
  person declares by hand, for an engine that calls no model and no tool. When
  it exists, whether `count` takes it is ruled then.
- **Concurrency.** A driver that runs cases in parallel needs a collection per
  case across workers. The driver is serial (`driver.py:1230`), and that ADR
  is its own.
