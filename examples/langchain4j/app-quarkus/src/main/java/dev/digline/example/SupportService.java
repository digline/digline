package dev.digline.example;

import dev.langchain4j.data.message.SystemMessage;
import dev.langchain4j.data.message.UserMessage;
import dev.langchain4j.model.chat.ChatLanguageModel;
import dev.langchain4j.model.chat.request.ChatRequest;
import dev.langchain4j.model.chat.response.ChatResponse;
import dev.langchain4j.model.output.TokenUsage;
import jakarta.enterprise.context.ApplicationScoped;
import jakarta.inject.Inject;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import org.eclipse.microprofile.config.inject.ConfigProperty;

/**
 * The thing being evaluated: a system prompt and a model, behind one method.
 *
 * <p>Deliberately the same shape as app-spring's service of the same name. Two
 * differences, both invisible from outside. The model is injected here and
 * built in a constructor there, because the quarkus-langchain4j extension
 * configures it from {@code application.properties}. And the interface is
 * {@code ChatLanguageModel} rather than {@code ChatModel}: the extension
 * currently brings langchain4j 1.0.0-beta2, which is before the rename that
 * app-spring's 1.0.1 is after.
 *
 * <p>Neither reaches the endpoint. That is the point of the pair: what digline
 * evaluates is the contract, and the contract does not know any of this.
 */
@ApplicationScoped
public class SupportService {

    /**
     * List prices in USD per million tokens, read from openai.com/pricing on
     * 2026-08-27.
     *
     * <p>Hardcoded and dated for the same reason as in app-spring: a price is a
     * fact about a day, digline cannot price a call it did not make, and this
     * number is the one that reaches {@code CostBudget}. Keep the two services
     * in step, or the same suite measures two different costs.
     */
    private static final double INPUT_PER_MTOK = 0.15;

    private static final double OUTPUT_PER_MTOK = 0.60;

    @Inject ChatLanguageModel model;

    @ConfigProperty(name = "support.model")
    String modelName;

    @ConfigProperty(name = "support.temperature")
    double temperature;

    @ConfigProperty(name = "support.max-tokens")
    int maxTokens;

    private String systemPrompt;

    /** The shared prompt, packaged from ../prompts by the build. */
    String systemPrompt() {
        if (systemPrompt == null) {
            try (InputStream in =
                    Thread.currentThread()
                            .getContextClassLoader()
                            .getResourceAsStream("prompts/system.txt")) {
                if (in == null) {
                    throw new IllegalStateException("prompts/system.txt is not on the classpath");
                }
                systemPrompt = new String(in.readAllBytes(), StandardCharsets.UTF_8);
            } catch (IOException exc) {
                throw new IllegalStateException("cannot read prompts/system.txt", exc);
            }
        }
        return systemPrompt;
    }

    /** One answer, and what it cost to produce. */
    public Answer answer(String question) {
        long started = System.nanoTime();
        ChatResponse response =
                model.chat(
                        ChatRequest.builder()
                                .messages(
                                        SystemMessage.from(systemPrompt()),
                                        UserMessage.from(question))
                                .build());
        double elapsedMs = (System.nanoTime() - started) / 1_000_000.0;
        return new Answer(response.aiMessage().text(), cost(response.tokenUsage()), elapsedMs);
    }

    private static double cost(TokenUsage usage) {
        if (usage == null) {
            return 0.0;
        }
        long in = usage.inputTokenCount() == null ? 0 : usage.inputTokenCount();
        long out = usage.outputTokenCount() == null ? 0 : usage.outputTokenCount();
        return (in * INPUT_PER_MTOK + out * OUTPUT_PER_MTOK) / 1_000_000.0;
    }

    public String modelName() {
        return modelName;
    }

    public double temperature() {
        return temperature;
    }

    public int maxTokens() {
        return maxTokens;
    }

    /** What one call produced: the text, the money, the milliseconds. */
    public record Answer(String text, double costUsd, double elapsedMs) {}
}
