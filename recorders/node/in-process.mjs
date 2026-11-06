// The calls the CI job `through-the-proxy` makes from Node with the recorder
// in the process: the same request every language sends,
// recorders/through-the-proxy.json, sent to the fake upstream directly
// through `diglineFetch`, a single call and a stream from each SDK, recorded
// under the app `node-in-process` in the directory the proxy writes to.
// tests/test_through_the_proxy.py holds that they give the case and the setup
// digest the proxy's recordings give from Node, Python and Java.
import { readFileSync } from "node:fs";
import OpenAI from "openai";
import Anthropic from "@anthropic-ai/sdk";
import { DiglineRecorder, suite } from "./digline/recorder.mjs";
import { diglineFetch } from "./digline/fetch.mjs";

const upstream = process.env.DIGLINE_UPSTREAM;
const asked = JSON.parse(readFileSync(new URL("../through-the-proxy.json", import.meta.url)));

// DIGLINE_RECORD=1, which recorders/through-the-proxy.sh sets: no switch file.
const recorder = DiglineRecorder.development(process.env.DIGLINE_ROOT, "t", "node-in-process");
const openai = new OpenAI({ baseURL: `${upstream}/v1`, apiKey: "in-process", fetch: diglineFetch(recorder) });
const anthropic = new Anthropic({ baseURL: upstream, apiKey: "in-process", fetch: diglineFetch(recorder) });

await suite(asked.suite, async () => {
  await openai.chat.completions.create(asked.openai);
  for await (const _ of await openai.chat.completions.create({ ...asked.openai, stream: true })) {}
  await anthropic.messages.create(asked.anthropic);
  for await (const _ of await anthropic.messages.create({ ...asked.anthropic, stream: true })) {}
});

// A whole reply is read beside the application: wait until all four are counted.
for (let i = 0; i < 200; i++) {
  const counted = recorder.counts();
  if (counted.recorded + Object.values(counted.not_recorded).reduce((a, b) => a + b, 0) >= 4) {
    break;
  }
  await new Promise((resolve) => setTimeout(resolve, 10));
}
const counted = recorder.counts();
console.log(`node-in-process: ${JSON.stringify(counted)}`);
if (counted.recorded !== 4) {
  process.exitCode = 1;
}
