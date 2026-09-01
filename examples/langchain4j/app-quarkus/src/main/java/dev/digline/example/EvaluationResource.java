package dev.digline.example;

import jakarta.inject.Inject;
import jakarta.ws.rs.Consumes;
import jakarta.ws.rs.POST;
import jakarta.ws.rs.Path;
import jakarta.ws.rs.Produces;
import jakarta.ws.rs.core.MediaType;
import java.util.LinkedHashMap;
import java.util.Map;

/**
 * The one endpoint digline calls — the same one app-spring exposes, to the
 * byte. JAX-RS instead of Spring MVC; the contract does not know the difference.
 *
 * <p>Three fields, and each answers a question digline cannot answer for itself
 * once the model call happens on this side of HTTP:
 *
 * <ul>
 *   <li>{@code data} — what the assistant said, which is what gets judged.
 *   <li>{@code usage} — what the call cost and how long it took. digline cannot
 *       price a call it did not make, so the service reports it.
 *   <li>{@code config} — which model answered and how it was set up. Without it
 *       a run records nothing about the system under test, and the day somebody
 *       changes the model the comparison says the configuration is unchanged.
 *       (digline ADR 0005 §8)
 * </ul>
 *
 * <p>The keys under {@code config} are a closed set — digline refuses one it
 * does not know rather than recording it, because an open bag of fields is
 * where a customer identifier ends up.
 */
@Path("/evaluate")
public class EvaluationResource {

    @Inject SupportService support;

    @POST
    @Consumes(MediaType.APPLICATION_JSON)
    @Produces(MediaType.APPLICATION_JSON)
    public Map<String, Object> evaluate(Map<String, String> body) {
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
