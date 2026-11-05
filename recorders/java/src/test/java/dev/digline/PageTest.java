package dev.digline;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.anthropic.client.AnthropicClient;
import com.anthropic.client.okhttp.AnthropicOkHttpClient;
import com.openai.client.OpenAIClient;
import com.openai.client.okhttp.OpenAIOkHttpClient;
import com.openai.models.chat.completions.ChatCompletion;
import com.openai.models.chat.completions.ChatCompletionCreateParams;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.function.Supplier;
import java.util.stream.Stream;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import software.amazon.awssdk.services.bedrockruntime.BedrockRuntimeClient;
import software.amazon.awssdk.services.bedrockruntime.model.ConverseRequest;

/**
 * The Java blocks of `docs/record-java.md`, as written, run against fake
 * providers on the ports the build's environment names. Each block stands
 * here between a `// page:` line and an `// end` line, and
 * `tests/test_recorder_java.py` holds every block of the page to one of
 * these, line for line.
 */
class PageTest {

    @TempDir
    Path root;

    final ChatCompletionCreateParams params = HooksTest.OPENAI_ASKED;
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

    @Test
    void theClientsAndTheSuite() throws IOException {
        switchOn("on = true\n");
        try (FakeProvider o = new FakeProvider(HooksTest.wire("openai-single"), 0, 18787);
                FakeProvider a = new FakeProvider(HooksTest.wire("anthropic-single"), 0, 18789);
                FakeProvider b = new FakeProvider(HooksTest.wire("bedrock-single"), 0, 18788)) {
            // page:
            DiglineRecorder recorder = DiglineRecorder.development(root, "acme", "support");

            OpenAIClient openai = OpenAIOkHttpClient.builder()
                    .fromEnv()
                    .addInterceptor(new DiglineOkHttp(recorder))
                    .build();

            AnthropicClient anthropic = AnthropicOkHttpClient.builder()
                    .fromEnv()
                    .addInterceptor(new DiglineAnthropic(recorder))
                    .build();

            BedrockRuntimeClient bedrock = BedrockRuntimeClient.builder()
                    .overrideConfiguration(c -> c.addExecutionInterceptor(new DiglineAws(recorder)))
                    .build();
            // end

            // page:
            try (var suite = DiglineRecorder.suite("refunds")) {
                openai.chat().completions().create(params);
            }
            // end
            try (var suite = DiglineRecorder.suite("refunds")) {
                anthropic.messages().create(HooksTest.ANTHROPIC_ASKED);
                bedrock.converse(ConverseRequest.builder().modelId(HooksTest.MODEL)
                        .messages(HooksTest.bedrockAsked()).build());
            }
            bedrock.close();
        }
        List<Map<String, Object>> written = recordings();
        assertEquals(List.of("refunds", "refunds", "refunds"),
                written.stream().map(each -> each.get("suite")).toList());
        assertEquals(List.of("gpt-4o-mini", "claude-haiku-4-5", HooksTest.MODEL), List.of(
                setup(written.get(0)).get("model"), setup(written.get(1)).get("model"),
                setup(written.get(2)).get("modelId")));
    }

    @SuppressWarnings("unchecked")
    static Map<String, Object> setup(Map<String, Object> recording) {
        return (Map<String, Object>) recording.get("setup");
    }

    interface Agent {
        String answer(String ticket);
    }

    /** The client the attached thread's lookup calls. */
    OpenAIClient lookups;

    Object lookup(String order) {
        return lookups.chat().completions().create(params);
    }

    @Test
    void aTurnAndAnAttachedThread() throws Exception {
        switchOn("on = true\n");
        DiglineRecorder recorder = DiglineRecorder.development(root, "acme", "support");
        try (FakeProvider o = new FakeProvider(HooksTest.wire("openai-single"), 0, 18787)) {
            OpenAIClient openai = OpenAIOkHttpClient.builder().fromEnv()
                    .addInterceptor(new DiglineOkHttp(recorder)).build();
            lookups = openai;
            String ticket = "Where is A1?";
            Agent agent = asked -> {
                openai.chat().completions().create(params);
                return "A1 left on Monday.";
            };
            // page:
            try (var episode = recorder.episode("order-agent", Map.of("ticket", ticket));
                    // The turn's calls name their suite here, or they are _unassigned.
                    var calls = DiglineRecorder.suite("order-agent")) {
                try {
                    String answer = agent.answer(ticket);
                    episode.output(answer);
                } catch (RuntimeException failed) {
                    episode.interrupted();
                    throw failed;
                }
            }
            // end
            Agent failing = asked -> {
                openai.chat().completions().create(params);
                throw new IllegalStateException("the lookup failed");
            };
            assertThrows(IllegalStateException.class, () -> {
                try (var episode = recorder.episode("order-agent", Map.of("ticket", ticket))) {
                    try {
                        String answer = failing.answer(ticket);
                        episode.output(answer);
                    } catch (RuntimeException failed) {
                        episode.interrupted();
                        throw failed;
                    }
                }
            });
            ExecutorService pool = Executors.newSingleThreadExecutor();
            String order = "A1";
            try (var episode = recorder.episode("order-agent", Map.of("ticket", ticket))) {
                // page:
                String id = episode.id();
                pool.submit(() -> {
                    try (var attached = DiglineRecorder.attach(id)) {
                        return lookup(order);
                    }
                });
                // end
                pool.shutdown();
                assertTrue(pool.awaitTermination(10, TimeUnit.SECONDS));
                episode.output("A1 left on Monday.");
            }
        }
        List<Map<String, Object>> written = recordings();
        assertEquals(6, written.size());
        // The turn, and its call, which names the suite the scope inside it named.
        assertEquals(written.get(1).get("id"), written.get(0).get("episode"));
        assertEquals("order-agent", written.get(0).get("suite"));
        // The turn that failed: written with what was seen, and said interrupted.
        assertEquals(Boolean.TRUE, written.get(3).get("interrupted"));
        assertEquals(written.get(3).get("id"), written.get(2).get("episode"));
        // The call made on the pool's thread, attached to its turn.
        assertEquals(written.get(5).get("id"), written.get(4).get("episode"));
        assertTrue(written.stream().noneMatch(each -> each.containsKey("orphan")));
    }

    @Test
    void production() throws IOException {
        switchOn("on = true\nsample = 1\nredact = \"none\"\nceiling = 1000000\n");
        // page:
        DiglineRecorder recorder = DiglineRecorder.production(root, () -> tenantOf(request), "support");
        // end
        assertTrue(recorder.on());
    }

    @Test
    void anAsynchronousCallMadeOnAThreadThatNamesIt() throws Exception {
        switchOn("on = true\n");
        DiglineRecorder recorder = DiglineRecorder.development(root, "acme", "support");
        ExecutorService pool = Executors.newSingleThreadExecutor();
        ChatCompletion answered;
        String turn;
        try (FakeProvider o = new FakeProvider(HooksTest.wire("openai-single"), 0, 18787)) {
            OpenAIClient openai = OpenAIOkHttpClient.builder().fromEnv()
                    .addInterceptor(new DiglineOkHttp(recorder)).build();
            try (var episode = recorder.episode("order-agent", Map.of("ticket", "A1"))) {
                turn = episode.id();
                // page:
                String id = episode.id();
                CompletableFuture<ChatCompletion> later = CompletableFuture.supplyAsync(() -> {
                    try (var attached = DiglineRecorder.attach(id);
                            var suite = DiglineRecorder.suite("refunds")) {
                        return openai.chat().completions().create(params);
                    }
                }, pool);
                // end
                answered = later.get(10, TimeUnit.SECONDS);
                episode.output("A1 left on Monday.");
            }
        } finally {
            pool.shutdown();
        }
        assertEquals("Je regarde.", answered.choices().get(0).message().content().orElseThrow());
        Map<String, Object> call = recordings().get(0);
        assertEquals("refunds", call.get("suite"));
        assertEquals(turn, call.get("episode"));
        assertTrue(!call.containsKey("orphan"));
    }

    @Test
    void aClientAFrameworkBuildsAndTheSuiteNamedByTheOneMethod() throws IOException {
        switchOn("on = true\n");
        DiglineRecorder recorder = DiglineRecorder.development(root, "acme", "support");
        try (FakeProvider b = new FakeProvider(HooksTest.wire("bedrock-single"), 0, 18788)) {
            // page:
            BedrockRuntimeClient client = BedrockRuntimeClient.builder()
                    .overrideConfiguration(c -> c.addExecutionInterceptor(new DiglineAws(recorder)))
                    .build();
            // end
            ask("triage", () -> client.converse(ConverseRequest.builder().modelId(HooksTest.MODEL)
                    .messages(HooksTest.bedrockAsked()).build()));
            client.close();
        }
        Map<String, Object> call = recordings().get(0);
        assertEquals("triage", call.get("suite"));
        // Named by the suite: no call site is written beside it.
        assertTrue(!call.containsKey("call_site"));
    }

    // page:
    <T> T ask(String feature, Supplier<T> call) {
        try (var suite = DiglineRecorder.suite(feature)) {
            return call.get();
        }
    }
    // end
}
