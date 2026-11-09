/*
 * digline's recorder for Java: the hook for OkHttp, which the official OpenAI
 * Java SDK uses, and any OkHttp client that calls Chat Completions.
 *
 * RECORDING_VERSION 1, written to the contract as it stood on 2026-11-05:
 * https://github.com/digline/digline/blob/main/docs/recording-format.md
 *
 * Copy it beside DiglineRecorder.java, under the package dev.digline. It needs
 * OkHttp 4 on the classpath, which openai-java brings.
 *
 * Licensed as digline is: Apache-2.0.
 */
package dev.digline;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import okhttp3.Interceptor;
import okhttp3.MediaType;
import okhttp3.Request;
import okhttp3.Response;
import okhttp3.ResponseBody;
import okio.Buffer;
import okio.BufferedSource;
import okio.ForwardingSource;
import okio.Okio;
import okio.Source;

/**
 * Records the Chat Completions calls an OkHttp client makes, whole or
 * streamed, through a {@link DiglineRecorder}:
 *
 * <pre>{@code
 * OpenAIClient client = OpenAIOkHttpClient.builder()
 *         .fromEnv()
 *         .addInterceptor(new DiglineOkHttp(recorder))
 *         .build();
 * }</pre>
 *
 * <p>The request is read as digline's OpenAI map reads it: the leading
 * {@code system} and {@code developer} messages are the setup's
 * {@code system}, the rest are the case, and the setup is everything else
 * but how the request travels and who it is for. The reply is read as the
 * plugin's {@code completion_of} reads it, and a stream as the SDK folds its
 * chunks, when the application has read it to its end.
 *
 * <p><b>It never fails the call.</b> A request or a reply it cannot read is
 * counted, and the reply reaches the application as the server sent it.
 */
public final class DiglineOkHttp implements Interceptor {

    /** The request's keys that are neither the case nor the setup. */
    static final Set<String> NOT_SETUP = Set.of("messages", "stream", "stream_options",
            "extra_headers", "extra_query", "timeout", "user", "metadata", "safety_identifier",
            "prompt_cache_key", "store");

    /** The roles of the leading messages that are the setup's {@code system}. */
    static final Set<String> INSTRUCTION_ROLES = Set.of("system", "developer");

    /** {@code finish_reason} in digline's vocabulary. */
    static final Map<String, String> FINISH = Map.of("stop", "stop", "length", "length",
            "tool_calls", "tool_use", "function_call", "tool_use", "content_filter", "filtered");

    private final DiglineRecorder recorder;

    public DiglineOkHttp(DiglineRecorder recorder) {
        this.recorder = recorder;
    }

    @Override
    public Response intercept(Chain chain) throws IOException {
        Request request = chain.request();
        if (!recorder.on() || !"POST".equals(request.method())
                || !request.url().encodedPath().replaceAll("/+$", "").endsWith("/chat/completions")
                || request.body() == null) {
            return chain.proceed(request);
        }
        DiglineRecorder.Captured at = recorder.capture();
        Map<String, Object> sent = null;
        try {
            Buffer body = new Buffer();
            request.body().writeTo(body);
            sent = DiglineRecorder.asMap(DiglineRecorder.Json.parse(body.readString(StandardCharsets.UTF_8)));
        } catch (IOException | RuntimeException notJson) {
            recorder.miss("not JSON", at);
        }
        long started = System.nanoTime();
        Response response = chain.proceed(request);
        if (sent != null && !response.isSuccessful()) {
            recorder.refused(response.code(), at);
        }
        if (sent == null || !response.isSuccessful() || response.body() == null) {
            return response;
        }
        Map<String, Object> asked = sent;
        MediaType type = response.body().contentType();
        if (type != null && "event-stream".equals(type.subtype())) {
            ResponseBody original = response.body();
            ByteArrayOutputStream kept = new ByteArrayOutputStream();
            Source watched = new ForwardingSource(original.source()) {
                private boolean done;

                @Override
                public long read(Buffer sink, long byteCount) throws IOException {
                    long read = super.read(sink, byteCount);
                    if (read > 0) {
                        sink.copyTo(kept, sink.size() - read, read);
                    } else if (read == -1 && !done) {
                        done = true;
                        ended(asked, kept, started, at);
                    }
                    return read;
                }

                @Override
                public void close() throws IOException {
                    try {
                        super.close();
                    } finally {
                        if (!done) {
                            done = true;
                            // The SDK stops reading at `[DONE]` and closes: a
                            // stream that carried its end is whole.
                            if (finished(kept)) {
                                ended(asked, kept, started, at);
                            } else {
                                recorder.miss("stream abandoned", at);
                            }
                        }
                    }
                }
            };
            BufferedSource buffered = Okio.buffer(watched);
            return response.newBuilder()
                    .body(ResponseBody.create(buffered, type, original.contentLength()))
                    .build();
        }
        try {
            String text = response.peekBody(Long.MAX_VALUE).string();
            double elapsed = (System.nanoTime() - started) / 1_000_000.0;
            recorder.record(call(asked, DiglineRecorder.asMap(DiglineRecorder.Json.parse(text)), elapsed), at);
        } catch (IOException | RuntimeException unread) {
            recorder.miss("map", at);
        }
        return response;
    }

    /** Whether what was read of a stream holds its closing {@code [DONE]}. */
    private static boolean finished(ByteArrayOutputStream kept) {
        String text = kept.toString(StandardCharsets.UTF_8).replace("\r\n", "\n");
        return text.contains("\ndata: [DONE]") || text.startsWith("data: [DONE]")
                || text.contains("\ndata:[DONE]");
    }

    /** A stream the application has read to its end: folded, then recorded. */
    private void ended(Map<String, Object> asked, ByteArrayOutputStream kept, long started,
            DiglineRecorder.Captured at) {
        try {
            double elapsed = (System.nanoTime() - started) / 1_000_000.0;
            List<Object> chunks = DiglineRecorder.events(kept.toString(StandardCharsets.UTF_8));
            recorder.record(streamed(asked, chunks, elapsed), at);
        } catch (RuntimeException unread) {
            recorder.miss("map", at);
        }
    }

    /** One call, whole: the request split, and the reply read. */
    static DiglineRecorder.Call call(Map<String, Object> request, Map<String, Object> reply,
            double latencyMs) {
        Map<String, Object> caseCompartment = new TreeMap<>();
        Map<String, Object> setup = new TreeMap<>();
        split(request, caseCompartment, setup);
        List<?> choices = reply.get("choices") instanceof List<?> found ? found : List.of();
        if (choices.isEmpty()) {
            throw new IllegalArgumentException("the provider returned no choices");
        }
        Map<String, Object> choice = DiglineRecorder.asMap(choices.get(0));
        Map<String, Object> message = choice.get("message") instanceof Map<?, ?> ? DiglineRecorder.asMap(choice.get("message"))
                : Map.of();
        String finish = DiglineRecorder.truthy(message.get("refusal")) ? "filtered"
                : DiglineRecorder.finishOf(choice.get("finish_reason"), FINISH);
        Object content = message.get("content");
        return new DiglineRecorder.Call(caseCompartment, setup,
                DiglineRecorder.truthy(content) ? String.valueOf(content) : "", latencyMs, usage(reply.get("usage")),
                finish, toolCalls(message));
    }

    /** One call, streamed: its chunks folded into the reply the SDK would build. */
    static DiglineRecorder.Call streamed(Map<String, Object> request, List<Object> chunks,
            double latencyMs) {
        Map<String, Object> snapshot = null;
        for (Object raw : chunks) {
            Map<String, Object> chunk = DiglineRecorder.asMap(raw);
            List<?> deltas = chunk.get("choices") instanceof List<?> found ? found : List.of();
            if (snapshot == null) {
                snapshot = new LinkedHashMap<>(chunk);
                List<Object> choices = new ArrayList<>(deltas);
                for (Object each : deltas) {
                    Map<String, Object> choice = DiglineRecorder.asMap(each);
                    choices.set(index(choice), firstChoice(choice));
                }
                snapshot.put("choices", choices);
                continue;
            }
            @SuppressWarnings("unchecked")
            List<Object> choices = (List<Object>) snapshot.get("choices");
            for (Object each : deltas) {
                Map<String, Object> choice = DiglineRecorder.asMap(each);
                int at = index(choice);
                Map<String, Object> held;
                if (at < choices.size()) {
                    held = DiglineRecorder.asMap(choices.get(at));
                    held.put("message", accumulate(DiglineRecorder.asMap(held.get("message")), deltaOf(choice)));
                } else {
                    held = firstChoice(choice);
                    choices.add(held);
                }
                if (DiglineRecorder.truthy(choice.get("finish_reason"))) {
                    held.put("finish_reason", choice.get("finish_reason"));
                }
                // `asMap` copies: the choice held is put back where it was.
                choices.set(Math.min(at, choices.size() - 1), held);
            }
            snapshot.put("usage", chunk.get("usage"));
        }
        if (snapshot == null) {
            throw new IllegalArgumentException("the stream ended with no chunk");
        }
        return call(request, snapshot, latencyMs);
    }

    private static Map<String, Object> firstChoice(Map<String, Object> choice) {
        Map<String, Object> held = new LinkedHashMap<>(choice);
        held.remove("delta");
        held.put("message", accumulate(new LinkedHashMap<>(), deltaOf(choice)));
        return held;
    }

    private static Map<String, Object> deltaOf(Map<String, Object> choice) {
        return choice.get("delta") instanceof Map<?, ?> ? DiglineRecorder.asMap(choice.get("delta")) : Map.of();
    }

    private static int index(Map<String, Object> entry) {
        if (!(entry.get("index") instanceof Long at)) {
            throw new IllegalArgumentException("a list delta entry has no integer index");
        }
        return Math.toIntExact(at);
    }

    /** The SDK's {@code accumulate_delta}: strings and numbers add, maps merge, indexed lists merge by index. */
    @SuppressWarnings("unchecked")
    static Map<String, Object> accumulate(Map<String, Object> held, Map<String, Object> delta) {
        Map<String, Object> acc = new LinkedHashMap<>(held);
        for (Map.Entry<String, Object> entry : delta.entrySet()) {
            String key = entry.getKey();
            Object value = entry.getValue();
            if (acc.get(key) == null) {
                if (indexed(value)) {
                    acc.put(key, new ArrayList<>());
                } else {
                    acc.put(key, value);
                    continue;
                }
            }
            Object current = acc.get(key);
            if (key.equals("index") || key.equals("type")) {
                acc.put(key, value);
                continue;
            }
            if (current instanceof String text && value instanceof String more) {
                acc.put(key, text + more);
            } else if (current instanceof Number number && value instanceof Number more
                    && !(current instanceof Boolean)) {
                acc.put(key, number instanceof Long && more instanceof Long
                        ? (Object) (number.longValue() + more.longValue())
                        : (Object) (number.doubleValue() + more.doubleValue()));
            } else if (current instanceof Map<?, ?> && value instanceof Map<?, ?>) {
                acc.put(key, accumulate(DiglineRecorder.asMap(current), DiglineRecorder.asMap(value)));
            } else if (current instanceof List<?> list && value instanceof List<?> more) {
                List<Object> merged = new ArrayList<>((List<Object>) list);
                boolean scalars = merged.stream().allMatch(item -> item instanceof String
                        || item instanceof Number);
                if (scalars && (!merged.isEmpty() || !indexed(more))) {
                    merged.addAll(more);
                } else {
                    for (Object item : more) {
                        Map<String, Object> part = DiglineRecorder.asMap(item);
                        int at = index(part);
                        if (at >= merged.size()) {
                            merged.add(Math.min(at, merged.size()), part);
                        } else {
                            merged.set(at, accumulate(DiglineRecorder.asMap(merged.get(at)), part));
                        }
                    }
                }
                acc.put(key, merged);
            } else {
                acc.put(key, current);
            }
        }
        return acc;
    }

    private static boolean indexed(Object value) {
        if (!(value instanceof List<?> list) || list.isEmpty()) {
            return false;
        }
        for (Object item : list) {
            if (item instanceof Map<?, ?> map && map.containsKey("index")) {
                return true;
            }
        }
        return false;
    }

    /** The case and the setup, as digline's OpenAI map divides a request. */
    static void split(Map<String, Object> request, Map<String, Object> caseCompartment,
            Map<String, Object> setup) {
        Object messages = request.get("messages");
        List<Object> listed = new ArrayList<>();
        if (messages instanceof List<?> list) {
            listed.addAll(list);
        } else {
            listed.add(messages);
        }
        int lead = 0;
        while (lead < listed.size() && listed.get(lead) instanceof Map<?, ?> message
                && INSTRUCTION_ROLES.contains(message.get("role"))) {
            lead++;
        }
        for (Map.Entry<String, Object> entry : request.entrySet()) {
            if (!NOT_SETUP.contains(entry.getKey())) {
                setup.put(entry.getKey(), entry.getValue());
            }
        }
        if (lead > 0) {
            setup.put("system", new ArrayList<>(listed.subList(0, lead)));
        }
        caseCompartment.put("messages", new ArrayList<>(listed.subList(lead, listed.size())));
    }

    /** The counts, with the cached prompt tokens taken out of the input, or {@code null}. */
    static DiglineRecorder.Usage usage(Object raw) {
        if (!(raw instanceof Map<?, ?>)) {
            return null;
        }
        Map<String, Object> usage = DiglineRecorder.asMap(raw);
        Long prompt = DiglineRecorder.count(usage.get("prompt_tokens"));
        Long completion = DiglineRecorder.count(usage.get("completion_tokens"));
        if (prompt == null || completion == null) {
            return null;
        }
        Long reasoning = null;
        if (usage.get("completion_tokens_details") instanceof Map<?, ?> details) {
            reasoning = DiglineRecorder.count(details.get("reasoning_tokens"));
        }
        long cached = 0;
        if (usage.get("prompt_tokens_details") instanceof Map<?, ?> details) {
            Long found = DiglineRecorder.count(details.get("cached_tokens"));
            cached = found == null ? 0 : found;
        }
        return new DiglineRecorder.Usage(Math.max(prompt - cached, 0), completion, cached, 0,
                reasoning);
    }

    /** The calls the model asked for: none reported is {@code null}, never an empty list. */
    static List<DiglineRecorder.ToolCall> toolCalls(Map<String, Object> message) {
        if (message.get("tool_calls") instanceof List<?> calls && !calls.isEmpty()) {
            List<DiglineRecorder.ToolCall> found = new ArrayList<>();
            for (Object each : calls) {
                Map<String, Object> call = DiglineRecorder.asMap(each);
                if ("custom".equals(call.get("type"))) {
                    Map<String, Object> custom = call.get("custom") instanceof Map<?, ?> ? DiglineRecorder.asMap(call.get("custom"))
                            : Map.of();
                    Object input = custom.get("input");
                    found.add(DiglineRecorder.ToolCall.asked(DiglineRecorder.name(custom.get("name")),
                            input instanceof String ? input : null));
                } else {
                    Map<String, Object> function = call.get("function") instanceof Map<?, ?>
                            ? DiglineRecorder.asMap(call.get("function")) : Map.of();
                    found.add(DiglineRecorder.ToolCall.asked(DiglineRecorder.name(function.get("name")),
                            decoded(function.get("arguments"))));
                }
            }
            return found;
        }
        if (message.get("function_call") instanceof Map<?, ?> single) {
            return List.of(DiglineRecorder.ToolCall.asked(DiglineRecorder.name(single.get("name")),
                    decoded(single.get("arguments"))));
        }
        return null;
    }

    private static Object decoded(Object text) {
        if (!(text instanceof String written)) {
            return null;
        }
        try {
            Object found = DiglineRecorder.Json.parse(written);
            return found instanceof Map<?, ?> ? found : written;
        } catch (IllegalArgumentException notJson) {
            return written;
        }
    }
}
