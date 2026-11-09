// The stand-in docs/stories/node.md was run against: OpenAI's Chat
// Completions, Anthropic's Messages, streamed or not, and Bedrock's Converse
// and ConverseStream, on 127.0.0.1. The application's answers, the judge's
// scores and every token count on that page are this file's. Nothing here
// calls a provider.
//
// HTTP/1.1 for OpenAI and Anthropic, and HTTP/2 in cleartext for Bedrock, on
// the next port: what the Bedrock client's default handler speaks.
//
//   node test/stand-in.mjs 18960    # 18960 for the two, 18961 for Bedrock
//
// The story's test, test/story.test.mjs, runs the page's lines against it.

import http from "node:http";
import http2 from "node:http2";
import { fileURLToPath } from "node:url";

import { crc32 } from "../digline/eventstream.mjs";

/** The ticket's category, by a word in it: "other" where none is found. */
function category(text) {
  const words = text.toLowerCase();
  if (words.includes("refund")) {
    return "refund";
  }
  if (words.includes("deliver") || words.includes("late") || words.includes("arrive")) {
    return "delivery";
  }
  return "other";
}

function read(request) {
  return new Promise((resolve) => {
    const chunks = [];
    request.on("data", (chunk) => chunks.push(chunk));
    request.on("end", () => resolve(Buffer.concat(chunks).toString("utf8")));
  });
}

function json(response, value) {
  response.writeHead(200, { "content-type": "application/json" });
  response.end(JSON.stringify(value));
}

async function openaiAndAnthropic(request, response) {
  const sent = JSON.parse((await read(request)) || "{}");
  const where = request.url.split("?")[0];
  if (where.endsWith("/chat/completions")) {
    const system = sent.messages.find((m) => m.role === "system")?.content ?? "";
    const user = sent.messages.filter((m) => m.role === "user").at(-1)?.content ?? "";
    let content;
    if (system.includes('"score"')) {
      // The judge: an answer of "other" scores 0, any other 1.
      const low = user.includes('"other"');
      content = JSON.stringify({
        score: low ? 0.0 : 1.0,
        reason: low ? "The category does not fit the ticket." : "The category fits the ticket.",
      });
    } else if (system.includes("subject")) {
      content = `Re: ${user.split(" ").slice(0, 4).join(" ")}`;
    } else {
      content = `Thank you for writing. We have your message about: ${user}`;
    }
    return json(response, {
      id: "chatcmpl-stand-in",
      object: "chat.completion",
      created: 1762430000,
      model: sent.model,
      choices: [{ index: 0, message: { role: "assistant", content, refusal: null }, finish_reason: "stop", logprobs: null }],
      usage: { prompt_tokens: 21, completion_tokens: 6, total_tokens: 27 },
    });
  }
  if (where.endsWith("/v1/messages")) {
    const words = ["Customer ", "asks: ", String(sent.messages.at(-1).content).slice(0, 40)];
    if (!sent.stream) {
      return json(response, {
        id: "msg_stand_in",
        type: "message",
        role: "assistant",
        model: sent.model,
        content: [{ type: "text", text: words.join("") }],
        stop_reason: "end_turn",
        stop_sequence: null,
        usage: { input_tokens: 18, output_tokens: 7 },
      });
    }
    response.writeHead(200, { "content-type": "text/event-stream" });
    const events = [
      {
        type: "message_start",
        message: {
          id: "msg_stand_in",
          type: "message",
          role: "assistant",
          model: sent.model,
          content: [],
          stop_reason: null,
          stop_sequence: null,
          usage: { input_tokens: 18, output_tokens: 1 },
        },
      },
      { type: "content_block_start", index: 0, content_block: { type: "text", text: "" } },
      ...words.map((text) => ({ type: "content_block_delta", index: 0, delta: { type: "text_delta", text } })),
      { type: "content_block_stop", index: 0 },
      { type: "message_delta", delta: { stop_reason: "end_turn", stop_sequence: null }, usage: { output_tokens: 7 } },
      { type: "message_stop" },
    ];
    for (const event of events) {
      response.write(`event: ${event.type}\ndata: ${JSON.stringify(event)}\n\n`);
    }
    response.end();
    return;
  }
  response.writeHead(404);
  response.end();
}

/** A header of AWS's event stream whose value is a string, type 7. */
function header(name, value) {
  const key = Buffer.from(name, "utf8");
  const text = Buffer.from(value, "utf8");
  const out = Buffer.alloc(1 + key.length + 1 + 2 + text.length);
  out[0] = key.length;
  key.copy(out, 1);
  out[1 + key.length] = 7;
  out.writeUInt16BE(text.length, 2 + key.length);
  text.copy(out, 4 + key.length);
  return out;
}

/** One event of AWS's event stream, framed with its two CRC-32s. */
function frame(type, payload) {
  const headers = Buffer.concat([
    header(":event-type", type),
    header(":content-type", "application/json"),
    header(":message-type", "event"),
  ]);
  const data = Buffer.from(JSON.stringify(payload), "utf8");
  const prelude = Buffer.alloc(12);
  prelude.writeUInt32BE(12 + headers.length + data.length + 4, 0);
  prelude.writeUInt32BE(headers.length, 4);
  prelude.writeUInt32BE(crc32(prelude.subarray(0, 8)), 8);
  const message = Buffer.concat([prelude, headers, data]);
  const trailer = Buffer.alloc(4);
  trailer.writeUInt32BE(crc32(message), 0);
  return Buffer.concat([message, trailer]);
}

async function bedrock(request, response) {
  const sent = JSON.parse((await read(request)) || "{}");
  const where = decodeURIComponent(request.url.split("?")[0]);
  const usage = { inputTokens: 40, outputTokens: 9, totalTokens: 49 };
  const first = sent.messages[0].content.find((block) => block.text !== undefined)?.text ?? "";
  if (where.endsWith("/converse")) {
    // A ticket that names an order asks for lookup_order once, then answers.
    const answered = sent.messages.at(-1).content.some((block) => block.toolResult !== undefined);
    const order = first.match(/order (\d+)/);
    if (order && !answered) {
      return json(response, {
        output: {
          message: {
            role: "assistant",
            content: [{ toolUse: { toolUseId: "tooluse_1", name: "lookup_order", input: { order: order[1] } } }],
          },
        },
        stopReason: "tool_use",
        usage,
        metrics: { latencyMs: 210 },
      });
    }
    return json(response, {
      output: { message: { role: "assistant", content: [{ text: JSON.stringify({ category: category(first) }) }] } },
      stopReason: "end_turn",
      usage,
      metrics: { latencyMs: 180 },
    });
  }
  if (where.endsWith("/converse-stream")) {
    const parts = ["We are sorry ", "about ", first.toLowerCase().replace(/[.?!]$/, ""), "."];
    response.writeHead(200, { "content-type": "application/vnd.amazon.eventstream" });
    response.end(
      Buffer.concat([
        frame("messageStart", { role: "assistant" }),
        ...parts.map((text) => frame("contentBlockDelta", { contentBlockIndex: 0, delta: { text } })),
        frame("contentBlockStop", { contentBlockIndex: 0 }),
        frame("messageStop", { stopReason: "end_turn" }),
        frame("metadata", { usage, metrics: { latencyMs: 230 } }),
      ]),
    );
    return;
  }
  response.writeHead(404);
  response.end();
}

/**
 * The stand-in, on `port` and `port + 1`, or on two free ports where `port`
 * is 0. Gives `{url, bedrockUrl, close}`.
 */
export async function standIn(port = 0) {
  const plain = http.createServer(openaiAndAnthropic);
  const h2 = http2.createServer(bedrock);
  await new Promise((resolve) => plain.listen(port, "127.0.0.1", resolve));
  await new Promise((resolve) => h2.listen(port === 0 ? 0 : port + 1, "127.0.0.1", resolve));
  const sessions = new Set();
  h2.on("session", (session) => sessions.add(session));
  return {
    url: `http://127.0.0.1:${plain.address().port}`,
    bedrockUrl: `http://127.0.0.1:${h2.address().port}`,
    close: async () => {
      plain.closeAllConnections();
      for (const session of sessions) {
        session.destroy();
      }
      await Promise.all([new Promise((r) => plain.close(r)), new Promise((r) => h2.close(r))]);
    },
  };
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const found = await standIn(Number(process.argv[2] ?? 18960));
  console.log(`stand-in: OpenAI and Anthropic on ${found.url}, Bedrock on ${found.bedrockUrl}`);
}
