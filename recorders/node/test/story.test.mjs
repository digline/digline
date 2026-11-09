// The lines docs/walkthroughs/node.md quotes, run. Each JavaScript block of the
// story, in order, is one of the blocks here between a `// page:` line and an
// `// end` line, and tests/test_story_node.py holds them equal, indentation
// aside. The clients find the stand-in the story was run against,
// test/stand-in.mjs, through the variables each SDK reads, so the lines are
// the page's as written: Bedrock's with its default handler, HTTP/2.

import assert from "node:assert/strict";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { test } from "node:test";

import OpenAI from "openai";
import Anthropic from "@anthropic-ai/sdk";
import { BedrockRuntimeClient, ConverseCommand, ConverseStreamCommand } from "@aws-sdk/client-bedrock-runtime";
import { DiglineRecorder, parse, suite } from "../digline/recorder.mjs";
import { diglineFetch } from "../digline/fetch.mjs";
import { diglineAws } from "../digline/aws.mjs";
import { standIn } from "./stand-in.mjs";

const MODEL = "us.anthropic.claude-haiku-4-5-20251001-v1:0";
const TOOLS = {
  tools: [
    { toolSpec: { name: "lookup_order", description: "An order's state, by its number.", inputSchema: { json: { type: "object", properties: { order: { type: "string" } }, required: ["order"] } } } },
    { toolSpec: { name: "escalate", description: "Hand the ticket to a person.", inputSchema: { json: { type: "object", properties: {} } } } },
  ],
};
const SYSTEM = [{ text: 'Answer with the ticket\'s category as JSON, {"category": "refund" | "delivery" | "other"}.' }];

async function lookupOrder({ order }) {
  return { order, state: "shipped" };
}

/** A response the application writes a stream into, kept. */
function sink() {
  const written = [];
  return { write: (text) => written.push(text), text: () => written.join("") };
}

function recordings(root) {
  const directory = path.join(root, ".digline", "acme", "recordings");
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

async function settled(recorder, n) {
  for (let i = 0; i < 200 && recorder.counts().recorded < n; i++) {
    await new Promise((resolve) => setTimeout(resolve, 10));
  }
}

test("the story's lines record what it says", async () => {
  const fake = await standIn();
  const saved = { ...process.env };
  Object.assign(process.env, {
    OPENAI_API_KEY: "fake",
    OPENAI_BASE_URL: `${fake.url}/v1`,
    ANTHROPIC_API_KEY: "fake",
    ANTHROPIC_BASE_URL: fake.url,
    AWS_REGION: "us-east-1",
    AWS_ACCESS_KEY_ID: "fake",
    AWS_SECRET_ACCESS_KEY: "fake",
    AWS_ENDPOINT_URL_BEDROCK_RUNTIME: fake.bedrockUrl,
  });
  try {
    const root = fs.mkdtempSync(path.join(os.tmpdir(), "digline-story-"));
    fs.mkdirSync(path.join(root, ".digline", "acme"), { recursive: true });
    fs.writeFileSync(path.join(root, ".digline", "acme", "recorder.toml"), "on = true\n", "utf8");

    // page:
    const recorder = DiglineRecorder.development(root, "acme", "desk");

    const openai = new OpenAI({ fetch: diglineFetch(recorder) });
    const anthropic = new Anthropic({ fetch: diglineFetch(recorder) });
    const bedrock = new BedrockRuntimeClient({});
    bedrock.middlewareStack.use(diglineAws(recorder));
    // end

    // page:
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
    // end

    // page:
    function triage(ticket) {
      return recorder.episode("triage", { ticket }, async (episode) => {
        const answer = await turn(ticket);
        episode.output(answer);
        return answer;
      });
    }
    // end

    // page:
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
    // end

    // page:
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
    // end

    assert.equal(await triage("Where is my refund for the blue jacket?"), '{"category":"refund"}');
    assert.equal(await triage("I want a refund for order 42."), '{"category":"refund"}');
    const summarised = sink();
    await summary("Where is my refund for the blue jacket?", summarised);
    const apologised = sink();
    await apology("My parcel is late.", apologised);

    let subjects = [];
    {
      // page:
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
      // end
      subjects.push(await subject("My parcel is late."));
    }
    {
      async function subject(ticket) {
        const completion = await subjectOf(ticket);
        return completion.choices[0].message.content;
      }
      // page:
      async function subjectOf(ticket) {
        return await openai.chat.completions.create({
          model: "gpt-4o-mini",
          messages: [{ role: "system", content: "Write the subject line." }, { role: "user", content: ticket }],
        });
      }
      // end
      subjects.push(await subject("My parcel is late."));
    }
    // Two episodes of one and two calls, two streams and two subjects.
    await settled(recorder, 9);

    const found = recordings(root);
    const episodes = found.filter((each) => each.id !== undefined);
    assert.deepEqual(
      episodes.map((each) => [each.response.output, found.filter((call) => call.episode === each.id).length]),
      [['{"category":"refund"}', 1], ['{"category":"refund"}', 2]],
    );
    const named = (suiteName) => found.filter((each) => each.suite === suiteName && each.id === undefined);
    assert.equal(named("triage").length, 3);
    // Each stream, recorded as the application read it.
    assert.equal(summarised.text(), "Customer asks: Where is my refund for the blue jacket?");
    assert.deepEqual(named("summaries").map((each) => each.response.output), [summarised.text()]);
    assert.equal(apologised.text(), "We are sorry about my parcel is late.");
    assert.deepEqual(named("apologies").map((each) => each.response.output), [apologised.text()]);
    // The call site: without `await`, the function that awaited the promise;
    // with `return await`, the function itself.
    assert.deepEqual(subjects, ["Re: My parcel is late.", "Re: My parcel is late."]);
    const sites = named("_unassigned").map((each) => each.call_site.split(":").at(-1));
    assert.deepEqual(sites, ["subject", "subjectOf"]);
    assert.equal(recorder.counts().recorded, 9);
  } finally {
    for (const key of Object.keys(process.env)) {
      if (!(key in saved)) {
        delete process.env[key];
      }
    }
    Object.assign(process.env, saved);
    await fake.close();
  }
});
