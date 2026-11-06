// A fake provider on 127.0.0.1 for the hooks' tests: OpenAI's Chat
// Completions, Anthropic's Messages and Bedrock's runtime, each answering
// with the reply of a wire fixture in recorders/fixtures/wire/. Nothing here
// calls a provider.

import * as fs from "node:fs";
import http from "node:http";
import http2 from "node:http2";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import * as zlib from "node:zlib";

const WIRE = path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "..", "fixtures", "wire");

/** A wire fixture, as JSON. */
export function wire(name) {
  return JSON.parse(fs.readFileSync(path.join(WIRE, `${name}.json`), "utf8"));
}

/** One frame of an AWS event stream, with its two checksums. */
function frame(type, payload) {
  const headers = [];
  for (const [key, value] of [
    [":message-type", "event"],
    [":event-type", type],
    [":content-type", "application/json"],
  ]) {
    const nameBytes = Buffer.from(key, "utf8");
    const valueBytes = Buffer.from(value, "utf8");
    const length = Buffer.alloc(2);
    length.writeUInt16BE(valueBytes.length);
    headers.push(Buffer.from([nameBytes.length]), nameBytes, Buffer.from([7]), length, valueBytes);
  }
  const headerBytes = Buffer.concat(headers);
  const body = Buffer.from(JSON.stringify(payload), "utf8");
  const total = 12 + headerBytes.length + body.length + 4;
  const prelude = Buffer.alloc(8);
  prelude.writeUInt32BE(total, 0);
  prelude.writeUInt32BE(headerBytes.length, 4);
  const preludeCrc = Buffer.alloc(4);
  preludeCrc.writeUInt32BE(zlib.crc32(prelude));
  const message = Buffer.concat([prelude, preludeCrc, headerBytes, body]);
  const messageCrc = Buffer.alloc(4);
  messageCrc.writeUInt32BE(zlib.crc32(message));
  return Buffer.concat([message, messageCrc]);
}

/**
 * The provider. `plan` holds the statuses to answer before the fixture's
 * reply, one per request, so a test can make the SDK retry or fail; `asked`
 * keeps each request's path and body; `hold` makes a stream send its first
 * event and wait until the client goes.
 */
export async function provider(options = {}) {
  const state = { plan: [], asked: [], hold: false };
  // HTTP/2 in cleartext, with prior knowledge, where asked: what the Bedrock
  // client's default handler speaks.
  const create = options.http2 ? http2.createServer : http.createServer;
  const server = create((request, response) => {
    const chunks = [];
    request.on("data", (chunk) => chunks.push(chunk));
    request.on("end", () => {
      const body = Buffer.concat(chunks).toString("utf8");
      const where = request.url.split("?")[0];
      state.asked.push({ path: where, body });
      const status = state.plan.shift();
      if (status !== undefined && status !== 200) {
        response.writeHead(status, { "content-type": "application/json" });
        response.end(JSON.stringify({ error: { message: "planned", type: "planned" }, message: "planned" }));
        return;
      }
      const sent = body === "" ? {} : JSON.parse(body);
      if (where.endsWith("/chat/completions")) {
        if (sent.stream) {
          return sse(response, wire("openai-stream").events, (event) => `data: ${JSON.stringify(event)}\n\n`, "data: [DONE]\n\n", state);
        }
        return json(response, wire("openai-single").reply);
      }
      if (where.endsWith("/v1/messages")) {
        if (sent.stream) {
          return sse(response, wire("anthropic-stream").events, (event) => `event: ${event.type}\ndata: ${JSON.stringify(event)}\n\n`, "", state);
        }
        return json(response, wire("anthropic-single").reply);
      }
      if (where.endsWith("/converse")) {
        return json(response, wire("bedrock-single").reply);
      }
      if (where.endsWith("/invoke")) {
        return json(response, where.includes("anthropic") ? wire("bedrock-invoke").reply : { outputText: "titan" });
      }
      if (where.endsWith("/converse-stream")) {
        response.writeHead(200, { "content-type": "application/vnd.amazon.eventstream" });
        for (const event of wire("bedrock-stream").events) {
          const [type] = Object.keys(event);
          response.write(frame(type, event[type]));
        }
        response.end();
        return;
      }
      response.writeHead(404);
      response.end();
    });
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  state.url = `http://127.0.0.1:${server.address().port}`;
  const sessions = new Set();
  server.on("session", (session) => sessions.add(session));
  state.close = () => {
    server.closeAllConnections?.();
    for (const session of sessions) {
      session.destroy();
    }
    return new Promise((resolve) => server.close(resolve));
  };
  return state;
}

function json(response, reply) {
  response.writeHead(200, { "content-type": "application/json" });
  response.end(JSON.stringify(reply));
}

function sse(response, events, written, closing, state) {
  response.writeHead(200, { "content-type": "text/event-stream" });
  if (state.hold) {
    response.write(written(events[0]));
    return;
  }
  for (const event of events) {
    response.write(written(event));
  }
  response.end(closing);
}
