package dev.digline;

import static org.junit.jupiter.api.Assertions.assertEquals;

import dev.langchain4j.model.chat.response.ChatResponse;
import dev.langchain4j.model.chat.response.StreamingChatResponseHandler;
import dev.langchain4j.model.openai.OpenAiChatModel;
import dev.langchain4j.model.openai.OpenAiStreamingChatModel;
import java.util.Map;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;

/**
 * The calls the CI job {@code through-the-proxy} makes from Java: LangChain4j's
 * OpenAI model, single and streamed, pointed at {@code digline record proxy}
 * by {@code baseUrl} and {@code customHeaders}. The question is the one in
 * {@code recorders/through-the-proxy.json}; LangChain4j builds the rest of the
 * request itself.
 */
class ThroughTheProxyTest {

  static final String PROXY = System.getProperty("digline.proxy", "http://127.0.0.1:8787");
  static final Map<String, String> HEADERS = Map.of("X-Digline-Suite", "triage", "X-Digline-App", "java");
  static final String QUESTION = "What is the capital of France?";

  @Test
  void aSingleCallAndAStreamGoThroughTheProxy() throws Exception {
    OpenAiChatModel model = OpenAiChatModel.builder()
        .baseUrl(PROXY + "/v1")
        .apiKey("via-proxy")
        .modelName("gpt-test")
        .maxTokens(16)
        .customHeaders(HEADERS)
        .build();
    assertEquals("Paris", model.chat(QUESTION));

    OpenAiStreamingChatModel streaming = OpenAiStreamingChatModel.builder()
        .baseUrl(PROXY + "/v1")
        .apiKey("via-proxy")
        .modelName("gpt-test")
        .maxTokens(16)
        .customHeaders(HEADERS)
        .build();
    CompletableFuture<ChatResponse> done = new CompletableFuture<>();
    streaming.chat(QUESTION, new StreamingChatResponseHandler() {
      @Override
      public void onPartialResponse(String partial) {}

      @Override
      public void onCompleteResponse(ChatResponse response) {
        done.complete(response);
      }

      @Override
      public void onError(Throwable error) {
        done.completeExceptionally(error);
      }
    });
    assertEquals("Paris", done.get(30, TimeUnit.SECONDS).aiMessage().text());
  }
}
