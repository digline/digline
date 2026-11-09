// Each hook on its SDK's real client, against the fake provider of
// provider.mjs: what the hook wrote is what the readers make of the bytes
// that crossed the wire, a reply that is not 2xx is never recorded and a
// refused attempt is counted by its status, a
// stream is recorded at its end and counted when it is abandoned, and the
// application's call never fails because of the recorder.

import assert from "node:assert/strict";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { after, before, test } from "node:test";

import Anthropic from "@anthropic-ai/sdk";
import {
  BedrockRuntimeClient,
  ConverseCommand,
  ConverseStreamCommand,
  InvokeModelCommand,
  InvokeModelWithResponseStreamCommand,
} from "@aws-sdk/client-bedrock-runtime";
import { NodeHttpHandler } from "@smithy/node-http-handler";
import OpenAI from "openai";

import * as aws from "../digline/aws.mjs";
import { chat, chatStreamed, diglineFetch } from "../digline/fetch.mjs";
import * as messages from "../digline/messages.mjs";
import { DiglineRecorder, StartError, attach, object, parse, singleDocument, suite } from "../digline/recorder.mjs";
import { diglineAws } from "../digline/aws.mjs";
import { decode } from "../digline/eventstream.mjs";
import { eventStream, provider, wire } from "./provider.mjs";

let fake;

before(async () => {
  fake = await provider();
});

after(async () => {
  await fake.close();
});

/** A root whose tenant `acme` records, with the switch file `digline record on` writes. */
function root(switchText = "on = true\n") {
  const made = fs.mkdtempSync(path.join(os.tmpdir(), "digline-hooks-"));
  if (switchText !== null) {
    fs.mkdirSync(path.join(made, ".digline", "acme"), { recursive: true });
    fs.writeFileSync(path.join(made, ".digline", "acme", "recorder.toml"), switchText, "utf8");
  }
  return made;
}

/** What the recorder wrote under `root`, in the order it wrote it. */
function written(made) {
  const directory = path.join(made, ".digline", "acme", "recordings");
  if (!fs.existsSync(directory)) {
    return [];
  }
  return fs
    .readdirSync(directory)
    .sort()
    .flatMap((process_) =>
      fs
        .readdirSync(path.join(directory, process_))
        .filter((name) => name.endsWith(".json") && !name.startsWith("."))
        .sort()
        .map((name) => parse(fs.readFileSync(path.join(directory, process_, name), "utf8"))),
    );
}

/** The part of a recording a reader decides, without the moment it was written. */
function decided(document) {
  const response = { ...document.response };
  delete response.latency_ms;
  return { case: document.case, setup: document.setup, digest: document.setup_digest, response };
}

function openai(recorder, options = {}) {
  return new OpenAI({ apiKey: "k", baseURL: `${fake.url}/v1`, fetch: diglineFetch(recorder), maxRetries: 1, ...options });
}

function anthropic(recorder) {
  return new Anthropic({ apiKey: "k", baseURL: fake.url, fetch: diglineFetch(recorder), maxRetries: 1 });
}

function bedrock(recorder) {
  const client = bareBedrock();
  client.middlewareStack.use(diglineAws(recorder));
  return client;
}

/** The same client, with no hook. */
function bareBedrock() {
  return new BedrockRuntimeClient({
    region: "us-east-1",
    endpoint: fake.url,
    credentials: { accessKeyId: "a", secretAccessKey: "s" },
    requestHandler: new NodeHttpHandler(),
    maxAttempts: 2,
  });
}

/** The last request the provider received, its body read as digline reads it. */
function lastAsked() {
  return parse(fake.asked[fake.asked.length - 1].body);
}

/** The recording matches what the reader makes of the bytes the provider received and sent. */
function compared(document, read) {
  const want = singleDocument("acme", "node", "triage", read, "2026-11-06T00:00:00+00:00");
  assert.deepEqual(decided(document), decided(want));
}

test("a Chat Completions call is recorded as the map reads its bytes", async () => {
  const made = root();
  const recorder = DiglineRecorder.development(made, "acme", "node");
  const asked = wire("openai-single").request;
  const answer = await suite("triage", () => openai(recorder).chat.completions.create(asked));
  assert.equal(answer.choices[0].message.content, "Je regarde.");
  await settled(recorder, 1);
  const [document] = written(made);
  assert.equal(document.suite, "triage");
  assert.equal(document.call_site, undefined);
  compared(document, chat(lastAsked(), parse(JSON.stringify(wire("openai-single").reply)), 0));
  assert.equal(document.response.output, "Je regarde.");
});

test("a Chat Completions stream is recorded at its end", async () => {
  const made = root();
  const recorder = DiglineRecorder.development(made, "acme", "node");
  const asked = { ...wire("openai-stream").request };
  let text = "";
  await suite("triage", async () => {
    for await (const chunk of await openai(recorder).chat.completions.create(asked)) {
      text += chunk.choices[0]?.delta?.content ?? "";
    }
  });
  await settled(recorder, 1);
  const [document] = written(made);
  const sentEvents = wire("openai-stream").events.map((event) => parse(JSON.stringify(event)));
  compared(document, chatStreamed(lastAsked(), sentEvents, 0));
  assert.equal(document.response.output, text);
});

test("a Messages call and a Messages stream are recorded as the map reads them", async () => {
  const made = root();
  const recorder = DiglineRecorder.development(made, "acme", "node");
  const client = anthropic(recorder);
  await suite("triage", () => client.messages.create(wire("anthropic-single").request));
  const single = lastAsked();
  await suite("triage", async () => {
    for await (const _ of await client.messages.create(wire("anthropic-stream").request)) {
      // read to the end
    }
  });
  const streamedAsked = lastAsked();
  await settled(recorder, 2);
  const [first, second] = written(made);
  compared(first, messages.call(single, parse(JSON.stringify(wire("anthropic-single").reply)), 0));
  const sentEvents = wire("anthropic-stream").events.map((event) => parse(JSON.stringify(event)));
  compared(second, messages.streamed(streamedAsked, sentEvents, 0));
});

test("a retry after an error is one call recorded, and each refused attempt is counted by its status", async () => {
  const made = root();
  const recorder = DiglineRecorder.development(made, "acme", "node");
  fake.plan.push(500);
  await suite("triage", () => openai(recorder).chat.completions.create(wire("openai-single").request));
  await settled(recorder, 1);
  assert.equal(written(made).length, 1);

  fake.plan.push(400);
  await assert.rejects(() =>
    suite("triage", () => openai(recorder).chat.completions.create(wire("openai-single").request)),
  );
  await pause();
  assert.equal(written(made).length, 1);
  // The hook sees each attempt: the 500 the SDK retried, and the 400 it did
  // not, each counted beside the one call recorded.
  assert.deepEqual(recorder.counts(), {
    noted: {},
    not_recorded: { "provider error 400": 1, "provider error 500": 1 },
    orphan: 0,
    recorded: 1,
  });
});

test("a call the provider refuses with a 403 is counted by its status and not recorded", async () => {
  const made = root();
  const recorder = DiglineRecorder.development(made, "acme", "node");
  fake.plan.push(403);
  await assert.rejects(() =>
    suite("triage", () => openai(recorder).chat.completions.create(wire("openai-single").request)),
  );
  const fixture = wire("bedrock-single");
  fake.plan.push(403);
  await assert.rejects(() =>
    suite("triage", () => bedrock(recorder).send(new ConverseCommand({ modelId: fixture.model_id, ...fixture.request }))),
  );
  await pause();
  assert.equal(written(made).length, 0);
  assert.deepEqual(recorder.counts(), {
    noted: {},
    not_recorded: { "provider error 403": 2 },
    orphan: 0,
    recorded: 0,
  });
});

test("a stream the application stops reading is counted abandoned", async () => {
  const made = root();
  const recorder = DiglineRecorder.development(made, "acme", "node");
  fake.hold = true;
  try {
    await suite("triage", async () => {
      for await (const _ of await openai(recorder).chat.completions.create(wire("openai-stream").request)) {
        break;
      }
    });
  } finally {
    fake.hold = false;
  }
  await pause();
  assert.equal(written(made).length, 0);
  assert.deepEqual(recorder.counts().not_recorded, { "stream abandoned": 1 });
});

test("off, nothing is read or written", async () => {
  const made = root(null);
  const recorder = DiglineRecorder.development(made, "acme", "node");
  const answer = await openai(recorder).chat.completions.create(wire("openai-single").request);
  assert.equal(answer.choices[0].message.content, "Je regarde.");
  await pause();
  assert.equal(fs.existsSync(path.join(made, ".digline")), false);
  // Off is one test per call: nothing read, so nothing counted either.
  assert.deepEqual(recorder.counts(), { noted: {}, not_recorded: {}, orphan: 0, recorded: 0 });
});

test("the application's call never fails because the recorder cannot write", async () => {
  const made = root();
  fs.mkdirSync(path.join(made, ".digline", "acme"), { recursive: true });
  fs.writeFileSync(path.join(made, ".digline", "acme", "recordings"), "not a directory", "utf8");
  const recorder = DiglineRecorder.development(made, "acme", "node");
  const answer = await suite("triage", () => openai(recorder).chat.completions.create(wire("openai-single").request));
  assert.equal(answer.choices[0].message.content, "Je regarde.");
  await pause();
  assert.deepEqual(recorder.counts().not_recorded, { writer: 1 });
});

test("a stream whose body the application cancels is counted abandoned", async () => {
  // The SDKs abort the request when a loop breaks, which the test above
  // reaches; a body cancelled by the application's own code is the other way
  // a stream ends early.
  const made = root();
  const recorder = DiglineRecorder.development(made, "acme", "node");
  const first = `data: ${JSON.stringify(wire("openai-stream").events[0])}\n\n`;
  const inner = async () =>
    new Response(
      new ReadableStream({
        start(controller) {
          controller.enqueue(new TextEncoder().encode(first));
        },
      }),
      { status: 200, headers: { "content-type": "text/event-stream" } },
    );
  const response = await suite("triage", () =>
    diglineFetch(recorder, { fetch: inner })(`${fake.url}/v1/chat/completions`, {
      method: "POST",
      body: JSON.stringify(wire("openai-stream").request),
    }),
  );
  const reader = response.body.getReader();
  await reader.read();
  await reader.cancel();
  await pause();
  assert.deepEqual(recorder.counts().not_recorded, { "stream abandoned": 1 });
});

async function answerTicket(client) {
  return await client.chat.completions.create(wire("openai-single").request);
}

async function answerTicketWithoutAwait(client) {
  return client.chat.completions.create(wire("openai-single").request);
}

test("a call that names no suite carries the function that awaited it", async () => {
  const made = root();
  const recorder = DiglineRecorder.development(made, "acme", "node");
  const client = openai(recorder);
  await answerTicket(client);
  await answerTicketWithoutAwait(client);
  await settled(recorder, 2);
  const [awaited, returned] = written(made);
  assert.equal(awaited.suite, "_unassigned");
  assert.match(awaited.call_site, /test\/hooks\.test\.mjs:answerTicket$/);
  // The limit the page states: a function that returns the promise without
  // awaiting it is not on the stack, and the frame that awaited it is named.
  assert.doesNotMatch(returned.call_site, /:answerTicketWithoutAwait$/);
  assert.match(returned.call_site, /test\/hooks\.test\.mjs:/);
});

test("an episode holds the calls made inside it, across awaits and in attach", async () => {
  const made = root();
  const recorder = DiglineRecorder.development(made, "acme", "node");
  const client = openai(recorder);
  let id = null;
  const answer = await recorder.episode("agent", { ticket: "A1" }, async (episode) => {
    id = episode.id;
    await suite("triage", () => client.chat.completions.create(wire("openai-single").request));
    await new Promise((resolve) => setTimeout(resolve, 5));
    await attach(episode.id, () => suite("triage", () => client.chat.completions.create(wire("openai-single").request)));
    episode.output("done");
    return "returned";
  });
  assert.equal(answer, "returned");
  await settled(recorder, 3);
  const found = written(made);
  const episode = found.find((document) => document.id !== undefined);
  assert.equal(episode.id, id);
  assert.equal(episode.response.output, "done");
  assert.equal(episode.response.steps.filter((step) => step.actor === "model").length, 2);
  assert.equal(found.filter((document) => document.episode === id).length, 2);
});

test("an episode whose turn throws is recorded interrupted, and the error passed on", async () => {
  const made = root();
  const recorder = DiglineRecorder.development(made, "acme", "node");
  const client = openai(recorder);
  await assert.rejects(
    recorder.episode("agent", { ticket: "A1" }, async () => {
      await suite("triage", () => client.chat.completions.create(wire("openai-single").request));
      throw new Error("the agent failed");
    }),
    /the agent failed/,
  );
  await settled(recorder, 2);
  const episode = written(made).find((document) => document.id !== undefined);
  assert.equal(episode.interrupted, true);
});

test("Bedrock's Converse is recorded as the map reads its bytes, the model from the path", async () => {
  const made = root();
  const recorder = DiglineRecorder.development(made, "acme", "node");
  const fixture = wire("bedrock-single");
  const answer = await suite("triage", () =>
    bedrock(recorder).send(new ConverseCommand({ modelId: fixture.model_id, ...fixture.request })),
  );
  assert.ok(answer.output.message.content.length > 0, "the SDK still reads the reply");
  await settled(recorder, 1);
  const [document] = written(made);
  const asked = object({ modelId: fixture.model_id, ...lastAsked() });
  compared(document, aws.call(asked, parse(JSON.stringify(fixture.reply)), 0));
});

test("Bedrock's InvokeModel with an Anthropic model is Messages, another family is counted", async () => {
  const made = root();
  const recorder = DiglineRecorder.development(made, "acme", "node");
  const fixture = wire("bedrock-invoke");
  const client = bedrock(recorder);
  const answer = await suite("triage", () =>
    client.send(
      new InvokeModelCommand({
        modelId: fixture.model_id,
        contentType: "application/json",
        body: JSON.stringify(fixture.request),
      }),
    ),
  );
  assert.ok(JSON.parse(Buffer.from(answer.body).toString("utf8")).content, "the SDK still hands the body over");
  await settled(recorder, 1);
  const [document] = written(made);
  const asked = object({ modelId: fixture.model_id, ...lastAsked() });
  compared(document, messages.call(asked, parse(JSON.stringify(fixture.reply)), 0));

  for (let i = 0; i < 2; i++) {
    await client.send(
      new InvokeModelCommand({ modelId: "amazon.titan-text-express-v1", contentType: "application/json", body: "{}" }),
    );
  }
  assert.deepEqual(recorder.counts().not_recorded, { "model family not recorded": 2 });
});

/** A ConverseStream of the wire fixture, read by the application to its end; its text. */
async function converseStream(recorder) {
  const fixture = wire("bedrock-stream");
  const client = recorder === null ? bareBedrock() : bedrock(recorder);
  const answer = await suite("triage", () =>
    client.send(new ConverseStreamCommand({ modelId: fixture.model_id, ...fixture.request })),
  );
  let text = "";
  for await (const event of answer.stream) {
    text += event.contentBlockDelta?.delta?.text ?? "";
  }
  return text;
}

/** What the SDK throws to the application for a stream: with the hook, or with none where `recorder` is `null`. */
async function thrown(recorder, name) {
  fake.stream = name;
  try {
    await converseStream(recorder);
  } catch (failed) {
    return `${failed.name}: ${failed.message}`;
  } finally {
    fake.stream = null;
  }
  return null;
}

test("Bedrock's ConverseStream is recorded at its end, as the map reads its bytes", async () => {
  const made = root();
  const recorder = DiglineRecorder.development(made, "acme", "node");
  assert.equal(await converseStream(recorder), "Looking it up.", "the SDK still reads the stream");
  await settled(recorder, 1);
  const [document] = written(made);
  const fixture = wire("bedrock-stream");
  const asked = object({ modelId: fixture.model_id, ...lastAsked() });
  compared(document, aws.streamed(asked, decode(eventStream("bedrock-stream")).events, 0));
  assert.equal(document.response.output, "Looking it up.");
  assert.equal(document.response.tool_calls[0].tool, "lookup");
});

test("Bedrock's InvokeModelWithResponseStream with an Anthropic model is Messages, its chunks decoded", async () => {
  const made = root();
  const recorder = DiglineRecorder.development(made, "acme", "node");
  const fixture = wire("bedrock-invoke-stream");
  const client = bedrock(recorder);
  const answer = await suite("triage", () =>
    client.send(
      new InvokeModelWithResponseStreamCommand({
        modelId: fixture.model_id,
        contentType: "application/json",
        body: JSON.stringify(fixture.request),
      }),
    ),
  );
  const types = [];
  for await (const event of answer.body) {
    types.push(JSON.parse(Buffer.from(event.chunk.bytes).toString("utf8")).type);
  }
  assert.equal(types.at(-1), "message_stop", "the SDK still hands each chunk over");
  await settled(recorder, 1);
  const [document] = written(made);
  const asked = object({ modelId: fixture.model_id, ...lastAsked() });
  compared(document, messages.streamed(asked, aws.chunks(decode(eventStream("bedrock-invoke-stream")).events), 0));
  assert.equal(document.response.output, "Looking it up.");

  // Another family's stream is not read, and reaches the SDK as it came.
  const other = await client.send(
    new InvokeModelWithResponseStreamCommand({ modelId: "amazon.titan-text-express-v1", contentType: "application/json", body: "{}" }),
  );
  let chunks = 0;
  for await (const _ of other.body) {
    chunks++;
  }
  assert.equal(chunks, types.length);
  assert.deepEqual(recorder.counts().not_recorded, { "model family not recorded": 1 });
});

test("Bedrock's ConverseStream is recorded over HTTP/2, the client's default", async () => {
  const fakeHttp2 = await provider({ http2: true });
  try {
    const made = root();
    const recorder = DiglineRecorder.development(made, "acme", "node");
    const client = new BedrockRuntimeClient({
      region: "us-east-1",
      endpoint: fakeHttp2.url,
      credentials: { accessKeyId: "a", secretAccessKey: "s" },
    });
    client.middlewareStack.use(diglineAws(recorder));
    const fixture = wire("bedrock-stream");
    const answer = await suite("triage", () =>
      client.send(new ConverseStreamCommand({ modelId: fixture.model_id, ...fixture.request })),
    );
    let text = "";
    for await (const event of answer.stream) {
      text += event.contentBlockDelta?.delta?.text ?? "";
    }
    assert.equal(text, "Looking it up.");
    await settled(recorder, 1);
    const [document] = written(made);
    const asked = object({ modelId: fixture.model_id, ...parse(fakeHttp2.asked.at(-1).body) });
    compared(document, aws.streamed(asked, decode(eventStream("bedrock-stream")).events, 0));
  } finally {
    await fakeHttp2.close();
  }
});

test("a Bedrock stream the application stops reading is counted abandoned", async () => {
  const made = root();
  const recorder = DiglineRecorder.development(made, "acme", "node");
  const fixture = wire("bedrock-stream");
  // The SDK stops reading a stream when its call is aborted: a `break` out of
  // the loop leaves the connection open, and nothing ends until it does.
  const stop = new AbortController();
  fake.hold = true;
  try {
    const answer = await suite("triage", () =>
      bedrock(recorder).send(new ConverseStreamCommand({ modelId: fixture.model_id, ...fixture.request }), {
        abortSignal: stop.signal,
      }),
    );
    for await (const _ of answer.stream) {
      stop.abort();
      break;
    }
  } finally {
    fake.hold = false;
  }
  await settled(recorder, 1);
  assert.equal(written(made).length, 0);
  assert.deepEqual(recorder.counts().not_recorded, { "stream abandoned": 1 });
});

test("a Bedrock stream that ends inside an event is abandoned, never read as whole", async () => {
  const made = root();
  const recorder = DiglineRecorder.development(made, "acme", "node");
  const app = await thrown(recorder, "abandoned");
  assert.equal(app, await thrown(null, "abandoned"));
  await settled(recorder, 1);
  assert.equal(written(made).length, 0);
  assert.deepEqual(recorder.counts().not_recorded, { "stream abandoned": 1 });
});

for (const name of ["bad-crc", "bad-prelude", "exception"]) {
  test(`a Bedrock stream that does not check is refused and counted, and never thrown by the hook: ${name}`, async () => {
    const made = root();
    const recorder = DiglineRecorder.development(made, "acme", "node");
    const app = await thrown(recorder, name);
    // What the application meets is the SDK's, as without the hook.
    assert.notEqual(app, null, "the SDK refuses these bytes itself");
    assert.equal(app, await thrown(null, name));
    await settled(recorder, 1);
    assert.equal(written(made).length, 0);
    assert.deepEqual(recorder.counts().not_recorded, { "stream error": 1 });
  });
}

test("a Bedrock retry after an error is one call recorded, its refused attempt counted", async () => {
  const made = root();
  const recorder = DiglineRecorder.development(made, "acme", "node");
  const fixture = wire("bedrock-single");
  fake.plan.push(500);
  await suite("triage", () => bedrock(recorder).send(new ConverseCommand({ modelId: fixture.model_id, ...fixture.request })));
  await settled(recorder, 1);
  await pause();
  assert.equal(written(made).length, 1);
  assert.deepEqual(recorder.counts(), {
    noted: {},
    not_recorded: { "provider error 500": 1 },
    orphan: 0,
    recorded: 1,
  });
});

test("production refuses a development file, and records under a production one", async () => {
  assert.throws(
    () => DiglineRecorder.production(root(), () => "acme", "node"),
    (refused) => refused instanceof StartError && refused.message.includes("switches recording on in production"),
  );
  const made = root('on = true\nsample = 1\nredact = "none"\nceiling = 1000000\n');
  const recorder = DiglineRecorder.production(made, () => "acme", "node");
  await suite("triage", () => openai(recorder).chat.completions.create(wire("openai-single").request));
  await settled(recorder, 1);
  assert.equal(written(made).length, 1);
});

/** Waits until the recorder has counted `n` outcomes: a whole reply is read beside the application. */
async function settled(recorder, n) {
  for (let i = 0; i < 200; i++) {
    const counted = recorder.counts();
    const total = counted.recorded + Object.values(counted.not_recorded).reduce((a, b) => a + b, 0);
    if (total >= n) {
      return;
    }
    await pause(10);
  }
  assert.fail(`the recorder counted ${JSON.stringify(recorder.counts())}, not ${n} outcomes`);
}

function pause(ms = 50) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
