package dev.digline;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Map;
import java.util.zip.CRC32;

/**
 * A provider on 127.0.0.1 that answers every POST with one wire fixture, in
 * the provider's own shape: a JSON reply, server-sent events for OpenAI and
 * Anthropic, or an AWS event stream for Bedrock. It keeps the last request's
 * body, which is what the SDK actually sent.
 */
final class FakeProvider implements AutoCloseable {

    private final HttpServer server;
    private final Map<String, Object> wire;
    private final long pauseMs;
    volatile String path;
    volatile byte[] request;

    FakeProvider(Map<String, Object> wire) throws IOException {
        this(wire, 0);
    }

    /** One that pauses after a stream's first event, so a client can leave before its end. */
    FakeProvider(Map<String, Object> wire, long pauseMs) throws IOException {
        this(wire, pauseMs, 0);
    }

    /** One on a fixed port, for a client that reads its base URL from the environment. */
    FakeProvider(Map<String, Object> wire, long pauseMs, int port) throws IOException {
        this.wire = wire;
        this.pauseMs = pauseMs;
        this.server = HttpServer.create(new InetSocketAddress("127.0.0.1", port), 0);
        server.createContext("/", this::answer);
        server.start();
    }

    String url() {
        return "http://127.0.0.1:" + server.getAddress().getPort();
    }

    @SuppressWarnings("unchecked")
    Map<String, Object> sent() {
        return (Map<String, Object>) DiglineRecorder.Json.parse(
                new String(request, StandardCharsets.UTF_8));
    }

    private void answer(HttpExchange exchange) throws IOException {
        path = exchange.getRequestURI().getRawPath();
        request = exchange.getRequestBody().readAllBytes();
        byte[] body;
        String type;
        @SuppressWarnings("unchecked")
        List<Object> events = (List<Object>) wire.get("events");
        if (events == null) {
            body = DiglineRecorder.Json.compact(wire.get("reply")).getBytes(StandardCharsets.UTF_8);
            type = "application/json";
        } else if ("bedrock".equals(wire.get("route"))) {
            body = eventStream(events);
            type = "application/vnd.amazon.eventstream";
        } else {
            StringBuilder text = new StringBuilder();
            for (Object event : events) {
                if (event instanceof Map<?, ?> map && map.get("type") instanceof String name) {
                    text.append("event: ").append(name).append('\n');
                }
                text.append("data: ").append(DiglineRecorder.Json.compact(event)).append("\n\n");
            }
            if ("openai".equals(wire.get("route"))) {
                text.append("data: [DONE]\n\n");
            }
            body = text.toString().getBytes(StandardCharsets.UTF_8);
            type = "text/event-stream";
        }
        exchange.getResponseHeaders().add("Content-Type", type);
        exchange.sendResponseHeaders(200, events == null ? body.length : 0);
        try (OutputStream out = exchange.getResponseBody()) {
            if (events == null) {
                out.write(body);
            } else {
                // A piece at a time, as a stream arrives.
                int first = new String(body, StandardCharsets.UTF_8).indexOf("\n\n") + 2;
                for (int at = 0; at < body.length; at += 37) {
                    out.write(body, at, Math.min(37, body.length - at));
                    out.flush();
                    if (pauseMs > 0 && at < first && at + 37 >= first) {
                        Thread.sleep(pauseMs);
                    }
                }
            }
        } catch (IOException | InterruptedException left) {
            // The client left before the end, which is what a pause is for.
        }
    }

    /** Each event as an AWS event-stream frame, as Bedrock sends ConverseStream's. */
    static byte[] eventStream(List<Object> events) {
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        for (Object event : events) {
            Map.Entry<?, ?> only = ((Map<?, ?>) event).entrySet().iterator().next();
            byte[] payload = DiglineRecorder.Json.compact(only.getValue()).getBytes(StandardCharsets.UTF_8);
            ByteArrayOutputStream headers = new ByteArrayOutputStream();
            header(headers, ":event-type", (String) only.getKey());
            header(headers, ":content-type", "application/json");
            header(headers, ":message-type", "event");
            byte[] head = headers.toByteArray();
            int total = 16 + head.length + payload.length;
            ByteBuffer frame = ByteBuffer.allocate(total);
            frame.putInt(total).putInt(head.length);
            frame.putInt(crc(frame.array(), 0, 8));
            frame.put(head).put(payload);
            frame.putInt(crc(frame.array(), 0, total - 4));
            out.writeBytes(frame.array());
        }
        return out.toByteArray();
    }

    private static void header(ByteArrayOutputStream out, String name, String value) {
        byte[] key = name.getBytes(StandardCharsets.UTF_8);
        byte[] text = value.getBytes(StandardCharsets.UTF_8);
        out.write(key.length);
        out.writeBytes(key);
        out.write(7);
        out.write(text.length >> 8);
        out.write(text.length & 0xff);
        out.writeBytes(text);
    }

    private static int crc(byte[] bytes, int offset, int length) {
        CRC32 crc = new CRC32();
        crc.update(bytes, offset, length);
        return (int) crc.getValue();
    }

    @Override
    public void close() {
        server.stop(0);
    }
}
