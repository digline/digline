# A Node application on three SDKs, from its first call to a gate

This page records the calls a Node application makes through three
providers' SDKs, turns the recordings into a suite, and ends with a gate
on it.

## Who this is for

A Node application that calls its models through the providers' own SDKs:
`openai`, `@anthropic-ai/sdk`, and `@aws-sdk/client-bedrock-runtime` with an
Anthropic model. Here it is a support desk of one file, `app.mjs`, on
`node:http`, with no framework. Bedrock sorts a ticket in a turn that may ask
for a tool, Anthropic streams a summary, Bedrock streams an apology with
`converseStream`, and OpenAI writes a subject line.

Everything on this page was run, on 2026-11-07, with digline installed from
this repository at `37d5c1dd`, except the block of `digline record on`, run
again at `be52d283` (#953) once its last line named Node. It ran on Node
22.22.0, with openai 7.50.0, @anthropic-ai/sdk 1.4.0 and
@aws-sdk/client-bedrock-runtime 3.1163.0. **No call reached a provider or a
model.** A stand-in on 127.0.0.1,
`recorders/node/test/stand-in.mjs` in digline's repository, answered the
application and the judge, and every answer, score and token count below is
the stand-in's. Each SDK was pointed at it by the variable it
reads, `OPENAI_BASE_URL`, `ANTHROPIC_BASE_URL` and
`AWS_ENDPOINT_URL_BEDROCK_RUNTIME`; on your machine those are left out and
the providers answer. Paths are shortened to `…`.

## Day one: recording

**One directory.** Copy `recorders/node/digline/` into the project as
`digline/`: five files, no package
([which file, for which client](../record-node.md#in-the-process-the-files-to-copy)).

**One recorder, and a hook on each client**, where `app.mjs` builds them:

```js
const recorder = DiglineRecorder.development(root, "acme", "desk");

const openai = new OpenAI({ fetch: diglineFetch(recorder) });
const anthropic = new Anthropic({ fetch: diglineFetch(recorder) });
const bedrock = new BedrockRuntimeClient({});
bedrock.middlewareStack.use(diglineAws(recorder));
```

`root` is the directory `app.mjs` sits in,
`fileURLToPath(new URL(".", import.meta.url))`, which is the one that holds
`.digline/`. The two `fetch` hooks are each client's option, and the
Bedrock hook is a middleware on the client.

**The turn is an episode, and its calls name the suite.** The turn asks
Converse until the model stops asking for a tool:

```js
async function turn(ticket) {
  const messages = [{ role: "user", content: [{ text: ticket }] }];
  for (;;) {
    const reply = await suite("triage", () =>
      bedrock.send(new ConverseCommand({ modelId: MODEL, system: SYSTEM, messages, toolConfig: TOOLS })),
    );
    messages.push(reply.output.message);
    if (reply.stopReason !== "tool_use") {
      return reply.output.message.content.find((block) => block.text !== undefined).text;
    }
    const results = [];
    for (const { toolUse } of reply.output.message.content.filter((block) => block.toolUse)) {
      const found = await lookupOrder(toolUse.input);
      results.push({ toolResult: { toolUseId: toolUse.toolUseId, content: [{ json: found }] } });
    }
    messages.push({ role: "user", content: results });
  }
}
```

`TOOLS` declares two tools, `lookup_order` and `escalate`, and `SYSTEM` asks
for the category as JSON. The episode keeps the turn as one recording, with
its input and its answer:

```js
function triage(ticket) {
  return recorder.episode("triage", { ticket }, async (episode) => {
    const answer = await turn(ticket);
    episode.output(answer);
    return answer;
  });
}
```

**Two streams.** Anthropic's, server-sent events read with `for await`:

```js
async function summary(ticket, out) {
  await suite("summaries", async () => {
    const stream = await anthropic.messages.create({
      model: "claude-haiku-4-5",
      max_tokens: 256,
      messages: [{ role: "user", content: ticket }],
      stream: true,
    });
    for await (const event of stream) {
      if (event.type === "content_block_delta" && event.delta.type === "text_delta") {
        out.write(event.delta.text);
      }
    }
  });
}
```

and Bedrock's, `converseStream`, which replies in AWS's event stream:

```js
async function apology(ticket, out) {
  await suite("apologies", async () => {
    const reply = await bedrock.send(new ConverseStreamCommand({
      modelId: MODEL,
      messages: [{ role: "user", content: [{ text: ticket }] }],
    }));
    for await (const event of reply.stream) {
      if (event.contentBlockDelta) {
        out.write(event.contentBlockDelta.delta.text);
      }
    }
  });
}
```

Each is recorded once the application has read it to its end, with the text
it wrote out as the answer.

**A call that names no suite**, OpenAI's, through a helper that returns the
SDK's promise:

```js
function subjectOf(ticket) {
  return openai.chat.completions.create({
    model: "gpt-4o-mini",
    messages: [{ role: "system", content: "Write the subject line." }, { role: "user", content: ticket }],
  });
}

async function subject(ticket) {
  const completion = await subjectOf(ticket);
  return completion.choices[0].message.content;
}
```

**Switch it on, and run the application**, from the project's directory:

```console
$ digline record on --tenant acme
recording on for tenant 'acme': …/desk/.digline/acme/recorder.toml
  values: on true, sample 1.0 (default), redact none (default), ceiling 104857600 bytes (default), interval 5.0 s (default)
  development: what the file leaves out is a default; an application that resolves its tenant per request is production (wrap(tenant=callable) in Python, DiglineRecorder.production in Java and Node; the proxy's --tenant is never production), and refuses this file unless it declares sample, redact and ceiling
```

```console
$ OPENAI_API_KEY=fake OPENAI_BASE_URL=http://127.0.0.1:18960/v1 ANTHROPIC_API_KEY=fake ANTHROPIC_BASE_URL=http://127.0.0.1:18960 AWS_ENDPOINT_URL_BEDROCK_RUNTIME=http://127.0.0.1:18961 AWS_REGION=us-east-1 AWS_ACCESS_KEY_ID=fake AWS_SECRET_ACCESS_KEY=fake node app.mjs
desk on http://127.0.0.1:8080
```

That line is the application's own, and the recorder wrote nothing on
standard error. Four tickets went to the turn, one to each stream and one to
the subject line, through the application's endpoints:

```console
$ curl -s -X POST --data 'Where is my refund for the blue jacket?' http://127.0.0.1:8080/triage
{"category":"refund"}
```

```console
$ curl -s -X POST --data 'Where is my refund for the blue jacket?' http://127.0.0.1:8080/summary
Customer asks: Where is my refund for the blue jacket?
```

```console
$ curl -s -X POST --data 'My parcel is late.' http://127.0.0.1:8080/apology
We are sorry about my parcel is late.
```

```console
$ digline record status --tenant acme
tenant 'acme' · recording on
  switch:     …/desk/.digline/acme/recorder.toml
  values:     on true, sample 1.0 (default), redact none (default), ceiling 104857600 bytes (default), interval 5.0 s (default)
  writes to:  …/desk/.digline/acme/recordings
  size:       13341 bytes of recordings (as written; disk use is higher), ceiling 104857600
  suite _unassigned: 1 call, 0 orphans; since the last import: not read (pass --suite)
  suite apologies: 1 call, 0 orphans; since the last import: not read (pass --suite)
  suite summaries: 1 call, 0 orphans; since the last import: not read (pass --suite)
  suite triage: 4 calls, 4 inside episodes, 0 orphans, 4 episodes; since the last import: not read (pass --suite)
  not counted: 1 process keeps recordings and no counts, so what was not recorded there is not known
```

The four turns, each one Converse call inside its episode; the two streams,
each recorded with the text the application wrote out; and the subject line
under `_unassigned`. The last line is the Node writer's: it keeps its counts
in memory, `recorder.counts()`, and no counts file.

**Development and production.** `DiglineRecorder.development` files every
recording under one tenant. An application that resolves its tenant per
request uses `DiglineRecorder.production(root, () => tenantOf(request),
"desk")`, which refused to start on the file `digline record on` wrote, with
a `StartError`: *"switches recording on in production with no declared
redaction (write redact = "none", the one this release implements); no
declared sampling (write sample = p, above 0 and at most 1); no ceiling on
the size of its recordings (write ceiling = N, in bytes). In production all
three are declared (ADR 0058 §10)"*.

## Day two: from recordings to a suite

**A first suite, proposed**, from a directory `eval/` in the project:

```console
$ digline suggest --suite triage --tenant acme --repository private --root ..
digline suggest: wrote …/desk/eval/suite.proposed.toml. It is a proposal, not a suite: no command of digline reads it, nothing in it is a verdict, and no answer was marked. Adopt its lines into your suite, and the commit is yours
assumed:
  the form: suite.toml, the suite does not exist yet; the proposal is always TOML, and a target that is a function needs a suite.py (docs/declarative.md, What it cannot say)
  the setup its target reproduces: db92a897 for episodes
  the judge: none read: llm_rubric is proposed with judge = "provider/model", a placeholder that is refused until you name the provider plugin and the model, which are yours to choose; the provider plugins installed here: anthropic, bedrock, openai
  each check: 1. is_json, every one of 4 recordings answers JSON, top level object
  each check: 2. json_schema, the draft requires the keys every one of 4 recordings carries
  each check: 3. never, declared to the model and called in none of 4 recordings
  each check: 4. never, declared to the model and called in none of 4 recordings
  each check: 5. max_steps, the model's turns, in an agent's episode; limit is a placeholder, the strictest the check accepts: no run measured it
  each check: 6. latency_budget, every one of 4 recordings carries it, and the target has to report it too; max_ms is a placeholder, the strictest the check accepts: no run measured it; tolerance is a placeholder
  each check: 7. llm_rubric, the judged check the capture reviews answers for, asked three times with two in three to agree; threshold is a placeholder, the strictest the check accepts: no run measured it; the rubric, the judge and the tolerance are placeholders
  each starting number: no run read; 7 placeholders, each the strictest value its check accepts and marked in the file, failing until a measured number replaces it
  the calibration band: a skeleton for llm_rubric, with the answer to paste and the band to place, strictly between 0 and 1, both yours
  the counterexample: counterexample-1, constructed and marked as constructed: its input is yours to write, one whose answer llm_rubric must refuse, and nothing in it was recorded
  the regime: repository = 'private': without an assistant, the file quotes no recorded input or answer; the rules read from the recordings, a tool's name or a key, are in its checks
not yet examined: group 1 · episodes, text · 4 answers from 4 recordings
to examine them, once the proposal is your suite: digline record import --tenant acme --suite <your suite>
1 call of tenant 'acme' named no suite (_unassigned): counted, and read for nothing here. To give them a suite: digline record import --tenant acme --suite <your suite> --from _unassigned
```

It read the suite `triage` alone: the two streams are suites of their own,
and the subject line is in none. The two `never` checks are the two tools
`TOOLS` declares, which no turn called. A placeholder is the strictest value
its check accepts, marked `# placeholder`, and replaced by hand with a number
the runs measured ([the guide](../guide.md), chapters 4 and 5).

**Adopting it** is copying the file to `suite.toml` and writing what it leaves
to you: where the suite runs, the rubric and the judge.

```console
$ diff suite.proposed.toml suite.toml
11c11
< # environment = WRITE: mandatory, with no default: where it runs
---
> environment = "dev"
75,76c75,76
<   rubric = "WRITE: one question a good answer says yes to"  # placeholder: yours to write
<   judge = "provider/model"  # placeholder: yours to write, docs/declarative.md#the-judge-by-coordinates
---
>   rubric = "Is the category right for the ticket?"
>   judge = "openai/gpt-4o-mini"
```

**A person's yes or no**, on the page `digline view` serves with
`--allow-record`, from the project's directory:

```console
$ digline view --suite eval/suite.toml --allow-record
digline view on http://127.0.0.1:7373/?launch=… — the recorder's writes enabled, for the first browser that opens this address; --allow-promote to promote — ctrl-c to stop
```

Its *Recordings* view of `triage` lists one group, *an episode, text, steps
model, finish stop*, with the four turns. Each is a row with its id, when it
was first recorded, its setup and its answer, and two choices, `--good` and
`--bad`. Under them is one field, *Your name, the mark each case carries
(--by)*, and one button, *Write the answers named*, and under the button the
command that does what the button does, served as `digline record import
--tenant acme --suite eval/suite.toml`. Three yeses and one no, the turn that
answered `other` to *"I want my money back for the shoes."*, sent with the
name *Ada Lovelace*, wrote `eval/captured.json`. The form was sent as the
browser sends it, from `curl` with the cookie the launch address sets; no
browser was opened. With the choices and the name written out, the command
is:

```console
$ digline record import --tenant acme --suite eval/suite.toml --good cap-2ff5a5465dc6d823-763e65be --good cap-538c23ee6b0f3c97-0fd5adf9 --bad cap-379139c501bdf803-aefc126d --good cap-1697668d0e59c172-0fd5adf9 --by 'Ada Lovelace'
tenant 'acme' · suite triage · writes to eval/captured.json · repository private · check llm_rubric
  wrote cap-2ff5a5465dc6d823-763e65be
tenant 'acme' · suite triage · writes to eval/captured.json · repository private · check llm_rubric
  wrote cap-538c23ee6b0f3c97-0fd5adf9
tenant 'acme' · suite triage · writes to eval/captured.json · repository private · check llm_rubric
  wrote cap-379139c501bdf803-aefc126d
tenant 'acme' · suite triage · writes to eval/captured.json · repository private · check llm_rubric
  wrote cap-1697668d0e59c172-0fd5adf9
4 cases written to eval/captured.json: the diff is the review and the commit is the signature; nothing was committed, run or promoted (ADR 0023 §7)
```

The form and this command, given the same four answers and the same name,
wrote the same `captured.json`, byte for byte.

**The run.** The suite's cases are reviewed answers, so the run asks the
judge and never the application. The judge is digline's OpenAI plugin,
pointed at the stand-in by `OPENAI_BASE_URL`, the variable OpenAI's Python
SDK reads:

```console
$ OPENAI_BASE_URL=http://127.0.0.1:18960/v1 OPENAI_API_KEY=fake digline run --suite eval/suite.toml
digline: tenant 'acme' · 0 cases × 3 samples = 0 calls to the target; 4 reviewed answers judged 36 times, with no call to the target; each answer is judged 3 times by llm_rubric
digline: judge: 36 calls · counts: 756 in / 216 out · cost: 0.000243 USD
digline: recorded .digline/acme/runs/triage/2026-11-07T10-37-06-728717-00-00-1e95069890cca3f4.json
digline: next: digline promote --suite eval/suite.toml --run latest --replacing none  # keeps this run as the reference
2026-11-07T10-37-06-728717-00-00-1e95069890cca3f4
```

The counts are the stand-in's, and the cost is digline's, from
`gpt-4o-mini`'s price. The run exited `0`, and a person made it the
reference:

```console
$ digline promote --suite eval/suite.toml --run latest --replacing none
tenant 'acme' · triage baseline set to 2026-11-07T10-37-06-728717-00-00-1e95069890cca3f4
```

**The gate.** A later ticket named an order, so the turn asked for
`lookup_order` and took two Converse calls:

```console
$ curl -s -X POST --data 'I want a refund for order 42.' http://127.0.0.1:8080/triage
{"category":"refund"}
```

The answer is right, and the person said yes to it:

```console
$ digline record import --tenant acme --suite eval/suite.toml --good cap-baa842f3dfae2b30-763e65be --by 'Ada Lovelace'
tenant 'acme' · suite triage · writes to eval/captured.json · repository private · check llm_rubric
  wrote cap-baa842f3dfae2b30-763e65be
1 case written to eval/captured.json: the diff is the review and the commit is the signature; nothing was committed, run or promoted (ADR 0023 §7)
```

```console
$ OPENAI_BASE_URL=http://127.0.0.1:18960/v1 OPENAI_API_KEY=fake digline run --suite eval/suite.toml
digline: tenant 'acme' · 0 cases × 3 samples = 0 calls to the target; 5 reviewed answers judged 45 times, with no call to the target; each answer is judged 3 times by llm_rubric
digline: judge: 45 calls · counts: 945 in / 270 out · cost: 0.000304 USD
digline: checks on the steps contradicted a person on 1 reviewed answer: never, on case cap-baa842f3dfae2b30-763e65be; max_steps, on case cap-baa842f3dfae2b30-763e65be.
digline: recorded .digline/acme/runs/triage/2026-11-07T10-37-09-063718-00-00-1e95069890cca3f4.json
digline: next: digline compare --suite eval/suite.toml --run latest  # says whether anything got worse
2026-11-07T10-37-09-063718-00-00-1e95069890cca3f4
```

```console
$ digline compare --suite eval/suite.toml --run latest
Checks on the steps contradicted a person on 1 reviewed answer: never, on case cap-baa842f3dfae2b30-763e65be; max_steps, on case cap-baa842f3dfae2b30-763e65be, and the case fails: cap-baa842f3dfae2b30-763e65be for never, failed where the person said yes; cap-baa842f3dfae2b30-763e65be for max_steps, failed where the person said yes. Nothing got worse compared with the reference. Every case could be judged. No case is suspended. The suite is unchanged from the reference.
tenant 'acme', against baseline 2026-11-07T10-37-06-728717-00-00-1e95069890cca3f4
```

`compare` exited `1`, which is what a gate in CI reads. A yes on a turn is a
yes to its steps too: the person vouched for a turn that called
`lookup_order`, which the suite says is never called, and that took two model
turns, past the placeholder `limit = 1`. Which of the two is wrong, the rule
or the yes, is the person's to say.

**The call that named no suite** is listed as a suite's with `--from
_unassigned`, and says where it was made:

```console
$ digline record import --tenant acme --suite eval/suite.toml --from _unassigned
tenant 'acme' · suite triage · read from _unassigned · writes to eval/captured.json · repository private · check llm_rubric
  deterministic_output false

group 1 · a single call, text · 1 answer from 1 recording
  setup in force for single calls: 4ae6bb98
  cap-2d6997740b38c1e7-7f364bfe · 2026-11-07T10:37:01.880890+00:00 · setup 4ae6bb98
    made at: app.mjs:subject
    input:  {"messages": [{"content": "My parcel is late.", "role": "user"}]}
    answer: Re: My parcel is late.
    electable

1 answer in 1 group, from 1 recording of the suite; not cases: 0 orphans, 0 calls whose episode is not among the files, 0 interrupted episodes, 0 over the ceiling of a recording, 0 files that are not readable recordings
to write, name each answer with --good ID or --bad ID, and give --by NAME, your own name. An answer not named stays out
```

`app.mjs:subject`, and not `subjectOf`, which made the call: **a function
that returns the SDK's promise without `await` is not on the stack when the
call is made**, so the call carries the function that awaited the promise.
`return await` names the function itself:

```js
async function subjectOf(ticket) {
  return await openai.chat.completions.create({
    model: "gpt-4o-mini",
    messages: [{ role: "system", content: "Write the subject line." }, { role: "user", content: ticket }],
  });
}
```

With it, the application started again and the same ticket sent, the listing
read `made at: app.mjs:subject, app.mjs:subjectOf`: one answer, recorded
twice, from the two versions.

## What you get, and what stays out

- **Recorded in this story**: Bedrock's Converse inside a turn of an agent,
  Anthropic's Messages streamed, Bedrock's `converseStream`, and OpenAI's Chat
  Completions without a suite. The hooks also read what this story did not
  send: Chat Completions streamed, Messages unstreamed, and Bedrock's
  `invokeModel` and `invokeModelWithResponseStream` with an Anthropic model
  ([what the hooks read](../record-node.md#what-the-hooks-read)).
- **The call site** is where the promise was awaited, as above. A call made
  inside `suite(...)` carries none: in this story only the subject line
  carried one.
- **The second road is the proxy.** Where the application's code is not to be
  touched, `digline record proxy` runs on the application's machine and its
  SDKs point at it, with the suite in a header
  ([*Through the proxy*](../record-node.md#through-the-proxy)). This story did
  not run it.
- **OpenAI's Responses API is not recorded.** `diglineFetch` reads Chat
  Completions and Messages by the request's path. A `responses.create` sent
  through it inside a `suite`, to a server on 127.0.0.1 that answered it,
  reached `/v1/responses`, and wrote no recording and counted nothing in
  `recorder.counts()`.
- **Not measured**: a framework over the SDKs, LangChain.js or the Vercel AI
  SDK, and a call made in a worker thread, where whether `suite`, `episode`
  and `attach` reach it was not tried
  ([what stays out](../record-node.md#what-stays-out)).
- **No call in this story reached a provider or a model.** The application's
  answers, the judge's scores and the token counts the costs are printed from
  are the stand-in's.

The pages this one leans on: [the Node recorder](../record-node.md),
[`digline suggest`](../suggest.md), [`digline record`](../record.md) and
[`digline view`](../view.md#-allow-record).
