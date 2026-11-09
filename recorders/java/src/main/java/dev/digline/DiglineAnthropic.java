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
import java.util.List;
import java.util.Map;
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
            Map<String, Object> sent = DiglineRecorder.asMap(
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
            if (sent != null) {
                recorder.refused(response.statusCode(), at);
            }
            if (sent == null || response.statusCode() < 200 || response.statusCode() > 299) {
                return response;
            }
            boolean streamed = response.headers().values("Content-Type").stream()
                    .anyMatch(value -> value.contains("text/event-stream"));
            return new Replaced(response, new DiglineRecorder.Kept(response.body(),
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
                    recorder.record(DiglineMessages.streamed(sent, events, elapsed), at);
                } else {
                    recorder.record(DiglineMessages.call(sent, DiglineRecorder.asMap(DiglineRecorder.Json.parse(text)),
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
}
