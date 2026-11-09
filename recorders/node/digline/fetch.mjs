/*
 * digline's recorder for Node: the hook for the `fetch` the OpenAI and
 * Anthropic SDKs take as an option, for Chat Completions and Messages.
 *
 * RECORDING_VERSION 1, written to the contract as it stood on 2026-11-06:
 * https://github.com/digline/digline/blob/main/docs/recording-format.md
 *
 * Licensed as digline is: Apache-2.0.
 */

import * as messages from "./messages.mjs";
import {
  Call,
  ToolCall,
  Usage,
  asObject,
  clock,
  count,
  events,
  finishOf,
  isObject,
  name,
  object,
  parse,
  textOf,
  truthy,
} from "./recorder.mjs";

/**
 * A `fetch` that records the Chat Completions and Messages calls made
 * through it, whole or streamed, through a `DiglineRecorder`:
 *
 *     const openai = new OpenAI({ fetch: diglineFetch(recorder) });
 *     const anthropic = new Anthropic({ fetch: diglineFetch(recorder) });
 *
 * A request is read as digline's maps read it, and a reply only where its
 * status is 2xx: a retry the SDK makes after an error is one call, recorded
 * once. The hook sees each attempt, and counts each one the provider refuses,
 * 4xx or 5xx, as `provider error <status>`; the Python wrapper sees the
 * whole call and counts only the refusal the SDK raises. A stream is recorded when the application has read it to its end,
 * and one it stops reading before is counted *stream abandoned*. Any other
 * request goes through untouched. `options.fetch` is the `fetch` it calls,
 * the global one where none is given.
 *
 * It never fails the call: a request or a reply it cannot read is counted,
 * and the reply reaches the application as the server sent it.
 */
export function diglineFetch(recorder, options = {}) {
  return async function fetch(input, init) {
    const inner = options.fetch ?? globalThis.fetch;
    let watched = null;
    try {
      watched = watch(recorder, input, init);
    } catch {
      watched = null;
    }
    if (watched === null) {
      return inner(input, init);
    }
    const response = await inner(input, init);
    try {
      return watched.reply(response);
    } catch {
      return response;
    }
  };
}

/** The route a request takes, `openai` or `anthropic`, or `null` for one let through. */
function routeOf(input, init) {
  const method = init?.method ?? (input instanceof Request ? input.method : "GET");
  if (String(method).toUpperCase() !== "POST") {
    return null;
  }
  const where = typeof input === "string" ? input : input instanceof URL ? input.href : input?.url;
  const pathname = new URL(String(where)).pathname.replace(/\/+$/, "");
  if (pathname.endsWith("/chat/completions")) {
    return "openai";
  }
  if (pathname.endsWith("/v1/messages")) {
    return "anthropic";
  }
  return null;
}

/** A call this hook reads, or `null` for one it lets through untouched. */
function watch(recorder, input, init) {
  if (!recorder.on()) {
    return null;
  }
  const route = routeOf(input, init);
  if (route === null || init?.body === undefined || init.body === null) {
    return null;
  }
  const at = recorder.capture();
  let sent = null;
  try {
    const text = textOf(init.body);
    if (text === null) {
      throw new TypeError("a body that is not text");
    }
    sent = asObject(parse(text));
  } catch {
    recorder.miss("not JSON", at);
  }
  return new Watched(recorder, route, sent, at);
}

/** One call under way: the request sent, and when. */
class Watched {
  constructor(recorder, route, sent, at) {
    this.recorder = recorder;
    this.route = route;
    this.sent = sent;
    this.at = at;
    this.started = clock();
  }

  reply(response) {
    if (this.sent !== null) {
      this.recorder.refused(response.status, this.at);
    }
    if (this.sent === null || response.status < 200 || response.status > 299 || response.body === null) {
      return response;
    }
    const type = response.headers.get("content-type") ?? "";
    if (type.includes("text/event-stream")) {
      return this.#streamed(response);
    }
    response
      .clone()
      .text()
      .then(
        (text) => this.#ended(text, true, false),
        () => this.recorder.miss("map", this.at),
      );
    return response;
  }

  /**
   * The reply, with its body replaced by one that passes on what it reads
   * and keeps a copy: only what the application reads is read, so a stream
   * it stops reading is not read to its end on its behalf.
   */
  #streamed(response) {
    const reader = response.body.getReader();
    const kept = [];
    let done = false;
    const end = (whole) => {
      if (!done) {
        done = true;
        this.#ended(Buffer.concat(kept).toString("utf8"), whole, true);
      }
    };
    const body = new ReadableStream({
      async pull(controller) {
        let read;
        try {
          read = await reader.read();
        } catch (failed) {
          end(false);
          controller.error(failed);
          return;
        }
        if (read.done) {
          end(true);
          controller.close();
          return;
        }
        kept.push(Buffer.from(read.value));
        controller.enqueue(read.value);
      },
      cancel(reason) {
        end(false);
        return reader.cancel(reason);
      },
    });
    return new Response(body, { status: response.status, statusText: response.statusText, headers: response.headers });
  }

  /**
   * The body, as the application read it: at its end, or when it stopped
   * reading. A stream stopped before its end was abandoned, unless what was
   * read already carries the end: OpenAI's `[DONE]`, Anthropic's
   * `message_stop`, where each SDK stops reading.
   */
  #ended(text, whole, streamed) {
    try {
      const elapsed = clock() - this.started;
      if (!streamed) {
        const reply = asObject(parse(text));
        const read =
          this.route === "openai" ? chat(this.sent, reply, elapsed) : messages.call(this.sent, reply, elapsed);
        this.recorder.recordAt(read, this.at);
        return;
      }
      const found = events(text);
      const finished =
        whole ||
        (this.route === "openai"
          ? /(^|\n)data: ?\[DONE\]/.test(text.replaceAll("\r\n", "\n"))
          : found.some((event) => isObject(event) && event.type === "message_stop"));
      if (!finished) {
        this.recorder.miss("stream abandoned", this.at);
        return;
      }
      const read =
        this.route === "openai"
          ? chatStreamed(this.sent, found, elapsed)
          : messages.streamed(this.sent, found, elapsed);
      this.recorder.recordAt(read, this.at);
    } catch {
      this.recorder.miss("map", this.at);
    }
  }
}

// ------------------------------------------------------------------ Chat Completions

/** The request's keys that are neither the case nor the setup. */
const NOT_SETUP = new Set([
  "messages",
  "stream",
  "stream_options",
  "extra_headers",
  "extra_query",
  "timeout",
  "user",
  "metadata",
  "safety_identifier",
  "prompt_cache_key",
  "store",
]);

/** The roles of the leading messages that are the setup's `system`. */
const INSTRUCTION_ROLES = new Set(["system", "developer"]);

/** `finish_reason` in digline's vocabulary. */
const FINISH = {
  stop: "stop",
  length: "length",
  tool_calls: "tool_use",
  function_call: "tool_use",
  content_filter: "filtered",
};

/** One call, whole: the request split, and the reply read. */
export function chat(request, reply, latencyMs) {
  const { caseCompartment, setup } = split(request);
  const choices = Array.isArray(reply.choices) ? reply.choices : [];
  if (choices.length === 0) {
    throw new TypeError("the provider returned no choices");
  }
  const choice = asObject(choices[0]);
  const message = isObject(choice.message) ? asObject(choice.message) : object();
  const finish = truthy(message.refusal) ? "filtered" : finishOf(choice.finish_reason, FINISH);
  const content = message.content;
  return new Call(
    caseCompartment,
    setup,
    truthy(content) ? String(content) : "",
    latencyMs,
    chatUsage(reply.usage),
    finish,
    chatToolCalls(message),
  );
}

/** One call, streamed: its chunks folded into the reply the SDK would build. */
export function chatStreamed(request, chunks, latencyMs) {
  let snapshot = null;
  for (const raw of chunks) {
    const chunk = asObject(raw);
    const deltas = Array.isArray(chunk.choices) ? chunk.choices : [];
    if (snapshot === null) {
      snapshot = asObject(chunk);
      const choices = [...deltas];
      for (const each of deltas) {
        const choice = asObject(each);
        choices[index(choice)] = firstChoice(choice);
      }
      snapshot.choices = choices;
      continue;
    }
    const choices = snapshot.choices;
    for (const each of deltas) {
      const choice = asObject(each);
      const at = index(choice);
      let held;
      if (at < choices.length) {
        held = asObject(choices[at]);
        held.message = accumulate(asObject(held.message), deltaOf(choice));
      } else {
        held = firstChoice(choice);
        choices.push(held);
      }
      if (truthy(choice.finish_reason)) {
        held.finish_reason = choice.finish_reason;
      }
      choices[Math.min(at, choices.length - 1)] = held;
    }
    snapshot.usage = chunk.usage ?? null;
  }
  if (snapshot === null) {
    throw new TypeError("the stream ended with no chunk");
  }
  return chat(request, snapshot, latencyMs);
}

function firstChoice(choice) {
  const held = asObject(choice);
  delete held.delta;
  held.message = accumulate(object(), deltaOf(choice));
  return held;
}

function deltaOf(choice) {
  return isObject(choice.delta) ? asObject(choice.delta) : object();
}

function index(entry) {
  if (typeof entry.index !== "bigint") {
    throw new TypeError("a list delta entry has no integer index");
  }
  return Number(entry.index);
}

function isScalar(item) {
  return typeof item === "string" || typeof item === "number" || typeof item === "bigint";
}

/** The SDK's `accumulate_delta`: strings and numbers add, objects merge, indexed lists merge by index. */
export function accumulate(held, delta) {
  const acc = asObject(held);
  for (const key of Object.keys(delta)) {
    const value = delta[key];
    if (acc[key] === undefined || acc[key] === null) {
      if (indexed(value)) {
        acc[key] = [];
      } else {
        acc[key] = value;
        continue;
      }
    }
    const held_ = acc[key];
    if (key === "index" || key === "type") {
      acc[key] = value;
      continue;
    }
    if (typeof held_ === "string" && typeof value === "string") {
      acc[key] = held_ + value;
    } else if (isNumeric(held_) && isNumeric(value)) {
      acc[key] =
        typeof held_ === "bigint" && typeof value === "bigint" ? held_ + value : Number(held_) + Number(value);
    } else if (isObject(held_) && isObject(value)) {
      acc[key] = accumulate(held_, value);
    } else if (Array.isArray(held_) && Array.isArray(value)) {
      const merged = [...held_];
      const scalars = merged.every(isScalar);
      if (scalars && (merged.length > 0 || !indexed(value))) {
        merged.push(...value);
      } else {
        for (const item of value) {
          const part = asObject(item);
          const at = index(part);
          if (at >= merged.length) {
            merged.splice(Math.min(at, merged.length), 0, part);
          } else {
            merged[at] = accumulate(asObject(merged[at]), part);
          }
        }
      }
      acc[key] = merged;
    } else {
      acc[key] = held_;
    }
  }
  return acc;
}

function isNumeric(value) {
  return typeof value === "bigint" || typeof value === "number";
}

function indexed(value) {
  return Array.isArray(value) && value.length > 0 && value.some((item) => isObject(item) && "index" in item);
}

/** The case and the setup, as digline's OpenAI map divides a request. */
function split(request) {
  const listed = Array.isArray(request.messages) ? [...request.messages] : [request.messages ?? null];
  let lead = 0;
  while (lead < listed.length && isObject(listed[lead]) && INSTRUCTION_ROLES.has(listed[lead].role)) {
    lead++;
  }
  const setup = object();
  for (const key of Object.keys(request)) {
    if (!NOT_SETUP.has(key)) {
      setup[key] = request[key];
    }
  }
  if (lead > 0) {
    setup.system = listed.slice(0, lead);
  }
  return { caseCompartment: object({ messages: listed.slice(lead) }), setup };
}

/** The counts, with the cached prompt tokens taken out of the input, or `null`. */
function chatUsage(raw) {
  if (!isObject(raw)) {
    return null;
  }
  const prompt = count(raw.prompt_tokens);
  const completion = count(raw.completion_tokens);
  if (prompt === null || completion === null) {
    return null;
  }
  const reasoning = isObject(raw.completion_tokens_details)
    ? count(raw.completion_tokens_details.reasoning_tokens)
    : null;
  const cached = isObject(raw.prompt_tokens_details) ? (count(raw.prompt_tokens_details.cached_tokens) ?? 0n) : 0n;
  const input = prompt - cached > 0n ? prompt - cached : 0n;
  return new Usage(input, completion, cached, 0n, reasoning);
}

/** The calls the model asked for: none reported is `null`, never an empty list. */
function chatToolCalls(message) {
  if (Array.isArray(message.tool_calls) && message.tool_calls.length > 0) {
    return message.tool_calls.map((each) => {
      const asked = asObject(each);
      if (asked.type === "custom") {
        const custom = isObject(asked.custom) ? asked.custom : object();
        return ToolCall.asked(name(custom.name), typeof custom.input === "string" ? custom.input : null);
      }
      const fn = isObject(asked.function) ? asked.function : object();
      return ToolCall.asked(name(fn.name), decoded(fn.arguments));
    });
  }
  if (isObject(message.function_call)) {
    return [ToolCall.asked(name(message.function_call.name), decoded(message.function_call.arguments))];
  }
  return null;
}

function decoded(text) {
  if (typeof text !== "string") {
    return null;
  }
  try {
    const found = parse(text);
    return isObject(found) ? found : text;
  } catch {
    return text;
  }
}
