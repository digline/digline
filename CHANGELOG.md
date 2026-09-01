# Changelog

What changed for you, three lines a version. The reasoning lives in
[`docs/adr/`](docs/adr/); this says what to expect.

## 0.3.0 — 2026-09-01

digline 0.3.0. The plugins stay at 0.2.0: nothing in this release changes a
protocol they implement, and `config` is still the optional property it was.

- **Added:** `HttpTarget(config_path=…)`. An application digline cannot import
  can now say which model answered and how it was set up, in the same answer
  that already carries the cost — so a run from a Java or Go service is as
  complete a document as one from a plugin, and `compare` names a model change
  instead of reporting the configuration as unchanged (ADR 0005 §8). Left out,
  the target declares nothing, exactly as before.
- **Added:** `examples/langchain4j/` — a Spring Boot + LangChain4j service with
  one endpoint, the suite that evaluates it, and the CI gate. The walkthrough
  for a team whose application is not Python.
- **Fixed:** every example's CI workflow promoted the fresh run and *then*
  compared it, which compares a run with itself and passes whatever happened.
  They now compare against the baseline committed in the repository and key on
  the exit code. `prompt-first` and `rag` are shipped red on purpose, so theirs
  assert exit 1 — a green run there means the example stopped demonstrating
  what its README claims.
- **Fixed:** the four shipped example baselines were still schema 7 and could
  not be read by 0.2.0 at all — `compare` against them raised. Migrated in
  place. The workflow bug above is why nobody noticed.
- **Changed:** `execute()` asks a target for its `config` twice, before the
  first case and after the last, and records the second answer. A target that
  declares statically gives the same answer both times; nothing a plugin does
  changes.

## 0.2.0 — 2026-08-31

digline 0.2.0, digline-anthropic 0.2.0, digline-openai 0.2.0,
digline-bedrock 0.2.0. **Run files move to schema 8**, so stored runs and
baselines must be migrated once: `digline migrate --suite <your suite>` rewrites
them in place, and until it is run, `compare`, `report` and `promote` refuse a
schema-7 document rather than half-reading it. Migration is not a re-promotion —
the baseline keeps its key, its date and its scores, gains an empty
configuration, and compares as `unknown` against it.

- **Added:** a run records the configuration of the system under test —
  provider, model, token cap, temperature, region, endpoint host, and the shape
  the answer was asked for — as `target_config`, and the judge's as
  `judge_config` (ADR 0005). Not folded into `config_hash`: two runs at two
  temperatures stay comparable, which is the experiment.
- **Added:** `compare` names what moved instead of hashing it. The report, the
  terminal and `--json` say `temperature 0.3 → 0.7`, and where a regression
  lands in the same comparison the report says *"this drop coincides with
  temperature 0.3 → 0.7"* beside it.
- **Added:** a suite that grades with several judges records **which**
  instruments graded, one identity per distinct `provider/model`. Replacing one
  of two judges is reported as one removed and one added — and reported more
  strongly than a target change, because the scale moved rather than the thing
  measured.
- **Changed:** the headline no longer uses "configuration" for two different
  things. The first sentence is now **"The suite is unchanged from the
  reference."** — the rules — and "configuration" is left to mean how the
  system under test was set up. Both locales, the terminal, and `view`'s
  `OLDER SUITE` marker. A pipeline matching on the sentence rather than on
  `--json` needs updating.
- **Changed:** a plugin's `Target` and `Judge` now answer a `config` property.
  It is **optional**, like `preflight` and `artifacts`: a plain-function target
  and a hand-written fake judge keep working and simply record nothing.
- **Compatibility:** `SCHEMA_VERSION` 7 → 8, additive. A baseline with no
  recorded configuration compares as `unknown` rather than as a change.
  `OUTPUT_VERSION` is unchanged: `--json` only gained keys.
- **Privacy:** a model id and a decoding parameter travel in clear; `base_url`
  is recorded as a host and is withheld under redaction, exactly as an artifact
  is (ADR 0003 §4). No `Disclosure` releases it. `prefill` is not recorded —
  it is prompt, so it belongs to `Suite.artifacts` — and neither are
  `additional_request_fields`, `extra_body` or `token_param`.

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
