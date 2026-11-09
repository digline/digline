/*
 * digline's recorder for Java: the hook for the AWS SDK v2, for Bedrock's
 * Converse and ConverseStream, and InvokeModel and InvokeModelWithResponseStream
 * with an Anthropic model, whose body is Anthropic's Messages.
 *
 * RECORDING_VERSION 1, written to the contract as it stood on 2026-11-05:
 * https://github.com/digline/digline/blob/main/docs/recording-format.md
 *
 * Copy it beside DiglineRecorder.java and DiglineMessages.java, under the
 * package dev.digline. It needs the AWS SDK v2's bedrockruntime on the
 * classpath.
 *
 * Licensed as digline is: Apache-2.0.
 */
package dev.digline;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.TreeMap;
import java.util.zip.CRC32;
import org.reactivestreams.Publisher;
import org.reactivestreams.Subscriber;
import org.reactivestreams.Subscription;
import software.amazon.awssdk.core.async.AsyncRequestBody;
import software.amazon.awssdk.core.interceptor.Context;
import software.amazon.awssdk.core.interceptor.ExecutionAttribute;
import software.amazon.awssdk.core.interceptor.ExecutionAttributes;
import software.amazon.awssdk.core.interceptor.ExecutionInterceptor;
import software.amazon.awssdk.core.interceptor.SdkExecutionAttribute;
import software.amazon.awssdk.core.sync.RequestBody;

/**
 * Records the Converse and ConverseStream calls a Bedrock runtime client
 * makes, through a {@link DiglineRecorder}:
 *
 * <pre>{@code
 * BedrockRuntimeClient client = BedrockRuntimeClient.builder()
 *         .overrideConfiguration(c -> c.addExecutionInterceptor(new DiglineAws(recorder)))
 *         .build();
 * }</pre>
 *
 * <p>The request is read as digline's Bedrock map reads boto3's: the model's
 * id, which travels in the path, beside the body; the messages are the case,
 * and the setup is everything else but {@code requestMetadata}, which names
 * who or what the request is for. The reply is read as the plugin's
 * {@code completion_of} reads it, and a stream's events as the plugin folds
 * them, when the application has read the stream to its end.
 *
 * <p><b>It never fails the call.</b> A request or a reply it cannot read is
 * counted, and the reply reaches the application as the server sent it.
 */
public final class DiglineAws implements ExecutionInterceptor {

    /** The request's keys that are neither the case nor the setup. */
    static final Set<String> NOT_SETUP = Set.of("messages", "requestMetadata");

    /** {@code stopReason} in digline's vocabulary. */
    static final Map<String, String> FINISH = Map.of("end_turn", "stop", "stop_sequence", "stop",
            "max_tokens", "length", "model_context_window_exceeded", "length", "tool_use",
            "tool_use", "guardrail_intervened", "filtered", "content_filtered", "filtered",
            "malformed_model_output", "other", "malformed_tool_use", "other");

    private static final Set<String> OPERATIONS = Set.of("Converse", "ConverseStream",
            "InvokeModel", "InvokeModelWithResponseStream");

    /**
     * A cross-region inference profile's prefix, before the vendor's name: taken
     * off before the family is read, as digline's Bedrock map takes it.
     */
    static final List<String> REGION_PREFIXES = List.of("us.", "eu.", "apac.", "global.");

    /** The families already said on standard error in this process. */
    private static final Set<String> SAID = java.util.concurrent.ConcurrentHashMap.newKeySet();

    private static final ExecutionAttribute<Watched> WATCHED = new ExecutionAttribute<>(
            "digline.watched");

    private final DiglineRecorder recorder;

    public DiglineAws(DiglineRecorder recorder) {
        this.recorder = recorder;
    }

    /** One call under way: where it was made, when, and what was sent. */
    private final class Watched {
        final DiglineRecorder.Captured at;
        final long started = System.nanoTime();
        final ByteArrayOutputStream sent = new ByteArrayOutputStream();
        /** InvokeModel's name in digline's words, or {@code null} for Converse. */
        final String invoke;
        volatile String modelId;
        volatile boolean ended;

        Watched(DiglineRecorder.Captured at, String operation) {
            this.at = at;
            this.invoke = "InvokeModel".equals(operation) ? "invoke_model"
                    : "InvokeModelWithResponseStream".equals(operation)
                    ? "invoke_model_with_response_stream" : null;
        }

        void ended(byte[] kept, boolean whole, boolean streamed) {
            if (ended) {
                return;
            }
            ended = true;
            if (invoke != null) {
                String[] refusal = refusal(invoke, modelId);
                if (refusal != null) {
                    // Another family's body is not read: counted by its reason,
                    // and said once a family. (P-1543)
                    if (SAID.add(refusal[1])) {
                        System.err.println("digline recorder: " + refusal[2]);
                    }
                    recorder.miss(refusal[0], at);
                    return;
                }
            }
            Map<String, Object> request;
            try {
                request = new LinkedHashMap<>();
                request.put("modelId", modelId);
                request.putAll(DiglineRecorder.asMap(DiglineRecorder.Json.parse(
                        sent.toString(StandardCharsets.UTF_8))));
            } catch (RuntimeException notJson) {
                recorder.miss("not JSON", at);
                return;
            }
            try {
                double elapsed = (System.nanoTime() - started) / 1_000_000.0;
                if (streamed && !whole) {
                    recorder.miss("stream abandoned", at);
                } else if (invoke != null && streamed) {
                    recorder.record(DiglineMessages.streamed(request, chunks(frames(kept)), elapsed),
                            at);
                } else if (invoke != null) {
                    recorder.record(DiglineMessages.call(request, DiglineRecorder.asMap(
                            DiglineRecorder.Json.parse(new String(kept, StandardCharsets.UTF_8))),
                            elapsed), at);
                } else if (streamed) {
                    recorder.record(streamed(request, frames(kept), elapsed), at);
                } else {
                    recorder.record(call(request, DiglineRecorder.asMap(DiglineRecorder.Json.parse(
                            new String(kept, StandardCharsets.UTF_8))), elapsed), at);
                }
            } catch (StreamError failed) {
                recorder.miss("stream error", at);
            } catch (RuntimeException unread) {
                recorder.miss("map", at);
            }
        }
    }

    /**
     * A stream that ended in an error Bedrock sent inside it, after its 200:
     * counted {@code stream error}, as the proxy counts it, not as a reading
     * that failed.
     */
    static final class StreamError extends RuntimeException {
        private static final long serialVersionUID = 1L;

        StreamError() {
            super("the stream carried an exception");
        }
    }

    @Override
    public void beforeExecution(Context.BeforeExecution context, ExecutionAttributes attributes) {
        try {
            String operation = attributes.getAttribute(SdkExecutionAttribute.OPERATION_NAME);
            if (OPERATIONS.contains(operation) && recorder.on()) {
                attributes.putAttribute(WATCHED, new Watched(recorder.capture(), operation));
            }
        } catch (RuntimeException unknown) {
            // Not watched: the call goes on as it would without the hook.
        }
    }

    @Override
    public Optional<RequestBody> modifyHttpContent(Context.ModifyHttpRequest context,
            ExecutionAttributes attributes) {
        Watched watched = attributes.getAttribute(WATCHED);
        if (watched != null && context.requestBody().isPresent()) {
            try {
                watched.modelId = modelIdOf(context.httpRequest().encodedPath());
                try (InputStream body = context.requestBody().get().contentStreamProvider().newStream()) {
                    body.transferTo(watched.sent);
                }
            } catch (Exception unread) {
                attributes.putAttribute(WATCHED, null);
                recorder.miss("not JSON", watched.at);
            }
        }
        return context.requestBody();
    }

    @Override
    public Optional<AsyncRequestBody> modifyAsyncHttpContent(Context.ModifyHttpRequest context,
            ExecutionAttributes attributes) {
        Watched watched = attributes.getAttribute(WATCHED);
        Optional<AsyncRequestBody> body = context.asyncRequestBody();
        if (watched == null || body.isEmpty() || context.requestBody().isPresent()) {
            return body;
        }
        try {
            watched.modelId = modelIdOf(context.httpRequest().encodedPath());
        } catch (RuntimeException unread) {
            return body;
        }
        AsyncRequestBody original = body.get();
        return Optional.of(new AsyncRequestBody() {
            @Override
            public Optional<Long> contentLength() {
                return original.contentLength();
            }

            @Override
            public String contentType() {
                return original.contentType();
            }

            @Override
            public void subscribe(Subscriber<? super ByteBuffer> subscriber) {
                original.subscribe(new Tee(subscriber, watched.sent, (kept, whole) -> { }));
            }
        });
    }

    /**
     * Each response the call received, sync or async, before its body is read:
     * a refusal is counted here, the one place both clients pass for a reply
     * that is not a 2xx.
     */
    @Override
    public void afterTransmission(Context.AfterTransmission context, ExecutionAttributes attributes) {
        Watched watched = attributes.getAttribute(WATCHED);
        if (watched != null && !context.httpResponse().isSuccessful()) {
            recorder.refused(context.httpResponse().statusCode(), watched.at);
        }
    }

    @Override
    public Optional<InputStream> modifyHttpResponseContent(Context.ModifyHttpResponse context,
            ExecutionAttributes attributes) {
        Watched watched = attributes.getAttribute(WATCHED);
        Optional<InputStream> body = context.responseBody();
        if (watched == null || body.isEmpty() || !context.httpResponse().isSuccessful()) {
            return body;
        }
        boolean streamed = eventStream(context);
        return Optional.of(new DiglineRecorder.Kept(body.get(),
                (kept, whole) -> watched.ended(kept, whole, streamed)));
    }

    @Override
    public Optional<Publisher<ByteBuffer>> modifyAsyncHttpResponseContent(
            Context.ModifyHttpResponse context, ExecutionAttributes attributes) {
        Watched watched = attributes.getAttribute(WATCHED);
        Optional<Publisher<ByteBuffer>> body = context.responsePublisher();
        if (watched == null || body.isEmpty() || !context.httpResponse().isSuccessful()) {
            return body;
        }
        boolean streamed = eventStream(context);
        Publisher<ByteBuffer> original = body.get();
        return Optional.of(subscriber -> original.subscribe(new Tee(subscriber,
                new ByteArrayOutputStream(), (kept, whole) -> watched.ended(kept, whole, streamed))));
    }

    private static boolean eventStream(Context.ModifyHttpResponse context) {
        return context.httpResponse().firstMatchingHeader("Content-Type")
                .map(value -> value.contains("eventstream")).orElse(false);
    }

    /**
     * The vendor a model id names, and what its body is to the recorder:
     * {@code messages}, {@code embeddings} or {@code other}, as digline's
     * {@code family_of} reads it. An ARN is read by its last segment.
     */
    static String[] familyOf(String modelId) {
        String name = modelId.substring(modelId.lastIndexOf('/') + 1);
        for (String prefix : REGION_PREFIXES) {
            if (name.startsWith(prefix)) {
                name = name.substring(prefix.length());
                break;
            }
        }
        int dot = name.indexOf('.');
        String vendor = dot < 0 ? name : name.substring(0, dot);
        String family = name.contains("embed") ? "embeddings"
                : "anthropic".equals(vendor) ? "messages" : "other";
        return new String[] {vendor, family};
    }

    /**
     * Why InvokeModel on this model is not recorded, as the reason it is
     * counted as, the family it is said once for and the sentence, or
     * {@code null} for Anthropic's Messages. The words are digline's.
     */
    static String[] refusal(String method, String modelId) {
        String[] found = familyOf(modelId == null ? "" : modelId);
        if ("messages".equals(found[1])) {
            return null;
        }
        if ("embeddings".equals(found[1])) {
            return new String[] {"embeddings not recorded", "bedrock embeddings " + found[0],
                    method + " on " + modelId + ": embeddings are not recorded"};
        }
        return new String[] {"model family not recorded", "bedrock " + found[0],
                method + " on " + modelId + ": this model family is not recorded"};
    }

    /**
     * InvokeModelWithResponseStream's events, each a {@code chunk} whose
     * {@code bytes} carry a Messages event in base64: the events, decoded.
     */
    static List<Object> chunks(List<Object> frames) {
        List<Object> events = new ArrayList<>();
        for (Object frame : frames) {
            Map<String, Object> event = DiglineRecorder.asMap(frame);
            if (event.get("chunk") instanceof Map<?, ?> chunk && chunk.get("bytes") instanceof String data) {
                events.add(DiglineRecorder.Json.parse(new String(
                        java.util.Base64.getDecoder().decode(data), StandardCharsets.UTF_8)));
            }
        }
        return events;
    }

    /** The model's id, from {@code /model/<id>/converse}, percent-decoded and nothing else. */
    static String modelIdOf(String path) {
        String[] parts = path.split("/");
        for (int i = 0; i + 1 < parts.length; i++) {
            if (parts[i].equals("model")) {
                return java.net.URLDecoder.decode(parts[i + 1].replace("+", "%2B"),
                        StandardCharsets.UTF_8);
            }
        }
        throw new IllegalArgumentException("no model in the path");
    }

    /** A subscriber that keeps a copy of every buffer it passes on, and says so at the end. */
    private static final class Tee implements Subscriber<ByteBuffer> {
        private final Subscriber<? super ByteBuffer> downstream;
        private final ByteArrayOutputStream kept;
        private final java.util.function.BiConsumer<byte[], Boolean> end;

        Tee(Subscriber<? super ByteBuffer> downstream, ByteArrayOutputStream kept,
                java.util.function.BiConsumer<byte[], Boolean> end) {
            this.downstream = downstream;
            this.kept = kept;
            this.end = end;
        }

        @Override
        public void onSubscribe(Subscription subscription) {
            downstream.onSubscribe(new Subscription() {
                @Override
                public void request(long n) {
                    subscription.request(n);
                }

                @Override
                public void cancel() {
                    subscription.cancel();
                    quietly(false);
                }
            });
        }

        @Override
        public void onNext(ByteBuffer buffer) {
            try {
                ByteBuffer copy = buffer.duplicate();
                byte[] bytes = new byte[copy.remaining()];
                copy.get(bytes);
                synchronized (kept) {
                    kept.write(bytes, 0, bytes.length);
                }
            } catch (RuntimeException ignored) {
                // What is kept is short; the reading says so at the end.
            }
            downstream.onNext(buffer);
        }

        @Override
        public void onError(Throwable failed) {
            quietly(false);
            downstream.onError(failed);
        }

        @Override
        public void onComplete() {
            quietly(true);
            downstream.onComplete();
        }

        private void quietly(boolean whole) {
            try {
                byte[] bytes;
                synchronized (kept) {
                    bytes = kept.toByteArray();
                }
                end.accept(bytes, whole);
            } catch (RuntimeException ignored) {
                // The recorder counts what it could not do; the stream goes on.
            }
        }
    }

    /**
     * The events of an AWS event stream, each as boto3 hands it over:
     * {@code {type: payload}}. A frame whose prelude or message checksum does
     * not match, or an exception the stream carries, is refused.
     */
    static List<Object> frames(byte[] bytes) {
        ByteBuffer buffer = ByteBuffer.wrap(bytes);
        List<Object> events = new ArrayList<>();
        while (buffer.remaining() > 0) {
            int start = buffer.position();
            int total = buffer.getInt();
            int headersLength = buffer.getInt();
            int preludeCrc = buffer.getInt();
            if (crc(bytes, start, 8) != preludeCrc) {
                throw new IllegalArgumentException("an event's prelude does not check");
            }
            Map<String, String> headers = new TreeMap<>();
            int headersEnd = buffer.position() + headersLength;
            while (buffer.position() < headersEnd) {
                String name = text(buffer, buffer.get() & 0xff);
                int type = buffer.get();
                switch (type) {
                    case 0, 1 -> { }
                    case 2 -> buffer.get();
                    case 3 -> buffer.getShort();
                    case 4 -> buffer.getInt();
                    case 5, 8 -> buffer.getLong();
                    case 6 -> buffer.position(buffer.position() + (buffer.getShort() & 0xffff));
                    case 7 -> headers.put(name, text(buffer, buffer.getShort() & 0xffff));
                    case 9 -> buffer.position(buffer.position() + 16);
                    default -> throw new IllegalArgumentException("an unknown header type");
                }
            }
            int payloadLength = total - headersLength - 16;
            byte[] payload = new byte[payloadLength];
            buffer.get(payload);
            int messageCrc = buffer.getInt();
            if (crc(bytes, start, total - 4) != messageCrc) {
                throw new IllegalArgumentException("an event's message does not check");
            }
            if (!"event".equals(headers.get(":message-type"))) {
                throw new StreamError();
            }
            Map<String, Object> event = new LinkedHashMap<>();
            event.put(headers.get(":event-type"), payloadLength == 0 ? new LinkedHashMap<>()
                    : DiglineRecorder.Json.parse(new String(payload, StandardCharsets.UTF_8)));
            events.add(event);
        }
        return events;
    }

    private static String text(ByteBuffer buffer, int length) {
        byte[] bytes = new byte[length];
        buffer.get(bytes);
        return new String(bytes, StandardCharsets.UTF_8);
    }

    private static int crc(byte[] bytes, int offset, int length) {
        CRC32 crc = new CRC32();
        crc.update(bytes, offset, length);
        return (int) crc.getValue();
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
        List<Object> blocks = blocks(reply);
        StringBuilder text = new StringBuilder();
        for (Object block : blocks) {
            if (block instanceof Map<?, ?> map && map.containsKey("text")) {
                text.append(map.get("text") instanceof String said ? said
                        : String.valueOf(map.get("text")));
            }
        }
        Object stop = reply.get("stopReason");
        return new DiglineRecorder.Call(caseCompartment, setup, text.toString(), latencyMs,
                usage(reply.get("usage")),
                DiglineRecorder.finishOf(DiglineRecorder.truthy(stop) ? String.valueOf(stop) : null,
                        FINISH),
                toolCalls(blocks));
    }

    /** One call, streamed: its events folded into the Converse reply the plugin builds. */
    static DiglineRecorder.Call streamed(Map<String, Object> request, List<Object> events,
            double latencyMs) {
        String role = "assistant";
        Map<Integer, Map<String, Object>> held = new TreeMap<>();
        Object stop = null;
        Object usage = null;
        for (Object raw : events) {
            if (!(raw instanceof Map<?, ?>)) {
                continue;
            }
            Map<String, Object> event = DiglineRecorder.asMap(raw);
            if (event.containsKey("messageStart")) {
                Object said = DiglineRecorder.asMap(event.get("messageStart")).getOrDefault("role",
                        "assistant");
                role = String.valueOf(said);
            } else if (event.containsKey("contentBlockStart")) {
                Map<String, Object> start = DiglineRecorder.asMap(event.get("contentBlockStart"));
                Object begun = start.get("start") instanceof Map<?, ?> map ? map.get("toolUse") : null;
                if (begun != null) {
                    Map<String, Object> use = DiglineRecorder.asMap(begun);
                    use.put("input", "");
                    Map<String, Object> block = new LinkedHashMap<>();
                    block.put("toolUse", use);
                    held.put(index(start.get("contentBlockIndex")), block);
                }
            } else if (event.containsKey("contentBlockDelta")) {
                Map<String, Object> delta = DiglineRecorder.asMap(event.get("contentBlockDelta"));
                int at = index(delta.get("contentBlockIndex"));
                Map<String, Object> change = delta.get("delta") instanceof Map<?, ?>
                        ? DiglineRecorder.asMap(delta.get("delta")) : Map.of();
                Map<String, Object> block = held.computeIfAbsent(at, key -> new LinkedHashMap<>());
                if (change.containsKey("text")) {
                    block.put("text", String.valueOf(block.getOrDefault("text", ""))
                            + String.valueOf(change.get("text")));
                } else if (change.containsKey("toolUse")) {
                    Map<String, Object> use = block.get("toolUse") instanceof Map<?, ?>
                            ? DiglineRecorder.asMap(block.get("toolUse")) : new LinkedHashMap<>(Map.of("input", ""));
                    Object more = DiglineRecorder.asMap(change.get("toolUse")).getOrDefault("input", "");
                    use.put("input", String.valueOf(use.getOrDefault("input", "")) + String.valueOf(more));
                    block.put("toolUse", use);
                }
            } else if (event.containsKey("messageStop")) {
                stop = DiglineRecorder.asMap(event.get("messageStop")).get("stopReason");
            } else if (event.containsKey("metadata")) {
                usage = DiglineRecorder.asMap(event.get("metadata")).get("usage");
            }
        }
        List<Object> content = new ArrayList<>();
        for (Map<String, Object> block : held.values()) {
            if (block.containsKey("toolUse")) {
                Map<String, Object> use = DiglineRecorder.asMap(block.get("toolUse"));
                Object raw = use.get("input");
                Object input = DiglineRecorder.truthy(raw) ? raw : "{}";
                use.put("input", input instanceof String written ? DiglineRecorder.Json.parse(written) : input);
                content.add(Map.of("toolUse", use));
            } else if (block.containsKey("text")) {
                content.add(Map.of("text", block.get("text")));
            }
        }
        Map<String, Object> message = new LinkedHashMap<>();
        message.put("role", role);
        message.put("content", content);
        Map<String, Object> reply = new LinkedHashMap<>();
        reply.put("output", Map.of("message", message));
        reply.put("stopReason", stop);
        if (usage != null) {
            reply.put("usage", usage);
        }
        return call(request, reply, latencyMs);
    }

    private static int index(Object value) {
        Long at = DiglineRecorder.count(value);
        if (at == null) {
            throw new IllegalArgumentException("a content block with no index");
        }
        return Math.toIntExact(at);
    }

    private static List<Object> blocks(Map<String, Object> reply) {
        if (!(reply.get("output") instanceof Map<?, ?> output)) {
            throw new IllegalArgumentException("the reply carries no output");
        }
        if (!(output.get("message") instanceof Map<?, ?> message)) {
            throw new IllegalArgumentException("the reply carries no output.message");
        }
        Object content = message.get("content");
        return content instanceof List<?> list ? new ArrayList<>(list) : List.of();
    }

    /** The counts, with the cache's beside the input, or {@code null}. */
    static DiglineRecorder.Usage usage(Object raw) {
        if (!(raw instanceof Map<?, ?>)) {
            return null;
        }
        Map<String, Object> usage = DiglineRecorder.asMap(raw);
        Object details = usage.get("cacheDetails");
        if (DiglineRecorder.truthy(details)) {
            if (!(details instanceof List<?> list)) {
                throw new IllegalArgumentException("usage.cacheDetails is not a list of cache writes");
            }
            for (Object detail : list) {
                if (!(detail instanceof Map<?, ?> entry)) {
                    throw new IllegalArgumentException("usage.cacheDetails holds an entry that is not a record");
                }
                tokens(entry.get("inputTokens"));
            }
        }
        if (usage.get("inputTokens") == null || usage.get("outputTokens") == null) {
            return null;
        }
        return new DiglineRecorder.Usage(tokens(usage.get("inputTokens")),
                tokens(usage.get("outputTokens")), tokens(usage.get("cacheReadInputTokens")),
                tokens(usage.get("cacheWriteInputTokens")), null);
    }

    /** A token count, 0 where absent, refused where it is not a number. */
    private static long tokens(Object value) {
        if (value == null || Boolean.FALSE.equals(value)) {
            return 0;
        }
        if (value instanceof Boolean || !(value instanceof Number number)) {
            throw new IllegalArgumentException("a usage count that is not a token count");
        }
        return number.longValue();
    }

    /**
     * The calls in the reply: a {@code toolUse} the application runs, so
     * {@code not_reported}; a server tool's with its {@code toolResult} in the
     * reply, an error by its text, a success whose payload is not recorded.
     * Never {@code null}.
     */
    static List<DiglineRecorder.ToolCall> toolCalls(List<Object> blocks) {
        Map<String, Map<String, Object>> outcomes = new LinkedHashMap<>();
        for (Object block : blocks) {
            if (block instanceof Map<?, ?> map && map.get("toolResult") instanceof Map<?, ?> result) {
                Map<String, Object> found = DiglineRecorder.asMap(result);
                outcomes.put(String.valueOf(found.getOrDefault("toolUseId", "")), found);
            }
        }
        List<DiglineRecorder.ToolCall> calls = new ArrayList<>();
        for (Object block : blocks) {
            if (!(block instanceof Map<?, ?> map) || !map.containsKey("toolUse")) {
                continue;
            }
            Map<String, Object> use = DiglineRecorder.asMap(map.get("toolUse"));
            String name = DiglineRecorder.name(use.get("name"));
            Object arguments = arguments(use.get("input"));
            Map<String, Object> outcome = "server_tool_use".equals(use.get("type"))
                    ? outcomes.get(String.valueOf(use.getOrDefault("toolUseId", ""))) : null;
            if (outcome == null) {
                calls.add(DiglineRecorder.ToolCall.asked(name, arguments));
            } else if ("error".equals(outcome.get("status"))) {
                String said = errorText(outcome);
                calls.add(new DiglineRecorder.ToolCall(name, arguments, "error", said,
                        said == null ? "not_reported" : null));
            } else {
                calls.add(new DiglineRecorder.ToolCall(name, arguments,
                        "success".equals(outcome.get("status")) ? "success" : "not_reported", null,
                        "not_recorded"));
            }
        }
        return calls;
    }

    private static Object arguments(Object value) {
        if (value == null || value instanceof Map<?, ?>) {
            return value;
        }
        return DiglineRecorder.Json.compact(DiglineRecorder.rounded(value));
    }

    private static String errorText(Map<String, Object> outcome) {
        List<String> parts = new ArrayList<>();
        Object content = outcome.get("content");
        for (Object item : content instanceof List<?> list ? list : List.of()) {
            if (!(item instanceof Map<?, ?> entry)) {
                continue;
            }
            if (entry.get("text") instanceof String said) {
                parts.add(said);
            } else if (entry.containsKey("json")) {
                parts.add(DiglineRecorder.Json.compact(DiglineRecorder.rounded(entry.get("json"))));
            }
        }
        return parts.isEmpty() ? null : String.join("\n", parts);
    }
}
