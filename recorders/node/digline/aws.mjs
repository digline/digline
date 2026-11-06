/*
 * digline's recorder for Node: the hook for the AWS SDK for JavaScript v3,
 * for Bedrock's Converse, and InvokeModel with an Anthropic model, whose body
 * is Anthropic's Messages.
 *
 * RECORDING_VERSION 1, written to the contract as it stood on 2026-11-06:
 * https://github.com/digline/digline/blob/main/docs/recording-format.md
 *
 * Licensed as digline is: Apache-2.0.
 */

import { Readable } from "node:stream";

import * as messages from "./messages.mjs";
import {
  Call,
  ToolCall,
  Usage,
  asObject,
  clock,
  compact,
  finishOf,
  isObject,
  name,
  object,
  parse,
  rounded,
  textOf,
  truthy,
} from "./recorder.mjs";

/**
 * A plugin for a Bedrock runtime client that records its Converse calls,
 * and its InvokeModel calls with an Anthropic model, through a
 * `DiglineRecorder`:
 *
 *     const bedrock = new BedrockRuntimeClient({});
 *     bedrock.middlewareStack.use(diglineAws(recorder));
 *
 * It sits after the SDK's deserializer, so it reads the reply's bytes before
 * the SDK does and hands the SDK the same bytes. A reply is read only where
 * its status is 2xx: a retry after an error is one call, recorded once.
 * ConverseStream and InvokeModelWithResponseStream pass unrecorded, and are
 * counted *stream not recorded*. InvokeModel with another family is counted
 * by its reason and said once a family on standard error.
 *
 * It never fails the call: a request or a reply it cannot read is counted,
 * and the reply reaches the SDK as the server sent it.
 */
export function diglineAws(recorder) {
  return {
    applyToStack(stack) {
      stack.addRelativeTo(middleware(recorder), {
        relation: "after",
        toMiddleware: "deserializerMiddleware",
        name: "diglineRecorder",
        override: true,
      });
    },
  };
}

/** `stopReason` in digline's vocabulary. */
const FINISH = {
  end_turn: "stop",
  stop_sequence: "stop",
  max_tokens: "length",
  model_context_window_exceeded: "length",
  tool_use: "tool_use",
  guardrail_intervened: "filtered",
  content_filtered: "filtered",
  malformed_model_output: "other",
  malformed_tool_use: "other",
};

/** The request's keys that are neither the case nor the setup. */
const NOT_SETUP = new Set(["messages", "requestMetadata"]);

/** The operations read, by the command's name, and InvokeModel's name in digline's words. */
const READ = { ConverseCommand: null, InvokeModelCommand: "invoke_model" };

/** The operations that stream: passed, and counted, until their reading lands. */
const STREAMED = new Set(["ConverseStreamCommand", "InvokeModelWithResponseStreamCommand"]);

/**
 * A cross-region inference profile's prefix, before the vendor's name: taken
 * off before the family is read, as digline's Bedrock map takes it.
 */
const REGION_PREFIXES = ["us.", "eu.", "apac.", "global."];

/** The families already said on standard error in this process. */
const SAID = new Set();

function middleware(recorder) {
  return (next, context) => async (args) => {
    let watched = null;
    try {
      watched = watch(recorder, context?.commandName, args.request);
    } catch {
      watched = null;
    }
    const out = await next(args);
    if (watched === null) {
      return out;
    }
    return watched.reply(out);
  };
}

/** A call this hook reads, or `null` for one it lets through untouched. */
function watch(recorder, command, request) {
  if (!recorder.on()) {
    return null;
  }
  if (STREAMED.has(command)) {
    recorder.miss("stream not recorded");
    return null;
  }
  if (!Object.hasOwn(READ, command)) {
    return null;
  }
  const at = recorder.capture();
  let sent = null;
  try {
    const text = textOf(request.body);
    if (text === null) {
      throw new TypeError("a body that is not text");
    }
    sent = object({ modelId: modelIdOf(request.path) });
    Object.assign(sent, asObject(parse(text)));
  } catch {
    recorder.miss("not JSON", at);
    return null;
  }
  return new Watched(recorder, READ[command], sent, at);
}

/** One call under way: where it was made, when, and what was sent. */
class Watched {
  constructor(recorder, invoke, sent, at) {
    this.recorder = recorder;
    this.invoke = invoke;
    this.sent = sent;
    this.at = at;
    this.started = clock();
  }

  async reply(out) {
    const response = out?.response;
    const status = response?.statusCode;
    if (typeof status !== "number" || status < 200 || status > 299) {
      return out;
    }
    if (this.invoke !== null) {
      const said = refusal(this.invoke, this.sent.modelId);
      if (said !== null) {
        // Another family's body is not read: counted by its reason, and said
        // once a family.
        if (!SAID.has(said[1])) {
          SAID.add(said[1]);
          process.stderr.write(`digline recorder: ${said[2]}\n`);
        }
        this.recorder.miss(said[0], this.at);
        return out;
      }
    }
    // The bytes are read here, whole, and handed on as they came: a failure
    // to read them is the call's, as it would be without the hook.
    const bytes = await bodyOf(response.body);
    response.body = Readable.from([bytes]);
    try {
      const elapsed = clock() - this.started;
      const reply = asObject(parse(bytes.toString("utf8")));
      const read = this.invoke !== null ? messages.call(this.sent, reply, elapsed) : call(this.sent, reply, elapsed);
      this.recorder.recordAt(read, this.at);
    } catch {
      this.recorder.miss("map", this.at);
    }
    return out;
  }
}

async function bodyOf(body) {
  if (body === undefined || body === null) {
    return Buffer.alloc(0);
  }
  const text = textOf(body);
  if (text !== null) {
    return Buffer.from(text, "utf8");
  }
  const chunks = [];
  for await (const chunk of body) {
    chunks.push(typeof chunk === "string" ? Buffer.from(chunk, "utf8") : Buffer.from(chunk));
  }
  return Buffer.concat(chunks);
}

/** The model's id, from `/model/<id>/converse`, percent-decoded and nothing else. */
export function modelIdOf(where) {
  const parts = String(where).split("/");
  for (let i = 0; i + 1 < parts.length; i++) {
    if (parts[i] === "model") {
      return decodeURIComponent(parts[i + 1]);
    }
  }
  throw new TypeError("no model in the path");
}

/**
 * The vendor a model id names, and what its body is to the recorder:
 * `messages`, `embeddings` or `other`, as digline's `family_of` reads it. An
 * ARN is read by its last segment.
 */
export function familyOf(modelId) {
  let found = modelId.slice(modelId.lastIndexOf("/") + 1);
  for (const prefix of REGION_PREFIXES) {
    if (found.startsWith(prefix)) {
      found = found.slice(prefix.length);
      break;
    }
  }
  const dot = found.indexOf(".");
  const vendor = dot < 0 ? found : found.slice(0, dot);
  const family = found.includes("embed") ? "embeddings" : vendor === "anthropic" ? "messages" : "other";
  return [vendor, family];
}

/**
 * Why InvokeModel on this model is not recorded, as the reason it is counted
 * as, the family it is said once for and the sentence, or `null` for
 * Anthropic's Messages. The words are digline's.
 */
export function refusal(method, modelId) {
  const [vendor, family] = familyOf(modelId ?? "");
  if (family === "messages") {
    return null;
  }
  if (family === "embeddings") {
    return [
      "embeddings not recorded",
      `bedrock embeddings ${vendor}`,
      `${method} on ${modelId}: embeddings are not recorded`,
    ];
  }
  return ["model family not recorded", `bedrock ${vendor}`, `${method} on ${modelId}: this model family is not recorded`];
}

/** One Converse call, whole: the request split, and the reply read. */
export function call(request, reply, latencyMs) {
  const caseCompartment = object({ messages: request.messages ?? null });
  const setup = object();
  for (const key of Object.keys(request)) {
    if (!NOT_SETUP.has(key)) {
      setup[key] = request[key];
    }
  }
  const content = blocks(reply);
  let text = "";
  for (const block of content) {
    if (isObject(block) && "text" in block) {
      text += typeof block.text === "string" ? block.text : String(block.text);
    }
  }
  const stop = reply.stopReason;
  return new Call(
    caseCompartment,
    setup,
    text,
    latencyMs,
    usage(reply.usage),
    finishOf(truthy(stop) ? String(stop) : null, FINISH),
    toolCalls(content),
  );
}

function blocks(reply) {
  if (!isObject(reply.output)) {
    throw new TypeError("the reply carries no output");
  }
  if (!isObject(reply.output.message)) {
    throw new TypeError("the reply carries no output.message");
  }
  const content = reply.output.message.content;
  return Array.isArray(content) ? [...content] : [];
}

/** The counts, with the cache's beside the input, or `null`. */
export function usage(raw) {
  if (!isObject(raw)) {
    return null;
  }
  const details = raw.cacheDetails;
  if (truthy(details)) {
    if (!Array.isArray(details)) {
      throw new TypeError("usage.cacheDetails is not a list of cache writes");
    }
    for (const detail of details) {
      if (!isObject(detail)) {
        throw new TypeError("usage.cacheDetails holds an entry that is not a record");
      }
      tokens(detail.inputTokens);
    }
  }
  if (raw.inputTokens === undefined || raw.inputTokens === null || raw.outputTokens === undefined || raw.outputTokens === null) {
    return null;
  }
  return new Usage(
    tokens(raw.inputTokens),
    tokens(raw.outputTokens),
    tokens(raw.cacheReadInputTokens),
    tokens(raw.cacheWriteInputTokens),
    null,
  );
}

/** A token count, 0 where absent, refused where it is not a number. */
function tokens(value) {
  if (value === undefined || value === null || value === false) {
    return 0n;
  }
  if (typeof value === "bigint") {
    return value;
  }
  if (typeof value === "number" && Number.isFinite(value)) {
    return BigInt(Math.trunc(value));
  }
  throw new TypeError("a usage count that is not a token count");
}

/**
 * The calls in the reply: a `toolUse` the application runs, so
 * `not_reported`; a server tool's with its `toolResult` in the reply, an
 * error by its text, a success whose payload is not recorded. Never `null`.
 */
export function toolCalls(content) {
  const outcomes = new Map();
  for (const block of content) {
    if (isObject(block) && isObject(block.toolResult)) {
      const found = asObject(block.toolResult);
      outcomes.set(String(found.toolUseId ?? ""), found);
    }
  }
  const calls = [];
  for (const block of content) {
    if (!isObject(block) || !("toolUse" in block)) {
      continue;
    }
    const use = asObject(block.toolUse);
    const tool = name(use.name);
    const args = argumentsOf(use.input);
    const outcome = use.type === "server_tool_use" ? outcomes.get(String(use.toolUseId ?? "")) : undefined;
    if (outcome === undefined) {
      calls.push(ToolCall.asked(tool, args));
    } else if (outcome.status === "error") {
      const said = errorText(outcome);
      calls.push(new ToolCall(tool, args, "error", said, said === null ? "not_reported" : null));
    } else {
      calls.push(new ToolCall(tool, args, outcome.status === "success" ? "success" : "not_reported", null, "not_recorded"));
    }
  }
  return calls;
}

function argumentsOf(value) {
  if (value === undefined || value === null || isObject(value)) {
    return value ?? null;
  }
  return compact(rounded(value));
}

function errorText(outcome) {
  const parts = [];
  for (const item of Array.isArray(outcome.content) ? outcome.content : []) {
    if (!isObject(item)) {
      continue;
    }
    if (typeof item.text === "string") {
      parts.push(item.text);
    } else if ("json" in item) {
      parts.push(compact(rounded(item.json)));
    }
  }
  return parts.length === 0 ? null : parts.join("\n");
}
