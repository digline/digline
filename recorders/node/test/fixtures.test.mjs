// The writer held to what digline's Python answers, on the files
// recorders/fixtures/make.py writes from digline's own code and
// tests/test_recorder_fixtures.py holds equal to it: the files Java's
// recorder is held to as well.

import assert from "node:assert/strict";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

import * as aws from "../digline/aws.mjs";
import { chat, chatStreamed } from "../digline/fetch.mjs";
import * as messages from "../digline/messages.mjs";
import {
  Call,
  DiglineRecorder,
  GATE_DIRECTORY,
  GITATTRIBUTES,
  GITIGNORE,
  StartError,
  ToolCall,
  Usage,
  file,
  floatText,
  gate,
  isName,
  object,
  parse,
  parseSwitch,
  pythonRepr,
  refusal,
  round,
  setupDigest,
  singleDocument,
} from "../digline/recorder.mjs";

const FIXTURES = path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "..", "fixtures");

function read(name) {
  return fs.readFileSync(path.join(FIXTURES, name), "utf8");
}

function parsed(name) {
  return parse(read(name));
}

/** The latency every wire fixture is recorded with: `WIRE_LATENCY_MS` in make.py. */
const LATENCY_MS = 250.5;

/** The wire calls this pull request reads. Bedrock's two streams are read by the next. */
const STREAMS_OF_BEDROCK = ["bedrock-invoke-stream.json", "bedrock-stream.json"];

test("every setup digest is Python's", () => {
  const setups = parsed("setups.json");
  assert.equal(setups.length, 3);
  for (const each of setups) {
    assert.equal(setupDigest(each.setup), each.digest, file(each.setup));
  }
  // The one measured across Java and Python on 2026-11-04 (ADR 0062).
  assert.equal(setupDigest(object({ max_tokens: 64n, model: "claude-haiku-4-5" })), "81869b20f0d8875a");
});

test("every float is written as Python writes it", () => {
  // Each row: the double's bits, its repr, its float_text, the repr of it rounded.
  const floats = parsed("floats.json");
  assert.ok(floats.length > 1000, "the edges, the powers of two, the random draws");
  const wrong = [];
  const view = new DataView(new ArrayBuffer(8));
  for (const [bits, repr, text, roundedRepr] of floats) {
    view.setBigUint64(0, BigInt(`0x${bits}`));
    const value = view.getFloat64(0);
    for (const [what, python, node] of [
      ["repr", repr, pythonRepr(value)],
      ["text", text, floatText(value)],
      ["rounded", roundedRepr, pythonRepr(round(value))],
    ]) {
      if (python !== node) {
        wrong.push(`${bits} ${what}: Python ${python}, Node ${node}`);
      }
    }
  }
  assert.deepEqual(wrong, []);
});

test("a tie at the sixth place goes to the even digit, as Python's round takes it", () => {
  // floats.json holds no exact tie, so it cannot tell half to even from half
  // up. A double is a tie at the sixth place only at an odd multiple of
  // 1/128; Python 3.14's round(value, 6), read on 2026-11-06, gave these.
  for (const [value, python] of [
    [0.0078125, "0.007812"],
    [0.0234375, "0.023438"],
    [-0.0078125, "-0.007812"],
    [1.0078125, "1.007812"],
  ]) {
    assert.equal(pythonRepr(round(value)), python, String(value));
  }
});

test("every switch is read as Python reads it", () => {
  for (const each of parsed("switches.json")) {
    if (each.refusal !== undefined) {
      assert.throws(
        () => parseSwitch(each.text, "recorder.toml", each.production),
        (refused) => refused instanceof StartError && refused.message === each.refusal,
        each.text,
      );
      continue;
    }
    const expected = each.switch;
    const found = parseSwitch(each.text, "recorder.toml", each.production);
    assert.equal(found.on, expected.on, each.text);
    assert.equal(found.sample, Number(expected.sample), each.text);
    assert.equal(found.ceiling, expected.ceiling, each.text);
    assert.equal(found.interval, Number(expected.interval), each.text);
    assert.equal(found.production, expected.production, each.text);
    assert.deepEqual([...found.declared].sort(), expected.declared, each.text);
  }
});

function callOf(call) {
  const usage = call.usage;
  return new Call(
    call.case,
    call.setup,
    call.output,
    call.latency_ms,
    new Usage(
      usage.input_tokens,
      usage.output_tokens,
      usage.cache_read_tokens,
      usage.cache_write_tokens,
      usage.thinking_tokens,
    ),
    call.finish,
    call.tool_calls.map((each) => ToolCall.asked(each.tool, each.arguments)),
  );
}

test("one call is the file digline's writer writes", () => {
  const call = parsed("call.json");
  const written = singleDocument(call.tenant, call.app, call.suite, callOf(call), call.recorded_at);
  assert.equal(file(written) + "\n", read("call.expected.json"));
});

/** A wire fixture read by the reader its route takes, as each hook reads it. */
function readWire(wire) {
  const streamed = wire.events !== undefined;
  switch (wire.route) {
    case "openai":
      return streamed ? chatStreamed(wire.request, wire.events, LATENCY_MS) : chat(wire.request, wire.reply, LATENCY_MS);
    case "anthropic":
      return streamed
        ? messages.streamed(wire.request, wire.events, LATENCY_MS)
        : messages.call(wire.request, wire.reply, LATENCY_MS);
    case "bedrock": {
      const asked = object({ modelId: wire.model_id, ...wire.request });
      return wire.path.includes("/invoke")
        ? messages.call(asked, wire.reply, LATENCY_MS)
        : aws.call(asked, wire.reply, LATENCY_MS);
    }
    default:
      throw new Error(`no route ${wire.route}`);
  }
}

test("every wire call is the file digline's map writes", () => {
  const wire = path.join(FIXTURES, "wire");
  const calls = fs
    .readdirSync(wire)
    .filter((name) => !name.endsWith(".expected.json"))
    .sort();
  assert.equal(calls.length, 12, calls.join(" "));
  const call = parsed("call.json");
  const read_ = calls.filter((name) => !STREAMS_OF_BEDROCK.includes(name));
  assert.equal(read_.length, 10);
  for (const name of read_) {
    const fixture = parse(fs.readFileSync(path.join(wire, name), "utf8"));
    const written = singleDocument(call.tenant, call.app, call.suite, readWire(fixture), call.recorded_at);
    const expected = fs.readFileSync(path.join(wire, name.replace(".json", ".expected.json")), "utf8");
    assert.equal(file(written) + "\n", expected, name);
  }
});

test("Bedrock takes the model from the path", () => {
  assert.equal(
    aws.modelIdOf("/model/anthropic.claude-3-5-haiku-20241022-v1%3A0/converse-stream"),
    "anthropic.claude-3-5-haiku-20241022-v1:0",
  );
  assert.equal(aws.modelIdOf("/model/a+b/converse"), "a+b");
  assert.equal(
    aws.modelIdOf("/model/arn%3Aaws%3Abedrock%3Aus-east-1%3A1%3Ap%2Fx/converse"),
    "arn:aws:bedrock:us-east-1:1:p/x",
  );
});

test("every gate marker is read as Python reads it", () => {
  // Each row: the markers laid out, each with its age in seconds, and what
  // digline.recorder._gate answered for them. (ADR 0058, 2026-11-05)
  const gates = parsed("gates.json");
  assert.ok(gates.length > 5, "none, live, stale, two, unreadable, ignored names");
  const scratch = fs.mkdtempSync(path.join(os.tmpdir(), "digline-gates-"));
  gates.forEach((each, row) => {
    const root = path.join(scratch, `row${row}`);
    const place = path.join(root, ".digline", "acme", ...GATE_DIRECTORY);
    fs.mkdirSync(place, { recursive: true });
    const now = Date.now();
    for (const marker of each.markers) {
      const where = path.join(place, marker.name);
      fs.writeFileSync(where, marker.text, "utf8");
      const when = new Date(now - Number(marker.age) * 1000);
      fs.utimesSync(where, when, when);
    }
    const found = gate(root, "acme", now);
    assert.equal(found === null ? null : found[0], each.origin, JSON.stringify(each.markers.map((m) => m.name)));
    assert.equal(found === null ? null : found[1], each.run_id, JSON.stringify(each.markers.map((m) => m.name)));
  });
  assert.deepEqual(GATE_DIRECTORY, ["runs", ".gate"]);
});

test("a gate or a marker that links out of the store is not read", () => {
  // As digline.host.gate holds it: resolved, and inside the store.
  const scratch = fs.mkdtempSync(path.join(os.tmpdir(), "digline-links-"));
  const marker = '{"run_id": "k", "pid": 1, "started_at": "x", "suite": "s"}';
  const outside = path.join(scratch, "outside");
  fs.mkdirSync(outside);
  fs.writeFileSync(path.join(outside, "1-k.json"), marker, "utf8");
  const linked = path.join(scratch, "linked");
  const runs = path.join(linked, ".digline", "acme", "runs");
  fs.mkdirSync(runs, { recursive: true });
  fs.symlinkSync(outside, path.join(runs, ".gate"));
  assert.equal(gate(linked, "acme", Date.now()), null);

  const inside = path.join(scratch, "inside");
  const place = path.join(inside, ".digline", "acme", "runs", ".gate");
  fs.mkdirSync(place, { recursive: true });
  fs.symlinkSync(path.join(outside, "1-k.json"), path.join(place, "1-k.json"));
  assert.equal(gate(inside, "acme", Date.now()), null);
  fs.writeFileSync(path.join(place, "2-k.json"), marker, "utf8");
  assert.deepEqual(gate(inside, "acme", Date.now()), ["gate", "k"]);
});

test("every tenant name is read as Python reads it", () => {
  const names = parsed("names.json");
  assert.ok(names.length > 10);
  for (const each of names) {
    const said = each.refusal ?? null;
    assert.equal(isName(each.name), said === null, each.name);
    if (said !== null) {
      assert.equal(refusal(each.name), said, each.name);
      if (each.name !== "") {
        assert.throws(
          () => DiglineRecorder.development(".", each.name, "app"),
          (refused) => refused instanceof StartError && refused.message === said,
          each.name,
        );
      }
    }
  }
});

test("the layout is digline's", () => {
  assert.equal(GITIGNORE, read("layout/gitignore"));
  assert.equal(GITATTRIBUTES, read("layout/gitattributes"));
});
