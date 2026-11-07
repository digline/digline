package dev.digline;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.FileTime;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.TreeSet;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/**
 * The writer held to what digline's Python answers, on the files
 * {@code recorders/fixtures/make.py} writes from digline's own code and
 * {@code tests/test_recorder_fixtures.py} holds equal to it.
 */
class FixturesTest {

    static Path fixtures() {
        String where = System.getProperty("digline.fixtures");
        assertTrue(where != null, "run through Maven, which says where the fixtures are");
        return Path.of(where);
    }

    static String read(String name) throws IOException {
        return Files.readString(fixtures().resolve(name), StandardCharsets.UTF_8);
    }

    @SuppressWarnings("unchecked")
    static <T> T parsed(String name) throws IOException {
        return (T) DiglineRecorder.Json.parse(read(name));
    }

    @Test
    void everySetupDigestIsPythons() throws IOException {
        List<Map<String, Object>> setups = parsed("setups.json");
        assertEquals(3, setups.size());
        for (Map<String, Object> each : setups) {
            @SuppressWarnings("unchecked")
            Map<String, Object> setup = (Map<String, Object>) each.get("setup");
            assertEquals(each.get("digest"), DiglineRecorder.setupDigest(setup), setup.toString());
        }
        // The one measured across the two languages on 2026-11-04 (ADR 0062).
        assertEquals("81869b20f0d8875a", DiglineRecorder.setupDigest(
                Map.of("max_tokens", 64L, "model", "claude-haiku-4-5")));
    }

    @Test
    void everyFloatIsWrittenAsPythonWritesIt() throws IOException {
        // Each row: the double's bits, its repr, its float_text, the repr of it rounded.
        List<List<String>> floats = parsed("floats.json");
        assertTrue(floats.size() > 1000, "the edges, the powers of two, the random draws");
        List<String> wrong = new ArrayList<>();
        for (List<String> row : floats) {
            double value = Double.longBitsToDouble(Long.parseUnsignedLong(row.get(0), 16));
            check(wrong, row, 1, "repr", DiglineRecorder.pythonRepr(value));
            check(wrong, row, 2, "text", DiglineRecorder.floatText(value));
            check(wrong, row, 3, "rounded", DiglineRecorder.pythonRepr(DiglineRecorder.round(value)));
        }
        assertEquals(List.of(), wrong);
    }

    @Test
    void aTieAtTheSixthPlaceGoesToTheEvenDigitAsPythonsRoundTakesIt() {
        // floats.json holds no exact tie, so it cannot tell half to even from
        // half up. A double is a tie at the sixth place only at an odd multiple
        // of 1/128; Python 3.14's round(value, 6), read on 2026-11-06, gave
        // these, which Node's fixtures test holds too.
        Map<Double, String> ties = new java.util.LinkedHashMap<>();
        ties.put(0.0078125, "0.007812");
        ties.put(0.0234375, "0.023438");
        ties.put(-0.0078125, "-0.007812");
        ties.put(1.0078125, "1.007812");
        for (Map.Entry<Double, String> tie : ties.entrySet()) {
            assertEquals(tie.getValue(), DiglineRecorder.pythonRepr(DiglineRecorder.round(tie.getKey())),
                    String.valueOf(tie.getKey()));
        }
    }

    private static void check(List<String> wrong, List<String> row, int at, String what, String java) {
        if (!row.get(at).equals(java)) {
            wrong.add(row.get(0) + " " + what + ": Python " + row.get(at) + ", Java " + java);
        }
    }

    @Test
    void everySwitchIsReadAsPythonReadsIt() throws IOException {
        List<Map<String, Object>> switches = parsed("switches.json");
        for (Map<String, Object> each : switches) {
            String text = (String) each.get("text");
            boolean production = (Boolean) each.get("production");
            if (each.containsKey("refusal")) {
                DiglineRecorder.StartError refused = assertThrows(DiglineRecorder.StartError.class,
                        () -> DiglineRecorder.parseSwitch(text, "recorder.toml", production), text);
                assertEquals(each.get("refusal"), refused.getMessage(), text);
                continue;
            }
            @SuppressWarnings("unchecked")
            Map<String, Object> expected = (Map<String, Object>) each.get("switch");
            DiglineRecorder.Switch read = DiglineRecorder.parseSwitch(text, "recorder.toml", production);
            assertEquals(expected.get("on"), read.on, text);
            assertEquals(expected.get("sample"), read.sample, text);
            assertEquals(expected.get("ceiling"), read.ceiling, text);
            assertEquals(expected.get("interval"), read.interval, text);
            assertEquals(expected.get("production"), read.production, text);
            assertEquals(expected.get("declared"), new ArrayList<>(new TreeSet<>(read.declared)), text);
        }
    }

    @Test
    void oneCallIsTheFileDiglinesWriterWrites() throws IOException {
        Map<String, Object> call = parsed("call.json");
        Map<String, Object> written = DiglineRecorder.singleDocument((String) call.get("tenant"),
                (String) call.get("app"), (String) call.get("suite"), callOf(call),
                (String) call.get("recorded_at"));
        assertEquals(read("call.expected.json"), DiglineRecorder.Json.file(written) + "\n");
    }

    @SuppressWarnings("unchecked")
    static DiglineRecorder.Call callOf(Map<String, Object> call) {
        Map<String, Object> usage = (Map<String, Object>) call.get("usage");
        List<DiglineRecorder.ToolCall> tools = new ArrayList<>();
        for (Map<String, Object> each : (List<Map<String, Object>>) call.get("tool_calls")) {
            tools.add(DiglineRecorder.ToolCall.asked((String) each.get("tool"), each.get("arguments")));
        }
        return new DiglineRecorder.Call(
                (Map<String, Object>) call.get("case"),
                (Map<String, Object>) call.get("setup"),
                (String) call.get("output"),
                (Double) call.get("latency_ms"),
                new DiglineRecorder.Usage((Long) usage.get("input_tokens"),
                        (Long) usage.get("output_tokens"), (Long) usage.get("cache_read_tokens"),
                        (Long) usage.get("cache_write_tokens"), (Long) usage.get("thinking_tokens")),
                (String) call.get("finish"),
                tools);
    }

    @Test
    void everyGateMarkerIsReadAsPythonReadsIt(@TempDir Path scratch) throws IOException {
        // Each row: the markers laid out, each with its age in seconds, and
        // what digline.recorder._gate answered for them. (ADR 0058, 2026-11-05)
        List<Map<String, Object>> gates = parsed("gates.json");
        assertTrue(gates.size() > 5, "none, live, stale, two, unreadable, ignored names");
        int row = 0;
        for (Map<String, Object> each : gates) {
            Path root = Files.createDirectory(scratch.resolve("row" + row++));
            Path place = root.resolve(".digline").resolve("acme").resolve("runs").resolve(".gate");
            Files.createDirectories(place);
            long now = System.currentTimeMillis();
            @SuppressWarnings("unchecked")
            List<Map<String, Object>> markers = (List<Map<String, Object>>) each.get("markers");
            for (Map<String, Object> marker : markers) {
                Path file = place.resolve((String) marker.get("name"));
                Files.writeString(file, (String) marker.get("text"), StandardCharsets.UTF_8);
                long age = ((Number) marker.get("age")).longValue();
                Files.setLastModifiedTime(file, FileTime.fromMillis(now - age * 1000));
            }
            String[] gate = DiglineRecorder.gate(root, "acme", now);
            String origin = gate == null ? null : gate[0];
            String runId = gate == null ? null : gate[1];
            assertEquals(each.get("origin"), origin, markers.toString());
            assertEquals(each.get("run_id"), runId, markers.toString());
        }
        assertEquals(List.of("runs", ".gate"), List.of(DiglineRecorder.GATE_DIRECTORY));
    }

    @Test
    void everyTenantNameIsReadAsPythonReadsIt() throws IOException {
        List<Map<String, Object>> names = parsed("names.json");
        assertTrue(names.size() > 10);
        for (Map<String, Object> each : names) {
            String name = (String) each.get("name");
            Object refusal = each.get("refusal");
            assertEquals(refusal == null, DiglineRecorder.isName(name), name);
            if (refusal != null) {
                assertEquals(refusal, DiglineRecorder.refusal(name), name);
                if (!name.isEmpty()) {
                    DiglineRecorder.StartError refused = assertThrows(DiglineRecorder.StartError.class,
                            () -> DiglineRecorder.development(Path.of("."), name, "app"), name);
                    assertEquals(refusal, refused.getMessage(), name);
                }
            }
        }
    }

    @Test
    void aGateOrAMarkerThatLinksOutOfTheStoreIsNotRead(@TempDir Path scratch) throws IOException {
        // As digline.host.gate holds it: resolved, and inside the store.
        String marker = "{\"run_id\": \"k\", \"pid\": 1, \"started_at\": \"x\", \"suite\": \"s\"}";
        Path outside = Files.createDirectory(scratch.resolve("outside"));
        Files.writeString(outside.resolve("1-k.json"), marker, StandardCharsets.UTF_8);
        Path linked = scratch.resolve("linked");
        Path runs = Files.createDirectories(linked.resolve(".digline").resolve("acme").resolve("runs"));
        Files.createSymbolicLink(runs.resolve(".gate"), outside);
        assertEquals(null, DiglineRecorder.gate(linked, "acme", System.currentTimeMillis()));

        Path inside = scratch.resolve("inside");
        Path place = Files.createDirectories(
                inside.resolve(".digline").resolve("acme").resolve("runs").resolve(".gate"));
        Files.createSymbolicLink(place.resolve("1-k.json"), outside.resolve("1-k.json"));
        assertEquals(null, DiglineRecorder.gate(inside, "acme", System.currentTimeMillis()));
        Files.writeString(place.resolve("2-k.json"), marker, StandardCharsets.UTF_8);
        assertEquals(List.of("gate", "k"),
                List.of(DiglineRecorder.gate(inside, "acme", System.currentTimeMillis())));
    }

    @Test
    void theLayoutIsDiglines() throws IOException {
        assertEquals(read("layout/gitignore"), DiglineRecorder.GITIGNORE);
        assertEquals(read("layout/gitattributes"), DiglineRecorder.GITATTRIBUTES);
    }
}
