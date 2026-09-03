# Changelog

What changed for you, three lines a version. The reasoning lives in
[`docs/adr/`](docs/adr/); this says what to expect.

## 0.5.0 — unreleased

digline 0.5.0, with digline-anthropic, digline-openai and digline-bedrock at
0.3.0. The plugins move because they now register themselves, and their
`digline>=` floor moves with them: a plugin at 0.3.0 needs a core that has
`Provider`, and claiming otherwise would resolve for somebody and then fail on
import.

- **Added:** a suite can be **TOML**. `digline run --suite eval/suite.toml`
  reads `[suite]`, an ordered `[[assertions]]` list with the check named by
  `type`, and a `[target]` that is either an HTTP endpoint or a provider. The
  extension chooses the format; there is no new flag. Cases are always a
  separate file, because a rule and a case change at different rhythms and a
  diff has to say which one moved. The loader builds the same objects the
  Python form builds — the same assertion identities and the same
  `config_hash` — so a suite can be ported between the two forms **without
  re-promoting its baseline**. (ADR 0007, and
  [`docs/declarative.md`](docs/declarative.md))
- **Added:** providers are found through **entry points**. Each plugin
  registers its name under `digline.providers`, and a suite names a judge or a
  target by coordinate — `judge = "anthropic/claude-haiku-4-5"`, which is the
  same `provider/model` identity a run already records. Resolution is by name
  and never by import: nothing shipped with digline imports a plugin, and
  resolving one provider does not load the others. Fixed decision 6 in
  `CLAUDE.md` has said this since the first commit; this is the release where
  it is true. (ADR 0007 §3)
- **Added:** `HttpTarget(body=…)`, a table shaped like the payload whose
  leaves name case fields — `question = "case.vars.question"`. One level of
  reference and no expressions, so the nesting, the arrays and the types of a
  real body survive. Additive: `request=` is untouched and remains what a body
  that has to be *computed* is written with. A reference that names no case
  field is refused when the suite loads, not once per case half way through a
  run.
- **Added:** `examples/quickstart-toml/` — the two-file suite against a local
  stub, with no Python in it and no key anywhere. The stub reports `config`
  like a real service, so the example shows the sentence that says the answer
  got worse while the model did not change.
- **Changed:** what a TOML suite cannot express, it refuses **by name**. An
  unknown key is a load error with the near miss when there is one — a
  silently dropped `treshold` would be a check running on the default that
  passes — and a custom judge, a computed body, a custom assertion or a
  `disclosure` gets a sentence saying which wall it is and where to go. A
  credential is refused outright: there is no `api_key` in this format, and
  each provider's SDK reads the key from the environment.
- **Note:** `disclosure` is not settable from a data file, deliberately. What
  it widens is what leaves a perimeter, and a suite that is data cannot widen
  it — in world 3 that is a security property, not a missing feature. A suite
  that genuinely needs to disclose more is a `suite.py`.
- **Unchanged:** `SCHEMA_VERSION` stays at 9. No baseline needs re-promoting,
  no run needs migrating, and no example was re-recorded: nothing downstream
  can tell how a `Suite` was built, which is the point.

## 0.4.0 — 2026-09-02

digline 0.4.0. The plugins stay at 0.2.0: a sample is taken by the driver,
which calls a target the same way it always did, so nothing in this release
changes a protocol they implement.

- **Added:** a **noise floor**. A sampled check now records the raw per-sample
  scores and the interval they span, and `compare` reads the *baseline's*
  interval: a movement that lands inside it is `unchanged`, with
  `within_noise` on the delta and a sentence saying so in the report and in
  `--json`. Nothing rescues a flip, an interval of zero width is not a floor,
  and a baseline with no interval keeps the absolute rule. Two controls now
  exist and the reason says which one spoke: `tolerance` is *declared* — what a
  reviewer allows — and this one is *measured*. (ADR 0006)
- **Added:** aggregates get an interval of their own. Precision and accuracy are
  computed once per run and so have no samples, but the noise they need sizing
  against is real — one case in twenty-one moving and coming back was what
  prompted the ADR. The driver evaluates each aggregate once more per sample
  index and records those N values. No call to a target, no call to a judge, and
  the recorded score is unchanged. (ADR 0006 §7)
- **Added:** `digline run` announces the multiplied call count on stderr before
  the first call — `20 cases × 5 samples = 100 calls to the target`. Arithmetic
  over the declared suite; a suspended case is not counted, and a `Repeated` is
  named with its own factor. A money estimate is deferred to an ADR of its own:
  it would need a new optional method on every target. (ADR 0006 §8)
- **Changed:** `SCHEMA_VERSION` 8 → 9, additively. **No baseline needs
  re-promoting and no example was re-recorded**: the score is still the mean, so
  every stored number is the one this release computes, and the migration
  *derives* the new fields from the `metadata["scores"]` a sampled run already
  carried. A run at `samples=1` gains only the version number. Run
  `digline migrate` after upgrading — a stored run at schema 8 is skipped by a
  scan and refused by name until you do. Aggregate intervals are the one thing
  migration cannot supply; they arrive with your next promotion.
- **Added:** `examples/langchain/` — a LangChain pipeline evaluated in process:
  the target is a function that invokes the chain, so there is no server and no
  HTTP. The default path runs on LangChain's own `FakeListChatModel`, which is
  what CI runs — no key, no network — and `DIGLINE_LIVE=1` puts a real model
  under the chain and `AnthropicJudge` behind the rubric. Tested against
  langchain 1.3.18.
- **Added:** `ci.yml` builds the digline.dev site on every push — the site's own
  config and its own sync script, `mkdocs build --strict` — so a relative link
  in an example README, or an example with no entry in the site's nav, fails on
  the pull request instead of in `publish.yml`, where the build runs *after*
  PyPI. `tests/test_examples.py` checks the nav entry too, and names the example
  and the line to add. Both are on the pre-tag checklist in `RELEASING.md`.
- **Note on 0.3.0:** the tag `v0.3.0` is the release that is on PyPI and needs
  nothing done to it, but the examples at that commit do not resolve — they
  still pinned `digline<0.2` while their baselines had moved to schema 8, and
  `examples/langchain4j/` was missing the `[tool.pyright]` block that keeps
  pyright out of the virtualenv. Three commits on `main` after the tag fixed
  both, along with the README links that failed the site build. If you are
  reading the examples, read them from `main`, not from the tag.

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
