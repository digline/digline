# `digline record` — the calls your application makes, kept as cases

While an application is being built, the calls it makes to a model are the
material a suite is made of. The recorder keeps them, at the place where the
application makes them, in the shape a suite reads: what the call was asked,
what decided how it answered, and what it answered. A person then reads them
back and names the ones that become cases.

> **Arrives with digline 1.1.** On 1.0.3, `digline record` and
> `digline.recorder` do not exist.

It is four things:

- **`digline.recorder.wrap`**, around the provider's own client, in the
  application;
- **a switch**, `.digline/<tenant>/recorder.toml`, and `digline record on`,
  `off` and `status`;
- **`digline record import`**, which lists a suite's recorded answers and
  writes the ones a person names, with their yes or no, into a file the suite
  loads;
- **`digline record compare`**, which shows a suite's recorded answers by case
  and by setup, and writes nothing.

The decision behind it is
[ADR 0058](adr/0058-the-recorder-a-call-recorded-where-the-application-makes-it.md),
and the rules the import follows are [ADR 0023](adr/0023-capture.md)'s.

## Wrapping the client

```python
import anthropic
import digline.recorder as recorder

client = recorder.wrap(anthropic.Anthropic(), app="helpdesk", tenant="acme")

reply = client.messages.create(
    model="claude-sonnet-4-5",
    max_tokens=200,
    system="Give the category of the ticket.",
    messages=[{"role": "user", "content": ticket}],
    suite="category",
)
```

- **`app=`** names the application. It is written on every recording.
- **`tenant=`** is the tenant the recordings are filed under,
  `.digline/<tenant>/recordings/`. A name is **development**: one tenant,
  fixed. A function, called at every call, is **production**: each customer's
  calls are filed under that customer's tenant.
- **`root=`** is the directory that holds `.digline/`, the current directory
  if left out.
- **`suite=`**, on the call, is the name of the suite the call belongs to:
  the same name as that suite's `Suite(name=...)`. It is a name, where
  `--suite` on the command line is a path to the suite's file. A call that
  names no suite is recorded under `_unassigned`, with the function it was
  made from, and enters no suite until a person gives it one.
- **`digline_vars=`**, on the call, adds the variables a template was filled
  with to the case, beside the messages, where the user message mixes a
  template and the data.

A recording keeps the call in three compartments: the **case**, the messages
(less the leading instructions, for OpenAI) and the `digline_vars`; the
**setup**, everything else the call decided; and the **response**, the answer
with its measurements. The response also carries its **input**, the case's
messages as JSON text: the question the import puts beside the answer for the
judge, whether the call was made, streamed or awaited.

`suite=` and `digline_vars=` are taken out of the call before it reaches the
provider's SDK, whether the recorder is on or off. The client returned is the
client: everything but the call is its own.

The clients recorded are the ones a plugin maps, one method at a time:

| Plugin | Client | Methods |
|---|---|---|
| `digline-anthropic` | `anthropic.Anthropic`, `anthropic.AsyncAnthropic` | `messages.create`, `messages.stream` |
| `digline-openai` | `openai.OpenAI`, `openai.AsyncOpenAI` | `chat.completions.create`, `chat.completions.stream` |
| `digline-bedrock` | a `bedrock-runtime` client | `converse`, `converse_stream` |

Any other client is refused when it is wrapped, by name. Bedrock has no
asynchronous client in botocore; aiobotocore's is a package of its own that no
plugin maps, so it is refused like any other.

**The application's call never fails because of the recorder.** Whatever goes
wrong while recording, the call returns what the provider returned, and the
reason it was not recorded is counted (below). An exception of the SDK itself
propagates as it always did.

## A streamed reply

A streamed call is recorded too: `create(..., stream=True)`, and the methods
that stream by name, `messages.stream()`, `chat.completions.stream()` and
`converse_stream`.

- **The application gets the stream the SDK built**, the same object, event
  by event, as it reads them. The recorder watches each event pass and holds
  none back. The stream keeps its class: `isinstance(stream, anthropic.Stream)`
  is true, and `type(stream)` is a subclass of it that watches.
- **It is recorded when the stream ends**, read from its events into the reply
  the whole answer would have been. The same request streamed and not
  streamed gives the same case, the same setup and the same text.
- **A stream closed before its end, or dropped unread, is not recorded**: half
  a reply is not a reply. It is counted `stream abandoned`.
- **An exception inside the stream** propagates as the SDK raised it, and is
  counted under its class's name, `APIStatusError` for example.
- **Usage that arrives only on request** is never requested by the recorder:
  it does not change the request. OpenAI sends counts in a stream only with
  `stream_options={"include_usage": True}`. Without them the reply is recorded
  with no counts, which a recorded response may have, and the status says
  `usage not reported`.
- **Inside an episode**, a streamed call joins the episode when its stream
  ends. If the episode has closed by then, the call is recorded as an orphan
  with the episode's id, and noted `ended after its episode`; the episode
  counts it among the calls it did not see.

## An asynchronous client

`wrap` takes `anthropic.AsyncAnthropic` and `openai.AsyncOpenAI` as it takes
their synchronous clients, and records the same thing for the same request.

```python
client = recorder.wrap(anthropic.AsyncAnthropic(), app="helpdesk", tenant="acme")

reply = await client.messages.create(..., suite="category")

stream = await client.messages.create(..., stream=True, suite="category")
async for event in stream:
    ...

async with recorder.episode(client, suite="order-agent", case={"ticket": t}) as ep:
    await asyncio.gather(lookup(...), lookup(...))
```

- **What the application awaits is what the SDK returns**: the reply, or the
  SDK's asynchronous stream, unread, watched as the application reads it, as a
  synchronous stream is.
- **An episode is the same with `async with`.** Its id is a context variable,
  so every task created inside it, `asyncio.gather` among them, is in it. A
  task created before it is not: there, `async with recorder.attach(ep.id)`
  puts the task's calls in it, and without it they are orphans.
- **A recording is written inside the event loop, and never `fsync`ed.** It
  is a small file, written beside its place and linked into it, so no reader
  sees half of one. It is durable at the operating system's pace: a crash of
  the machine may lose the last recordings written before it. A recording is
  a sample, not a ledger. Writing one holds the caller, and an event loop
  with it, under 2 ms on the CI's Linux runner, the least of three launches
  on each of three Pythons (measured on 2026-11-03), so it is not moved to a
  thread. **The first recording
  imports digline's core**, about 90 ms where it was measured, which holds
  the loop when the client is asynchronous. So when the recorder is on as the
  client is wrapped, `wrap()` imports the core then, at the application's
  start, and the first call costs what the second does. Switched on later
  from the file, while the application runs, the first recording pays it,
  once. (Measured on 2026-11-03, on a laptop running macOS, CPython 3.14.)

## A turn of an agent: `episode`

```python
with recorder.episode(client, suite="order-agent", case={"ticket": ticket}) as ep:
    first = client.messages.create(..., tools=tools, suite="order-agent-step")
    result = run_the_tool(first)
    second = client.messages.create(..., tools=tools, suite="order-agent-step")
    ep.output(second.content[0].text)
```

An episode is one recording for the whole turn, with the calls made inside it
attached to it.

- **`case=` is required**: the input that started the turn, a mapping of
  names to JSON values, as the case will hold it. Two turns with the same
  `case` are the same case at the import. The case, as JSON text, is also the
  episode's input, the question the judge reads beside the turn's answer;
  never the messages of one of its calls, which may be a step on the way or
  carry a tool's result.
- **`ep.output(...)`** is the turn's final answer. Without it, the episode's
  answer is the text of the last model call made inside it.
- Its trajectory is a list of steps, kept in its response as a single call's
  are: one `model` step per call, then a `tool` step per tool the model asked
  for. The recorder never sees what your tool returned, so a tool step says
  its result was `not_reported`. What makes the recording an episode is the
  `id` of its own, which the calls inside it carry.
- An exception inside the block propagates as it was raised, and the episode
  is still written with what was seen, marked `interrupted`.
- A call made in another thread or process does not inherit the episode. Pass
  `ep.id` there and wrap the call in `recorder.attach(...)`:

```python
def lookup(order, episode_id):
    with recorder.attach(episode_id):
        return client.messages.create(..., suite="lookup")


with recorder.episode(client, suite="order-agent", case={"ticket": ticket}) as ep:
    pool.submit(lookup, "A1", ep.id).result()
```

**A call that ends after its episode closed** is not one of its steps: the
episode is already written. Whether it is a stream read to its end too late,
or a call made in a task attached to the episode that ran on, it is recorded
with the episode's id, marked an orphan, and noted `ended after its
episode`. An id from another process is not late: the episode was never open
in this one, and its calls carry the id for the import to join.

A call made with no episode while one is open in the process is recorded as
an **orphan**: the recorder cannot tell a child that was not attached from a
call that belongs to no episode, and it attaches neither.

## Steps, live

A run reads an agent's trajectory as steps, in the target's response:
`metadata["response"]["steps"]`, beside `tools`, `tool_calls` and `finish`.
A step is a mapping with `index`, from 0, and `actor`: a `model` step is one
call to a model, with the `finish` its reply reported; a `tool` step is one
tool call the model asked for, with the call's keys as `tool_calls` holds
them (`status`, `result` and `result_absence` are left out below).

```python
[
    {"index": 0, "actor": "model", "finish": "tool_use"},
    {"index": 1, "actor": "tool", "tool": "lookup_order", "arguments": {"order": 42}},
    {"index": 2, "actor": "model", "finish": "stop"},
]
```

**When there are steps:**

- **A provider target** writes the steps of its one call: one `model` step
  and its `tool` steps.
- **A target that calls a model through a client `wrap()` returned** has the
  steps of every call it made inside the case, in the order their replies
  were read. `digline run` and the MCP server open the collection around each
  call of the target, recorder on or off, and close it before the assertions
  run, so a judge's calls are never the agent's. Off, nothing is written to
  disk.
- **A target that does not wrap its client** has what it reports: a function
  that returns its last call's response reports that call alone, and one that
  returns text reports no steps.
- **Absent is not empty.** There are no steps where a call reported nothing
  about tools, or where a call inside the case could not be read: a stream
  the target returned before its end, or a call made with positional
  arguments. A check that needs steps then errors, and never fails on what
  was not seen.

**What a wrapped target's response then carries.** `usage` is summed over its
calls, and `latency_ms` is summed too: **the time spent waiting for the
model, excluding the time your tools took.** It is not the duration of the
case, so a `LatencyBudget` on a target that wraps its client measures the
model's time. `metadata["response"]["collected"]` says how many calls were
made and what the latency is. A cost is computed only where the target has a
price list, a provider target's, each call at the model it reports; a function
target's calls have no cost, and the run says why.

**Limits.** The collection does not cross a `threading.Thread` or a
`ThreadPoolExecutor` worker, and `recorder.attach(...)` does not carry it.
`pytest-digline` calls `execute()` itself and does not open it yet. A program
that calls `execute()` itself passes
`around_target=digline.recorder.collecting` to have it.

Four checks read the steps: `Subsequence`, `Before`, `Never` and `MaxSteps`
([the API](api.md#four-checks-on-the-steps)).

**And in the run document.** A suite that records its responses keeps the steps
on each recorded response, from schema 23, so a replay judges them again as the
live run judged them. A response whose steps name other calls than its
`tool_calls` is refused rather than recorded.

The decision is
[ADR 0060](adr/0060-the-steps-of-a-trajectory-live-recorded-and-collected.md)
§1–§4.

## Switching it on

Off is the default, and off costs one comparison and one read of a context
variable per call.

**In development**, either:

```console
$ DIGLINE_RECORD=1 python app.py
$ digline record on --tenant acme
```

The variable records with the defaults. `digline record on` writes
`.digline/<tenant>/recorder.toml`, which wins over the variable wherever it
exists, and prints every value the file now holds. A value written before
stays until it is changed: `record on` with no option switches on and keeps
the rest, and `record off` switches off and keeps the rest. Like every
command that writes under `.digline/`, it lays out the tenant's whole
directory first, `baselines/` and `runs/` beside the switch, so a tenant that
only records has them too, empty.

| Key | | Development default |
|---|---|---|
| `on` | `true` or `false` | required |
| `sample` | the share of calls recorded, above 0 and at most 1 | 1 |
| `redact` | `"none"`, the one implemented | `"none"` |
| `ceiling` | the bytes the tenant's recordings may reach, as written | 100 MiB |
| `interval` | seconds between two looks at the file | 5 |
| `production` | the file is held to the production rules | `false` |

Any other key is refused by name. The file is looked at again at the interval,
so a change takes effect without a restart. An episode is sampled once: its
calls are in or out with it. At the ceiling the recorder stops recording for
that tenant and says so in the status; it never rotates or deletes.

**In production** (`tenant=` is a function), a file that switches a tenant on
must declare `redact`, `sample` and `ceiling`, and the tenant's directory must
be writable. Otherwise the client is refused when it is wrapped, and the
refusal names each missing declaration. `DIGLINE_RECORD=1` is refused there:
it declares neither redaction nor sampling.

```console
$ digline record on --tenant acme --production --sample 0.1 --redact none --ceiling 500000000
```

**In development a switch file that is invalid does not stop the
application.** The recorder says why on standard error, once, and records
nothing for that tenant until the file is right.

The switch file and the recordings are ignored by git, in the `.gitignore`
digline writes under `.digline/`.

## What was recorded, and what was not

```console
$ digline record status
$ digline record status --tenant acme --suite eval/suite.py --json
```

For each tenant: whether it records and with which values, where, and the
size against the ceiling. **The size is the bytes of the recordings as
written**, and it is the measure the ceiling is held against; the disk holds
more, a block per file at the least. Per suite: the single calls (with how
many were made inside an episode), the orphans, the episodes (with how many
were interrupted), and **what was not recorded, by reason**: `not JSON` for a
request a recording cannot hold, `sampled out`, `ceiling`, `stream
abandoned`, `config invalid` and the rest, and what was **recorded with
something noted**: `usage not reported`, `ended after its episode`. A suite
says only what it holds: a suite of episodes whose calls name another suite
shows no calls.

**Each process writes one subdirectory per tenant**,
`recordings/p<pid>-<8 hex>/`, however many clients it wraps, and keeps its
counts there beside its recordings, so the status reads them from any
process. With
`--suite`, it also says how many recordings the suite gained since its last
import. In the application, `client.digline_counts` gives the counts of that
client, in that process.

## From recordings to cases: `digline record import`

The suite declares where its captured cases go, under which regime and for
which judged check, and loads that file beside its own cases. In a `suite.py`:

```python
from pathlib import Path

from digline.host import read_cases
from digline.run import CaptureSource, Case, Suite

HERE = Path(__file__).parent

suite = Suite(
    tenant="acme",
    environment="dev",
    name="category",
    assertions=[...],
    cases=[*my_cases, *read_cases(HERE / "captured.json")],
    samples=2,
    min_agreement="2/2",
    capture=CaptureSource(
        cases_file="captured.json", repository="private", check="llm_rubric"
    ),
)
```

In a `suite.toml`, the same declaration is a `[capture]` table, and the file is
one of `cases`:

```toml
[suite]
cases = ["cases.json", "captured.json"]

[capture]
cases_file = "captured.json"
repository = "private"
check = "llm_rubric"
```

`repository` has no default, in either form. `"private"` says the file is
readable only inside the perimeter of whoever owns the text, and the input and
the answer are written whole. `"public"` says it is not: the import lists and
refuses to write, because a recorded answer is that text. `check` is the
judged assertion the cases are reviewed for, and the suite refuses a name that
is not one of its judged assertions when it is loaded. A suite that declares a
source and does not load its file is refused when it is loaded, naming the
cases it left out.

Then two invocations:

```console
$ digline record import --tenant acme --suite eval/suite.py
$ digline record import --tenant acme --suite eval/suite.py --good cap-…-9f8e7d6c --bad cap-…-4c3b2a1d --by "Ada Lovelace"
```

Both print the declaration whole, tenant, suite, `cases_file`, `repository`
and `check`: the first at its head, the second before the line of each case it
writes, so a declaration copied from another suite is in front of you every
time.

**The first lists and writes nothing.** What you name is an answer: an input
and one answer recorded for it. Its id is the input's (`cap-` and sixteen
characters) and the first eight characters of the answer's digest, so two
answers to one question are two ids. The answers are grouped by the shape of
their output: a single call by its kind (`text`, `structured`,
`conversation`), an episode by the actors of its steps in order and the last
finish they carry. Each group says how many answers and recordings it holds;
groups come in the order of their first answer, and answers in the files'
order. For each answer: its id, its first date, the setups it was recorded
under, how many times it came back, its input and its text, and whether it can
be written. Nothing is ranked, nothing is proposed, and there is no way to
write them all.

An answer recorded only under an earlier setup is shown and cannot be written:
a yes about an answer the setup in force did not give says nothing about it.
Nor can one recorded without its input, which the judge reads, or a
conversation, which a cases file cannot hold as an answer yet. Orphans,
interrupted episodes and recordings over the ceiling are counted, and are never
cases.

**The second writes the answers named, and no other.** Each one becomes a
[reviewed answer](api.md#casereviewed_answer-a-persons-yes-or-no-about-an-answer)
for the source's check: the recorded answer, its input, and your yes or no,
`--good` or `--bad`. `--by NAME` is mandatory, and the cases carry it as
`reviewed_by`: it is your mark, so it is never read from git or from the
environment. The suite must sample at least twice, as a reviewed answer needs.
No `expected` is written, with one exception: where the suite declares
`deterministic_output = true`, a `--good` also writes an ordinary case with the
input and the answer as its `expected`, with the same mark. A `--bad` never
does, since *not this answer* names no answer.

The import writes the file and stops: the diff is the review, the commit is the
signature.

A reviewed answer runs with the suite: the target is not asked for it, the
check it names judges the answer you read, and a judge that says the other of
what you said fails the case, so `digline report` and `digline compare` exit
`1`, and the report names the case and which way the judge went. How it sits
beside the other ways of reading a judge, calibration cases, the labelled
aggregates and `Repeated`, is [Calibrating a judge](calibration.md).

Recordings of another tenant than the suite's are refused before anything is
shown: bringing one tenant's material into another's suite is the bridge,
which is planned and not built, and until then the recordings stay in the
perimeter [ADR 0034](adr/0034-the-store-outside-and-the-reference-that-names-nothing.md)
§1 keeps them in.

## Comparing setups: `digline record compare`

What the application answered, case by case, under each setup it ran with:

```console
$ digline record compare --tenant acme --suite eval/suite.py
$ digline record compare --tenant acme --suite eval/suite.py --setup 1a2b3c4d 5e6f7a8b --show-setup
```

A case is the recordings with the same input, under the id the import gives
it. Under each setup, in the order of its first answer, come the answers in the
order they were recorded, each with its date and the first eight characters of
its digest. An answer recorded several times in a row under the same setup is
one line with how many times, and the date it ran to. Nothing is hidden: the
same answer recorded again after a different one is a line of its own.
Orphans, interrupted episodes and recordings over the ceiling are counted, as
the import counts them.

It shows, and judges nothing. No answer is ranked, and no word calls one better
or worse: whether a setup answered as it should is for the person reading. It
writes nothing, and does not move the import's `examined_through`.

- `--case ID` keeps one case.
- `--since WHEN` keeps the recordings made at or after an instant, written as
  `recorded_at` is, with its offset (`2026-11-03T08:00:00+00:00`). A recording
  with no `recorded_at` is then left out, and counted.
- `--setup A B` keeps two setups, by the eight characters the listing prints,
  and shows each case's answers under one beside its answers under the other.
- `--show-setup`, only with `--setup`, adds the keys the two setups differ
  on. Each value is shown by its first line, up to 60 characters, and its
  length, so a prompt is never printed whole.
- `--json` is the same structure for a program. It carries digests, never the
  recorded text (fixed decision 9): the cases by their ids, the setups and
  the answers by their digests, the dates, the counts, and for `--show-setup`
  the keys that differ, never their values. The words are in the terminal's
  text, for the person who ran the command.

Recordings of another tenant than the suite's are refused before anything is
shown, as the import refuses them. A suite with nothing recorded says so, and
exits 0.

## The page

`digline view --suite eval/suite.py` shows the same three things in a browser,
beside its screens over the runs: the recordings as `record import` lists
them, the answers across setups as `record compare` shows them, with a chart
for one case, and the recorder as `record status` says it. Each page calls the
function its command calls, and says what the command says.

Without a flag the page reads and writes nothing. Started with
`digline view --allow-record`, it switches the recorder on and off and writes
the answers a person names as cases, through the functions these commands
call, with the person's own name typed in the form. Under each button is the
command that does the same thing. See [`--allow-record`](view.md#-allow-record).

## Not yet

- An application in another language than Python.
