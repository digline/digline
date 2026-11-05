/*
 * digline's recorder for Java: Anthropic's Messages API, read as JSON, for the
 * hooks that carry it: DiglineAnthropic, for a direct call, and DiglineAws,
 * for Bedrock's InvokeModel with an Anthropic model.
 *
 * RECORDING_VERSION 1, written to the contract as it stood on 2026-11-05:
 * https://github.com/digline/digline/blob/main/docs/recording-format.md
 *
 * Copy it beside DiglineRecorder.java, under the package dev.digline. It
 * needs the JDK and nothing else.
 *
 * Licensed as digline is: Apache-2.0.
 */
package dev.digline;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;

/**
 * A Messages request split into its case and its setup, and a Messages reply,
 * whole or as its events, read into a call, as digline's Anthropic map reads
 * them. One reading of Messages for every hook that meets it, so a call made
 * to Anthropic directly and one made through Bedrock are read alike.
 */
final class DiglineMessages {

    private DiglineMessages() {
    }

    /** The request's keys that are neither the case nor the setup. */
    static final Set<String> NOT_SETUP = Set.of("messages", "stream", "extra_headers",
            "extra_query", "timeout", "metadata");

    /** {@code stop_reason} in digline's vocabulary. */
    static final Map<String, String> FINISH = Map.of("end_turn", "stop", "stop_sequence", "stop",
            "max_tokens", "length", "model_context_window_exceeded", "length", "tool_use",
            "tool_use", "refusal", "filtered", "pause_turn", "other");

    /** The blocks whose input arrives as JSON in pieces. */
    static final Set<String> TRACKS_TOOL_INPUT = Set.of("tool_use", "server_tool_use");

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
                content.add(DiglineRecorder.asMap(block));
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
            Map<String, Object> event = DiglineRecorder.asMap(raw);
            Object type = event.get("type");
            if (snapshot == null) {
                if (!"message_start".equals(type)) {
                    throw new IllegalArgumentException("an event before message_start");
                }
                snapshot = DiglineRecorder.asMap(event.get("message"));
                if (snapshot.get("content") instanceof List<?> blocks) {
                    for (Object block : blocks) {
                        content.add(DiglineRecorder.asMap(block));
                    }
                }
                continue;
            }
            if ("content_block_start".equals(type)) {
                content.add(DiglineRecorder.asMap(event.get("content_block")));
            } else if ("content_block_delta".equals(type)) {
                int at = Math.toIntExact((Long) event.get("index"));
                Map<String, Object> block = content.get(at);
                Map<String, Object> delta = DiglineRecorder.asMap(event.get("delta"));
                if ("text_delta".equals(delta.get("type")) && "text".equals(block.get("type"))) {
                    block.put("text", String.valueOf(block.get("text")) + delta.get("text"));
                } else if ("input_json_delta".equals(delta.get("type"))
                        && TRACKS_TOOL_INPUT.contains(block.get("type"))) {
                    inputs.computeIfAbsent(at, key -> new StringBuilder())
                            .append((String) delta.get("partial_json"));
                }
            } else if ("message_delta".equals(type)) {
                Map<String, Object> delta = DiglineRecorder.asMap(event.get("delta"));
                snapshot.put("stop_reason", delta.get("stop_reason"));
                Map<String, Object> usage = snapshot.get("usage") instanceof Map<?, ?>
                        ? DiglineRecorder.asMap(snapshot.get("usage")) : new LinkedHashMap<>();
                Map<String, Object> more = DiglineRecorder.asMap(event.get("usage"));
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
        Map<String, Object> usage = DiglineRecorder.asMap(raw);
        Long input = DiglineRecorder.count(usage.get("input_tokens"));
        Long output = DiglineRecorder.count(usage.get("output_tokens"));
        if (input == null || output == null) {
            return null;
        }
        Long read = DiglineRecorder.count(usage.get("cache_read_input_tokens"));
        Long written = DiglineRecorder.count(usage.get("cache_creation_input_tokens"));
        Long thinking = null;
        if (usage.get("output_tokens_details") instanceof Map<?, ?> details) {
            thinking = DiglineRecorder.count(details.get("thinking_tokens"));
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
            String name = DiglineRecorder.name(block.get("name"));
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
                code = DiglineRecorder.truthy(error) ? String.valueOf(error) : word;
            }
            calls.add(code == null
                    ? new DiglineRecorder.ToolCall(name, arguments, "success", null, "not_recorded")
                    : new DiglineRecorder.ToolCall(name, arguments, "error", code, null));
        }
        return calls;
    }
}
