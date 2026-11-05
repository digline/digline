# digline for Node

A Node application's calls to a model, recorded by digline: the answers it
gives become cases a person names, as [`digline record`](record.md) does for
an application in Python. In Node the door is **`digline record proxy`**, a
process on the application's own machine that its SDK points at. Nothing is
installed in the application.

> **Arrives with digline 1.1.** On 1.0.3, `digline record proxy` does not
> exist.

## The proxy

On the machine that runs the application, in the directory that holds its
`.digline/`:

```console
$ digline record on --tenant acme
$ digline record proxy --tenant acme
```

What it prints, the routes and the addresses, and what it does and does not
do, are in [*Through the proxy*](record.md#through-the-proxy-digline-record-proxy).

## Three lines

Each line below is a line of `recorders/node/through-the-proxy.mjs`, which
the CI job `through-the-proxy` runs on every pull request: `openai` 7.50.0
and `@anthropic-ai/sdk` 1.4.0, a single call and a stream from each, through
the proxy to a fake provider. A test holds every line quoted here to that
file. What the job measures is that the proxy records Node's calls with the
same case and the same setup digest as the same request sent from Python,
and, for OpenAI's, from LangChain4j in Java.

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

- **An interceptor in the application**, around `fetch`, is not in 1.1: it
  comes after, with its own job (ADR 0062 §4). Until then a Node application
  is recorded through the proxy only.
- **Bedrock from Node**, through the AWS SDK for JavaScript, is not
  measured: the proxy records Bedrock, and the job sends it no call from Node.
- **A framework over the SDKs**, LangChain.js or the Vercel AI SDK, is not
  measured. One that takes a base URL and headers for the provider's SDK
  should be read the same way, and that is a sentence nobody has run.
- **Another version of either SDK** is what Dependabot proposes, and the job
  says on that pull request whether the proxy still records what it sends.
