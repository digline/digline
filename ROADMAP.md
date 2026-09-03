# Digline Roadmap

This project moves by **tracks and gates, not dates**. Each track has an exit
gate; some tracks cannot start until evidence from real usage opens them. That
is deliberate: Digline's thesis is that quality regressions should be caught
by comparing against an approved, versioned baseline — and the roadmap itself
follows the same discipline. Features ship when validated, not when scheduled.

Two things will never be on this roadmap:

- **A hosted service that receives your payloads.** Prompts, outputs and the
  judge stay in your perimeter. Only verdicts and redacted runs are ever
  designed to travel.
- **Usage data collection, ever.** Digline makes no network calls except the
  ones your suite explicitly configures.

---

## Track A — Provider coverage

*Status: completed*

Complete and stabilize the provider plugins under the plugin contract
(ADR 0004: every plugin ships Target + Judge + ClaimJudge).

- [x] `digline-anthropic`
- [x] `digline-openai` (incl. OpenAI-compatible endpoints via `base_url`)
- [x] `digline-bedrock` (Converse API; per-region pricing; conservative price
      seeding — unknown model/region fails preflight rather than guessing)
- [x] Price sentinel in CI: compare hardcoded plugin prices against a public
      dataset and open an issue/PR with the diff when they drift

**Exit gate:** three providers published, symmetric, and boring.

## Track B — Verdict credibility

*Status: completed*

A regression tool that mistakes noise for regression is worse than no tool.
This track makes the verdict itself trustworthy.

- [x] Record the configuration of the system under test (model, temperature,
      sampling parameters where the provider exposes them) in runs and
      baselines; `compare` highlights which parameters changed between the
      two (ADR 0005) — shipped in 0.2.0, extended in 0.3.0 to targets Digline
      cannot import, which report theirs in the answer (ADR 0005 §8)
- [x] Repeated runs per case: score as a distribution, not a single sample —
      `Suite.samples` folds N calls per case, and since ADR 0006 the raw
      per-sample scores and the interval they span are recorded on the verdict
      and travel with it
- [x] Regression thresholds expressed relative to measured variance, not as
      absolute deltas — a drop is a regression only when it leaves the interval
      the *baseline* observed across its own samples (ADR 0006 §5), and an
      aggregate gets an interval of its own from one evaluation per sample
      index (§7). The observed min and max rather than a variance: five samples
      do not earn a distributional assumption, and a reader can check a min
      against the raw values printed beside it

**Exit gate:** a baseline comparison can state, honestly, whether an observed
difference is signal or sampling noise. **Met** — the two runs in
`tests/fixtures/brief/` are the case it was written against, and the test that
reads them fails if it stops being met.

## Track C — Adoption and developer experience

*Status: ongoing, low ceremony*

- [ ] Try-without-installing: a Codespace on the examples repo — you test it
      in the browser, but in *your* environment, because Digline has no server
      by design
- [ ] The run/baseline JSON format documented as a **versioned public
      contract**. The engine is Python; the contract is language-neutral
- [x] A LangChain example evaluated in process: the target is a function
      that invokes the chain, so there is no server and no HTTP, and the
      default path runs on a fake chat model — no key, no network, and CI runs
      it (`examples/langchain/`)
- [x] A LangChain4j example over `HttpTarget`: one endpoint reporting the
      answer, what the call cost, and which model answered under what settings
      — so a run from a service Digline cannot import is as complete a document
      as one from a plugin (`examples/langchain4j/`, ADR 0005 §8)
- [x] A declarative suite format, `digline run suite.toml` (ADR 0007) —
      implemented on `adr-0007`, ships in 0.5.0. TOML rather than YAML:
      `tomllib` is in the standard library from 3.11, and a suite format that
      costs a runtime dependency to read would double the one this project has.
      It arrived together with **providers as entry points** — fixed decision
      6, stated since the first commit and real from 0.5.0, because a judge
      named in data has to be resolvable without anything under `src/`
      importing a plugin. Scope was the assertions whose parameters are already
      data; a custom assertion, a custom target and a `Disclosure` stay Python,
      and the loader says so by name
- [ ] README pass with fresh eyes: assume the reader arrived five minutes ago
- [ ] An official container image, `ghcr.io/digline/digline`: the CLI and the
      three provider plugins, published by the release workflow on a `v*` tag.
      For the reader who wants the cycle in CI without a Python toolchain of
      their own. Not started — no `Dockerfile` exists yet, and the shape of the
      thing is the open question: the image mounts the repository, because
      `.digline/` lives there and never in the container

This replaces *"a thin JVM emitter"*, which was on this list and was wrong. An
emitter means the JVM side runs its own assertions and posts the verdicts, which
is a **second engine**: two implementations of what `contains` means, drifting
apart, with the run format as the only thing holding them together. The one
place that is allowed to happen is nowhere. `HttpTarget` keeps one engine and
one set of assertion semantics, and asks the application only for what it alone
can know — its answer, its cost, its configuration.

**Exit gate:** someone who is not the author sets up a suite without asking
the author anything.

---

The two tracks below are **gated on evidence from real production pilots**,
not on a feature schedule. If you run LLM calls in production and want to be
one of those pilots, open an issue — that is the fastest way to move them.

## Track D — Production (world 2)

*Status: design open, implementation gated on pilot evidence*

Everything below is a **hypothesis under validation**, not a commitment.

- Push ingestion over HTTP (runs emitted from any language)
- A transparent proxy as a third capture path — point your agent's base URL
  at it, zero code changes. Honest caveats: correlation metadata (tenant, run
  boundaries) is still required, and an in-path component carries production
  obligations (latency, availability) that a shadow-path library does not
- Traffic → cases: turning captured production traffic into evaluable cases
  and golden candidates, cleanly separated from the noise around them
- Redaction as a first-class transformation: per-tenant HMAC digests,
  scrubbing of provider error payloads — the payload stays where it is born;
  the verdict travels
- A production store (Postgres) alongside the file store
- Agent trajectories with **readable reasoning**: not just which tools were
  called in which order, but a non-technical account of why — extending the
  existing principle that reports must be legible to people who don't code
- Open question, deliberately undecided: a reactive mode ("is this specific
  output valid, right now?") as opposed to the retrospective one

## Track E — Fleet (world 3)

*Status: titles only, entirely dependent on the same pilot evidence*

For software houses maintaining AI features across many end clients: a fleet
console, redacted runs traveling per tenant, per-client reports. Nothing here
is designed yet — on purpose.

---

*Suggestions and war stories are welcome as issues.*
