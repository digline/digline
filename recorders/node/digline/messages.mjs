/*
 * digline's recorder for Node: Anthropic's Messages API, read as JSON, for the
 * hooks that carry it: fetch.mjs, for a direct call, and aws.mjs, for
 * Bedrock's InvokeModel with an Anthropic model.
 *
 * RECORDING_VERSION 1, written to the contract as it stood on 2026-11-06:
 * https://github.com/digline/digline/blob/main/docs/recording-format.md
 *
 * Licensed as digline is: Apache-2.0.
 */

import {
  Call,
  ToolCall,
  Usage,
  asObject,
  count,
  finishOf,
  isObject,
  name,
  object,
  parse,
  truthy,
} from "./recorder.mjs";

/** The request's keys that are neither the case nor the setup. */
const NOT_SETUP = new Set(["messages", "stream", "extra_headers", "extra_query", "timeout", "metadata"]);

/** `stop_reason` in digline's vocabulary. */
const FINISH = {
  end_turn: "stop",
  stop_sequence: "stop",
  max_tokens: "length",
  model_context_window_exceeded: "length",
  tool_use: "tool_use",
  refusal: "filtered",
  pause_turn: "other",
};

/** The blocks whose input arrives as JSON in pieces. */
const TRACKS_TOOL_INPUT = new Set(["tool_use", "server_tool_use"]);

/** One call, whole: the request split, and the reply read. */
export function call(request, reply, latencyMs) {
  const caseCompartment = object({ messages: request.messages ?? null });
  const setup = object();
  for (const key of Object.keys(request)) {
    if (!NOT_SETUP.has(key)) {
      setup[key] = request[key];
    }
  }
  if (!Array.isArray(reply.content)) {
    throw new TypeError("the reply carries no content");
  }
  const content = reply.content.map(asObject);
  let text = "";
  for (const block of content) {
    if (block.type === "text") {
      text += String(block.text);
    }
  }
  return new Call(
    caseCompartment,
    setup,
    text,
    latencyMs,
    usage(reply.usage),
    finishOf(reply.stop_reason, FINISH),
    toolCalls(content),
  );
}

/** One call, streamed: its events folded into the message the SDK would build. */
export function streamed(request, events, latencyMs) {
  let snapshot = null;
  const content = [];
  const inputs = new Map();
  for (const raw of events) {
    const event = asObject(raw);
    const type = event.type;
    if (snapshot === null) {
      if (type !== "message_start") {
        throw new TypeError("an event before message_start");
      }
      snapshot = asObject(event.message);
      if (Array.isArray(snapshot.content)) {
        content.push(...snapshot.content.map(asObject));
      }
      continue;
    }
    if (type === "content_block_start") {
      content.push(asObject(event.content_block));
    } else if (type === "content_block_delta") {
      const at = Number(event.index);
      const block = content[at];
      const delta = asObject(event.delta);
      if (delta.type === "text_delta" && block.type === "text") {
        block.text = String(block.text) + String(delta.text);
      } else if (delta.type === "input_json_delta" && TRACKS_TOOL_INPUT.has(block.type)) {
        inputs.set(at, (inputs.get(at) ?? "") + delta.partial_json);
      }
    } else if (type === "message_delta") {
      const delta = asObject(event.delta);
      snapshot.stop_reason = delta.stop_reason ?? null;
      const held = isObject(snapshot.usage) ? asObject(snapshot.usage) : object();
      const more = asObject(event.usage);
      held.output_tokens = more.output_tokens ?? null;
      for (const key of [
        "input_tokens",
        "cache_creation_input_tokens",
        "cache_read_input_tokens",
        "server_tool_use",
        "output_tokens_details",
      ]) {
        if (more[key] !== undefined && more[key] !== null) {
          held[key] = more[key];
        }
      }
      snapshot.usage = held;
    }
  }
  if (snapshot === null) {
    throw new TypeError("the stream ended with no message");
  }
  for (const [at, written] of inputs) {
    if (written.length > 0) {
      content[at].input = parse(written);
    }
  }
  snapshot.content = content;
  return call(request, snapshot, latencyMs);
}

/** The counts, with the cache's beside the input, or `null`. */
export function usage(raw) {
  if (!isObject(raw)) {
    return null;
  }
  const input = count(raw.input_tokens);
  const output = count(raw.output_tokens);
  if (input === null || output === null) {
    return null;
  }
  const read = count(raw.cache_read_input_tokens);
  const written = count(raw.cache_creation_input_tokens);
  const thinking = isObject(raw.output_tokens_details) ? count(raw.output_tokens_details.thinking_tokens) : null;
  return new Usage(input, output, read ?? 0n, written ?? 0n, thinking);
}

/**
 * The calls in the reply: a `tool_use` the application runs, so
 * `not_reported`; a `server_tool_use` with its result in the reply, an error
 * by its code or a success whose payload is not recorded. Never `null`: the
 * reply always says what the turn held.
 */
export function toolCalls(content) {
  const outcomes = new Map();
  for (const block of content) {
    if (String(block.type ?? "").endsWith("_tool_result")) {
      outcomes.set(String(block.tool_use_id ?? ""), block);
    }
  }
  const calls = [];
  for (const block of content) {
    if (block.type !== "tool_use" && block.type !== "server_tool_use") {
      continue;
    }
    const tool = name(block.name);
    const args = isObject(block.input) ? block.input : null;
    const outcome = block.type === "server_tool_use" ? outcomes.get(String(block.id ?? "")) : undefined;
    if (outcome === undefined) {
      calls.push(ToolCall.asked(tool, args));
      continue;
    }
    let code = null;
    const said = outcome.content;
    if (isObject(said) && typeof said.type === "string" && said.type.includes("_error")) {
      code = truthy(said.error_code) ? String(said.error_code) : said.type;
    }
    calls.push(
      code === null
        ? new ToolCall(tool, args, "success", null, "not_recorded")
        : new ToolCall(tool, args, "error", code, null),
    );
  }
  return calls;
}
