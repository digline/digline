// The calls the CI job `through-the-proxy` makes from Node, and the lines
// docs/record-node.md quotes: a test holds each quoted line to this file. The
// request is recorders/through-the-proxy.json, the one every language sends.
import { readFileSync } from "node:fs";
import OpenAI from "openai";
import Anthropic from "@anthropic-ai/sdk";

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
