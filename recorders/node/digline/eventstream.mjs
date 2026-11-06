/*
 * digline's recorder for Node: AWS's event stream, the framing Bedrock's
 * ConverseStream and InvokeModelWithResponseStream reply in, read with no
 * package. aws.mjs reads a stream's bytes through it once the application
 * has read them.
 *
 * Each message is a prelude, its total length and its headers' length, each
 * four bytes big-endian, and the prelude's CRC-32; the headers, each a name,
 * a type and a value; the payload; and the CRC-32 of everything before it.
 *
 * Licensed as digline is: Apache-2.0.
 */

import { object, parse } from "./recorder.mjs";

/**
 * A stream digline does not read as one: a checksum that does not match, a
 * header of no known type, a payload that is not JSON, or an exception the
 * stream carries after its 200. Counted *stream error*, as the proxy counts
 * the same bytes.
 */
export class StreamError extends Error {}

/** CRC-32, the polynomial zlib's and botocore's use, a table of 256 entries. */
const TABLE = (() => {
  const table = new Uint32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) {
      c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    }
    table[n] = c >>> 0;
  }
  return table;
})();

/** The CRC-32 of `bytes`, as an unsigned 32-bit number. */
export function crc32(bytes) {
  let c = 0xffffffff;
  for (let i = 0; i < bytes.length; i++) {
    c = TABLE[(c ^ bytes[i]) & 0xff] ^ (c >>> 8);
  }
  return (c ^ 0xffffffff) >>> 0;
}

/** The bytes of each header type's value that are not a string, by type: -1 for a length of its own. */
const WIDTH = { 0: 0, 1: 0, 2: 1, 3: 2, 4: 4, 5: 8, 6: -1, 8: 8, 9: 16 };

/** The type of a string header's value. */
const STRING = 7;

/** The prelude and its checksum, and the message's checksum. */
const PRELUDE = 12;
const TRAILER = 4;

/**
 * The events in `bytes`, each as the SDK hands it to the application,
 * `{type: payload}`, and whether the bytes end inside a message: `cut`. A
 * message the bytes do not hold whole is never read, and what precedes it
 * is. A checksum that does not match, a header of no known type or an
 * exception refuses the whole, with a `StreamError`.
 */
export function decode(bytes) {
  const events = [];
  let at = 0;
  while (at < bytes.length) {
    if (bytes.length - at < PRELUDE) {
      return { events, cut: true };
    }
    const total = bytes.readUInt32BE(at);
    const headersLength = bytes.readUInt32BE(at + 4);
    if (crc32(bytes.subarray(at, at + 8)) !== bytes.readUInt32BE(at + 8)) {
      throw new StreamError("an event's prelude does not check");
    }
    if (total < PRELUDE + headersLength + TRAILER) {
      throw new StreamError("an event shorter than its headers");
    }
    if (bytes.length - at < total) {
      return { events, cut: true };
    }
    const end = at + total;
    if (crc32(bytes.subarray(at, end - TRAILER)) !== bytes.readUInt32BE(end - TRAILER)) {
      throw new StreamError("an event's message does not check");
    }
    const payloadAt = at + PRELUDE + headersLength;
    const headers = headersOf(bytes.subarray(at + PRELUDE, payloadAt));
    if (headers[":message-type"] !== "event") {
      throw new StreamError(`the stream carried ${headers[":exception-type"] ?? "an exception"}`);
    }
    const payload = bytes.subarray(payloadAt, end - TRAILER);
    let found;
    try {
      found = payload.length === 0 ? object() : parse(payload.toString("utf8"));
    } catch {
      throw new StreamError("an event whose payload is not JSON");
    }
    events.push(object({ [String(headers[":event-type"])]: found }));
    at = end;
  }
  return { events, cut: false };
}

/** A message's headers: the string ones by name, every other one read past. */
function headersOf(bytes) {
  const headers = object();
  let at = 0;
  while (at < bytes.length) {
    const nameLength = bytes[at];
    const name = bytes.subarray(at + 1, at + 1 + nameLength).toString("utf8");
    at += 1 + nameLength;
    const type = bytes[at];
    at += 1;
    if (type === STRING) {
      const length = bytes.readUInt16BE(at);
      headers[name] = bytes.subarray(at + 2, at + 2 + length).toString("utf8");
      at += 2 + length;
    } else if (type === 6) {
      at += 2 + bytes.readUInt16BE(at);
    } else if (Object.hasOwn(WIDTH, type)) {
      at += WIDTH[type];
    } else {
      throw new StreamError("a header of no known type");
    }
  }
  if (at !== bytes.length) {
    throw new StreamError("headers that overrun their length");
  }
  return headers;
}
