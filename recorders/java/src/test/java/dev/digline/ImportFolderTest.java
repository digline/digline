package dev.digline;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;
import java.util.stream.Stream;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/**
 * Writes the recordings {@code digline record import} reads in the CI job
 * {@code recorder-java}, under {@code -Ddigline.importRoot=<directory>}: one
 * episode of suite {@code s} and then two of its calls, for tenant {@code t}.
 * {@code tests/test_recorder_java.py} then imports them with digline alone.
 * Without the property the same files go to a temporary directory.
 */
class ImportFolderTest {

    @TempDir
    Path scratch;

    @Test
    void writesWhatTheImportReads() throws IOException {
        String given = System.getProperty("digline.importRoot");
        Path root = given == null || given.isEmpty() ? scratch : Path.of(given);
        Path tenant = root.resolve(".digline").resolve("t");
        Files.createDirectories(tenant);
        Files.writeString(tenant.resolve("recorder.toml"), "on = true\n", StandardCharsets.UTF_8);

        DiglineRecorder recorder = DiglineRecorder.development(root, "t", "java");
        Map<String, Object> setup = Map.of("model", "gpt-4o-mini", "temperature", 0.2);
        // The episode first: the setup in force is the newest's, and the two calls
        // after it are what the import offers to elect.
        try (var episode = recorder.episode("s", Map.of("ticket", "A1 is late"))) {
            try (var suite = DiglineRecorder.suite("lookup")) {
                recorder.record(new DiglineRecorder.Call(
                        Map.of("messages", List.of(Map.of("role", "user", "content", "A1?"))),
                        setup, "", 120.0, new DiglineRecorder.Usage(5, 2), "tool_use",
                        List.of(DiglineRecorder.ToolCall.asked("lookup", Map.of("order", "A1")))));
            }
            episode.output("A1 left the warehouse on Monday.");
        }
        try (var suite = DiglineRecorder.suite("s")) {
            recorder.record(new DiglineRecorder.Call(
                    Map.of("messages", List.of(Map.of("role", "user", "content", "Where is my refund?"))),
                    setup, "It was sent on Monday.", 812.0, new DiglineRecorder.Usage(14, 7), "stop",
                    List.of()));
            recorder.record(new DiglineRecorder.Call(
                    Map.of("messages", List.of(Map.of("role", "user", "content", "Où est la facture ?"))),
                    setup, "Dans votre espace client.", 640.5, new DiglineRecorder.Usage(12, 6), "stop",
                    List.of()));
        }
        assertEquals(Map.of("recorded", 4L, "not_recorded", Map.of(), "orphan", 0L, "noted", Map.of()),
                recorder.counts());
        try (Stream<Path> files = Files.walk(tenant.resolve("recordings"))) {
            assertEquals(4, files.filter(path -> path.toString().endsWith(".json")).count());
        }
    }
}
