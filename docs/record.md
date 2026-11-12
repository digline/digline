# `digline record` — the calls and agent turns your application makes, kept as cases

While an application is being built, the calls it makes to a model are the
material a suite is made of. The recorder keeps them, at the place where the
application makes them, in the shape a suite reads: what the call was asked,
what decided how it answered, and what it answered. A turn of an agent, the
calls it makes on the way to one answer, is kept as one recording, an
episode with its steps. A person then reads them back and names the ones that
become cases.

If you don't know what to do next, open `digline view`, with no suite yet:
its first page, [*Where you are*](view.md#where-you-are), reads `.digline/`
and says the next step, with its command. Before anything is recorded it
needs the tenant, `digline view --tenant acme`.

It is five things:

- **`digline.recorder.wrap`**, around the provider's own client, in the
  application;
- **`digline record proxy`**, for an application in any language, which
  points its SDK at it;
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
What a recording file holds, for a program in another language that writes
one, is [the recording document](recording-format.md), and an application in
Java has [a page of its own](record-java.md).

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
  made from, and enters no suite until a person gives it one. There are two
  ways to give it one: name the suite at that call site, `suite=...`, the
  function the listing below prints as `made at:`; or import from it,
  `digline record import --tenant T --suite S --from _unassigned`, which lists
  the calls that named no suite as suite `S`'s, under `S`'s capture
  declaration, and writes the ones you name into `S`'s cases file. The
  recordings stay where they are, and the next listing shows what you said
  of each.
- **`digline_vars=`**, on the call, adds the variables a template was filled
  with to the case, beside the messages, where the user message mixes a
  template and the data.

A recording of a call keeps it in three compartments: the **case**, the
messages (less the leading instructions, for OpenAI) and the `digline_vars`;
the **setup**, everything else the call decided; and the **response**, the
answer with its measurements, and its steps unless the call reported nothing
about tools ([below](#steps-live)). The response also carries its **input**, the case's messages as JSON
text: the question the import puts beside the answer for the judge, whether
the call was made, streamed or awaited. An agent's turn is one recording of
its own, with the `case` it was given
([an episode](#a-turn-of-an-agent-episode)).

`suite=` and `digline_vars=` are taken out of the call before it reaches the
provider's SDK, whether the recorder is on or off. The client returned is the
client: everything but the call is its own.

The clients recorded are the ones a plugin maps, one method at a time:

| Plugin | Client | Methods |
|---|---|---|
| `digline-anthropic` | `anthropic.Anthropic`, `anthropic.AsyncAnthropic` | `messages.create`, `messages.stream` |
| `digline-openai` | `openai.OpenAI`, `openai.AsyncOpenAI` | `chat.completions.create`, `chat.completions.stream` |
| `digline-bedrock` | a `bedrock-runtime` client | `converse`, `converse_stream`, `invoke_model`, `invoke_model_with_response_stream` |

**Bedrock's `invoke_model` is recorded for an Anthropic model**, whose body is
Anthropic's Messages, read with the map `digline-anthropic` reads a direct call
with: `digline-bedrock` depends on it. Another family, Titan, Llama or Mistral,
is not recorded, nor is an embedding model: the call is counted with its
reason, *model family not recorded* or *embeddings not recorded*, which `digline
record status` shows, and standard error says it once a family, as `digline
recorder: invoke_model on amazon.titan-text-express-v1: this model family is
not recorded`. The family is read from the model id, a cross-region prefix
(`us.`, `eu.`, `apac.`, `global.`) taken off first. The proxy reads the same
calls, `/model/<id>/invoke` and `/model/<id>/invoke-with-response-stream`, by
the same rule.

Any other client is refused when it is wrapped, by name. Bedrock has no
asynchronous client in botocore; aiobotocore's is a package of its own that no
plugin maps, so it is refused like any other.

**The application's call never fails because of the recorder.** Whatever goes
wrong while recording, the call returns what the provider returned, and the
reason it was not recorded is counted (below). An exception of the SDK itself
propagates as it always did.

## The variables of a prompt

**The system prompt is part of the setup**, not of the case: Anthropic's
`system`, Bedrock's `system`, and on OpenAI the leading `system` and
`developer` messages. The Java files read a call the same way. So a value the
application fills into the system prompt, a customer's name, today's date, a
document it retrieved, makes **a different setup for each value**. Measured on
2026-11-12, at `2aaae91d`, with the three plugins' maps: two calls that differ
only by a name in the system prompt give one case and two setups, and the same
two calls with the name in the first user message give one setup and two
cases.

That decides what can be imported. The setup in force is the newest, and an
answer recorded under another one is shown and
[cannot be written](#from-recordings-to-cases-digline-record-import). With a
variable in the system prompt, only the answers given under its newest value
can be written, and every other one is listed as recorded under an earlier
setup.

**Put what changes per request in the first message**, and keep the system
prompt the same for every call; in Python, `digline_vars=` adds the values to
the case as well. Then the setup changes when the application does, a new
prompt or a new model, which is what
[`digline record compare`](#comparing-setups-digline-record-compare) shows.

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
- **A call the provider refuses**, with a 4xx or a 5xx, raises the SDK's
  exception as it was raised and records nothing: there is no reply. It is
  counted `provider error <status>`, `provider error 403` for a key the
  provider does not accept, where the exception carries the status.
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
  run, so a judge's calls are never the agent's. **On or off, nothing of a
  run is recorded**: the target's calls and a judge's are the gate's, not
  your application's traffic, so they write no recording and move no count,
  and an `episode()` opened inside one is an empty context. A program that
  calls `execute()` itself enters `digline.recorder.running()` around it for
  the same.
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
([the API](api.md#four-checks-on-the-steps)). They go in the suite's
assertions beside the checks on the output, and every case of the suite is
asked them: no form narrows one to some cases or to a group.

**And in the run document.** A suite that records its responses keeps the steps
on each recorded response, from schema 23, so a replay judges them again as the
live run judged them. A response whose steps name other calls than its
`tool_calls` is refused rather than recorded.

The decision is
[ADR 0060](adr/0060-the-steps-of-a-trajectory-live-recorded-and-collected.md)
§1–§4.

## Through the proxy: `digline record proxy`

An application that is not in Python, or that cannot wrap its client, points
its SDK at a proxy on its own machine ([digline for Node](record-node.md) has
the lines for Node), and the proxy records each call as the
recorder in process does: the same switch, the same files, the same digest
and the same counts. It listens on `127.0.0.1` and nowhere else.

In `/home/you/app`, with `DIGLINE_RECORD=1`:

```console
$ digline record proxy --tenant acme
digline record proxy: listening on http://127.0.0.1:8787
  tenant:     acme, app proxy
  writes to:  /home/you/app/.digline/acme/recordings
  recording:  on, from DIGLINE_RECORD=1: sample 1, ceiling 104857600 bytes, interval 5 s
  route anthropic: https://api.anthropic.com
  route bedrock: https://bedrock-runtime.eu-central-1.amazonaws.com
  route openai: https://api.openai.com/v1
  point the SDK here:
    ANTHROPIC_BASE_URL=http://127.0.0.1:8787
    AWS_ENDPOINT_URL_BEDROCK_RUNTIME=http://127.0.0.1:8787
    OPENAI_BASE_URL=http://127.0.0.1:8787/v1
```

In any language, three things:

1. **The base URL**: the SDK's own variable, as the last lines say, or its
   base URL option. The key stays the application's own, and travels in its
   own headers: the proxy never reads, logs or writes it. Bedrock's is the
   exception, below.
2. **The suite**: a header, `X-Digline-Suite: refunds`, or, where the SDK can
   set a base URL and no header, a path, `http://127.0.0.1:8787/suite/refunds/v1`.
   Neither reaches the provider. A call that names no suite is recorded under
   `_unassigned`, with the SDK's `User-Agent` and the path as its call site.
   `digline record import --from _unassigned` lists those calls as a suite's,
   and shows that call site on its `made at:` line, where a call in process
   names its function.
3. **The episode**, where a turn makes several calls: the same
   `X-Digline-Episode` value on each, any value the application chooses. Once
   no call has carried it for 30 seconds (`--episode-idle`), or when the proxy
   stops, the turn is written as an episode: its answer is the last call's
   text, and its case is what `X-Digline-Case` gave, a JSON object or a text.
   Without it the case is the first call's, and the import says *case from
   the first call*. An episode off the wire is never *interrupted*: an
   exception in the application does not cross the wire.

`X-Digline-App` names the app a call is filed under, `proxy` unless `--app`
says otherwise.

**Which provider.** The path says which plugin reads a call:
`/chat/completions` is OpenAI's, `/v1/messages` Anthropic's,
`/model/<id>/converse`, `/model/<id>/converse-stream`, `/model/<id>/invoke`
and `/model/<id>/invoke-with-response-stream` Bedrock's. Such a
call goes to that provider, whatever its headers say, or to
`--upstream ROUTE=URL` for that route, for a gateway or a compatible
endpoint, once per route:

```console
$ digline record proxy --tenant acme --upstream openai=https://generativelanguage.googleapis.com/v1beta/openai
```

A call over a path no plugin reads goes to the provider whose SDK its
headers show, `anthropic-version` Anthropic's, an AWS signature Bedrock's, a
bearer key without them OpenAI's, and is forwarded and not recorded. The path
comes first because the headers can mislead: boto3 sends a Bedrock API key as
a bearer, as OpenAI's SDK sends its key. An endpoint that answers in OpenAI's
shape, such as Gemini's OpenAI-compatible one, is read by OpenAI's plugin.
That was measured with a fake endpoint at another path whose replies have
fewer fields than OpenAI's; Gemini itself was not called, so what it sends was
not read. A provider whose plugin is not installed is refused, and the
refusal names the package.

**Bedrock** needs `digline-bedrock`. An AWS SDK signs its request for the
address it sends it to, which is the proxy's, so the proxy signs it again,
with SigV4 and the credentials and region boto3 finds on the proxy's machine:
the environment first, then the profile in `~/.aws/config` and
`~/.aws/credentials`. **First it checks that the application signed the
call with those same credentials**, as AWS checks a signature: the access key
is the machine's, and the signature, computed again with its secret over the
path, the query, the headers the call says it signed and the body, is the
one the call carries, made within 15 minutes of the machine's clock. A call
that was not is a 403, *the request was not signed with this machine's AWS
credentials*, which says why, and goes nowhere: a process on the machine
without its keys spends nothing with them. So an application signs with the
same profile the proxy reads, and a Bedrock API key, which is not a
signature, is refused. The application's signature itself does not go on.
Credentials that may call Bedrock and nothing else are still worth giving
the proxy. Where it finds no region or no credentials, the start says so on
the route's line, and a call is a 502 that says the same.

The address: `AWS_ENDPOINT_URL_BEDROCK_RUNTIME`, which boto3 reads (measured
with boto3 1.43), or the SDK's endpoint option, `endpoint_url` in boto3,
`endpointOverride` in the AWS SDK for Java. Whether another AWS SDK reads the
variable was not measured. boto3 adds a header before it signs:

```python
client.meta.events.register(
    "before-sign.bedrock-runtime.*",
    lambda request, **_: request.headers.update({"X-Digline-Episode": turn_id}),
)
```

The streamed reply is an AWS event stream, passed on as it arrives and read
at its end. One that carries an error after it began, as a throttled call's
does, is counted `stream error` and not recorded. **Measured against a fake Bedrock only**: boto3 against a fake
upstream that checks nothing but the shape, with the real SigV4 code signing.
One real `converse` was made through the proxy, to Haiku 4.5 in
`eu-central-1`, and Bedrock refused the key it was signed with as
unrecognised. So no call to Bedrock itself has been recorded yet.

**An agent's steps, off the wire.** In an episode, each call is a model step,
and each tool it asks for a tool step, as in process. What the wire adds is
the tool's result: the application's next call sends it back to the model, a
`tool` message on OpenAI, a `tool_result` block on Anthropic, a `toolResult`
block on Bedrock, and that closes the step before. Its status is the
provider's word, `error` or `success` where Anthropic's `is_error` or
Bedrock's `status` says one, and `not_reported` where it does not, always on
OpenAI. In process the same step says `not_reported`, because the call ends
where the tool starts; the places, the tools and the arguments are the same.
A result is put on a step only where the next call carries results for the
same tools, in the same order: never on one it may not answer.

**What passes on as it came.** The reply, its body and its headers, but those
a connection owns. A stream is passed on as it arrives and recorded at its
end; one the application closes first is counted `stream abandoned` and not
recorded, as in process. A reply that is not a 200 is passed on and not
recorded; a refusal, 4xx or 5xx, is counted `provider error <status>`, as in
process. An upstream that does not answer within 600 seconds is a 504 that
says so.

**What it does not see**: a call the application does not point at it, the
application's own code between two calls, and a tool the application runs
without sending its result back to the model: the last call's tool steps, and
any whose result never reaches the model, stay `not_reported`.

**Behind a corporate proxy, or a CA of the company's.** What follows was
measured on 2026-11-12, at `2aaae91d` with Python 3.14.5, against an upstream
on the same machine whose certificate a private CA had signed:

- **The proxy goes to the upstream directly.** It does not read `HTTPS_PROXY`,
  `HTTP_PROXY` or `NO_PROXY`: with `HTTPS_PROXY` naming a listener, the call
  reached the upstream and nothing connected to the listener. Where the network
  lets HTTPS out only through a company proxy, the provider cannot be reached,
  and each call is a 502, *the upstream cannot be reached*, with the reason.
  `--upstream ROUTE=URL` naming an endpoint the machine reaches directly, an
  internal gateway, is the way through.
- **It checks the upstream's certificate against Python's default store**, and
  `SSL_CERT_FILE` in its environment names another. Without it the call was a
  502 whose reason said `CERTIFICATE_VERIFY_FAILED`; with
  `SSL_CERT_FILE=/path/to/company-ca.pem` it was a 200 and the reply passed on.
- **To check a setup**, start the proxy with that environment and make one call
  of the application through it: a 200 is the route working, and a 502 names
  which of the two failed, the network or the certificate.

The judge's calls do not go through it. `digline-bedrock`'s judge builds its
boto3 client with the region alone and passes no proxy and no CA, so they
are boto3's own settings, which this page did not measure; a judge given
`client=`, a boto3 client built with them, uses that one.

The proxy is a Python process like any that wraps a client: `digline record
status` counts it, and Ctrl-C or SIGTERM stops it after writing its open
episodes and its counts. Through it, a call adds a fraction of a millisecond:
0.28 ms at the median of 100 single calls, measured against a fake provider
on the same machine.

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

**In production**, for an application that resolves its tenant per request
(`wrap(tenant=callable)` in Python, `DiglineRecorder.production` in Java and
Node; the proxy's `--tenant` is never production), a file that switches a
tenant on must declare `redact`, `sample` and `ceiling`, and the tenant's
directory must be writable. Otherwise the client is refused when it is
wrapped, and the refusal names each missing declaration. `DIGLINE_RECORD=1`
is refused there: it declares neither redaction nor sampling.

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
abandoned`, `stream error` for a stream that carried an error after it began
and `client gone` for a client that left before it had sent its whole request
(both through the proxy), `config invalid` and the rest, and what was **recorded with
something noted**: `usage not reported`, `ended after its episode`. A suite
says only what it holds: a suite of episodes whose calls name another suite
shows no calls. Apart from those, **from gate runs**: the calls a `digline
run` made, while it was in progress, to an application that records itself,
which no list, import or compare reads
([the recording's format](recording-format.md#a-run-in-progress-the-gates-calls)).

**Each process writes one subdirectory per tenant**, however many clients it
wraps: `recordings/p<pid>-…/` from Python, `recordings/j<pid>-…/` from Java,
`recordings/n<pid>-…/` from Node; the format leaves the name free. digline's recorder keeps its counts there
beside its recordings, so the status reads them from any process. With
`--suite`, it also says how many recordings the suite gained since its last
import. In the application, `client.digline_counts` gives the counts of that
client, in that process.

A process that wrote recordings and keeps no counts file, as a program in
another language does, is said as **not counted**: what it did not record is
not known, which is not the same as nothing.

## From recordings to cases: `digline record import`

**The first step is [`digline suggest`](suggest.md)**, which proposes the
suite these cases run in, its `[capture]` included, from the recordings
themselves, and marks nothing. Then the import below, which is yours.

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
**The setup in force is per form**, the newest among the episodes for an
episode and among the single calls for a single call, and each group says
its own under its heading, `setup in force for single calls: …`. An episode
recorded after them does not put the single calls under an earlier setup, so
an answer reads the same in the suite's listing and with
`--from _unassigned`.
Nor can one recorded without its input, which the judge reads, or a
conversation, which a cases file cannot hold as an answer yet. Orphans,
interrupted episodes and recordings over the ceiling are counted, and are never
cases.

**With `--json` the listing is for a program**, and holds no recorded word:
the declaration, the setup in force per form, and per group the shape, how
many answers and recordings, how many no person has named yet, how many are
already a yes or a no, and how many cannot be written, by why. No answer's id,
which carries its digest, no input and no text. It says where a yes or a no is
given, `review`: the page of [`digline view`](view.md) that lists the same
answers. `--json` is refused with `--good`, `--bad` and `--by`, because a yes
or a no is a person's, given by reading the answer, and the listing for a
program has none in it to read.

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
`1`, and the report names the case and which way the judge went. An answer
the import took from an episode carries the episode's steps, and the suite's
checks on the steps run on it too: on a yes a red one is a contradiction, on
a no they decide nothing. How it sits
beside the other ways of reading a judge, calibration cases, the labelled
aggregates and `Repeated`, is [Calibrating a judge](calibration.md).

A coding agent can propose the suite these cases run in, by digline's
method and from the same first proposal, and leave the yes and no to you:
[Letting an agent propose a suite](proposing-a-suite.md).

Recordings of another tenant than the suite's are refused before anything is
shown: bringing one tenant's material into another's suite is the bridge,
which is planned and not built, and until then the recordings stay in the
perimeter [ADR 0034](adr/0034-the-store-outside-and-the-reference-that-names-nothing.md)
§1 keeps them in.

## Comparing setups: `digline record compare`

What the application answered, case by case, under each setup it ran with.
Where a suite's target is the application over HTTP, a run's `config_hash`
does not see the application's prompt or model: compare setups through the
recordings, here; the run's identity is the suite's, not the app's.

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
the import counts them. An episode's setup is the set of its calls' setups and
the commit, so its digest alone says nothing of its shape: beside it come how
many model calls its episodes made and the models its calls named, as in
`setup 5e6f7a8b · model calls per episode: 2 · models: claude-haiku,
claude-sonnet`. A list, never a ranking.

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
  length, so a prompt is never printed whole. A list of messages, a `system`
  the way Chat Completions carries it, is shown by its first message's text
  and how many messages there are, never as JSON. An episode's
  `child_setups` are shown one per line, each child setup by its eight
  characters and the model it names.
- `--json` is the same structure for a program. It carries digests, never the
  recorded text (fixed decision 9): the cases by their ids, the setups and
  the answers by their digests, the dates, the counts, and for `--show-setup`
  the keys that differ, never their values. For an episode it also carries
  the shape of its steps under each setup: how many model calls its episodes
  made, and the models its child setups name, which are values of the
  configuration and travel as a run's do. The words are in the terminal's
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

- A call to Bedrock itself recorded through the proxy: the one made was
  refused for its key.
- An interceptor in the application's own language for .NET, Node and Go,
  which go through the proxy until then. Java has one: [digline for
  Java](record-java.md).
