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
 *   <li>{@code usage} — what the call cost, how long it took, and the token
 *       counts behind the price. digline cannot price a call it did not make,
 *       so the service reports it. {@code usage.tokens} is its own object,
 *       closed to digline's own count names.
 *   <li>{@code config} — which model answered and how it was set up. Without it
 *       a run records nothing about the system under test, and the day somebody
 *       changes the model the comparison says the configuration is unchanged.
 *       (digline ADR 0005 §8)
 * </ul>
 *
 * <p>The keys under {@code config} are a closed set — digline refuses one it
 * does not know rather than recording it, because an open bag of fields is
 * where a customer identifier ends up.
 *
 * <p><b>And the configuration this reports is not reviewed by anything on this
 * side.</b> Whatever this method puts in {@code model} is what a digline run
 * records and what crosses a boundary, so the suite declares
 * {@code expect_config} and digline refuses an answer that contradicts it
 * (ADR 0030 §4). Nothing here changes for that — the endpoint reports, and the
 * agreement is checked on the other side. It is worth knowing which of the two
 * is the reviewed value: the one in the suite.
 *
 * <p><b>The fourth field, for an application that has one.</b> This assistant
 * calls no tools, so it reports none — and a demonstration that invented some
 * would be demonstrating nothing. An application that does call tools reports
 * its trajectory in the same answer, under a key the suite names with
 * {@code tool_calls_path}; each call carries a tool name, its arguments, a
 * mandatory {@code status} of {@code success}, {@code error} or
 * {@code not_reported}, and a result. The JSON is in this example's README,
 * under "If your application calls tools", and it is written there rather than
 * here so that the two endpoints stay the peers the pair exists to be.
 *
 * <p>{@code status} having no default is the part worth carrying across: a tool
 * that ran and failed must not be able to report as one that worked by saying
 * nothing.
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
        // A second object under `usage`, beside the money and not merged into
        // it, read by its own `usage_path = "usage.tokens"`. digline closes this
        // one to its own count names, so a `cost_usd` sitting among them would
        // be refused as a count under a name nothing adds up — the two facts
        // travel together and stay two objects.
        //
        // Left out entirely when the provider reported no usage. A `0` here
        // would be a measurement digline records and nobody made.
        if (answer.inputTokens() != null && answer.outputTokens() != null) {
            Map<String, Object> tokens = new LinkedHashMap<>();
            tokens.put("input_tokens", answer.inputTokens());
            tokens.put("output_tokens", answer.outputTokens());
            usage.put("tokens", tokens);
        }

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
