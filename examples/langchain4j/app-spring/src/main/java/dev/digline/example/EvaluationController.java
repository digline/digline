package dev.digline.example;

import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

/**
 * The one endpoint digline calls. This is the whole integration.
 *
 * <p>Three fields, and each answers a question digline cannot answer for
 * itself once the model call happens on this side of HTTP:
 *
 * <ul>
 *   <li>{@code data} — what the assistant said, which is what gets judged.
 *   <li>{@code usage} — what the call cost and how long it took. digline
 *       cannot price a call it did not make, so the service reports it.
 *   <li>{@code config} — which model answered and how it was set up. Without
 *       it a run records nothing about the system under test, and the day
 *       somebody changes the model the comparison says the configuration is
 *       unchanged. (digline ADR 0005 §8)
 * </ul>
 *
 * <p>The keys under {@code config} are a closed set — digline refuses one it
 * does not know rather than recording it, because an open bag of fields is
 * where a customer identifier ends up. Report only what decided how the model
 * answered.
 */
@RestController
public class EvaluationController {

    private final SupportService support;

    public EvaluationController(SupportService support) {
        this.support = support;
    }

    @PostMapping(value = "/evaluate", produces = MediaType.APPLICATION_JSON_VALUE)
    public Map<String, Object> evaluate(@RequestBody Map<String, String> body) {
        SupportService.Answer answer = support.answer(body.get("question"));

        Map<String, Object> usage = new LinkedHashMap<>();
        usage.put("cost_usd", answer.costUsd());
        usage.put("elapsed_ms", answer.elapsedMs());

        Map<String, Object> config = new LinkedHashMap<>();
        config.put("provider", "openai");
        config.put("model", support.modelName());
        config.put("temperature", support.temperature());
        config.put("max_tokens", support.maxTokens());

        Map<String, Object> out = new LinkedHashMap<>();
        out.put("data", answer.text());
        out.put("usage", usage);
        out.put("config", config);
        return out;
    }
}
