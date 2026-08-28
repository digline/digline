# Changelog

What changed for you, three lines a version. The reasoning lives in
[`docs/adr/`](docs/adr/); this says what to expect.

## digline-bedrock 0.1.0 — 2026-08-28

Tag `digline-bedrock-v0.1.0`; nothing in the core changed.

- **Added:** `BedrockTarget`, `BedrockJudge` and `BedrockClaimJudge`, on the
  Converse API. The region is resolved at construction, not at the first call,
  so a missing one fails before anything is paid for; `bedrock_pricing(region)`
  is the price list for the region you actually called, and `free()` covers a
  model billed by provisioned capacity.
- **Added:** ARNs are scrubbed out of error messages — an account id does not
  belong in a `Verdict.reason` that ends up in a committed baseline.
- **Added:** the cache-read convention was verified against the live API:
  Converse reports cached input **outside** `inputTokens`, so it is added, not
  subtracted, when the cost is computed.

## 0.1.3 — 2026-08-28

Tag `v0.1.3`: digline 0.1.3, digline-anthropic 0.1.1, digline-openai 0.1.0.

- **Added:** `JudgeBase` in `digline.targets` is public API. A plugin now ships
  a target *and* a judge — `Target` + `Judge` + `ClaimJudge` — instead of the
  core owning a judge it cannot call (ADR 0004).
- **Added:** `digline-openai`, with `OpenAITarget`, `OpenAIJudge` and
  `OpenAIClaimJudge`. `base_url` points them at any OpenAI-compatible provider,
  and the JSON parser is lenient: `response_format` is an optimisation, so a
  provider that refuses it falls back to reading the object out of the reply.
- **Added:** `AnthropicJudge` and `AnthropicClaimJudge` in `digline-anthropic`.
- **Added:** a judge counts what it spends — `calls`, `spent_usd`, `latency_ms`
  — so the budget covers the judging, not only the answer under test.
- **Docs:** "Requires Python 3.12+" in the README and on each plugin's install
  page, where it is read before the install fails instead of after.

## 0.1.2 — 2026-08-27

- **Fixed:** a rubric score landing exactly on the threshold inside `Repeated`
  produced `error` instead of `pass`.
- **Changed:** every assertion that asks a judge now sends one prompt shape —
  instruction first, `Output to judge:` last and once, exported as
  `JUDGE_OUTPUT_LABEL`. `Faithfulness` used a different label and a trailing
  line; judges that parsed the old shape need updating.
- **Added:** `HttpTarget`, for an application digline cannot import.

## 0.1.1 — 2026-08-27

- **Changed:** `digline --help` describes the command instead of printing the
  module's docstring.

## 0.1.0 — 2026-08-26

- First release: the offline cycle — write a suite, run, promote, compare,
  report — with the baseline committed in your own repository.
