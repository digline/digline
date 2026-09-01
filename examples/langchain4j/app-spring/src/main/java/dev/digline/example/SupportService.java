package dev.digline.example;

import dev.langchain4j.data.message.SystemMessage;
import dev.langchain4j.data.message.UserMessage;
import dev.langchain4j.model.chat.ChatModel;
import dev.langchain4j.model.chat.request.ChatRequest;
import dev.langchain4j.model.chat.response.ChatResponse;
import dev.langchain4j.model.openai.OpenAiChatModel;
import dev.langchain4j.model.output.TokenUsage;
import java.nio.charset.StandardCharsets;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.ClassPathResource;
import org.springframework.stereotype.Service;
import org.springframework.util.StreamUtils;

/**
 * The thing being evaluated: a system prompt and a model, behind one method.
 *
 * <p>Everything the evaluation needs to record is decided here — the prompt
 * file, the model name, the decoding parameters, and the price list used to
 * turn a token count into money. That is why {@link SupportController} can
 * report them without asking anyone.
 */
@Service
public class SupportService {

    /**
     * List prices in USD per million tokens, read from openai.com/pricing on
     * 2026-08-27.
     *
     * <p>Hardcoded on purpose, and dated on purpose: the price is a fact about
     * a day, and the only honest thing a copy of one can carry is when it was
     * copied. digline cannot price a call it did not make, so this number is
     * the one that reaches {@code CostBudget}. When it goes stale, the budget
     * quietly measures the wrong thing — so keep the date beside it.
     */
    private static final double INPUT_PER_MTOK = 0.15;

    private static final double OUTPUT_PER_MTOK = 0.60;

    private final ChatModel model;
    private final String systemPrompt;
    private final String modelName;
    private final double temperature;
    private final int maxTokens;

    public SupportService(
            @Value("${support.model}") String modelName,
            @Value("${support.temperature}") double temperature,
            @Value("${support.max-tokens}") int maxTokens,
            @Value("${OPENAI_API_KEY:}") String apiKey)
            throws Exception {
        this.modelName = modelName;
        this.temperature = temperature;
        this.maxTokens = maxTokens;
        this.systemPrompt =
                StreamUtils.copyToString(
                        new ClassPathResource("prompts/system.txt").getInputStream(),
                        StandardCharsets.UTF_8);
        this.model =
                OpenAiChatModel.builder()
                        .apiKey(apiKey)
                        .modelName(modelName)
                        .temperature(temperature)
                        .maxTokens(maxTokens)
                        .build();
    }

    /** One answer, and what it cost to produce. */
    public Answer answer(String question) {
        long started = System.nanoTime();
        ChatResponse response =
                model.chat(
                        ChatRequest.builder()
                                .messages(
                                        SystemMessage.from(systemPrompt),
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
