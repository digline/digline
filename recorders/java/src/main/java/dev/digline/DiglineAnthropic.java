/*
 * digline's recorder for Java: the hook for the official Anthropic Java SDK,
 * whose builder takes an interceptor of its own and not an OkHttp one.
 *
 * RECORDING_VERSION 1, written to the contract as it stood on 2026-11-05:
 * https://github.com/digline/digline/blob/main/docs/recording-format.md
 *
 * Copy it beside DiglineRecorder.java, under the package dev.digline. It needs
 * anthropic-java on the classpath.
 *
 * Licensed as digline is: Apache-2.0.
 */
package dev.digline;

import com.anthropic.core.RequestOptions;
import com.anthropic.core.http.Headers;
import com.anthropic.core.http.HttpClient;
import com.anthropic.core.http.HttpMethod;
import com.anthropic.core.http.HttpRequest;
import com.anthropic.core.http.HttpResponse;
import com.anthropic.core.http.Interceptor;
import java.io.ByteArrayOutputStream;
import java.io.FilterInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import java.util.concurrent.CompletableFuture;

/**
 * Records the Messages calls the official Anthropic Java SDK makes, whole or
 * streamed, through a {@link DiglineRecorder}:
 *
 * <pre>{@code
 * AnthropicClient client = AnthropicOkHttpClient.builder()
 *         .fromEnv()
 *         .addInterceptor(new DiglineAnthropic(recorder))
 *         .build();
 * }</pre>
 *
 * <p>The request is read as digline's Anthropic map reads it: the messages
 * are the case, and the setup is everything else but how the request travels
 * and {@code metadata}, which names who the request is for. The reply is read
 * as the plugin's {@code completion_of} reads it, and a stream as the SDK
 * folds its events, when the application has read it to its end.
 *
 * <p><b>It never fails the call.</b> A request or a reply it cannot read is
 * counted, and the reply reaches the application as the server sent it.
 */
public final class DiglineAnthropic implements Interceptor {

    /** The request's keys that are neither the case nor the setup. */
    static final Set<String> NOT_SETUP = Set.of("messages", "stream", "extra_headers",
            "extra_query", "timeout", "metadata");

    /** {@code stop_reason} in digline's vocabulary. */
    static final Map<String, String> FINISH = Map.of("end_turn", "stop", "stop_sequence", "stop",
            "max_tokens", "length", "model_context_window_exceeded", "length", "tool_use",
            "tool_use", "refusal", "filtered", "pause_turn", "other");

    /** The blocks whose input arrives as JSON in pieces. */
    static final Set<String> TRACKS_TOOL_INPUT = Set.of("tool_use", "server_tool_use");

    private final DiglineRecorder recorder;

    public DiglineAnthropic(DiglineRecorder recorder) {
        this.recorder = recorder;
    }

    @Override
    public HttpClient intercept(HttpClient next) {
        return new HttpClient() {
            @Override
            public HttpResponse execute(HttpRequest request, RequestOptions options) {
                Watched watched = watch(request);
                if (watched == null) {
                    return next.execute(request, options);
                }
                return watched.reply(next.execute(watched.request, options));
            }

            @Override
            public CompletableFuture<HttpResponse> executeAsync(HttpRequest request,
                    RequestOptions options) {
                Watched watched = watch(request);
                if (watched == null) {
                    return next.executeAsync(request, options);
                }
                return next.executeAsync(watched.request, options).thenApply(watched::reply);
            }

            @Override
            public void close() {
                next.close();
            }
        };
    }

    /** A call this hook reads, or {@code null} for one it lets through untouched. */
    private Watched watch(HttpRequest request) {
        try {
            List<String> path = request.pathSegments();
            if (!recorder.on() || request.method() != HttpMethod.POST || path.size() < 2
                    || !path.get(path.size() - 1).equals("messages")
                    || !path.get(path.size() - 2).equals("v1") || request.body().isEmpty()) {
                return null;
            }
        } catch (RuntimeException unknown) {
            return null;
        }
        DiglineRecorder.Captured at = recorder.capture();
        HttpRequest buffered = request.buffered();
        try {
            ByteArrayOutputStream body = new ByteArrayOutputStream();
            buffered.body().orElseThrow().writeTo(body);
            Map<String, Object> sent = DiglineOkHttp.asMap(
                    DiglineRecorder.Json.parse(body.toString(StandardCharsets.UTF_8)));
            return new Watched(buffered, sent, at);
        } catch (RuntimeException notJson) {
            recorder.miss("not JSON", at);
            return new Watched(buffered, null, at);
        }
    }

    /** One call under way: the request sent, and when. */
    private final class Watched {
        final HttpRequest request;
        final Map<String, Object> sent;
        final DiglineRecorder.Captured at;
        final long started = System.nanoTime();

        Watched(HttpRequest request, Map<String, Object> sent, DiglineRecorder.Captured at) {
            this.request = request;
            this.sent = sent;
            this.at = at;
        }

        HttpResponse reply(HttpResponse response) {
            if (sent == null || response.statusCode() < 200 || response.statusCode() > 299) {
                return response;
            }
            boolean streamed = response.headers().values("Content-Type").stream()
                    .anyMatch(value -> value.contains("text/event-stream"));
            return new Replaced(response, new Kept(response.body(),
                    (kept, whole) -> ended(kept, whole, streamed)));
        }

        /**
         * The body, as the application read it: at its end, or when it was
         * closed. A stream closed before its end was abandoned; a whole reply
         * is read from what was read, which the SDK reads to its last brace.
         */
        void ended(byte[] kept, boolean whole, boolean streamed) {
            try {
                double elapsed = (System.nanoTime() - started) / 1_000_000.0;
                String text = new String(kept, StandardCharsets.UTF_8);
                List<Object> events = streamed ? DiglineRecorder.events(text) : List.of();
                // Closed before its end is abandoned, unless what was read
                // already carries the end: `message_stop`.
                boolean finished = whole || events.stream().anyMatch(event -> event instanceof Map<?, ?> map
                        && "message_stop".equals(map.get("type")));
                if (streamed && !finished) {
                    recorder.miss("stream abandoned", at);
                } else if (streamed) {
                    recorder.record(streamed(sent, events, elapsed), at);
                } else {
                    recorder.record(call(sent, DiglineOkHttp.asMap(DiglineRecorder.Json.parse(text)),
                            elapsed), at);
                }
            } catch (RuntimeException unread) {
                recorder.miss("map", at);
            }
        }
    }

    /** The reply, with its body replaced by one that reads the same bytes. */
    private static final class Replaced implements HttpResponse {
        private final HttpResponse original;
        private final InputStream body;

        Replaced(HttpResponse original, InputStream body) {
            this.original = original;
            this.body = body;
        }

        @Override
        public int statusCode() {
            return original.statusCode();
        }

        @Override
        public Headers headers() {
            return original.headers();
        }

        @Override
        public InputStream body() {
            return body;
        }

        @Override
        public void close() {
            try {
                body.close();
            } catch (IOException ignored) {
                // Closing what was read: nothing the application waits on.
            }
            original.close();
        }
    }

    /**
     * A body that keeps what is read through it, and says what was kept once:
     * at its end, or when it is closed before it, which the second argument
     * tells apart.
     */
    static final class Kept extends FilterInputStream {
        private final ByteArrayOutputStream kept = new ByteArrayOutputStream();
        private final java.util.function.BiConsumer<byte[], Boolean> end;
        private boolean done;

        Kept(InputStream in, java.util.function.BiConsumer<byte[], Boolean> end) {
            super(in);
            this.end = end;
        }

        @Override
        public int read() throws IOException {
            int read = super.read();
            if (read == -1) {
                ended(true);
            } else {
                kept.write(read);
            }
            return read;
        }

        @Override
        public int read(byte[] buffer, int offset, int length) throws IOException {
            int read = super.read(buffer, offset, length);
            if (read == -1) {
                ended(true);
            } else if (read > 0) {
                kept.write(buffer, offset, read);
            }
            return read;
        }

        @Override
        public long skip(long count) throws IOException {
            // Skipped bytes are not read through here, so what is kept would
            // be short: said as an abandoned body rather than misread.
            done = true;
            return super.skip(count);
        }

        @Override
        public void close() throws IOException {
            try {
                super.close();
            } finally {
                ended(false);
            }
        }

        private void ended(boolean whole) {
            if (!done) {
                done = true;
                end.accept(kept.toByteArray(), whole);
            }
        }
    }

    /** One call, whole: the request split, and the reply read. */
    static DiglineRecorder.Call call(Map<String, Object> request, Map<String, Object> reply,
            double latencyMs) {
        Map<String, Object> caseCompartment = new TreeMap<>();
        caseCompartment.put("messages", request.get("messages"));
        Map<String, Object> setup = new TreeMap<>();
        for (Map.Entry<String, Object> entry : request.entrySet()) {
            if (!NOT_SETUP.contains(entry.getKey())) {
                setup.put(entry.getKey(), entry.getValue());
            }
        }
        List<Map<String, Object>> content = new ArrayList<>();
        if (reply.get("content") instanceof List<?> blocks) {
            for (Object block : blocks) {
                content.add(DiglineOkHttp.asMap(block));
            }
        } else {
            throw new IllegalArgumentException("the reply carries no content");
        }
        StringBuilder text = new StringBuilder();
        for (Map<String, Object> block : content) {
            if ("text".equals(block.get("type"))) {
                text.append(block.get("text"));
            }
        }
        return new DiglineRecorder.Call(caseCompartment, setup, text.toString(), latencyMs,
                usage(reply.get("usage")), DiglineRecorder.finishOf(reply.get("stop_reason"), FINISH),
                toolCalls(content));
    }

    /** One call, streamed: its events folded into the message the SDK would build. */
    static DiglineRecorder.Call streamed(Map<String, Object> request, List<Object> events,
            double latencyMs) {
        Map<String, Object> snapshot = null;
        List<Map<String, Object>> content = new ArrayList<>();
        Map<Integer, StringBuilder> inputs = new HashMap<>();
        for (Object raw : events) {
            Map<String, Object> event = DiglineOkHttp.asMap(raw);
            Object type = event.get("type");
            if (snapshot == null) {
                if (!"message_start".equals(type)) {
                    throw new IllegalArgumentException("an event before message_start");
                }
                snapshot = DiglineOkHttp.asMap(event.get("message"));
                if (snapshot.get("content") instanceof List<?> blocks) {
                    for (Object block : blocks) {
                        content.add(DiglineOkHttp.asMap(block));
                    }
                }
                continue;
            }
            if ("content_block_start".equals(type)) {
                content.add(DiglineOkHttp.asMap(event.get("content_block")));
            } else if ("content_block_delta".equals(type)) {
                int at = Math.toIntExact((Long) event.get("index"));
                Map<String, Object> block = content.get(at);
                Map<String, Object> delta = DiglineOkHttp.asMap(event.get("delta"));
                if ("text_delta".equals(delta.get("type")) && "text".equals(block.get("type"))) {
                    block.put("text", String.valueOf(block.get("text")) + delta.get("text"));
                } else if ("input_json_delta".equals(delta.get("type"))
                        && TRACKS_TOOL_INPUT.contains(block.get("type"))) {
                    inputs.computeIfAbsent(at, key -> new StringBuilder())
                            .append((String) delta.get("partial_json"));
                }
            } else if ("message_delta".equals(type)) {
                Map<String, Object> delta = DiglineOkHttp.asMap(event.get("delta"));
                snapshot.put("stop_reason", delta.get("stop_reason"));
                Map<String, Object> usage = snapshot.get("usage") instanceof Map<?, ?>
                        ? DiglineOkHttp.asMap(snapshot.get("usage")) : new LinkedHashMap<>();
                Map<String, Object> more = DiglineOkHttp.asMap(event.get("usage"));
                usage.put("output_tokens", more.get("output_tokens"));
                for (String key : List.of("input_tokens", "cache_creation_input_tokens",
                        "cache_read_input_tokens", "server_tool_use", "output_tokens_details")) {
                    if (more.get(key) != null) {
                        usage.put(key, more.get(key));
                    }
                }
                snapshot.put("usage", usage);
            }
        }
        if (snapshot == null) {
            throw new IllegalArgumentException("the stream ended with no message");
        }
        for (Map.Entry<Integer, StringBuilder> entry : inputs.entrySet()) {
            if (entry.getValue().length() > 0) {
                content.get(entry.getKey()).put("input",
                        DiglineRecorder.Json.parse(entry.getValue().toString()));
            }
        }
        snapshot.put("content", new ArrayList<Object>(content));
        return call(request, snapshot, latencyMs);
    }

    /** The counts, with the cache's beside the input, or {@code null}. */
    static DiglineRecorder.Usage usage(Object raw) {
        if (!(raw instanceof Map<?, ?>)) {
            return null;
        }
        Map<String, Object> usage = DiglineOkHttp.asMap(raw);
        Long input = DiglineOkHttp.count(usage.get("input_tokens"));
        Long output = DiglineOkHttp.count(usage.get("output_tokens"));
        if (input == null || output == null) {
            return null;
        }
        Long read = DiglineOkHttp.count(usage.get("cache_read_input_tokens"));
        Long written = DiglineOkHttp.count(usage.get("cache_creation_input_tokens"));
        Long thinking = null;
        if (usage.get("output_tokens_details") instanceof Map<?, ?> details) {
            thinking = DiglineOkHttp.count(details.get("thinking_tokens"));
        }
        return new DiglineRecorder.Usage(input, output, read == null ? 0 : read,
                written == null ? 0 : written, thinking);
    }

    /**
     * The calls in the reply: a {@code tool_use} the application runs, so
     * {@code not_reported}; a {@code server_tool_use} with its result in the
     * reply, an error by its code or a success whose payload is not recorded.
     * Never {@code null}: the reply always says what the turn held.
     */
    static List<DiglineRecorder.ToolCall> toolCalls(List<Map<String, Object>> content) {
        Map<String, Map<String, Object>> outcomes = new HashMap<>();
        for (Map<String, Object> block : content) {
            if (String.valueOf(block.getOrDefault("type", "")).endsWith("_tool_result")) {
                outcomes.put(String.valueOf(block.getOrDefault("tool_use_id", "")), block);
            }
        }
        List<DiglineRecorder.ToolCall> calls = new ArrayList<>();
        for (Map<String, Object> block : content) {
            Object kind = block.get("type");
            if (!"tool_use".equals(kind) && !"server_tool_use".equals(kind)) {
                continue;
            }
            String name = DiglineOkHttp.name(block.get("name"));
            Object arguments = block.get("input") instanceof Map<?, ?> input ? input : null;
            Map<String, Object> outcome = "server_tool_use".equals(kind)
                    ? outcomes.get(String.valueOf(block.getOrDefault("id", ""))) : null;
            if (outcome == null) {
                calls.add(DiglineRecorder.ToolCall.asked(name, arguments));
                continue;
            }
            String code = null;
            if (outcome.get("content") instanceof Map<?, ?> said && said.get("type") instanceof String word
                    && word.contains("_error")) {
                Object error = said.get("error_code");
                code = DiglineOkHttp.truthy(error) ? String.valueOf(error) : word;
            }
            calls.add(code == null
                    ? new DiglineRecorder.ToolCall(name, arguments, "success", null, "not_recorded")
                    : new DiglineRecorder.ToolCall(name, arguments, "error", code, null));
        }
        return calls;
    }
}
