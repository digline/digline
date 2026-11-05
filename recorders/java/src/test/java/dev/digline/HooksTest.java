package dev.digline;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.anthropic.client.AnthropicClient;
import com.anthropic.client.okhttp.AnthropicOkHttpClient;
import com.anthropic.core.http.StreamResponse;
import com.anthropic.models.messages.MessageCreateParams;
import com.anthropic.models.messages.RawMessageStreamEvent;
import com.openai.client.OpenAIClient;
import com.openai.client.okhttp.OpenAIOkHttpClient;
import com.openai.models.chat.completions.ChatCompletion;
import com.openai.models.chat.completions.ChatCompletionChunk;
import com.openai.models.chat.completions.ChatCompletionCreateParams;
import java.io.IOException;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Stream;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import software.amazon.awssdk.auth.credentials.AwsBasicCredentials;
import software.amazon.awssdk.auth.credentials.StaticCredentialsProvider;
import software.amazon.awssdk.http.Protocol;
import software.amazon.awssdk.http.nio.netty.NettyNioAsyncHttpClient;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.bedrockruntime.BedrockRuntimeAsyncClient;
import software.amazon.awssdk.services.bedrockruntime.BedrockRuntimeClient;
import software.amazon.awssdk.core.SdkBytes;
import software.amazon.awssdk.services.bedrockruntime.model.ContentBlock;
import software.amazon.awssdk.services.bedrockruntime.model.ConversationRole;
import software.amazon.awssdk.services.bedrockruntime.model.ConverseRequest;
import software.amazon.awssdk.services.bedrockruntime.model.ConverseResponse;
import software.amazon.awssdk.services.bedrockruntime.model.ConverseStreamRequest;
import software.amazon.awssdk.services.bedrockruntime.model.ConverseStreamResponseHandler;
import software.amazon.awssdk.services.bedrockruntime.model.InvokeModelRequest;
import software.amazon.awssdk.services.bedrockruntime.model.InvokeModelWithResponseStreamRequest;
import software.amazon.awssdk.services.bedrockruntime.model.InvokeModelWithResponseStreamResponseHandler;

/**
 * Each hook, installed the way its page says, on the SDK's real client, which
 * calls a fake provider on 127.0.0.1 that answers with a wire fixture. The
 * recording the hook writes is held to what its reading makes of the request
 * the SDK actually sent and the reply the provider gave, and that reading is
 * held to digline's own map by {@link WireFixturesTest}.
 */
class HooksTest {

    @TempDir
    Path root;

    static final String MODEL = "anthropic.claude-3-5-haiku-20241022-v1:0";

    DiglineRecorder recorder() throws IOException {
        Path tenant = root.resolve(".digline").resolve("acme");
        Files.createDirectories(tenant);
        Files.writeString(tenant.resolve("recorder.toml"), "on = true\n", StandardCharsets.UTF_8);
        return DiglineRecorder.development(root, "acme", "support");
    }

    @SuppressWarnings("unchecked")
    static Map<String, Object> wire(String name) throws IOException {
        return (Map<String, Object>) DiglineRecorder.Json.parse(Files.readString(
                FixturesTest.fixtures().resolve("wire").resolve(name + ".json")));
    }

    List<Map<String, Object>> recordings() throws IOException {
        Path directory = root.resolve(".digline/acme/recordings");
        if (!Files.isDirectory(directory)) {
            return List.of();
        }
        try (Stream<Path> found = Files.walk(directory)) {
            return found.filter(path -> path.getFileName().toString().matches("\\d{6}\\.json")).sorted()
                    .map(RecorderTest::documentOrThrow).toList();
        }
    }

    /**
     * The one recording written, against what the hook's reading makes of
     * the request the SDK sent and the fixture's reply, at the latency and
     * the time the recording itself says.
     */
    void heldToItsReading(Map<String, Object> wire, FakeProvider provider) throws IOException {
        List<Map<String, Object>> written = recordings();
        assertEquals(1, written.size(), written.toString());
        Map<String, Object> recording = written.get(0);
        @SuppressWarnings("unchecked")
        Map<String, Object> response = (Map<String, Object>) recording.get("response");
        double latency = (Double) response.get("latency_ms");
        assertTrue(latency > 0);
        Map<String, Object> sent = new LinkedHashMap<>(wire);
        sent.put("request", provider.sent());
        if ("bedrock".equals(wire.get("route"))) {
            assertTrue(provider.path.endsWith(wire.get("path").toString().replaceFirst("^.*/", "/")),
                    provider.path);
        }
        Map<String, Object> expected = DiglineRecorder.singleDocument("acme", "support", "refunds",
                WireFixturesTest.read(sent, latency), (String) recording.get("recorded_at"));
        assertEquals(DiglineRecorder.Json.file(expected), DiglineRecorder.Json.file(recording));
    }

    OpenAIClient openai(FakeProvider provider, DiglineRecorder recorder) {
        return OpenAIOkHttpClient.builder().baseUrl(provider.url() + "/v1").apiKey("k").maxRetries(0)
                .addInterceptor(new DiglineOkHttp(recorder)).build();
    }

    AnthropicClient anthropic(FakeProvider provider, DiglineRecorder recorder) {
        return AnthropicOkHttpClient.builder().baseUrl(provider.url()).apiKey("k").maxRetries(0)
                .addInterceptor(new DiglineAnthropic(recorder)).build();
    }

    static final ChatCompletionCreateParams OPENAI_ASKED = ChatCompletionCreateParams.builder()
            .model("gpt-4o-mini").addSystemMessage("Answer in one line.")
            .addUserMessage("Où est la commande A1 ?").temperature(0.2).build();

    static final MessageCreateParams ANTHROPIC_ASKED = MessageCreateParams.builder()
            .model("claude-haiku-4-5").maxTokens(256).system("Answer in one line.")
            .addUserMessage("Où est la commande A1 ?").build();

    @Test
    void openAIWhole() throws IOException {
        Map<String, Object> wire = wire("openai-single");
        DiglineRecorder recorder = recorder();
        try (FakeProvider provider = new FakeProvider(wire);
                var suite = DiglineRecorder.suite("refunds")) {
            ChatCompletion reply = openai(provider, recorder).chat().completions().create(OPENAI_ASKED);
            assertEquals("Je regarde.", reply.choices().get(0).message().content().orElseThrow());
            heldToItsReading(wire, provider);
        }
    }

    @Test
    void openAIStreamed() throws IOException {
        assertEquals("It left on Monday.", openAIStream("openai-stream"));
    }

    @Test
    void openAIStreamedToolCall() throws IOException {
        assertEquals("", openAIStream("openai-stream-tool"));
    }

    String openAIStream(String name) throws IOException {
        Map<String, Object> wire = wire(name);
        DiglineRecorder recorder = recorder();
        StringBuilder text = new StringBuilder();
        try (FakeProvider provider = new FakeProvider(wire);
                var suite = DiglineRecorder.suite("refunds");
                var stream = openai(provider, recorder).chat().completions()
                        .createStreaming(OPENAI_ASKED)) {
            stream.stream().forEach(chunk -> chunk.choices().forEach(
                    choice -> choice.delta().content().ifPresent(text::append)));
            stream.close();
            heldToItsReading(wire, provider);
        }
        return text.toString();
    }

    @Test
    void anthropicWhole() throws IOException {
        Map<String, Object> wire = wire("anthropic-single");
        DiglineRecorder recorder = recorder();
        try (FakeProvider provider = new FakeProvider(wire);
                var suite = DiglineRecorder.suite("refunds")) {
            var reply = anthropic(provider, recorder).messages().create(ANTHROPIC_ASKED);
            assertEquals(3, reply.content().size());
            heldToItsReading(wire, provider);
        }
    }

    @Test
    void anthropicStreamed() throws IOException {
        Map<String, Object> wire = wire("anthropic-stream");
        DiglineRecorder recorder = recorder();
        int[] events = {0};
        try (FakeProvider provider = new FakeProvider(wire);
                var suite = DiglineRecorder.suite("refunds");
                StreamResponse<RawMessageStreamEvent> stream = anthropic(provider, recorder).messages()
                        .createStreaming(ANTHROPIC_ASKED)) {
            stream.stream().forEach(event -> events[0]++);
            stream.close();
            heldToItsReading(wire, provider);
        }
        assertEquals(11, events[0]);
    }

    /** The request body of a wire fixture, as InvokeModel sends it. */
    static SdkBytes bodyOf(Map<String, Object> wire) {
        return SdkBytes.fromUtf8String(DiglineRecorder.Json.compact(wire.get("request")));
    }

    @Test
    void bedrockInvokeModel() throws IOException {
        Map<String, Object> wire = wire("bedrock-invoke");
        DiglineRecorder recorder = recorder();
        try (FakeProvider provider = new FakeProvider(wire);
                var suite = DiglineRecorder.suite("refunds");
                BedrockRuntimeClient client = bedrock(provider, recorder)) {
            String reply = client.invokeModel(InvokeModelRequest.builder()
                    .modelId((String) wire.get("model_id")).body(bodyOf(wire)).build())
                    .body().asUtf8String();
            // The application reads the reply the server sent, whole.
            assertTrue(reply.contains("\"stop_reason\":\"tool_use\""), reply);
            heldToItsReading(wire, provider);
        }
    }

    @Test
    void bedrockInvokeModelWithResponseStream() throws Exception {
        Map<String, Object> wire = wire("bedrock-invoke-stream");
        DiglineRecorder recorder = recorder();
        int[] events = {0};
        try (FakeProvider provider = new FakeProvider(wire);
                var suite = DiglineRecorder.suite("refunds");
                BedrockRuntimeAsyncClient client = BedrockRuntimeAsyncClient.builder()
                        .endpointOverride(URI.create(provider.url())).region(Region.US_EAST_1)
                        .credentialsProvider(StaticCredentialsProvider.create(
                                AwsBasicCredentials.create("a", "b")))
                        .overrideConfiguration(c -> c.addExecutionInterceptor(new DiglineAws(recorder)))
                        .httpClientBuilder(NettyNioAsyncHttpClient.builder().protocol(Protocol.HTTP1_1))
                        .build()) {
            client.invokeModelWithResponseStream(InvokeModelWithResponseStreamRequest.builder()
                    .modelId((String) wire.get("model_id")).body(bodyOf(wire)).build(),
                    InvokeModelWithResponseStreamResponseHandler.builder()
                            .subscriber(event -> events[0]++).build())
                    .get();
            heldToItsReading(wire, provider);
        }
        assertEquals(9, events[0]);
    }

    @Test
    void anotherFamilyIsCountedAndSaidOnceNotRecorded() throws IOException {
        Map<String, Object> wire = wire("bedrock-invoke");
        DiglineRecorder recorder = recorder();
        java.io.PrintStream err = System.err;
        java.io.ByteArrayOutputStream said = new java.io.ByteArrayOutputStream();
        System.setErr(new java.io.PrintStream(said, true, StandardCharsets.UTF_8));
        try (FakeProvider provider = new FakeProvider(wire);
                var suite = DiglineRecorder.suite("refunds");
                BedrockRuntimeClient client = bedrock(provider, recorder)) {
            for (String model : List.of("amazon.titan-text-express-v1", "amazon.titan-text-lite-v1",
                    "cohere.embed-english-v3", "us.meta.llama3-1-8b-instruct-v1:0")) {
                client.invokeModel(InvokeModelRequest.builder().modelId(model)
                        .body(bodyOf(wire)).build()).body().asUtf8String();
            }
        } finally {
            System.setErr(err);
        }
        assertEquals(List.of(), recordings());
        assertEquals(Map.of("model family not recorded", 3L, "embeddings not recorded", 1L),
                recorder.counts().get("not_recorded"));
        String text = said.toString(StandardCharsets.UTF_8);
        // Once a family: Titan's second model says nothing more.
        assertTrue(text.contains("digline recorder: invoke_model on amazon.titan-text-express-v1: "
                + "this model family is not recorded"), text);
        assertFalse(text.contains("amazon.titan-text-lite-v1"), text);
        assertTrue(text.contains("invoke_model on cohere.embed-english-v3: embeddings are not recorded"),
                text);
        assertTrue(text.contains("invoke_model on us.meta.llama3-1-8b-instruct-v1:0: "
                + "this model family is not recorded"), text);
    }

    @Test
    void theRegionPrefixIsTakenOffBeforeTheVendorIsRead() {
        for (String prefix : List.of("", "us.", "eu.", "apac.", "global.")) {
            assertEquals(List.of("anthropic", "messages"),
                    List.of(DiglineAws.familyOf(prefix + "anthropic.claude-3-5-haiku-20241022-v1:0")));
            assertEquals(List.of("amazon", "other"),
                    List.of(DiglineAws.familyOf(prefix + "amazon.titan-text-express-v1")));
        }
        assertEquals(List.of("anthropic", "messages"), List.of(DiglineAws.familyOf(
                "arn:aws:bedrock:us-east-1:123:inference-profile/us.anthropic.claude-3-haiku")));
        assertEquals(List.of("amazon", "embeddings"),
                List.of(DiglineAws.familyOf("amazon.titan-embed-text-v2:0")));
    }

    BedrockRuntimeClient bedrock(FakeProvider provider, DiglineRecorder recorder) {
        return BedrockRuntimeClient.builder().endpointOverride(URI.create(provider.url()))
                .region(Region.US_EAST_1)
                .credentialsProvider(StaticCredentialsProvider.create(AwsBasicCredentials.create("a", "b")))
                .overrideConfiguration(c -> c.addExecutionInterceptor(new DiglineAws(recorder))).build();
    }

    static software.amazon.awssdk.services.bedrockruntime.model.Message bedrockAsked() {
        return software.amazon.awssdk.services.bedrockruntime.model.Message.builder()
                .role(ConversationRole.USER).content(ContentBlock.fromText("Où est la commande A1 ?"))
                .build();
    }

    @Test
    void bedrockConverse() throws IOException {
        Map<String, Object> wire = wire("bedrock-single");
        DiglineRecorder recorder = recorder();
        try (FakeProvider provider = new FakeProvider(wire);
                var suite = DiglineRecorder.suite("refunds");
                BedrockRuntimeClient client = bedrock(provider, recorder)) {
            ConverseResponse reply = client.converse(ConverseRequest.builder().modelId(MODEL)
                    .messages(bedrockAsked()).build());
            assertEquals("Je regarde.", reply.output().message().content().get(0).text());
            heldToItsReading(wire, provider);
        }
    }

    @Test
    void bedrockConverseStream() throws Exception {
        Map<String, Object> wire = wire("bedrock-stream");
        DiglineRecorder recorder = recorder();
        int[] events = {0};
        try (FakeProvider provider = new FakeProvider(wire);
                var suite = DiglineRecorder.suite("refunds");
                BedrockRuntimeAsyncClient client = BedrockRuntimeAsyncClient.builder()
                        .endpointOverride(URI.create(provider.url())).region(Region.US_EAST_1)
                        .credentialsProvider(StaticCredentialsProvider.create(
                                AwsBasicCredentials.create("a", "b")))
                        .overrideConfiguration(c -> c.addExecutionInterceptor(new DiglineAws(recorder)))
                        // The fake provider speaks HTTP/1.1, where Bedrock speaks
                        // HTTP/2 to this operation: the hook sits above both.
                        .httpClientBuilder(NettyNioAsyncHttpClient.builder().protocol(Protocol.HTTP1_1))
                        .build()) {
            client.converseStream(ConverseStreamRequest.builder().modelId(MODEL)
                    .messages(bedrockAsked()).build(),
                    ConverseStreamResponseHandler.builder().subscriber(event -> events[0]++).build())
                    .get();
            heldToItsReading(wire, provider);
        }
        assertEquals(10, events[0]);
    }

    @Test
    void anAsynchronousCallDoesNotCarryItsThreadsSuite() throws Exception {
        DiglineRecorder recorder = recorder();
        try (FakeProvider anthropicProvider = new FakeProvider(wire("anthropic-single"));
                FakeProvider openaiProvider = new FakeProvider(wire("openai-single"));
                var suite = DiglineRecorder.suite("refunds");
                var episode = recorder.episode("agent", Map.of("ticket", "A1"))) {
            anthropic(anthropicProvider, recorder).async().messages().create(ANTHROPIC_ASKED).get();
            openai(openaiProvider, recorder).async().chat().completions().create(OPENAI_ASKED).get();
            episode.output("done");
        }
        List<Map<String, Object>> written = recordings().subList(0, 2);
        // In no episode either: each is an orphan of the one open.
        assertEquals(List.of(true, true), written.stream().map(each -> each.get("orphan")).toList());
        assertEquals(List.of(false, false),
                written.stream().map(each -> each.containsKey("episode")).toList());
        // Neither SDK's asynchronous client calls the hook on the calling
        // thread, so neither call carries the suite named there.
        assertEquals(List.of("_unassigned", "_unassigned"),
                written.stream().map(each -> each.get("suite")).toList());
    }

    @Test
    void anAttachInTheCallbackComesTooLate() throws Exception {
        DiglineRecorder recorder = recorder();
        try (FakeProvider provider = new FakeProvider(wire("openai-single"));
                var episode = recorder.episode("agent", Map.of("ticket", "A1"))) {
            String id = episode.id();
            openai(provider, recorder).async().chat().completions().create(OPENAI_ASKED)
                    .thenApply(reply -> {
                        try (var attached = DiglineRecorder.attach(id);
                                var suite = DiglineRecorder.suite("refunds")) {
                            return reply;
                        }
                    }).get();
            episode.output("done");
        }
        // The call was made, and recorded, before the callback ran.
        Map<String, Object> call = recordings().get(0);
        assertEquals("_unassigned", call.get("suite"));
        assertEquals(Boolean.TRUE, call.get("orphan"));
        assertFalse(call.containsKey("call_site"));
    }

    @Test
    void aCallThatNamesNoSuiteSaysWhereItWasMadeAndTheDigestDoesNotMove() throws IOException {
        DiglineRecorder recorder = recorder();
        try (FakeProvider provider = new FakeProvider(wire("anthropic-single"))) {
            AnthropicClient client = anthropic(provider, recorder);
            client.messages().create(ANTHROPIC_ASKED);
            try (var suite = DiglineRecorder.suite("refunds")) {
                client.messages().create(ANTHROPIC_ASKED);
            }
        }
        List<Map<String, Object>> written = recordings();
        // `class:method` of the application's frame, as digline's Python
        // recorder writes `module:function`.
        assertEquals(getClass().getName() + ":aCallThatNamesNoSuiteSaysWhereItWasMadeAndTheDigestDoesNotMove",
                written.get(0).get("call_site"));
        assertFalse(written.get(1).containsKey("call_site"));
        // The call site is beside the setup, never in it.
        assertEquals(written.get(0).get("setup_digest"), written.get(1).get("setup_digest"));
    }

    @Test
    void offTheHooksRecordNothingAndTheCallsGoOn() throws IOException {
        DiglineRecorder recorder = DiglineRecorder.development(root, "acme", "support");
        try (FakeProvider provider = new FakeProvider(wire("openai-single"))) {
            openai(provider, recorder).chat().completions().create(OPENAI_ASKED);
        }
        try (FakeProvider provider = new FakeProvider(wire("anthropic-single"))) {
            anthropic(provider, recorder).messages().create(ANTHROPIC_ASKED);
        }
        try (FakeProvider provider = new FakeProvider(wire("bedrock-single"));
                BedrockRuntimeClient client = bedrock(provider, recorder)) {
            client.converse(ConverseRequest.builder().modelId(MODEL).messages(bedrockAsked()).build());
        }
        assertFalse(Files.exists(root.resolve(".digline")));
        assertEquals(0L, recorder.counts().get("recorded"));
    }

    @Test
    void aReplyTheHookCannotReadReachesTheApplicationAndIsCounted() throws IOException {
        Map<String, Object> wire = new LinkedHashMap<>(wire("openai-single"));
        Map<String, Object> reply = new LinkedHashMap<>(DiglineRecorder.asMap(wire.get("reply")));
        reply.put("choices", List.of());
        wire.put("reply", reply);
        DiglineRecorder recorder = recorder();
        try (FakeProvider provider = new FakeProvider(wire)) {
            ChatCompletion answered = openai(provider, recorder).chat().completions().create(OPENAI_ASKED);
            assertEquals(List.of(), answered.choices());
        }
        assertEquals(List.of(), recordings());
        assertEquals(Map.of("map", 1L), recorder.counts().get("not_recorded"));
    }

    @Test
    void aStreamClosedBeforeItsEndIsAbandoned() throws IOException {
        DiglineRecorder recorder = recorder();
        try (FakeProvider provider = new FakeProvider(wire("anthropic-stream"), 500);
                StreamResponse<RawMessageStreamEvent> stream = anthropic(provider, recorder).messages()
                        .createStreaming(ANTHROPIC_ASKED)) {
            stream.stream().findFirst();
        }
        try (FakeProvider provider = new FakeProvider(wire("openai-stream"), 500);
                var stream = openai(provider, recorder).chat().completions().createStreaming(OPENAI_ASKED)) {
            ChatCompletionChunk first = stream.stream().findFirst().orElseThrow();
            assertEquals("gpt-4o-mini", first.model());
        }
        assertEquals(List.of(), recordings());
        assertEquals(Map.of("stream abandoned", 2L), recorder.counts().get("not_recorded"));
    }

    @Test
    void aStreamClosedAfterItsLastEventIsWhole() throws IOException {
        Map<String, Object> wire = wire("anthropic-stream");
        DiglineRecorder recorder = recorder();
        try (FakeProvider provider = new FakeProvider(wire, -2000);
                var suite = DiglineRecorder.suite("refunds")) {
            try (StreamResponse<RawMessageStreamEvent> stream = anthropic(provider, recorder).messages()
                    .createStreaming(ANTHROPIC_ASKED)) {
                // The application stops at message_stop and closes, before the
                // server has closed the connection.
                assertTrue(stream.stream().anyMatch(event -> event.isMessageStop()));
            }
            heldToItsReading(wire, provider);
        }
    }

    @Test
    void offTheOkHttpHookDoesNotReadTheRequest() throws IOException {
        DiglineRecorder recorder = DiglineRecorder.development(root, "acme", "support");
        int[] written = {0};
        okhttp3.RequestBody body = new okhttp3.RequestBody() {
            @Override
            public okhttp3.MediaType contentType() {
                return okhttp3.MediaType.get("application/json");
            }

            @Override
            public void writeTo(okio.BufferedSink sink) throws IOException {
                written[0]++;
                sink.writeUtf8("{\"model\":\"gpt-4o-mini\",\"messages\":[]}");
            }
        };
        try (FakeProvider provider = new FakeProvider(wire("openai-single"))) {
            okhttp3.OkHttpClient client = new okhttp3.OkHttpClient.Builder()
                    .addInterceptor(new DiglineOkHttp(recorder)).build();
            try (okhttp3.Response response = client.newCall(new okhttp3.Request.Builder()
                    .url(provider.url() + "/v1/chat/completions").post(body).build()).execute()) {
                assertEquals(200, response.code());
            }
        }
        // Once, by OkHttp sending it: off, the hook costs one test and reads nothing.
        assertEquals(1, written[0]);
    }

    @Test
    void aCallMadeThroughLangChain4jNamesTheApplicationsFrameNotTheLibrarys() throws IOException {
        DiglineRecorder recorder = recorder();
        try (FakeProvider provider = new FakeProvider(wire("anthropic-single"))) {
            new dev.langchain4j.fake.ChatModel(anthropic(provider, recorder)).chat(ANTHROPIC_ASKED);
        }
        // The frame that called the SDK is in dev.langchain4j: skipped, as
        // the SDKs' own are, so the call site is the code that asked.
        assertEquals(getClass().getName()
                + ":aCallMadeThroughLangChain4jNamesTheApplicationsFrameNotTheLibrarys",
                recordings().get(0).get("call_site"));
    }

    @Test
    void aCallInAnEpisodeCarriesItsId() throws IOException {
        DiglineRecorder recorder = recorder();
        String id;
        try (FakeProvider provider = new FakeProvider(wire("anthropic-single"));
                var episode = recorder.episode("agent", Map.of("ticket", "A1"))) {
            id = episode.id();
            anthropic(provider, recorder).messages().create(ANTHROPIC_ASKED);
        }
        List<Map<String, Object>> written = recordings();
        assertEquals(2, written.size());
        assertEquals(id, written.get(0).get("episode"));
        assertEquals(id, written.get(1).get("id"));
        assertTrue(((String) written.get(0).get("call_site")).startsWith(getClass().getName() + ":"),
                (String) written.get(0).get("call_site"));
    }
}
