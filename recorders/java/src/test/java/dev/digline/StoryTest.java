package dev.digline;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import jakarta.annotation.PostConstruct;
import jakarta.enterprise.context.ApplicationScoped;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;
import java.util.function.Supplier;
import java.util.stream.Stream;
import org.eclipse.microprofile.config.inject.ConfigProperty;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import software.amazon.awssdk.core.SdkBytes;
import software.amazon.awssdk.services.bedrockruntime.BedrockRuntimeClient;
import software.amazon.awssdk.services.bedrockruntime.model.ConverseRequest;

/**
 * The Java blocks of `docs/walkthroughs/java-quarkus-bedrock.md`, as written, against the
 * fake Bedrock on the port the build's environment names. Each block stands
 * here between a `// page:` line and an `// end` line, and
 * `tests/test_story_java_quarkus.py` holds every block of the page to one of
 * these, line for line. The bean is compiled with its annotations and called
 * by hand: no container runs here, which is the story's to run.
 */
class StoryTest {

    @TempDir
    Path root;

    static final String MODEL = HooksTest.MODEL;

    final Object request = new Object();

    String tenantOf(Object asked) {
        return "acme";
    }

    void switchOn(String text) throws IOException {
        Path tenant = root.resolve(".digline").resolve("acme");
        Files.createDirectories(tenant);
        Files.writeString(tenant.resolve("recorder.toml"), text, StandardCharsets.UTF_8);
    }

    List<Map<String, Object>> recordings() throws IOException {
        try (Stream<Path> found = Files.walk(root.resolve(".digline/acme/recordings"))) {
            return found.filter(path -> path.getFileName().toString().matches("\\d{6}\\.json")).sorted()
                    .map(RecorderTest::documentOrThrow).toList();
        }
    }

    // page:
    @ApplicationScoped
    public class BedrockClients {

        @ConfigProperty(name = "digline.root")
        Path root;

        DiglineRecorder recorder;
        BedrockRuntimeClient client;

        @PostConstruct
        void build() {
            recorder = DiglineRecorder.development(root, "acme", "triage-app");
            client = BedrockRuntimeClient.builder()
                    .overrideConfiguration(c -> c.addExecutionInterceptor(new DiglineAws(recorder)))
                    .build();
        }

        public DiglineRecorder recorder() {
            return recorder;
        }

        public BedrockRuntimeClient client() {
            return client;
        }
    }
    // end

    BedrockClients bedrock;

    /** One model call of the turn, which the story's agent loops over. */
    String turn(String ticket) {
        return bedrock.client().converse(ConverseRequest.builder().modelId(MODEL)
                .messages(HooksTest.bedrockAsked()).build())
                .output().message().content().get(0).text();
    }

    String classify(String ticket) {
        // page:
        try (var episode = bedrock.recorder().episode("triage", Map.of("ticket", ticket));
                var calls = DiglineRecorder.suite("triage")) {
            try {
                String answer = turn(ticket);
                episode.output(answer);
                return answer;
            } catch (RuntimeException failed) {
                episode.interrupted();
                throw failed;
            }
        }
        // end
    }

    // page:
    <T> T ask(String feature, Supplier<T> call) {
        try (var suite = DiglineRecorder.suite(feature)) {
            return call.get();
        }
    }
    // end

    String classifyByInvoke(String body) {
        // page:
        return ask("triage", () -> bedrock.client().invokeModel(r -> r
                .modelId(MODEL)
                .body(SdkBytes.fromString(body, StandardCharsets.UTF_8)))
                .body().asUtf8String());
        // end
    }

    BedrockClients built() {
        BedrockClients clients = new BedrockClients();
        clients.root = root;
        clients.build();
        return clients;
    }

    @Test
    void theBeanTheTurnAndTheCall() throws IOException {
        switchOn("on = true\n");
        bedrock = built();
        try (FakeProvider converse = new FakeProvider(HooksTest.wire("bedrock-single"), 0, 18788)) {
            classify("Où est la commande A1 ?");
        }
        Map<String, Object> wire = HooksTest.wire("bedrock-invoke");
        try (FakeProvider invoke = new FakeProvider(wire, 0, 18788)) {
            classifyByInvoke(HooksTest.bodyOf(wire).asUtf8String());
        }
        bedrock.client().close();
        List<Map<String, Object>> written = recordings();
        // The turn's call, its episode, and the single InvokeModel call.
        assertEquals(3, written.size());
        assertEquals(written.get(1).get("id"), written.get(0).get("episode"));
        assertEquals(List.of("triage", "triage", "triage"),
                written.stream().map(each -> each.get("suite")).toList());
        assertTrue(!written.get(2).containsKey("episode"));
    }

    @Test
    void productionRefusesASwitchThatLeavesItsValuesToDefaults() throws IOException {
        switchOn("on = true\n");
        DiglineRecorder.StartError refused = assertThrows(DiglineRecorder.StartError.class,
                () -> DiglineRecorder.production(root, () -> tenantOf(request), "triage-app"));
        System.out.println("STORY production refused: " + refused.getMessage());
        switchOn("on = true\nsample = 1\nredact = \"none\"\nceiling = 1000000\n");
        DiglineRecorder recorder;
        // page:
        recorder = DiglineRecorder.production(root, () -> tenantOf(request), "triage-app");
        // end
        assertTrue(recorder.on());
    }
}
