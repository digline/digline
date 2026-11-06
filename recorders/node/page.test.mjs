// The lines docs/record-node.md quotes, run. Each JavaScript block of the
// page's first part, in order, is one of the blocks here between a `// page:`
// line and an `// end` line, and tests/test_record_node_page.py holds them
// equal, indentation aside. The clients find the fake provider of
// test/provider.mjs through the variables each SDK reads, so the lines are
// the page's as written: Bedrock's with its default handler, HTTP/2.
// page:
import OpenAI from "openai";
import Anthropic from "@anthropic-ai/sdk";
import { BedrockRuntimeClient, ConverseCommand } from "@aws-sdk/client-bedrock-runtime";
import { DiglineRecorder, attach, suite } from "./digline/recorder.mjs";
import { diglineFetch } from "./digline/fetch.mjs";
import { diglineAws } from "./digline/aws.mjs";
// end

import assert from "node:assert/strict";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { test } from "node:test";

import { parse } from "./digline/recorder.mjs";
import { provider, wire } from "./test/provider.mjs";

function recordings(root, tenant) {
  const directory = path.join(root, ".digline", tenant, "recordings");
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

test("the page's lines record what they say", async () => {
  const fake = await provider();
  const fakeBedrock = await provider({ http2: true });
  const saved = { ...process.env };
  Object.assign(process.env, {
    OPENAI_API_KEY: "k",
    OPENAI_BASE_URL: `${fake.url}/v1`,
    ANTHROPIC_API_KEY: "k",
    ANTHROPIC_BASE_URL: fake.url,
    AWS_REGION: "us-east-1",
    AWS_ACCESS_KEY_ID: "a",
    AWS_SECRET_ACCESS_KEY: "s",
    AWS_ENDPOINT_URL_BEDROCK_RUNTIME: fakeBedrock.url,
  });
  try {
    const root = fs.mkdtempSync(path.join(os.tmpdir(), "digline-page-"));
    fs.mkdirSync(path.join(root, ".digline", "acme"), { recursive: true });
    fs.writeFileSync(path.join(root, ".digline", "acme", "recorder.toml"), "on = true\n", "utf8");

    // page:
    const recorder = DiglineRecorder.development(root, "acme", "support");

    const openai = new OpenAI({ fetch: diglineFetch(recorder) });
    const anthropic = new Anthropic({ fetch: diglineFetch(recorder) });
    const bedrock = new BedrockRuntimeClient({});
    bedrock.middlewareStack.use(diglineAws(recorder));
    // end

    const params = wire("openai-single").request;
    // page:
    await suite("refunds", () => openai.chat.completions.create(params));
    // end
    await suite("refunds", () => anthropic.messages.create(wire("anthropic-single").request));
    const converse = wire("bedrock-single");
    await suite("refunds", () => bedrock.send(new ConverseCommand({ modelId: converse.model_id, ...converse.request })));
    await settled(recorder, 3);

    const ticket = "A1 is late";
    const agent = { answer: async () => (await openai.chat.completions.create(params)).choices[0].message.content };
    // page:
    await recorder.episode("order-agent", { ticket }, async (episode) => {
      episode.output(await agent.answer(ticket));
    });
    // end

    let id = null;
    const order = "A1";
    const lookup = async () => suite("refunds", () => openai.chat.completions.create(params));
    await recorder.episode("order-agent", { ticket }, async (episode) => {
      id = episode.id;
      await new Promise((resolve) => setTimeout(resolve, 1));
      // page:
      await attach(id, () => lookup(order));
      // end
    });
    await settled(recorder, 7);

    const found = recordings(root, "acme");
    const singles = found.filter((each) => each.suite === "refunds" && each.episode === undefined);
    assert.deepEqual(
      singles.map((each) => each.setup.model ?? each.setup.modelId),
      ["gpt-4o-mini", "claude-haiku-4-5", converse.model_id],
    );
    const episodes = found.filter((each) => each.id !== undefined);
    assert.equal(episodes.length, 2);
    assert.equal(episodes[0].response.output, "Je regarde.");
    assert.equal(found.filter((each) => each.episode === id).length, 1);

    // In production the tenant is asked at every call, from a file that
    // declares the three values production requires.
    const request = { tenant: "globex" };
    const tenantOf = (asked) => asked.tenant;
    fs.mkdirSync(path.join(root, ".digline", "globex"), { recursive: true });
    fs.writeFileSync(
      path.join(root, ".digline", "globex", "recorder.toml"),
      'on = true\nsample = 1\nredact = "none"\nceiling = 1000000\n',
      "utf8",
    );
    fs.rmSync(path.join(root, ".digline", "acme", "recorder.toml"));
    {
      // page:
      const recorder = DiglineRecorder.production(root, () => tenantOf(request), "support");
      // end
      const client = new OpenAI({ fetch: diglineFetch(recorder) });
      await suite("refunds", () => client.chat.completions.create(params));
      await settled(recorder, 1);
      assert.equal(recordings(root, "globex").length, 1);
    }
  } finally {
    for (const key of Object.keys(process.env)) {
      if (!(key in saved)) {
        delete process.env[key];
      }
    }
    Object.assign(process.env, saved);
    await fake.close();
    await fakeBedrock.close();
  }
});
