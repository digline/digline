# digline for Node

A Node application's calls to a model, recorded by digline: the answers it
gives become cases a person names, as [`digline record`](record.md) does for
an application in Python. In Node the door is **a directory of five files
copied into the application**, which hooks the client the application already
builds. Where the application's code is not to be touched,
**`digline record proxy`** is the second door: a process on the application's
own machine that its SDK points at.

> **Arrives with the next digline-openai, digline-anthropic and digline-bedrock**, for `digline record
> proxy` alone. digline 1.1.1 is on PyPI with `digline record`, and the
> files below are in this repository; the proxy reads a provider's wire
> through that provider's plugin, and no release of the three on PyPI
> has that reading yet.

Either way the files written are the same, and so is everything downstream:
`digline record import`, `compare`, the page, a run. What a file holds is
[the recording document](recording-format.md). The commands, `digline record
on`, `status` and `import`, are digline's command line, which is Python:
[*Install the digline CLI*](record-java.md#install-the-digline-cli) says how
to install it apart from a project that is not Python.

## In the process: the files to copy

Copy `recorders/node/digline/` from digline's repository into your project,
as a directory named `digline`. Its five files need Node 22 or later and no
package: `recorder.mjs`, the writer, `messages.mjs`, which reads Anthropic's
Messages for the two hooks that meet it, `eventstream.mjs`, which reads the
event stream Bedrock's streams reply in, and the two hooks:

| Your client | The hook | How it is installed |
|---|---|---|
| `openai` | `diglineFetch(recorder)`, in `fetch.mjs` | the client's `fetch` option |
| `@anthropic-ai/sdk` | `diglineFetch(recorder)`, in `fetch.mjs` | the client's `fetch` option |
| `@aws-sdk/client-bedrock-runtime` | `diglineAws(recorder)`, in `aws.mjs` | `middlewareStack.use(...)` on the client |

Every line of JavaScript in this part is a line of
`recorders/node/page.test.mjs`, which the CI job `recorder-node` runs on every
pull request against a fake provider on `127.0.0.1`, with openai 7.50.0,
@anthropic-ai/sdk 1.4.0 and @aws-sdk/client-bedrock-runtime 3.1163.0. A test
holds every block here to that file. The job also holds the writer to the
fixtures digline's own Python makes, the ones Java's recorder is held to, and
imports what it wrote with digline alone. The CI job `through-the-proxy` sends
the request it sends from every language through `diglineFetch` too, and holds
that it gives the same case and setup digest as through the proxy. It sends
Bedrock's two streams from Node through `diglineAws` and through the proxy,
each answered with the same bytes, and holds that both write the same
recording.

```js
import OpenAI from "openai";
import Anthropic from "@anthropic-ai/sdk";
import { BedrockRuntimeClient, ConverseCommand } from "@aws-sdk/client-bedrock-runtime";
import { DiglineRecorder, attach, suite } from "./digline/recorder.mjs";
import { diglineFetch } from "./digline/fetch.mjs";
import { diglineAws } from "./digline/aws.mjs";
```

The recorder is made once, for the application, with the directory that holds
`.digline/`, the tenant and the application's name, and each client takes the
hook:

```js
const recorder = DiglineRecorder.development(root, "acme", "support");

const openai = new OpenAI({ fetch: diglineFetch(recorder) });
const anthropic = new Anthropic({ fetch: diglineFetch(recorder) });
const bedrock = new BedrockRuntimeClient({});
bedrock.middlewareStack.use(diglineAws(recorder));
```

**The hook is the `fetch` the client is given, not the global one.** A client
built before the global `fetch` was replaced keeps the one it read when it was
built: measured with openai's client on 2026-11-06 (ADR 0062 §4, as amended
that day), and @anthropic-ai/sdk's code reads it the same way, at
construction. So a client that should be recorded is given the option.

A call names its suite, the same name as that suite's `Suite(name=...)`, for
what the function given to `suite` runs and awaits:

```js
await suite("refunds", () => openai.chat.completions.create(params));
```

A call that names none is recorded under `_unassigned`, with the file, relative
to the root, and the function it was made from. **A function that returns the
SDK's promise without `await` is not on the stack when the call is made**, so
the call carries the function that awaited it instead: `return await` names
the function itself.

It records nothing until the tenant's switch says so, the file
[`digline record on`](record.md#switching-it-on) writes, which the writer reads
with digline's own rules and reads again at its interval. Without the file the
recorder is off, and so it is where the root holds no `.digline/`. In
development `DIGLINE_RECORD=1` switches it on where no file exists.

### A turn of an agent

An episode keeps one turn as one recording, with the calls made inside it as
its steps, written when the turn's function ends. A turn that throws is
recorded *interrupted*, and the error goes on to the caller:

```js
await recorder.episode("order-agent", { ticket }, async (episode) => {
  episode.output(await agent.answer(ticket));
});
```

The episode names its own suite, and not its calls': each call names one, or
is recorded under `_unassigned`. A call made by work the turn's function does
not run itself is put in the episode by its id, which is `null` while the
recorder is off:

```js
await attach(id, () => lookup(order));
```

### In production

`production` takes a function asked at every call, and each tenant's
recordings are filed under its own directory. It refuses to start, with a
`StartError`, where a tenant's file is invalid, or switches recording on
without `redact`, `sample` and `ceiling`, as `digline record on --production`
writes them. It also refuses where `DIGLINE_RECORD=1` is set:

```js
const recorder = DiglineRecorder.production(root, () => tenantOf(request), "support");
```

### What the hooks read

- **`diglineFetch`** reads Chat Completions and Messages, single and
  streamed, by the request's path. Any other request goes through untouched
  and is not counted.
- **`diglineAws`** reads Converse and `converseStream`, and InvokeModel and
  `invokeModelWithResponseStream` with an Anthropic model, whose body is
  Anthropic's Messages, read as a direct call to Anthropic is. InvokeModel
  with another family, Titan, Llama or Mistral, streamed or not, is not
  recorded,
  and neither is an embedding model: each call is counted in
  `recorder.counts()` with its reason, *model family not recorded* or
  *embeddings not recorded*, and standard error says it once a family. The
  family is read from the model id, a cross-region prefix (`us.`, `eu.`,
  `apac.`, `global.`) taken off first.
- **A reply is read only where its status is 2xx.** A retry the SDK makes
  after an error is one call, recorded once. The hook sees each attempt, so
  each one the provider refuses, 4xx or 5xx, is counted `provider error
  <status>`: a call retried after a 500 and then answered is
  `provider error 500` beside one recording. The Python wrapper sees the
  whole call, after the SDK's retries, and counts only the refusal it raises.
- **A stream is recorded when the application has read it to its end.** One it
  stops reading before is counted *stream abandoned*. OpenAI's SDK stops at
  `[DONE]`, and Anthropic's at `message_stop`: either counts as the end, and
  so do Bedrock's `metadata` and, in InvokeModel's chunks, `message_stop`.
  Bedrock's SDK stops reading a stream when its call is aborted, with
  `abortSignal`. A `break` out of the loop alone was measured to leave the
  connection open, and the call is not settled while it is.
- **A Bedrock stream whose bytes do not check**, a checksum that does not
  match, or that carries an exception after its 200, is not recorded and is
  counted *stream error*, as the proxy counts it. What the application meets
  is what the SDK throws, as it would without the hook.

## Through the proxy

On the machine that runs the application, in the directory that holds its
`.digline/`:

```console
$ digline record on --tenant acme
$ digline record proxy --tenant acme
```

What it prints, the routes and the addresses, and what it does and does not
do, are in [*Through the proxy*](record.md#through-the-proxy-digline-record-proxy).

**The proxy's machine needs digline and its plugins; the application needs
neither.** The proxy reads each provider's calls with that provider's plugin,
`pip install digline digline-openai digline-anthropic`, and a route whose
plugin is not installed is refused, naming the package. Nothing is installed in
the Node application: it keeps its own SDKs and points them at the proxy.

### Three lines

Each line below is a line of `recorders/node/through-the-proxy.mjs`, which
the CI job `through-the-proxy` runs on every pull request, with the versions
above: a single call and a stream from each, through the proxy to a fake
provider. A test holds every line quoted here to that file. What the job
measures is that the proxy records Node's calls with the same case and the
same setup digest as the same request sent from Python, and, for OpenAI's,
from LangChain4j in Java.

**1. The base URL.** Either the SDK's own variable, with no change to the
code, which the job sets for Anthropic's client:

```console
$ ANTHROPIC_BASE_URL=http://127.0.0.1:8787 node app.mjs
```

or the client's option, `baseURL`, which the job gives OpenAI's:

```js
  baseURL: `${proxy}/v1`,
```

OpenAI's ends in `/v1`, and so does its variable, `OPENAI_BASE_URL`, which
the start of the proxy prints; Anthropic's is the address alone, and the SDK
adds `/v1/messages` itself. `OPENAI_BASE_URL` is read by the SDK, as ADR
0062's table measured on 2026-11-04, and the job does not run it. The key
stays the application's own, in its own headers, and the proxy never reads,
logs or writes it.

**2. The suite**, a header on every call, through `defaultHeaders`:

```js
  defaultHeaders: { "X-Digline-Suite": "triage", "X-Digline-App": "node" },
```

`X-Digline-App` is optional, and names the app the call is filed under,
`proxy` otherwise. Neither header reaches the provider. A call that names no
suite is recorded under `_unassigned`, with the SDK's `User-Agent` and the
path where a call in Python names its function, and
`digline record import --from _unassigned` lists those calls as a suite's.

**3. The episode**, where a turn of an agent makes several calls: the same
`X-Digline-Episode` on each, as a request's own headers:

```js
const turn = { headers: { "X-Digline-Episode": "turn-node" } };
await openai.chat.completions.create(asked.openai, turn);
```

Any value the application chooses, one per turn. The proxy writes the turn
as an episode once no call has carried it for 30 seconds, or when it stops:
its answer is the last call's text, its case the first call's messages or the
JSON object `X-Digline-Case` gives, and each tool step is closed by the
result the next call sends back to the model.

Then the recordings are where every recording is, and
[`digline record import`](record.md#from-recordings-to-cases-digline-record-import)
lists them.

## What stays out

- **HTTP/2 to AWS.** The Bedrock client speaks HTTP/2 by default, and the
  page's lines were run that way, and so was a `converseStream` in the hooks'
  tests, but against the fake provider on `127.0.0.1`, not against AWS. The hook sits above the transport and reads
  the bytes the SDK reads.
- **Bedrock's single calls through the proxy from Node** are not measured:
  the job sends the proxy Node's two streams, not Converse or InvokeModel.
- **The counts.** The writer keeps no counts file, which is not part of the
  contract. `digline record status` says *not counted* for its process, and
  `recorder.counts()` gives the same counts in memory.
- **A worker thread** is not measured: what `suite`, `episode` and `attach`
  hold is held by `AsyncLocalStorage`, and whether it reaches a call made in a
  `Worker` was not tried.
- **A framework over the SDKs**, LangChain.js or the Vercel AI SDK, is not
  measured. One that hands the provider's SDK a `fetch`, or a base URL and
  headers for the proxy, should be read the same way, and that is a sentence
  nobody has run.
- **Another version of any of the three SDKs** is what Dependabot proposes, and
  the jobs say on that pull request whether the hooks and the proxy still
  record what it sends.
