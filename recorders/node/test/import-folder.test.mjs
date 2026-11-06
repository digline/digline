// Writes the recordings `digline record import` reads in the CI job
// recorder-node, under DIGLINE_NODE_IMPORT_ROOT: one episode of suite `s` and
// then two of its calls, for tenant `t`, the same as Java's ImportFolderTest.
// tests/test_recorder_node.py then imports them with digline alone. Without
// the variable the same files go to a temporary directory.

import assert from "node:assert/strict";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { test } from "node:test";

import { DiglineRecorder, ToolCall, Usage, suite } from "../digline/recorder.mjs";

test("writes what the import reads", async () => {
  const given = process.env.DIGLINE_NODE_IMPORT_ROOT;
  const root = given ? given : fs.mkdtempSync(path.join(os.tmpdir(), "digline-import-"));
  const tenant = path.join(root, ".digline", "t");
  fs.mkdirSync(tenant, { recursive: true });
  fs.writeFileSync(path.join(tenant, "recorder.toml"), "on = true\n", "utf8");

  const recorder = DiglineRecorder.development(root, "t", "node");
  const setup = { model: "gpt-4o-mini", temperature: 0.2 };
  // The episode first: the setup in force is the newest's, and the two calls
  // after it are what the import offers to elect.
  await recorder.episode("s", { ticket: "A1 is late" }, async (episode) => {
    await suite("lookup", async () =>
      recorder.record({
        caseCompartment: { messages: [{ role: "user", content: "A1?" }] },
        setup,
        output: "",
        latencyMs: 120.0,
        usage: new Usage(5, 2),
        finish: "tool_use",
        toolCalls: [ToolCall.asked("lookup", { order: "A1" })],
      }),
    );
    episode.output("A1 left the warehouse on Monday.");
  });
  await suite("s", async () => {
    recorder.record({
      caseCompartment: { messages: [{ role: "user", content: "Where is my refund?" }] },
      setup,
      output: "It was sent on Monday.",
      latencyMs: 812.0,
      usage: new Usage(14, 7),
      finish: "stop",
      toolCalls: [],
    });
    recorder.record({
      caseCompartment: { messages: [{ role: "user", content: "Où est la facture ?" }] },
      setup,
      output: "Dans votre espace client.",
      latencyMs: 640.5,
      usage: new Usage(12, 6),
      finish: "stop",
      toolCalls: [],
    });
  });
  assert.deepEqual(recorder.counts(), { noted: {}, not_recorded: {}, orphan: 0, recorded: 4 });
  const files = fs
    .readdirSync(path.join(tenant, "recordings"), { recursive: true })
    .filter((name) => String(name).endsWith(".json"));
  assert.equal(files.length, 4);
});
