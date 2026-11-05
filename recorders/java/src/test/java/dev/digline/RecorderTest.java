package dev.digline;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.PrintStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.regex.Pattern;
import java.util.stream.Stream;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/** The recorder as an application meets it: the switch, the files, the episode. */
class RecorderTest {

    @TempDir
    Path root;

    static final Pattern RECORDED_AT = Pattern.compile(
            "\\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\\d|3[01])"
            + "T([01]\\d|2[0-3]):[0-5]\\d:[0-5]\\d(\\.\\d{1,6})?\\+00:00");

    void switchOn(String tenant, String text) throws IOException {
        Path directory = root.resolve(".digline").resolve(tenant);
        Files.createDirectories(directory);
        Files.writeString(directory.resolve("recorder.toml"), text, StandardCharsets.UTF_8);
    }

    static DiglineRecorder.Call call(String question, String answer) {
        return new DiglineRecorder.Call(
                Map.of("messages", List.of(Map.of("role", "user", "content", question))),
                Map.of("model", "gpt-4o-mini", "temperature", 0.2),
                answer, 12.5, new DiglineRecorder.Usage(10, 3), "stop", List.of());
    }

    List<Path> recordings(String tenant) throws IOException {
        Path directory = root.resolve(".digline").resolve(tenant).resolve("recordings");
        if (!Files.isDirectory(directory)) {
            return List.of();
        }
        try (Stream<Path> found = Files.walk(directory)) {
            return found.filter(path -> path.getFileName().toString().endsWith(".json")
                    && !path.getFileName().toString().startsWith(".")
                    && !path.getFileName().toString().equals("ceiling-reached.json"))
                    .sorted().toList();
        }
    }

    @SuppressWarnings("unchecked")
    static Map<String, Object> document(Path path) throws IOException {
        return (Map<String, Object>) DiglineRecorder.Json.parse(Files.readString(path));
    }

    @Test
    void withoutADigineDirectoryTheRecorderIsOff() throws IOException {
        DiglineRecorder recorder = DiglineRecorder.development(root, "acme", "support");
        assertFalse(recorder.on());
        recorder.record(call("q", "a"));
        assertEquals(List.of(), recordings("acme"));
        assertFalse(Files.exists(root.resolve(".digline")));
        assertEquals(0L, recorder.counts().get("recorded"));
    }

    @Test
    void aCallIsFiledWhereDiglineReadsIt() throws IOException {
        switchOn("acme", "on = true\n");
        DiglineRecorder recorder = DiglineRecorder.development(root, "acme", "support");
        try (var suite = DiglineRecorder.suite("refunds")) {
            recorder.record(call("Where is my refund?", "Sent Monday."));
            recorder.record(call("And the other one?", "Tomorrow."));
        }
        List<Path> written = recordings("acme");
        assertEquals(2, written.size());
        Path process = written.get(0).getParent();
        assertTrue(process.getFileName().toString().matches("j\\d+-[0-9a-f]{8}"), process.toString());
        assertEquals(List.of("000001.json", "000002.json"),
                written.stream().map(path -> path.getFileName().toString()).toList());
        Map<String, Object> first = document(written.get(0));
        assertEquals(1L, first.get("recording_version"));
        assertEquals("acme", first.get("source_tenant"));
        assertEquals("support", first.get("app"));
        assertEquals("refunds", first.get("suite"));
        assertEquals("fce37866a724540f", first.get("setup_digest"));
        assertTrue(RECORDED_AT.matcher((String) first.get("recorded_at")).matches());
        assertFalse(first.containsKey("call_site"));
        @SuppressWarnings("unchecked")
        Map<String, Object> response = (Map<String, Object>) first.get("response");
        assertEquals("[{\"content\":\"Where is my refund?\",\"role\":\"user\"}]", response.get("input"));
        assertEquals(List.of(Map.of("actor", "model", "finish", "stop", "index", 0L)), response.get("steps"));
        // The layout digline makes before a tenant's first recording, so git ignores it.
        assertEquals(DiglineRecorder.GITIGNORE, Files.readString(root.resolve(".digline/.gitignore")));
        assertTrue(Files.isDirectory(root.resolve(".digline/acme/baselines")));
        // No counts file: not part of the contract, and `record status` says "not counted".
        try (Stream<Path> files = Files.list(process)) {
            assertEquals(List.of(), files.filter(path -> path.getFileName().toString().equals(".counts")
                    || !path.getFileName().toString().endsWith(".json")).toList());
        }
        assertEquals(2L, recorder.counts().get("recorded"));
        // A file already in place is never written over.
        assertTrue(written.stream().allMatch(path -> !Files.isSymbolicLink(path)));
    }

    @Test
    void aCallThatNamesNoSuiteIsUnassignedWithItsCallSite() throws IOException {
        switchOn("acme", "on = true\n");
        DiglineRecorder recorder = DiglineRecorder.development(root, "acme", "support");
        recorder.record(call("q", "a"));
        Map<String, Object> written = document(recordings("acme").get(0));
        assertEquals("_unassigned", written.get("suite"));
        assertTrue(((String) written.get("call_site")).startsWith("org.junit.") || ((String) written
                .get("call_site")).startsWith(getClass().getName()), (String) written.get("call_site"));
    }

    @Test
    void aSuiteScopePutsBackWhatTheThreadHad() throws IOException {
        switchOn("acme", "on = true\n");
        DiglineRecorder recorder = DiglineRecorder.development(root, "acme", "support");
        try (var outer = DiglineRecorder.suite("outer")) {
            try (var inner = DiglineRecorder.suite("inner")) {
                recorder.record(call("q", "a"));
            }
            recorder.record(call("q", "a"));
        }
        recorder.record(call("q", "a"));
        List<Object> suites = new ArrayList<>();
        for (Path path : recordings("acme")) {
            suites.add(document(path).get("suite"));
        }
        assertEquals(List.of("inner", "outer", "_unassigned"), suites);
    }

    @Test
    void anEpisodeIsOneRecordingWithItsCallsAsSteps() throws Exception {
        switchOn("acme", "on = true\n");
        DiglineRecorder recorder = DiglineRecorder.development(root, "acme", "agent");
        String id;
        try (var episode = recorder.episode("order-agent", Map.of("ticket", "Where is A1?"))) {
            id = episode.id();
            assertNotNull(id);
            assertTrue(id.matches("[0-9a-f]{32}"));
            recorder.record(new DiglineRecorder.Call(
                    Map.of("messages", List.of(Map.of("role", "user", "content", "Where is A1?"))),
                    Map.of("model", "m"), "", 5.0, new DiglineRecorder.Usage(1, 1), "tool_use",
                    List.of(DiglineRecorder.ToolCall.asked("lookup", Map.of("order", "A1")))));
            // A call made on another thread, attached by the episode's id.
            Thread other = new Thread(() -> {
                try (var attached = DiglineRecorder.attach(episode.id())) {
                    recorder.record(call("A1?", "Shipped."));
                }
            });
            other.start();
            other.join();
            episode.output("A1 shipped on Monday.");
        }
        List<Path> written = recordings("acme");
        assertEquals(3, written.size());
        Map<String, Object> child = document(written.get(0));
        assertEquals(id, child.get("episode"));
        assertFalse(child.containsKey("orphan"));
        assertEquals(id, document(written.get(1)).get("episode"));
        Map<String, Object> episode = document(written.get(2));
        assertEquals(id, episode.get("id"));
        assertEquals("order-agent", episode.get("suite"));
        @SuppressWarnings("unchecked")
        Map<String, Object> response = (Map<String, Object>) episode.get("response");
        assertEquals("A1 shipped on Monday.", response.get("output"));
        assertEquals("{\"ticket\":\"Where is A1?\"}", response.get("input"));
        assertEquals("stop", response.get("finish"));
        assertEquals(List.of("lookup"), response.get("tools"));
        @SuppressWarnings("unchecked")
        List<Map<String, Object>> steps = (List<Map<String, Object>>) response.get("steps");
        assertEquals(List.of("model", "tool", "model"), steps.stream().map(step -> step.get("actor")).toList());
        @SuppressWarnings("unchecked")
        Map<String, Object> setup = (Map<String, Object>) episode.get("setup");
        // Its two children's setups, distinct and sorted.
        List<String> children = new ArrayList<>(List.of(
                DiglineRecorder.setupDigest(Map.of("model", "m")),
                DiglineRecorder.setupDigest(Map.of("model", "gpt-4o-mini", "temperature", 0.2))));
        children.sort(null);
        assertEquals(children, setup.get("child_setups"));
        assertEquals(DiglineRecorder.setupDigest(setup), episode.get("setup_digest"));
    }

    @Test
    void aCallInNoEpisodeWhileOneIsOpenIsAnOrphanAndOneAfterItClosedIsLate() throws Exception {
        switchOn("acme", "on = true\n");
        DiglineRecorder recorder = DiglineRecorder.development(root, "acme", "agent");
        String id;
        try (var episode = recorder.episode("agent", Map.of("ticket", "t"))) {
            id = episode.id();
            Thread unattached = new Thread(() -> recorder.record(call("q", "orphan")));
            unattached.start();
            unattached.join();
            episode.output("done");
        }
        try (var late = DiglineRecorder.attach(id)) {
            recorder.record(call("q", "late"));
        }
        List<Path> written = recordings("acme");
        Map<String, Object> orphan = document(written.get(0));
        assertEquals(Boolean.TRUE, orphan.get("orphan"));
        assertFalse(orphan.containsKey("episode"));
        Map<String, Object> late = document(written.get(2));
        assertEquals(Boolean.TRUE, late.get("orphan"));
        assertEquals(id, late.get("episode"));
        assertEquals(Map.of("ended after its episode", 1L), recorder.counts().get("noted"));
        assertEquals(1L, recorder.counts().get("orphan"));
    }

    @Test
    void anInterruptedEpisodeSaysSo() throws IOException {
        switchOn("acme", "on = true\n");
        DiglineRecorder recorder = DiglineRecorder.development(root, "acme", "agent");
        try (var episode = recorder.episode("agent", Map.of("ticket", "t"))) {
            recorder.record(call("q", "the last text"));
            episode.interrupted();
        }
        Map<String, Object> episode = document(recordings("acme").get(1));
        assertEquals(Boolean.TRUE, episode.get("interrupted"));
        @SuppressWarnings("unchecked")
        Map<String, Object> response = (Map<String, Object>) episode.get("response");
        assertEquals("the last text", response.get("output"));
    }

    @Test
    void aChildTheEpisodeDidNotSeeIsCounted() throws IOException {
        switchOn("acme", "on = true\n");
        DiglineRecorder recorder = DiglineRecorder.development(root, "acme", "agent");
        try (var episode = recorder.episode("agent", Map.of("ticket", "t"))) {
            recorder.record(call("q", "seen"));
            recorder.record(new DiglineRecorder.Call(Map.of("messages", List.of()),
                    Map.of("model", new Object()), "unseen", 1.0, null, null, null));
            recorder.miss("map");
        }
        Map<String, Object> episode = document(recordings("acme").get(1));
        assertEquals(2L, episode.get("unrecorded_children"));
        assertEquals(Map.of("map", 1L, "not JSON", 1L), recorder.counts().get("not_recorded"));
    }

    @Test
    void aRecordingIsNeverWrittenOverAnother() throws IOException {
        DiglineRecorder.Writer writer = new DiglineRecorder.Writer(root);
        writer.write("acme", "{\"first\": true}\n");
        Path first;
        try (Stream<Path> found = Files.walk(root.resolve(".digline/acme/recordings"))) {
            first = found.filter(path -> path.getFileName().toString().equals("000001.json"))
                    .findFirst().orElseThrow();
        }
        Path second = first.resolveSibling("000002.json");
        Files.writeString(second, "somebody else's\n");
        IOException refused = assertThrows(IOException.class, () -> writer.write("acme", "{}\n"));
        assertTrue(refused.getMessage().endsWith("a recording is never written over another"));
        assertEquals("somebody else's\n", Files.readString(second));
        try (Stream<Path> left = Files.list(first.getParent())) {
            assertEquals(2, left.count(), "no temporary file is left behind");
        }
    }

    @Test
    void anEpisodeWithNoOutputAndNoCallIsNotRecorded() throws IOException {
        switchOn("acme", "on = true\n");
        DiglineRecorder recorder = DiglineRecorder.development(root, "acme", "agent");
        try (var episode = recorder.episode("agent", Map.of("ticket", "t"))) {
            assertNotNull(episode.id());
        }
        assertEquals(List.of(), recordings("acme"));
        assertEquals(Map.of("no output", 1L), recorder.counts().get("not_recorded"));
    }

    @Test
    void offAnEpisodeIsAnEmptyScope() {
        DiglineRecorder recorder = DiglineRecorder.development(root, "acme", "agent");
        try (var episode = recorder.episode("agent", Map.of("ticket", "t"))) {
            assertNull(episode.id());
            try (var attached = DiglineRecorder.attach(episode.id())) {
                recorder.record(call("q", "a"));
            }
        }
        assertEquals(0L, recorder.counts().get("recorded"));
    }

    @Test
    void aValueJsonCannotCarryIsNotRecordedAndTheCallGoesOn() throws IOException {
        switchOn("acme", "on = true\n");
        DiglineRecorder recorder = DiglineRecorder.development(root, "acme", "support");
        recorder.record(new DiglineRecorder.Call(Map.of("messages", List.of()),
                Map.of("model", new Object()), "a", 1.0, null, null, null));
        recorder.record(new DiglineRecorder.Call(Map.of("messages", List.of("\ud800")),
                Map.of("model", "m"), "a", 1.0, null, null, null));
        recorder.record(new DiglineRecorder.Call(Map.of("messages", List.of()),
                Map.of("temperature", Double.NaN), "a", 1.0, null, null, null));
        assertEquals(List.of(), recordings("acme"));
        assertEquals(Map.of("not JSON", 3L), recorder.counts().get("not_recorded"));
    }

    @Test
    void aCallWithNoCountsIsRecordedAndNoted() throws IOException {
        switchOn("acme", "on = true\n");
        DiglineRecorder recorder = DiglineRecorder.development(root, "acme", "support");
        recorder.record(new DiglineRecorder.Call(Map.of("messages", List.of()), Map.of("model", "m"),
                "a", 1.0, null, null, null));
        Map<String, Object> written = document(recordings("acme").get(0));
        @SuppressWarnings("unchecked")
        Map<String, Object> response = (Map<String, Object>) written.get("response");
        assertFalse(response.containsKey("usage"));
        assertFalse(response.containsKey("steps"), "no tool calls reported, so no steps");
        assertEquals("[]", response.get("input"));
        assertEquals(Map.of("usage not reported", 1L), recorder.counts().get("noted"));
    }

    @Test
    void anAnswerOverTheCeilingOfAFieldIsOversizeWholeOrNothing() throws IOException {
        switchOn("acme", "on = true\n");
        DiglineRecorder recorder = DiglineRecorder.development(root, "acme", "support");
        recorder.record(call("q", "x".repeat(DiglineRecorder.MAX_RECORDED_CHARS + 1)));
        @SuppressWarnings("unchecked")
        Map<String, Object> response = (Map<String, Object>) document(recordings("acme").get(0))
                .get("response");
        assertEquals(Map.of("oversize", true, "latency_ms", 12.5,
                "usage", Map.of("input_tokens", 10L, "output_tokens", 3L)), response);
    }

    @Test
    void atTheCeilingTheRecorderStopsAndSaysSo() throws IOException {
        switchOn("acme", "on = true\nceiling = 1\n");
        DiglineRecorder recorder = DiglineRecorder.development(root, "acme", "support");
        recorder.record(call("q", "a"));
        recorder.record(call("q", "a"));
        assertEquals(1, recordings("acme").size());
        assertEquals(Map.of("ceiling", 1L), recorder.counts().get("not_recorded"));
        String marker = Files.readString(root.resolve(".digline/acme/recordings/ceiling-reached.json"));
        assertTrue(marker.startsWith("{\"ceiling\": 1, \"size\": "), marker);
    }

    @Test
    void aSampleOfAlmostNothingRecordsNothing() throws IOException {
        switchOn("acme", "on = true\nsample = 1e-300\n");
        DiglineRecorder recorder = DiglineRecorder.development(root, "acme", "support");
        for (int i = 0; i < 20; i++) {
            recorder.record(call("q", "a"));
        }
        assertEquals(List.of(), recordings("acme"));
        assertEquals(Map.of("sampled out", 20L), recorder.counts().get("not_recorded"));
    }

    @Test
    void theSwitchIsReadAgainAtItsInterval() throws Exception {
        switchOn("acme", "on = false\ninterval = 0.01\n");
        DiglineRecorder recorder = DiglineRecorder.development(root, "acme", "support");
        recorder.record(call("q", "a"));
        assertEquals(List.of(), recordings("acme"));
        // A different size, so the stamp moves even where the clock is coarse.
        switchOn("acme", "on = true\ninterval = 0.01\n\n");
        Thread.sleep(50);
        recorder.record(call("q", "a"));
        assertEquals(1, recordings("acme").size());
    }

    @Test
    void anInvalidFileInDevelopmentIsSaidOnceAndLeavesTheRecorderOff() throws IOException {
        switchOn("acme", "on = true\ncolour = 1\n");
        PrintStream before = System.err;
        ByteArrayOutputStream said = new ByteArrayOutputStream();
        System.setErr(new PrintStream(said, true, StandardCharsets.UTF_8));
        DiglineRecorder recorder;
        try {
            recorder = DiglineRecorder.development(root, "acme", "support");
        } finally {
            System.setErr(before);
        }
        assertFalse(recorder.on());
        String line = said.toString(StandardCharsets.UTF_8);
        assertTrue(line.startsWith("digline recorder: not recording for this tenant: "), line);
        assertTrue(line.contains("has keys the recorder does not read: colour"), line);
        assertEquals(Map.of("config invalid", 1L), recorder.counts().get("not_recorded"));
    }

    @Test
    void productionRefusesToStartOnAFileThatDeclaresTooLittle() throws IOException {
        switchOn("acme", "on = true\nsample = 0.5\n");
        DiglineRecorder.StartError refused = assertThrows(DiglineRecorder.StartError.class,
                () -> DiglineRecorder.production(root, () -> "acme", "support"));
        assertTrue(refused.getMessage().contains("switches recording on in production with no "
                + "declared redaction"), refused.getMessage());
    }

    @Test
    void productionFilesEachTenantUnderItsOwnDirectory() throws IOException {
        String declared = "on = true\nsample = 1\nredact = \"none\"\nceiling = 1000000\n";
        switchOn("acme", declared);
        switchOn("globex", declared);
        String[] tenant = {"acme"};
        DiglineRecorder recorder = DiglineRecorder.production(root, () -> tenant[0], "support");
        recorder.record(call("q", "a"));
        tenant[0] = "globex";
        recorder.record(call("q", "a"));
        tenant[0] = "initech";
        recorder.record(call("q", "a"));
        assertEquals("acme", document(recordings("acme").get(0)).get("source_tenant"));
        assertEquals("globex", document(recordings("globex").get(0)).get("source_tenant"));
        assertEquals(List.of(), recordings("initech"));
        assertEquals(Map.of("off for this tenant", 1L), recorder.counts().get("not_recorded"));
    }

    @Test
    void anEmptyAppOrTenantIsRefusedAtTheStart() {
        assertThrows(DiglineRecorder.StartError.class,
                () -> DiglineRecorder.development(root, "acme", ""));
        assertThrows(DiglineRecorder.StartError.class,
                () -> DiglineRecorder.development(root, "", "support"));
    }

    @Test
    void recordedAtIsTheContractsOneForm() {
        assertEquals("2026-11-05T08:00:00+00:00",
                DiglineRecorder.timestamp(Instant.parse("2026-11-05T08:00:00Z")));
        assertEquals("2026-11-05T08:00:00.100000+00:00",
                DiglineRecorder.timestamp(Instant.parse("2026-11-05T08:00:00.1Z")));
        assertEquals("2026-11-05T08:00:00.000001+00:00",
                DiglineRecorder.timestamp(Instant.parse("2026-11-05T08:00:00.000001999Z")));
        assertTrue(RECORDED_AT.matcher(DiglineRecorder.now()).matches());
    }

    @Test
    void jsonIsReadStrictly() {
        assertThrows(IllegalArgumentException.class, () -> DiglineRecorder.Json.parse("NaN"));
        assertThrows(IllegalArgumentException.class, () -> DiglineRecorder.Json.parse("{} x"));
        assertThrows(IllegalArgumentException.class, () -> DiglineRecorder.Json.parse("[1,]"));
        assertThrows(IllegalArgumentException.class, () -> DiglineRecorder.Json.parse("01"));
        assertEquals(List.of(1L, 1.0, new java.math.BigInteger("12345678901234567890")),
                DiglineRecorder.Json.parse("[1, 1.0, 12345678901234567890]"));
    }
}
