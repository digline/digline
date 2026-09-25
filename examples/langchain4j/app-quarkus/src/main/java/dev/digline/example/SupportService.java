package dev.digline.example;

import dev.langchain4j.data.message.SystemMessage;
import dev.langchain4j.data.message.UserMessage;
import dev.langchain4j.model.chat.ChatModel;
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
 * <p>Deliberately the same shape as app-spring's service of the same name. One
 * difference, invisible from outside: the model is injected here and built in a
 * constructor there, because the quarkus-langchain4j extension configures it
 * from {@code application.properties}.
 *
 * <p>There used to be a second difference — this service named the interface
 * {@code ChatLanguageModel} because the extension brought a langchain4j from
 * before that rename, while app-spring was already on {@code ChatModel}. The
 * extension caught up, and the two now read the same.
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

    @Inject ChatModel model;

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

    /** One answer, what it cost, and the counts that priced it. */
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
        TokenUsage usage = response.tokenUsage();
        Integer inputTokens = usage == null ? null : usage.inputTokenCount();
        Integer outputTokens = usage == null ? null : usage.outputTokenCount();
        return new Answer(
                response.aiMessage().text(),
                cost(inputTokens, outputTokens),
                elapsedMs,
                inputTokens,
                outputTokens);
    }

    private static double cost(Integer inputTokens, Integer outputTokens) {
        long in = inputTokens == null ? 0 : inputTokens;
        long out = outputTokens == null ? 0 : outputTokens;
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

    /**
     * What one call produced: the text, the money, the milliseconds, and the
     * counts behind the money.
     *
     * <p>The counts are boxed so they can be {@code null}, and that is the only
     * reason they are not {@code long}. A provider that reported no usage leaves
     * them unset, and the endpoint then leaves the field out of its answer
     * entirely — because digline records an absent count as absent and would
     * record a {@code 0} as a measurement. "We were not told" and "it used no
     * tokens" are different facts, and only one of them can be true.
     */
    public record Answer(
            String text,
            double costUsd,
            double elapsedMs,
            Integer inputTokens,
            Integer outputTokens) {}
}
