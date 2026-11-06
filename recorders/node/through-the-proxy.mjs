// The calls the CI job `through-the-proxy` makes from Node, and the lines
// docs/record-node.md quotes: a test holds each quoted line to this file. The
// request is recorders/through-the-proxy.json, the one every language sends.
import { readFileSync } from "node:fs";
import OpenAI from "openai";
import Anthropic from "@anthropic-ai/sdk";
import {
  BedrockRuntimeClient,
  ConverseStreamCommand,
  InvokeModelWithResponseStreamCommand,
} from "@aws-sdk/client-bedrock-runtime";
import { NodeHttpHandler } from "@smithy/node-http-handler";

const proxy = process.env.DIGLINE_PROXY;
const asked = JSON.parse(readFileSync(new URL("../through-the-proxy.json", import.meta.url)));

const openai = new OpenAI({
  baseURL: `${proxy}/v1`,
  apiKey: process.env.OPENAI_API_KEY ?? "via-proxy",
  defaultHeaders: { "X-Digline-Suite": "triage", "X-Digline-App": "node" },
});
await openai.chat.completions.create(asked.openai);
for await (const _ of await openai.chat.completions.create({ ...asked.openai, stream: true })) {}

const turn = { headers: { "X-Digline-Episode": "turn-node" } };
await openai.chat.completions.create(asked.openai, turn);
await openai.chat.completions.create(asked.openai, turn);

// No baseURL: ANTHROPIC_BASE_URL, which recorders/through-the-proxy.sh sets.
const anthropic = new Anthropic({
  apiKey: process.env.ANTHROPIC_API_KEY ?? "via-proxy",
  defaultHeaders: { "X-Digline-Suite": "triage", "X-Digline-App": "node" },
});
await anthropic.messages.create(asked.anthropic);
for await (const _ of await anthropic.messages.create({ ...asked.anthropic, stream: true })) {}

// Bedrock's two streams, the requests of recorders/fixtures/wire/, under the
// suite `bedrock`: the upstream answers each with the same bytes it gives
// in-process.mjs. The proxy speaks HTTP/1.1, and takes a call signed with
// the credentials it signs it again with, which the client reads from the
// environment recorders/through-the-proxy.sh sets.
const wire = (name) => JSON.parse(readFileSync(new URL(`../fixtures/wire/${name}.json`, import.meta.url)));
const bedrock = new BedrockRuntimeClient({ endpoint: proxy, requestHandler: new NodeHttpHandler() });
bedrock.middlewareStack.add(
  (next) => (args) => {
    args.request.headers["x-digline-suite"] = "bedrock";
    args.request.headers["x-digline-app"] = "node";
    return next(args);
  },
  { step: "build", name: "diglineSuite" },
);
const converse = wire("bedrock-stream");
for await (const _ of (await bedrock.send(new ConverseStreamCommand({ modelId: converse.model_id, ...converse.request }))).stream) {}
const invoke = wire("bedrock-invoke-stream");
const invoked = new InvokeModelWithResponseStreamCommand({
  modelId: invoke.model_id,
  contentType: "application/json",
  body: JSON.stringify(invoke.request),
});
for await (const _ of (await bedrock.send(invoked)).body) {}
