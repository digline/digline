package dev.digline;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Stream;
import org.junit.jupiter.api.Test;

/**
 * Each hook's reading of a call off the wire, held byte for byte to the file
 * digline's own map writes from the same bytes: `recorders/fixtures/wire/`,
 * which `recorders/fixtures/make.py` writes with the plugins' code.
 */
class WireFixturesTest {

    /** The latency every wire fixture is recorded with: `WIRE_LATENCY_MS` in make.py. */
    static final double LATENCY_MS = 250.5;

    @SuppressWarnings("unchecked")
    static DiglineRecorder.Call read(Map<String, Object> wire, double latencyMs) {
        Map<String, Object> request = (Map<String, Object>) wire.get("request");
        boolean streamed = wire.containsKey("events");
        List<Object> events = (List<Object>) wire.get("events");
        Map<String, Object> reply = (Map<String, Object>) wire.get("reply");
        return switch ((String) wire.get("route")) {
            case "openai" -> streamed ? DiglineOkHttp.streamed(request, events, latencyMs)
                    : DiglineOkHttp.call(request, reply, latencyMs);
            case "anthropic" -> streamed ? DiglineMessages.streamed(request, events, latencyMs)
                    : DiglineMessages.call(request, reply, latencyMs);
            case "bedrock" -> {
                Map<String, Object> asked = new LinkedHashMap<>();
                asked.put("modelId", wire.get("model_id"));
                asked.putAll(request);
                if (((String) wire.get("path")).contains("/invoke")) {
                    // InvokeModel with an Anthropic model: Messages, read as a
                    // direct call is, its stream's chunks decoded first.
                    yield streamed ? DiglineMessages.streamed(asked, DiglineAws.chunks(events), latencyMs)
                            : DiglineMessages.call(asked, reply, latencyMs);
                }
                yield streamed ? DiglineAws.streamed(asked, events, latencyMs)
                        : DiglineAws.call(asked, reply, latencyMs);
            }
            default -> throw new IllegalArgumentException("no route " + wire.get("route"));
        };
    }

    @Test
    void everyWireCallIsTheFileDiglinesMapWrites() throws IOException {
        Path wire = FixturesTest.fixtures().resolve("wire");
        List<Path> calls;
        try (Stream<Path> found = Files.list(wire)) {
            calls = found.filter(path -> !path.getFileName().toString().endsWith(".expected.json"))
                    .sorted().toList();
        }
        assertEquals(12, calls.size(), calls.toString());
        Map<String, Object> call = FixturesTest.parsed("call.json");
        for (Path path : calls) {
            String name = path.getFileName().toString();
            @SuppressWarnings("unchecked")
            Map<String, Object> fixture = (Map<String, Object>) DiglineRecorder.Json.parse(
                    Files.readString(path));
            Map<String, Object> written = DiglineRecorder.singleDocument((String) call.get("tenant"),
                    (String) call.get("app"), (String) call.get("suite"), read(fixture, LATENCY_MS),
                    (String) call.get("recorded_at"));
            String expected = Files.readString(wire.resolve(name.replace(".json", ".expected.json")));
            assertEquals(expected, DiglineRecorder.Json.file(written) + "\n", name);
        }
    }

    @Test
    @SuppressWarnings("unchecked")
    void anEventStreamIsReadFrameByFrameAndAFrameThatDoesNotCheckIsRefused() throws IOException {
        List<Object> events = (List<Object>) HooksTest.wire("bedrock-stream").get("events");
        byte[] frames = FakeProvider.eventStream(events);
        assertEquals(DiglineRecorder.Json.compact(events),
                DiglineRecorder.Json.compact(DiglineAws.frames(frames)));
        for (int at : new int[] {5, 20, frames.length - 1}) {
            byte[] broken = frames.clone();
            broken[at] ^= 1;
            org.junit.jupiter.api.Assertions.assertThrows(IllegalArgumentException.class,
                    () -> DiglineAws.frames(broken), "byte " + at);
        }
    }

    @Test
    void anExceptionInTheStreamIsAStreamError() {
        byte[] frames = FakeProvider.eventStream(List.of(Map.of("messageStart", Map.of("role", "assistant"))));
        // The same frame, said an exception: its message type changed, its checksums made again.
        String text = new String(frames, java.nio.charset.StandardCharsets.ISO_8859_1)
                .replace("\u0005event", "\u0009exception");
        byte[] header = text.getBytes(java.nio.charset.StandardCharsets.ISO_8859_1);
        java.nio.ByteBuffer frame = java.nio.ByteBuffer.wrap(header);
        int total = header.length;
        frame.putInt(0, total);
        frame.putInt(4, frame.getInt(4) + 4);
        java.util.zip.CRC32 prelude = new java.util.zip.CRC32();
        prelude.update(header, 0, 8);
        frame.putInt(8, (int) prelude.getValue());
        java.util.zip.CRC32 message = new java.util.zip.CRC32();
        message.update(header, 0, total - 4);
        frame.putInt(total - 4, (int) message.getValue());
        org.junit.jupiter.api.Assertions.assertThrows(DiglineAws.StreamError.class,
                () -> DiglineAws.frames(header));
    }

    @Test
    void bedrockTakesTheModelFromThePath() {
        assertEquals("anthropic.claude-3-5-haiku-20241022-v1:0", DiglineAws.modelIdOf(
                "/model/anthropic.claude-3-5-haiku-20241022-v1%3A0/converse-stream"));
        assertEquals("a+b", DiglineAws.modelIdOf("/model/a+b/converse"));
        assertTrue(DiglineAws.modelIdOf("/model/arn%3Aaws%3Abedrock%3Aus-east-1%3A1%3Ap%2Fx/converse")
                .equals("arn:aws:bedrock:us-east-1:1:p/x"));
    }
}
